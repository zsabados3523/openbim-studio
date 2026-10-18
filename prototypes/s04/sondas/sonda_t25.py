# SPDX-License-Identifier: AGPL-3.0-or-later
"""Sonda da F0-S04-T25 (teste T2-0 do lote Opus 57): a troca de comprimento de uma parede reenvia a cena inteira à placa? Cenas SINTÉTICAS, tela virtual.
Só ENVOLVE o fluxo A (não edita fluxo_a.py, lote.py nem o núcleo); fica em sondas/ para não entrar na contagem de linhas do M7. Uma execução = uma rodada, em processo próprio.
Por quadro novo (relógio da Cena) lê `estatisticas()` UMA vez (sem laço apertado: o mutex da cena é do desenho também) e guarda pedaços de lote enviados, triângulos na placa e contextos.
Casos: criar (controle: só acrescenta um lote), trocar parede criada pelo roteiro (lote de 1 parede), trocar parede do arquivo aberto (lote de BLOCO paredes), reenvio completo forçado por
`perder_contexto()` e cena parada. O JSON só leva números e o rótulo de tamanho.
Uso: sonda_t25.py rodada --sintetica N --rotulo R --saida ARQ.json [--criar 30] [--trocas 30] [--trocas-arquivo 10]
     sonda_t25.py agregar PASTA ROTULO[,ROTULO...]   (lê PASTA/ROTULO_r*.json; mediana das rodadas, pior valor e os critérios do cartão)"""
import argparse
import json
import os
import shutil
import sys
import tempfile
import time
import traceback
from pathlib import Path

import numpy as np

AQUI = Path(__file__).resolve().parent
for p in (AQUI.parent / "fluxo_a", AQUI.parents[2] / "scripts", AQUI.parents[1], AQUI.parents[2] / "app"):
    sys.path.insert(0, str(p))
ROTULOS = {"sint3000": 3000, "sint10k": 10000, "sint20k": 20000, "sint42k": 41600}
TIPO = {"cmd": "criar_tipo", "nome": "PAR15", "camadas_m": [0.02, 0.11, 0.02]}
PAREDE = {"cmd": "criar_parede", "tipo": "PAR15", "comprimento": 4.0, "altura": 2.8, "espessura": 0.15}
CASOS = ("criar", "troca_recente", "reenvio_pos_recente", "troca_arquivo", "reenvio_pos_arquivo")  # cada reenvio forçado vem logo depois da troca e do mesmo estado da cena
CHAVES = ("triangulos", "triangulos_na_placa", "fatias_enviadas", "contextos")


def observar(f, agir, limite_ms=15000):  # um caso: `agir()` -> {"seq", "t0", "t_cmd", ["contexto"]}; amostra uma vez por quadro novo depois de o comando voltar
    c = f.cena
    e0 = c.estatisticas()
    ultimo = max([t for t, _ in c.relogio()] or [0.0])
    a = agir()
    seq, t0, t_cmd, ctx = a["seq"], a["t0"], a["t_cmd"], a.get("contexto", False)
    quadros, ant, fim = [], e0, f._relogio() + limite_ms
    while True:
        novos = [(t, s) for t, s in c.relogio()[-64:] if t > ultimo]
        if novos:
            ultimo = novos[-1][0]
            depois = [x for x in novos if x[0] > t_cmd]
            if depois:
                e = c.estatisticas()
                quadros.append({"t": depois[-1][0], "seq_placa": depois[-1][1], "agrupados": len(depois), "dfatias": int(e["fatias_enviadas"] - ant["fatias_enviadas"]),
                                "tri_placa": int(e["triangulos_na_placa"]), "contextos": int(e["contextos"])})
                ant = e
                if depois[-1][1] >= seq and (not ctx or e["contextos"] > e0["contextos"]):
                    break
        if f._relogio() > fim:
            raise TimeoutError(f"sem quadro com a sequência {seq} em {limite_ms} ms")
        f._bombear(lambda: False, 2)
    t_fim = quadros[-1]["t"]
    todos = [t for t, _ in c.relogio() if t0 <= t <= t_fim]
    tri, seqs = [q["tri_placa"] for q in quadros], [s for t, s in c.relogio() if t0 <= t <= t_fim]
    return {"ms_total": t_fim - t0, "ms_comando": t_cmd - t0, "quadros_t22": len(todos), "quadros_antes": len([t for t in todos if t <= t_cmd]), "quadros_depois": sum(q["agrupados"] for q in quadros),
            "quadros_agrupados": sum(q["agrupados"] > 1 for q in quadros), "fatias": int(ant["fatias_enviadas"] - e0["fatias_enviadas"]), "dfatias_por_quadro": [q["dfatias"] for q in quadros],
            "tri_placa_por_quadro": tri, "tri_placa_antes": int(e0["triangulos_na_placa"]), "tri_placa_min": int(min(tri if ctx else tri + [e0["triangulos_na_placa"]])),
            "triangulos_antes": int(e0["triangulos"]), "triangulos_depois": int(ant["triangulos"]), "tri_placa_depois": tri[-1], "contextos_delta": int(ant["contextos"] - e0["contextos"]),
            "sequencia_caiu": any(b < a_ for a_, b in zip(seqs, seqs[1:]))}, a


def comando(f, cmd):
    def agir():
        g, u = f.executar_detalhado(cmd)
        return {"seq": u["sequencia"], "t0": u["t0_ms"], "t_cmd": u["t_comando_ms"], "guids": g}
    return agir


def forcar(f):
    def agir():
        t0 = f._relogio()
        f.cena.perder_contexto()
        return {"seq": f.sequencias[-1], "t0": t0, "t_cmd": f._relogio(), "contexto": True}
    return agir


def lotes_da_cena(f):  # bytes de vértices e índices de cada lote anotado em `f.sequencias` (lotes vazios e marcadores ficam de fora e são contados à parte)
    b, vazios, indisp = [], 0, 0
    for s in f.sequencias:
        try:
            o = f.cena.objetos(s)
        except Exception:  # lote já refeito ou removido
            indisp += 1
            continue
        nb = int(28 * o["n_vertices"].sum() + 4 * o["n_indices"].sum())
        b.append(nb) if nb else None
        vazios += nb == 0
    b = sorted(b)
    return {"lotes": len(b), "vazios": vazios, "indisponiveis": indisp, "mediana_bytes": float(np.median(b)) if b else 0, "maior_bytes": b[-1] if b else 0, "menor_bytes": b[0] if b else 0, "soma_bytes": sum(b)}


def estat(f):
    e = f.cena.estatisticas()
    return {k: int(e[k]) for k in ("triangulos", "vertices", "lotes", "bytes_copia", "fatias_enviadas", "triangulos_na_placa", "contextos")}


def uma_vez(f, saida, casos, nome, cmds, par=None):  # roda os comandos em sequência; com `par`, cada um é seguido de um reenvio forçado da MESMA cena (a troca reenvia a cena já trocada)
    for cmd in cmds:
        try:
            r, a = observar(f, cmd)
        except ValueError as e:  # só a classe: o texto pode ter dado do modelo
            saida.setdefault("erros_comando", []).append({"caso": nome, "classe": type(e).__name__})
            continue
        casos[nome].append(r)
        f._bombear(lambda: False, 150)  # a cena assenta antes do próximo caso
        if par:
            casos[par].append(observar(f, forcar(f))[0])
            f._bombear(lambda: False, 150)
        yield a


def rodada(a):
    import ifcopenshell  # noqa: F401  (antes do obimcore)
    import fluxo_a
    import gerar_modelo_grande
    saida = {"versao": 1, "rotulo": a.rotulo, "paredes": ROTULOS[a.rotulo], "casos": {c: [] for c in CASOS}, "erro": None, "carga_antes": os.getloadavg(), "bloco_abrir": fluxo_a.BLOCO}
    passo, tmp = "gerar", tempfile.mkdtemp(dir=os.environ.get("TMPDIR"))
    try:
        ifc = str(Path(tmp) / f"base{ROTULOS[a.rotulo]}.ifc")
        gerar_modelo_grande.gerar(ifc, paredes=ROTULOS[a.rotulo])
        passo = "abrir_ifc"
        f = fluxo_a.FluxoA(ifc, janela=True, saida=Path(tmp) / "saida")
        saida["desenho"] = {"info": str(f.cena.info()), "software": bool(f.cena.desenho_por_software())}
        if not (hasattr(f.cena, "perder_contexto") and "contextos" in f.cena.estatisticas()):
            raise RuntimeError("módulo sem perder_contexto ou contextos")
        todos = [p.GlobalId for p in f.ifc.by_type("IfcProduct") if p.Representation]  # mesma ordem do `abrir`
        passo = "abrir"
        _, u = f.executar_detalhado({"cmd": "abrir"})
        f._quadro(u["sequencia"], u["t0_ms"], u["t_comando_ms"])
        f._bombear(lambda: False, 500)
        saida["cena_depois_de_abrir"], saida["lotes_depois_de_abrir"] = estat(f), lotes_da_cena(f)
        f.executar(TIPO)
        passo = "criar"
        guids = [g for a_ in uma_vez(f, saida, saida["casos"], "criar", [comando(f, PAREDE)] * a.criar) for g in a_["guids"]]
        f.executar({"cmd": "enquadrar"})
        f._bombear(lambda: False, 500)
        saida["cena_antes_das_trocas"], saida["lotes_antes_das_trocas"] = estat(f), lotes_da_cena(f)
        passo = "troca_recente"
        list(uma_vez(f, saida, saida["casos"], "troca_recente", [comando(f, {"cmd": "mudar_comprimento", "alvo": g, "comprimento": 5.0}) for g in guids[:a.trocas]], "reenvio_pos_recente"))
        passo = "troca_arquivo"
        nlotes = -(-len(todos) // fluxo_a.BLOCO)
        alvos = [todos[k * fluxo_a.BLOCO + 7] for k in range(0, nlotes, max(1, nlotes // a.trocas_arquivo))][:a.trocas_arquivo]  # uma parede por lote do arquivo
        list(uma_vez(f, saida, saida["casos"], "troca_arquivo", [comando(f, {"cmd": "mudar_comprimento", "alvo": g, "comprimento": 5.0}) for g in alvos], "reenvio_pos_arquivo"))
        saida["cena_depois_das_trocas"] = estat(f)
        passo = "parado"
        e0, t0 = f.cena.estatisticas(), f._relogio()
        f._bombear(lambda: False, 1000)
        e1 = f.cena.estatisticas()
        saida["parado"] = {"ms": f._relogio() - t0, "dfatias": int(e1["fatias_enviadas"] - e0["fatias_enviadas"]), "dcontextos": int(e1["contextos"] - e0["contextos"])}
    except BaseException as e:  # só a classe, o passo e os nomes das funções da pilha
        saida["erro"] = {"classe": type(e).__name__, "passo": passo, "funcoes": [x.name for x in traceback.extract_tb(e.__traceback__)][-6:]}
    saida["carga_depois"] = os.getloadavg()
    Path(a.saida).write_text(json.dumps(saida, ensure_ascii=False, indent=1), encoding="utf-8")
    shutil.rmtree(tmp, ignore_errors=True)
    sys.stdout.flush()
    os._exit(0)


def med(v):
    return float(np.median(v)) if len(v) else None


def resumo_caso(rs, caso):  # rs: rodadas; por rodada a mediana do caso; devolve mediana das rodadas e pior valor
    ev = [x["casos"][caso] for x in rs]
    d = {"eventos_por_rodada": [len(e) for e in ev]}
    for k, pior in (("fatias", max), ("quadros_t22", max), ("quadros_antes", max), ("quadros_depois", max), ("ms_total", max), ("ms_comando", max), ("quadros_agrupados", max)):
        por = [med([q[k] for q in e]) for e in ev]
        d[k] = {"mediana_das_rodadas": med(por), "medianas": por, "pior": pior(q[k] for e in ev for q in e)}
    por = [med([q["tri_placa_min"] / q["triangulos_antes"] for q in e]) for e in ev]
    d["tri_placa_min_fracao"] = {"mediana_das_rodadas": med(por), "medianas": por, "pior_menor": min(q["tri_placa_min"] / q["triangulos_antes"] for e in ev for q in e)}
    pf = [x for e in ev for q in e for x in q["dfatias_por_quadro"]]
    d["fatias_por_quadro"] = {"mediana": med(pf), "maior": max(pf), "quadros_observados": len(pf)}
    d["contextos_delta_maior"] = max(q["contextos_delta"] for e in ev for q in e)
    d["eventos"] = sum(len(e) for e in ev)
    d["tri_placa_min_abaixo_de_triangulos_menos_24"] = sum(q["tri_placa_min"] < q["triangulos_antes"] - 24 for e in ev for q in e)
    d["tri_placa_nunca_abaixo_do_anterior"] = sum(q["tri_placa_min"] >= q["tri_placa_antes"] for e in ev for q in e)
    d["tri_placa_final_igual_cena"] = sum(q["tri_placa_depois"] == q["triangulos_depois"] for e in ev for q in e)
    d["sequencia_caiu"] = sum(bool(q["sequencia_caiu"]) for e in ev for q in e)
    return d


def agregar(pasta, rotulos):
    por = {}
    for r in rotulos:
        rs = [json.loads(p.read_text()) for p in sorted(Path(pasta).glob(f"{r}_r*.json"))]
        if not rs or any(x["erro"] for x in rs):
            por[r] = {"erro": [x["erro"] for x in rs] or "sem rodadas"}
            continue
        e = rs[0]["cena_antes_das_trocas"]
        bvi = 28 * e["vertices"] + 12 * e["triangulos"]  # só vértices e índices (lote 57 §1 item 6)
        d = {"rodadas": len(rs), "paredes": rs[0]["paredes"], "desenho_software": [x["desenho"]["software"] for x in rs], "carga": [[x["carga_antes"][0], x["carga_depois"][0]] for x in rs],
             "cena_antes_das_trocas": e, "lotes_antes_das_trocas": [x["lotes_antes_das_trocas"] for x in rs], "bytes_vertices_indices": bvi, "quadros_previstos_vi_2MiB": bvi / (2 << 20),
             "quadros_previstos_bytes_copia_2MiB": e["bytes_copia"] / (2 << 20), "parado": [x["parado"] for x in rs], "erros_comando": [x.get("erros_comando", []) for x in rs]}
        d["casos"] = {c: resumo_caso(rs, c) for c in CASOS if all(x["casos"][c] for x in rs)}
        for c, fz in (("troca_recente", "reenvio_pos_recente"), ("troca_arquivo", "reenvio_pos_arquivo")):  # pares (troca, reenvio forçado da mesma cena) com o critério 3 do cartão
            if c in d["casos"] and fz in d["casos"]:
                pares = [(q, z) for x in rs for q, z in zip(x["casos"][c], x["casos"][fz])]
                d["casos"][c]["pares"] = len(pares)
                d["casos"][c]["razao_fatias_sobre_forcado"] = {"mediana": med([q["fatias"] / z["fatias"] for q, z in pares]), "menor": min(q["fatias"] / z["fatias"] for q, z in pares), "maior": max(q["fatias"] / z["fatias"] for q, z in pares)}
                d["casos"][c]["criterio3_fatias_dentro_de_10pct"] = sum(abs(q["fatias"] - z["fatias"]) <= 0.1 * z["fatias"] for q, z in pares)
                d["casos"][c]["dif_quadros_depois_sobre_forcado"] = {"mediana": med([q["quadros_depois"] - z["quadros_depois"] for q, z in pares]), "menor": min(q["quadros_depois"] - z["quadros_depois"] for q, z in pares), "maior": max(q["quadros_depois"] - z["quadros_depois"] for q, z in pares)}
                d["casos"][c]["criterio3_quadros_dentro_de_10pct_ou_1"] = sum(abs(q["quadros_depois"] - z["quadros_depois"]) <= max(1, 0.1 * z["quadros_depois"]) for q, z in pares)
        por[r] = d
    return por


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="modo", required=True)
    r = sub.add_parser("rodada")
    r.add_argument("--sintetica", type=int, required=True)
    r.add_argument("--rotulo", required=True, choices=sorted(ROTULOS))
    r.add_argument("--saida", required=True)
    r.add_argument("--criar", type=int, default=30)
    r.add_argument("--trocas", type=int, default=30)
    r.add_argument("--trocas-arquivo", type=int, default=10)
    ag = sub.add_parser("agregar")
    ag.add_argument("pasta")
    ag.add_argument("rotulos")
    a = ap.parse_args()
    if a.modo == "rodada":
        if a.sintetica != ROTULOS[a.rotulo]:
            sys.exit("--sintetica não bate com o rótulo")
        import faulthandler
        faulthandler.dump_traceback_later(int(os.environ.get("OBIM_LIMITE", 3600)) - 20, exit=True)
        rodada(a)
    else:
        print(json.dumps(agregar(a.pasta, a.rotulos.split(",")), ensure_ascii=False, indent=1))
