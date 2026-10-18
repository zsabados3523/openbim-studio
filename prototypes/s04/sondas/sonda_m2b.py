# SPDX-License-Identifier: AGPL-3.0-or-later
"""Sonda da F0-S04-T22: onde o tempo do M2b (trocar a geometria de uma parede) vai, por fase, em IFC real.
Só ENVOLVE o fluxo A (troca métodos e funções no processo; não edita fluxo_a.py, lote.py nem o núcleo). Uma execução = uma rodada, em processo próprio.
Fica em sondas/ (e não em fluxo_a/) para não entrar na contagem de linhas do M7. Fases (mesmo relógio do núcleo): comando (API do ifcopenshell, com um item por caso de uso), commit, malha (obimcore.malhas), montagem (LoteMalha), atualizar (Cena.atualizar), quadro
(da volta do comando até o quadro apresentado), outros (o resto de ms_total). O JSON só leva números e o rótulo de tamanho: nada de nome de arquivo, GlobalId ou texto de erro.
Uso: sonda_m2b.py rodada (--ifc ARQ | --sintetica N) --rotulo R --saida ARQ.json [--trocas 30] [--criar 200] [--perfil ARQ.json] [--exigir-placa]
     sonda_m2b.py agregar PASTA ROTULO[,ROTULO...]   (lê PASTA/ROTULO_r*.json; tabela por fase: mediana das rodadas e pior valor)"""
import argparse
import cProfile
import json
import os
import pstats
import shutil
import sys
import tempfile
import time
import traceback
from collections import defaultdict
from pathlib import Path

import numpy as np

AQUI = Path(__file__).resolve().parent
for p in (AQUI.parent / "fluxo_a", AQUI.parents[2] / "scripts", AQUI.parents[1], AQUI.parents[2] / "app"):  # só a pasta do fluxo A (não prototypes/s04: `fluxo_a/` viraria pacote)
    sys.path.insert(0, str(p))
ROTULOS = ("sint3000", "sint42k", "m25", "m25perfil", "det")  # sintética 3.000, sintética 41.600, 25 MB (sem e com perfil), detalhado
FASES = ("comando", "commit", "malha", "montagem", "atualizar", "quadro", "outros")
TIPO = {"cmd": "criar_tipo", "nome": "PAR15", "camadas_m": [0.02, 0.11, 0.02]}
PAREDE = {"cmd": "criar_parede", "tipo": "PAR15", "comprimento": 4.0, "altura": 2.8, "espessura": 0.15}


class CenaCron:  # intermediário da Cena: cronometra `atualizar` e repassa o resto
    def __init__(self, cena, soma, rel):
        self._c, self._s, self._r = cena, soma, rel

    def atualizar(self, *a):
        t = self._r()
        try:
            return self._c.atualizar(*a)
        finally:
            self._s["atualizar"] += self._r() - t

    def __getattr__(self, nome):
        return getattr(self._c, nome)


def cronometrar(soma, chave, fn, rel):
    def f(*a, **k):
        t = rel()
        try:
            return fn(*a, **k)
        finally:
            soma[chave] += rel() - t
    return f


def instalar(f, soma):  # só durante a sonda; tudo cronometrado com o relógio do núcleo (f._relogio)
    import fluxo_a
    import obimcore
    rel = f._relogio
    api0, mal0 = fluxo_a.api, obimcore.malhas
    fluxo_a.api = lambda nome, *a, **k: cronometrar(soma, "api:" + nome, api0, rel)(nome, *a, **k)

    def malhas(*a, **k):
        t = rel()
        try:
            r = mal0(*a, **k)
            soma["tri_malha"] += sum(len(v["indices"]) for v in r.values())
            return r
        finally:
            soma["malha"] += rel() - t
    obimcore.malhas = malhas
    f._lote = cronometrar(soma, "lote", f._lote, rel)
    for c in ("criar_parede", "mudar_comprimento"):
        setattr(f, "_c_" + c, cronometrar(soma, "comando", getattr(f, "_c_" + c), rel))
    for m in ("begin_transaction", "end_transaction"):
        setattr(f.ifc, m, cronometrar(soma, "commit", getattr(f.ifc, m), rel))
    f.cena = CenaCron(f.cena, soma, rel)


def executar(f, cmd, soma, perfis=None):  # um comando + espera do quadro, como o `executar_roteiro`; devolve o registro das fases
    soma.clear()
    pc, pq = perfis or (None, None)
    fatias0 = f.cena.estatisticas()["fatias_enviadas"]
    pc and pc.enable()
    try:
        guids, u = f.executar_detalhado(cmd)
    finally:
        pc and pc.disable()
    seq, tq = u["sequencia"], u["t_comando_ms"]
    if seq is not None and (u["geometria"] or u["apagados"]):
        pq and pq.enable()
        try:
            tq = f._quadro(seq, u["t0_ms"], u["t_comando_ms"])  # limite padrão de 10 s: nunca alterado
        finally:
            pq and pq.disable()
    total, quadro = tq - u["t0_ms"], tq - u["t_comando_ms"]
    rel = [(t, s) for t, s in f.cena.relogio() if u["t0_ms"] <= t <= tq]
    r = {"ms_total": total, "comando": soma["comando"], "commit": soma["commit"], "malha": soma["malha"], "montagem": soma["lote"] - soma["malha"], "atualizar": soma["atualizar"], "quadro": quadro,
         "api": {k[4:]: v for k, v in soma.items() if k.startswith("api:")}, "triangulos_malha": int(soma["tri_malha"]), "quadros": len(rel), "fatias": int(f.cena.estatisticas()["fatias_enviadas"] - fatias0), "sequencia_caiu": any(b < a for (_, a), (_, b) in zip(rel, rel[1:]))}
    r["outros"] = total - sum(r[k] for k in FASES if k != "outros")
    f._bombear()
    return r, guids


def estatisticas(f):
    e = f.cena.estatisticas()
    return {k: int(e[k]) for k in ("triangulos", "vertices", "lotes", "bytes_copia", "fatias_enviadas", "triangulos_na_placa")}


def perfil_top(pr, n, rep):  # função, chamadas, ms próprios e ms acumulados por troca; só nome do módulo e da função (sem caminho)
    st = pstats.Stats(pr)
    curto = lambda a: a[2] if a[0] in ("~", "") else (Path(a[0]).stem + ":" + a[2])  # noqa: E731
    linhas = [(curto(k), v[0], v[2] * 1000 / rep, v[3] * 1000 / rep) for k, v in st.stats.items()]
    return [{"funcao": a, "chamadas_por_troca": c / rep, "proprio_ms": round(p, 3), "acumulado_ms": round(ac, 3)} for a, c, p, ac in sorted(linhas, key=lambda x: -x[2])[:n]]


def rodada(a):
    import ifcopenshell  # noqa: F401  (antes do obimcore)
    import fluxo_a
    saida = {"versao": 1, "rotulo": a.rotulo, "trocas": a.trocas, "criar": a.criar, "criar_reps": [], "trocar_reps": [], "erro": None}
    passo = "abrir_ifc"
    tmp = tempfile.mkdtemp(dir=os.environ.get("TMPDIR"))  # IFC sintético e pasta de saída do fluxo: apagados no fim
    try:
        if a.sintetica:
            import gerar_modelo_grande
            ifc = str(Path(tmp) / f"base{a.sintetica}.ifc")
            gerar_modelo_grande.gerar(ifc, paredes=a.sintetica)
        else:
            ifc = a.ifc
        t = time.perf_counter()
        f = fluxo_a.FluxoA(ifc, janela=True, saida=Path(tmp) / "saida")
        saida["abrir_ifc_s"] = time.perf_counter() - t
        saida["desenho"] = {"info": str(f.cena.info()), "software": bool(f.cena.desenho_por_software())}  # prova de qual desenho esta rodada usou
        if a.exigir_placa and saida["desenho"]["software"]:
            raise RuntimeError("desenho por software")
        if f.ifc.schema != "IFC4":
            raise ValueError("esquema")
        saida["modelo"] = {"esquema": f.ifc.schema, "produtos_com_geometria": sum(1 for p in f.ifc.by_type("IfcProduct") if p.Representation), "relacoes": len(f.ifc.by_type("IfcRelationship")),
                           "objetos": len(f.ifc.by_type("IfcRoot")), "entidades": sum(1 for _ in f.ifc)}
        soma = defaultdict(float)
        instalar(f, soma)
        passo = "abrir"
        ti = f._relogio()
        _, u = f.executar_detalhado({"cmd": "abrir"})
        saida["abrir_ms"] = f._quadro(u["sequencia"], u["t0_ms"], u["t_comando_ms"]) - ti if u["sequencia"] is not None else None
        saida["cena_depois_de_abrir"] = estatisticas(f)
        f.executar(TIPO)
        passo = "criar_parede"
        guids = []
        for _ in range(a.criar):
            r, g = executar(f, PAREDE, soma)
            saida["criar_reps"].append(r)
            guids += g
        f.executar({"cmd": "enquadrar"})
        f._bombear(lambda: False, 500)
        saida["cena_antes_das_trocas"] = estatisticas(f)
        passo = "mudar_comprimento"
        perfis = (cProfile.Profile(), cProfile.Profile()) if a.perfil else None
        for g in guids[:a.trocas]:
            saida["trocar_reps"].append(executar(f, {"cmd": "mudar_comprimento", "alvo": g, "comprimento": 5.0}, soma, perfis)[0])
        saida["cena_depois_das_trocas"] = estatisticas(f)
        passo = "orbita"
        f.executar({"cmd": "animar_orbita", "graus_por_s": 30})
        f._bombear(lambda: False, 1500)
        f.executar({"cmd": "parar_animacao"})
        ts = np.diff([t for t, _ in f.cena.relogio()][-45:])  # controle: intervalo entre quadros com a cena girando (custo do desenho em software)
        saida["orbita"] = {"intervalos": len(ts), "mediana_ms": float(np.median(ts)) if len(ts) else None, "maior_ms": float(ts.max()) if len(ts) else None}
        if perfis:
            n = max(1, len(saida["trocar_reps"]))
            Path(a.perfil).write_text(json.dumps({"rotulo": a.rotulo, "trocas": n, "comando": perfil_top(perfis[0], 10, n), "espera_do_quadro": perfil_top(perfis[1], 10, n)}, ensure_ascii=False, indent=1), encoding="utf-8")
    except BaseException as e:  # só a classe, o passo e os nomes das funções da pilha: a mensagem pode ter dado do modelo
        saida["erro"] = {"classe": type(e).__name__, "passo": passo, "funcoes": [x.name for x in traceback.extract_tb(e.__traceback__)][-6:]}
    Path(a.saida).write_text(json.dumps(saida, ensure_ascii=False, indent=1), encoding="utf-8")
    shutil.rmtree(tmp, ignore_errors=True)
    sys.stdout.flush()
    os._exit(0)  # sem desmontar o Qt nem o modelo grande


def agregar(pasta, rotulos):
    por = {}
    for r in rotulos:
        rs = [json.loads(p.read_text()) for p in sorted(Path(pasta).glob(f"{r}_r*.json"))]
        if not rs or any(x["erro"] for x in rs):
            por[r] = {"erro": [x["erro"] for x in rs] or "sem rodadas"}
            continue
        d = {"rodadas": len(rs), "trocas_por_rodada": [len(x["trocar_reps"]) for x in rs], "modelo": rs[0]["modelo"], "cena_antes_das_trocas": rs[0]["cena_antes_das_trocas"], "orbita_mediana_ms": [x["orbita"]["mediana_ms"] for x in rs],
             "fatias_previstas_por_orcamento_de_2_MiB": rs[0]["cena_antes_das_trocas"]["bytes_copia"] / (2 << 20)}  # ORCAMENTO_BYTES de nucleo/motor.h: lido, não alterado
        for grupo in ("criar_reps", "trocar_reps"):
            d[grupo] = {}
            for fase in ("ms_total", *FASES):
                med = [float(np.median([q[fase] for q in x[grupo]])) for x in rs]
                d[grupo][fase] = {"mediana_das_rodadas": float(np.median(med)), "medianas": med, "pior": max(q[fase] for x in rs for q in x[grupo])}
            apis = sorted({k for x in rs for q in x[grupo] for k in q["api"]})
            d[grupo]["api"] = {k: float(np.median([float(np.median([q["api"].get(k, 0.0) for q in x[grupo]])) for x in rs])) for k in apis}
            d[grupo]["triangulos_malha"] = rs[0][grupo][0]["triangulos_malha"]
            d[grupo]["quadros_por_comando_mediana"] = float(np.median([q["quadros"] for x in rs for q in x[grupo]]))
            d[grupo]["fatias_por_comando_mediana"] = float(np.median([q["fatias"] for x in rs for q in x[grupo]]))
            d[grupo]["sequencia_caiu"] = sum(bool(q["sequencia_caiu"]) for x in rs for q in x[grupo])
        por[r] = d
    return por


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="modo", required=True)
    r = sub.add_parser("rodada")
    g = r.add_mutually_exclusive_group(required=True)
    g.add_argument("--ifc")
    g.add_argument("--sintetica", type=int)
    r.add_argument("--rotulo", required=True, choices=ROTULOS)  # só rótulos de tamanho: nunca nome de arquivo
    r.add_argument("--saida", required=True)
    r.add_argument("--trocas", type=int, default=30)
    r.add_argument("--criar", type=int, default=200)
    r.add_argument("--perfil")
    r.add_argument("--exigir-placa", action="store_true", help="para a rodada se o desenho for por software")
    ag = sub.add_parser("agregar")
    ag.add_argument("pasta")
    ag.add_argument("rotulos")
    a = ap.parse_args()
    if a.modo == "rodada":
        import faulthandler
        faulthandler.dump_traceback_later(int(os.environ.get("OBIM_LIMITE", 3600)) - 20, exit=True)
        rodada(a)
    else:
        print(json.dumps(agregar(a.pasta, a.rotulos.split(",")), ensure_ascii=False, indent=1))
