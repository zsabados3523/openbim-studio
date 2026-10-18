# SPDX-License-Identifier: AGPL-3.0-or-later
"""Sonda da F0-S04-T27 (G-0a do lote Opus 58): a troca de geometria com os 13 tamanhos de lote do detalhado. Cena SINTÉTICA, tela virtual.
Pela API Python do núcleo (`obimcore.Cena.adicionar_lote` / `atualizar`), sem IFC do PO e sem editar `fluxo_a.py`, `lote.py` ou o núcleo.
Monta os 13 lotes do detalhado (T25 §10.1, 0,55 a 285,36 MiB) e põe 3 paredes em cada um dos lotes de ~8, 24, 68 e 285 MiB (mais as
paredes de 1 KB criadas pelo roteiro). Por troca mede: quadros depois do comando, pedaços enviados e o menor `triangulos_na_placa`;
por quadro lê `estatisticas()` UMA vez (nunca em laço apertado). "Criar parede" é o piso (só acrescenta; nunca esvazia a placa).
Os milissegundos de software NÃO valem como os da placa; o que se lê são contadores (quadros, pedaços, triângulos).
Geometria de enchimento DEGENERADA mas REFERENCIADA: nv vértices na origem e nv índices (um por vértice), de modo que os bytes do lote
(28*vértices + 4*índices) sobrevivam a `sem` de `cena.cpp` — que descarta vértice sem índice vivo (um enchimento com poucos índices
encolheria o lote a cada troca; achado no ensaio). Sem fragmento (triângulos de área zero), mas o desenho por software ainda processa os vértices.
O contador de quadros depende dos BYTES por quadro (2 MiB), não da forma. Uso: sonda_t27.py rodada --rotulo t27 --saida ARQ.json [--cena cheia|reduzida] [--paredes 3] [--limite-ms 120000]
     sonda_t27.py agregar PASTA
"""
import argparse
import json
import os
import shutil
import sys
import tempfile
import traceback
from pathlib import Path

import numpy as np

AQUI = Path(__file__).resolve().parent
for p in (AQUI.parent / "fluxo_a", AQUI.parents[2] / "scripts", AQUI.parents[1], AQUI.parents[2] / "app"):
    sys.path.insert(0, str(p))
from formato_malha import DTYPE_OBJETO, DTYPE_VERTICE, LoteMalha  # noqa: E402

ORCAMENTO = 2 << 20  # ORCAMENTO_BYTES de nucleo/motor.h (2 MiB); nunca alterado aqui
LIMITE_MS = 120000  # limite por troca (a sonda; não é o OBIM_QUADRO_MS nem nenhum limite do produto)
# T25 §10.1: os 13 lotes do detalhado, em MiB (a soma dá 805,72 MiB; o exato por lote não foi publicado)
LOTES_MIB = [117.20, 61.73, 0.55, 1.24, 8.97, 8.97, 4.20, 47.75, 53.55, 24.24, 68.27, 123.69, 285.36]
TOCADOS = {"8MiB": 4, "24MiB": 9, "68MiB": 10, "285MiB": 12}  # índices dos lotes grandes tocados (cena cheia)
CENA_REDUZIDA = [24.24, 68.27, 285.36]  # critério 4: só os lotes grandes (~378 MiB)
PAREDE_TRI = 12  # a parede do roteiro (T25 §2): 12 triângulos -> 28*36 + 4*36 = 1.152 bytes
PAREDE_BYTES = 28 * 3 * PAREDE_TRI + 4 * 3 * PAREDE_TRI


def lote_de(bytes_alvo, guids_parede=(), guid_filler="T27FILLER"):
    # Enchimento REAL: nv_f vértices degenerados (todos na origem) e nv_f índices (arange), de modo que cada vértice
    # fica referenciado. `sem` (cena.cpp) descarta vértice sem índice vivo: um enchimento com 3 índices degenerados
    # apontando sempre para o vértice 0 encolheria o lote a ~40 bytes em qualquer troca (achado no ensaio). Assim os bytes
    # do lote sobrevivem à troca, como no detalhado (que tem ~3 vértices por triângulo, 8,8 M tri em 805,7 MiB).
    # Guids únicos por lote (enchimento e paredes): `atualizar` soma os guids do lote novo ao conjunto de remoção.
    nv_p = 3 * PAREDE_TRI
    nb = len(guids_parede)
    restante = int(bytes_alvo) - nb * PAREDE_BYTES
    nv_f = 0
    if nb == 0 or restante > 0:
        nv_f = max(3, (max(32, restante) // 32) // 3 * 3)  # 28 bytes/vértice + 4 bytes/índice (indice = vertice)
    ni_f = nv_f
    total_v = nv_f + nb * nv_p
    total_i = ni_f + nb * 3 * PAREDE_TRI
    v, ind = np.zeros(total_v, DTYPE_VERTICE), np.zeros(total_i, np.uint32)
    objs = np.empty((1 if nv_f else 0) + nb, DTYPE_OBJETO)
    vv, ii, k = 0, 0, 0
    tri = 0
    if nv_f:  # vértices na origem -> triângulos degenerados (sem fragmento), mas todos referenciados
        ind[ii:ii + ni_f] = np.arange(vv, vv + ni_f, dtype=np.uint32)
        objs[k] = (0, guid_filler.encode("ascii"), ii, ni_f, vv, nv_f, [0.0, 0.0, 0.0], [0.0, 0.0, 0.0])
        vv, ii, k, tri = vv + nv_f, ii + ni_f, k + 1, ni_f // 3
    for g in guids_parede:
        base = np.arange(nv_p, dtype=np.float32)
        v["pos"][vv:vv + nv_p, 0] = (base % 6) * 0.2
        v["pos"][vv:vv + nv_p, 1] = (base // 6).astype(np.float32) * 0.2
        v["cor"][vv:vv + nv_p] = (200, 200, 200, 255)
        ind[ii:ii + nv_p] = np.arange(vv, vv + nv_p, dtype=np.uint32)
        objs[k] = (0, g.encode("ascii"), ii, 3 * PAREDE_TRI, vv, nv_p, [0.0, 0.0, 0.0], [1.2, 0.4, 0.0])
        vv, ii, k, tri = vv + nv_p, ii + 3 * PAREDE_TRI, k + 1, tri + PAREDE_TRI
    lote = LoteMalha(0, v, ind, objs, np.zeros(3), k, k)
    return lote, 28 * total_v + 4 * total_i, tri  # (lote, bytes vértices+índices, triângulos do lote)


def observar(f, agir, limite_ms=None):  # um caso: agir() devolve a sequência; amostra UMA vez por quadro novo depois do comando
    limite_ms = limite_ms or LIMITE_MS
    c = f.cena
    e0 = c.estatisticas()
    ultimo = max([t for t, _ in c.relogio()] or [0.0])
    t0 = f._relogio()
    seq = agir()
    t_cmd = f._relogio()
    quadros, ant, fim = [], e0, f._relogio() + limite_ms
    while True:
        novos = [(t, s) for t, s in c.relogio()[-64:] if t > ultimo]
        if novos:
            ultimo = novos[-1][0]
            depois = [x for x in novos if x[0] > t_cmd]
            if depois:
                e = c.estatisticas()
                quadros.append({"agrupados": len(depois), "dfatias": int(e["fatias_enviadas"] - ant["fatias_enviadas"]),
                                "tri_placa": int(e["triangulos_na_placa"]), "contextos": int(e["contextos"])})
                ant = e
                if depois[-1][1] >= seq:
                    break
        if f._relogio() > fim:
            raise TimeoutError(f"sem quadro com a sequência {seq} em {limite_ms} ms")
        f._bombear(lambda: False, 2)
    frames = [t for t, _ in c.relogio() if t > t_cmd]
    t_fim = max(frames) if frames else t_cmd
    tri = [q["tri_placa"] for q in quadros]
    vi = 28 * int(ant["vertices"]) + 12 * int(ant["triangulos"])  # bytes de vértices+índices da cena depois do comando (lote 58 §1 item 6)
    return {"ms_total": t_fim - t0, "quadros_depois": sum(q["agrupados"] for q in quadros), "fatias": int(ant["fatias_enviadas"] - e0["fatias_enviadas"]),
            "dfatias_por_quadro": [q["dfatias"] for q in quadros], "amostras": [[q["agrupados"], q["dfatias"], q["tri_placa"]] for q in quadros], "lotes_antes": int(e0["lotes"]), "lotes_depois": int(ant["lotes"]), "tri_placa_antes": int(e0["triangulos_na_placa"]), "tri_placa_min": int(min(tri) if tri else e0["triangulos_na_placa"]),
            "tri_placa_depois": tri[-1] if tri else int(e0["triangulos_na_placa"]), "triangulos_antes": int(e0["triangulos"]), "triangulos_depois": int(ant["triangulos"]),
            "contextos_delta": int(ant["contextos"] - e0["contextos"]), "cena_vi_depois": vi, "previsto_quadros": -(-vi // ORCAMENTO) + 1}


def trocar(f, casos, caso, guid_antigo, gnovo, bytes_tocado, tri_tocado, seq_guids):
    lote, _, _ = lote_de(PAREDE_BYTES, [gnovo])
    r = observar(f, lambda l=lote, o=guid_antigo: int(f.cena.atualizar(l, [o])))
    r.update({"caso": caso, "bytes_lote_tocado": bytes_tocado, "tri_lote_tocado": tri_tocado, "guids": seq_guids})
    casos.setdefault(caso, []).append(r)
    f._bombear(lambda: False, 150)
    return gnovo


def rodada(a):
    import fluxo_a
    if a.cena == "cheia":
        mibs, idx_tocados = LOTES_MIB, dict(TOCADOS)
    else:
        mibs, idx_tocados = CENA_REDUZIDA, {"24MiB": 0, "68MiB": 1, "285MiB": 2}
    saida = {"versao": 1, "rotulo": a.rotulo, "cena": a.cena, "paredes": a.paredes, "arquivo_real": False, "casos": {}, "erro": None,
             "orcamento_bytes": ORCAMENTO, "limite_ms": LIMITE_MS, "carga_antes": list(os.getloadavg()), "uptime_s": float(Path("/proc/uptime").read_text().split()[0])}
    passo, tmp, n = "abrir_janela", tempfile.mkdtemp(dir=os.environ.get("TMPDIR")), 0
    try:
        f = fluxo_a.FluxoA(None, janela=True, saida=Path(tmp) / "saida")
        c = f.cena
        saida["desenho"] = {"info": str(c.info()), "software": bool(c.desenho_por_software())}
        gs_parede, tri_lote = {}, {}
        for i, mib in enumerate(mibs):
            gs = []
            if i in idx_tocados.values():
                gs = [f"T27PAREDE{n + k:013d}" for k in range(a.paredes)]
            n += len(gs)
            lote, nb, tri = lote_de(mib * (1 << 20), gs, f"T27FILLER{i:013d}")
            c.adicionar_lote(lote)
            if i in idx_tocados.values():
                gs_parede[i], tri_lote[i] = list(gs), tri
            saida.setdefault("lotes_bytes", []).append(nb)
        passo = "assentar"  # espera a placa completar (805 MiB levam ~400 quadros em software); sem isso o "criar" mediria a placa ainda enchendo
        fim = f._relogio() + 300000
        while f._relogio() < fim:
            f._bombear(lambda: False, 100)
            e = c.estatisticas()
            if int(e["triangulos_na_placa"]) >= int(e["triangulos"]):
                break
        e = c.estatisticas()
        saida["cena_antes"] = {k: int(e[k]) for k in ("triangulos", "vertices", "lotes", "bytes_copia", "fatias_enviadas", "triangulos_na_placa")}
        saida["cena_bytes_vi"] = int(sum(saida["lotes_bytes"]))
        saida["previsto_quadros"] = -(-saida["cena_bytes_vi"] // ORCAMENTO) + 1
        casos = saida["casos"]
        # criar parede de 1 KB (piso): só acrescenta um lote, nunca esvazia a placa
        passo = "criar"
        criadas = []
        for k in range(a.paredes):
            g = f"T27CRIADA{n + k:013d}"
            lote, _, tri = lote_de(PAREDE_BYTES, [g])
            r = observar(f, lambda l=lote: int(c.atualizar(l, [])))
            r.update({"caso": "criar_1KB", "bytes_lote_tocado": PAREDE_BYTES, "tri_lote_tocado": tri, "guids": [g]})
            casos.setdefault("criar_1KB", []).append(r)
            criadas.append(g)
            f._bombear(lambda: False, 150)
        n += len(criadas)
        # trocar a parede criada (lote de 1 KB)
        passo = "troca_1KB"
        for k, g in enumerate(criadas):
            gn = f"T27TROCA{n + k:013d}"
            trocar(f, casos, "troca_1KB", g, gn, PAREDE_BYTES, PAREDE_TRI, [gn])
        n += len(criadas)
        # trocar uma parede de cada lote grande
        for nome, idx in idx_tocados.items():
            passo = "troca_" + nome
            for k, g in enumerate(gs_parede[idx]):
                gn = f"T27TROCA{n + k:013d}"
                trocar(f, casos, "troca_" + nome, g, gn, saida["lotes_bytes"][idx], tri_lote[idx], [gn])
            n += len(gs_parede[idx])
        e = c.estatisticas()
        saida["cena_depois"] = {k: int(e[k]) for k in ("triangulos", "vertices", "lotes", "bytes_copia", "fatias_enviadas", "triangulos_na_placa")}
    except BaseException as exc:
        saida["erro"] = {"classe": type(exc).__name__, "passo": passo, "funcoes": [x.name for x in traceback.extract_tb(exc.__traceback__)][-6:]}
    saida["carga_depois"] = list(os.getloadavg())
    saida["uptime_fim_s"] = float(Path("/proc/uptime").read_text().split()[0])
    Path(a.saida).write_text(json.dumps(saida, ensure_ascii=False, indent=1), encoding="utf-8")
    shutil.rmtree(tmp, ignore_errors=True)
    sys.stdout.flush()
    os._exit(0)


def med(v):
    return float(np.median(v)) if len(v) else None


def agregar(pasta):
    rs = [json.loads(p.read_text()) for p in sorted(Path(pasta).glob("t27_r*.json"))]
    ok = [x for x in rs if not x["erro"]]
    out = {"rodadas": len(rs), "ok": len(ok), "erros": [x["erro"] for x in rs if x["erro"]], "cena": ok[0]["cena"] if ok else None,
           "desenho_software": [x["desenho"]["software"] for x in ok], "lotes_bytes": ok[0]["lotes_bytes"] if ok else None,
           "cena_bytes_vi": ok[0]["cena_bytes_vi"] if ok else None, "previsto_quadros": ok[0]["previsto_quadros"] if ok else None,
           "carga": [[x["carga_antes"][0], x["carga_depois"][0]] for x in ok], "casos": {}}
    for caso in sorted({k for x in ok for k in x["casos"]}):
        ev = [q for x in ok for q in x["casos"].get(caso, [])]
        if not ev:
            continue
        df = [q["quadros_depois"] - q["previsto_quadros"] for q in ev]  # previsto = teto(cena vi ÷ 2 MiB) + 1, por evento
        dft = [q["quadros_depois"] - (-(-q["bytes_lote_tocado"] // ORCAMENTO) + 1) for q in ev]  # previsto pelo lote tocado
        am = [a for q in ev for a in q["amostras"]]  # [agrupados, dfatias, tri_placa] por quadro novo; pedaços por quadro só de amostras com 1 quadro (as agrupadas somam vários)
        fp = [a[1] for a in am if a[0] == 1]
        por_rodada = [[q["quadros_depois"] for q in x["casos"].get(caso, [])] for x in ok if x["casos"].get(caso)]
        out["casos"][caso] = {
            "eventos": len(ev), "eventos_por_rodada": [len(v) for v in por_rodada],
            "quadros_depois": {"mediana": med([q["quadros_depois"] for q in ev]), "pior": max(q["quadros_depois"] for q in ev), "por_rodada": [med(v) for v in por_rodada]},
            "fatias": {"mediana": med([q["fatias"] for q in ev]), "pior": max(q["fatias"] for q in ev)},
            "previsao_cena": {"mediana": med([q["previsto_quadros"] for q in ev]), "dif_mediana": med(df), "dif_menor": min(df), "dif_maior": max(df), "dentro_de_1": sum(abs(x) <= 1 for x in df)},
            "previsao_lote_tocado": {"dif_mediana": med(dft), "dif_menor": min(dft), "dif_maior": max(dft), "dentro_de_1": sum(abs(x) <= 1 for x in dft)},
            "cena_vi_depois": {"mediana": med([q["cena_vi_depois"] for q in ev]), "maior": max(q["cena_vi_depois"] for q in ev)},
            "fatias_por_quadro": {"mediana": med(fp), "maior": max(fp) if fp else None, "quadros_unicos": len(fp), "amostras_agrupadas_descartadas": len(am) - len(fp),
                                  "quadros_com_2": sum(x == 2 for x in fp), "quadros_com_1": sum(x == 1 for x in fp), "quadros_com_3_ou_mais": sum(x >= 3 for x in fp)},
            "lotes_antes_depois": {"antes": sorted({q["lotes_antes"] for q in ev}), "depois": sorted({q["lotes_depois"] for q in ev}), "eventos_com_mesmo_numero": sum(q["lotes_antes"] == q["lotes_depois"] for q in ev)},
            "dif_cena_por_rodada": [[min(q["quadros_depois"] - q["previsto_quadros"] for q in x["casos"][caso]), max(q["quadros_depois"] - q["previsto_quadros"] for q in x["casos"][caso])] for x in ok if x["casos"].get(caso)],
            "contextos_delta_maior": max(q["contextos_delta"] for q in ev),
            "tri_placa_min_fracao": med([q["tri_placa_min"] / q["triangulos_antes"] for q in ev if q["triangulos_antes"]]),
            "esvaziou_abaixo_do_lote_tocado": sum(q["tri_placa_min"] < q["triangulos_antes"] - q["tri_lote_tocado"] for q in ev),
            "nunca_abaixo_do_anterior": sum(q["tri_placa_min"] >= q["tri_placa_antes"] for q in ev),
            "fatias_2_exatas": sum(q["fatias"] == 2 for q in ev),
            "ms_total_mediana": med([q["ms_total"] for q in ev])}
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="modo", required=True)
    r = sub.add_parser("rodada")
    r.add_argument("--rotulo", required=True)
    r.add_argument("--saida", required=True)
    r.add_argument("--cena", choices=("cheia", "reduzida"), default="cheia")
    r.add_argument("--paredes", type=int, default=3)
    r.add_argument("--limite-ms", type=int, default=120000)
    ag = sub.add_parser("agregar")
    ag.add_argument("pasta")
    a = ap.parse_args()
    if a.modo == "rodada":
        LIMITE_MS = a.limite_ms
        p = Path(a.saida).resolve()
        if AQUI.parents[2] in p.parents:
            sys.exit("a saída da sonda tem de ficar fora do repositório")
        import faulthandler
        faulthandler.dump_traceback_later(int(os.environ.get("OBIM_LIMITE", 3600)) - 20, exit=True)
        rodada(a)
    else:
        print(json.dumps(agregar(a.pasta), ensure_ascii=False, indent=1))
