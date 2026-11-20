# SPDX-License-Identifier: AGPL-3.0-or-later
"""Núcleo do construtor de cache geométrico por lotes (sem processo)."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import ctypes
import sys
import time

import ifcopenshell.geom
import ifcopenshell.util.placement as _placement
import ifcopenshell.util.unit as _unit
import numpy as np

from obim_geometria import cache_geometria, malha_direta, nucleos

TESSELACAO = {"use_world_coords": False}
_IDADE_MAX_S = 30 * 86400
_TETO_BYTES = 5 * (2**30)
_TOL_MATRIZ = 1e-9

documento_de = cache_geometria.documento_de


def abrir_banco(pasta) -> cache_geometria.CacheGeometria:
    """Abre o cache em disco com cabeçalho do construtor e aplica limpeza de retenção."""
    cache = cache_geometria.abrir_cache(pasta, cache_geometria.cabecalho_atual(tesselacao=TESSELACAO))
    if cache.em_memoria:
        cache.fechar()
        raise ValueError("banco_em_memoria")
    cache.limpar(idade_max_s=_IDADE_MAX_S, teto_bytes=_TETO_BYTES)
    return cache


def fila_inicial(f) -> list[int]:
    """IDs STEP de IfcElement com Representation, sem IfcOpeningElement, ordenados por GlobalId."""
    if f is None:
        return []
    elementos = [
        el
        for el in f.by_type("IfcElement")
        if not el.is_a("IfcOpeningElement") and getattr(el, "Representation", None) is not None
    ]
    elementos.sort(key=lambda el: getattr(el, "GlobalId", "") or "")
    return [int(el.id()) for el in elementos]


def priorizar(fila: list[int], primeiro) -> list[int]:
    """Move os IDs de `primeiro` presentes em `fila` para a frente, preservando a ordem relativa."""
    alvo = set(primeiro)
    if not alvo or not fila:
        return list(fila)
    frente = [x for x in fila if x in alvo]
    resto = [x for x in fila if x not in alvo]
    return frente + resto


def pavimento_de(el) -> str | None:
    """Devolve o GlobalId do IfcBuildingStorey que contém a peça (até 5 níveis de agregação)."""
    atual = el
    vistos: set[int] = set()
    for _ in range(6):
        if atual is None:
            return None
        ident = int(atual.id()) if hasattr(atual, "id") else id(atual)
        if ident in vistos:
            return None
        vistos.add(ident)
        if atual.is_a("IfcBuildingStorey"):
            return getattr(atual, "GlobalId", None)
        proximo = None
        for rel in getattr(atual, "ContainedInStructure", None) or ():
            est = getattr(rel, "RelatingStructure", None)
            if est is not None:
                if est.is_a("IfcBuildingStorey"):
                    return getattr(est, "GlobalId", None)
                proximo = est
                break
        if proximo is None:
            for rel in getattr(atual, "Decomposes", None) or ():
                if rel.is_a("IfcRelAggregates"):
                    pai = getattr(rel, "RelatingObject", None)
                    if pai is not None:
                        proximo = pai
                        break
        atual = proximo
    return None


def soldar(v, t, tol: float = 1e-6) -> tuple[np.ndarray, np.ndarray]:
    """Solda vértices dentro de `tol` e remove triângulos degenerados ou órfãos.

    Origem: algoritmo de soldagem por quantização em grade (s06).
    """
    verts = np.asarray(v, dtype=np.float64).reshape(-1, 3)
    tris = np.asarray(t, dtype=np.int64).reshape(-1, 3)
    if len(verts) == 0 or len(tris) == 0:
        return np.zeros((0, 3), dtype=np.float64), np.zeros((0, 3), dtype=np.int32)
    passo = float(tol) if tol and tol > 0 else 1e-6
    grade = np.round(verts / passo).astype(np.int64)
    _, idx_unicos, inv = np.unique(grade, axis=0, return_index=True, return_inverse=True)
    # Preserva o primeiro vértice de cada célula para estabilidade determinística.
    ordem = np.argsort(idx_unicos, kind="mergesort")
    reord = np.empty_like(ordem)
    reord[ordem] = np.arange(len(ordem), dtype=reord.dtype)
    sv = verts[idx_unicos[ordem]]
    st = reord[inv[tris]]
    ok = (st[:, 0] != st[:, 1]) & (st[:, 1] != st[:, 2]) & (st[:, 2] != st[:, 0])
    st = st[ok]
    if len(st) == 0:
        return np.zeros((0, 3), dtype=np.float64), np.zeros((0, 3), dtype=np.int32)
    usados, inv_usados = np.unique(st.ravel(), return_inverse=True)
    sv = sv[usados]
    st = inv_usados.reshape(-1, 3)
    return np.ascontiguousarray(sv, dtype=np.float64), np.ascontiguousarray(st, dtype=np.int32)


def rss_mb() -> float:
    """Devolve o RSS atual do processo em MiB."""
    if sys.platform.startswith("linux"):
        try:
            with open("/proc/self/status", encoding="ascii", errors="ignore") as arq:
                for linha in arq:
                    if linha.startswith("VmRSS:"):
                        partes = linha.split()
                        if len(partes) >= 2:
                            return float(partes[1]) / 1024.0
        except OSError:
            pass
    elif sys.platform == "win32":
        class _PROCESS_MEMORY_COUNTERS(ctypes.Structure):
            _fields_ = [
                ("cb", ctypes.c_ulong),
                ("PageFaultCount", ctypes.c_ulong),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        pmc = _PROCESS_MEMORY_COUNTERS()
        pmc.cb = ctypes.sizeof(pmc)
        proc = ctypes.windll.kernel32.GetCurrentProcess()
        if ctypes.windll.psapi.GetProcessMemoryInfo(proc, ctypes.byref(pmc), pmc.cb):
            return float(pmc.WorkingSetSize) / (1024.0 * 1024.0)
    import resource

    return float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss) / 1024.0


def matriz_mundo(el, escala: float) -> np.ndarray:
    """Matriz 4x4 do placement no mundo em metros (`translação * escala`)."""
    m = np.asarray(_placement.get_local_placement(getattr(el, "ObjectPlacement", None)), dtype=np.float64).copy()
    m[:3, 3] *= float(escala)
    return m


def _tesselar_representantes(
    f, representantes: dict[str, object], escala: float, n_threads: int
) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """Tessela uma peça por chave ausente em coordenadas locais, tentando malha direta antes do iterador."""
    if not representantes:
        return {}
    itens = sorted(representantes.items(), key=lambda kv: kv[0])
    cache_direto: dict = {}

    def _direta(par):
        chave, el = par
        malha = malha_direta.malha_local(el, escala, cache_direto)
        return chave, el, malha

    if n_threads == 1 or len(itens) <= 1:
        lidos = [_direta(par) for par in itens]
    else:
        with ThreadPoolExecutor(max_workers=min(n_threads, len(itens))) as ex:
            lidos = list(ex.map(_direta, itens))

    formas: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    restantes = []
    chave_por_id: dict[int, str] = {}
    for chave, el, malha in lidos:
        if malha is not None:
            sv, st = soldar(malha[0], malha[1])
            if len(sv) and len(st):
                formas[chave] = (sv, st)
                continue
        eid = int(el.id())
        restantes.append(el)
        chave_por_id[eid] = chave

    if restantes:
        cfg = ifcopenshell.geom.settings()
        cfg.set(cfg.USE_WORLD_COORDS, False)
        it = ifcopenshell.geom.iterator(cfg, f, n_threads, include=restantes)
        if it.initialize():
            while True:
                try:
                    sh = it.get()
                    geo = getattr(sh, "geometry", None)
                    chave = chave_por_id.get(int(sh.id))
                    if chave is not None and geo is not None and geo.verts and geo.faces:
                        verts = np.asarray(geo.verts, dtype=np.float64).reshape(-1, 3)
                        tris = np.asarray(geo.faces, dtype=np.int32).reshape(-1, 3)
                        sv, st = soldar(verts, tris)
                        if len(sv) and len(st):
                            formas[chave] = (sv, st)
                except Exception:
                    pass
                if not it.next():
                    break
    return formas


def construir_lote(
    f,
    cache: cache_geometria.CacheGeometria,
    ids,
    *,
    documento: str,
    assinatura: str,
    memo: dict[int, str],
    threads: int | None = None,
) -> dict:
    """Constrói e persiste formas ausentes e ocorrências novas/alteradas para `ids` em uma única transação."""
    if cache.em_memoria:
        raise ValueError("banco_em_memoria")

    inicio = time.perf_counter()
    n_threads = nucleos.limitar_threads(threads)
    try:
        escala = float(_unit.calculate_unit_scale(f))
    except Exception:
        escala = 1.0

    falhas = 0
    pecas: list[tuple[int, object, str, str]] = []
    for raw_id in ids:
        eid = int(raw_id)
        try:
            el = f.by_id(eid)
            gid = getattr(el, "GlobalId", None) if el is not None else None
            if el is None or not gid:
                falhas += 1
                continue
            chave = memo.get(eid)
            if not chave:
                chave = cache_geometria.chave_da_forma(el, tesselacao=TESSELACAO)
                memo[eid] = chave
            pecas.append((eid, el, gid, chave))
        except Exception:
            falhas += 1

    existentes = cache.ocorrencias_por_ids([gid for _, _, gid, _ in pecas], documento=documento)
    pendentes: list[tuple[object, str, str, np.ndarray]] = []
    reaproveitadas = 0
    for _, el, gid, chave in pecas:
        try:
            mat = matriz_mundo(el, escala)
        except Exception:
            falhas += 1
            continue
        ant = existentes.get(gid)
        if ant is not None and ant.chave_forma == chave and np.allclose(ant.matriz, mat, rtol=0.0, atol=_TOL_MATRIZ):
            reaproveitadas += 1
            continue
        pendentes.append((el, gid, chave, mat))

    if not pendentes:
        return {
            "tesseladas": 0,
            "reaproveitadas": reaproveitadas,
            "falhas": falhas,
            "gravadas": 0,
            "segundos": time.perf_counter() - inicio,
        }

    chaves_nec = {chave for _, _, chave, _ in pendentes}
    presentes = cache.formas_presentes(chaves_nec)

    formas_lidas: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for chave in sorted(presentes):
        par = cache.ler_forma(chave)
        if par is not None:
            formas_lidas[chave] = par

    representantes: dict[str, object] = {}
    for el, gid, chave, _ in sorted(pendentes, key=lambda x: x[1]):
        if chave not in formas_lidas and chave not in representantes:
            representantes[chave] = el

    formas_novas = _tesselar_representantes(f, representantes, escala, n_threads)
    tesseladas = len(formas_novas)

    todas_formas = {**formas_lidas, **formas_novas}
    ocorrencias: list[cache_geometria.Ocorrencia] = []
    for el, gid, chave, mat in pendentes:
        par = todas_formas.get(chave)
        if par is None:
            falhas += 1
            continue
        if chave in formas_lidas:
            reaproveitadas += 1
        v, _ = par
        w = v @ mat[:3, :3].T + mat[:3, 3]
        caixa = np.vstack((w.min(axis=0), w.max(axis=0)))
        ocorrencias.append(
            cache_geometria.Ocorrencia(
                global_id=gid,
                chave_forma=chave,
                matriz=mat,
                caixa=caixa,
                pavimento=pavimento_de(el),
                classe_ifc=el.is_a(),
            )
        )

    ocorrencias.sort(key=lambda oc: oc.global_id)
    if formas_novas or ocorrencias:
        cache.gravar_lote(formas_novas, ocorrencias, documento=documento, memo=(assinatura, memo))

    return {
        "tesseladas": tesseladas,
        "reaproveitadas": reaproveitadas,
        "falhas": falhas,
        "gravadas": len(ocorrencias),
        "segundos": time.perf_counter() - inicio,
    }
