# SPDX-License-Identifier: AGPL-3.0-or-later
"""Ferramenta que lê `medicao.json` do fluxo A (e do B), aplica as metas M2 a M5, compara os IFCs do passo 7, calcula M6 e conta linhas (M7).
O contrato (linha de comando, JSON e regras) está no cabeçalho de `tests/test_s04_metas.py`.
Só biblioteca padrão, numpy e ifcopenshell. Os tempos vêm dos tempos brutos (não confiar no campo `metas` gravado pelos fluxos).
Código de saída: 0 aprovado, 1 reprovado, 2 entrada inválida."""
import argparse
import ast
import json
import math
import os
import sys
import traceback
from pathlib import Path

import numpy as np

LIMITES = {"M2": 200.0, "M2b": 200.0, "M3": 50.0}  # ms; p95 na régua estrita, mediana na virtual
TETO, TETO_MIN_MS, M4_MS, M5_VIRTUAL_MS, M5_ESTRITO_MS = 3.0, 250.0, 20000.0, 100.0, 200.0


def _teto_ms(lim):  # teto rígido de um valor só; mesma conta de tests/s04_fluxo_aux.teto_ms
    return max(TETO * lim, TETO_MIN_MS)
OFICIAL = 3000  # paredes do modelo oficial (régua estrita)
TOL = 1e-6
SUFIXOS = {".py", ".cpp", ".h", ".hpp", ".cc"}
# Geometria de apoio (montagem livre no contrato): fica fora da contagem por classe.
LIVRES = {"IfcCartesianPoint", "IfcDirection", "IfcAxis2Placement2D", "IfcAxis2Placement3D", "IfcCartesianPointList2D", "IfcCartesianPointList3D", "IfcIndexedPolyCurve",
          "IfcPolyline", "IfcArbitraryClosedProfileDef", "IfcRectangleProfileDef"}
FIRE = ("Pset_WallCommon", "FireRating")
MAX_DIFERENCAS = 20


def primeiro_quadro(relogio, sequencia):
    """Tempo (ms) do primeiro quadro de `relogio` ([[t_ms, seq], ...] em ordem de tempo) com seq >= `sequencia`, ou None.
    A sequência CAI a 0 durante o reenvio da cena: não supor que seja crescente."""
    for t, seq in relogio:
        if seq >= sequencia:
            return t
    return None


# ---------- M7: linhas depois de formatar ----------
def _largura(linha):
    return max(1, math.ceil(len(linha) / 100))


def _sem_docstrings(arvore):
    for no in ast.walk(arvore):
        corpo = getattr(no, "body", None)
        if isinstance(no, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and corpo:
            p = corpo[0]
            if isinstance(p, ast.Expr) and isinstance(p.value, ast.Constant) and isinstance(p.value.value, str):
                corpo[:] = corpo[1:] or [ast.Pass()]
    return arvore


def _linhas_python(texto):
    try:
        linhas = ast.unparse(_sem_docstrings(ast.parse(texto))).splitlines()
    except (SyntaxError, ValueError):  # arquivo que não compila: conta o que sobra sem comentário de linha inteira
        linhas = [x.rstrip() for x in texto.splitlines() if x.strip() and not x.strip().startswith("#")]
    return sum(_largura(x) for x in linhas if x.strip())


def _prefixo_bruto(t, i):  # o R de R"d(...)d" pode vir depois de u8, u, U ou L (u8R"(...)"), nunca de outro identificador
    j = i
    while j > 0 and (t[j - 1].isalnum() or t[j - 1] == "_"):
        j -= 1
    return t[j:i] in ("", "u8", "u", "U", "L")


def _separador_digitos(t, i):  # o ' em 1'000 ou 0xFF'FF: dentro de um número, que começa em dígito
    j = i
    while j > 0 and (t[j - 1].isalnum() or t[j - 1] in "_'."):
        j -= 1
    return j < i and t[j].isdigit() and i + 1 < len(t) and t[i + 1].isalnum()


def _sem_comentarios_c(t):  # tira // e /* */, respeitando textos entre aspas, caracteres e textos brutos R"d( )d"
    out, i, n = [], 0, len(t)
    while i < n:
        c = t[i]
        if c == "R" and t.startswith('R"', i) and _prefixo_bruto(t, i) and "(" in t[i:i + 20]:
            ab = t.index("(", i)
            fim = t.find(")" + t[i + 2:ab] + '"', ab)
            fim = n if fim < 0 else fim + len(t[i + 2:ab]) + 2
            out.append(t[i:fim])
            i = fim
        elif c == "'" and _separador_digitos(t, i):  # 1'000 não abre um caractere
            out.append(c)
            i += 1
        elif c in "\"'":
            j = i + 1
            while j < n and t[j] != c and t[j] != "\n":
                j += 2 if t[j] == "\\" else 1
            out.append(t[i:j + 1])
            i = j + 1
        elif t.startswith("//", i):
            j = t.find("\n", i)
            i = n if j < 0 else j
        elif t.startswith("/*", i):
            j = t.find("*/", i + 2)
            out.append(" ")
            i = n if j < 0 else j + 2
        else:
            out.append(c)
            i += 1
    return "".join(out)


def _linhas_c(texto):
    return sum(_largura(x.rstrip()) for x in _sem_comentarios_c(texto).splitlines() if x.strip())


def _cru_python(texto):  # linhas não vazias que não são comentário de linha inteira (docstrings contam)
    return sum(1 for x in texto.splitlines() if x.strip() and not x.strip().startswith("#"))


def _cru_c(texto):  # linhas não vazias depois de tirar os comentários, sem o peso da largura
    return sum(1 for x in _sem_comentarios_c(texto).splitlines() if x.strip())


def _contar(raiz, f_py, f_c):
    raiz, out = Path(raiz), {}
    for pasta in ("obimcore", "fluxo_a", "fluxo_b"):
        total, base = 0, raiz / pasta
        for f in sorted(base.rglob("*")) if base.is_dir() else []:
            partes = f.relative_to(base).parts[:-1]
            if f.suffix not in SUFIXOS or not f.is_file() or any(p in ("build", "__pycache__") or p.startswith(".") for p in partes):
                continue
            texto = f.read_text(encoding="utf-8", errors="replace")
            total += (f_py if f.suffix == ".py" else f_c)(texto)
        out[pasta] = total
    return out


def contar_linhas(raiz):
    """{"obimcore": n, "fluxo_a": n, "fluxo_b": n}: linhas de código depois de formatar."""
    return _contar(raiz, _linhas_python, _linhas_c)


def contar_linhas_cruas(raiz):
    """Mesma forma, sem normalizar: Python conta as linhas do arquivo como estão (sem vazias nem comentário de linha inteira); C/C++ sem peso de largura.
    Fica ao lado da contagem normalizada para quem lê ver o efeito do formato (o Python é normalizado a uma instrução por linha, o C++ não)."""
    return _contar(raiz, _cru_python, _cru_c)


# ---------- metas M2 a M5 (dos tempos brutos) ----------
def _carregar(pasta):
    arq = Path(pasta) / "medicao.json"
    if not arq.is_file():
        raise ValueError(f"{arq} não existe")
    try:
        m = json.loads(arq.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise ValueError(f"{arq} ilegível: {e}")
    if not isinstance(m, dict) or not isinstance(m.get("passos"), list):
        raise ValueError(f"{arq} sem lista de passos")
    return m


ROTEIRO = Path(__file__).resolve().parent / "fluxo_a" / "roteiro_r.json"
MEDIDOS = ("3", "4a", "4b", "4c", "5b")


def _num(x):
    try:
        return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)
    except OverflowError:  # inteiro gigante no JSON (10**400) não cabe em float
        return False


def _roteiro():  # {"n": {passo: repetições}, "lote": tamanho do lote do 5b}: os números do roteiro R, nunca fixos aqui
    try:
        ps = {p["id"]: p for p in json.loads(ROTEIRO.read_text(encoding="utf-8"))["passos"]}
        return {"n": {i: int(ps[i].get("n", 1)) for i in MEDIDOS}, "lote": int(ps["5b"]["quantidade"])}
    except (OSError, ValueError, KeyError, TypeError) as e:
        raise ValueError(f"não consegui ler os números do roteiro R em {ROTEIRO}: {e!r}")


def _tempos(pid, k, r, painel):  # t0 <= t_comando <= t_quadro (e t_painel >= t0 no 4a); tudo número finito
    if not isinstance(r, dict):
        raise ValueError(f"passo {pid}, repetição {k}: não é um objeto")
    for c in ("t0_ms", "t_comando_ms", "t_quadro_ms") + (("t_painel_ms",) if painel else ()):
        if not _num(r.get(c)):
            raise ValueError(f"passo {pid}, repetição {k}: `{c}` ausente ou não é número finito ({r.get(c)!r})")
    if not r["t0_ms"] <= r["t_comando_ms"] <= r["t_quadro_ms"]:
        raise ValueError(f"passo {pid}, repetição {k}: tempos fora de ordem (t0 {r['t0_ms']!r}, t_comando {r['t_comando_ms']!r}, t_quadro {r['t_quadro_ms']!r})")
    if painel and r["t_painel_ms"] < r["t0_ms"]:
        raise ValueError(f"passo {pid}, repetição {k}: t_painel_ms {r['t_painel_ms']!r} antes de t0_ms {r['t0_ms']!r}")


def _relogio(pid, r):  # [[t_ms, seq], ...] ordenado por tempo (a ferramenta nunca confia na ordem gravada); r já passou por _tempos
    rel = r.get("relogio")
    if not isinstance(rel, list):
        raise ValueError(f"passo {pid}: `relogio` ausente ou não é lista")
    for k, x in enumerate(rel):
        if not (isinstance(x, (list, tuple)) and len(x) == 2 and _num(x[0]) and _num(x[1])):
            raise ValueError(f"passo {pid}: entrada {k} do relógio inválida ({x!r})")
        if not r["t0_ms"] <= x[0] <= r["t_quadro_ms"]:  # janela inclusiva da própria repetição: rejeita, não filtra
            raise ValueError(f"passo {pid}: quadro do relógio em {x[0]!r} ms fora da janela [{r['t0_ms']!r}, {r['t_quadro_ms']!r}] da repetição")
    r = sorted(([float(x[0]), x[1]] for x in rel), key=lambda x: x[0])
    if len({x[0] for x in r}) != len(r):
        raise ValueError(f"passo {pid}: relógio com tempo repetido")
    return r


def _validar_medicao(m, rotulo):
    """Levanta ValueError (que vira código 2) para qualquer medicao.json que não permita um veredito: nada de aprovar sobre dado quebrado."""
    ro, por_id = _roteiro(), {}
    if not isinstance(m.get("base") or {}, dict):
        raise ValueError(f"{rotulo}: `base` não é um objeto")
    for k, p in enumerate(m["passos"]):
        if not isinstance(p, dict) or not isinstance(p.get("id"), str) or not p["id"]:
            raise ValueError(f"{rotulo}: passo sem `id` (posição {k})")
        if not isinstance(p.get("reps"), list):
            raise ValueError(f"{rotulo}: passo {p['id']} sem `reps` ou `reps` não é lista")
        if p["id"] in por_id:
            raise ValueError(f"{rotulo}: passo {p['id']} repetido")
        por_id[p["id"]] = p
    for pid in MEDIDOS:
        if pid not in por_id:
            raise ValueError(f"{rotulo}: passo {pid} ausente")
        reps = por_id[pid]["reps"]
        if len(reps) != ro["n"][pid]:  # o roteiro fixa N (padrão 1 onde não define; o fluxo A faz int(p.get("n", 1))): nem a menos nem a mais
            raise ValueError(f"{rotulo}: passo {pid} com {len(reps)} repetições (o roteiro pede {ro['n'][pid]})")
        for k, r in enumerate(reps):
            _tempos(pid, k, r, pid == "4a")
            if pid in ("4c", "5b"):
                _relogio(pid, r)
    for k, r in enumerate(por_id["5b"]["reps"]):
        n = len(r["criados"]) if isinstance(r.get("criados"), list) else None
        if n != ro["lote"]:
            raise ValueError(f"{rotulo}: passo 5b, repetição {k}: `criados` {'ausente' if n is None else f'com {n} paredes'} (o roteiro pede {ro['lote']})")
        if len(set(r["criados"])) != n:
            raise ValueError(f"{rotulo}: passo 5b, repetição {k}: `criados` com GlobalId repetido")
        if not (isinstance(r.get("sequencia"), int) and not isinstance(r.get("sequencia"), bool) and r["sequencia"] >= 1):
            raise ValueError(f"{rotulo}: passo 5b, repetição {k}: `sequencia` ausente ou inválida ({r.get('sequencia')!r})")
        t = primeiro_quadro(_relogio("5b", r), r["sequencia"])
        if t is None or t > r["t_quadro_ms"]:
            raise ValueError(f"{rotulo}: passo 5b, repetição {k}: o lote (sequência {r['sequencia']!r}) " + ("nunca aparece nos quadros" if t is None else f"só aparece em {t:.0f} ms, depois do t_quadro_ms {r['t_quadro_ms']:.0f}"))


def _exigir_oficial(m, rotulo):  # régua estrita só vale sobre o modelo oficial (3000 paredes)
    n = (m.get("base") or {}).get("produtos")
    if not _num(n) or n < OFICIAL:
        raise ValueError(f"{rotulo}: a régua estrita exige o modelo oficial de {OFICIAL} paredes (base.produtos = {n!r}); meça de novo com a base oficial")


def _reps(m, passo):
    for p in m["passos"]:
        if p["id"] == passo:
            return p["reps"]
    raise ValueError(f"passo {passo} ausente")


def _serie(m, passo, fim="t_quadro_ms"):
    return [r[fim] - r["t0_ms"] for r in _reps(m, passo)]


def _resumo(v):
    return {"n": len(v), "mediana_ms": float(np.median(v)), "p95_ms": float(np.percentile(v, 95)), "max_ms": float(max(v))}


def _m5(m):
    lote, parado = _reps(m, "5b")[0], _reps(m, "4c")[0]
    t = np.sort(np.array([x[0] for x in lote["relogio"]], float))
    ini, fim = lote["t0_ms"], lote["t_quadro_ms"]
    jan = [int(((t >= ini + 1000 * k) & (t < ini + 1000 * (k + 1))).sum()) for k in range(int((fim - ini) // 1000))]
    tp = np.sort(np.array([x[0] for x in parado["relogio"]], float))
    return {"janelas": jan, "quadros": len(t), "duracao_ms": float(fim - ini), "maior_intervalo_ms": float(np.diff(np.r_[ini, t, fim]).max()),
            "maior_intervalo_parado_ms": float(np.diff(tp).max()) if len(tp) > 1 else 0.0}


def _calcular(m):
    try:
        return {"M2": _resumo(_serie(m, "3")), "M2b": _resumo(_serie(m, "4b")), "M3": _resumo(_serie(m, "4a", "t_painel_ms")),
                "M4": _resumo(_serie(m, "5b")), "M5": _m5(m)}
    except (KeyError, TypeError, IndexError, ValueError) as e:
        raise ValueError(f"medicao.json com tempos inválidos: {e!r}")


def _erros(c, estrito):  # a mesma régua de s04_fluxo_aux.veredito
    e = []
    for k, lim in LIMITES.items():
        r = c[k]
        if estrito and r["p95_ms"] >= lim:
            e.append(f"{k}: p95 {r['p95_ms']:.0f} ms >= {lim:.0f}")
        if not estrito and r["mediana_ms"] >= lim:
            e.append(f"{k}: mediana {r['mediana_ms']:.0f} ms >= {lim:.0f}")
        if not estrito and r["max_ms"] >= _teto_ms(lim):
            e.append(f"{k}: máximo {r['max_ms']:.0f} ms >= {_teto_ms(lim):.0f}")
    if c["M4"]["max_ms"] >= M4_MS:
        e.append(f"M4: {c['M4']['max_ms']:.0f} ms >= {M4_MS:.0f}")
    q, lim5 = c["M5"], M5_ESTRITO_MS if estrito else M5_VIRTUAL_MS
    e += [f"M5: janela de 1 s com {n} quadros (< 20): {q['janelas']}" for n in q["janelas"] if n < 20]
    if not q["janelas"] and q["quadros"] < 20 * q["duracao_ms"] / 1000:
        e.append(f"M5: {q['quadros']} quadros em {q['duracao_ms']:.0f} ms (< 20/s)")
    if q["maior_intervalo_ms"] >= lim5:
        e.append(f"M5: maior intervalo {q['maior_intervalo_ms']:.0f} ms >= {lim5:.0f}")
    if q["maior_intervalo_ms"] > 3 * max(33.3, q["maior_intervalo_parado_ms"]):
        e.append(f"M5: intervalo {q['maior_intervalo_ms']:.0f} ms > 3x o parado {q['maior_intervalo_parado_ms']:.0f}")
    return e


def _metas(c, erros, estrito):
    ok = lambda k: not any(x.startswith(k + ":") for x in erros)  # noqa: E731
    out = {k: dict(c[k], limite_ms=LIMITES.get(k, M4_MS), ok=ok(k)) for k in ("M2", "M2b", "M3", "M4")}
    out["M5"] = {"janelas": c["M5"]["janelas"], "maior_intervalo_ms": c["M5"]["maior_intervalo_ms"], "maior_intervalo_parado_ms": c["M5"]["maior_intervalo_parado_ms"],
                 "limite_ms": M5_ESTRITO_MS if estrito else M5_VIRTUAL_MS, "ok": ok("M5")}
    return out


def _m6(ca, cb):  # informativo: nunca reprova
    razoes = {k: (ca[k]["mediana_ms"] / cb[k]["mediana_ms"] if cb[k]["mediana_ms"] > 0 else None) for k in ("M2", "M2b", "M3", "M4")}
    pares = [(200.0, ca["M2"]["p95_ms"]), (200.0, ca["M2b"]["p95_ms"]), (50.0, ca["M3"]["p95_ms"]), (M4_MS, ca["M4"]["max_ms"]), (200.0, ca["M5"]["maior_intervalo_ms"])]
    folgas = [lim / v for lim, v in pares if v > 0]
    folga = min(folgas) if folgas else None
    return {"razoes": razoes, "folga_minima": folga, "pesa": folga is not None and folga < 2}


def _conferir_par(ma, mb):
    ra, rb = sorted((p["id"], len(p["reps"])) for p in ma["passos"]), sorted((p["id"], len(p["reps"])) for p in mb["passos"])
    if ra != rb:
        raise ValueError(f"B mediu passos diferentes de A: A {ra}, B {rb}")
    pa, pb = (ma.get("base") or {}).get("produtos"), (mb.get("base") or {}).get("produtos")
    if pa != pb:
        raise ValueError(f"base.produtos diferente: A {pa}, B {pb} (têm de ter medido o mesmo modelo)")


# ---------- saída igual: IFC inteiro, como gravado ----------
def _caminho_ifc(pasta, m):
    x = m.get("arquivo_ifc")
    if not x or not isinstance(x, str):
        raise ValueError(f"{pasta}/medicao.json sem `arquivo_ifc` (o IFC do passo 7 é necessário para comparar A e B)")
    p = Path(x) if Path(x).is_absolute() else Path(pasta) / x
    if not p.is_file():
        raise ValueError(f"IFC {p} não existe")
    return p


def _formas(f):  # id da parede -> (triângulos, canto mínimo, canto máximo, volume), no mundo, em metros
    import ifcopenshell.geom as G
    import ifcopenshell.util.shape as SH
    s = G.settings()
    s.set("use-world-coords", True)
    out, ws = {}, f.by_type("IfcWall")
    it = G.iterator(s, f, 1, include=ws) if ws else None
    if it is not None and it.initialize():
        while True:
            sh = it.get()
            v = np.array(sh.geometry.verts).reshape(-1, 3)
            out[sh.id] = (len(sh.geometry.faces) // 3, *v.min(0).tolist(), *v.max(0).tolist(), float(SH.get_volume(sh.geometry)))
            if not it.next():
                break
    return out


def _abrir(caminho):  # importa e abre com stderr calado (fd 2): a biblioteca avisa em stderr ao importar e ao falhar, e isso não pode vir antes da nossa mensagem
    sys.stderr.flush()
    salvo, nulo = os.dup(2), os.open(os.devnull, os.O_WRONLY)
    try:
        os.dup2(nulo, 2)
        import ifcopenshell
        return ifcopenshell.open(str(caminho))
    finally:
        os.dup2(salvo, 2)
        os.close(salvo)
        os.close(nulo)


def _camadas(mat, escala):  # espessuras em metros (o IFC pode estar em mm)
    if mat is not None and mat.is_a("IfcMaterialLayerSetUsage"):
        mat = mat.ForLayerSet
    return [float(c.LayerThickness) * escala for c in mat.MaterialLayers] if mat is not None and mat.is_a("IfcMaterialLayerSet") else []


def _modelo(caminho, rotulo="?"):  # (contagem por classe, {chave discreta: [vetores numéricos]}); IFC que não abre ou não tem geometria calculável = ValueError
    try:
        return _ler_modelo(caminho)
    except Exception as e:  # noqa: BLE001  (ifcopenshell levanta tipos próprios; qualquer falha aqui é IFC ilegível)
        raise ValueError(f"IFC de {rotulo} ({caminho}) ilegível: {e}")


def _ler_modelo(caminho):
    f = _abrir(caminho)
    import ifcopenshell.util.element as E
    import ifcopenshell.util.unit as U
    escala = U.calculate_unit_scale(f)
    fm, nome = _formas(f), lambda x: x.Name if x is not None else ""  # noqa: E731
    classes, grupos = {}, {}
    for e in f:
        if e.is_a() not in LIVRES:
            classes[e.is_a()] = classes.get(e.is_a(), 0) + 1
    for w in f.by_type("IfcWall"):
        tipo = E.get_type(w)
        cw, ct = _camadas(E.get_material(w, should_inherit=False), escala), _camadas(E.get_material(tipo, should_inherit=False) if tipo is not None else None, escala)
        chave = (w.Name or "", nome(tipo), nome(E.get_container(w)), str(E.get_pset(w, *FIRE) or ""), len(cw), len(ct))
        forma = fm.get(w.id())
        grupos.setdefault(chave, []).append(cw + ct + (list(forma) if forma else [-1.0] * 8))
    return classes, grupos


def _validar(caminho, rotulo="?"):  # erros do ifcopenshell.validate com regras EXPRESS (o nível vem em minúsculas)
    try:
        f = _abrir(caminho)
        import ifcopenshell.validate as V
        lg = V.json_logger()
        V.validate(f, lg, express_rules=True)
    except Exception as e:  # noqa: BLE001
        raise ValueError(f"IFC de {rotulo} ({caminho}) ilegível: {e}")
    return [str(s.get("message"))[:160] for s in lg.statements if str(s.get("level", "")).lower() == "error"]


def _nome_coluna(i, ncam):
    base = [f"camada {k + 1}" for k in range(ncam)]
    return (base + ["triângulos", "mín x", "mín y", "mín z", "máx x", "máx y", "máx z", "volume"])[i]


def _comparar_grupos(ga, gb):
    dif = []
    for chave in sorted(set(ga) | set(gb)):
        dim = len((ga.get(chave) or gb[chave])[0])
        a, b = (np.array(g.get(chave, []), float).reshape(-1, dim) for g in (ga, gb))
        usada = np.zeros(len(b), bool)
        desc = f"parede '{chave[0]}' (tipo {chave[1]!r}, pavimento {chave[2]!r}, FireRating {chave[3]!r})"
        ncam = chave[4] + chave[5]
        for linha in a:
            d = np.where(usada[:, None], np.inf, np.abs(b - linha)).max(axis=1) if len(b) else np.array([])
            j = int(d.argmin()) if len(d) else -1
            if j >= 0 and d[j] <= TOL:
                usada[j] = True
            elif j >= 0 and np.isfinite(d[j]):
                col = int(np.abs(b[j] - linha).argmax())
                dif.append(f"{desc}: A e B diferem em {_nome_coluna(col, ncam)} ({linha[col]!r} x {b[j][col]!r})")
                usada[j] = True
            else:
                dif.append(f"{desc} de A sem par em B")
        dif += [f"{desc} de B sem par em A"] * int((~usada).sum())
    return dif


def comparar_ifc(ia, ib):
    """Lista de diferenças entre os dois IFCs (vazia = saída igual); inclui a validação (esquema + regras EXPRESS) dos dois."""
    ca, ga = _modelo(ia, "A")
    cb, gb = _modelo(ib, "B")
    dif = [f"classe {k}: A {ca.get(k, 0)} x B {cb.get(k, 0)}" for k in sorted(set(ca) | set(cb)) if ca.get(k, 0) != cb.get(k, 0)]
    dif += _comparar_grupos(ga, gb)
    for rotulo, caminho in (("A", ia), ("B", ib)):
        dif += [f"IFC de {rotulo} inválido: {x}" for x in _validar(caminho, rotulo)[:3]]
    return dif


# ---------- avaliação ----------
def avaliar(pasta_a, pasta_b=None, estrito=False):
    """Dicionário do JSON de saída (`metas`, `erros`, `m6`, `saida_igual`, `aprovado`); levanta ValueError em entrada inválida."""
    estrito = bool(estrito or os.environ.get("OBIM_S04_ESTRITO") == "1")
    ma = _carregar(pasta_a)
    _validar_medicao(ma, "A")
    estrito and _exigir_oficial(ma, "A")
    ca = _calcular(ma)
    erros = _erros(ca, estrito)
    out = {"estrito": estrito, "metas": _metas(ca, erros, estrito), "erros": erros, "m6": None, "saida_igual": None}
    if pasta_b is not None:
        mb = _carregar(pasta_b)
        _validar_medicao(mb, "B")
        estrito and _exigir_oficial(mb, "B")
        _conferir_par(ma, mb)
        cb = _calcular(mb)
        ia, ib = _caminho_ifc(pasta_a, ma), _caminho_ifc(pasta_b, mb)
        dif = comparar_ifc(ia, ib)
        extra = len(dif) - MAX_DIFERENCAS
        out["m6"] = _m6(ca, cb)
        out["saida_igual"] = {"ok": not dif, "diferencas": dif[:MAX_DIFERENCAS] + ([f"... e mais {extra} diferenças"] if extra > 0 else [])}
    out["aprovado"] = not erros and (out["saida_igual"] is None or out["saida_igual"]["ok"])
    return out


def _resumo_texto(r):
    linhas = [f"Régua {'estrita' if r['estrito'] else 'virtual'}: {'APROVADO' if r['aprovado'] else 'REPROVADO'}"]
    for k, v in r["metas"].items():
        linhas.append(f"  {k}: {'ok' if v['ok'] else 'FALHOU'}" + (f" (mediana {v['mediana_ms']:.1f} ms, p95 {v['p95_ms']:.1f} ms, máx {v['max_ms']:.1f} ms)" if "mediana_ms" in v else f" (maior intervalo {v['maior_intervalo_ms']:.1f} ms)"))
    linhas += [f"  erro: {e}" for e in r["erros"]]
    if r["saida_igual"] is not None:
        linhas.append(f"  saída igual: {'sim' if r['saida_igual']['ok'] else 'NÃO'}" + "".join(f"\n    - {d}" for d in r["saida_igual"]["diferencas"]))
    if r["m6"] is not None:
        linhas.append(f"  M6 (informativo): razões {r['m6']['razoes']}, folga mínima {r['m6']['folga_minima']}, pesa {r['m6']['pesa']}")
    return "\n".join(linhas)


def main(argv=None):
    p = argparse.ArgumentParser(description="Metas, saída igual, M6 e linhas")
    p.add_argument("--a", help="pasta do fluxo A (medicao.json e o IFC do passo 7)")
    p.add_argument("--b", help="pasta do fluxo B (opcional)")
    p.add_argument("--estrito", action="store_true", help="régua estrita (p95), como OBIM_S04_ESTRITO=1")
    p.add_argument("--json", help="grava o resultado neste arquivo")
    p.add_argument("--linhas", action="store_true", help="conta as linhas (M7) em --raiz")
    p.add_argument("--raiz", help="pasta com obimcore, fluxo_a e fluxo_b")
    args = p.parse_args(argv)
    try:
        if args.linhas:
            if not args.raiz:
                raise ValueError("--linhas exige --raiz")
            if not Path(args.raiz).is_dir():
                raise ValueError(f"{args.raiz} não é uma pasta")
            res, rc, texto = {"linhas": contar_linhas(args.raiz), "linhas_cruas": contar_linhas_cruas(args.raiz)}, 0, None
        else:
            if not args.a:
                raise ValueError("informe --a PASTA (ou --linhas --raiz DIR)")
            res = avaliar(args.a, args.b, args.estrito)
            rc, texto = (0 if res["aprovado"] else 1), _resumo_texto(res)
    except (ValueError, OSError) as e:
        print(f"ENTRADA INVÁLIDA: {e}", file=sys.stderr)
        return 2
    except (KeyError, TypeError, IndexError, AttributeError, OverflowError) as e:  # rede de segurança: dado fora do formato nunca vira aprovação
        print(f"ENTRADA INVÁLIDA: formato inesperado em medicao.json ({e!r})", file=sys.stderr)
        print(traceback.format_exc(), file=sys.stderr)  # depois da mensagem: o traceback ajuda quem depura
        return 2
    if args.json:
        Path(args.json).write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(texto if texto else json.dumps(res, ensure_ascii=False))
    return rc


if __name__ == "__main__":
    sys.exit(main())
