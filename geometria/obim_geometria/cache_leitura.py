# SPDX-License-Identifier: AGPL-3.0-or-later
"""Leitura de malhas do cache de geometria transformadas para coordenadas do mundo."""
from __future__ import annotations

import numpy as np

from obim_geometria.cache_geometria import CacheGeometria


def malhas_do_cache(
    cache: CacheGeometria,
    documento: str,
    global_ids,
) -> tuple[dict[str, tuple[np.ndarray, np.ndarray]], list[str]]:
    """Lê ocorrências por `global_ids` e aplica suas matrizes 4x4 às formas em cache.

    Devolve `(malhas_mundo, faltantes)`, ambos ordenados por GlobalId ascendente.
    Formas existentes em disco cuja leitura falha (corrompidas) são apagadas via
    `cache.apagar_forma` para que o construtor possa regerá-las.
    """
    ids = sorted(set(global_ids))
    if not ids:
        return {}, []

    ocorrencias = cache.ocorrencias_por_ids(ids, documento=documento)
    chaves = sorted({oc.chave_forma for oc in ocorrencias.values()})

    formas: dict[str, tuple[np.ndarray, np.ndarray] | None] = {}
    chaves_nulas: list[str] = []
    for chave in chaves:
        forma = cache.ler_forma(chave)
        formas[chave] = forma
        if forma is None:
            chaves_nulas.append(chave)

    if chaves_nulas:
        for chave in sorted(cache.formas_presentes(chaves_nulas)):
            cache.apagar_forma(chave)

    malhas_mundo: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    faltantes: list[str] = []
    for gid in ids:
        oc = ocorrencias.get(gid)
        if oc is None:
            faltantes.append(gid)
            continue
        forma = formas.get(oc.chave_forma)
        if forma is None:
            faltantes.append(gid)
            continue
        v_loc, t_loc = forma
        verts_mundo = np.ascontiguousarray(
            v_loc.astype(np.float64) @ oc.matriz[:3, :3].T + oc.matriz[:3, 3],
            dtype=np.float64,
        )
        tris = np.array(t_loc, dtype=np.int32, copy=True, order="C")
        malhas_mundo[gid] = (verts_mundo, tris)

    return malhas_mundo, faltantes
