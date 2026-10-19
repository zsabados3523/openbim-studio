# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo da F0-S04-T29b: reinício planejado do filho de geometria (regra R-A), peça por peça.

Transcrição de docs/state/lotes/LOTE_OPUS_59/resultado.md §2.4. Quem implementa o T29a e o T29c não edita este arquivo.

Como ler:
- Os testes SEM marca (forma canônica, controle "normal contra normal", limites padrão) passam com o produto de hoje.
- Os testes com `xfail(strict=True)` exigem o reinício (ganchos OBIM_TESTE_REINICIO_BLOCO e OBIM_TESTE_CRESCER_MB, bloco 250).
  Hoje falham; quando o produto existir devem passar, e o `strict` acusa se passarem antes da hora.
- A forma canônica junta todos os pedaços de cada peça (id_step), gira cada triângulo para começar no menor vértice SEM trocar a
  ordem (mantém o sentido da face), ordena e compara exato, em bits. Não compara número e ordem dos lotes.
- O número de filhos e a posição do reinício vêm de um espião no `multiprocessing` do carregador (não dependem de nomes novos
  no resumo). Tudo com os mesmos fios nos dois lados (1 fio, bloco de 3 peças); o passe de 1 fio do T21 não é referência.
- Modelo sintético de 12 paredes: 4 blocos de 3 peças; `max_bytes_lote` pequeno parte cada peça em 2 pedaços.
Hipótese registrada: o gancho OBIM_TESTE_CRESCER_MB aceita vários pares separados por vírgula ("g1=mb,g2=mb"), só para o caso do
segundo reinício pedido com o teto padrão (a especificação descreve um par; ver PERGUNTA_PO do retorno).
"""
import inspect
import multiprocessing
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

import ifcopenshell
import ifcopenshell.api

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "prototypes"))
sys.path.insert(0, str(RAIZ / "scripts"))

from gerar_modelo_grande import gerar  # noqa: E402
from viewport_qrhi import carregador as modulo_carregador  # noqa: E402
from viewport_qrhi import processo_malhas  # noqa: E402
from viewport_qrhi.carregador import CarregadorMalhas, ResumoCarga  # noqa: E402

BLOCO = 3  # peças por bloco nos testes
KW = dict(threads=1, tamanho_bloco=BLOCO, max_bytes_lote=600)
CRESCER_MB = 1100  # acima de G (1.000 MB)
LENTA_S = 10.0  # peça lenta (abaixo de limite_peca_s = 20): o filho velho tem de morrer antes de terminá-la
NAO_DEVOLVEU = "o conversor não devolveu a peça"
AINDA_NAO = pytest.mark.xfail(strict=True, reason="T29a/T29c ainda não implementados")


# ---------- modelo e peças ----------
def _descrever(caminho):
    f = ifcopenshell.open(str(caminho))
    ordem = sorted((p for p in f.by_type("IfcProduct") if p.Representation is not None
                    and not p.is_a("IfcFeatureElementSubtraction") and not p.is_a("IfcSpace")), key=lambda p: p.id())
    assert len(ordem) == 12
    return SimpleNamespace(caminho=str(caminho), ids=[p.id() for p in ordem], guids=[p.GlobalId for p in ordem])


@pytest.fixture(scope="module")
def modelo(tmp_path_factory):
    c = tmp_path_factory.mktemp("t29b") / "m12.ifc"
    gerar(c, paredes=12, por_andar=6)
    return _descrever(c)


@pytest.fixture(scope="module")
def modelo_bloco1_vazio(tmp_path_factory):
    """3 proxies com representação vazia (ids menores) + 9 paredes: o bloco 1 inteiro não dá geometria, então `desl` nasce vazio."""
    api = ifcopenshell.api.run
    f = api("project.create_file", version="IFC4")
    api("root.create_entity", f, ifc_class="IfcProject", name="Teste")
    api("unit.assign_unit", f)
    ctx = api("context.add_context", f, context_type="Model")
    corpo = api("context.add_context", f, context_type="Model", context_identifier="Body", target_view="MODEL_VIEW", parent=ctx)
    for k in range(3):
        p = api("root.create_entity", f, ifc_class="IfcBuildingElementProxy", name=f"vazio{k}")
        p.Representation = f.create_entity("IfcProductDefinitionShape", Representations=[
            f.create_entity("IfcShapeRepresentation", ContextOfItems=corpo, RepresentationIdentifier="Body",
                            RepresentationType="SweptSolid", Items=[])])
    for k in range(9):
        w = api("root.create_entity", f, ifc_class="IfcWall", name=f"p{k}")
        rep = api("geometry.add_wall_representation", f, context=corpo, length=3.0, height=2.8, thickness=0.15)
        api("geometry.assign_representation", f, product=w, representation=rep)
        m = np.eye(4)
        m[:3, 3] = (k * 4.0, 0.0, 0.0)
        api("geometry.edit_object_placement", f, product=w, matrix=m)
    c = tmp_path_factory.mktemp("t29b_vazio") / "vazio.ifc"
    f.write(str(c))
    return _descrever(c)


def _guid(m, k):
    """GUID da peça de posição k (0 a 11); o bloco b (1 a 4) tem as posições 3(b-1) a 3b-1."""
    return m.guids[k]


# ---------- espião do multiprocessing do carregador ----------
_CTX_REAL = multiprocessing.get_context("spawn")


class _Filho:
    def __init__(self, real, alvo, params):
        self.real, self.alvo, self.params, self.iniciado = real, alvo, params, False

    def start(self):
        self.real.start()
        self.iniciado = True

    def __getattr__(self, nome):
        return getattr(self.real, nome)


class Espia:
    def __init__(self):
        self.filhos, self.dois_vivos, self.car = [], 0, None
        self.ao_criar = self.ao_iniciar = None  # funções (índice do filho de conversão, filho)

    @property
    def conversao(self):
        return [f for f in self.filhos if f.alvo == "entrada"]

    def instalar(self, monkeypatch):
        real = _CTX_REAL
        espia = self

        def processo(target, args, name=None, daemon=None):
            if any(f.iniciado and f.is_alive() for f in espia.filhos):
                espia.dois_vivos += 1  # nasce um filho com outro ainda vivo
            f = _Filho(real.Process(target=target, args=args, name=name, daemon=daemon), target.__name__, args[1])
            espia.filhos.append(f)
            if espia.ao_criar and f.alvo == "entrada":
                espia.ao_criar(len(espia.conversao) - 1, f)
            return _Proxy(f, espia)

        ctx = SimpleNamespace(Pipe=real.Pipe, Process=processo)
        monkeypatch.setattr(modulo_carregador, "multiprocessing", SimpleNamespace(get_context=lambda _m: ctx))
        return self


class _Proxy:
    """O que o carregador enxerga como processo: repassa tudo ao filho real e avisa o espião ao iniciar."""

    def __init__(self, f, espia):
        self._f, self._e = f, espia

    def start(self):
        if any(o is not self._f and o.iniciado and o.is_alive() for o in self._e.filhos):
            self._e.dois_vivos += 1
        self._f.start()
        if self._e.ao_iniciar and self._f.alvo == "entrada":
            self._e.ao_iniciar(len(self._e.conversao) - 1, self._f)

    def __getattr__(self, nome):
        return getattr(self._f.real, nome)


def _rodar(modelo, monkeypatch, env=None, espia_cb=None, pausa_s=0.0, **kw):
    """Uma abertura completa com o espião. Devolve (lotes, resumo, espia)."""
    for k, v in (env or {}).items():
        monkeypatch.setenv(k, v)
    esp = Espia().instalar(monkeypatch)
    if espia_cb:
        espia_cb(esp)
    car = CarregadorMalhas(modelo.caminho, **{**KW, **kw})
    esp.car = car
    lotes, fim = [], time.perf_counter() + 300.0
    car.iniciar()
    while time.perf_counter() < fim:
        x = car.obter(timeout=0.05)
        if isinstance(x, ResumoCarga):
            assert car.aguardar(30), "a thread do carregador não terminou"
            return lotes, x, esp
        if x is not None:
            lotes.append(x)
            if pausa_s:
                time.sleep(pausa_s)
    car.cancelar()
    raise AssertionError("carga não terminou no tempo")


# ---------- forma canônica ----------
def _triangulo_canonico(a, b, c):
    """Três vértices (bytes exatos) girados para começar no menor, mesma ordem: o sentido da face não muda."""
    v = [a, b, c]
    k = v.index(min(v))
    return tuple(v[k:] + v[:k])


def forma_canonica(lotes):
    """Por id_step: triângulos canônicos ordenados, vértices, caixa (mín e máx de todos os pedaços), nº de pedaços."""
    pecas = {}
    for lote in lotes:
        for o in lote.objetos:
            iv, nv, ii, ni = int(o["primeiro_vertice"]), int(o["n_vertices"]), int(o["primeiro_indice"]), int(o["n_indices"])
            vs = [lote.vertices[iv + j].tobytes() for j in range(nv)]
            idx = lote.indices[ii:ii + ni].astype(np.int64) - iv
            p = pecas.setdefault(int(o["id_step"]), {"tri": [], "nv": 0, "mn": None, "mx": None, "pedacos": 0})
            p["tri"] += [_triangulo_canonico(vs[idx[t]], vs[idx[t + 1]], vs[idx[t + 2]]) for t in range(0, ni, 3)]
            p["nv"] += nv
            p["pedacos"] += 1
            mn, mx = o["caixa_min"].tobytes(), o["caixa_max"].tobytes()
            mn_a, mx_a = np.frombuffer(mn, "<f4"), np.frombuffer(mx, "<f4")
            p["mn"] = mn_a if p["mn"] is None else np.minimum(p["mn"], mn_a)
            p["mx"] = mx_a if p["mx"] is None else np.maximum(p["mx"], mx_a)
    return {i: (sorted(p["tri"]), p["nv"], p["mn"].tobytes(), p["mx"].tobytes()) for i, p in pecas.items()}


def _pedacos(lotes):
    n = {}
    for lote in lotes:
        for i in lote.objetos["id_step"]:
            n[int(i)] = n.get(int(i), 0) + 1
    return n


def _desl(lotes):
    return {lote.deslocamento.tobytes() for lote in lotes}


def conferir_igual(a, b, ctx=""):
    """Mesmas peças e mesma geometria exata; mesmo deslocamento; sem_malha, simplificadas e totais iguais."""
    (la, ra), (lb, rb) = a, b
    assert _desl(la) == _desl(lb) and len(_desl(la)) == 1, f"{ctx}: deslocamento diferente"
    ca, cb = forma_canonica(la), forma_canonica(lb)
    assert ca.keys() == cb.keys(), f"{ctx}: peças diferentes"
    for i in ca:
        assert ca[i] == cb[i], f"{ctx}: forma da peça {i} difere"
    motivo = lambda s: (s[0], s[1], s[2], s[3].split(":")[0])  # o registro do conversor traz hora: só o começo do motivo
    assert sorted(map(motivo, ra.sem_malha)) == sorted(map(motivo, rb.sem_malha)), ctx
    assert sorted((s[0], s[4]) for s in ra.simplificadas) == sorted((s[0], s[4]) for s in rb.simplificadas), ctx
    assert (ra.produtos_total, ra.produtos_com_malha, ra.triangulos, ra.vertices) == \
           (rb.produtos_total, rb.produtos_com_malha, rb.triangulos, rb.vertices), ctx


# ---------- testes que passam hoje: a régua e o controle ----------
def test_forma_canonica_gira_o_triangulo_mas_nao_troca_o_sentido():
    a, b, c = b"a", b"b", b"c"
    assert _triangulo_canonico(a, b, c) == _triangulo_canonico(b, c, a) == _triangulo_canonico(c, a, b)
    assert _triangulo_canonico(a, b, c) != _triangulo_canonico(a, c, b)  # sentido trocado = face virada = diferente


def test_controle_normal_contra_normal(modelo, monkeypatch):
    """Duas aberturas do produto de hoje, mesmos fios: forma canônica exata igual. Se falhar, parar e reportar a causa."""
    a = _rodar(modelo, monkeypatch)
    b = _rodar(modelo, monkeypatch)
    for lotes, r, esp in (a, b):
        assert r.estado == "concluido" and r.produtos_com_malha == 12 and not r.sem_malha
        assert len(esp.conversao) == 1 and esp.dois_vivos == 0
        assert max(_pedacos(lotes).values()) > 1, "o modelo de teste precisa partir peças em pedaços"
    conferir_igual(a[:2], b[:2], "normal contra normal")


def test_limites_padrao_na_assinatura():
    p = inspect.signature(CarregadorMalhas.__init__).parameters
    assert (p["limite_peca_s"].default, p["limite_abrir_s"].default, p["max_pecas_condenadas"].default,
            p["max_espera_s"].default) == (20.0, 600.0, 20, 120.0)


def test_bloco_padrao_e_250():
    assert inspect.signature(CarregadorMalhas.__init__).parameters["tamanho_bloco"].default == 250


# ---------- reinício forçado (T29a) ----------
def _lenta(modelo, k, env):
    """Acrescenta ao env uma peça lenta (LENTA_S) na posição k."""
    return {**env, "OBIM_TESTE_PECA_LENTA": f"{_guid(modelo, k)}={LENTA_S:g}"}


def _comparar_com_normal(modelo, monkeypatch, env, filhos, normal=None, sem_malha_ok=False, perdido_max=None, **kw):
    """Normal (sem ganchos) contra a abertura com `env`. `perdido_max`: o filho velho tem de morrer antes de terminar a peça
    lenta, isto é, `perdido_s` < L: só a vigia que decide NO MEIO do bloco consegue isso."""
    ref = normal or _rodar(modelo, monkeypatch, **kw)
    novo = _rodar(modelo, monkeypatch, env=env, **kw)
    lotes, r, esp = novo
    assert r.estado == "concluido" and (sem_malha_ok or not r.sem_malha), r.sem_malha
    assert not any(NAO_DEVOLVEU in s[3] for s in r.sem_malha)
    assert len(esp.conversao) == filhos, f"filhos de conversão: {len(esp.conversao)}"
    assert esp.dois_vivos == 0 and all(not f.is_alive() for f in esp.filhos)
    if perdido_max is not None:
        assert r.tempos["perdido_s"] < perdido_max, f"o filho velho só morreu depois de {r.tempos['perdido_s']:.1f} s"
    conferir_igual(ref[:2], novo[:2], "reinício contra normal")
    return novo


def test_reinicio_forcado_no_bloco_2_igual_ao_normal(modelo, monkeypatch):
    _, r, esp = _comparar_com_normal(modelo, monkeypatch, {"OBIM_TESTE_REINICIO_BLOCO": "2"}, filhos=2)
    # resumo: número de filhos, bloco do reinício, perdido do filho morto, mensagens juntadas, tempos do filho novo
    assert r.filhos == len(esp.conversao) and r.reinicios == [2]
    assert r.tempos["perdido_s"] > 0
    assert any("reinício planejado do filho no bloco 2" in m for m in r.mensagens), r.mensagens
    assert all(r.tempos.get(k, 0) > 0 for k in ("abrir_s", "listar_s", "geometria_s")), r.tempos
    # o filho novo recebe os não resolvidos a partir da fronteira do bloco 2 (nada do bloco 2 foi entregue antes)
    assert esp.conversao[1].params["ids"] == modelo.ids[BLOCO:]
    assert esp.conversao[1].params["desl"] is not None  # o mesmo deslocamento do primeiro filho


def test_dois_reinicios_nenhuma_peca_some(modelo, monkeypatch):
    """Blocos globais 2 e 4 (o 3º é a refeitura do 2º no filho novo): 3 filhos, nada em sem_malha."""
    _comparar_com_normal(modelo, monkeypatch, {"OBIM_TESTE_REINICIO_BLOCO": "2,4"}, filhos=3)


# ---------- reinício pelo caminho real (T29c) ----------
@AINDA_NAO
def test_crescer_em_bloco_que_nao_e_o_primeiro_reinicia_uma_vez_no_bloco_certo(modelo, monkeypatch):
    g = _guid(modelo, BLOCO)  # 1ª peça do bloco 2 cresce; a última do mesmo bloco é lenta (L)
    env = _lenta(modelo, 2 * BLOCO - 1, {"OBIM_TESTE_CRESCER_MB": f"{g}={CRESCER_MB}"})
    lotes, r, esp = _comparar_com_normal(modelo, monkeypatch, env, filhos=2, perdido_max=LENTA_S)
    assert esp.conversao[1].params["ids"] == modelo.ids[BLOCO:]  # recomeça na fronteira do bloco 2
    assert r.pico_filho_mb >= 1000, "a peça precisa ter crescido de verdade no filho"


@AINDA_NAO
def test_crescer_no_primeiro_bloco_do_filho_nao_reinicia_isencao(modelo, monkeypatch):
    g = _guid(modelo, 0)  # 1ª peça do bloco 1 cresce; a última do bloco é lenta: a regra isenta, não falta tempo à vigia
    env = _lenta(modelo, BLOCO - 1, {"OBIM_TESTE_CRESCER_MB": f"{g}={CRESCER_MB}"})
    lotes, r, esp = _rodar(modelo, monkeypatch, env=env)
    assert r.pico_filho_mb >= 1000, "a peça precisa ter crescido de verdade no filho"  # prova que o gancho agiu
    assert len(esp.conversao) == 1 and r.estado == "concluido" and not r.sem_malha


@AINDA_NAO
def test_segundo_reinicio_pedido_com_teto_padrao_e_registrado_e_nao_feito(modelo, monkeypatch):
    gs = ",".join(f"{_guid(modelo, k)}={CRESCER_MB}" for k in (BLOCO, 2 * BLOCO))  # 1ª peça dos blocos 2 e 3 da lista
    lentas = ",".join(f"{_guid(modelo, k)}={LENTA_S:g}" for k in (2 * BLOCO - 1, 3 * BLOCO - 1))  # fim dos dois blocos que crescem
    env = {"OBIM_TESTE_CRESCER_MB": gs, "OBIM_TESTE_PECA_LENTA": lentas}
    lotes, r, esp = _comparar_com_normal(modelo, monkeypatch, env, filhos=2, perdido_max=LENTA_S)  # 2º pedido: o teto de 1 vale
    assert not any("visto só no fim do bloco" in m for m in r.mensagens), r.mensagens  # a vigia viu a tempo, não só o fim
    assert any("reinício pedido e não feito" in m for m in r.mensagens), r.mensagens


@AINDA_NAO
def test_fila_cheia_durante_o_bloco_vigiado_a_regra_ainda_dispara(modelo, monkeypatch):
    g = _guid(modelo, 2 * BLOCO)  # 1ª peça do bloco 3 cresce; a última dele é lenta; consumidor lento mantém a fila cheia
    env = _lenta(modelo, 3 * BLOCO - 1, {"OBIM_TESTE_CRESCER_MB": f"{g}={CRESCER_MB}"})
    _comparar_com_normal(modelo, monkeypatch, env, filhos=2, perdido_max=LENTA_S, fila_max=1, pausa_s=0.2)


# ---------- cancelar ----------
def test_cancelar_entre_a_morte_e_o_filho_novo(modelo, monkeypatch):
    def preparar(esp):
        esp.ao_criar = lambda n, f: esp.car.cancelar() if n == 1 else None  # o filho novo ainda nem começou
    lotes, r, esp = _rodar(modelo, monkeypatch, env={"OBIM_TESTE_REINICIO_BLOCO": "2"}, espia_cb=preparar)
    assert len(esp.conversao) == 2 and not esp.conversao[1].iniciado
    assert r.reinicios == [2]  # o cancelamento veio depois da morte planejada, não antes
    assert r.estado == "cancelado" and all(not f.is_alive() for f in esp.filhos) and esp.dois_vivos == 0


def test_cancelar_durante_o_filho_novo(modelo, monkeypatch):
    def preparar(esp):
        esp.ao_iniciar = lambda n, f: esp.car.cancelar() if n == 1 else None
    lotes, r, esp = _rodar(modelo, monkeypatch, env={"OBIM_TESTE_REINICIO_BLOCO": "2"}, espia_cb=preparar)
    assert len(esp.conversao) == 2 and esp.conversao[1].iniciado
    assert r.estado == "cancelado" and all(not f.is_alive() for f in esp.filhos) and esp.dois_vivos == 0


# ---------- queda e limite no bloco refeito: caminho de hoje, sem mudança ----------
@pytest.mark.parametrize("gancho,motivo", [("OBIM_TESTE_MATAR_FILHO", "caiu"), ("OBIM_TESTE_PECA_LENTA", "limite")])
def test_queda_e_limite_no_bloco_refeito_seguem_o_caminho_de_hoje(modelo, monkeypatch, gancho, motivo):
    g = _guid(modelo, 2 * BLOCO - 1)  # última peça do bloco 2 (com 1 fio, as outras saem antes)
    valor = g if gancho == "OBIM_TESTE_MATAR_FILHO" else f"{g}=4"
    env, kw = {gancho: valor}, dict(limite_peca_s=1.0)
    normal = _rodar(modelo, monkeypatch, env=env, **kw)
    assert [s[0] for s in normal[1].simplificadas] == [modelo.ids[2 * BLOCO - 1]]
    assert motivo in normal[1].simplificadas[0][4]
    n_normal = len(normal[2].conversao)
    refeito = _rodar(modelo, monkeypatch, env={**env, "OBIM_TESTE_REINICIO_BLOCO": "2"}, **kw)
    assert len(refeito[2].conversao) == n_normal + 1  # só o filho a mais do reinício
    assert refeito[2].dois_vivos == 0
    conferir_igual(normal[:2], refeito[:2], "queda/limite com reinício contra sem reinício")


# ---------- modo isolado: a vigia nunca arma ----------
@AINDA_NAO
def test_modo_isolado_nunca_arma_a_vigia(modelo, monkeypatch):
    mata, cresce = _guid(modelo, 1), _guid(modelo, 0)  # bloco 1: a queda leva ao modo isolado, onde a peça cresce
    ref = _rodar(modelo, monkeypatch, env={"OBIM_TESTE_MATAR_FILHO": mata})
    novo = _rodar(modelo, monkeypatch, env=_lenta(modelo, 2, {"OBIM_TESTE_MATAR_FILHO": mata,  # lenta depois da que cresce
                                                              "OBIM_TESTE_CRESCER_MB": f"{cresce}={CRESCER_MB}"}))
    assert novo[1].pico_filho_mb >= 1000, "a peça precisa ter crescido de verdade no filho"
    assert len(novo[2].conversao) == len(ref[2].conversao)  # o crescimento não pediu reinício
    assert novo[2].dois_vivos == 0
    conferir_igual(ref[:2], novo[:2], "isolado com crescimento contra isolado sem")


# ---------- `desl` vazio: o bloco 1 inteiro sem geometria ----------
def test_reinicio_com_desl_vazio_o_filho_novo_calcula_o_seu(modelo_bloco1_vazio, monkeypatch):
    m = modelo_bloco1_vazio
    normal = _rodar(m, monkeypatch)
    assert normal[1].produtos_com_malha == 9 and len(normal[1].sem_malha) == 3, "o bloco 1 não pode dar geometria"
    assert min(int(i) for lote in normal[0] for i in lote.objetos["id_step"]) > m.ids[BLOCO - 1]
    _, r, esp = _comparar_com_normal(m, monkeypatch, {"OBIM_TESTE_REINICIO_BLOCO": "2"}, filhos=2, normal=normal,
                                     sem_malha_ok=True)
    assert esp.conversao[1].params["desl"] is None  # nada foi entregue antes: o filho novo calcula o seu
    assert r.reinicios == [2]
