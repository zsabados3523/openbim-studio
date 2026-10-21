# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo do F0-S04-V1 (LOTE_OPUS_69; ADR-004 §5.1, regras 1 a 6 e critério 1): a forma "mista" de `prototypes/s04/fluxo_a/lote.py`.
Quem implementa o V1 não edita este arquivo; quem tira os `@AINDA_NAO` (xfail estrito) é o autor do oráculo, em commit próprio, depois da implementação
(só as linhas `AINDA_NAO = ...` e `@AINDA_NAO`). Contrato (o implementador lê só isto e o cartão `docs/state/cards/F0-S04/F0-S04-V1.md`):
1. `lote.medir(f, "mista", ...)`: o comando roda na thread da JANELA, cedendo como a forma 2 (`_Fatiador`, `fluxo_a.api` e `Cena.atualizar` são operações);
   cada chamada de `obimcore.malhas` (capturada no início do comando, como na forma 2) vira UM pedido inteiro (sem blocos) a uma `threading.Thread`
   chamada "lote-geometria"; a janela fecha a fatia em andamento, entra em `QEventLoop.exec()` e só sai quando o resultado chega por sinal Qt enfileirado
   (`Qt.QueuedConnection`) de um QObject criado na thread da janela; erro da geometria sobe na thread da janela (a mesma exceção). A espera não é fatia.
   Saída: a de `medir` + `geometria` = [{"t_ini_ms", "t_fim_ms", "n", "thread"}] (relógio `obimcore.agora`, medido na thread de geometria).
2. Regra 3: durante a malha a trava do modelo segue presa pelo comando e nada escreve (nenhuma `fluxo_a.api` nem `Cena.atualizar` sobreposta).
3. Regra 4: durante a espera a janela trata eventos; tratador que pede comando com `espera=0` recebe `ModeloOcupado` (nunca entra).
4. Regra 5: na thread de geometria, nenhum objeto Qt é construído e a única chamada ao PySide6 é `SignalInstance.emit`.
5. Comando `{"cmd": "composto", "passos": [...]}` só na mista (`lote_partido_cmd`, `lote_pesado_cmd`): passos em ordem, um `executar_detalhado` cada.
6. Critério 1 (intactos), `main_mista` e `veredito_mista`: na segunda parte, `tests/test_s04_v1_veredito_oraculo.py`.
GUARDA (pula, nunca afrouxa): casos com janela em SUBPROCESSO sob `xvfb-run -a` (nunca na tela real; Windows só no CI ou com OBIM_S04_TELA_VIRTUAL=1);
os casos "real" pedem o obimcore; com OBIM_S04_V1_OBRIGATORIO=1 todo pulo vira falha. Os números do §5.1 (itens 2 a 8) são MEDIÇÃO do cartão, não daqui."""
import importlib.util
import json
import os
import shutil
import statistics
import sys
import tempfile
import threading
import time
import traceback
import types
from pathlib import Path

import pytest
import s04_fluxo_aux as aux

ESTE = Path(__file__).resolve()
OBRIGATORIO = os.environ.get("OBIM_S04_V1_OBRIGATORIO") == "1"
AINDA_NAO = pytest.mark.xfail(strict=True, reason="V1: lote.py ainda não tem a forma mista")
GEO = "lote-geometria"
REG = {"log": [], "qt": [], "falha": False, "geo_s": 0.3, "f": None}


def pular(msg):
    (pytest.fail if OBRIGATORIO else pytest.skip)(f"\n!!! S04-V1: {msg} (oráculo da forma mista NÃO FOI EXECUTADO) !!!\n")


# ---------- espiões (só no subprocesso, ANTES de `import lote`) ----------
def _perfil(frame, ev, arg):  # regra 5: chamada C ao PySide6/shiboken6 na thread de geometria (construtor não aparece aqui: ver _espioes_qt)
    if ev == "c_call" and threading.current_thread().name == GEO:
        mods = (getattr(arg, "__module__", None) or "", type(getattr(arg, "__self__", None)).__module__ or "")
        if any(m.startswith(("PySide6", "shiboken6")) for m in mods) and getattr(arg, "__qualname__", "") != "SignalInstance.emit":
            REG["qt"].append(f"chamada {getattr(arg, '__qualname__', repr(arg))}")


def _espioes_qt():  # construção de QObject, QEventLoop, QTimer ou QThread fora da thread da janela
    import PySide6.QtCore as C
    for nome in ("QObject", "QEventLoop", "QTimer", "QThread"):
        base = getattr(C, nome)

        def init(s, *a, _b=base, _n=nome, **k):
            threading.current_thread() is threading.main_thread() or REG["qt"].append(f"{_n} construído em {threading.current_thread().name}")
            _b.__init__(s, *a, **k)
        setattr(C, nome, type(nome, (base,), {"__init__": init}))
    threading.setprofile(_perfil)


def _ambiente():  # obimcore de ensaio (malha que dorme `geo_s` sem o bloqueio), fluxo_a.api espiã; janela Qt simples
    agora = lambda: time.perf_counter() * 1000.0  # noqa: E731

    def malhas(ifc, guids):
        t, f = agora(), REG["f"]
        time.sleep(REG["geo_s"])
        REG["log"].append(("malhas", threading.current_thread().name, t, agora(), bool(f and f.trava.locked()), len(list(guids))))
        if REG["falha"]:
            raise RuntimeError("falha de ensaio na geometria")
        return {g: {"indices": []} for g in guids}
    sys.modules["obimcore"] = types.SimpleNamespace(agora=agora, malhas=malhas)
    _espioes_qt()
    from PySide6.QtWidgets import QApplication, QMainWindow
    app, jan = QApplication.instance() or QApplication(sys.argv[:1]), QMainWindow()
    jan.resize(640, 480)
    jan.show()
    for _ in range(30):
        app.processEvents()
        time.sleep(0.01)
    import fluxo_a
    import lote

    def api(nome, *a, **k):
        t = agora()
        time.sleep(0.001)
        REG["log"].append(("api", threading.current_thread().name, t, agora(), nome))
    fluxo_a.api = api
    return app, jan, lote, agora


class _Cena:
    def atualizar(s, lote_, remover):
        t = time.perf_counter() * 1000.0
        REG["log"].append(("atualizar", threading.current_thread().name, t, t + 0.01, bool(REG["f"].trava.locked())))
        return None

    def relogio(s):
        return []


class _F:  # o `f` de ensaio: o mesmo caminho do FluxoA (trava não reentrante, api, `obimcore.malhas` lida na hora, `self.cena.atualizar`)
    def __init__(s, app, jan, agora, n_api=300):
        s._app, s.janela_principal, s.agora, s.n_api, s.trava, s.ifc, s.cena, s.cmds = app, jan, agora, n_api, threading.Lock(), object(), _Cena(), []
        REG["f"] = s

    def executar(s, cmd, espera=None):
        return s.executar_detalhado(cmd, espera)[0]

    def executar_detalhado(s, cmd, espera=None):
        import fluxo_a
        import obimcore
        if not (s.trava.acquire(blocking=False) if espera == 0 else s.trava.acquire()):
            raise fluxo_a.ModeloOcupado("o modelo está ocupado por outro comando")
        try:
            t0 = s.agora()
            s.cmds.append(cmd.get("nome", cmd.get("cmd")))
            for _ in range(s.n_api):
                fluxo_a.api("op")
            mal = obimcore.malhas(s.ifc, [f"G{i}" for i in range(7)])
            s.cena.atualizar(mal, [])
            for _ in range(s.n_api // 3):
                fluxo_a.api("op")
            return [cmd.get("nome", "G")], {"sequencia": None, "t0_ms": t0, "t_comando_ms": s.agora(), "criados": [cmd.get("nome", "G")]}
        finally:
            s.trava.release()

    def _bombear(s, cond=None, ms=0):  # como FluxoA._bombear, na thread da janela
        fim = time.perf_counter() + ms / 1000
        while True:
            s._app.processEvents()
            if cond is None or cond():
                return True
            if time.perf_counter() >= fim:
                return False
            time.sleep(0.0005)


def c_ensaio(res):  # regras 2 a 5 e erro, com o `f` de ensaio (sem obimcore de verdade)
    import fluxo_a
    from PySide6.QtCore import QTimer
    app, jan, lote, agora = _ambiente()
    api0, mal0 = fluxo_a.api, sys.modules["obimcore"].malhas
    f, tent = _F(app, jan, agora), []

    def tenta():  # regra 4: só tenta com a trava presa (durante o comando)
        if f.trava.locked():
            try:
                f.executar({"cmd": "intruso", "nome": "intruso"}, espera=0)
                tent.append((agora(), "passou"))
            except fluxo_a.ModeloOcupado:
                tent.append((agora(), "ocupado"))
            except Exception as e:
                tent.append((agora(), repr(e)))
    tm = QTimer()
    tm.setInterval(5)
    tm.timeout.connect(tenta)
    tm.start()
    r = lote.medir(f, "mista", 10, cmd={"cmd": "ensaio"})
    tm.stop()
    f.cmds.clear()
    res["r"] = {k: r.get(k) for k in ("forma", "thread_janela", "thread_lote", "pulsos", "mouse", "fatias", "geometria")}
    res["log"], res["tentativas"], res["qt"] = list(REG["log"]), tent, list(REG["qt"])
    res["restaurado"] = fluxo_a.api is api0 and sys.modules["obimcore"].malhas is mal0 and isinstance(f.cena, _Cena)
    REG["log"].clear()
    REG["falha"] = True  # erro na geometria: sobe na janela, solta a trava, restaura os embrulhos, não deixa a thread viva
    try:
        lote.medir(f, "mista", 10, cmd={"cmd": "ensaio"}, mouse=False)
        res["excecao"] = None
    except Exception as e:
        res["excecao"] = [type(e).__name__, str(e)]
    REG["falha"] = False
    res["erro_log"] = [x[:2] for x in REG["log"] if x[0] == "malhas"]
    res["erro_estado"] = {"trava": f.trava.locked(), "restaurado": fluxo_a.api is api0 and sys.modules["obimcore"].malhas is mal0 and isinstance(f.cena, _Cena),
                          "vivas": sorted(t.name for t in threading.enumerate() if t.name == GEO)}
    REG["geo_s"] = 0.02  # composto: passos em ordem, um executar_detalhado cada; detalhe somado
    f.n_api = 20
    f.cmds.clear()
    rc = lote.medir(f, "mista", 10, cmd={"cmd": "composto", "passos": [{"cmd": "ensaio", "nome": n} for n in ("a", "b", "c")]}, mouse=False)
    res["composto"] = {"cmds": list(f.cmds), "criados": rc["criados"], "n_geo": len(rc["geometria"])}
    res["cmds_lote"] = [lote.lote_partido_cmd(10), lote.lote_pesado_cmd("GUIDPESADO", 10, 0.01)]
    res["qt_fim"] = list(REG["qt"])
    return res


def c_real(res, base, aberturas):  # o FluxoA e o obimcore de verdade: parede pesada e lote pequeno na mista
    import fluxo_a
    import lote
    import obimcore
    from PySide6.QtCore import QTimer
    tmp = Path(tempfile.mkdtemp())
    guid = lote.base_pesada(tmp / "b.ifc", int(base), int(aberturas))
    f = lote.preparar(str(tmp / "b.ifc"), tmp / "s")
    threading.setprofile(_perfil)
    log, mal0, api0 = [], obimcore.malhas, fluxo_a.api

    def malhas(ifc, guids):
        t = obimcore.agora()
        r = mal0(ifc, guids)
        log.append(("malhas", threading.current_thread().name, t, obimcore.agora(), f.trava.locked()))
        return r

    def api(nome, *a, **k):
        t = obimcore.agora()
        r = api0(nome, *a, **k)
        log.append(("api", threading.current_thread().name, t, obimcore.agora()))
        return r
    obimcore.malhas, fluxo_a.api = malhas, api
    nome0, tent = f.ler_propriedade(guid, "Name"), []

    def tenta():
        if f.trava.locked():
            t = time.perf_counter()
            v = f.ler_propriedade(guid, "Name")
            try:
                f.executar(dict(aux.PAREDE), espera=0)
                tent.append([obimcore.agora(), "passou", v, (time.perf_counter() - t) * 1000])
            except fluxo_a.ModeloOcupado:
                tent.append([obimcore.agora(), "ocupado", v, (time.perf_counter() - t) * 1000])
    tm = QTimer()
    tm.setInterval(5)
    tm.timeout.connect(tenta)
    paredes = len(f.ifc.by_type("IfcWall"))
    tm.start()
    rp = lote.medir(f, "mista", cmd={"cmd": "mover", "alvo": guid, "dx": 0.01, "dy": 0, "dz": 0})
    tm.stop()
    res["pesada"] = {"geometria": rp.get("geometria"), "pulsos": rp["pulsos"], "thread": rp["thread_lote"] == rp["thread_janela"], "forma": rp["forma"]}
    res["log"], res["tent"], res["nome0"], res["paredes"] = list(log), tent, nome0, len(f.ifc.by_type("IfcWall")) - paredes
    tri = lambda: int(f.cena.estatisticas()["triangulos"])  # noqa: E731
    obimcore.malhas, fluxo_a.api = mal0, api0
    t0 = tri()
    lote.medir(f, 2, 30, mouse=False)
    d2 = tri() - t0
    f.executar({"cmd": "desfazer"})
    f.executar({"cmd": "esperar", "ms": 300})
    t1 = tri()
    rm = lote.medir(f, "mista", 30, mouse=False)
    res["lote"] = {"tri_forma2": d2, "tri_mista": tri() - t1, "criados": rm["criados"], "geo": [g["n"] for g in rm.get("geometria") or []]}
    f.executar({"cmd": "desfazer"})
    res["desfeito"] = len(f.ifc.by_type("IfcWall")) - paredes
    res["qt"] = list(REG["qt"])
    f.fechar()
    return res


# ---------- testes ----------
def _rodar(nome, *a, limite, alvo=ESTE):
    if not (aux.PASTA / "lote.py").is_file():
        pular("prototypes/s04/fluxo_a/lote.py ausente")
    if not (os.environ.get("CI") or os.environ.get("OBIM_S04_TELA_VIRTUAL") == "1") if sys.platform == "win32" else not shutil.which("xvfb-run"):
        pular("sem tela virtual (xvfb-run; no Windows só no CI ou com OBIM_S04_TELA_VIRTUAL=1): nunca na tela real")
    from test_s04_viewport import caso
    try:
        return caso(nome, *a, alvo=alvo, limite=limite)
    except (pytest.fail.Exception, AssertionError) as e:  # o caso devolveu "erro" ou caiu: cada teste falha com ele (sem rodar o subprocesso de novo)
        return {"erro": str(e)}


def _ok(r):
    "erro" in r and pytest.fail(r["erro"][-3000:])
    return r


@pytest.fixture(scope="module")
def ensaio():
    return _rodar("ensaio", limite=180)


@pytest.fixture(scope="module")
def real():
    if importlib.util.find_spec("obimcore") is None:
        pular("módulo obimcore ausente")
    return _rodar("real", 30, 150, limite=300)


def test_v1_ambiente_tela_virtual_e_obimcore():  # sem marcador: com OBIM_S04_V1_OBRIGATORIO=1 a falta de ambiente falha aqui (o xfail não a esconde)
    if not (os.environ.get("CI") or os.environ.get("OBIM_S04_TELA_VIRTUAL") == "1") if sys.platform == "win32" else not shutil.which("xvfb-run"):
        pular("sem tela virtual")
    importlib.util.find_spec("obimcore") is None and pular("módulo obimcore ausente")
    assert (aux.PASTA / "lote.py").is_file()


def _dentro(t, ini, fim):
    return ini < t < fim


@AINDA_NAO
def test_v1_comando_na_janela_e_cada_malha_inteira_na_thread_de_geometria(ensaio):
    r = _ok(ensaio)["r"]
    mal = [x for x in ensaio["log"] if x[0] == "malhas"]
    assert r["forma"] == "mista" and r["thread_lote"] == r["thread_janela"], "a mista roda o comando na thread da janela (como a forma 2)"
    assert len(mal) == 1 and mal[0][1] == GEO and mal[0][5] == 7, f"um pedido inteiro (7 GlobalIds, sem blocos) na thread {GEO!r}: {mal}"
    g = r["geometria"]
    assert len(g) == 1 and g[0]["n"] == 7 and g[0]["thread"] != r["thread_janela"] and g[0]["t_fim_ms"] - g[0]["t_ini_ms"] >= 280, f"`geometria`: {g}"
    assert all(x[1] == "MainThread" for x in ensaio["log"] if x[0] in ("api", "atualizar")), "api e Cena.atualizar só na thread da janela"
    assert ensaio["restaurado"], "fluxo_a.api, obimcore.malhas e f.cena voltam a ser os de antes depois do comando"


@AINDA_NAO
def test_v1_regra_3_trava_presa_e_nada_escreve_durante_a_malha(ensaio):
    mal = [x for x in _ok(ensaio)["log"] if x[0] == "malhas"]
    assert mal and all(x[4] for x in mal), "durante a malha a trava do modelo segue presa pelo comando"
    for _, _, ini, fim, *_ in mal:
        dentro = [x for x in ensaio["log"] if x[0] in ("api", "atualizar") and x[3] > ini and x[2] < fim]
        assert not dentro, f"{len(dentro)} chamadas de api/Cena.atualizar sobrepostas à malha (regra 3: o comando espera parado): {dentro[:3]}"
    at = [x for x in ensaio["log"] if x[0] == "atualizar"]
    assert at and all(x[2] >= mal[0][3] for x in at) and all(x[4] for x in at), "Cena.atualizar depois do resultado, ainda com a trava"


@AINDA_NAO
def test_v1_regra_2_janela_trata_eventos_durante_a_malha_e_a_espera_nao_e_fatia(ensaio):
    r = _ok(ensaio)["r"]
    g = r["geometria"][0]
    pul = [t for t in r["pulsos"] if _dentro(t, g["t_ini_ms"], g["t_fim_ms"])]
    mouse = [m for m in r["mouse"] if m[2] is not None and _dentro(m[2], g["t_ini_ms"], g["t_fim_ms"])]
    assert len(pul) >= 10 and len(mouse) >= 5, f"a janela ficou parada esperando a geometria (300 ms): {len(pul)} pulsos e {len(mouse)} mouses tratados dentro"
    fz = r["fatias"]
    assert fz and len(fz) >= 20 and statistics.median(x["ms"] for x in fz) <= 20.0, "a mista fatia como a forma 2 (>= 20 fatias, mediana <= 20 ms)"
    assert max(x["ms"] for x in fz) < 150 and all(x["op_mais_longa"] != "obimcore.malhas" for x in fz), f"a espera da geometria entrou numa fatia: {max(fz, key=lambda x: x['ms'])}"


@AINDA_NAO
def test_v1_regra_4_tratador_durante_a_espera_recebe_modelo_ocupado(ensaio):
    g = _ok(ensaio)["r"]["geometria"][0]
    t = ensaio["tentativas"]
    dentro = [x for x in t if _dentro(x[0], g["t_ini_ms"], g["t_fim_ms"])]
    assert len(dentro) >= 5 and all(x[1] == "ocupado" for x in dentro), f"durante a espera: {len(dentro)} tentativas, {dentro[:3]}"
    assert all(x[1] == "ocupado" for x in t), f"nenhum comando entra no meio (reentrada proibida): {[x for x in t if x[1] != 'ocupado'][:3]}"


@AINDA_NAO
def test_v1_regra_5_nenhum_objeto_qt_fora_da_thread_da_janela(ensaio):
    _ok(ensaio)
    assert ensaio["r"]["geometria"], "sem geometria medida a regra 5 não foi exercitada"
    assert not ensaio["qt_fim"], f"na thread de geometria só `SignalInstance.emit`; nada construído fora da janela: {ensaio['qt_fim'][:5]}"


@AINDA_NAO
def test_v1_erro_na_geometria_sobe_na_janela_e_solta_tudo(ensaio):
    _ok(ensaio)
    assert ensaio["excecao"] == ["RuntimeError", "falha de ensaio na geometria"], f"o erro da thread de geometria sobe igual na janela: {ensaio['excecao']}"
    assert ensaio["erro_log"] == [["malhas", GEO]], f"o erro aconteceu na thread de geometria: {ensaio['erro_log']}"
    e = ensaio["erro_estado"]
    assert not e["trava"] and e["restaurado"] and not e["vivas"], f"trava solta, embrulhos restaurados, nenhuma {GEO} viva: {e}"


@AINDA_NAO
def test_v1_composto_roda_os_passos_em_ordem(ensaio):
    c = _ok(ensaio)["composto"]
    assert c == {"cmds": ["a", "b", "c"], "criados": 3, "n_geo": 3}, f"composto: um executar_detalhado por passo, em ordem; criados somados: {c}"
    partido, pesado = ensaio["cmds_lote"]
    lc = lambda n: {"cmd": "criar_paredes_lote", "quantidade": n, "tipo": "PAR15", "comprimento": 4.0, "altura": 2.8, "espessura": 0.15}  # noqa: E731
    assert partido == {"cmd": "composto", "passos": [lc(5), lc(5)]}, partido
    assert pesado == {"cmd": "composto", "passos": [lc(5), {"cmd": "mover", "alvo": "GUIDPESADO", "dx": 0.01, "dy": 0, "dz": 0}, lc(5)]}, pesado


@AINDA_NAO
def test_v1_real_parede_pesada_na_mista(real):
    r = _ok(real)
    p, mal = r["pesada"], [x for x in r["log"] if x[0] == "malhas"]
    assert p["forma"] == "mista" and p["thread"] and mal and all(x[1] == GEO and x[4] for x in mal), f"malha só na {GEO}, com a trava presa: {mal}"
    for _, _, ini, fim, _ in mal:
        assert not [x for x in r["log"] if x[0] == "api" and x[3] > ini and x[2] < fim], "nenhuma escrita durante a malha (regra 3)"
    g = max(p["geometria"], key=lambda x: x["t_fim_ms"] - x["t_ini_ms"])
    assert g["t_fim_ms"] - g["t_ini_ms"] >= 50, f"a malha da parede pesada levou {g['t_fim_ms'] - g['t_ini_ms']:.0f} ms: o caso não mede nada (voltar ao líder)"
    assert [t for t in p["pulsos"] if _dentro(t, g["t_ini_ms"], g["t_fim_ms"])], "a janela não tratou nenhum pulso durante a malha da parede pesada"
    dentro = [x for x in r["tent"] if _dentro(x[0], g["t_ini_ms"], g["t_fim_ms"])]
    assert len(dentro) >= 3 and all(x[1] == "ocupado" and x[2] == r["nome0"] and x[3] < 50 for x in r["tent"]), f"reentrada e painel durante a espera: {r['tent'][:4]}"
    assert r["paredes"] == 0 and not r["qt"], f"nenhuma parede entrou no meio; nada de Qt fora da janela: {r['paredes']}, {r['qt'][:3]}"


@AINDA_NAO
def test_v1_real_lote_na_mista_igual_ao_da_forma_2(real):
    r = _ok(real)
    x = r["lote"]
    assert x["criados"] == 30 and x["tri_mista"] == x["tri_forma2"] > 0 and x["geo"] == [30], f"a mista põe na cena o mesmo que a forma 2, com a malha do lote num pedido só: {x}"
    assert r["desfeito"] == 0, "o desfazer depois da mista volta o modelo"


if __name__ == "__main__":
    import faulthandler
    faulthandler.enable()
    faulthandler.dump_traceback_later(int(os.environ.get("OBIM_LIMITE", 300)) - 10, exit=True)
    if sys.argv[1] != "ensaio":
        import ifcopenshell  # noqa: F401  (antes do obimcore)
    try:
        saida = globals()["c_" + sys.argv[1]]({}, *sys.argv[2:])
    except BaseException:
        saida = {"erro": traceback.format_exc()}
    print("RESULTADO " + json.dumps(saida, ensure_ascii=False, default=str), flush=True)
    os._exit(0)
