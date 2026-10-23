# SPDX-License-Identifier: AGPL-3.0-or-later
"""F0-S05-T02: sondas do ifcopenshell para o oplog (só números; nada de produto).
Uso: python sondas_ifcopenshell.py {ids|custo|tempo|fsync|registro} --saida X.json [--ifc A.ifc]
Cada subcomando mede uma coisa do cartão e grava um JSON bruto (fica fora do repositório)."""
import argparse
import gc
import hashlib
import json
import os
import platform
import shutil
import statistics as st
import sys
import tempfile
import time
import tracemalloc
import weakref
from collections import Counter

import ifcopenshell
import ifcopenshell.api
import numpy as np

api = ifcopenshell.api.run
GRANDE = 100000  # histórico praticamente sem limite (como o protótipo da S04)

def preparar(f, n_psets=0):
    """Paredes, andar e contexto; cria `n_psets` conjuntos (sem histórico) para editar depois."""
    f.set_history_size(0)
    P = {"w": f.by_type("IfcWall"), "st": f.by_type("IfcBuildingStorey")[0],
         "ctx": f.by_type("IfcGeometricRepresentationSubContext")[0], "pos": 0}
    for w in P["w"][:n_psets]:
        api("pset.edit_pset", f, pset=api("pset.add_pset", f, product=w, name="Pset_Sonda"), properties={"Valor": 0.0})
    f.set_history_size(GRANDE)
    return P

def faixa(P, n):
    a = P["pos"]
    P["pos"] += n
    return P["w"][a:a + n]

def c_nome(f, w, i, P):
    api("attribute.edit_attributes", f, product=w, attributes={"Name": f"Nome {i}"})
def c_prop(f, w, i, P):
    ps = [r for r in f.get_inverse(w) if r.is_a("IfcRelDefinesByProperties")][0].RelatingPropertyDefinition
    api("pset.edit_pset", f, pset=ps, properties={"Valor": float(i + 1)})

def c_pos(f, w, i, P):
    m = np.eye(4)
    m[0, 3] = 0.01 * (i + 1)
    api("geometry.edit_object_placement", f, product=w, matrix=m)

def c_criar(f, w, i, P):
    p = api("root.create_entity", f, ifc_class="IfcWall", name=f"Nova {i}")
    rep = api("geometry.add_wall_representation", f, context=P["ctx"], length=3.0, height=2.8, thickness=0.15)
    api("geometry.assign_representation", f, product=p, representation=rep)
    api("geometry.edit_object_placement", f, product=p, matrix=np.eye(4))
    api("spatial.assign_container", f, products=[p], relating_structure=P["st"])

def c_apagar(f, w, i, P):
    api("root.remove_product", f, product=w)
def c_lote(f, ws, i, P):
    f.batch()
    for w in ws:
        api("root.remove_product", f, product=w)
    f.unbatch()


# nome -> (função, paredes por transação). "propriedade" vem primeiro: usa as paredes que ganharam conjunto em preparar()
CMDS = {"propriedade": (c_prop, 1), "mudar_nome": (c_nome, 1), "posicao": (c_pos, 1),
        "criar_parede": (c_criar, 0), "apagar_parede": (c_apagar, 1), "apagar_lote_50": (c_lote, 50)}

def tx(f, fn, *a):
    f.begin_transaction()
    fn(f, *a)
    f.end_transaction()

def alvo(P, n):
    return None if n == 0 else faixa(P, n)[0] if n == 1 else faixa(P, n)

def deep(o, vistos=None):  # tamanho em memória de um objeto Python e do que ele guarda (sem contar duas vezes)
    vistos = set() if vistos is None else vistos
    if id(o) in vistos:
        return 0
    vistos.add(id(o))
    filhos = [x for kv in o.items() for x in kv] if isinstance(o, dict) else o if isinstance(o, (list, tuple, set)) else ()
    return sys.getsizeof(o) + sum(deep(x, vistos) for x in filhos)

def cron(passo):
    t0 = time.perf_counter_ns()
    passo()
    return time.perf_counter_ns() - t0

def rss_mb():
    with open("/proc/self/statm") as h:
        return int(h.read().split()[1]) * os.sysconf("SC_PAGE_SIZE") / 1e6

def resumo_ms(ns):
    ms = sorted(x / 1e6 for x in ns)
    p = lambda q: ms[min(len(ms) - 1, round(q * (len(ms) - 1)))]
    return {"n": len(ms), "media": round(st.mean(ms), 3), "p50": round(p(.5), 3), "p95": round(p(.95), 3), "max": round(ms[-1], 3)}

def sha(p):
    with open(p, "rb") as a:
        return hashlib.file_digest(a, "sha256").hexdigest()

def foto(f):
    """id STEP -> hash do texto completo da entidade; e GlobalId -> id."""
    c = {e.id(): hash(str(e)) for e in f}
    g = {e.GlobalId: e.id() for e in f.by_type("IfcRoot")}
    return c, g

def comparar(a, b):
    (ca, ga), (cb, gb) = a, b
    return {"entidades": len(ca), "ids_faltando": len(ca.keys() - cb.keys()), "ids_extras": len(cb.keys() - ca.keys()),
            "conteudo_diferente": sum(1 for k in ca.keys() & cb.keys() if ca[k] != cb[k]),
            "globalid_com_id_diferente": sum(1 for k, v in ga.items() if gb.get(k) != v), "iguais": ca == cb and ga == gb}

def regravar(f, tmp):
    f.write(tmp)
    g = ifcopenshell.open(tmp)
    os.remove(tmp)
    return g

# ---------------- sondas ----------------
def ciclo(f, P, nomes, via="memoria", regrava=None):
    """Foto-base, uma rodada dos comandos, desfazer tudo (as operações podem passar por JSON), compara, refaz tudo."""
    base = foto(f)
    for nome in nomes:
        fn, n = CMDS[nome]
        for k in range(2 if n == 50 else 60 if len(nomes) > 1 else 20):
            tx(f, fn, alvo(P, n), k, P)
    r = {"transacoes": len(f.history)}
    if via != "memoria":
        for t in f.history:
            t.operations = json.loads(json.dumps(t.operations))
            if via == "json_chaves_int":  # JSON só tem chave de texto: o id STEP precisa voltar a ser número
                for op in t.operations:
                    if "inverses" in op:
                        op["inverses"] = {int(k): v for k, v in op["inverses"].items()}
    depois, erro = foto(f), None
    try:
        while f.history:
            f.undo()
    except sys.modules["ifcopenshell.file"].UndoSystemError as e:
        erro = repr(e.__cause__)[:100]
    fim = foto(f)
    r.update(comparar(base, fim), erro_no_undo=erro,
             classes_sobrando=dict(Counter(f.by_id(i).is_a() for i in fim[0].keys() - base[0].keys()).most_common(6)))
    if regrava:
        r["desfazer_e_regravar"] = comparar(base, foto(regravar(f, regrava)))
    if erro is None:
        while f.future:
            f.redo()
        r["refazer_igual_ao_antes_de_desfazer"] = comparar(depois, foto(f))["iguais"]
    f.set_history_size(0)
    f.set_history_size(GRANDE)
    return r

def sonda_ids(a):
    out, tmp = {}, os.path.join(os.path.dirname(a.saida), "regravado.tmp")
    for rotulo, caminho in (("modelo_1m", a.ifc), ("modelo_50mb", a.ifc50)):
        f = ifcopenshell.open(caminho)
        r = {"arquivo": caminho, "bytes": os.path.getsize(caminho), "sha256": sha(caminho),
             "gravar_e_abrir": comparar(foto(f), foto(regravar(f, tmp)))}
        P = preparar(f, 300)  # cria 300 conjuntos fora do histórico: a foto-base vem depois
        r["misto_desfazer_tudo"] = ciclo(f, P, list(CMDS), regrava=tmp)
        out[rotulo] = r
        print(rotulo, json.dumps(r)[:400], flush=True)
        del f
        gc.collect()
    return out

def sonda_ids_comando(a):
    """Diagnóstico: por comando (20 transações, 2 no lote), desfazer com as operações em memória e depois de ida e volta por JSON."""
    f = ifcopenshell.open(a.ifc50)
    P = preparar(f, 100)
    out = {}
    for nome in CMDS:
        for via in ("memoria", "json_cru", "json_chaves_int"):
            out[f"{nome}/{via}"] = ciclo(f, P, [nome], via)
            print(nome, via, out[f"{nome}/{via}"], flush=True)
    return out

def sonda_custo(a):
    f = ifcopenshell.open(a.ifc50)
    P = preparar(f, 1200)
    reps = {"apagar_lote_50": 20}
    out = {}
    for nome, (fn, n) in CMDS.items():
        k = reps.get(nome, 200)
        for modo in ("com_historico", "sem_historico"):
            f.set_history_size(GRANDE if modo == "com_historico" else 0)
            alvos = [alvo(P, n) for _ in range(k)]
            gc.collect()
            tracemalloc.start()
            d, js, prof, nops = [], [], [], []
            for i, w in enumerate(alvos):
                a0 = tracemalloc.get_traced_memory()[0]
                tx(f, fn, w, i, P)
                d.append(tracemalloc.get_traced_memory()[0] - a0)
                if modo == "com_historico":
                    ops = f.history[-1].operations
                    js.append(len(json.dumps(ops).encode()))
                    prof.append(deep(ops))
                    nops.append(len(ops))
            tracemalloc.stop()
            r = {"transacoes": k, "tracemalloc_media_bytes": round(st.mean(d)), "tracemalloc_mediana_bytes": round(st.median(d))}
            if js:
                r.update({"json_media_bytes": round(st.mean(js)), "json_max_bytes": max(js), "python_profundo_media_bytes": round(st.mean(prof)),
                          "operacoes_por_transacao_media": round(st.mean(nops), 1)})
            out.setdefault(nome, {})[modo] = r
        f.set_history_size(0)
        f.set_history_size(GRANDE)
        print(nome, out[nome], flush=True)
    return out

def sonda_tempo(a):
    f = ifcopenshell.open(a.ifc50)
    P = preparar(f, 1000)
    out = {}
    for nome, (fn, n) in CMDS.items():
        k = 20 if n == 50 else 1000
        alvos = [alvo(P, n) for _ in range(k)]
        t = [cron(lambda: tx(f, fn, w, i, P)) for i, w in enumerate(alvos)]
        u = [cron(f.undo) for _ in range(len(f.history))]
        rd = [cron(f.redo) for _ in range(len(f.future))]
        out[nome] = {"transacao_ms": resumo_ms(t), "undo_ms": resumo_ms(u), "redo_ms": resumo_ms(rd)}
        f.set_history_size(0)
        f.set_history_size(GRANDE)
        print(nome, out[nome], flush=True)
    return out

def sonda_fsync(a):
    d = tempfile.mkdtemp(prefix="fsync_", dir=a.pasta)
    linha = b"x" * 119 + b"\n"
    out = {"pasta": d, "sistema_arquivos": os.popen(f"df -T '{d}' | tail -1").read().split()[1]}
    def medir(nome, passo, n=1000):
        out[nome] = resumo_ms([cron(passo) for _ in range(n)])
    with open(os.path.join(d, "diario.log"), "ab") as h:
        medir("so_escrever_buffer", lambda: h.write(linha))
        medir("flush", lambda: (h.write(linha), h.flush()))
        medir("flush_fsync", lambda: (h.write(linha), h.flush(), os.fsync(h.fileno())))
    dado = os.urandom(1 << 20)
    alvo_ = os.path.join(d, "Casa.ifc")
    def troca(fsync_pasta, tamanho):
        def passo():
            with open(alvo_ + ".tmp", "wb") as h:
                h.write(dado[:tamanho])
                h.flush()
                os.fsync(h.fileno())
            os.replace(alvo_ + ".tmp", alvo_)
            if fsync_pasta:
                fd = os.open(d, os.O_RDONLY)
                os.fsync(fd)
                os.close(fd)
        return passo
    for tam, rot in ((4096, "4kb"), (1 << 20, "1mb")):
        medir(f"tmp_fsync_replace_{rot}", troca(False, tam), 300)
        medir(f"tmp_fsync_replace_fsyncpasta_{rot}", troca(True, tam), 300)
    shutil.rmtree(d)
    print(out, flush=True)
    return out

def sonda_registro(a):
    R = ifcopenshell.file.registry
    out = {}
    # D) (roda primeiro, para a memória estar limpa) RSS no modelo de 50 MB: soltar com histórico e depois limpar o registry
    R.clear()
    gc.collect()
    r0 = rss_mb()
    f = ifcopenshell.open(a.ifc50)
    r1 = rss_mb()
    P = preparar(f)
    for k in range(5):
        tx(f, c_nome, P["w"][k], k, P)
    w = weakref.ref(f)
    del f, P
    gc.collect()
    r2, vivo = rss_mb(), w() is not None
    R.clear()
    gc.collect()
    out["D_memoria_50mb_mb"] = {"antes": round(r0), "aberto": round(r1), "solto_com_historico": round(r2), "arquivo_vivo_depois_de_soltar": vivo,
                                "arquivo_vivo_depois_de_limpar_registry": w() is not None, "depois_de_limpar_registry": round(rss_mb())}
    def cenario(acao):  # 30 aberturas do modelo pequeno; `acao` mexe no arquivo antes de soltar
        R.clear()
        gc.collect()
        herdou, enderecos, fila = 0, set(), []
        for _ in range(30):
            f = ifcopenshell.open(a.ifc_pequeno)
            enderecos.add(int(f.this))
            herdou += bool(f.history) or bool(f.future)
            acao(f)
            fila.append(weakref.ref(f))
            del f
            gc.collect()
        return {"aberturas": 30, "enderecos_distintos": len(enderecos), "herdou_historico_velho": herdou,
                "arquivos_ainda_vivos_depois_de_soltar": sum(w() is not None for w in fila), "tamanho_registry": len(R)}
    def mexer(f, desfazer):
        P = preparar(f)
        for k in range(3):
            tx(f, c_nome, P["w"][k], k, P)
        if desfazer:
            while f.history:
                f.undo()
    out["A_tres_transacoes"] = cenario(lambda f: mexer(f, False))
    out["B_transacoes_desfeitas"] = cenario(lambda f: mexer(f, True))
    out["C_nenhuma_transacao"] = cenario(lambda f: None)
    print(out, flush=True)
    return out

SONDAS = {"ids": sonda_ids, "ids_comando": sonda_ids_comando, "custo": sonda_custo, "tempo": sonda_tempo,
          "fsync": sonda_fsync, "registro": sonda_registro}

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("sonda", choices=SONDAS)
    p.add_argument("--saida", required=True)
    p.add_argument("--ifc", help="modelo-grande-1m.ifc")
    p.add_argument("--ifc50", help="modelo sintético de ~50 MB")
    p.add_argument("--ifc-pequeno", dest="ifc_pequeno", help="modelo sintético pequeno (sonda registro)")
    p.add_argument("--pasta", default=tempfile.gettempdir(), help="pasta do teste de fsync")
    a = p.parse_args()
    r = {"maquina": {"so": platform.platform(), "cpu": platform.processor() or platform.machine(), "python": sys.version.split()[0],
                     "ifcopenshell": ifcopenshell.version}, "resultado": SONDAS[a.sonda](a)}
    with open(a.saida, "w") as h:
        json.dump(r, h, indent=1)

if __name__ == "__main__":
    main()
