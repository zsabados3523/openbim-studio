# SPDX-License-Identifier: AGPL-3.0-or-later
"""Motor de planta pelo cache de geometria (T24c, ADR-010 P3)."""
from __future__ import annotations

import html
import math
import time

import numpy as np

from obim_geometria import (
    aneis,
    corte_plano,
    nucleos,
    oclusores,
    recorte,
    visibilidade,
)


def _fmt6(v: float) -> str:
    """Formata coordenada com 6 casas decimais, normalizando -0.0 para 0.0."""
    return f"{round(float(v), 6) + 0.0:.6f}"


def _validar_malha(verts_raw, tris_raw) -> tuple[np.ndarray, np.ndarray] | None:
    """Valida malha (N,3) float64 finita e (M,3) int dentro dos limites."""
    try:
        v = np.asarray(verts_raw, dtype=np.float64)
        t_raw = np.asarray(tris_raw)
    except (TypeError, ValueError):
        return None
    if v.ndim != 2 or v.shape[1] != 3 or len(v) == 0:
        return None
    if t_raw.ndim != 2 or t_raw.shape[1] != 3 or len(t_raw) == 0:
        return None
    if not np.issubdtype(t_raw.dtype, np.integer):
        return None
    t = t_raw.astype(np.int64, copy=False)
    if int(t.min()) < 0 or int(t.max()) >= len(v):
        return None
    if not np.isfinite(v).all() or float(np.abs(v).max()) > 1e12:
        return None
    return v, t


def _anel_para_d(anel: np.ndarray, xs: list[float], ys: list[float]) -> str | None:
    """Converte anel 2D em subpath SVG `M ... L ...` sem `Z` (eixo Y invertido)."""
    pts = np.asarray(anel, dtype=np.float64)
    if pts.ndim != 2 or len(pts) < 3 or pts.shape[1] < 2:
        return None
    coords = [(float(p[0]), -float(p[1])) for p in pts]
    if abs(coords[0][0] - coords[-1][0]) > 1e-12 or abs(coords[0][1] - coords[-1][1]) > 1e-12:
        coords.append(coords[0])
    for x, y in coords:
        xs.append(x)
        ys.append(y)
    cmds = [f"M {_fmt6(coords[0][0])},{_fmt6(coords[0][1])}"]
    cmds.extend(f"L {_fmt6(x)},{_fmt6(y)}" for x, y in coords[1:])
    return " ".join(cmds)


def _poli_para_d(poli: np.ndarray, xs: list[float], ys: list[float]) -> str | None:
    """Converte polilinha 2D em path SVG `M ... L ...` sem `Z` (eixo Y invertido)."""
    pts = np.asarray(poli, dtype=np.float64)
    if pts.ndim != 2 or len(pts) < 2 or pts.shape[1] < 2:
        return None
    coords = [(float(p[0]), -float(p[1])) for p in pts]
    for x, y in coords:
        xs.append(x)
        ys.append(y)
    cmds = [f"M {_fmt6(coords[0][0])},{_fmt6(coords[0][1])}"]
    cmds.extend(f"L {_fmt6(x)},{_fmt6(y)}" for x, y in coords[1:])
    return " ".join(cmds)


def _montar_svg(
    pav_guid: str,
    pecas_secao: list[tuple[str, str, list[np.ndarray]]],
    pols_proj: list[np.ndarray],
) -> tuple[str, int]:
    """Monta SVG deterministico compativel com `estilo.aplicar_estilo`."""
    xs: list[float] = []
    ys: list[float] = []
    partes_secao: list[str] = []
    n_paths = 0

    for gid, classe, fechados in pecas_secao:
        subpaths: list[str] = []
        for anel in fechados:
            sub = _anel_para_d(anel, xs, ys)
            if sub:
                subpaths.append(sub)
        if not subpaths:
            continue
        cls_esc = html.escape(classe, quote=True)
        gid_esc = html.escape(gid, quote=True)
        d_attr = " ".join(subpaths)
        partes_secao.append(f'<g class="{cls_esc}" ifc:guid="{gid_esc}"><path d="{d_attr}"/></g>')
        n_paths += 1

    proj_paths: list[str] = []
    for poli in pols_proj:
        d_proj = _poli_para_d(poli, xs, ys)
        if d_proj:
            proj_paths.append(f'<path d="{d_proj}"/>')
            n_paths += 1

    if xs and ys:
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        vb = f"{_fmt6(min_x)} {_fmt6(min_y)} {_fmt6(max_x - min_x)} {_fmt6(max_y - min_y)}"
    else:
        vb = "0 0 1 1"

    pav_esc = html.escape(pav_guid, quote=True)
    linhas = [
        f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'xmlns:ifc="http://www.ifcopenshell.org/ns" viewBox="{vb}">',
        f'<g class="IfcBuildingStorey" ifc:guid="{pav_esc}">',
        *partes_secao,
    ]
    if proj_paths:
        linhas.append('<g class="projection">')
        linhas.extend(proj_paths)
        linhas.append("</g>")
    linhas.append("</g>")
    linhas.append("</svg>")
    return "\n".join(linhas), n_paths


def desenhar_planta_cache(
    f,
    pedido: dict,
    malhas_mundo: dict[str, tuple[np.ndarray, np.ndarray]],
    elementos_validos: list[tuple[int, str]],
    *,
    fase=None,
    abrir_s: float = 0.0,
    cache_s: float = 0.0,
) -> tuple[dict | None, str | None]:
    """Desenha planta completa a partir das malhas em `malhas_mundo`.

    Retorna `(resp, None)` em sucesso ou `(None, motivo_queda)` em falha
    (`"malha_invalida"`, `"secao_aberta"`, `"erro_motor"`).
    """
    del fase
    try:
        vista = pedido["vista"]
        pav_guid = str(vista["pavimento"])
        z = float(vista["altura_corte_m"])
        if not math.isfinite(z):
            return None, "erro_motor"

        eps = 1e-9 * max(1.0, abs(z))
        eps_plano = max(1e-9, 1e-12 * max(1.0, abs(z)))
        ordenados = sorted(elementos_validos, key=lambda item: (str(item[1]), int(item[0])))

        t_corte0 = time.perf_counter()
        enviados: list[int] = []
        pecas_secao: list[tuple[str, str, list[np.ndarray]]] = []
        grupos_secao: list[list[np.ndarray]] = []
        malhas_proj: list[tuple[np.ndarray, np.ndarray]] = []

        for id_step, gid in ordenados:
            if gid not in malhas_mundo:
                return None, "malha_invalida"
            verts_raw, tris_raw = malhas_mundo[gid]
            validada = _validar_malha(verts_raw, tris_raw)
            if validada is None:
                return None, "malha_invalida"
            v, t = validada

            el = f.by_id(int(id_step))
            if el is None:
                return None, "erro_motor"
            classe = str(el.is_a() or "IfcProduct")

            zmin = float(v[:, 2].min())
            zmax = float(v[:, 2].max())
            if zmin > z + eps:
                continue

            enviados.append(int(id_step))
            if zmax <= z + eps:
                malhas_proj.append((v, t))
                continue

            if np.any(np.abs(v[:, 2] - z) <= eps_plano):
                return None, "secao_aberta"

            v_ab, t_ab, segs = corte_plano.cortar_malha_no_plano(v, t, z)
            fechados, abertos = aneis.aneis_de_segmentos(segs)
            if abertos or not fechados:
                return None, "secao_aberta"

            grupos = oclusores._agrupar_aneis(fechados)
            if not grupos:
                return None, "secao_aberta"

            pecas_secao.append((str(gid), classe, fechados))
            for rings, _ in grupos:
                grupos_secao.append(rings)
            if len(t_ab) > 0:
                malhas_proj.append((v_ab, t_ab))

        corte_s = time.perf_counter() - t_corte0

        threads_ped = pedido.get("threads")
        n_trab = nucleos.limitar_threads(threads_ped) if threads_ped is not None else None

        t_mot0 = time.perf_counter()
        if malhas_proj:
            pols_por_peca = visibilidade.linhas_visiveis_multi(
                malhas_proj,
                angulo_graus=0.001,
                trabalhadores=n_trab,
            )
            pols_proj = [poli for pols_i in pols_por_peca for poli in pols_i]
        else:
            pols_proj = []
        motor_s = time.perf_counter() - t_mot0

        if pols_proj and grupos_secao:
            t_tampa0 = time.perf_counter()
            pols_proj = recorte.recortar_fora_dos_aneis(pols_proj, grupos_secao, encolher=5e-4)
            corte_s += time.perf_counter() - t_tampa0

        svg, n_paths = _montar_svg(pav_guid, pecas_secao, pols_proj)
        return {
            "ok": True,
            "svg": svg,
            "n_paths": n_paths,
            "enviados": enviados,
            "caixas": [],
            "em_cache": [],
            "pesados": [],
            "falhas_geometria": [],
            "tempos": {
                "abrir_s": float(abrir_s),
                "geo_s": 0.0,
                "write_s": 0.0,
                "finalize_s": 0.0,
                "cache_s": float(cache_s),
                "corte_s": float(corte_s),
                "motor_s": float(motor_s),
            },
        }, None
    except Exception:
        return None, "erro_motor"
