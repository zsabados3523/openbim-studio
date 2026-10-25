# SPDX-License-Identifier: AGPL-3.0-or-later
"""Apoio do teste do fluxo A (tests/test_s04_fluxo_a.py): referência independente (só ifcopenshell), espião da Cena e os casos
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
PASTA = RAIZ / "tools" / "s04" / "fluxo_a"
ROTEIRO = PASTA / "roteiro_r.json"
sys.path[:0] = [str(PASTA), str(RAIZ / "app"), str(RAIZ / "viewport"), str(RAIZ / "scripts"), str(AQUI.parent)]  # só a pasta do fluxo (não tools/s04: `fluxo_a/` viraria pacote)
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

def erros_ifc(g):  # erros do validador (esquema + regras EXPRESS). O nível vem em minúsculas ("error"): o filtro antigo (== "ERROR", sem express_rules) nunca via nada
    import ifcopenshell.validate as V
    lg = V.json_logger()
    V.validate(g, lg, express_rules=True)
    return [s for s in lg.statements if str(s.get("level", "")).lower() == "error"]

def materiais(f):  # usos de camadas e relações de material, vistos de fora pelo ifcopenshell
    return {c: len(f.by_type(c, include_subtypes=False)) for c in ("IfcMaterialLayerSetUsage", "IfcRelAssociatesMaterial", "IfcMaterialLayerSet", "IfcMaterialLayer", "IfcMaterial")}

def confere_uma_camada_por_parede(f, n, tipos=1):  # n paredes -> n usos e n relações de material (+1 relação por tipo); cada uso/relação é só da sua parede
    import ifcopenshell.util.element as E
    ws = f.by_type("IfcWall")
    assert len(ws) == n, f"{len(ws)} paredes, esperado {n}"
    m = materiais(f)
    assert m["IfcMaterialLayerSetUsage"] == n, f"{m['IfcMaterialLayerSetUsage']} IfcMaterialLayerSetUsage para {n} paredes (cada parede precisa do seu): {m}"
    assert m["IfcRelAssociatesMaterial"] == n + tipos, f"{m['IfcRelAssociatesMaterial']} IfcRelAssociatesMaterial para {n} paredes e {tipos} tipo(s), esperado {n + tipos}: {m}"
    assert m["IfcMaterialLayerSet"] == tipos, "o conjunto de camadas continua sendo o do tipo (1 por tipo)"
    usos = [E.get_material(w, should_inherit=False) for w in ws]
    assert all(u is not None and u.is_a("IfcMaterialLayerSetUsage") for u in usos) and len({u.id() for u in usos}) == n, "dois usos iguais numa mesma entidade (compartilhado)"
    for w, u in zip(ws, usos):
        rels = [r for r in f.by_type("IfcRelAssociatesMaterial") if w in r.RelatedObjects]
        assert len(rels) == 1 and list(rels[0].RelatedObjects) == [w] and rels[0].RelatingMaterial == u, "a relação de material de cada parede tem só ela e o seu uso"
        assert u.ForLayerSet == E.get_type(w).HasAssociations[0].RelatingMaterial, "o uso aponta para o conjunto de camadas do tipo"

def estado(f):  # assinatura do modelo: contagem por classe e, por parede, nome, resistência ao fogo e forma
    return Counter(e.is_a() for e in f), {w.GlobalId: (w.Name, fire(w), forma(w) if w.Representation else None) for w in f.by_type("IfcWall")}

# ---------- conta das metas a partir dos tempos brutos ----------
ESTRITO = os.environ.get("OBIM_S04_ESTRITO") == "1"
LIM, TETO, TETO_MIN_MS, M4_MS = {"M2": 200.0, "M2b": 200.0, "M3": 50.0}, 3.0, 250.0, 20000.0
def teto_ms(lim):  # teto rígido de um valor só (RG-09): TETO x limite, nunca abaixo de 250 ms (uma pausa do coletor de lixo ou do runner não reprova; mesma regra de medir_s04.py)
    return max(TETO * lim, TETO_MIN_MS)
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
        e += [f"{k}: máximo {r['max_ms']:.0f} ms >= {teto_ms(lim):.0f}"] * (not ESTRITO and r["max_ms"] >= teto_ms(lim))
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
class Espiao:  # fica no lugar de `f.cena`: anota cada chamada de atualizar/adicionar_lote (e se a trava do modelo estava presa) e cada quadro que `relogio()` já mostrou
    def __init__(s, real, f):
        s.real, s.f, s.log, s.falhar, s.vistos, s.marca = real, f, [], None, {}, -1.0  # falhar: exceção que o PRÓXIMO atualizar levanta (antes de tocar na cena)

    def __getattr__(s, nome):
        a = getattr(s.real, nome)
        if nome == "relogio":
            def relogio():
                r = a()
                for t, q in reversed(r):  # só o que é novo desde a última chamada (custo pequeno, não perturba as medidas)
                    if t <= s.marca:
                        break
                    s.vistos[float(t)] = int(q)
                s.marca = max(s.marca, float(r[-1][0])) if r else s.marca
                return r
            return relogio
        if nome not in ("atualizar", "adicionar_lote"):
            return a

        def chamada(*args, **kw):
            if nome == "atualizar" and s.falhar is not None:
                e, s.falhar = s.falhar, None
                raise e
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

def c_roteiro(res, paredes):  # o roteiro R inteiro, com a cena espiada e cada comando conferido por fora (modelo, relógio do núcleo, rótulo do painel, câmera)
    import fluxo_a
    import gerar_modelo_grande
    import ifcopenshell
    import obimcore
    from PySide6.QtCore import QEvent, QObject
    from PySide6.QtWidgets import QLabel
    tmp = Path(tempfile.mkdtemp())
    gerar_modelo_grande.gerar(str(tmp / "base.ifc"), paredes=int(paredes))
    f = fluxo_a.FluxoA(str(tmp / "base.ifc"), janela=True, saida=tmp / "saida")
    res["ponto_decimal"] = locale.localeconv()["decimal_point"]
    base = [p.GlobalId for p in f.ifc.by_type("IfcProduct") if p.Representation]
    res["base_guids"] = base
    esp = f.cena = Espiao(f.cena, f)
    rotulo = f.janela_principal.findChild(QLabel)  # o painel de propriedades (M3): QLabel dentro da janela principal
    res["rotulo_achado"] = rotulo is not None

    class Pintura(QObject):  # anota cada evento de pintura do rótulo, com o texto que ele mostrava na hora e o relógio do núcleo
        def __init__(s):
            super().__init__(rotulo)
            s.eventos = []

        def eventFilter(s, obj, ev):
            if ev.type() == QEvent.Type.Paint:
                s.eventos.append((obimcore.agora(), rotulo.text()))
            return False
    pint = Pintura()
    rotulo.installEventFilter(pint)
    chamadas, prof = [], [0]

    def embrulhar(nome):  # a mesma entrada que o roteiro usa (executar ou executar_detalhado); só a chamada de fora é anotada
        orig = getattr(f, nome)

        def vigia(cmd, espera=None):
            if prof[0]:
                return orig(cmd, espera)
            antes, i0, p0, az = ids_modelo(f.ifc), len(esp.log), len(pint.eventos), esp.camera()["azimute"]
            prof[0] += 1
            try:
                ini = obimcore.agora()  # relógio do núcleo, tomado por fora: t0 do fluxo tem de cair entre `ini` e `fim`
                r = orig(cmd, espera)
                fim = obimcore.agora()
            finally:
                prof[0] -= 1
            guids, det = r if isinstance(r, tuple) else (r, dict(f.ultimo))
            depois = ids_modelo(f.ifc)
            chamadas.append({"cmd": cmd["cmd"], "args": {k: v for k, v in cmd.items() if isinstance(v, (str, int, float, list))}, "criados": sorted(depois - antes), "apagados": sorted(antes - depois),
                             "chamadas": esp.log[i0:], "r": guids, "ini": ini, "fim": fim, "azimute": az, "pinturas": pint.eventos[p0:], "rotulo": rotulo.text(), "t_painel": det.get("t_painel_ms")})
            return r
        return vigia
    f.executar = embrulhar("executar")
    hasattr(f, "executar_detalhado") and setattr(f, "executar_detalhado", embrulhar("executar_detalhado"))
    res["med"] = med = f.executar_roteiro(ROTEIRO)
    esp.relogio()
    res["chamadas"], res["sequencias"], res["arquivo_medicao"] = chamadas, list(f.sequencias), med["arquivo_medicao"]
    res["quadros_vistos"] = sorted(esp.vistos.items())  # [[t_ms, sequencia]]: todo quadro que o fluxo ou o teste viu em `Cena.relogio()`
    res["lc_numeric"] = locale.setlocale(locale.LC_NUMERIC)
    res["tri_ref"] = sum(forma(p)[0] for p in f.ifc.by_type("IfcProduct") if p.Representation)
    por = {p["id"]: p["reps"] for p in med["passos"]}
    g3, glote = [x["guids"][0] for x in por["3"]], por["5b"][0]["guids"]
    g2 = ifcopenshell.open(med["arquivo_ifc"])
    dims = lambda gs: sorted({tuple(forma(g2.by_guid(g))[1]) for g in gs})  # noqa: E731
    res["salvo"] = dict(mesmos_guids=ids_modelo(g2) == ids_modelo(f.ifc), paredes=len(g2.by_type("IfcWall")), tipos=len(g2.by_type("IfcWallType")), erros=[str(s.get("message", s))[:300] for s in erros_ifc(g2)][:5],
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

def secao(res, nome, fn):  # cada seção do c_fino é independente: o erro de uma não esconde as outras
    import traceback
    try:
        res[nome] = fn()
    except BaseException:
        res[nome] = {"erro": traceback.format_exc()}

class Falha:  # injeta uma falha DEPOIS de a transação ter fechado: no próximo `Cena.atualizar` ("atualizar") ou na montagem da malha, `obimcore.malhas` ("malhas")
    def __init__(s, esp, onde):
        s.esp, s.onde = esp, onde

    def __enter__(s):
        import obimcore
        s.real = obimcore.malhas
        if s.onde == "atualizar":
            s.esp.falhar = RuntimeError("falha injetada em Cena.atualizar")
        else:
            def malhas(*a, **k):
                raise RuntimeError("falha injetada em obimcore.malhas")
            obimcore.malhas = malhas

    def __exit__(s, *e):
        import obimcore
        s.esp.falhar, obimcore.malhas = None, s.real

def _tabela(f, esp):  # id STEP não vai à tabela do núcleo (a coluna `id_step` de `objetos(seq)` é 0 para todo objeto de todo lote)
    g = f.executar(PAREDE)[0]  # (a abertura da base já foi feita pelo c_fino: o `esp.log` tem o `abrir`)
    f.executar(dict(PAREDE, cmd="criar_paredes_lote", quantidade=3))
    f.executar({"cmd": "mudar_comprimento", "alvo": g, "comprimento": 6.0})
    f.executar({"cmd": "mover", "alvo": g, "dx": 0.0, "dy": 0.0, "dz": 1.0})
    f.executar({"cmd": "desfazer"})
    assentar(f)
    saida = []
    for k in esp.log:
        if k["guids"]:
            try:
                t = f.cena.objetos(k["seq"])
            except ValueError as e:  # lote já substituído pelo núcleo: não há tabela para conferir
                saida.append({"m": k["m"], "descartado": str(e)})
                continue
            saida.append({"m": k["m"], "guids": [x.decode() if isinstance(x, bytes) else str(x) for x in t["guid"]], "esperado": k["guids"], "ids": [int(i) for i in t["id_step"]]})
    return saida

def _propriedade(f, esp):  # desfazer/refazer de edição de propriedade não manda malha nova (nem reenvia a cena); o de mudar_comprimento manda só a parede
    gs = [f.executar(PAREDE)[0] for _ in range(4)]
    assentar(f)
    est = lambda: f.cena.estatisticas()  # noqa: E731

    def passo(cmd):
        a, i0 = est(), len(esp.log)
        r = f.executar(cmd)
        assentar(f)
        b = est()
        return {"guids": r, "dfatias": b["fatias_enviadas"] - a["fatias_enviadas"], "tri": [a["triangulos"], b["triangulos"], b["triangulos_na_placa"]], "log": esp.log[i0:]}
    out = {"alvo": gs[0]}
    for nome, cmd in (("editar", {"cmd": "editar_propriedades", "alvo": gs[0], "nome": "Outro", "propriedades": {FIRE: "R90"}}), ("mudar", {"cmd": "mudar_comprimento", "alvo": gs[1], "comprimento": 6.0})):
        out[nome], out["des_" + nome], out["ref_" + nome] = passo(cmd), passo({"cmd": "desfazer"}), passo({"cmd": "refazer"})
    out["alvo_mudar"] = gs[1]
    return out

def _falhas(f, esp, cont):  # falha DEPOIS do fim da transação: o modelo volta a ser o de antes, o histórico não muda e a cena segue igual ao modelo
    n = cont  # paredes que o fluxo criou de verdade, de todas as seções (a grade não anda por comando que falhou)
    tri = lambda: f.cena.estatisticas()["triangulos"]  # noqa: E731
    geo = lambda: 12 * sum(1 for p in f.ifc.by_type("IfcProduct") if p.Representation)  # noqa: E731
    sinc = lambda: esperar(lambda: f.cena.estatisticas()["triangulos_na_placa"] == tri() == geo(), 5000)  # noqa: E731
    casos = {"criar_parede": lambda a: PAREDE, "criar_paredes_lote": lambda a: dict(PAREDE, cmd="criar_paredes_lote", quantidade=3), "mudar_comprimento": lambda a: {"cmd": "mudar_comprimento", "alvo": a, "comprimento": 6.0},
             "mover": lambda a: {"cmd": "mover", "alvo": a, "dx": 0.0, "dy": 0.0, "dz": 1.0}, "apagar": lambda a: {"cmd": "apagar", "alvo": a},
             "editar_propriedades": lambda a: {"cmd": "editar_propriedades", "alvo": a, "nome": "Falha", "propriedades": {FIRE: "R120"}}}
    saida = {}
    for onde in ("atualizar", "malhas"):
        for nome, mk in casos.items():
            if onde == "malhas" and nome in ("apagar", "editar_propriedades"):
                continue  # esses não montam malha nova
            e_ant = estado(f.ifc)
            alvo = f.executar(PAREDE)[0]  # o comando anterior: o `desfazer` depois da falha tem de desfazer ESTE, não a transação que falhou
            assentar(f)
            e0, ids0, h0, seq0, cmd = estado(f.ifc), ids_modelo(f.ifc), len(f.historico), list(f.sequencias), mk(alvo)
            v = {}
            try:
                with Falha(esp, onde):
                    f.executar(cmd)
                v["levantou"] = False
            except RuntimeError as e:
                v["levantou"] = "falha injetada" in str(e)
            v.update(modelo_igual=estado(f.ifc) == e0 and ids_modelo(f.ifc) == ids0, historico_igual=len(f.historico) == h0, sequencias_iguais=f.sequencias == seq0, trava_livre=not f.trava.locked(), cena_igual_ao_modelo=sinc())
            try:
                r = f.executar(cmd)  # sem falha: o comando funciona e acha a grade e a pilha intactas
            except Exception:  # (o comando não pode mais rodar: a falha deixou o modelo diferente do de antes)
                saida[f"{nome}/{onde}"] = dict(v, recupera=False)
                continue
            assentar(f)
            if nome in ("criar_parede", "criar_paredes_lote"):
                k = n["criadas"] - len(r)  # índice da grade da primeira parede deste comando
                v["grade_ok"] = forma(f.ifc.by_guid(r[0]))[2] == [k % 50 * 5.0, k // 50 * 4.0, 0.0]
            v.update(cena_depois_ok=sinc(), desfaz_o_comando=f.executar({"cmd": "desfazer"}) == r and estado(f.ifc) == e0)
            assentar(f)
            v.update(desfaz_o_anterior=f.executar({"cmd": "desfazer"}) == [alvo] and estado(f.ifc) == e_ant)
            assentar(f)
            saida[f"{nome}/{onde}"] = v
    return saida

def _falhas_desfazer(f, esp):  # desfazer/refazer cujo `atualizar` (ou cuja malha) falha: o modelo volta ao que era, o registro volta à pilha e a cena segue igual ao modelo
    geo = lambda: 12 * sum(1 for p in f.ifc.by_type("IfcProduct") if p.Representation)  # noqa: E731
    sinc = lambda: esperar(lambda: f.cena.estatisticas()["triangulos_na_placa"] == f.cena.estatisticas()["triangulos"] == geo(), 5000)  # noqa: E731
    saida = {}
    for onde in ("atualizar", "malhas"):
        e0 = estado(f.ifc)
        g = f.executar(PAREDE)[0]
        f.executar({"cmd": "mudar_comprimento", "alvo": g, "comprimento": 6.0})  # desfazer e refazer precisam de malha nova (a parede inteira)
        assentar(f)
        v = {}
        for qual in ("desfazer", "refazer"):  # o desfazer que falha deixa o modelo com o comprimento novo; o refazer que falha, com o antigo
            e1, h1 = estado(f.ifc), len(f.historico)
            try:
                with Falha(esp, onde):
                    f.executar({"cmd": qual})
                levantou = False
            except RuntimeError as e:
                levantou = "falha injetada" in str(e)
            v[qual] = dict(levantou=levantou, modelo_igual=estado(f.ifc) == e1, historico_igual=len(f.historico) == h1, trava_livre=not f.trava.locked(), cena_igual_ao_modelo=sinc())
            v[qual]["repete_ok"] = f.executar({"cmd": qual}) == [g]  # a pilha está intacta: o mesmo comando agora funciona
            assentar(f)
        f.executar({"cmd": "desfazer"})  # volta ao modelo anterior à parede, para a próxima rodada
        f.executar({"cmd": "desfazer"})
        assentar(f)
        v["voltou"] = estado(f.ifc) == e0
        saida[onde] = v
    return saida

def c_fino(res):  # id STEP 0 na tabela do núcleo, desfazer de propriedade sem malha nova e falhas depois do fim da transação (base mm de 12 paredes, cena espiada)
    import fluxo_a
    import gerar_modelo_grande
    tmp = Path(tempfile.mkdtemp())
    gerar_modelo_grande.gerar(str(tmp / "base.ifc"), paredes=12)
    f = fluxo_a.FluxoA(str(tmp / "base.ifc"), janela=True, saida=tmp / "saida")
    esp = f.cena = Espiao(f.cena, f)
    cont, orig = {"criadas": 0}, f.executar

    def contar(cmd, espera=None):  # quantas paredes o fluxo criou (a grade não devolve as desfeitas)
        r = orig(cmd, espera)
        cont["criadas"] += 1 if cmd["cmd"] == "criar_parede" else int(cmd["quantidade"]) if cmd["cmd"] == "criar_paredes_lote" else 0
        return r
    f.executar = contar
    f.executar({"cmd": "abrir"})
    f.executar(TIPO)
    assentar(f)
    for nome, fn in (("tabela", _tabela), ("propriedade", _propriedade), ("falhas", lambda f, e: _falhas(f, e, cont)), ("falhas_desfazer", _falhas_desfazer)):
        secao(res, nome, lambda fn=fn: fn(f, esp))
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
