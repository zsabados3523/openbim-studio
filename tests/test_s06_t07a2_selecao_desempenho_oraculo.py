# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo do F0-S06-T07a2: desempenho da seleção do corte SEM mudar o resultado (cartão `cards/F0-S06/F0-S06-T07a2.md`, ADR-006 §4).
Só testes; implementada (marcadores `AINDA_NAO_T07A2` retirados). Implementador não edita este arquivo.
API/GANCHOS OBSERVÁVEIS (nomes fixos; o resto da implementação é livre):
1. `obim_geometria/nucleos.py` (novo): `nucleos_fisicos() -> int` (>=1) e `limitar_threads(pedido=None, *, fisicos=None) -> int`.
   `pedido=None` -> `min(fisicos, 8)` (fisicos=None: chama `nucleos_fisicos()` pelo atributo do módulo, para o teste trocar por monkeypatch);
   inteiro >=1 -> `min(pedido, fisicos, 8)`. Valor 0, negativo, NaN, infinito, bool, float não inteiro ou texto -> `nucleos.ThreadsInvalidas` (herda ValueError),
   nunca "ajuste" silencioso. `caixas.processar` e `desenho.processar` usam isso (pedido sem `threads` -> padrão; inválido -> {"ok": False, "erro": {"tipo": "ThreadsInvalidas"}}).
   `auxiliar.preparar` e `selecao.selecionar` põem `pedido["threads"] = limitar_threads(None)` (hoje: `min(8, os.cpu_count())`, que conta núcleo lógico).
2. `caixas.processar(pedido)`: UMA construção de `ifcopenshell.geom.iterator` por passagem; a resposta ganha `passagens_iterator` (int) e `erros_iterator`
   (lista de {"tipo","mensagem"}; [] se nada deu errado). Se `it.get()` levantar, registra o erro (não engole) e refaz SÓ os elementos ainda sem caixa
   (nova passagem com `include` menor); se uma passagem não avançar nada, para: os que sobraram vão para `falhas_geometria`. Termina sempre.
   `include` vazio nunca vira "todos os elementos do arquivo": 0 elementos -> nenhuma construção do iterator, `caixas_envolventes == {}`.
3. `caixas.ArvoreCaixas(caixas: dict[str, [xmin,ymin,zmin,xmax,ymax,zmax]])`: `len()`, `.cruzando(minimo, maximo) -> list[int]` (step ids em ordem crescente, intervalos
   FECHADOS como na T07a). Caixa com NaN/inf ou min>max -> ValueError ao construir; consulta com min>max ou NaN -> ValueError.
4. `selecao.SessaoSelecao()` (app, sem Qt): `selecionar(..., sessao=SessaoSelecao())` guarda por elemento a caixa (ou a falha) já calculada; um corte novo só manda ao
   executor os elementos que a sessão ainda não tem (nenhum -> nem chama `preparar` nem o executor) e filtra pela árvore. `sessao.invalidar(ids=None)` esquece
   os ids dados (None = tudo); quem altera o modelo é quem invalida. Resultado IGUAL ao sem sessão. `Selecao.erros_geometria: tuple[str, ...] = ()` leva "Tipo: mensagem" de `erros_iterator`.
5. Equivalência: threads 1, N e o padrão dão as mesmas caixas, bit a bit; ids selecionados iguais aos da versão atual.
DEPENDE DE T07c (fora deste arquivo): UMA só passagem para selecionar E desenhar o corte vertical (a T07c ainda não existe; hoje o corte não desenha). Aqui só a planta
(já uma passagem) e a seleção do corte. Ver PERGUNTA_PO do retorno.
GUARDA: sem ifcopenshell, pula (falha com OBIM_S05_OBRIGATORIO=1)."""
import math
import random
import time

import pytest
import s06_t07_aux as X
import s06_t07e_aux as T
from s05_conteudo_aux import _limpa, exigir  # noqa: F401  (fixture autouse; também põe `geometria/` no sys.path via T)


def _ifcgeom():
    exigir()
    import ifcopenshell.geom as G
    return G


class _Laco(BaseException):
    """Estoura se a implementação entrar em laço sem fim (BaseException: `except Exception` não engole)."""


class Espia:
    """Troca `ifcopenshell.geom.iterator`: registra (threads, tamanho do include) por construção; `ruim` = step ids cujo `get()` levanta SEMPRE;
    `falhar_na_1a` = o 1o iterator levanta no 2o `get()` e os seguintes são normais; `init_falha` = `initialize()` levanta."""

    def __init__(self, mp, ruim=(), falhar_na_1a=False, init_falha=False, next_falha=False, teto=50, msg=None):
        self.G, self.real = _ifcgeom(), _ifcgeom().iterator
        self.construcoes, self.ruim, self.falhar_na_1a, self.init_falha, self.next_falha, self.teto = [], set(ruim), falhar_na_1a, init_falha, next_falha, teto
        self.msg = msg or (lambda i: f"elemento {i} quebrou")  # texto da exceção do elemento ruim, em função do step id
        mp.setattr(self.G, "iterator", self)

    def __call__(self, settings, f, threads=1, *a, include=None, **k):
        if len(self.construcoes) >= self.teto:
            raise _Laco("iterator reconstruído sem parar")
        if isinstance(threads, bool) or not isinstance(threads, int) or threads < 1:
            raise AssertionError(f"threads invalido chegou ao iterator: {threads!r}")  # o real TRAVA com 0 (medido): nunca deixar chegar
        self.construcoes.append((threads, None if include is None else tuple(e.id() for e in include)))
        real = self.real(settings, f, threads, *a, **({} if include is None else {"include": include}), **k)
        return _Envolto(real, self, len(self.construcoes) - 1)


class _Envolto:
    def __init__(self, real, esp, n):
        self.real, self.esp, self.n, self.gets = real, esp, n, 0

    def initialize(self):
        if self.esp.init_falha:
            raise RuntimeError("init quebrou")
        return self.real.initialize()

    def get(self):
        self.gets += 1
        if self.esp.falhar_na_1a and self.n < int(self.esp.falhar_na_1a) and self.gets == 2:  # True = só a 1a; inteiro k = as k primeiras
            raise RuntimeError(f"iterator abortou {self.n}")
        shape = self.real.get()
        if shape is not None and shape.id in self.esp.ruim:
            raise RuntimeError(self.esp.msg(shape.id))
        return shape

    def next(self):
        if self.esp.next_falha and self.n == 0:
            raise RuntimeError("next quebrou")
        return self.real.next()

    def __getattr__(self, n):
        return getattr(self.real, n)


@pytest.fixture
def modelo(tmp_path):
    """Modelo pequeno da T07e (P, M, falha, Q + vistas) gravado em disco; devolve (f, d, pedido_caixas, ids_bons)."""
    exigir()
    f, d = T.modelo()
    arq = tmp_path / "m.ifc"
    f.write(str(arq))
    elementos = T.elementos(f, "P", "M", "falha", "Q")
    return f, d, {"op": "caixas", "arquivo": str(arq), "elementos": elementos}, {d["P"].id(), d["M"].id(), d["Q"].id()}


def _cx(pedido, **extra):
    from obim_geometria import caixas
    return caixas.processar({**pedido, **extra})


def _ok(r):
    assert r["ok"], r
    return r

# ---------- 1. equivalência e threads ----------
def test_caixas_iguais_com_1_2_4_threads_e_padrao(modelo):
    _, _, ped, bons = modelo
    ref = _ok(_cx(ped, threads=1))
    assert {int(k) for k in ref["caixas_envolventes"]} == bons and ref["falhas_geometria"] == [ped["elementos"][2][0]]
    for t in (2, 4):
        r = _ok(_cx(ped, threads=t))
        assert r["caixas_envolventes"] == ref["caixas_envolventes"] and r["falhas_geometria"] == ref["falhas_geometria"]
    r = _ok(_cx(ped))  # sem `threads`: padrão
    assert r["caixas_envolventes"] == ref["caixas_envolventes"]


def test_limitar_threads_teto_nucleos_fisicos_e_8():
    exigir()
    from obim_geometria import nucleos as N
    assert N.limitar_threads(None, fisicos=4) == 4 and N.limitar_threads(None, fisicos=16) == 8 and N.limitar_threads(None, fisicos=1) == 1
    assert N.limitar_threads(3, fisicos=16) == 3 and N.limitar_threads(64, fisicos=16) == 8 and N.limitar_threads(64, fisicos=4) == 4
    assert N.limitar_threads(1, fisicos=1) == 1 and isinstance(N.limitar_threads(None, fisicos=4), int)
    assert 1 <= N.nucleos_fisicos() <= 4096 and isinstance(N.nucleos_fisicos(), int)


@pytest.mark.parametrize("ruim", [0, -1, -8, float("nan"), float("inf"), -float("inf"), 2.5, True, False, "4", [], 1e9 + 0.5])
def test_limitar_threads_invalido_e_erro_explicito(ruim):
    exigir()
    from obim_geometria import nucleos as N
    assert issubclass(N.ThreadsInvalidas, ValueError)
    with pytest.raises(N.ThreadsInvalidas):
        N.limitar_threads(ruim, fisicos=4)


@pytest.mark.parametrize("ruim", [0, -3, float("nan")])
def test_processar_threads_invalido_devolve_erro_e_nao_roda_iterator(modelo, monkeypatch, ruim):
    _, _, ped, _ = modelo
    esp = Espia(monkeypatch)
    r = _cx(ped, threads=ruim)
    assert r["ok"] is False and r["erro"]["tipo"] == "ThreadsInvalidas" and esp.construcoes == []


def test_padrao_de_threads_vem_dos_nucleos_fisicos(modelo, monkeypatch):
    f, d, ped, _ = modelo
    from obim_geometria import nucleos as N
    monkeypatch.setattr(N, "nucleos_fisicos", lambda: 3)
    esp = Espia(monkeypatch)
    _ok(_cx(ped))
    assert [c[0] for c in esp.construcoes] == [3]
    monkeypatch.setattr(N, "nucleos_fisicos", lambda: 32)
    esp = Espia(monkeypatch)
    _ok(_cx(ped))
    assert [c[0] for c in esp.construcoes] == [8]  # teto 8
    _ok(_cx(ped, threads=2))
    assert esp.construcoes[-1][0] == 2
    # o mesmo padrão no pedido de preparar (auxiliar) e no da seleção do corte
    from openbim_app.desenho import auxiliar, selecao
    monkeypatch.setattr(N, "nucleos_fisicos", lambda: 3)
    with auxiliar.preparar(f, {"op": "caixas", "elementos": []}) as p:
        assert p.pedido["threads"] == 3
    vistos = []

    def executor(pedido):
        vistos.append(pedido)
        from obim_geometria import local
        return local.executar(pedido)
    selecao.selecionar(f, d["vc"], executor=executor)
    assert vistos and all(p["threads"] == 3 for p in vistos)


def test_planta_uma_so_passagem_do_iterator(monkeypatch):
    exigir()
    from obim_geometria import local
    from openbim_app.desenho import planta
    f, d = T.modelo()
    esp = Espia(monkeypatch)
    r = planta.gerar_planta(f, d["vp"], executor=local.executar)
    assert r.n_paths > 0 and len(esp.construcoes) == 1  # seleção da planta não calcula geometria; desenho = 1 passagem

# ---------- 2. iterator que falha ----------
def test_get_que_levanta_e_registrado_e_refaz_so_os_restantes(modelo, monkeypatch):
    f, _, ped, bons = modelo
    ref = _ok(_cx(ped, threads=1))
    esp = Espia(monkeypatch, falhar_na_1a=True)
    r = _ok(_cx(ped, threads=1))
    assert r["caixas_envolventes"] == ref["caixas_envolventes"] and r["falhas_geometria"] == ref["falhas_geometria"]  # coerente com o caso sem erro
    assert len(r["erros_iterator"]) == 1 and r["erros_iterator"][0]["tipo"] == "RuntimeError" and "abortou" in r["erros_iterator"][0]["mensagem"]
    assert r["passagens_iterator"] == len(esp.construcoes) == 2
    primeira, segunda = esp.construcoes[0][1], esp.construcoes[1][1]
    assert set(segunda) < set(primeira) and len(segunda) < len(primeira)  # só os restantes


def test_sem_erro_uma_passagem_e_erros_vazios(modelo, monkeypatch):
    _, _, ped, _ = modelo
    esp = Espia(monkeypatch)
    r = _ok(_cx(ped))
    assert r["erros_iterator"] == [] and r["passagens_iterator"] == 1 and len(esp.construcoes) == 1


def test_elemento_que_sempre_quebra_vai_para_falhas_e_termina(modelo, monkeypatch):
    _, d, ped, bons = modelo
    ruim = d["M"].id()
    esp = Espia(monkeypatch, ruim={ruim}, teto=len(ped["elementos"]) + 3)
    r = _ok(_cx(ped, threads=1))
    assert {int(k) for k in r["caixas_envolventes"]} == bons - {ruim}  # os outros saem
    assert set(r["falhas_geometria"]) == {ruim, ped["elementos"][2][0]} and r["erros_iterator"]
    assert all("quebrou" in e["mensagem"] for e in r["erros_iterator"]) and r["passagens_iterator"] <= len(ped["elementos"]) + 1


def test_initialize_que_levanta_e_erro_explicito(modelo, monkeypatch):
    _, _, ped, _ = modelo
    Espia(monkeypatch, init_falha=True)
    r = _cx(ped)
    assert r["ok"] is False and r["erro"]["tipo"] == "RuntimeError" and "init quebrou" in r["erro"]["mensagem"]


def test_selecionar_leva_erros_do_iterator_para_a_selecao():
    exigir()
    from obim_geometria import local
    from openbim_app.desenho import selecao
    f, d = T.modelo()
    assert selecao.selecionar(f, d["vc"], executor=local.executar).erros_geometria == ()

    def executor(pedido):
        r = local.executar(pedido)
        return {**r, "erros_iterator": [{"tipo": "RuntimeError", "mensagem": "boom"}]}
    s = selecao.selecionar(f, d["vc"], executor=executor)
    assert s.erros_geometria == ("RuntimeError: boom",) and s.ids == selecao.selecionar(f, d["vc"], executor=local.executar).ids

# ---------- 3. limites ----------
def test_zero_elementos_nao_roda_iterator_nem_devolve_o_arquivo_todo(modelo, monkeypatch):
    _, _, ped, _ = modelo
    esp = Espia(monkeypatch)
    r = _ok(_cx({**ped, "elementos": []}))
    assert r["caixas_envolventes"] == {} and r["falhas_geometria"] == [] and esp.construcoes == [] and r["passagens_iterator"] == 0


def test_zero_elementos_resultado_vazio(modelo):
    _, _, ped, _ = modelo
    r = _ok(_cx({**ped, "elementos": []}))
    assert r["caixas_envolventes"] == {} and r["falhas_geometria"] == []  # vale hoje e depois: nunca as caixas do arquivo inteiro


# ---------- árvore de caixas ----------
def _forca(caixas, lo, hi):
    return sorted(int(k) for k, c in caixas.items() if c[0] <= hi[0] and c[3] >= lo[0] and c[1] <= hi[1] and c[4] >= lo[1] and c[2] <= hi[2] and c[5] >= lo[2])

def _aleatorias(n, rng, longe=(324550.0, 7405473.0, 0.0)):
    out = {}
    for i in range(n):
        x, y, z = (longe[0] + rng.randrange(0, 4096) / 64, longe[1] + rng.randrange(0, 4096) / 64, rng.randrange(-640, 640) / 64)
        out[str(1000 + i)] = [x, y, z, x + rng.randrange(0, 256) / 64, y + rng.randrange(0, 256) / 64, z + rng.randrange(0, 256) / 64]
    return out


def test_arvore_igual_a_forca_bruta_incluindo_toque_e_ponto():
    exigir()
    from obim_geometria.caixas import ArvoreCaixas
    rng = random.Random(7)
    cx = _aleatorias(500, rng)
    a = ArvoreCaixas(cx)
    assert len(a) == 500
    consultas = []
    for _ in range(40):
        lo = (324550.0 + rng.randrange(0, 4096) / 64, 7405473.0 + rng.randrange(0, 4096) / 64, rng.randrange(-640, 640) / 64)
        consultas.append((lo, (lo[0] + rng.randrange(0, 512) / 64, lo[1] + rng.randrange(0, 512) / 64, lo[2] + rng.randrange(0, 512) / 64)))
    for k in list(cx)[:30]:  # encostando exatamente em cada face e em um ponto (volume zero)
        c = cx[k]
        consultas += [((c[3], c[1], c[2]), (c[3] + 1, c[4], c[5])), ((c[0] - 1, c[1], c[2]), (c[0], c[4], c[5])), ((c[0], c[1], c[2]), (c[0], c[1], c[2]))]
        consultas.append(((c[0], c[1], c[5] + 2 ** -6), (c[3], c[4], c[5] + 1)))  # 1/64 acima: fora
    for lo, hi in consultas:
        r = a.cruzando(lo, hi)
        assert r == _forca(cx, lo, hi) and r == sorted(set(r)) and all(isinstance(i, int) for i in r)
    assert a.cruzando((-1e9, -1e9, -1e9), (1e9, 1e9, 1e9)) == sorted(int(k) for k in cx) and a.cruzando((0, 0, 0), (1, 1, 1)) == []


def test_arvore_vazia_uma_caixa_e_entradas_invalidas():
    exigir()
    from obim_geometria.caixas import ArvoreCaixas
    assert len(ArvoreCaixas({})) == 0 and ArvoreCaixas({}).cruzando((0, 0, 0), (1, 1, 1)) == []
    um = ArvoreCaixas({"7": [0, 0, 0, 1, 1, 1]})
    assert um.cruzando((1, 1, 1), (2, 2, 2)) == [7] and um.cruzando((1.015625, 1, 1), (2, 2, 2)) == []
    for ruim in ([0, 0, 0, float("nan"), 1, 1], [0, 0, 0, math.inf, 1, 1], [2, 0, 0, 1, 1, 1]):
        with pytest.raises(ValueError):
            ArvoreCaixas({"1": ruim})
    for lo, hi in (((2, 0, 0), (1, 1, 1)), ((float("nan"), 0, 0), (1, 1, 1))):
        with pytest.raises(ValueError):
            um.cruzando(lo, hi)

# ---------- 4. sessão: vários cortes reaproveitam caixas ----------
class Executor:
    def __init__(self):
        self.pedidos = []

    def __call__(self, pedido):
        from obim_geometria import local
        self.pedidos.append(pedido)
        return local.executar(pedido)

def _cortes(f, pavs, off=(0.0, 0.0), base=0.0):
    return (X.vista(f, "CORTE", pavs[0], origem=(off[0], off[1] + 2.0, base), tamanho=(10.0, 1.0, 6.0), nome="A"),
            X.vista(f, "CORTE", pavs[0], origem=(off[0] - 5.0, off[1] + 1.0, base), tamanho=(8.0, 2.0, 3.0), nome="B"))


def test_sessao_segundo_corte_nao_recalcula_e_da_o_mesmo_resultado(monkeypatch):
    exigir()
    from openbim_app.desenho import auxiliar, selecao
    f, pavs, dentro, fora = X.faixa("IFC4", X.GEO, 0.0)
    ga, gb = _cortes(f, pavs, X.GEO)
    ref_a, ref_b = (selecao.selecionar(f, g, executor=Executor()) for g in (ga, gb))
    ses, ex, prep = selecao.SessaoSelecao(), Executor(), []
    real = auxiliar.preparar
    monkeypatch.setattr(auxiliar, "preparar", lambda *a, **k: prep.append(1) or real(*a, **k))
    sa = selecao.selecionar(f, ga, executor=ex, sessao=ses)
    assert sa == ref_a and len(ex.pedidos) == 1 and len(prep) == 1
    sb = selecao.selecionar(f, gb, executor=ex, sessao=ses)
    assert sb == ref_b and len(ex.pedidos) == 1 and len(prep) == 1  # nada novo: nem preparar (cópia do IFC) nem executor
    sc = selecao.selecionar(f, ga, executor=ex, sessao=ses, categorias_ocultas=("IfcFurnishingElement",))
    assert sc == selecao.selecionar(f, ga, executor=Executor(), categorias_ocultas=("IfcFurnishingElement",)) and len(ex.pedidos) == 1
    assert sa.falhas_geometria == ref_a.falhas_geometria and len(sa.falhas_geometria) == 3  # falha também fica na sessão


def test_sessao_invalidar_manda_so_os_ids_pedidos_e_acompanha_o_modelo():
    exigir()
    from openbim_app.desenho import selecao
    f, pavs, dentro, fora = X.faixa("IFC4")
    ga, _ = _cortes(f, pavs)
    ses, ex = selecao.SessaoSelecao(), Executor()
    selecao.selecionar(f, ga, executor=ex, sessao=ses)
    alvo = f.by_type("IfcBuildingElementProxy")[0]
    nome = next(e for e in f.by_type("IfcBuildingElementProxy") if e.Name == "fora_x")
    nome.ObjectPlacement.RelativePlacement.Location.Coordinates = (1.0, 2.25, 0.5)  # entra na faixa
    ses.invalidar([nome.id()])
    s = selecao.selecionar(f, ga, executor=ex, sessao=ses)
    assert [e[0] for e in ex.pedidos[-1]["elementos"]] == [nome.id()] and len(ex.pedidos) == 2
    assert s == selecao.selecionar(f, ga, executor=Executor()) and nome.id() in s.ids and alvo is not None
    ses.invalidar()
    selecao.selecionar(f, ga, executor=ex, sessao=ses)
    assert len(ex.pedidos) == 3 and len(ex.pedidos[-1]["elementos"]) > 10  # None = tudo
    ses.invalidar([])  # lista vazia: não esquece nada
    selecao.selecionar(f, ga, executor=ex, sessao=ses)
    assert len(ex.pedidos) == 3


def test_sessao_vazia_e_modelo_sem_elemento():
    exigir()
    from openbim_app.desenho import selecao
    f, pavs = X.estrutura("IFC4")
    g = X.vista(f, "CORTE", pavs[0], tamanho=(10.0, 10.0, 6.0))
    ex = Executor()
    s = selecao.selecionar(f, g, executor=ex, sessao=selecao.SessaoSelecao())
    assert s.ids == () and s.falhas_geometria == () and ex.pedidos == []
    f, pavs = X.estrutura("IFC4")
    e = X.caixa(f, "IfcWall", "unica", 1.0, 1.0, 0.0, 1.0, 1.0, 1.0)
    X.conter(f, pavs[0], e)
    g = X.vista(f, "CORTE", pavs[0], tamanho=(10.0, 10.0, 6.0))
    assert selecao.selecionar(f, g, executor=Executor(), sessao=selecao.SessaoSelecao()).ids == (e.id(),)
