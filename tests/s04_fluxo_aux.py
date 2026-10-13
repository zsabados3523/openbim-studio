# SPDX-License-Identifier: AGPL-3.0-or-later
"""Apoio do oráculo do fluxo A (S04-T11, tests/test_s04_fluxo_a.py): referência independente (só ifcopenshell), espião da Cena e os casos
gráficos c_<nome>, que rodam num processo próprio (`python s04_fluxo_aux.py <nome> [args]`, sob xvfb-run, nunca na tela real)."""
import json
import locale
import os
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

import numpy as np

AQUI = Path(__file__).resolve()
RAIZ = AQUI.parent.parent
PASTA = RAIZ / "prototypes" / "s04" / "fluxo_a"
ROTEIRO = PASTA / "roteiro_r.json"
sys.path[:0] = [str(PASTA), str(RAIZ / "app"), str(RAIZ / "prototypes"), str(RAIZ / "scripts"), str(AQUI.parent)]  # só a pasta do fluxo (não prototypes/s04: `fluxo_a/` viraria pacote)
FIRE = "Pset_WallCommon.FireRating"
TIPO = {"cmd": "criar_tipo", "nome": "PAR15", "camadas_m": [0.02, 0.11, 0.02]}
PAREDE = {"cmd": "criar_parede", "tipo": "PAR15", "comprimento": 4.0, "altura": 2.8, "espessura": 0.15}

# ---------- referência independente: só ifcopenshell ----------
def ids_modelo(f):  # GlobalId de todo objeto e tipo (as relações ficam de fora)
    return {e.GlobalId for t in ("IfcObject", "IfcTypeObject") for e in f.by_type(t)}

def forma(w):  # (triângulos, dimensões, canto mínimo) no mundo
    import ifcopenshell.geom as G
    s = G.settings()
    s.set("use-world-coords", True)
    g = G.create_shape(s, w).geometry
    v = np.array(g.verts).reshape(-1, 3)
    return len(g.faces) // 3, np.round(v.max(0) - v.min(0), 6).tolist(), np.round(v.min(0), 6).tolist()

def fire(w):
    import ifcopenshell.util.element as E
    return E.get_pset(w, *FIRE.split("."))

def estado(f):  # assinatura do modelo: contagem por classe e, por parede, nome, resistência ao fogo e forma
    return Counter(e.is_a() for e in f), {w.GlobalId: (w.Name, fire(w), forma(w) if w.Representation else None) for w in f.by_type("IfcWall")}

# ---------- conta das metas a partir dos tempos brutos ----------
ESTRITO = os.environ.get("OBIM_S04_ESTRITO") == "1"
LIM, TETO, M4_MS = {"M2": 200.0, "M2b": 200.0, "M3": 50.0}, 3.0, 20000.0
def serie(med, passo, fim="t_quadro_ms"):
    return [r[fim] - r["t0_ms"] for p in med["passos"] if p["id"] == passo for r in p["reps"]]

def resumo(v):
    return dict(mediana_ms=float(np.median(v)), p95_ms=float(np.percentile(v, 95)), max_ms=float(max(v)), n=len(v))

def m5(med):
    rep = lambda i: next(p for p in med["passos"] if p["id"] == i)["reps"][0]  # noqa: E731
    lote, parado = rep("5b"), rep("4c")
    t = np.array([x[0] for x in lote["relogio"]], float)
    ini, fim = lote["t0_ms"], lote["t_quadro_ms"]
    jan = [int(((t >= ini + 1000 * k) & (t < ini + 1000 * (k + 1))).sum()) for k in range(int((fim - ini) // 1000))]
    tp = np.array([x[0] for x in parado["relogio"]], float)
    return dict(janelas=jan, quadros=len(t), duracao_ms=fim - ini, maior_intervalo_ms=float(np.diff(np.r_[ini, t, fim]).max()),
                maior_intervalo_parado_ms=float(np.diff(tp).max()) if len(tp) > 1 else 0.0)

def calcular(med):
    out = {"M2": resumo(serie(med, "3")), "M2b": resumo(serie(med, "4b")), "M4": resumo(serie(med, "5b")), "M5": m5(med),
           "M3": resumo([r["t_painel_ms"] - r["t0_ms"] for p in med["passos"] if p["id"] == "4a" for r in p["reps"]])}
    return out

def veredito(m):  # lista de erros da régua do CI virtual (ou do p95, em ESTRITO)
    e = []
    for k, lim in LIM.items():
        r = m[k]
        e += [f"{k}: p95 {r['p95_ms']:.0f} ms >= {lim}"] * (ESTRITO and r["p95_ms"] >= lim)
        e += [f"{k}: mediana {r['mediana_ms']:.0f} ms >= {lim}"] * (not ESTRITO and r["mediana_ms"] >= lim)
        e += [f"{k}: máximo {r['max_ms']:.0f} ms >= {TETO * lim:.0f}"] * (not ESTRITO and r["max_ms"] >= TETO * lim)
    e += [f"M4: {m['M4']['max_ms']:.0f} ms >= {M4_MS:.0f}"] * (m["M4"]["max_ms"] >= M4_MS)
    c = m["M5"]
    e += [f"M5: janela de 1 s com {n} quadros (< 20): {c['janelas']}" for n in c["janelas"] if n < 20]
    e += [f"M5: {c['quadros']} quadros em {c['duracao_ms']:.0f} ms (< 20/s)"] * (not c["janelas"] and c["quadros"] < 20 * c["duracao_ms"] / 1000)
    e += [f"M5: maior intervalo {c['maior_intervalo_ms']:.0f} ms >= {200 if ESTRITO else 100}"] * (c["maior_intervalo_ms"] >= (200 if ESTRITO else 100))
    e += [f"M5: intervalo {c['maior_intervalo_ms']:.0f} ms > 3x o parado {c['maior_intervalo_parado_ms']:.0f}"] * (c["maior_intervalo_ms"] > 3 * max(33.3, c["maior_intervalo_parado_ms"]))
    return e

def sintetico(t_ms=100.0, painel=30.0, quadros=None):
    rep = lambda **k: {"t0_ms": 0.0, "t_quadro_ms": t_ms, "t_painel_ms": painel, **k}  # noqa: E731
    fr = quadros or [[16.0 * i, i] for i in range(1, 188)]
    return {"passos": [{"id": "3", "reps": [rep()] * 5}, {"id": "4a", "reps": [rep()] * 5}, {"id": "4b", "reps": [rep()] * 5},
                       {"id": "4c", "reps": [{"t0_ms": 0.0, "t_quadro_ms": 3000.0, "relogio": fr}]},
                       {"id": "5b", "reps": [{"t0_ms": 0.0, "t_quadro_ms": 3000.0, "relogio": fr}]}]}

# ---------- no processo do caso gráfico ----------
class Espiao:  # fica no lugar de `f.cena`: anota cada chamada de atualizar/adicionar_lote e se a trava do modelo estava presa
    def __init__(s, real, f):
        s.real, s.f, s.log = real, f, []

    def __getattr__(s, nome):
        a = getattr(s.real, nome)
        if nome not in ("atualizar", "adicionar_lote"):
            return a

        def chamada(*args, **kw):
            lote = args[0] if args else kw.get("lote_novo", kw.get("lote"))
            rem = args[1] if len(args) > 1 else kw.get("guids_remover", [])
            seq = a(*args, **kw)
            gs = [] if lote is None else [g.decode() if isinstance(g, bytes) else str(g) for g in lote.objetos["guid"]]
            s.log.append({"m": nome, "guids": gs, "remover": list(rem), "seq": int(seq), "trava": s.f.trava.locked()})
            return seq
        return chamada

def esperar(cond, ms=10000):
    from PySide6.QtWidgets import QApplication
    t = time.perf_counter()
    while not cond() and (time.perf_counter() - t) * 1000 < ms:
        QApplication.processEvents()
        time.sleep(0.01)
    return cond()

def assentar(f):  # espera o quadro com a última sequência, a placa igual à cena e mais 3 quadros
    c, seq = f.cena, f.sequencias[-1]
    assert esperar(lambda: any(s >= seq for _, s in c.relogio()) and c.estatisticas()["triangulos_na_placa"] == c.estatisticas()["triangulos"]), "o quadro com a mudança não chegou"
    n = len(c.relogio())
    esperar(lambda: len(c.relogio()) >= n + 3, 3000)

def c_roteiro(res, paredes):  # o roteiro R inteiro, com a cena espiada e cada comando conferido por fora
    import fluxo_a
    import gerar_modelo_grande
    import ifcopenshell
    import ifcopenshell.validate as V
    tmp = Path(tempfile.mkdtemp())
    gerar_modelo_grande.gerar(str(tmp / "base.ifc"), paredes=int(paredes))
    f = fluxo_a.FluxoA(str(tmp / "base.ifc"), janela=True, saida=tmp / "saida")
    res["ponto_decimal"] = locale.localeconv()["decimal_point"]
    base = [p.GlobalId for p in f.ifc.by_type("IfcProduct") if p.Representation]
    res["base_guids"] = base
    esp = f.cena = Espiao(f.cena, f)
    orig, chamadas = f.executar, []

    def vigia(cmd, espera=None):  # a mesma entrada que o roteiro usa; confere por fora o que o fluxo diz que criou e apagou
        antes, i0 = ids_modelo(f.ifc), len(esp.log)
        r = orig(cmd, espera)
        depois = ids_modelo(f.ifc)
        chamadas.append({"cmd": cmd["cmd"], "criados": sorted(depois - antes), "apagados": sorted(antes - depois), "chamadas": esp.log[i0:], "r": r})
        return r
    f.executar = vigia
    res["med"] = med = f.executar_roteiro(ROTEIRO)
    res["chamadas"], res["sequencias"], res["arquivo_medicao"] = chamadas, list(f.sequencias), med["arquivo_medicao"]
    res["lc_numeric"] = locale.setlocale(locale.LC_NUMERIC)
    res["tri_ref"] = sum(forma(p)[0] for p in f.ifc.by_type("IfcProduct") if p.Representation)
    por = {p["id"]: p["reps"] for p in med["passos"]}
    g3, glote = [x["guids"][0] for x in por["3"]], por["5b"][0]["guids"]
    g2 = ifcopenshell.open(med["arquivo_ifc"])
    lg = V.json_logger()
    V.validate(g2, lg)
    dims = lambda gs: sorted({tuple(forma(g2.by_guid(g))[1]) for g in gs})  # noqa: E731
    res["salvo"] = dict(mesmos_guids=ids_modelo(g2) == ids_modelo(f.ifc), paredes=len(g2.by_type("IfcWall")), tipos=len(g2.by_type("IfcWallType")), erros=[s for s in lg.statements if s.get("level") == "ERROR"][:5],
                        nomes=[g2.by_guid(g).Name for g in g3], fire=sorted({fire(g2.by_guid(g)) for g in g3}), dims_200=dims(g3), dims_lote=dims(glote[::50]))
    f.fechar()
    return res

def c_cena(res):  # desfazer e refazer: IFC, triângulos da cena, imagem e seleção voltam ao que eram (câmera parada, 3 paredes)
    import fluxo_a
    from test_s04_viewport import captura
    f = fluxo_a.FluxoA(None, janela=True, saida=Path(tempfile.mkdtemp()))
    est = lambda: f.cena.estatisticas()["triangulos"]  # noqa: E731
    centro = lambda: (f.executar({"cmd": "selecionar", "x": "centro", "y": "centro"}) or [None])[0]  # noqa: E731
    f.executar(TIPO)
    f.executar({"cmd": "camera", "alvo": [7.0, 0.075, 1.4], "distancia": 30.0, "azimute": -90.0, "elevacao": 20.0})
    gs = [f.executar(PAREDE)[0] for _ in range(3)]
    assentar(f)
    res.update(g1=gs[1], ops={}, janela=bool(f.janela_principal and f.janela_principal.isVisible()), viva=bool(f.cena.viva()), sel={})
    res["sel"]["centro"], res["sel"]["canto"] = centro(), (f.executar({"cmd": "selecionar", "x": 3, "y": 3}) or [None])[0]
    pix = lambda a, b: int((np.abs(a.astype(int) - b.astype(int)).max(axis=2) > 24).sum())  # noqa: E731
    ops = {"criar_parede": PAREDE, "mudar_comprimento": {"cmd": "mudar_comprimento", "alvo": gs[0], "comprimento": 6.0},
           "mover": {"cmd": "mover", "alvo": gs[2], "dx": 0.0, "dy": 0.0, "dz": 3.0}, "apagar": {"cmd": "apagar", "alvo": gs[1]}}
    for nome, cmd in ops.items():
        tira = lambda: (captura(f.cena).copy(), ids_modelo(f.ifc), est())  # noqa: E731
        a, ia, ta = tira()
        r1 = f.executar(cmd)
        assentar(f)
        b, ib, tb = tira()
        if nome == "apagar":
            res["sel"]["apos_apagar"] = centro()
        assert f.executar({"cmd": "desfazer"}) == r1
        assentar(f)
        c, ic, tc = tira()
        if nome == "apagar":
            res["sel"]["apos_desfazer"] = centro()
        assert f.executar({"cmd": "refazer"}) == r1
        assentar(f)
        d, idd, td = tira()
        res["ops"][nome] = dict(tri=[ta, tb, tc, td], ids=[ia == ic, ib == idd, ia != ib], muda=pix(a, b), desfaz=pix(a, c), refaz=pix(b, d))
        f.executar({"cmd": "desfazer"})  # volta às 3 paredes para a próxima operação
        assentar(f)
    f.fechar()
    return res

def c_locale(res):
    import ifcopenshell
    from PySide6.QtWidgets import QApplication
    app = QApplication(sys.argv[:1])  # controle: criar a aplicação sozinho deixa a vírgula no processo
    res["controle_virgula"] = locale.localeconv()["decimal_point"] == ","
    import fluxo_a
    pasta = Path(tempfile.mkdtemp())
    f = fluxo_a.FluxoA(None, janela=True, saida=pasta)
    res["depois"], res["lc"] = locale.localeconv()["decimal_point"], locale.setlocale(locale.LC_NUMERIC)
    f.executar(TIPO)
    g = f.executar(PAREDE)[0]
    locale.setlocale(locale.LC_NUMERIC, "pt_BR.UTF-8")  # algo desfaz a correção antes de gravar
    f.executar({"cmd": "gravar", "arquivo": "loc.ifc"})
    res["apos_gravar"] = locale.localeconv()["decimal_point"]
    g2 = ifcopenshell.open(str(pasta / "loc.ifc"))  # (o arquivo precisa ficar vivo enquanto a entidade é usada)
    res["dims"] = forma(g2.by_guid(g))[1]
    f.fechar()
    app.quit()
    return res

if __name__ == "__main__":
    import faulthandler
    import traceback
    faulthandler.dump_traceback_later(int(os.environ.get("OBIM_LIMITE", 600)) - 20, exit=True)
    nome, *resto = sys.argv[1:]
    import ifcopenshell  # noqa: F401  (antes do obimcore)
    try:
        saida = globals()["c_" + nome]({}, *resto)
    except BaseException:
        saida = {"erro": traceback.format_exc()}
    print("RESULTADO " + json.dumps(saida, ensure_ascii=False), flush=True)
    os._exit(0)
