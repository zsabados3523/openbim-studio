# SPDX-License-Identifier: AGPL-3.0-or-later
"""F0-S04-T26 (R-0): simula a regra de reinício R-A nas curvas de memória já gravadas pelo T24.

Só leitura. Não abre IFC, não roda o carregador. Lê apenas campos numéricos dos JSON de `n250_r*` e `rb250_r*`
(`marcas`, `amostras`, `reinicios`, `abrir_s`, `silencio_max_s_por_bloco`), na tela virtual e na tela real.

Regra simulada (lote 58 §2.3 R-A): em um bloco que NÃO é o primeiro do filho, se a memória residente atual do filho
crescer mais que G desde o começo do bloco, o pai mata o filho e refaz o bloco num filho novo.

Uso:
    python simular_ra_t26.py [--virtual PASTA] [--real PASTA]   # tabelas em markdown
    python simular_ra_t26.py --conferir                          # refaz tudo com `jq` e compara
"""
from __future__ import annotations

import argparse
import json
import statistics as est
import subprocess
from pathlib import Path

VIRTUAL = Path("~/openbim-medicao/2026-10-18-T24/dados").expanduser()
REAL = Path("~/openbim-medicao/2026-10-18-real/dados").expanduser()
GS = (500, 1000, 1500, 2000)  # MB (G = 0,5; 1,0; 1,5; 2,0 GB; 1 GB = 1.000 MB)
BLOCO_PESADO = 22
LIMITE_S, REINICIO_S, X_MB = 60.0, 3.79, 106  # metas e custos do lote 58 (não são afrouxados aqui)

# Mesma conta em jq: por bloco [n, filho, base, fim, cresc_max, n_amostras, cruz500, cruz1000, cruz1500, cruz2000].
JQ = r"""
def chaves: [keys_unsorted[] | select(. != "t" and . != "pai")];
[.marcas[] | select(.[1] == "convertendo") | .[0]] as $M
| ([.marcas[] | .[0]] | max) as $fim
| .amostras as $A
| [range(0; $M | length)] | map(
    . as $b | $M[$b] as $s
    | (if $b + 1 < ($M | length) then $M[$b + 1] else $fim end) as $e
    | ([$A[] | select(.t >= $s and (chaves | length) > 0)] | first) as $a0
    | (if $a0 == null then null else ($a0 | chaves | sort | last) end) as $k
    | if $k == null then [$b + 1, null, null, null, null, 0, null, null, null, null] else
      ([$A[] | select(.t >= $s and .t < $e and has($k))]) as $w
      | (([$A[] | select(.t <= $s and has($k))] | last) // $w[0]) as $p
      | if $p == null or ($w | length) == 0 then [$b + 1, $k, null, null, null, 0, null, null, null, null] else
        ($p[$k][0]) as $base
        | ($w | map({t: .t, v: .[$k][0]})) as $sr
        | [$b + 1, $k, $base, $sr[-1].v, ($sr | map(.v - $base) | max), ($sr | length)]
          + [[500, 1000, 1500, 2000][] as $g | (([$sr[] | select(.v - $base > $g)] | first) as $c
              | if $c == null then null else (($c.t - $s) * 100 | round) / 100 end)]
      end end)
"""


def _filho(a):
    c = sorted(k for k in a if k not in ("t", "pai"))
    return c[-1] if c else None


def blocos(r):
    """Por bloco de 250: filho, memória no começo e no fim, maior crescimento, nº de amostras e instante de cruzar cada G."""
    M = [m[0] for m in r["marcas"] if m[1] == "convertendo"]
    fim = max(m[0] for m in r["marcas"])
    A = r["amostras"]
    out = []
    for i, s in enumerate(M):
        e = M[i + 1] if i + 1 < len(M) else fim
        a0 = next((a for a in A if a["t"] >= s and _filho(a)), None)
        k = _filho(a0) if a0 else None
        w = [a for a in A if s <= a["t"] < e and k in a] if k else []
        p = ([a for a in A if a["t"] <= s and k in a] or w[:1] or [None])[-1] if k else None
        if not w or p is None:
            out.append([i + 1, k, None, None, None, 0, None, None, None, None])
            continue
        base = p[k][0]
        cr = []
        for g in GS:
            c = next((a for a in w if a[k][0] - base > g), None)
            cr.append(None if c is None else round((c["t"] - s) * 100) / 100)
        out.append([i + 1, k, base, w[-1][k][0], max(a[k][0] - base for a in w), len(w), *cr])
    return out, M, fim


def resumo(bl, M, fim, r):
    """Aplica a regra a uma abertura. `bl` = lista de blocos (de `blocos` ou do jq)."""
    primeiro = {b[0] for i, b in enumerate(bl) if i == 0 or b[1] != bl[i - 1][1]}  # 1º bloco de cada filho: regra não vale
    b22 = bl[BLOCO_PESADO - 1]
    base0 = bl[0][2]
    leves = [b for b in bl if b[0] not in primeiro and b[0] != BLOCO_PESADO and b[4] is not None]
    d = {"rotulo": r["rotulo"], "abrir_s": r["abrir_s"], "filhos": len({b[1] for b in bl if b[1]}), "blocos": len(bl),
         "b22_filho": b22[1], "b22_ini_mb": b22[2], "b22_fim_mb": b22[3], "b22_cresc_mb": b22[4], "b22_amostras": b22[5],
         "b22_dur_s": round(((M[BLOCO_PESADO] if BLOCO_PESADO < len(M) else fim) - M[BLOCO_PESADO - 1]) * 100) / 100,
         "b22_primeiro_do_filho": BLOCO_PESADO in primeiro, "base0_mb": base0, "leve_max_mb": max(b[4] for b in leves),
         "leve_max_bloco": max(leves, key=lambda b: b[4])[0],
         "x_blocos": sum(1 for b in bl if b[0] not in primeiro and b[2] - base0 >= X_MB),
         "x_blocos_total": sum(1 for b in bl if b[0] not in primeiro), "gs": {}}
    for j, g in enumerate(GS):
        falsos = [b[0] for b in leves if b[4] > g]
        d["gs"][g] = {"falsos": falsos, "b22_cruza_s": b22[6 + j], "b22_passa": b22[4] is not None and b22[4] > g}
    return d


def carregar(pasta, rotulo):
    for p in sorted(Path(pasta).glob(f"{rotulo}_r[0-9].json")):
        r = json.loads(p.read_text())
        bl, M, fim = blocos(r)
        yield p.stem, r, bl, M, fim


def silencio(r):
    """Maior silêncio do filho (s) por bloco global: chave 'filho.bloco_no_filho'."""
    s = {}
    for k, v in r["silencio_max_s_por_bloco"].items():
        f, c = (int(x) for x in k.split("."))
        s[sum(r["reinicios"][:f - 1]) + c] = v
    return s


def jq_blocos(p):
    saida = subprocess.run(["jq", "-c", JQ, str(p)], capture_output=True, text=True, check=True).stdout
    return json.loads(saida)


def conferir(pastas):
    """Compara, número a número, a tabela de blocos e o resumo do Python com os do jq. Devolve (bateram, total)."""
    ok = tot = 0
    for tela, pasta in pastas.items():
        for rot in ("n250", "rb250"):
            for nome, r, bl, M, fim in carregar(pasta, rot):
                jb = jq_blocos(Path(pasta) / f"{nome}.json")
                tot_b = len(bl)
                for a, b in zip(bl, jb):
                    for x, y in zip(a, b):
                        tot += 1
                        ok += (x == y) or (isinstance(x, (int, float)) and isinstance(y, (int, float)) and abs(x - y) < 0.006)
                tot += 1
                ok += tot_b == len(jb)
                da, dj = resumo(bl, M, fim, r), resumo(jb, M, fim, r)  # mesmo agregador sobre o que o jq calculou
                for k, v in da.items():
                    if k == "gs":
                        for g, w in v.items():
                            for kk, vv in w.items():
                                tot += 1
                                ok += vv == dj["gs"][g][kk]
                    else:
                        tot += 1
                        ok += v == dj[k]
                # números de entrada lidos direto por jq
                for campo in ("abrir_s", "pico_somado_mb"):
                    v = float(subprocess.run(["jq", f".{campo}", str(Path(pasta) / f"{nome}.json")], capture_output=True, text=True).stdout)
                    tot += 1
                    ok += v == r[campo]
                s = silencio(r)
                for filtro, esperado in (('.silencio_max_s_por_bloco | (.["1.22"] // .["2.1"])', s[BLOCO_PESADO]),
                                         ('[.silencio_max_s_por_bloco | to_entries[] | select(.key != "1.22" and .key != "2.1") | .value] | max',
                                          max(v for b, v in s.items() if b != BLOCO_PESADO))):
                    v = float(subprocess.run(["jq", filtro, str(Path(pasta) / f"{nome}.json")], capture_output=True, text=True).stdout)
                    tot += 1
                    ok += v == esperado
    return ok, tot


def mediana(v):
    return est.median(v) if v else None


def fmt(x, nd=2):
    return "-" if x is None else (f"{x:.{nd}f}".replace(".", ",") if isinstance(x, float) else f"{x:,}".replace(",", "."))


def tabelas(pastas):
    todos = {}
    for tela, pasta in pastas.items():
        for rot in ("n250", "rb250"):
            for nome, r, bl, M, fim in carregar(pasta, rot):
                todos[(tela, nome)] = (r, bl, M, fim, resumo(bl, M, fim, r))
    print("## A. Por abertura: bloco 22 e blocos leves\n")
    print("| tela | abertura | abrir s | filhos | bloco 22: filho | começo MB | fim MB | cresce MB | duração s | amostras | intervalo médio s | maior crescimento de bloco leve MB (bloco) |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for (tela, nome), (r, bl, M, fim, d) in todos.items():
        iv = d["b22_dur_s"] / d["b22_amostras"] if d["b22_amostras"] else None
        print(f"| {tela} | {nome} | {fmt(d['abrir_s'])} | {d['filhos']} | {d['b22_filho']} | {fmt(d['b22_ini_mb'])} | {fmt(d['b22_fim_mb'])} | "
              f"{fmt(d['b22_cresc_mb'])} | {fmt(d['b22_dur_s'])} | {d['b22_amostras']} | {fmt(iv, 3)} | {fmt(d['leve_max_mb'])} ({d['leve_max_bloco']}) |")
    print("\n## B. Instante em que o bloco 22 cruza G (segundos desde o começo do bloco)\n")
    print("| tela | abertura | " + " | ".join(f"G={g / 1000:g} GB".replace(".", ",") for g in GS) + " |\n|---|---|" + "---|" * len(GS))
    for (tela, nome), (r, bl, M, fim, d) in todos.items():
        print(f"| {tela} | {nome} | " + " | ".join(fmt(d["gs"][g]["b22_cruza_s"]) for g in GS) + " |")
    print("\n## C. Reinícios falsos (blocos leves que passariam de G; bloco 22 e 1º bloco de cada filho ficam de fora)\n")
    print("| tela | abertura | " + " | ".join(f"G={g / 1000:g} GB".replace(".", ",") for g in GS) + " |\n|---|---|" + "---|" * len(GS))
    for (tela, nome), (r, bl, M, fim, d) in todos.items():
        print(f"| {tela} | {nome} | " + " | ".join(
            (str(len(d["gs"][g]["falsos"])) + (" (blocos " + ",".join(map(str, d["gs"][g]["falsos"])) + ")" if d["gs"][g]["falsos"] else "")) for g in GS) + " |")
    print("\n## D. Veredito por G (critério 1) e tempo, tela real\n")
    pior_real = max(d["abrir_s"] for (t, n), (r, bl, M, fim, d) in todos.items() if t == "real" and n.startswith("rb250"))
    print(f"Pior abrir de `rb250` na tela real: {fmt(pior_real)} s. Limite {fmt(LIMITE_S, 0)} s. Custo de um reinício: {fmt(REINICIO_S)} s (já dentro do `rb250`).\n")
    print("| G | reinício exatamente 1x, no bloco 22, nas 12 aberturas? | n250 sem cruzar (aberturas) | falsos (soma nas 12) | perdido pior, real (s) | 52,74 + perdido (s) | + 3,79 (leitura conservadora) | cumpre ≤ 60 s? |")
    print("|---|---|---|---|---|---|---|---|")
    for g in GS:
        n250 = [(k, v) for k, v in todos.items() if k[1].startswith("n250")]
        sem_cruz = sum(1 for k, v in n250 if not v[4]["gs"][g]["b22_passa"])
        falsos = sum(len(v[4]["gs"][g]["falsos"]) for v in todos.values())
        reais = [v[4]["gs"][g]["b22_cruza_s"] for k, v in n250 if k[0] == "real" and v[4]["gs"][g]["b22_cruza_s"] is not None]
        perd = max(reais) if reais else None
        ok1 = sem_cruz == 0 and falsos == 0
        t1 = pior_real + perd if perd is not None else None
        t2 = t1 + REINICIO_S if t1 is not None else None
        cumpre = ok1 and t1 is not None and t1 <= LIMITE_S
        print(f"| {str(g / 1000).replace('.', ',')} GB | {'sim' if ok1 else 'NAO'} | {sem_cruz} | {falsos} | {fmt(perd)} | {fmt(t1)} | {fmt(t2)} | "
              f"{'sim' if cumpre else 'NAO'}{'' if t2 is None or t2 <= LIMITE_S else ' (leitura conservadora estoura)'} |")
    print("\n## E. Regra \"memória que sobrou antes do bloco\" (lote 58 §2.4): blocos fora do 1º de cada filho cujo começo está ≥ 106 MB acima do começo do bloco 1\n")
    print("| tela | abertura | começo do bloco 1 MB | blocos com excesso ≥ 106 MB | de | menor excesso entre blocos que não são 1º do filho MB |\n|---|---|---|---|---|---|")
    for (tela, nome), (r, bl, M, fim, d) in todos.items():
        prim = {b[0] for i, b in enumerate(bl) if i == 0 or b[1] != bl[i - 1][1]}
        exc = [b[2] - d["base0_mb"] for b in bl if b[0] not in prim]
        print(f"| {tela} | {nome} | {fmt(d['base0_mb'])} | {d['x_blocos']} | {d['x_blocos_total']} | {fmt(min(exc))} |")
    print("\n## F. Maior silêncio do filho por bloco (s), tela real e virtual (limite do vigia: 20 s)\n")
    print("| tela | abertura | bloco 22 | maior dos outros blocos (bloco) | blocos com marca |\n|---|---|---|---|---|")
    for (tela, nome), (r, bl, M, fim, d) in todos.items():
        s = silencio(r)
        outros = {b: v for b, v in s.items() if b != BLOCO_PESADO}
        bm = max(outros, key=outros.get)
        print(f"| {tela} | {nome} | {fmt(s.get(BLOCO_PESADO))} | {fmt(outros[bm])} ({bm}) | {len(s)} |")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--virtual", default=str(VIRTUAL))
    ap.add_argument("--real", default=str(REAL))
    ap.add_argument("--conferir", action="store_true")
    a = ap.parse_args()
    pastas = {"virtual": a.virtual, "real": a.real}
    if a.conferir:
        ok, tot = conferir(pastas)
        print(f"conferência com jq: {ok} de {tot} bateram")
        raise SystemExit(0 if ok == tot else 1)
    tabelas(pastas)


if __name__ == "__main__":
    main()
