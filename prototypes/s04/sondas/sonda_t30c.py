# SPDX-License-Identifier: AGPL-3.0-or-later
"""Sonda da F0-S04-T30c (LOTE_OPUS_63 §3 ponto 2): em que sub-lote da `Cena` (T30a2) cai cada peça, e a regra de decisão da T-2. Só números.
Carrega o IFC pelo `CarregadorMalhas` de hoje, entrega cada lote à `Cena` (sem janela, sem placa) e lê as tabelas dos sub-lotes (`objetos`).
Não grava nome de arquivo, GlobalId nem nada do modelo: só classes IFC, contagens e bytes. O IFC é argumento; a saída tem de ficar fora do repositório.
Regra (escrita antes dos dados, cartão T30c): (i) nenhuma parede em sub-lote maior que C; (ii) nenhum lote do caso (b) com parede, onde caso (b) = lote de entrada
que NÃO ladrilha e passa de C (o que o núcleo conta como `nao_partido`). Parede que ela mesma passa de C: volta ao Opus. O JSON traz também os lotes que
não ladrilham com parede e cabem em C (inofensivos para a (ii), mas visíveis). Quem decide é o líder; a sonda só calcula.
Uso: sonda_t30c.py ifc ARQ.ifc [--saida ARQ.json]     (dados reais; o IFC do PO só entra por argumento, nunca embutido)
     sonda_t30c.py sintetica [--cena reduzida|cheia] [--saida ARQ.json]     (cena sintética do T27, sem IFC)
     sonda_t30c.py autoteste     (casos montados à mão: a regra dá o veredito esperado)"""
import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np

AQUI = Path(__file__).resolve().parent
for p in (AQUI, AQUI.parent / "fluxo_a", AQUI.parents[2] / "scripts", AQUI.parents[1], AQUI.parents[2] / "app"):
    sys.path.insert(0, str(p))
import sonda_t27 as t27  # noqa: E402

C = 8 << 20  # BYTES_SUBLOTE de nucleo/cena.h (vértices*28 + índices*4); nunca alterado aqui
PAREDES = ("IfcWall", "IfcWallStandardCase")
APP = []  # guarda a QApplication viva
# classes editáveis na 1.0 (lista provisória desta sonda; o líder confirma). O JSON traz TODAS as classes, esta lista só marca `editavel`.
EDITAVEIS = PAREDES + ("IfcSlab", "IfcDoor", "IfcWindow", "IfcColumn", "IfcBeam", "IfcRoof", "IfcStair", "IfcStairFlight", "IfcRailing", "IfcCovering", "IfcMember", "IfcPlate", "IfcFurnishingElement")


def motivos(l):
    """Por que o lote NÃO ladrilha, pela mesma regra de `DadosCena::preparar` (cena.cpp); lista vazia = ladrilha."""
    o, ind = l.objetos, l.indices
    if not len(o):
        return ["sem_pecas"]
    pi, ni, pv, nv = (o[k].astype(np.int64) for k in ("primeiro_indice", "n_indices", "primeiro_vertice", "n_vertices"))
    fi, fv, r = np.cumsum(ni), np.cumsum(nv), []
    ordem = np.array_equal(pi, fi - ni) and np.array_equal(pv, fv - nv)
    if not ordem:
        r.append("fora_de_ordem")
    if fi[-1] != len(ind) or fv[-1] != len(l.vertices):
        r.append("sobra")
    cheio = ni > 0
    if ordem and fi[-1] <= len(ind):  # contíguo: mínimo e máximo de cada peça de uma vez
        if cheio.any():
            mn, mx = np.minimum.reduceat(ind[:fi[-1]], pi[cheio]), np.maximum.reduceat(ind[:fi[-1]], pi[cheio])
            ruim = bool(((mn < pv[cheio]) | (mx - pv[cheio] >= nv[cheio])).any())
        else:
            ruim = False
    else:  # fora de ordem: peça a peça (caso raro)
        ruim = any((s := ind[a:a + n]).min() < v or s.max() - v >= m for a, n, v, m in zip(pi[cheio], ni[cheio], pv[cheio], nv[cheio]))
    if ruim:
        r.append("vertice_compartilhado")
    return r


def analisar(c, l, classes, ult):
    """Entrega `l` à cena e lê os sub-lotes. Devolve (registro do lote, tamanho em bytes do sub-lote de cada peça, bytes de cada peça, nova `ult`)."""
    o, mot = l.objetos, motivos(l)
    peca = o["n_vertices"].astype(np.int64) * 28 + o["n_indices"].astype(np.int64) * 4
    s = int(c.adicionar_lote(l))
    subs = [c.objetos(q) for q in range(ult + 1, s + 1)]
    bs = [int(d["n_vertices"].sum()) * 28 + int(d["n_indices"].sum()) * 4 for d in subs]
    por_peca = np.repeat(bs, [len(d["guid"]) for d in subs])
    ok = len(por_peca) == len(o) and (not mot or len(subs) == 1)  # lote que não ladrilha fica em 1 sub-lote
    reg = {"bytes": int(peca.sum()), "pecas": len(o), "ladrilha": not mot, "motivos": mot, "sublotes": len(subs), "maior_sublote": max(bs, default=0),
           "pecas_maiores_que_c": int((peca > C).sum()), "tem_parede": any(k in PAREDES for k in classes), "coerente_com_a_cena": bool(ok)}
    return reg, por_peca, peca, s


def veredito(lotes, classes_pecas):
    """Regra de decisão do cartão. `lotes`: registros; `classes_pecas`: {classe: (bytes do sub-lote por peça, bytes da peça)}."""
    def das_paredes(j):  # j = 0: bytes do sub-lote por peça; j = 1: bytes da peça
        return np.concatenate([classes_pecas[k][j] for k in PAREDES if k in classes_pecas] or [np.zeros(0, np.int64)])
    em_parede = das_paredes(0)
    parede_gigante = int((das_paredes(1) > C).sum())
    i_falha = int((em_parede > C).sum())
    caso_b = sum(1 for x in lotes if not x["ladrilha"] and x["bytes"] > C and x["tem_parede"])
    nao_lad = sum(1 for x in lotes if not x["ladrilha"] and x["tem_parede"])
    v = "T2_VALE"
    if parede_gigante:
        v = "VOLTA_AO_OPUS"  # a própria parede passa de C: não é caso da T-2
    elif caso_b:
        v = "ABRIR_CARTAO_DIVISAO_PARCIAL"
    elif i_falha:
        v = "FALHA_INESPERADA"  # (i) falhou sem parede gigante nem caso (b): não deveria acontecer; olhar os números
    return {"veredito": v, "i_paredes_em_sublote_maior_que_c": i_falha, "i_ok": i_falha == 0, "paredes_maiores_que_c": parede_gigante,
            "ii_lotes_caso_b_com_parede": caso_b, "ii_ok": caso_b == 0, "lotes_que_nao_ladrilham_com_parede_qualquer_tamanho": nao_lad}


def estatistica(arr):
    return {"pecas": len(arr), "sublote_max": int(arr.max()), "sublote_p99": float(np.percentile(arr, 99)), "em_sublote_maior_que_c": int((arr > C).sum())}


def rodar(fonte):
    """`fonte`: gera (LoteMalha, classes IFC de cada peça). Devolve o dicionário do JSON."""
    import obimcore
    from PySide6.QtWidgets import QApplication
    APP[:] = [QApplication.instance() or QApplication(sys.argv[:1])]  # a Cena exige a QApplication; sem janela
    c = obimcore.Cena(True)
    lotes, ult, acc = [], 0, {}  # acc: classe -> ([bytes do sub-lote por peça], [bytes da peça])
    for l, classes in fonte:
        reg, sub, peca, ult = analisar(c, l, classes, ult)
        lotes.append(reg)
        for k in set(classes):
            m = np.array([x == k for x in classes])
            a = acc.setdefault(k, ([], []))
            a[0].append(sub[m] if len(sub) == len(m) else np.zeros(0, np.int64))
            a[1].append(peca[m])
    acc = {k: (np.concatenate(a), np.concatenate(b)) for k, (a, b) in acc.items()}
    e = c.estatisticas()
    c.parar()
    por_classe = {k: estatistica(a) | {"editavel": k in EDITAVEIS, "pecas_maiores_que_c": int((b > C).sum())} for k, (a, b) in sorted(acc.items()) if len(a)}
    return {"versao": 1, "c_bytes": C, "arquivo_real": False, "lotes_antes": len(lotes), "lotes_depois": int(e["lotes"]),
            "sublotes_total": sum(x["sublotes"] for x in lotes), "contadores_da_cena": {k: int(e[k]) for k in ("nao_partidos", "pecas_maiores_que_c") if k in e},
            "lotes_que_nao_ladrilham": sum(not x["ladrilha"] for x in lotes), "incoerentes": sum(not x["coerente_com_a_cena"] for x in lotes),
            "pecas_maiores_que_c_por_classe": {k: v["pecas_maiores_que_c"] for k, v in por_classe.items() if v["pecas_maiores_que_c"]},
            "por_classe": por_classe, "paredes": {k: por_classe[k] for k in PAREDES if k in por_classe}, "decisao": veredito(lotes, acc), "lotes": lotes}


def fonte_ifc(caminho, resumo):
    from viewport_qrhi.carregador import CarregadorMalhas, ResumoCarga  # o carregador de hoje, sem alterar nada
    car = CarregadorMalhas(str(caminho))
    car.iniciar()
    while True:
        r = car.obter(1.0)
        if isinstance(r, ResumoCarga):
            resumo.update(estado=r.estado, produtos_total=r.produtos_total, produtos_com_malha=r.produtos_com_malha)
            return
        if r is not None:  # `_produtos`: id_step -> (guid, classe, nome, família), preenchido pelo filho antes do 1o lote
            yield r, [car._produtos.get(int(i), (None, "(desconhecida)"))[1] for i in r.objetos["id_step"]]


def fonte_sintetica(cena):
    mibs = t27.LOTES_MIB if cena == "cheia" else t27.CENA_REDUZIDA
    for i, mib in enumerate(mibs):
        gs = [f"T27PAREDE{i:02d}{k:010d}" for k in range(3)]
        l, _, _ = t27.lote_de(mib * (1 << 20), gs, f"T27F{i:02d}")
        yield l, [("IfcWall" if g.decode().startswith("T27PAREDE") else "IfcSlab") for g in l.objetos["guid"]]


def lote_manual(pecas):
    """pecas: [(classe, nv)] com ni = nv; cada peça só aponta para os próprios vértices. Devolve (lote, classes)."""
    nv = np.array([p[1] for p in pecas])
    pv = np.cumsum(nv) - nv
    v, o = np.zeros(nv.sum(), t27.DTYPE_VERTICE), np.zeros(len(pecas), t27.DTYPE_OBJETO)
    ind = np.concatenate([np.arange(m) + a for m, a in zip(nv, pv)]).astype(np.uint32)
    for j, (cl, m) in enumerate(pecas):
        o[j] = (0, f"A{j:010d}".encode(), pv[j], m, pv[j], m, [0, 0, 0], [0, 0, 0])
    return t27.LoteMalha(0, v, ind, o, np.zeros(3), len(pecas), len(pecas)), [p[0] for p in pecas]


def autoteste():
    """Casos montados à mão (peças de 3,2 MB; 5 somam 16 MB > C): a regra e os motivos saem como esperado, e a tabela da cena concorda."""
    lajes, base = [("IfcSlab", 99_999)] * 5, [("IfcSlab", 99_999)] * 5 + [("IfcWall", 30)]
    l, cl = lote_manual(base)
    ind = l.indices.copy()
    ind[l.objetos["primeiro_indice"][1]] = l.objetos["primeiro_vertice"][2]  # a peça 1 usa um vértice da 2
    comp = (replace(l, indices=ind), cl)
    l2, cl2 = lote_manual(lajes[:1] + [("IfcWall", 30)])
    ind2 = l2.indices.copy()
    ind2[0] = 100_000  # compartilhado, mas o lote cabe em C: inofensivo para a (ii)
    o = l.objetos.copy()
    o[[0, 1]] = o[[1, 0]]

    def sobra(lc):  # 9 vértices a mais, que nenhum índice usa
        lote, classes = lc
        return replace(lote, vertices=np.concatenate([lote.vertices, np.zeros(9, lote.vertices.dtype)])), classes
    casos = [("tudo_pequeno", lote_manual([("IfcWall", 30)] * 3 + [("IfcSlab", 60)]), "T2_VALE", []),
             ("ladrilha_com_parede", (l, cl), "T2_VALE", []),
             ("vertice_compartilhado_grande_com_parede", comp, "ABRIR_CARTAO_DIVISAO_PARCIAL", ["vertice_compartilhado"]),
             ("vertice_compartilhado_pequeno_com_parede", (replace(l2, indices=ind2), cl2), "T2_VALE", ["vertice_compartilhado"]),
             ("fora_de_ordem_grande_com_parede", (replace(l, objetos=o), cl), "ABRIR_CARTAO_DIVISAO_PARCIAL", ["fora_de_ordem"]),
             ("sobra_grande_sem_parede", sobra(lote_manual(lajes)), "T2_VALE", ["sobra"]),
             ("sobra_grande_com_parede", sobra((l, cl)), "ABRIR_CARTAO_DIVISAO_PARCIAL", ["sobra"]),
             ("parede_gigante", lote_manual([("IfcSlab", 99), ("IfcWall", 300_000)]), "VOLTA_AO_OPUS", []),
             ("parede_standard_gigante", lote_manual([("IfcWallStandardCase", 480_000)]), "VOLTA_AO_OPUS", [])]
    falhas = []
    for nome, (lote, classes), esperado, mot in casos:
        r = rodar([(lote, classes)])
        got = (r["decisao"]["veredito"], r["lotes"][0]["motivos"])
        if got != (esperado, mot):
            falhas.append(f"{nome}: obtido {got}, esperado {(esperado, mot)}")
        if r["incoerentes"]:
            falhas.append(f"{nome}: tabela da cena incoerente com a regra")
    print("AUTOTESTE", "FALHOU: " + "; ".join(falhas) if falhas else f"OK ({len(casos)} casos)")
    return not falhas


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="modo", required=True)
    i = sub.add_parser("ifc")
    i.add_argument("arquivo")
    s = sub.add_parser("sintetica")
    s.add_argument("--cena", choices=("cheia", "reduzida"), default="reduzida")
    sub.add_parser("autoteste")
    for x in (i, s):
        x.add_argument("--saida")
    a = ap.parse_args()
    if a.modo == "autoteste":
        sys.exit(0 if autoteste() else 1)
    resumo = {}
    saida = rodar(fonte_ifc(a.arquivo, resumo) if a.modo == "ifc" else fonte_sintetica(a.cena))
    saida["arquivo_real"], saida["carga"] = a.modo == "ifc", resumo
    texto = json.dumps(saida, ensure_ascii=False, indent=1)
    if a.saida:
        p = Path(a.saida).resolve()
        if AQUI.parents[2] in p.parents:
            sys.exit("a saída da sonda tem de ficar fora do repositório")
        p.write_text(texto, encoding="utf-8")
        print(json.dumps({k: saida[k] for k in ("lotes_antes", "lotes_depois", "lotes_que_nao_ladrilham", "paredes", "decisao")}, ensure_ascii=False, indent=1))
    else:
        print(texto)
