# SPDX-License-Identifier: AGPL-3.0-or-later
"""Apoio do teste do fluxo B, parte 2 (tests/test_s04_fluxo_b_janela.py; contrato: prototypes/s04/fluxo_b/CONTRATO.md, "Parte 2"):
como achar e rodar o executável (sob xvfb-run, nunca na tela real), validação estrutural do `medicao.json`, assinatura de IFC sem GlobalId nem posição."""
import json
import math
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
ROTEIRO = RAIZ / "prototypes" / "s04" / "fluxo_a" / "roteiro_r.json"
NOME = "fluxo_b_janela" + (".exe" if sys.platform == "win32" else "")

def achar_exe():  # None se não existe (o teste pula ou falha, conforme OBIM_S04_T14_OBRIGATORIO)
    pastas = [os.environ.get("OBIM_S04_FLUXO_B_DIR"), *os.environ.get("PYTHONPATH", "").split(os.pathsep), str(RAIZ / "out" / "s04")]
    for c in [os.environ.get("OBIM_S04_FLUXO_B_EXE"), *(Path(p) / NOME for p in pastas if p)]:
        if c and Path(c).is_file():
            return Path(c)
    return None

def rodar(exe, args, grafico=False, env=None, timeout=900):  # grafico: tela virtual (Linux: xvfb-run + Mesa por software; Windows: só no CI ou com OBIM_S04_TELA_VIRTUAL=1)
    e = {k: v for k, v in os.environ.items() if k not in ("DISPLAY", "WAYLAND_DISPLAY", "PYTHONPATH", "PYTHONHOME")}  # sem Python por perto: o executável não pode depender dele
    if grafico:
        e.update(QT_QPA_PLATFORM="windows", RHI="d3d11") if sys.platform == "win32" else e.update(QT_QPA_PLATFORM="xcb", LIBGL_ALWAYS_SOFTWARE="1")
    else:
        e["QT_QPA_PLATFORM"] = "offscreen"
    e.update(env or {})
    pre = ["xvfb-run", "-a", "-s", "-screen 0 1280x800x24"] if grafico and sys.platform != "win32" else []
    return subprocess.run([*pre, str(exe), *map(str, args)], env=e, capture_output=True, encoding="utf-8", errors="replace", timeout=timeout)  # o executável escreve UTF-8; não a codificação da localidade (cp1252 no Windows)

def resultado(p, rotulo):  # JSON da linha `RESULTADO`; queda ou DLL/plugin Qt ausente aparecem com o código de saída e a saída unida (sob xvfb-run o stderr vem junto do stdout)
    linhas = [x for x in p.stdout.splitlines() if x.startswith("RESULTADO ")]
    assert p.returncode == 0 and linhas, f"{rotulo}: o executável CAIU ou não respondeu (código {p.returncode}; no Windows 0xC0000135 = DLL ausente, 'platform plugin' = Qt sem plugin):\n{(p.stdout + p.stderr)[-2300:]}"
    return json.loads(linhas[-1][10:])

def roteiro_json():
    return json.loads(ROTEIRO.read_text(encoding="utf-8"))

COMUNS = {"r", "guids", "criados", "alterados", "apagados", "geometria", "sequencia", "t0_ms", "t_comando_ms", "t_quadro_ms", "ms_total", "triangulos_cena"}

def validar_medicao(med, rot, produtos=None):  # lista de erros estruturais do medicao.json de B (os mesmos campos do fluxo A, mais thread/pulso no passo 5b)
    e = [f"{k}: {med.get(k)!r}" for k, v in (("fluxo", "B"), ("versao", 1)) if med.get(k) != v]
    e += [f"falta a chave {k}" for k in ("plataforma", "rhi", "base", "passos", "metas", "arquivo_ifc") if k not in med]
    if e:
        return e
    e += [f"base.produtos {med['base'].get('produtos')} != {produtos}"] * (produtos is not None and med["base"].get("produtos") != produtos)
    m = med["metas"] or {}
    e += ["metas.M1 e M6 devem ser null (a comparação A x B é do medir_s04)"] * (m.get("M1") is not None or m.get("M6") is not None)
    if [p["id"] for p in med["passos"]] != [p["id"] for p in rot["passos"]]:
        return e + ["ids de passo diferentes do roteiro"]
    for p, q in zip(rot["passos"], med["passos"]):
        e += [f"{p['id']}: {len(q['reps'])} repetições (roteiro: {p.get('n', 1)})"] * (len(q["reps"]) != p.get("n", 1))
        e += [f"{p['id']}: cmd {q.get('cmd')} != {p['cmd']}"] * (q.get("cmd") != p["cmd"])
        for x in q["reps"]:
            r = f"{p['id']}#{x.get('r')}"
            falta = (COMUNS | ({"t_painel_ms"} if p["cmd"] == "editar_propriedades" else set()) | ({"relogio"} if p["id"] in ("4c", "5b") else set())) - x.keys()
            e += [f"{r}: faltam {sorted(falta)}"] * bool(falta)
            if falta:
                continue
            e += [f"{r}: t0 <= t_comando <= t_quadro violado"] * (not x["t0_ms"] <= x["t_comando_ms"] <= x["t_quadro_ms"])
            e += [f"{r}: ms_total != t_quadro - t0"] * (not math.isclose(x["ms_total"], x["t_quadro_ms"] - x["t0_ms"], abs_tol=1e-6))
            e += [f"{r}: t_painel_ms só em editar_propriedades"] * (("t_painel_ms" in x) != (p["cmd"] == "editar_propriedades"))
            e += [f"{r}: sequencia {x['sequencia']!r}"] * (x["sequencia"] is not None and not isinstance(x["sequencia"], int))
            e += [f"{r}: guid inválido {g!r}" for g in x["guids"] if not (isinstance(g, str) and len(g) == 22)]
        if p["id"] == "5b":
            x = q["reps"][0]
            t, pulso = x.get("thread") or {}, x.get("pulso_janela_ms") or []
            e += ["5b: thread.comando e thread.janela têm de existir e ser diferentes (lote em thread C++)"] * (not (t.get("comando") and t.get("janela") and t["comando"] != t["janela"]))
            e += ["5b: pulso_janela_ms vazio, fora de ordem ou fora de [t0, t_quadro]"] * (len(pulso) < 10 or pulso != sorted(pulso) or pulso[0] < x["t0_ms"] or pulso[-1] > x["t_quadro_ms"])
    return e

def maior_pulso_ms(x):  # maior intervalo entre os pulsos da thread da janela, contando as pontas do passo
    t = [x["t0_ms"], *x["pulso_janela_ms"], x["t_quadro_ms"]]
    return max(b - a for a, b in zip(t, t[1:]))

def sintetica(rot, produtos=300):  # medicao.json de B válido, montado só do roteiro (sentinela: prova que a validação aceita um B correto e acusa cada defeito)
    passos = []
    for p in rot["passos"]:
        reps = []
        for r in range(p.get("n", 1)):
            x = {"r": r, "guids": ["G" * 22], "criados": [], "alterados": [], "apagados": [], "geometria": [], "sequencia": None, "t0_ms": 10.0, "t_comando_ms": 11.0, "t_quadro_ms": 12.0, "ms_total": 2.0, "triangulos_cena": 0}
            p["cmd"] == "editar_propriedades" and x.update(t_painel_ms=11.5)
            p["id"] in ("4c", "5b") and x.update(relogio=[[11.0, 1]])
            p["id"] == "5b" and x.update(t_quadro_ms=1000.0, ms_total=990.0, thread={"comando": "1", "janela": "2"}, pulso_janela_ms=[10.0 + 10 * i for i in range(99)])
            reps.append(x)
        passos.append({"id": p["id"], "cmd": p["cmd"], "reps": reps})
    return {"fluxo": "B", "versao": 1, "plataforma": "teste", "rhi": "gl", "base": {"arquivo": "b.ifc", "produtos": produtos}, "passos": passos, "metas": {"M1": None, "M6": None}, "arquivo_ifc": "r.ifc"}

def assin(caminho):  # assinatura sem GlobalId e sem achar parede pela posição (a base e a grade do roteiro colidem em 0,0,0): classes + multiconjunto de paredes (forma por create_shape)
    import ifcopenshell
    import ifcopenshell.util.element as E
    import s04_fluxo_aux as aux
    import s04_fluxo_b_aux as bx
    f = ifcopenshell.open(str(caminho))
    fm, nome = bx.formas(f), lambda x: (x.Name if x is not None else "")  # noqa: E731
    def parede(w):
        us, tri, lo, hi, vol = E.get_material(w, should_inherit=False), *fm[w.id()]
        return [w.Name or "", nome(E.get_type(w)), nome(E.get_container(w)), aux.fire(w) or "", [c.LayerThickness for c in us.ForLayerSet.MaterialLayers] if us else [], tri, *lo, *hi, vol]
    ps = sorted((parede(w) for w in f.by_type("IfcWall")), key=lambda p: (*p[:4], tuple(round(x, 3) for x in p[6:])))
    return {"classes": dict(Counter(e.is_a() for e in f if e.is_a() not in bx.LIVRES | bx.MATERIAL)), "paredes": ps}
