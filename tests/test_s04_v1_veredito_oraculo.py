# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo do F0-S04-V1, segunda parte (LOTE_OPUS_69; ADR-004 §5.1, critérios 1 a 6): o que fica intacto em `lote.py`, `main_mista` e `veredito_mista`.
A primeira parte (regras 2 a 5 da forma mista) está em `test_s04_v1_mista_oraculo.py`; mesmas regras de marcador e de guarda.
- Critério 1: formas 1 e 2, `fluxo_a.py` (régua, A29) e o resto de `lote.py` intactos (sha256 do código, linhas sem espaço à direita, `main` de
  2026-10-21); em `medir` só mudam linhas com "_forma", "geometria" ou "mista" (o despacho da forma e a chave `geometria`). Passa hoje.
- `main_mista([saida, "--parte", "lote"|"pesada", "--base", N, "--quantidade", N, "--rodadas", N, "--aberturas", N])` grava e devolve o mesmo
  dicionário: {"versao": 1, "parte", "plataforma", "rhi", "estrito", "base", "quantidade", "rodadas", "aberturas", "veredito", ...}. Parte "lote" (base do
  gerador): `formas` e `controle` com "1", "2" e "mista", rodadas na ordem do `main` (por forma: rodada, controle e depois com mouse; desfazer e
  esperar 300 ms). Parte "pesada" (`base_pesada`): `pesada` = `medir_pesada` + `formas["mista"]` (mover alternando 0,01 m); `longo` =
  {"com_parede": `lote_pesado_cmd`, "sem_parede": `lote_partido_cmd`}, alternados por rodada, na mista, com mouse.
- `veredito_mista(dados)`, função pura que lê só `resumo` de cada rodada e `pesada.malha_ms`: {critério: {"ok", "valor", "limite"}, "ok": todos}.
  Parte "lote": "4_controle_1s" (mediana do `pulso_maior_ms` da mista no controle < 1.000), "4_controle_forma2" (a mesma mediana <= a pior rodada
  da forma 2 no controle), "4_mouse_forma2" (mediana do M5b `mediana_ms` da mista <= a pior rodada da forma 2), "4_surda" (toda rodada da mista
  com `pulso_maior_ms` <= 1.000), "5_m5_1", "5_m5_2", "5_m5_mista" (controle + mouse: o texto do ADR, TODA rodada com janelas >= 20 e maior
  intervalo < 200, E a régua do T15b no limite dele, 100 ms, ou 200 com `dados["estrito"]`, que `main_mista` grava de OBIM_S04_ESTRITO=1; valor =
  mediana do maior intervalo, limite = o da régua do T15b). Parte "pesada": "3_parede" (mediana do M5b `max_ms` da mista < 0,5 x `malha_ms`), "6_longo" (mediana do M5b `max_ms` com a
  parede menos sem a parede <= 0,5 x `malha_ms`), "4_surda" (pesada e longo). Mediana = `numpy.median`."""
import hashlib
import importlib.util
import inspect
import json
import os
import statistics
import sys
import tempfile
import traceback
from pathlib import Path

import pytest
import s04_fluxo_aux as aux
from test_s04_v1_mista_oraculo import AINDA_NAO, _ok, _rodar, pular

ESTE = Path(__file__).resolve()


def c_main(res, parte):  # main_mista em tamanho mínimo: estrutura do JSON e veredito
    import lote
    saida = Path(tempfile.mkdtemp()) / f"{parte}.json"
    arg = [str(saida), "--parte", parte, "--base", "10", "--quantidade", "20", "--rodadas", "1", "--aberturas", "20"]
    res["ret"] = lote.main_mista(arg)
    res["arquivo"] = json.loads(saida.read_text(encoding="utf-8"))
    return res


# ---------- conta independente do veredito (ADR-004 §5.1, critérios 3 a 6) ----------
def _med(v):
    return float(statistics.median(v))


def _m5(rs, estrito):  # o ADR (toda rodada: janelas >= 20 e maior < 200) E a régua do T15b no limite dele (100 ms; 200 com OBIM_S04_ESTRITO=1)
    mx, lim = [r["M5"]["maior_intervalo_ms"] for r in rs], 200.0 if estrito else 100.0
    par, med = _med([r["M5"]["maior_intervalo_parado_ms"] for r in rs]), _med(mx)
    ok = all(r["M5"]["janelas"] and min(r["M5"]["janelas"]) >= 20 for r in rs) and max(mx) < 200 and med < lim and med <= 3 * max(33.3, par)
    return {"ok": bool(ok), "valor": med, "limite": lim}


def _veredito(d):
    s = lambda rs: [r["resumo"] for r in rs]  # noqa: E731
    c = lambda ok, v, lim: {"ok": bool(ok), "valor": float(v), "limite": float(lim)}  # noqa: E731
    if d["parte"] == "lote":
        ctl, frm = d["controle"], d["formas"]
        vc = _med([x["pulso_maior_ms"] for x in s(ctl["mista"])])
        w2 = max(x["pulso_maior_ms"] for x in s(ctl["2"]))
        vm, wm = _med([x["M5b"]["mediana_ms"] for x in s(frm["mista"])]), max(x["M5b"]["mediana_ms"] for x in s(frm["2"]))
        surda = max(x["pulso_maior_ms"] for x in s(ctl["mista"]) + s(frm["mista"]))
        v = {"4_controle_1s": c(vc < 1000, vc, 1000), "4_controle_forma2": c(vc <= w2, vc, w2), "4_mouse_forma2": c(vm <= wm, vm, wm), "4_surda": c(surda <= 1000, surda, 1000)}
        v |= {f"5_m5_{k}": _m5(s(ctl[k]) + s(frm[k]), d["estrito"]) for k in ("1", "2", "mista")}
    else:
        p, lg, lim = d["pesada"], d["longo"], 0.5 * d["pesada"]["malha_ms"]
        vp = _med([x["M5b"]["max_ms"] for x in s(p["formas"]["mista"])])
        dl = _med([x["M5b"]["max_ms"] for x in s(lg["com_parede"])]) - _med([x["M5b"]["max_ms"] for x in s(lg["sem_parede"])])
        surda = max(x["pulso_maior_ms"] for x in s(p["formas"]["mista"]) + s(lg["com_parede"]) + s(lg["sem_parede"]))
        v = {"3_parede": c(vp < lim, vp, lim), "6_longo": c(dl <= lim, dl, lim), "4_surda": c(surda <= 1000, surda, 1000)}
    v["ok"] = all(x["ok"] for x in v.values())
    return v


def _rod(pulso, mouse_med=10.0, mouse_max=20.0, maior=30.0, janelas=(40, 41), parado=17.0):
    return {"resumo": {"M5": {"janelas": list(janelas), "maior_intervalo_ms": maior, "maior_intervalo_parado_ms": parado},
                       "M5b": {"n": 5, "mediana_ms": mouse_med, "p95_ms": mouse_max, "max_ms": mouse_max}, "pulso_maior_ms": pulso}}


def _sinteticos():  # casos que passam e que reprovam por pouco (as pontas que mandam: <, <=, mediana, pior rodada)
    def lote_(c2, cm, fm, f2, m5m, estrito=False, par=17.0, jan=(40, 41)):  # m5m: um número para as 6 rodadas da mista, ou a lista (3 do controle, 3 com mouse)
        g, mx = (lambda vs, **k: [_rod(v, **k) for v in vs]), (m5m if isinstance(m5m, list) else [m5m] * 6)  # noqa: E731
        return {"parte": "lote", "estrito": estrito, "controle": {"1": g([400, 500, 600]), "2": g(c2), "mista": [_rod(v, maior=m, parado=par, janelas=jan) for v, m in zip(cm, mx)]},
                "formas": {"1": g([400, 500, 600], mouse_med=700), "2": [_rod(300, mouse_med=x) for x in f2],
                           "mista": [_rod(300, mouse_med=x, maior=m, parado=par, janelas=jan) for x, m in zip(fm, mx[3:])]}}

    def pes(mista, com, sem, malha=200.0):
        g = lambda vs: [_rod(50.0, mouse_max=v) for v in vs]  # noqa: E731
        return {"parte": "pesada", "pesada": {"malha_ms": malha, "formas": {"1": g([5, 5, 5]), "2": g([199, 199, 199]), "mista": g(mista)}},
                "longo": {"com_parede": g(com), "sem_parede": g(sem)}}
    return [lote_([640, 700, 717], [600, 717, 999], [13, 14, 30], [13, 14, 14], 30.0),  # passa: mediana 717 <= pior 717; mouse 14 <= 14
            lote_([640, 700, 717], [600, 718, 999], [13, 14, 30], [13, 14, 14], 30.0),  # reprova 4_controle_forma2 (718 > 717)
            lote_([640, 700, 717], [600, 700, 1001], [13, 14, 30], [13, 14, 14], 30.0),  # reprova só 4_surda (1001)
            lote_([640, 700, 717], [600, 700, 717], [13, 15, 30], [13, 14, 14], 210.0),  # reprova 4_mouse_forma2 e 5_m5_mista
            lote_([640, 700, 717], [600, 700, 717], [13, 14, 30], [13, 14, 14], 150.0, True, 60.0),  # passa: estrito (200), 150 < 3 x 60
            lote_([640, 700, 717], [600, 700, 717], [13, 14, 30], [13, 14, 14], 150.0, False, 60.0),  # reprova só 5_m5_mista: 150 >= 100 fora do estrito
            pes([2, 99.9, 300], [10, 110, 120], [5, 10, 20]),  # passa: 99,9 < 100; 110 - 10 = 100 <= 100
            pes([2, 100.0, 300], [10, 111, 120], [5, 10, 20]),  # reprova 3_parede (100 não é < 100) e 6_longo (101)
            # lote 70 §2.2: cada regra sozinha, na fronteira (cada um destes vira com um mutante da conta)
            lote_([640, 700, 717], [600, 700, 717], [13, 14, 30], [13, 14, 14], [30, 30, 210, 30, 30, 30]),  # reprova só 5_m5_mista: UMA rodada a 210 (o ADR: toda rodada < 200)
            lote_([640, 700, 717], [600, 700, 717], [13, 14, 30], [13, 14, 14], 30.0, jan=(19, 41)),  # reprova só 5_m5_mista: janela com 19 quadros
            lote_([640, 700, 717], [600, 700, 717], [13, 14, 30], [13, 14, 14], 150.0, True, 17.0),  # reprova só 5_m5_mista: estrito, mas 150 > 3 x 33,3
            lote_([640, 700, 717], [600, 700, 717], [13, 14, 30], [13, 14, 14], [30, 30, 30, 30, 200, 30]),  # reprova só 5_m5_mista: maior = 200 não é < 200
            lote_([640, 700, 717], [600, 700, 717], [13, 14, 30], [13, 14, 14], 100.0, False, 60.0),  # reprova só 5_m5_mista: mediana 100 não é < 100
            lote_([640, 700, 1000], [600, 1000, 1000], [13, 14, 30], [13, 14, 14], 30.0),  # reprova só 4_controle_1s: 1.000 não é < 1.000 (<= pior da forma 2)
            lote_([640, 700, 717], [600, 700, 1000], [13, 14, 30], [13, 14, 14], 30.0)]  # passa: 4_surda com pulso de 1.000 (<= 1.000)
FALHAS = [[], ["4_controle_forma2"], ["4_surda"], ["4_mouse_forma2", "5_m5_mista"], [], ["5_m5_mista"], [], ["3_parede", "6_longo"],
          ["5_m5_mista"], ["5_m5_mista"], ["5_m5_mista"], ["5_m5_mista"], ["5_m5_mista"], ["4_controle_1s"], []]  # o que cada caso sintético reprova


# ---------- testes ----------
INTACTAS = {"lote_cmd": "d5bb3138e24a7d04", "_caminhos": "64f71a63eeeb8595", "preparar": "539e2f9d37df2760", "_Fatiador": "0ddc417fe50fb112",
            "_CenaFatiada": "b4174a96f4de1130", "_forma_1": "f755f6e78f911dc8", "_forma_2": "6b98d53c60b27427", "_maior": "e0460bb707cd66ad",
            "resumo": "01448951e43bafbe", "main": "767c40caa9d53267", "base_pesada": "e3702a51a13ee328", "medir_pesada": "a18a297a6907c696",
            "main_pesada": "b5a243299bd527d7", "medir*": "b4455d847876c220", "__main__": "13e66f06a3d11547", "fluxo_a.py": "4b185cd5d8ff5f99"}  # main de 2026-10-21 (0de3e74)


def _h(t):
    return hashlib.sha256("\n".join(x.rstrip() for x in t.splitlines()).encode()).hexdigest()[:16]


def test_v1_criterio_1_formas_1_e_2_fluxo_a_e_resto_do_lote_intactos():  # passa hoje e tem de continuar passando
    if not (aux.PASTA / "lote.py").is_file():
        pular("prototypes/s04/fluxo_a/lote.py ausente")
    import lote
    h = {k: _h(inspect.getsource(getattr(lote, k))) for k in INTACTAS if k.isidentifier() and not k.startswith("__")}
    h["medir*"] = _h("\n".join(x for x in inspect.getsource(lote.medir).splitlines() if not any(s in x.lower() for s in ("_forma", "geometria", "mista"))))
    h["__main__"] = _h((aux.PASTA / "lote.py").read_text(encoding="utf-8").split('if __name__ == "__main__":')[-1])
    h["fluxo_a.py"] = _h((aux.PASTA / "fluxo_a.py").read_text(encoding="utf-8"))
    assert h == INTACTAS, f"mudou o que não pode mudar: {sorted(k for k in h if h[k] != INTACTAS[k])}"


def test_v1_veredito_mista_igual_a_conta_independente():
    import lote
    vs = [lote.veredito_mista(json.loads(json.dumps(d))) for d in _sinteticos()]
    for i, (d, v) in enumerate(zip(_sinteticos(), vs)):
        esp = _veredito(d)
        assert set(v) == set(esp), f"caso {i}: chaves {sorted(v)} != {sorted(esp)}"
        for k in esp:
            assert v[k] == esp[k] if k == "ok" else (v[k]["ok"] == esp[k]["ok"] and abs(v[k]["valor"] - esp[k]["valor"]) <= 1e-9 and abs(v[k]["limite"] - esp[k]["limite"]) <= 1e-9), f"caso {i}, {k}: {v[k]} != {esp[k]}"
    assert [v["ok"] for v in vs] == [True, False, False, False, True, False, True, False] + [False] * 6 + [True], "sentinela: os casos sintéticos passam e reprovam onde devem"
    falhas = [sorted(k for k, x in v.items() if k != "ok" and not x["ok"]) for v in vs]
    assert falhas == FALHAS, f"cada caso reprova só o que deve: {[(i, a, b) for i, (a, b) in enumerate(zip(falhas, FALHAS)) if a != b]}"


@pytest.mark.parametrize("parte", ["lote", "pesada"])
def test_v1_main_mista_grava_e_o_veredito_bate(parte):
    if importlib.util.find_spec("obimcore") is None:
        pular("módulo obimcore ausente")
    r = _ok(_rodar("main", parte, limite=600, alvo=ESTE))
    a = r["arquivo"]
    assert r["ret"] == a and a["versao"] == 1 and a["parte"] == parte and a["rodadas"] == 1 and a["base"] == 10 and a["estrito"] is (os.environ.get("OBIM_S04_ESTRITO") == "1"), sorted(a)
    if parte == "lote":
        assert set(a["formas"]) == set(a["controle"]) == {"1", "2", "mista"} and all(len(v) == 1 for v in a["formas"].values())
        assert all(rr["mouse"] == [] for v in a["controle"].values() for rr in v) and all("geometria" in rr for rr in a["formas"]["mista"] + a["controle"]["mista"])
    else:
        assert set(a["pesada"]["formas"]) == {"1", "2", "mista"} and a["pesada"]["malha_ms"] > 0 and set(a["longo"]) == {"com_parede", "sem_parede"}
        assert all(rr["criados"] == 20 for rr in a["longo"]["com_parede"] + a["longo"]["sem_parede"]), "o lote longo cria as paredes pedidas (10 + 10)"
    esp = _veredito(a)
    assert {k: (v if k == "ok" else v["ok"]) for k, v in a["veredito"].items()} == {k: (v if k == "ok" else v["ok"]) for k, v in esp.items()}, a["veredito"]


if __name__ == "__main__":
    import faulthandler
    faulthandler.enable()
    faulthandler.dump_traceback_later(int(os.environ.get("OBIM_LIMITE", 600)) - 10, exit=True)
    import ifcopenshell  # noqa: F401  (antes do obimcore)
    try:
        saida = globals()["c_" + sys.argv[1]]({}, *sys.argv[2:])
    except BaseException:
        saida = {"erro": traceback.format_exc()}
    print("RESULTADO " + json.dumps(saida, ensure_ascii=False, default=str), flush=True)
    os._exit(0)
