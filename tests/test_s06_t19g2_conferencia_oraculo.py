# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oraculo F0-S06-T19g2: so usa o IFC salvo quando ele bate com o modelo. Nao editar nesta tarefa.

CONTRATO (decisoes do oraculo; o cartao deixou o nome e o mapeamento em aberto)
1. Gate (`GerenteDesenho.pedir(tipo, ifc, guid, *, caminho_ifc=None, revisao_salva=None, revisao=None, **opcoes)`): o motor so recebe
   `opcoes["caminho_ifc"]` quando `caminho_ifc` foi dado, `revisao is not None and revisao == revisao_salva` e o arquivo existe.
   `revisao_salva` NUNCA vai ao motor; `caminho_ifc` nao vai quando o gate falha (None == None nao abre o gate).
2. Erro `Divergente`: classe `openbim_app.desenho.auxiliar.Divergente`, subclasse de `ErroAuxiliar` e de `ArquivoDivergente`
   (os testes antigos de `ArquivoDivergente` seguem valendo). A resposta CRUA do filho, nos pedidos que levam `assinatura`
   (isto e, abertos via `caminho_ifc`), tem `erro.tipo == "Divergente"` em vez de `"ArquivoDivergente"`, nas ops `desenho` e `caixas`
   (conferencia de pares `[id, GlobalId]` e de assinatura). Sem `assinatura` (IFC reduzido) o tipo continua `"ArquivoDivergente"`.
   `auxiliar._tratar_resposta` mapeia o tipo `"Divergente"` para `Divergente`. Nada e desenhado (`_corte`/`_planta*` nao rodam, sem `svg`).
3. `auxiliar.preparar(ifc, pedido, caminho_ifc=<arquivo existente>)` grava `pedido["assinatura"] = [st_size, st_mtime_ns]` (ints, JSON) do
   arquivo resolvido; sem `caminho_ifc` (ou arquivo inexistente) NAO ha `assinatura`. A conferencia da assinatura (`os.stat` contra ela) fica dentro de
   `desenho.processar` / `caixas.processar` (nao so em `processo.entrada`), antes de qualquer desenho.
4. `corte.gerar_corte` e `planta.gerar_planta`: se o pedido usou `caminho_ifc` e o filho/executor responde `Divergente` (em qualquer fase),
   refazem UMA vez pelo reduzido (sem `caminho_ifc`), com SVG igual ao do caminho normal. Segunda divergencia propaga `Divergente`.
   Sem `caminho_ifc`, `Divergente` propaga sem retry. Outro erro (ex.: `FalhaNoAuxiliar`) nunca causa retry.

MUTANTES derrubados: gate sempre aberto (test_1*), conferencia de GlobalId removida (test_2*), assinatura ignorada (test_3*: arquivo regravado com
os mesmos pares), sem retry (test_4_stub*, test_4_e2e), retry sem limite (test_4_segunda: a conta de chamadas e o corta-circuito em 12).
Comparacoes de SVG sao deterministas (T19g1 test_1b prova isso para o corte; a planta e comparada contra si mesma na mesma cena)."""
from __future__ import annotations

import copy
import os
import threading
import time
from pathlib import Path

import ifcopenshell
import ifcopenshell.guid
import pytest
import s06_t07b_aux as B
import s06_t07c_aux as C
from s05_conteudo_aux import _limpa, exigir  # noqa: F401  (fixture autouse e guarda)
from s06_t15i_aux import corte, desenho_geo, local, planta  # noqa: F401

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QtCore = pytest.importorskip("PySide6.QtCore")
from PySide6.QtCore import QCoreApplication, QEventLoop, QTimer  # noqa: E402

from openbim_app.desenho import auxiliar  # noqa: E402
from openbim_app.desenho.gerente import GerenteDesenho  # noqa: E402


# ------------------------------------------------------------------ (1) gate do gerente
@pytest.fixture(scope="module")
def app():
    return QCoreApplication.instance() or QCoreApplication([])


class MotorEspiao:
    def __init__(self):
        self.opcoes = []

    def __call__(self, tipo, ifc, guid, opcoes, *, cancelar, progresso, **kw):
        self.opcoes.append(dict(opcoes))
        return {"svg": "<svg/>", "n_paths": 0, "tempos": {}, "caixas": [], "em_cache": []}


def _pedir(app, **kw):
    m = MotorEspiao()
    g = GerenteDesenho(motor=m, chave_estado=lambda t, i, gu, o: f"{t}|{gu}|{len(m.opcoes)}|{time.monotonic_ns()}")
    fim = []
    g.pronto.connect(lambda c, d: fim.append(("pronto", c)))
    g.falhou.connect(lambda c, e: fim.append(("falhou", e)))
    loop = QEventLoop()
    g.pronto.connect(lambda *_: loop.quit())
    g.falhou.connect(lambda *_: loop.quit())
    QTimer.singleShot(5000, loop.quit)
    g.pedir("corte", object(), "GUID-VISTA", **kw)
    loop.exec()
    g.encerrar()
    assert fim and fim[0][0] == "pronto", fim
    assert len(m.opcoes) == 1
    return m.opcoes[0]


@pytest.mark.parametrize("revisao,salva,existe,abre", [
    (5, 5, True, True),
    (5, 6, True, False),       # modelo mudou depois do salvo
    (None, None, True, False),  # None == None nao pode abrir o gate
    (5, None, True, False),
    (None, 5, True, False),
    (5, 5, False, False),      # arquivo sumiu
])
def test_1_gate_do_gerente(app, tmp_path, revisao, salva, existe, abre):
    arq = tmp_path / "salvo.ifc"
    if existe:
        arq.write_text("ISO-10303-21;")
    op = _pedir(app, caminho_ifc=arq, revisao=revisao, revisao_salva=salva)
    assert "revisao_salva" not in op and "revisao" not in op
    if abre:
        assert Path(op["caminho_ifc"]) == arq
    else:
        assert "caminho_ifc" not in op, "gate fechado: o motor nao pode receber o caminho"


def test_1b_sem_caminho_nada_vai_ao_motor(app):
    op = _pedir(app, revisao=3, revisao_salva=3)
    assert "caminho_ifc" not in op and "revisao_salva" not in op


# ------------------------------------------------------------------ cena do corte (como T19g1)
def _cena(tmp_path):
    exigir()
    f, _g = C.modelo("IFC4", vaos=(C.PORTA,))
    salvo = tmp_path / "salvo.ifc"
    f.write(str(salvo))
    gid = C.corte(f)
    return f, gid, salvo


class Rastro:
    """Executor em processo: grava op/arquivo de cada chamada; `diverge(pedido)` decide se responde Divergente cru."""

    def __init__(self, diverge=None, erro=None, limite=12):
        self.diverge, self.erro, self.limite = diverge, erro, limite
        self.chamadas = []

    def __call__(self, pedido):
        self.chamadas.append({"op": pedido.get("op"), "arquivo": str(Path(pedido["arquivo"]).resolve()), "assinatura": pedido.get("assinatura"),
                              "pedido": copy.deepcopy(pedido)})
        if len(self.chamadas) > self.limite:
            raise AssertionError("retry sem limite")
        if self.diverge is not None and self.diverge(pedido):
            return {"ok": False, "erro": {"tipo": self.erro or "Divergente", "mensagem": "arquivo salvo nao confere", "rastro": ""}}
        return local.executar(pedido)

    def usos(self, arq):
        return [c for c in self.chamadas if c["arquivo"] == str(Path(arq).resolve())]


def _pedido_desenho_com_arquivo(f, gid, salvo):
    """Pedido de desenho exatamente como o corte o envia com caminho_ifc (capturado do executor)."""
    ex = Rastro()
    corte.gerar_corte(f, gid, executor=ex, caminho_ifc=salvo)
    ds = [c for c in ex.chamadas if c["op"] == "desenho"]
    assert len(ds) == 1 and ds[0]["arquivo"] == str(salvo.resolve())
    return ds[0]["pedido"]


# ------------------------------------------------------------------ (2) pares id/GlobalId no filho
def test_2_par_trocado_e_divergente_e_nada_e_desenhado(tmp_path, monkeypatch):
    f, gid, salvo = _cena(tmp_path)
    ped = _pedido_desenho_com_arquivo(f, gid, salvo)
    assert desenho_geo.processar(copy.deepcopy(ped)).get("ok") is True, "controle: pares certos desenham"
    assert len(ped["elementos"]) >= 2
    ruim = copy.deepcopy(ped)
    (i0, g0), (i1, g1) = ruim["elementos"][0], ruim["elementos"][1]
    ruim["elementos"][0], ruim["elementos"][1] = [i0, g1], [i1, g0]  # ids existem, GlobalIds trocados
    desenhou = []
    for nome in ("_corte", "_corte_em_faixas", "_planta_recortada", "_planta_em_faixas", "_planta_por_componentes"):
        monkeypatch.setattr(desenho_geo, nome, lambda *a, **k: desenhou.append(1) or {"ok": True, "svg": "x"}, raising=False)
    r = desenho_geo.processar(ruim)
    assert r["ok"] is False and r["erro"]["tipo"] == "Divergente"
    assert "svg" not in r and not desenhou


def test_2b_global_id_inexistente_tambem_diverge(tmp_path):
    f, gid, salvo = _cena(tmp_path)
    ped = _pedido_desenho_com_arquivo(f, gid, salvo)
    ped["elementos"][0][1] = ifcopenshell.guid.new()
    r = desenho_geo.processar(ped)
    assert r["ok"] is False and r["erro"]["tipo"] == "Divergente"


def test_2c_caixas_tambem_confere(tmp_path):
    f, gid, salvo = _cena(tmp_path)
    ws = f.by_type("IfcBuildingElement")[:2]
    assert len(ws) == 2
    base = {"op": "caixas", "elementos": [[w.id(), w.GlobalId] for w in ws], "vista": {"guid": gid}, "threads": 1}
    with auxiliar.preparar(f, base, caminho_ifc=salvo) as p:
        assert local.executar(p.pedido)["ok"] is True
        ruim = copy.deepcopy(p.pedido)
        ruim["elementos"] = [[ws[0].id(), ws[1].GlobalId], [ws[1].id(), ws[0].GlobalId]]
        r = local.executar(ruim)
    assert r["ok"] is False and r["erro"]["tipo"] == "Divergente"


def test_2d_sem_assinatura_continua_arquivo_divergente(tmp_path):
    """Reduzido (sem caminho_ifc): tipo antigo, para nao quebrar T07/T15."""
    f, gid, salvo = _cena(tmp_path)
    ex = Rastro()
    corte.gerar_corte(f, gid, executor=ex)
    ped = [c for c in ex.chamadas if c["op"] == "desenho"][0]["pedido"]
    ped.pop("arquivo")
    with auxiliar.preparar(f, ped) as p:  # reduzido novo (a pasta do original ja foi apagada)
        assert "assinatura" not in p.pedido
        p.pedido["elementos"][0][1] = ifcopenshell.guid.new()
        r = local.executar(p.pedido)
    assert r["ok"] is False and r["erro"]["tipo"] == "ArquivoDivergente"


def test_2e_classe_divergente_e_mapeamento():
    assert issubclass(auxiliar.Divergente, auxiliar.ErroAuxiliar) and issubclass(auxiliar.Divergente, auxiliar.ArquivoDivergente)
    with pytest.raises(auxiliar.Divergente):
        auxiliar._tratar_resposta({"ok": False, "erro": {"tipo": "Divergente", "mensagem": "x", "rastro": ""}})
    with pytest.raises(auxiliar.ArquivoDivergente) as e:
        auxiliar._tratar_resposta({"ok": False, "erro": {"tipo": "ArquivoDivergente", "mensagem": "x", "rastro": ""}})
    assert not isinstance(e.value, auxiliar.Divergente)


# ------------------------------------------------------------------ (3) assinatura do arquivo
def test_3_preparar_grava_assinatura(tmp_path):
    f, gid, salvo = _cena(tmp_path)
    st = os.stat(salvo)
    with auxiliar.preparar(f, {"op": "ping"}, caminho_ifc=salvo) as p:
        assert p.pedido["assinatura"] == [st.st_size, st.st_mtime_ns]
        assert all(isinstance(x, int) for x in p.pedido["assinatura"])
    with auxiliar.preparar(f, {"op": "ping", "elementos": [[f.by_type("IfcWall")[0].id(), f.by_type("IfcWall")[0].GlobalId]],
                               "vista": {"guid": gid}}) as p:
        assert "assinatura" not in p.pedido
    with auxiliar.preparar(f, {"op": "ping", "elementos": [[f.by_type("IfcWall")[0].id(), f.by_type("IfcWall")[0].GlobalId]],
                               "vista": {"guid": gid}}, caminho_ifc=tmp_path / "nao_existe.ifc") as p:
        assert "assinatura" not in p.pedido


def _pedido_real_com_assinatura(f, gid, salvo):
    ex = Rastro()
    corte.gerar_corte(f, gid, executor=ex, caminho_ifc=salvo)
    d = [c for c in ex.chamadas if c["op"] == "desenho"][0]["pedido"]
    assert d["assinatura"] == [os.stat(salvo).st_size, os.stat(salvo).st_mtime_ns]
    return d


def test_3b_arquivo_regravado_com_os_mesmos_pares_diverge(tmp_path):
    """Pares id/GlobalId continuam certos: so a assinatura pode denunciar (mata 'assinatura ignorada')."""
    f, gid, salvo = _cena(tmp_path)
    ped = _pedido_real_com_assinatura(f, gid, salvo)
    assert desenho_geo.processar(copy.deepcopy(ped))["ok"] is True, "controle: arquivo intacto desenha"
    with open(salvo, "a") as fh:
        fh.write("\n")  # muda o tamanho; conteudo IFC igual
    r = desenho_geo.processar(copy.deepcopy(ped))
    assert r["ok"] is False and r["erro"]["tipo"] == "Divergente"


def test_3c_so_o_mtime_mudou_diverge(tmp_path):
    f, gid, salvo = _cena(tmp_path)
    ped = _pedido_real_com_assinatura(f, gid, salvo)
    st = os.stat(salvo)
    os.utime(salvo, ns=(st.st_atime_ns, st.st_mtime_ns + 5_000_000_000))
    assert os.stat(salvo).st_size == st.st_size
    r = desenho_geo.processar(copy.deepcopy(ped))
    assert r["ok"] is False and r["erro"]["tipo"] == "Divergente"


def test_3d_caixas_confere_assinatura(tmp_path):
    f, gid, salvo = _cena(tmp_path)
    w = f.by_type("IfcWall")[0]
    base = {"op": "caixas", "elementos": [[w.id(), w.GlobalId]], "vista": {"guid": gid}, "threads": 1}
    with auxiliar.preparar(f, base, caminho_ifc=salvo) as p:
        with open(salvo, "a") as fh:
            fh.write("\n")
        r = local.executar(p.pedido)
    assert r["ok"] is False and r["erro"]["tipo"] == "Divergente"


# ------------------------------------------------------------------ (4) retry pelo reduzido
def _cena_planta(tmp_path):
    exigir()
    f, pavs, _g = B.modelo("IFC4")
    gid = B.planta(f, pavs[0])
    salvo = tmp_path / "salvo_planta.ifc"
    f.write(str(salvo))
    return f, gid, salvo


def _gerador(tipo, tmp_path):
    if tipo == "corte":
        f, gid, salvo = _cena(tmp_path)
        return f, salvo, lambda **kw: corte.gerar_corte(f, gid, **kw)
    f, gid, salvo = _cena_planta(tmp_path)
    return f, salvo, lambda **kw: planta.gerar_planta(f, gid, **kw)


@pytest.mark.parametrize("tipo", ["corte", "planta"])
def test_4_stub_diverge_no_salvo_refaz_pelo_reduzido(tmp_path, tipo):
    f, salvo, gerar = _gerador(tipo, tmp_path)
    base = gerar(executor=Rastro())
    assert base.n_paths >= 3
    alvo = str(salvo.resolve())
    ex = Rastro(diverge=lambda p: str(Path(p["arquivo"]).resolve()) == alvo)
    c = gerar(executor=ex, caminho_ifc=salvo)
    assert c.svg == base.svg and c.n_paths == base.n_paths
    usos = ex.usos(salvo)
    assert 1 <= len(usos) <= 2, "o salvo e tentado, falha e nao volta"
    i_ultimo_salvo = max(i for i, c_ in enumerate(ex.chamadas) if c_["arquivo"] == alvo)
    depois = ex.chamadas[i_ultimo_salvo + 1:]
    assert depois and all(c_["arquivo"] != alvo and c_["assinatura"] is None for c_ in depois), "o refeito usa o reduzido"
    assert any(c_["op"] == "desenho" for c_ in depois)


@pytest.mark.parametrize("tipo", ["corte", "planta"])
def test_4_segunda_divergencia_propaga(tmp_path, tipo):
    f, salvo, gerar = _gerador(tipo, tmp_path)
    ex = Rastro(diverge=lambda p: True)
    with pytest.raises(auxiliar.Divergente):
        gerar(executor=ex, caminho_ifc=salvo)
    assert 2 <= len(ex.chamadas) <= 4, ex.chamadas  # tentativa + UM refazer (selecao + desenho em cada, no maximo)
    assert ex.chamadas[-1]["arquivo"] != str(salvo.resolve())
    assert len(ex.usos(salvo)) <= 2


@pytest.mark.parametrize("tipo", ["corte", "planta"])
def test_4_sem_caminho_ifc_nao_ha_retry(tmp_path, tipo):
    f, salvo, gerar = _gerador(tipo, tmp_path)
    ex = Rastro(diverge=lambda p: True)
    with pytest.raises(auxiliar.Divergente):
        gerar(executor=ex)
    assert len(ex.chamadas) == 1


@pytest.mark.parametrize("tipo", ["corte", "planta"])
def test_4_outro_erro_nao_refaz(tmp_path, tipo):
    f, salvo, gerar = _gerador(tipo, tmp_path)
    ex = Rastro(diverge=lambda p: True, erro="ZeroDivisionError")
    with pytest.raises(auxiliar.FalhaNoAuxiliar):
        gerar(executor=ex, caminho_ifc=salvo)
    assert len(ex.chamadas) == 1


@pytest.mark.parametrize("tipo", ["corte", "planta"])
def test_4_arquivo_certo_nao_refaz(tmp_path, tipo):
    f, salvo, gerar = _gerador(tipo, tmp_path)
    base = gerar(executor=Rastro())
    ex = Rastro()
    c = gerar(executor=ex, caminho_ifc=salvo)
    assert c.svg == base.svg
    assert all(c_["arquivo"] == str(salvo.resolve()) for c_ in ex.chamadas), "sem divergencia, tudo pelo salvo"


def test_4_e2e_arquivo_velho_de_verdade(tmp_path):
    """Modelo mudou (GlobalId de uma parede) depois do salvo: filho real detecta, SVG final = o do reduzido."""
    f, gid, salvo = _cena(tmp_path)
    f.by_type("IfcWall")[0].GlobalId = ifcopenshell.guid.new()
    base = corte.gerar_corte(f, gid, executor=Rastro())
    assert "IfcWall" in base.svg
    ex = Rastro()
    c = corte.gerar_corte(f, gid, executor=ex, caminho_ifc=salvo)
    assert c.svg == base.svg and c.n_paths == base.n_paths
    alvo = str(salvo.resolve())
    assert ex.usos(salvo), "o salvo foi tentado primeiro"
    assert ex.chamadas[-1]["arquivo"] != alvo and ex.chamadas[-1]["op"] == "desenho"
    primeiro_reduzido = next(i for i, c_ in enumerate(ex.chamadas) if c_["arquivo"] != alvo)
    assert all(c_["arquivo"] != alvo for c_ in ex.chamadas[primeiro_reduzido:])


def test_4_e2e_arquivo_regravado(tmp_path):
    """Arquivo regravado entre preparar e abrir (so a assinatura muda): o executor regrava o salvo antes de delegar."""
    f, gid, salvo = _cena(tmp_path)
    base = corte.gerar_corte(f, gid, executor=Rastro())
    alvo = str(salvo.resolve())
    feito = []

    def regrava(p):
        if str(Path(p["arquivo"]).resolve()) == alvo and not feito:
            feito.append(1)
            with open(salvo, "a") as fh:
                fh.write("\n")
        return False  # a divergencia tem de vir do filho real, nao do stub

    ex = Rastro(diverge=regrava)
    c = corte.gerar_corte(f, gid, executor=ex, caminho_ifc=salvo)
    assert feito and c.svg == base.svg
    assert ex.chamadas[-1]["arquivo"] != alvo
