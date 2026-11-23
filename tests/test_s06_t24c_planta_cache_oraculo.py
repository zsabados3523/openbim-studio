# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oraculo F0-S06-T24c (ADR-010, P3): motor de planta pelo cache de geometria (`planta_cache.py`).

Modulo alvo (o implementador NAO edita este arquivo; somente `geometria/obim_geometria/planta_cache.py`
e a ligacao minima em `geometria/obim_geometria/desenho.py`):

CONTRATO (ESPEC_T24bcde.md §1.3, §1.4, §2.1, §2.2, §3.2; tampa = Opcao 1):
1. Funcao publica:
   `planta_cache.desenhar_planta_cache(f, pedido, malhas_mundo, elementos_validos, *, fase=None, abrir_s=0.0, cache_s=0.0) -> tuple[dict | None, str | None]`
   - `f`: modelo IFC ou stub com `.by_id(id_step)` (entidade com `.id()`, `.GlobalId`, `.is_a(...)`)
     e `.by_guid(pav_guid)` (entidade `IfcBuildingStorey`).
   - `pedido`: dict com `vista` (`tipo="PLANTA"`, `pavimento=<guid>`, `escala=float`,
     `altura_corte_m=float`), `elementos`, opcional `threads`.
   - `malhas_mundo`: `dict[str, tuple[np.ndarray, np.ndarray]]` (`gid -> (verts (N,3) float64, tris (M,3) int)`).
   - `elementos_validos`: lista de pares `(id_step: int, gid: str)`.
   - Retorno: `(resp, None)` em sucesso (`resp["ok"] is True`) ou `(None, motivo)` em queda
     (`motivo in {"malha_invalida", "secao_aberta", "erro_motor"}`).
2. Validacao e classificacao pelo plano horizontal `z = float(pedido["vista"]["altura_corte_m"])`
   (`eps = 1e-9 * max(1.0, abs(z))`, `eps_plano = max(1e-9, 1e-12 * max(1.0, abs(z)))`):
   - Qualquer peca em `elementos_validos` ausente de `malhas_mundo`, vazia, nao finita,
     `|verts| > 1e12`, shape invalido, `tris` nao inteiro ou indice fora de `[0, len(verts))`
     -> queda do pavimento inteiro `(None, "malha_invalida")`.
   - `zmin > z + eps`: acima do corte (excluida do SVG e fora de `falhas_geometria`).
   - `zmax <= z + eps`: abaixo do corte (malha inteira entra em projecao).
   - `zmin <= z + eps < zmax`: cortada. Vertice no plano (`|vz - z| <= eps_plano`) ou
     `aneis_de_segmentos(segs)` com `abertos` nao vazio ou `not fechados`
     -> queda do pavimento inteiro `(None, "secao_aberta")`.
   - Secao calculada via `corte_plano.cortar_malha_no_plano` + `aneis.aneis_de_segmentos`.
3. Visibilidade e tampa (Opcao 1):
   - Todas as pecas abaixo do corte e metades inferiores (`len(t_ab) > 0`) das cortadas entram
     juntas em UMA unica chamada `visibilidade.linhas_visiveis_multi(..., angulo_graus=0.001, trabalhadores=...)`
     (0 chamadas a `visibilidade.linhas_visiveis`).
   - Recorte 2D de projecao fora dos aneis da secao via `recorte.recortar_fora_dos_aneis(..., encolher=5e-4)`,
     com grupos separados por anel externo + respectivos furos (par-impar por grupo, uniao entre grupos).
4. Formato do SVG e resposta:
   - Raiz `<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"
     xmlns:ifc="http://www.ifcopenshell.org/ns" viewBox="...">`, valido em XML e `estilo.aplicar_estilo`.
   - Grupo `<g class="IfcBuildingStorey" ifc:guid="{pav_guid}">`.
   - Secoes cortadas em `<g class="{Classe}" ifc:guid="{gid}"><path d="..."/></g>` (ordem `GlobalId` ascendente).
   - Projecao em um unico `<g class="projection">` (SEM `ifc:guid` no `<g>`).
   - Comandos de `<path d="...">` exclusivamente `M` e `L` (SEM `Z`); aneis fecham repetindo ponto inicial;
     coordenadas em metros com Y invertido `(x, -y)` e 6 casas decimais sem `-0.000000`.
   - `resp`: `ok=True`, `svg`, `n_paths`, `enviados` (inclui todas as pecas nao excluidas),
     `caixas=[]`, `em_cache=[]`, `pesados=[]`, `falhas_geometria=[]`, sem `faltantes`/`incompleta`,
     `tempos` com `abrir_s`, `geo_s=0.0`, `write_s=0.0`, `finalize_s=0.0`, `cache_s`, `corte_s`, `motor_s`.
5. Integracao em `desenho.py`:
   - `desenho._desenhar_planta_cache` delega para `planta_cache.desenhar_planta_cache`.
   - `desenho.processar` com `pasta_cache_geometria` devolve `via_cache=True`, `queda=None`, `n_faltantes=0`
     no sucesso, e cai o pavimento inteiro (`via_cache=False`, `queda="secao_aberta"|"malha_invalida"|"erro_motor"`)
     em falha.
"""
from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace

import ifcopenshell
import ifcopenshell.api
import numpy as np
import pytest

from obim_geometria import aneis, construtor, corte_plano, desenho, recorte, visibilidade
from openbim_app.desenho import estilo

NS_SVG = "{http://www.w3.org/2000/svg}"
NS_IFC = "{http://www.ifcopenshell.org/ns}"
_CMD_RE = re.compile(r"[a-zA-Z]")
_TOK_RE = re.compile(r"[-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?|[a-zA-Z]")


def _mod():
    """Importa sob demanda para que todos os testes sejam coletados e falhem antes da implementacao."""
    from obim_geometria import planta_cache

    return planta_cache


# ---------- construtores de malhas sinteticas numpy ----------
def _caixa_np(x0: float, y0: float, z0: float, x1: float, y1: float, z1: float) -> tuple[np.ndarray, np.ndarray]:
    """Malha soldada fechada de paralelepipedo (8 verts float64, 12 tris int32, normais para fora)."""
    verts = np.array(
        [
            [x0, y0, z0], [x1, y0, z0], [x1, y1, z0], [x0, y1, z0],
            [x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1],
        ],
        dtype=np.float64,
    )
    tris = np.array(
        [
            [0, 2, 1], [0, 3, 2],  # base (-Z)
            [4, 5, 6], [4, 6, 7],  # topo (+Z)
            [0, 1, 5], [0, 5, 4],  # frente (-Y)
            [1, 2, 6], [1, 6, 5],  # direita (+X)
            [2, 3, 7], [2, 7, 6],  # tras (+Y)
            [3, 0, 4], [3, 4, 7],  # esquerda (-X)
        ],
        dtype=np.int32,
    )
    return verts, tris


def _tubo_np(
    ext: list[tuple[float, float]],
    furo: list[tuple[float, float]],
    z0: float,
    z1: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Moldura retangular fechada com furo vazado (anel externo + furo interno, soldada)."""
    verts = np.array([(x, y, z) for z in (z0, z1) for x, y in ext + furo], dtype=np.float64)
    tris = []
    for i in range(4):
        j = (i + 1) % 4
        a, b, c, d = i, j, 4 + j, 4 + i
        tris += [(a, c, b), (a, d, c), (a + 8, b + 8, c + 8), (a + 8, c + 8, d + 8)]
        tris += [(i, j, 8 + j), (i, 8 + j, 8 + i), (4 + j, 4 + i, 12 + i), (4 + j, 12 + i, 12 + j)]
    return verts, np.array(tris, dtype=np.int32)


def _telhado_dobra_np(
    x0: float, y0: float, x1: float, y1: float, z0: float, z1: float, *, angulo_diedro_graus: float = 2.0
) -> tuple[np.ndarray, np.ndarray]:
    """Bloco fechado cuja face superior tem cumeeira central com angulo diedro controlado."""
    xm = 0.5 * (x0 + x1)
    dz = math.tan(math.radians(angulo_diedro_graus / 2.0)) * (xm - x0)
    zc = z1 + dz
    verts = np.array(
        [
            [x0, y0, z0], [xm, y0, z0], [x1, y0, z0],
            [x1, y1, z0], [xm, y1, z0], [x0, y1, z0],
            [x0, y0, z1], [xm, y0, zc], [x1, y0, z1],
            [x1, y1, z1], [xm, y1, zc], [x0, y1, z1],
        ],
        dtype=np.float64,
    )
    tris = np.array(
        [
            # base (-Z)
            [0, 4, 1], [0, 5, 4], [1, 3, 2], [1, 4, 3],
            # duas aguas no topo (+Z) com cumeeira 7-10
            [6, 7, 10], [6, 10, 11],
            [7, 8, 9], [7, 9, 10],
            # frente (-Y)
            [0, 1, 7], [0, 7, 6], [1, 2, 8], [1, 8, 7],
            # direita (+X)
            [2, 3, 9], [2, 9, 8],
            # tras (+Y)
            [3, 4, 10], [3, 10, 9], [4, 5, 11], [4, 11, 10],
            # esquerda (-X)
            [5, 0, 6], [5, 6, 11],
        ],
        dtype=np.int32,
    )
    return verts, tris


def _degrau_no_plano_np(z_corte: float) -> tuple[np.ndarray, np.ndarray]:
    """Caixa que cruza z_corte e possui anel/face horizontal exatamente em z = z_corte."""
    v1, t1 = _caixa_np(0.0, 0.0, 0.0, 2.0, 0.4, z_corte)
    v2, t2 = _caixa_np(0.0, 0.0, z_corte, 1.0, 0.4, z_corte + 1.4)
    return np.vstack([v1, v2]), np.vstack([t1, t2 + len(v1)]).astype(np.int32)


# ---------- stub IFC leve (sem ifcopenshell para testes unitarios numpy) ----------
class _FalsaEntidade:
    def __init__(self, id_step: int, guid: str, classe: str, *, elevation: float = 0.0):
        self._id = int(id_step)
        self.GlobalId = str(guid)
        self._classe = str(classe)
        self.Elevation = float(elevation)
        self.Representation = object()

    def id(self) -> int:
        return self._id

    def is_a(self, nome: str | None = None):
        if nome is None:
            return self._classe
        return self._classe == nome


class _FalsoIfc:
    def __init__(self, pav_guid: str, entidades: list[_FalsaEntidade]):
        self._pav = _FalsaEntidade(1, pav_guid, "IfcBuildingStorey", elevation=0.0)
        self._por_id = {1: self._pav, **{e.id(): e for e in entidades}}
        self._por_guid = {pav_guid: self._pav, **{e.GlobalId: e for e in entidades}}

    def by_id(self, id_step: int):
        return self._por_id.get(int(id_step))

    def by_guid(self, gid: str):
        return self._por_guid.get(str(gid))


def _montar_cena_numpy(
    pecas: list[tuple[int, str, str, tuple[np.ndarray, np.ndarray]]],
    *,
    altura_corte_m: float = 1.2,
    pav_guid: str = "PAV_0001",
    threads: int | None = 1,
):
    """Monta (f, pedido, malhas_mundo, elementos_validos) a partir de pecas numpy puras."""
    entidades = [_FalsaEntidade(i, g, cls) for i, g, cls, _ in pecas]
    f = _FalsoIfc(pav_guid, entidades)
    elementos = [(i, g) for i, g, _, _ in pecas]
    malhas = {g: m for _, g, _, m in pecas}
    pedido = {
        "vista": {"tipo": "PLANTA", "pavimento": pav_guid, "escala": 1.0, "altura_corte_m": float(altura_corte_m)},
        "elementos": list(elementos),
    }
    if threads is not None:
        pedido["threads"] = threads
    return f, pedido, malhas, elementos


# ---------- parsers e metricas geometricas de SVG ----------
def _extrair_polilinhas_d(d: str) -> tuple[list[str], list[np.ndarray]]:
    """Extrai lista de comandos e polilinhas 2D (K, 2) em coordenadas SVG de um atributo `d`."""
    comandos = _CMD_RE.findall(d)
    toks = _TOK_RE.findall(d)
    runs: list[list[tuple[float, float]]] = []
    atual: list[tuple[float, float]] | None = None
    cmd, i = "", 0
    while i < len(toks):
        tok = toks[i]
        if tok.isalpha():
            cmd = tok
            i += 1
            continue
        if cmd in ("M", "L") and i + 1 < len(toks):
            p = (float(tok), float(toks[i + 1]))
            if cmd == "M" or atual is None:
                if atual:
                    runs.append(atual)
                atual = [p]
                cmd = "L"
            else:
                atual.append(p)
            i += 2
        else:
            i += 1
    if atual:
        runs.append(atual)
    return comandos, [np.asarray(r, dtype=np.float64) for r in runs if len(r) >= 2]


def _parse_svg(svg: str) -> SimpleNamespace:
    root = ET.fromstring(svg)
    assert root.tag.rsplit("}", 1)[-1] == "svg"
    storeys, proj_groups = [], []
    cut_by_guid: dict[str, list[ET.Element]] = {}
    all_paths: list[ET.Element] = []
    for elem in root.iter():
        tag = elem.tag.rsplit("}", 1)[-1]
        if tag == "path":
            all_paths.append(elem)
        elif tag == "g":
            cls = (elem.get("class") or "").split()
            gid = elem.get(f"{NS_IFC}guid")
            if "IfcBuildingStorey" in cls:
                storeys.append(elem)
            elif "projection" in cls:
                proj_groups.append(elem)
            elif gid is not None:
                cut_by_guid.setdefault(gid, []).append(elem)
    return SimpleNamespace(
        root=root,
        storeys=storeys,
        proj_groups=proj_groups,
        cut_by_guid=cut_by_guid,
        all_paths=all_paths,
    )


def _polilinhas_de_elementos(grupos: list[ET.Element]) -> list[np.ndarray]:
    """Retorna polilinhas em coordenadas do mundo (x, y) revertendo Y invertido do SVG."""
    out: list[np.ndarray] = []
    for g in grupos:
        for p in g.iter():
            if p.tag.rsplit("}", 1)[-1] == "path":
                _, runs = _extrair_polilinhas_d(p.get("d") or "")
                for r in runs:
                    pts = r.copy()
                    pts[:, 1] = -pts[:, 1]
                    out.append(pts)
    return out


def _polilinhas_para_segs(polilinhas: list[np.ndarray]) -> np.ndarray:
    partes = []
    for pl in polilinhas:
        if len(pl) >= 2:
            s = np.hstack([pl[:-1], pl[1:]])
            lens = np.hypot(s[:, 2] - s[:, 0], s[:, 3] - s[:, 1])
            s = s[lens > 1e-9]
            if len(s):
                partes.append(s)
    return np.vstack(partes) if partes else np.zeros((0, 4), dtype=np.float64)


def _simplificar_anel_colinear(pl: np.ndarray, tol: float = 1e-5) -> np.ndarray:
    """Remove vertices colineares intermediarios de uma polilinha (inclusive fechada)."""
    if len(pl) < 3:
        return pl
    fechado = bool(np.hypot(*(pl[0] - pl[-1])) <= tol)
    pts = pl[:-1] if fechado else pl
    if len(pts) < 3:
        return pl
    mantidos = []
    n = len(pts)
    for i in range(n):
        if not fechado and (i == 0 or i == n - 1):
            mantidos.append(pts[i])
            continue
        p_ant = pts[(i - 1) % n]
        p_cur = pts[i]
        p_prox = pts[(i + 1) % n]
        v1 = p_cur - p_ant
        v2 = p_prox - p_cur
        n1, n2 = float(np.hypot(*v1)), float(np.hypot(*v2))
        if n1 <= tol or n2 <= tol:
            continue
        cross = abs(float(v1[0] * v2[1] - v1[1] * v2[0])) / (n1 * n2)
        dot = float(v1[0] * v2[0] + v1[1] * v2[1]) / (n1 * n2)
        if not (cross <= 1e-4 and dot > 0.0):
            mantidos.append(p_cur)
    if len(mantidos) < 2:
        return pl
    arr = np.asarray(mantidos, dtype=np.float64)
    return np.vstack([arr, arr[0:1]]) if fechado else arr


def _contagem_segmentos_corte(polilinhas: list[np.ndarray]) -> int:
    """Conta segmentos geometricos de corte (apos fundir vertices colineares de faces trianguladas)."""
    total = 0
    for pl in polilinhas:
        simp = _simplificar_anel_colinear(pl)
        segs = _polilinhas_para_segs([simp])
        total += len(segs)
    return total


def _dist_pontos_a_segs(pts: np.ndarray, segs: np.ndarray) -> np.ndarray:
    if len(pts) == 0:
        return np.zeros((0,), dtype=np.float64)
    if len(segs) == 0:
        return np.full(len(pts), np.inf, dtype=np.float64)
    a = segs[:, :2]
    d = segs[:, 2:] - a
    l2 = np.maximum((d * d).sum(axis=1), 1e-30)
    w = pts[:, None, :] - a[None, :, :]
    u = np.clip((w * d[None, :, :]).sum(axis=2) / l2[None, :], 0.0, 1.0)
    diff = w - u[:, :, None] * d[None, :, :]
    return np.sqrt((diff * diff).sum(axis=2)).min(axis=1)


def _amostrar_segs(segs: np.ndarray, passo: float = 0.01) -> np.ndarray:
    if len(segs) == 0:
        return np.zeros((0, 2), dtype=np.float64)
    pts = []
    for s in segs:
        comp = float(np.hypot(s[2] - s[0], s[3] - s[1]))
        n = max(1, int(math.ceil(comp / passo)))
        t = ((np.arange(n, dtype=np.float64) + 0.5) / n)[:, None]
        pts.append(s[:2] + t * (s[2:] - s[:2]))
    return np.vstack(pts)


def _cobertura_bidirecional(segs_ref: np.ndarray, segs_cand: np.ndarray, *, tol: float = 5e-3) -> tuple[float, float]:
    """Retorna (recall, precisao) por amostragem de comprimento a `tol` metros."""
    p_ref = _amostrar_segs(segs_ref)
    p_cand = _amostrar_segs(segs_cand)
    recall = 1.0 if len(p_ref) == 0 else float((_dist_pontos_a_segs(p_ref, segs_cand) <= tol).mean())
    precisao = 1.0 if len(p_cand) == 0 else float((_dist_pontos_a_segs(p_cand, segs_ref) <= tol).mean())
    return recall, precisao


# ---------- cena IFC sintetica pequena em tmp_path (sem IFC real) ----------
def _criar_caixa_ifc(f, body, classe: str, comp: float, esp: float, alt: float, pos: tuple[float, float, float]):
    api = ifcopenshell.api.run
    el = api("root.create_entity", f, ifc_class=classe)
    rep = api("geometry.add_wall_representation", f, context=body, length=comp, height=alt, thickness=esp)
    el.Representation = f.createIfcProductDefinitionShape(Representations=[rep])
    m = np.eye(4)
    m[:3, 3] = pos
    api("geometry.edit_object_placement", f, product=el, matrix=m, is_si=False)
    return el
