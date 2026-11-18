# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oraculo F0-S06-T20d2: a previa nova (T20d1) chega ao app pelo filho persistente (T3). Cartao: docs/state/cards/F0-S06/F0-S06-T20d-previa-util.md (T20d2). Nao editar nesta tarefa.

INTERFACES QUE O IMPLEMENTADOR DEVE RESPEITAR (decididas aqui; o cartao deixa em aberto):
 1. TRANSPORTE = arquivo, como na T19n2: `pedido["previa_arquivo"]` (caminho do SVG da previa, gravado de forma atomica pelo lado de la).
 2. `auxiliar.executar(preparado, *, limite_s, cancelar, executor, previa=None, filho=None)`: o ramo `filho` TAMBEM define
    `preparado.pedido["previa_arquivo"] = preparado.pasta / "previa.svg"` ANTES de chamar `filho.executar(...)`, quando `previa` e callable, `executor is None`
    e `pedido["componentes"]` e verdadeiro (mesma regra do descartavel). Como `filho.executar` bloqueia, o pai vigia o arquivo numa thread auxiliar
    (poll <= 0,1 s) e chama `previa(svg_texto)` UMA vez, durante a espera, ANTES do resultado final; excecao do callback e engolida; a thread termina quando
    `filho.executar` volta (ok ou erro) e NUNCA chama `previa` depois disso. Sem `previa` ou sem `componentes`: nada muda (chave ausente, `filho.executar(pedido, cancelar=, limite_s=)`).
    `filho.executar` que levanta (estouro, queda, falha) => a previa ja entregue fica (nao ha retratacao), o erro tipado sobe igual. O dict final devolvido nao leva `parcial`.
    O `gerente._motor_padrao` ja embrulha o texto em `{"svg", ..., "parcial": True}` e emite o sinal `previa`; remover do docstring de `GerenteDesenho` a "Limitacao conhecida".
 3. `desenho._planta_por_componentes` (lado do filho, tambem em processo): SE `pedido["previa_arquivo"]`, logo APOS a unica carga de `silhueta.formas_do_mundo` e
    ANTES de `componentes.dividir_elementos` (portanto tambem quando so ha 1 grupo), chama `previa_planta.gerar_previa_planta(pecas, z_corte, ..., moveis_como_caixa=bool(pedido.get("moveis_como_caixa")), ao_fase=fase)`
    (chamada pelo ATRIBUTO do modulo `previa_planta`), onde `pecas` = so os elementos pedidos (nenhum fora da selecao), com `guid`, `classe` (`el.is_a()`), `verts`, `tris` das `formas` ja carregadas
    (`None` quando a forma nao existe) e `z_corte = vista["altura_corte_m"]`. Substitui a previa antiga (`_gravar_previa`, silhueta de pesados). O arquivo final tem `data-obim-previa="1"` na RAIZ `<svg>` e `xmlns:ifc`.
    `fase("previa")` chega UMA vez. Falha na previa nunca derruba o desenho final. A previa nao vaza para a resposta final (sem `data-obim-previa`, sem `parcial`, mesmas chaves).
    Sem `previa_arquivo` ou sem `componentes`: `gerar_previa_planta` nem e chamada e nenhum arquivo e escrito.
 4. `GerenteDesenho.salvar(caminho_ifc=None, *, revisao=None, revisao_salva=None)`: continua chamando `.salvar()` em todos os filhos; se `caminho_ifc` foi dado, DEPOIS disso chama
    `self.aquecer(caminho_ifc, revisao=revisao, revisao_salva=revisao_salva)` (o gate e do proprio `aquecer`). Sem argumentos: igual a hoje, sem aquecer. Abrir IFC: quem abre chama `aquecer` (ja existe).
    `servir` op "abrir" so abre o IFC: nao chama `formas_do_mundo`, nem `gerar_previa_planta`, nem `desenho.processar`, nao escreve previa.
 5. Sem filho (caminho descartavel): igual a hoje (T19n2 segue valendo, salvo a marca `data-silhueta` da previa antiga, que passa a ser a da previa nova)."""
from __future__ import annotations

import copy
import os
import re
import threading
import time
from pathlib import Path

import pytest

import obim_geometria.componentes as COMP
import obim_geometria.desenho as D
import obim_geometria.previa_planta as PP
from obim_geometria import persistente, silhueta
from openbim_app.desenho import auxiliar
from test_s06_t19g4a_persistente_oraculo import FakeRx, FakeTx
from test_s06_t19h_componentes_oraculo import _caixa, _cena, _guids
from test_s06_t19i1_nunca_descartar_oraculo import Fake, _cena3

MARCA = re.compile(r'<svg\b[^>]*\bdata-obim-previa="1"')
SVG_PREVIA = '<svg xmlns="http://www.w3.org/2000/svg" xmlns:ifc="http://www.ifcopenshell.org/ns" data-obim-previa="1"><g class="IfcWall cut" ifc:guid="G1"><path d="M 0,0 L 1,0 L 1,1 Z"/></g></svg>'


# ---------------------------------------------------------------- lado do filho: desenho.processar com previa_arquivo
class Espioes:
    """Espia formas_do_mundo, dividir_elementos e gerar_previa_planta (delegando aos originais)."""

    def __init__(self, mp, previa):
        self.previa, self.formas, self.chamadas_previa, self.ordem = previa, [], [], []
        of, od, og = silhueta.formas_do_mundo, COMP.dividir_elementos, PP.gerar_previa_planta

        def formas(f, elementos, *a, **k):
            self.formas.append(sorted(e.id() for e in elementos))
            return of(f, elementos, *a, **k)

        def dividir(*a, **k):
            self.ordem.append(("dividir", self._previa_pronta()))
            return od(*a, **k)

        def gerar(pecas, z_corte, *a, **k):
            pecas = list(pecas)
            self.chamadas_previa.append({"pecas": pecas, "z": z_corte, "kw": k, "args": a})
            r = og(pecas, z_corte, *a, **k)
            self.ultima = r
            return r
        mp.setattr(silhueta, "formas_do_mundo", formas)
        mp.setattr(COMP, "dividir_elementos", dividir)
        mp.setattr(PP, "gerar_previa_planta", gerar)

    def _previa_pronta(self):
        return os.path.exists(self.previa) and bool(MARCA.search(Path(self.previa).read_text(encoding="utf-8")))


def _roda(ped, fases=None):
    return D.processar(copy.deepcopy(ped), fases.append if fases is not None else None)


def test_a_previa_nova_antes_de_agrupar_com_uma_carga_e_so_o_pedido(monkeypatch, tmp_path):
    ped, ids, _ = _cena3(tmp_path)
    ped["previa_arquivo"] = str(tmp_path / "previa.svg")
    ped["moveis_como_caixa"] = True
    esp = Espioes(monkeypatch, ped["previa_arquivo"])
    visto_no_lote = []

    class FakeLote(Fake):
        def __call__(self, pedido, *a, **k):
            if pedido.get("op") == "desenho_lote":
                visto_no_lote.append(esp._previa_pronta())
            return super().__call__(pedido, *a, **k)
    FakeLote(monkeypatch, [], None)
    fases = []
    r = _roda(ped, fases)
    assert r["ok"]
    assert esp.formas == [sorted(ids)], "UMA carga de formas_do_mundo, so com os elementos pedidos (a previa reaproveita a mesma carga)"
    assert len(esp.chamadas_previa) == 1
    c = esp.chamadas_previa[0]
    guids = {g for _, g in ped["elementos"]}
    assert [p["guid"] for p in c["pecas"]] == [g for _, g in ped["elementos"]] and {p["guid"] for p in c["pecas"]} == guids
    assert all(p["classe"] == "IfcBuildingElementProxy" and p["verts"] is not None and p["tris"] is not None for p in c["pecas"])
    assert c["z"] == ped["vista"]["altura_corte_m"] and c["kw"].get("moveis_como_caixa") is True
    aud = esp.ultima["auditoria"]
    assert set().union(*(set(v) for v in aud.values())) == guids, "auditoria da previa cobre todos os GUIDs pedidos"
    assert esp.ordem == [("dividir", True)], "previa pronta (com marca) ANTES de agrupar"
    assert visto_no_lote and all(visto_no_lote), "previa pronta ANTES de qualquer lote do calculo final"
    assert fases.count("previa") == 1
    texto = Path(ped["previa_arquivo"]).read_text(encoding="utf-8")
    assert MARCA.search(texto) and "xmlns:ifc=" in texto and sorted(_guids(texto)) == sorted(guids)
    assert not os.path.exists(ped["previa_arquivo"] + ".tmp")


def test_b_previa_tambem_com_um_unico_grupo(monkeypatch, tmp_path):
    ped, ids = _cena(tmp_path, [_caixa(0, 0, 0, 1, 1, 1), _caixa(1, 0, 0, 2, 1, 1)], corte=0.5)  # encostadas: 1 grupo => fallback
    ped.update({"componentes": True, "threads": 1, "previa_arquivo": str(tmp_path / "previa.svg")})
    esp = Espioes(monkeypatch, ped["previa_arquivo"])
    fases = []
    r = _roda(ped, fases)
    assert r["ok"] and len(esp.chamadas_previa) == 1 and fases.count("previa") == 1
    texto = Path(ped["previa_arquivo"]).read_text(encoding="utf-8")
    assert MARCA.search(texto) and sorted(_guids(texto)) == sorted(g for _, g in ped["elementos"])
    assert esp.ordem and esp.ordem[0][1] is True or esp.ordem == []  # se agrupou, a previa ja existia


def test_c_resposta_final_igual_com_e_sem_previa_e_sem_vazamento(monkeypatch, tmp_path):
    ped, ids, _ = _cena3(tmp_path)
    Fake(monkeypatch, [], None)
    sem = _roda(ped)
    com_ped = {**ped, "previa_arquivo": str(tmp_path / "previa.svg")}
    com = _roda(com_ped)
    assert Path(com_ped["previa_arquivo"]).exists()
    assert com["svg"] == sem["svg"] and sorted(com) == sorted(sem) and sorted(com["tempos"]) == sorted(sem["tempos"])
    assert "data-obim-previa" not in com["svg"] and not com.get("parcial")


def test_d_falha_da_previa_nao_derruba_o_final(monkeypatch, tmp_path):
    ped, ids, _ = _cena3(tmp_path)
    Fake(monkeypatch, [], None)
    sem = _roda(ped)

    def quebra(*a, **k):
        raise RuntimeError("previa quebrou")
    monkeypatch.setattr(PP, "gerar_previa_planta", quebra)
    r = _roda({**ped, "previa_arquivo": str(tmp_path / "previa.svg")})
    assert r["ok"] and r["svg"] == sem["svg"]


def test_e_sem_previa_arquivo_ou_sem_componentes_nada_e_gerado(monkeypatch, tmp_path):
    ped, ids, _ = _cena3(tmp_path)
    chamadas = []
    monkeypatch.setattr(PP, "gerar_previa_planta", lambda *a, **k: chamadas.append(1))
    Fake(monkeypatch, [], None)
    assert _roda(ped)["ok"]  # componentes sem previa_arquivo
    sem_comp = {k: v for k, v in ped.items() if k != "componentes"}
    sem_comp["previa_arquivo"] = str(tmp_path / "previa.svg")
    assert _roda(sem_comp)["ok"]  # previa_arquivo sem componentes
    assert chamadas == [] and not (tmp_path / "previa.svg").exists()


# ---------------------------------------------------------------- servir (filho persistente): fase "previa" chega ao pai uma vez
def test_f_servir_manda_fase_previa_uma_vez_e_arquivo_antes_da_resposta(monkeypatch, tmp_path):
    ped, ids, _ = _cena3(tmp_path)
    Fake(monkeypatch, [], None)
    ped.update({"op": "desenho", "protocolo": 1, "numero": 1, "previa_arquivo": str(tmp_path / "previa.svg")})
    tx = FakeTx([])
    persistente.servir(tx, FakeRx([ped]))
    fases = [(i, m["fase"]) for i, m in enumerate(tx.msgs) if m.get("tipo") == "fase"]
    assert [f for _, f in fases].count("previa") == 1 and all(m["numero"] == 1 for m in tx.msgs if m.get("tipo") == "fase")
    i_resp = next(i for i, m in enumerate(tx.msgs) if m.get("tipo") == "resposta")
    assert next(i for i, f in fases if f == "previa") < i_resp
    assert tx.respostas[-1]["dados"]["ok"] and "data-obim-previa" not in tx.respostas[-1]["dados"]["svg"]
    assert MARCA.search(Path(ped["previa_arquivo"]).read_text(encoding="utf-8"))


def test_g_servir_op_abrir_so_abre_sem_carregar_malhas(monkeypatch, tmp_path):
    ped, ids, _ = _cena3(tmp_path)
    esp = Espioes(monkeypatch, str(tmp_path / "previa.svg"))
    abriu = []
    monkeypatch.setattr(D, "processar", lambda *a, **k: abriu.append(1))
    pedido = {**ped, "op": "abrir", "protocolo": 1, "numero": 1, "previa_arquivo": str(tmp_path / "previa.svg")}
    tx = FakeTx([])
    persistente.servir(tx, FakeRx([pedido]))
    assert tx.respostas[-1]["dados"] == {"aberto": True}
    assert esp.formas == [] and esp.chamadas_previa == [] and abriu == [] and not (tmp_path / "previa.svg").exists()


# ---------------------------------------------------------------- lado do pai: auxiliar.executar com filho
class FakeFilho:
    """Filho falso: `roteiro(filho, pedido)` roda dentro de `executar`; assinatura igual a do FilhoPersistente (sem ao_parcial)."""

    def __init__(self, roteiro):
        self.roteiro, self.pedidos, self.fim = roteiro, [], None

    def executar(self, pedido, *, cancelar=None, limite_s=180, ao_fase=None):
        self.pedidos.append(dict(pedido))
        try:
            return self.roteiro(self, pedido)
        finally:
            self.fim = time.monotonic()


def _final():
    return {"ok": True, "svg": "<svg/>", "n_paths": 0, "tempos": {}, "caixas": []}


def _escreve_previa(pedido, texto=SVG_PREVIA):
    destino = Path(pedido["previa_arquivo"])
    tmp = destino.with_name(destino.name + ".tmp")
    tmp.write_text(texto, encoding="utf-8")
    os.replace(tmp, destino)


def _preparar(tmp_path, componentes=True):
    ped, _ = _cena(tmp_path, [_caixa(3 * k, 0, 0, 3 * k + 1, 1, 1) for k in range(3)], corte=0.5)
    if componentes:
        ped["componentes"] = True
    ped.update({"protocolo": 1, "op": "desenho", "threads": 1})
    ped["vista"].setdefault("origem_pav", [0.0, 0.0, 0.0])
    return auxiliar.preparar(None, ped, caminho_ifc=ped["arquivo"])


class Cb:
    def __init__(self, levanta=False):
        self.textos, self.quando, self.visto, self.levanta = [], [], threading.Event(), levanta

    def __call__(self, texto):
        self.textos.append(texto)
        self.quando.append(time.monotonic())
        self.visto.set()
        if self.levanta:
            raise RuntimeError("callback ruim")


def test_h_filho_recebe_previa_arquivo_e_previa_chega_durante_a_espera_uma_vez(tmp_path):
    cb, chegou_antes = Cb(), []

    def roteiro(filho, pedido):
        assert pedido["previa_arquivo"] == str(p.pasta / "previa.svg")
        _escreve_previa(pedido)
        chegou_antes.append(cb.visto.wait(3.0))  # a previa tem de chegar ENQUANTO o filho ainda trabalha
        return _final()
    filho = FakeFilho(roteiro)
    with _preparar(tmp_path) as p:
        n_threads = threading.active_count()
        r = auxiliar.executar(p, previa=cb, filho=filho)
        time.sleep(0.3)  # nenhum chamado tardio
        assert threading.active_count() <= n_threads, "thread de vigia do arquivo nao terminou"
    assert chegou_antes == [True] and cb.textos == [SVG_PREVIA] and cb.quando[0] <= filho.fim
    assert r["svg"] == "<svg/>" and not r.get("parcial") and "data-obim-previa" not in r["svg"]
    assert len(filho.pedidos) == 1


def test_i_filho_que_estoura_depois_da_previa_mantem_a_previa_e_o_erro_sobe(tmp_path):
    cb = Cb()

    def roteiro(filho, pedido):
        _escreve_previa(pedido)
        assert cb.visto.wait(3.0)
        raise auxiliar.AuxiliarEstourouTempo(1.0, "geometria")
    with _preparar(tmp_path) as p:
        with pytest.raises(auxiliar.AuxiliarEstourouTempo):
            auxiliar.executar(p, previa=cb, filho=FakeFilho(roteiro))
    assert cb.textos == [SVG_PREVIA]


def test_j_previa_nunca_depois_do_final(tmp_path):
    cb = Cb()
    with _preparar(tmp_path) as p:
        r = auxiliar.executar(p, previa=cb, filho=FakeFilho(lambda f, ped: _final()))
        _escreve_previa(p.pedido)  # arquivo aparece depois do fim: ninguem mais le
        time.sleep(0.4)
    assert r["ok"] and cb.textos == []


def test_k_callback_que_levanta_nao_derruba_o_final(tmp_path):
    cb = Cb(levanta=True)

    def roteiro(filho, pedido):
        _escreve_previa(pedido)
        assert cb.visto.wait(3.0)
        time.sleep(0.2)
        return _final()
    with _preparar(tmp_path) as p:
        r = auxiliar.executar(p, previa=cb, filho=FakeFilho(roteiro))
    assert r["ok"] and len(cb.textos) == 1


@pytest.mark.parametrize("caso", ["sem_previa", "sem_componentes"])
def test_l_sem_previa_ou_sem_componentes_nada_muda_no_ramo_do_filho(tmp_path, caso):
    cb = Cb()
    filho = FakeFilho(lambda f, ped: _final())
    with _preparar(tmp_path, componentes=caso != "sem_componentes") as p:
        auxiliar.executar(p, previa=None if caso == "sem_previa" else cb, filho=filho)
    assert "previa_arquivo" not in filho.pedidos[0] and cb.textos == []


# ---------------------------------------------------------------- gerente: aquecer ao salvar
def test_m_gerente_salvar_com_caminho_aquece_depois_de_matar_os_filhos(monkeypatch, tmp_path):
    pytest.importorskip("PySide6.QtCore")
    from PySide6.QtCore import QCoreApplication
    QCoreApplication.instance() or QCoreApplication([])
    from openbim_app.desenho.gerente import GerenteDesenho

    ifc = tmp_path / "m.ifc"
    ifc.write_text("x")
    eventos = []

    class F:
        def salvar(self): eventos.append(("salvar",))
        def invalidar(self): pass
        def podar(self): pass
        def fechar(self): pass

    monkeypatch.setattr(GerenteDesenho, "aquecer", lambda self, caminho, **kw: eventos.append(("aquecer", str(caminho), kw)))
    g = GerenteDesenho(filho_persistente=True)
    g._filhos_doc[ifc.resolve()] = F()
    try:
        g.salvar()
        assert eventos == [("salvar",)], "sem argumentos: igual a hoje, nao aquece"
        eventos.clear()
        g.salvar(str(ifc), revisao=2, revisao_salva=2)
        assert eventos == [("salvar",), ("aquecer", str(ifc), {"revisao": 2, "revisao_salva": 2})]
    finally:
        g._filhos_doc.clear()
        g.fechar()


# ---------------------------------------------------------------- revisao Argon: pesados="silhueta", corrida da vigia, fallback
def _cena_pesados(tmp_path, classes, n=2):
    """n caixas separadas; `limiar_pesado=1` torna pesada (silhueta) toda candidata; `IfcFurniture` + moveis_como_caixa nao e candidata."""
    ped, ids = _cena(tmp_path, [_caixa(3 * k, 0, 0, 3 * k + 1, 1, 1) for k in range(n)], corte=0.5, classes=classes)
    ped.update({"componentes": True, "threads": 1, "pesados": "silhueta", "limiar_pesado": 1, "moveis_como_caixa": True,
                "previa_arquivo": str(tmp_path / "previa.svg")})
    return ped, ids


def _espia_pesadas(monkeypatch, previa):
    ordem, orig = [], D._pesadas_para_svg

    def esp(*a, **k):
        ordem.append(os.path.exists(previa) and bool(MARCA.search(Path(previa).read_text(encoding="utf-8"))))
        return orig(*a, **k)
    monkeypatch.setattr(D, "_pesadas_para_svg", esp)
    return ordem


def test_n_pesados_previa_cobre_todos_uma_carga_e_antes_das_pesadas(monkeypatch, tmp_path):
    ped, ids = _cena_pesados(tmp_path, {1: "IfcFurniture"})  # peca 0 pesada (candidata); peca 1 movel como caixa (nao candidata)
    esp = Espioes(monkeypatch, ped["previa_arquivo"])
    ordem = _espia_pesadas(monkeypatch, ped["previa_arquivo"])
    fases = []
    r = _roda(ped, fases)
    assert r["ok"] and [p["id"] for p in r["pesados"]] == [ids[0]], "premissa: so a peca 0 virou silhueta"
    guids = [g for _, g in ped["elementos"]]
    texto = Path(ped["previa_arquivo"]).read_text(encoding="utf-8")
    assert MARCA.search(texto) and sorted(_guids(texto)) == sorted(guids), "previa cobre TODOS os GUIDs pedidos, pesados inclusive"
    assert [p["guid"] for p in esp.chamadas_previa[0]["pecas"]] == guids
    assert esp.formas == [sorted(ids)], "UMA carga de formas_do_mundo, com todos os elementos pedidos"
    assert ordem == [True], "previa gravada ANTES de _pesadas_para_svg"
    assert fases.count("previa") == 1


def test_o_pesados_todas_pesadas_previa_ainda_e_gerada(monkeypatch, tmp_path):
    ped, ids = _cena_pesados(tmp_path, {})  # as duas viram silhueta: `restantes` vazio (hoje cai no fallback sem previa)
    esp = Espioes(monkeypatch, ped["previa_arquivo"])
    fases = []
    _roda(ped, fases)
    guids = [g for _, g in ped["elementos"]]
    assert len(esp.chamadas_previa) == 1 and fases.count("previa") == 1, "previa gerada uma vez mesmo sem restantes"
    texto = Path(ped["previa_arquivo"]).read_text(encoding="utf-8")
    assert MARCA.search(texto) and sorted(_guids(texto)) == sorted(guids)
    assert esp.formas == [sorted(ids)]


def test_p_leitura_lenta_nunca_entrega_depois_de_filho_executar_voltar(monkeypatch, tmp_path):
    cb = Cb()
    orig = Path.read_text

    def lento(self, *a, **k):
        t = orig(self, *a, **k)
        if self.name == "previa.svg":
            time.sleep(0.4)  # leitura em andamento quando o filho termina
        return t
    monkeypatch.setattr(Path, "read_text", lento)

    def roteiro(filho, pedido):
        _escreve_previa(pedido)
        time.sleep(0.2)  # o vigia (poll 0,05 s) ja comecou a ler; o filho volta antes de a leitura acabar
        return _final()
    filho = FakeFilho(roteiro)
    with _preparar(tmp_path) as p:
        auxiliar.executar(p, previa=cb, filho=filho)
        time.sleep(0.6)
    assert all(q <= filho.fim for q in cb.quando), "previa entregue DEPOIS de filho.executar voltar"
    assert cb.textos == [], "previa que so ficou pronta depois do final deve ser descartada"


def test_q_fallback_apos_filho_indisponivel_nao_duplica_previa_e_remove_residuo(monkeypatch, tmp_path):
    cb, no_fallback = Cb(), []

    def roteiro(filho, pedido):
        _escreve_previa(pedido)
        assert cb.visto.wait(3.0)
        raise auxiliar_filho.FilhoIndisponivel("indisponivel")

    def descartavel(preparado, limite_s, cancelar, previa=None, previa_caminho=None):
        no_fallback.append(previa_caminho is not None and previa_caminho.exists())
        if callable(previa) and previa_caminho is not None and previa_caminho.exists():  # o real entrega o que achar no arquivo
            previa(previa_caminho.read_text(encoding="utf-8"))
        return _final()
    from openbim_app.desenho import filho as auxiliar_filho
    monkeypatch.setattr(auxiliar, "_executar_filho", descartavel)
    with _preparar(tmp_path) as p:
        r = auxiliar.executar(p, previa=cb, filho=FakeFilho(roteiro))
    assert r["ok"] and no_fallback == [False], "arquivo residual da previa do filho tem de sumir antes do fallback"
    assert cb.textos == [SVG_PREVIA], "previa entregue uma vez so no total"
