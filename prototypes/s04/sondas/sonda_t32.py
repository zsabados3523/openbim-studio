# SPDX-License-Identifier: AGPL-3.0-or-later
"""Sonda da F0-S04-T32a (G-0b, lote Opus 59 §3): instrumentação do envio à placa e tempo de `atualizar`. RAMO DESCARTÁVEL, tela virtual, cena SINTÉTICA do T27.
Usa o anel por quadro que o C++ do ramo descartável expõe (`Cena.registros(desde)`: colunas por quadro, mais "proximo") e mede, por troca de parede:
bytes e pedaços enviados por fase, número e tempo de create(), motivo da parada do `enviar`, geração e versão vistas, sequência e triângulos na placa,
chamadas de desenho, e o tempo da chamada `atualizar` (Python, relógio monotônico). Dois modos, escolhidos pela variável OBIM_SEM_CONSERTADO que o
`rodar_t32.sh` põe: `hoje` (o `sem` de hoje) e `consertado` (reserva exata, cópia de trechos contínuos, `morto` só no lote tocado; só no ramo).
Também compara `bytes_copia` medido com o previsto pela capacidade dos vetores (modelo em `Modelo`).
Os milissegundos de software NÃO valem como os da placa; o que se lê são contadores, bytes e o tempo de CPU de `atualizar` desta máquina.
Uso: sonda_t32.py rodada --modo hoje|consertado --saida ARQ.json [--paredes 3] [--limite-ms 240000]
     sonda_t32.py agregar PASTA
"""
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
sys.path.insert(0, str(AQUI))
import sonda_t27 as t27  # noqa: E402  (reaproveita a cena sintética do T27 sem editá-la; ajusta o sys.path do projeto)

LOTE_V, LOTE_I = 28, 4
SIZEOF_OBJETO = 80  # int32 + std::string (32) + 4 x uint32 + 6 x float, com alinhamento de 8 (GCC, 64 bits)
CAP_GUID = 31       # guid de 22 caracteres: capacidade 30 + 1 (cena.cpp totais); preparar e a cópia de `sem` dão o mesmo
CAMPOS_QUADRO = ["idx", "ms_apos_comando", "bytes_v", "bytes_i", "ped_v", "ped_i", "n_create", "t_create_ms", "motivo", "ger", "ver", "seq_placa", "tri_placa", "chamadas", "t_env_ms"]
COLS = ["idx", "t_env_ini", "t_env_fim", "t_apres", "bytes_v", "bytes_i", "ped_v", "ped_i", "n_create", "t_create_ms", "motivo", "ger", "ver", "seq_placa", "tri_placa", "chamadas"]


def pot2(n):
    return 0 if n <= 0 else 1 << (n - 1).bit_length()


class Modelo:
    """Capacidade prevista dos vetores de cada lote (bytes_copia = soma de capacidades; cena.cpp totais()). `hoje`: o `sem` não reserva e o GCC dobra a
    capacidade (vértices 28 x 2^n, índices e objetos 2^n); `consertado`: reserva exata. Lotes que vêm de `preparar` têm vértices e índices exatos."""

    def __init__(self, modo):
        self.modo, self.lotes = modo, []

    def novo(self, lote):  # lote vindo de preparar()
        no = len(lote.objetos)
        self.lotes.append({"nv": len(lote.vertices), "ni": len(lote.indices), "no": no, "vcap": LOTE_V * len(lote.vertices), "icap": len(lote.indices),
                           "ocap": pot2(no), "guids": {o.decode("ascii") for o in lote.objetos["guid"]}})

    def tocar(self, guid):  # `sem`: remove a parede `guid` (PAREDE_TRI*3 vértices e índices) do lote que a tem
        for L in self.lotes:
            if guid in L["guids"]:
                L["guids"].discard(guid)
                L["nv"] -= 3 * t27.PAREDE_TRI; L["ni"] -= 3 * t27.PAREDE_TRI; L["no"] -= 1
                if self.modo == "hoje":
                    L["vcap"], L["icap"], L["ocap"] = LOTE_V * pot2(L["nv"]), pot2(L["ni"]), pot2(L["no"])
                else:
                    L["vcap"], L["icap"], L["ocap"] = LOTE_V * L["nv"], L["ni"], L["no"]
                return
        raise KeyError(guid)

    def bytes(self):
        return sum(L["vcap"] + L["icap"] * LOTE_I + L["ocap"] * SIZEOF_OBJETO + L["no"] * CAP_GUID for L in self.lotes)

    def componentes(self):
        return {"vertices": sum(L["vcap"] for L in self.lotes), "indices": sum(L["icap"] * LOTE_I for L in self.lotes),
                "objetos": sum(L["ocap"] * SIZEOF_OBJETO + L["no"] * CAP_GUID for L in self.lotes)}


def operar(f, c, obimcore, agir, limite_ms):
    """Roda um comando e lê o anel até a sequência chegar à placa. Devolve o dicionário do evento (campos documentados no relatório)."""
    est0 = c.estatisticas()
    r0 = c.registros(10 ** 12)  # só para saber o índice do próximo registro
    prox = int(r0["proximo"])
    ant = c.registros(max(prox - 1, 0))
    ger_antes = int(ant["ger"][-1]) if ant["ger"] else None
    ver_antes = int(ant["ver"][-1]) if ant["ver"] else None
    t_a = obimcore.agora()
    p0 = time.perf_counter()
    seq = int(agir())
    atualizar_ms = (time.perf_counter() - p0) * 1000.0
    t_cmd = obimcore.agora()
    col = {k: [] for k in COLS}
    atual, fim = prox, f._relogio() + limite_ms
    corte = None
    while corte is None:
        r = c.registros(atual)
        atual = int(r["proximo"])
        for k in COLS:
            col[k] += r[k]
        for j, s in enumerate(col["seq_placa"]):
            if s >= seq:
                corte = j + 1
                break
        if corte is None:
            if f._relogio() > fim:
                raise TimeoutError(f"sem quadro com a sequência {seq} em {limite_ms} ms")
            f._bombear(lambda: False, 2)
    col = {k: v[:corte] for k, v in col.items()}
    est1 = c.estatisticas()
    n = corte
    depois = [j for j in range(n) if col["t_apres"][j] > t_cmd]
    q = [[int(col["idx"][j]), round(col["t_apres"][j] - t_cmd, 3), int(col["bytes_v"][j]), int(col["bytes_i"][j]), int(col["ped_v"][j]), int(col["ped_i"][j]),
          int(col["n_create"][j]), round(col["t_create_ms"][j], 4), int(col["motivo"][j]), int(col["ger"][j]), int(col["ver"][j]), int(col["seq_placa"][j]),
          int(col["tri_placa"][j]), int(col["chamadas"][j]), round(col["t_env_fim"][j] - col["t_env_ini"][j], 4)] for j in range(n)]
    bv, bi = sum(col["bytes_v"]), sum(col["bytes_i"])
    vi = 28 * int(est1["vertices"]) + 12 * int(est1["triangulos"])
    ped = [col["ped_v"][j] + col["ped_i"][j] for j in depois]
    jmax = int(np.argmax(ped)) if ped else None
    primeiro = depois[0] if depois else None
    return {"seq": seq, "atualizar_ms": atualizar_ms, "ger_antes": ger_antes, "ver_antes": ver_antes, "ger_depois": int(col["ger"][-1]), "ver_depois": int(col["ver"][-1]),
            "quadros_janela": n, "quadros_depois": len(depois),
            "bytes_v": int(bv), "bytes_i": int(bi), "bytes_enviados": int(bv + bi), "cena_vi_depois": vi, "bytes_igual_cena": bool(bv + bi == vi),
            "primeiro_quadro_bytes": int(col["bytes_v"][primeiro] + col["bytes_i"][primeiro]) if primeiro is not None else None,
            "primeiro_quadro_ms_apos": round(col["t_apres"][primeiro] - t_cmd, 3) if primeiro is not None else None,
            "ped_v_total": int(sum(col["ped_v"])), "ped_i_total": int(sum(col["ped_i"])),
            "quadro_max_ped": ({"pos_entre_contados": jmax, "de": len(depois), "ped": int(ped[jmax]), "ped_v": int(col["ped_v"][depois[jmax]]), "ped_i": int(col["ped_i"][depois[jmax]]),
                                "n_create": int(col["n_create"][depois[jmax]]), "motivo": int(col["motivo"][depois[jmax]])} if ped else None),
            "n_create_total": int(sum(col["n_create"])), "t_create_ms_total": float(sum(col["t_create_ms"])), "t_create_ms_max": float(max(col["t_create_ms"])),
            "quadros_com_create": int(sum(1 for x in col["n_create"] if x > 0)),
            "motivos": {str(m): int(sum(1 for j in depois if col["motivo"][j] == m)) for m in (0, 1, 2, 3, 4)},
            "tri_placa_min": int(min(col["tri_placa"][j] for j in depois)) if depois else None, "chamadas_max": int(max(col["chamadas"])),
            "bytes_copia_antes": int(est0["bytes_copia"]), "bytes_copia_depois": int(est1["bytes_copia"]), "lotes_antes": int(est0["lotes"]), "lotes_depois": int(est1["lotes"]),
            "triangulos_antes": int(est0["triangulos"]), "triangulos_depois": int(est1["triangulos"]), "contextos_delta": int(est1["contextos"] - est0["contextos"]),
            "quadros": q}


def rodada(a):
    import fluxo_a
    import obimcore
    mibs, idx_tocados = t27.LOTES_MIB, dict(t27.TOCADOS)
    modo = a.modo
    saida = {"versao": 1, "rotulo": "t32a", "modo": modo, "sem_consertado_env": os.environ.get("OBIM_SEM_CONSERTADO"), "paredes": a.paredes, "arquivo_real": False, "casos": {},
             "campos_quadro": CAMPOS_QUADRO, "erro": None, "orcamento_bytes": t27.ORCAMENTO, "carga_antes": list(os.getloadavg()),
             "uptime_s": float(Path("/proc/uptime").read_text().split()[0])}
    passo, tmp, n = "abrir_janela", tempfile.mkdtemp(dir=os.environ.get("TMPDIR")), 0
    mod = Modelo(modo)
    try:
        f = fluxo_a.FluxoA(None, janela=True, saida=Path(tmp) / "saida")
        c = f.cena
        saida["desenho"] = {"info": str(c.info()), "software": bool(c.desenho_por_software())}
        gs_parede, tri_lote = {}, {}
        for i, mib in enumerate(mibs):
            gs = [f"T27PAREDE{n + k:013d}" for k in range(a.paredes)] if i in idx_tocados.values() else []
            n += len(gs)
            lote, nb, tri = t27.lote_de(mib * (1 << 20), gs, f"T27FILLER{i:013d}")
            c.adicionar_lote(lote)
            mod.novo(lote)
            if gs:
                gs_parede[i], tri_lote[i] = list(gs), tri
            saida.setdefault("lotes_bytes", []).append(nb)
        passo = "assentar"
        fim = f._relogio() + 300000
        while f._relogio() < fim:
            f._bombear(lambda: False, 100)
            e = c.estatisticas()
            if int(e["triangulos_na_placa"]) >= int(e["triangulos"]):
                break
        f._bombear(lambda: False, 300)
        e = c.estatisticas()
        saida["cena_antes"] = {k: int(e[k]) for k in ("triangulos", "vertices", "lotes", "bytes_copia", "fatias_enviadas", "triangulos_na_placa")}
        saida["cena_bytes_vi"] = int(sum(saida["lotes_bytes"]))
        saida["modelo_antes"] = {"previsto": mod.bytes(), "medido": int(e["bytes_copia"]), "componentes": mod.componentes()}
        casos = saida["casos"]

        def registrar(caso, ev, extra):
            ev.update(extra)
            ev["modelo_bytes_copia_depois"] = mod.bytes()
            ev["modelo_componentes_depois"] = mod.componentes()
            casos.setdefault(caso, []).append(ev)
            f._bombear(lambda: False, 150)

        passo = "criar"
        criadas = []
        for k in range(a.paredes):
            g = f"T27CRIADA{n + k:013d}"
            lote, _, tri = t27.lote_de(t27.PAREDE_BYTES, [g])
            ev = operar(f, c, obimcore, lambda l=lote: c.atualizar(l, []), a.limite_ms)
            mod.novo(lote)
            registrar("criar_1KB", ev, {"bytes_lote_tocado": t27.PAREDE_BYTES, "guids": [g]})
            criadas.append(g)
        n += len(criadas)
        passo = "troca_1KB"
        for k, g in enumerate(criadas):
            gn = f"T27TROCA{n + k:013d}"
            lote, _, _ = t27.lote_de(t27.PAREDE_BYTES, [gn])
            ev = operar(f, c, obimcore, lambda l=lote, o=g: c.atualizar(l, [o]), a.limite_ms)
            mod.tocar(g); mod.novo(lote)
            registrar("troca_1KB", ev, {"bytes_lote_tocado": t27.PAREDE_BYTES, "guids": [gn]})
        n += len(criadas)
        for nome, idx in idx_tocados.items():
            passo = "troca_" + nome
            for k, g in enumerate(gs_parede[idx]):
                gn = f"T27TROCA{n + k:013d}"
                lote, _, _ = t27.lote_de(t27.PAREDE_BYTES, [gn])
                ev = operar(f, c, obimcore, lambda l=lote, o=g: c.atualizar(l, [o]), a.limite_ms)
                mod.tocar(g); mod.novo(lote)
                registrar("troca_" + nome, ev, {"bytes_lote_tocado": saida["lotes_bytes"][idx], "guids": [gn]})
            n += len(gs_parede[idx])
        e = c.estatisticas()
        saida["cena_depois"] = {k: int(e[k]) for k in ("triangulos", "vertices", "lotes", "bytes_copia", "fatias_enviadas", "triangulos_na_placa")}
        saida["modelo_depois"] = {"previsto": mod.bytes(), "medido": int(e["bytes_copia"]), "componentes": mod.componentes()}
        saida["subida_medida"] = saida["modelo_depois"]["medido"] - saida["modelo_antes"]["medido"]
        saida["subida_prevista"] = saida["modelo_depois"]["previsto"] - saida["modelo_antes"]["previsto"]
    except BaseException as exc:
        saida["erro"] = {"classe": type(exc).__name__, "mensagem": str(exc)[:300], "passo": passo, "funcoes": [x.name for x in traceback.extract_tb(exc.__traceback__)][-6:]}
    saida["carga_depois"] = list(os.getloadavg())
    saida["uptime_fim_s"] = float(Path("/proc/uptime").read_text().split()[0])
    Path(a.saida).write_text(json.dumps(saida, ensure_ascii=False), encoding="utf-8")
    shutil.rmtree(tmp, ignore_errors=True)
    sys.stdout.flush()
    os._exit(0)


def med(v):
    return float(np.median(v)) if len(v) else None


def agregar(pasta):
    """Resume os t32_<modo>_r<N>.json da pasta. Saída: campos por modo e por caso (ver o relatório)."""
    out = {"modos": {}}
    for modo in ("hoje", "consertado"):
        arqs = sorted(Path(pasta).glob(f"t32_{modo}_r*.json"))
        rs = [json.loads(p.read_text()) for p in arqs]
        ok = [x for x in rs if not x["erro"]]
        for r in ok:  # variação de bytes_copia por evento: medida (estatisticas) e prevista (modelo), na ordem em que os eventos aconteceram
            ant = r["modelo_antes"]["previsto"]
            for evs in r["casos"].values():
                for q in evs:
                    q["delta_medido"] = q["bytes_copia_depois"] - q["bytes_copia_antes"]
                    q["delta_previsto"] = q["modelo_bytes_copia_depois"] - ant
                    ant = q["modelo_bytes_copia_depois"]
        m = {"rodadas": len(rs), "ok": len(ok), "erros": [x["erro"] for x in rs if x["erro"]], "uptime": {p.stem: (p.with_suffix(".uptime").read_text().strip() if p.with_suffix(".uptime").exists() else None) for p in arqs},
             "carga": [[x["carga_antes"][0], x["carga_depois"][0]] for x in ok], "desenho_software": [x["desenho"]["software"] for x in ok], "casos": {}}
        trocas = [(r, nome, ev) for r in ok for nome, evs in r["casos"].items() if nome.startswith("troca_") for ev in evs]
        m["criterio1"] = {"trocas": len(trocas), "bytes_igual_cena": sum(ev["bytes_igual_cena"] for _, _, ev in trocas),
                          "dif_bytes": [ev["bytes_enviados"] - ev["cena_vi_depois"] for _, _, ev in trocas if not ev["bytes_igual_cena"]]}
        m["criterio2"] = {"trocas": len(trocas), "primeiro_quadro_zero": sum(ev["primeiro_quadro_bytes"] == 0 for _, _, ev in trocas),
                          "trocas_com_404": sum(ev["quadros_depois"] == 404 for _, _, ev in trocas), "trocas_com_403": sum(ev["quadros_depois"] == 403 for _, _, ev in trocas),
                          "primeiro_zero_entre_404": sum(ev["quadros_depois"] == 404 and ev["primeiro_quadro_bytes"] == 0 for _, _, ev in trocas),
                          "primeiro_zero_entre_403": sum(ev["quadros_depois"] == 403 and ev["primeiro_quadro_bytes"] == 0 for _, _, ev in trocas),
                          "outros_quadros": sorted({ev["quadros_depois"] for _, _, ev in trocas if ev["quadros_depois"] not in (403, 404)})}
        cr = [ev for r in ok for ev in r["casos"].get("criar_1KB", [])]
        m["criar"] = {"eventos": len(cr), "quadros_depois": [ev["quadros_depois"] for ev in cr], "bytes_enviados": [ev["bytes_enviados"] for ev in cr],
                      "primeiro_quadro_bytes": [ev["primeiro_quadro_bytes"] for ev in cr]}
        m["criterio4"] = [{"rodada": i, "subida_medida": r["subida_medida"], "subida_prevista": r["subida_prevista"], "residuo": r["subida_medida"] - r["subida_prevista"],
                           "antes": r["modelo_antes"], "depois": r["modelo_depois"]} for i, r in enumerate(ok)]
        for caso in sorted({k for x in ok for k in x["casos"]}):
            ev = [q for x in ok for q in x["casos"].get(caso, [])]
            at = [q["atualizar_ms"] for q in ev]
            fp = [[q["quadros"][j][4] + q["quadros"][j][5] for j in range(len(q["quadros"])) if q["quadros"][j][1] > 0] for q in ev]
            qm = [q["quadro_max_ped"] for q in ev if q["quadro_max_ped"]]
            m["casos"][caso] = {
                "eventos": len(ev), "atualizar_ms": {"n": len(at), "mediana": med(at), "pior": max(at), "menor": min(at), "valores": at},
                "quadros_depois": {"mediana": med([q["quadros_depois"] for q in ev]), "menor": min(q["quadros_depois"] for q in ev), "maior": max(q["quadros_depois"] for q in ev)},
                "bytes_enviados": {"mediana": med([q["bytes_enviados"] for q in ev]), "cena_vi_mediana": med([q["cena_vi_depois"] for q in ev]), "iguais": sum(q["bytes_igual_cena"] for q in ev)},
                "ped_v_total_mediana": med([q["ped_v_total"] for q in ev]), "ped_i_total_mediana": med([q["ped_i_total"] for q in ev]),
                "ped_por_quadro_maior": max((max(x) for x in fp if x), default=None),
                "quadro_max_ped": {"pos_ultimos_10_de_contados": sum(1 for x in qm if x["pos_entre_contados"] >= x["de"] - 10), "eventos": len(qm), "n_create_medio": med([x["n_create"] for x in qm]),
                                   "ped_mediana": med([x["ped"] for x in qm]), "pos_mediana": med([x["pos_entre_contados"] for x in qm]), "de_mediana": med([x["de"] for x in qm])},
                "create": {"n_total_mediana": med([q["n_create_total"] for q in ev]), "t_total_ms_mediana": med([q["t_create_ms_total"] for q in ev]),
                           "t_total_ms_pior": max(q["t_create_ms_total"] for q in ev), "t_max_por_quadro_ms_pior": max(q["t_create_ms_max"] for q in ev),
                           "quadros_com_create_mediana": med([q["quadros_com_create"] for q in ev])},
                "motivos_mediana": {k: med([q["motivos"][k] for q in ev]) for k in ("0", "1", "2", "3", "4")},
                "ger_subiu": sum(q["ger_depois"] > (q["ger_antes"] if q["ger_antes"] is not None else q["ger_depois"]) for q in ev),
                "tri_placa_min_mediana": med([q["tri_placa_min"] for q in ev if q["tri_placa_min"] is not None]), "chamadas_max": max(q["chamadas_max"] for q in ev),
                "delta_bytes_copia": {"medido": [q["delta_medido"] for q in ev], "previsto": [q["delta_previsto"] for q in ev],
                                      "iguais": sum(q["delta_medido"] == q["delta_previsto"] for q in ev)},
                "contextos_delta_maior": max(q["contextos_delta"] for q in ev)}
        out["modos"][modo] = m
    h, c = out["modos"]["hoje"]["casos"], out["modos"]["consertado"]["casos"]
    out["consertado_285MiB_mediana_ms"] = c.get("troca_285MiB", {}).get("atualizar_ms", {}).get("mediana")
    out["consertado_285MiB_pior_ms"] = c.get("troca_285MiB", {}).get("atualizar_ms", {}).get("pior")
    out["consertado_285MiB_passa_de_100ms"] = bool(out["consertado_285MiB_mediana_ms"] is not None and out["consertado_285MiB_mediana_ms"] > 100)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="modo_cmd", required=True)
    r = sub.add_parser("rodada")
    r.add_argument("--modo", choices=("hoje", "consertado"), required=True)
    r.add_argument("--saida", required=True)
    r.add_argument("--paredes", type=int, default=3)
    r.add_argument("--limite-ms", type=int, default=240000)
    ag = sub.add_parser("agregar")
    ag.add_argument("pasta")
    a = ap.parse_args()
    if a.modo_cmd == "rodada":
        p = Path(a.saida).resolve()
        if AQUI.parents[2] in p.parents:
            sys.exit("a saída da sonda tem de ficar fora do repositório")
        if (os.environ.get("OBIM_SEM_CONSERTADO") == "1") != (a.modo == "consertado"):
            sys.exit("OBIM_SEM_CONSERTADO tem de ser 1 no modo consertado e vazio no modo hoje")
        import faulthandler
        faulthandler.dump_traceback_later(int(os.environ.get("OBIM_LIMITE", 3600)) - 20, exit=True)
        rodada(a)
    else:
        print(json.dumps(agregar(a.pasta), ensure_ascii=False, indent=1))
