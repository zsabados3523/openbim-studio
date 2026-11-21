# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oraculo F0-S06-T24f (ADR-010, P3): secao tolerante em `planta_cache.py`.

Modulo alvo (o implementador NAO edita este arquivo; somente
`geometria/obim_geometria/planta_cache.py`, `geometria/obim_geometria/desenho.py`,
`app/openbim_app/desenho/planta.py` e `app/openbim_app/desenho/gerente.py`):

CONTRATO NOVO (T24f):
1. Vertice no plano (`|vz - z_local| <= eps`):
   - `oz = z if abs(z) > 1000.0 else 0.0`, `z_local = z - oz`,
     `eps(zl) = max(1e-9, 1e-12 * max(1.0, abs(zl)))`.
   - Se NENHUMA peca (cortada ou nao) tem vertice com `|(v[:, 2] - oz) - z_local| <= eps(z_local)`,
     o plano permanece em `z_local` (`delta = 0.0`).
   - Se ALGUMA peca (cortada ou nao) tem vertice com `|(v[:, 2] - oz) - z_local| <= eps(z_local)`,
     o plano de corte de TODAS as pecas desloca para `z_ef = z_local + delta`, tentando `delta`
     na ordem fixa `(+1e-5, -1e-5, +3.7e-5, -3.7e-5)` metros.
   - Escolhe o primeiro `delta` que:
     (i) deixa nenhum vertice de nenhuma peca com `|(v[:, 2] - oz) - z_ef| <= eps(z_ef)`; e
     (ii) mantem a classificacao acima/abaixo coerente: nenhuma peca estritamente acima em
          `z_local` (`zmin > z_local + eps(z_local)`) deixa de estar acima em `z_ef`
          (`zmin > z_ef + eps(z_ef)`), nenhuma peca estritamente abaixo em `z_local`
          (`zmax < z_local - eps(z_local)`) deixa de estar abaixo em `z_ef`
          (`zmax < z_ef - eps(z_ef)`), e a classificacao final (acima/abaixo/cortada),
          origem relativa e corte de TODAS as pecas usam esse mesmo `z_ef`.
   - Se nenhum dos 4 deltas serve -> queda do pavimento inteiro `(None, "secao_aberta")`.
   - Deterministico e independente da ordem de entrada / GUID.
2. Aneis abertos (secoes parciais):
   - Peca cortada sem NENHUM anel fechado e sem NENHUMA cadeia aberta (`not fechados and not abertos`)
     -> queda do pavimento inteiro `(None, "secao_aberta")`.
   - Peca cortada com `fechados` e `abertos`:
     * `fechados` seguem o fluxo atual (desenhados na secao como subcaminhos fechados `M/L`
       repetindo o ponto inicial sem `Z` + entram na tampa `grupos_secao` via `oclusores._agrupar_aneis`).
     * `abertos` sao desenhados na secao da peca (`<g class="{Classe}" ifc:guid="{gid}">`) como
       subcaminhos `M/L` ABERTOS (sem `Z`, SEM fechar / sem repetir ponto inicial), e NAO entram
       na tampa (`grupos_secao`).
   - Peca cortada so com `abertos` (`not fechados` e `abertos` nao vazio):
     * Tambem aceita como parcial: cadeias abertas desenhadas na secao da peca (sem `Z`, sem fechar),
       NAO entram na tampa; metade inferior (`len(t_ab) > 0`) continua em projecao.
   - Telemetria nova em `resp`: `resp["secoes_parciais"]` (`int`, numero de pecas cortadas com alguma
     cadeia aberta; `0` quando nenhuma). `resp["tempos"]` e demais campos atuais permanecem intactos.
3. Limite de seguranca (25% das pecas cortadas):
   - Maximo aceito: `math.ceil(0.25 * n_cortadas)` (onde `n_cortadas` conta APENAS pecas cortadas,
     nunca pecas acima ou abaixo do corte).
   - Se `secoes_parciais > math.ceil(0.25 * n_cortadas)` -> queda do pavimento inteiro
     `(None, "secao_aberta")`.
4. Nunca omitir elemento:
   - Toda peca nao acima do corte permanece em `resp["enviados"]` e com linhas no SVG.
5. Telemetria integrada:
   - `desenho.processar`: `via_cache=True`, `queda=None` quando aceito; `secoes_parciais` (`int`)
     propagado em `resp` (0 em queda).
   - `planta.Planta` e `gerente._motor_padrao` / sinal `pronto` (`dados`): campo `secoes_parciais: int = 0`.
6. Determinismo, imutabilidade, UTM e memoria:
   - SHA-256 do SVG identico em 3 rodadas, entrada embaralhada e threads diferentes.
   - `malhas_mundo` (dict e arrays) e `pedido` nunca sao mutados.
   - Coordenadas UTM e Z grande funcionam com deslocamento de plano e secoes parciais.
   - Memoria liberada antes de `linhas_visiveis_multi` e `recortar_fora_dos_aneis` como hoje.
"""
from __future__ import annotations

from collections import Counter
import gc
import hashlib
import math
import re
import threading
import weakref
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace

import ifcopenshell
import ifcopenshell.api
import numpy as np
import pytest

from obim_geometria import aneis, construtor, corte_plano, desenho, planta_cache, recorte, visibilidade
from openbim_app import vistas_ifc
from openbim_app.desenho import cache as app_cache
from openbim_app.desenho import estilo
from openbim_app.desenho import gerente as app_gerente
from openbim_app.desenho import planta as app_planta
from openbim_app.desenho import selecao as app_selecao
from openbim_app.desenho.selecao import Selecao

NS_IFC = "{http://www.ifcopenshell.org/ns}"
_CMD_RE = re.compile(r"[a-zA-Z]")
_TOK_RE = re.compile(r"[-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?|[a-zA-Z]")
_DELTAS_ORDEM = (1e-5, -1e-5, 3.7e-5, -3.7e-5)


# ---------- construtores sinteticos numpy ----------
def _caixa_np(
    x0: float, y0: float, z0: float, x1: float, y1: float, z1: float
) -> tuple[np.ndarray, np.ndarray]:
    """Paralelepipedo fechado soldado (8 verts, 12 tris)."""
    verts = np.array(
        [
            [x0, y0, z0], [x1, y0, z0], [x1, y1, z0], [x0, y1, z0],
            [x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1],
        ],
        dtype=np.float64,
    )
    tris = np.array(
        [
            [0, 2, 1], [0, 3, 2],
            [4, 5, 6], [4, 6, 7],
            [0, 1, 5], [0, 5, 4],
            [1, 2, 6], [1, 6, 5],
            [2, 3, 7], [2, 7, 6],
            [3, 0, 4], [3, 4, 7],
        ],
        dtype=np.int32,
    )
    return verts, tris


def _caixa_com_aneis_z_np(
    x0: float,
    y0: float,
    z0: float,
    x1: float,
    y1: float,
    z1: float,
    zs_intermediarios: list[float] | tuple[float, ...],
) -> tuple[np.ndarray, np.ndarray]:
    """Caixa fechada soldada subdividida em camadas Z exatas (vertices exatamente em cada z da lista)."""
    zs = sorted({float(z0), float(z1), *(float(z) for z in zs_intermediarios)})
    verts_list = []
    for z in zs:
        verts_list.extend([[x0, y0, z], [x1, y0, z], [x1, y1, z], [x0, y1, z]])
    verts = np.asarray(verts_list, dtype=np.float64)
    tris = [[0, 2, 1], [0, 3, 2]]
    n_cam = len(zs)
    for k in range(n_cam - 1):
        b = 4 * k
        t = 4 * (k + 1)
        for i in range(4):
            j = (i + 1) % 4
            tris.append([b + i, b + j, t + j])
            tris.append([b + i, t + j, t + i])
    top = 4 * (n_cam - 1)
    tris.extend([[top + 0, top + 1, top + 2], [top + 0, top + 2, top + 3]])
    return verts, np.asarray(tris, dtype=np.int32)


def _malha_grande_poucos_vertices_no_plano_np(
    x0: float, y0: float, z0: float, x1: float, y1: float, z1: float, z_plano: float, *, n_faixas_x: int = 30
) -> tuple[np.ndarray, np.ndarray]:
    """Malha fechada com muitos triangulos (parede subdividida em X) onde apenas 2 vertices caem em `z_plano`."""
    # Dividimos em X em n_faixas_x colunas e apenas uma coluna tem vertice intermediario em z_plano
    xs = np.linspace(x0, x1, n_faixas_x + 1, dtype=np.float64)
    # Constroi prisma fechado com 2 camadas intermediarias: z_plano - 0.1 e z_plano + 0.1,
    # exceto no indice central onde um unico par (frente/tras) fica exatamente em z_plano.
    z_a = z_plano - 0.25
    z_b = z_plano + 0.25
    n_x = len(xs)
    # Contorno 2D fechado (frente x0..x1 em y0, tras x1..x0 em y1)
    anel_xy = [(float(x), float(y0)) for x in xs] + [(float(x), float(y1)) for x in reversed(xs)]
    m = len(anel_xy)
    zs_base = [z0, z_a, z_b, z1]
    verts_list = []
    for ci, z in enumerate(zs_base):
        for pi, (x, y) in enumerate(anel_xy):
            zz = z_plano if (ci == 1 and pi in (n_x // 2, m - 1 - n_x // 2)) else z
            verts_list.append([x, y, zz])
    verts = np.asarray(verts_list, dtype=np.float64)
    tris = []
    for k in range(len(zs_base) - 1):
        b = m * k
        t = m * (k + 1)
        for i in range(m):
            j = (i + 1) % m
            tris.append([b + i, b + j, t + j])
            tris.append([b + i, t + j, t + i])
    # Tampas inferior e superior por faixas entre frente (i) e tras (m - 1 - i)
    top = m * (len(zs_base) - 1)
    for i in range(n_x - 1):
        f0, f1 = i, i + 1
        r0, r1 = m - 1 - i, m - 2 - i
        tris.append([f0, r0, f1])
        tris.append([f1, r0, r1])
        tris.append([top + f0, top + f1, top + r0])
        tris.append([top + f1, top + r1, top + r0])
    return verts, np.asarray(tris, dtype=np.int32)


def _degrau_no_plano_np(z_corte: float, *, dx: float = 0.0, dy: float = 0.0) -> tuple[np.ndarray, np.ndarray]:
    """Bloco em degrau com face horizontal exatamente em z_corte."""
    v1, t1 = _caixa_np(dx, dy, 0.0, dx + 2.0, dy + 0.4, z_corte)
    v2, t2 = _caixa_np(dx, dy, z_corte, dx + 1.0, dy + 0.4, z_corte + 1.4)
    return np.vstack([v1, v2]), np.vstack([t1, t2 + len(v1)]).astype(np.int32)


def _parede_inclinada_np(
    x0: float, y0: float, y1: float, z0: float, z1: float, *, esp: float = 0.3, inclinacao_dx_dz: float = 2.0
) -> tuple[np.ndarray, np.ndarray]:
    """Prisma fechado inclinado em X conforme Z (`x(z) = x0 + inclinacao_dx_dz * (z - z0)`)."""
    dx = inclinacao_dx_dz * (z1 - z0)
    verts = np.array(
        [
            [x0, y0, z0], [x0 + esp, y0, z0], [x0 + esp, y1, z0], [x0, y1, z0],
            [x0 + dx, y0, z1], [x0 + dx + esp, y0, z1], [x0 + dx + esp, y1, z1], [x0 + dx, y1, z1],
        ],
        dtype=np.float64,
    )
    tris = np.array(
        [
            [0, 2, 1], [0, 3, 2],
            [4, 5, 6], [4, 6, 7],
            [0, 1, 5], [0, 5, 4],
            [1, 2, 6], [1, 6, 5],
            [2, 3, 7], [2, 7, 6],
            [3, 0, 4], [3, 4, 7],
        ],
        dtype=np.int32,
    )
    return verts, tris


def _caixas_fundidas_em_t_np(
    dx: float = 0.0, dy: float = 0.0, z0: float = 0.0, z1: float = 2.8
) -> tuple[np.ndarray, np.ndarray]:
    """Duas caixas fechadas fundidas numa malha nao-manifold em T (0 bordas livres, arestas com 3 tris).

    Caixa 1: [dx, dx+2.0] x [dy, dy+0.4] x [z0, z1] (produz 1 anel fechado no corte).
    Caixa 2: [dx+0.8, dx+1.2] x [dy+0.4, dy+2.0] x [z0, z1] tocando Caixa 1 com arestas compartilhadas
    (nos (dx+0.8, dy+0.4) e (dx+1.2, dy+0.4) de grau 3 -> 1 cadeia aberta no corte).
    """
    pts2d = [
        (dx + 0.0, dy + 0.0), (dx + 2.0, dy + 0.0), (dx + 2.0, dy + 0.4),
        (dx + 1.2, dy + 0.4), (dx + 0.8, dy + 0.4), (dx + 0.0, dy + 0.4),
        (dx + 0.8, dy + 2.0), (dx + 1.2, dy + 2.0),
    ]
    n = len(pts2d)
    verts = np.array([(x, y, z) for z in (z0, z1) for (x, y) in pts2d], dtype=np.float64)
    arestas = [(0, 1), (1, 2), (2, 3), (3, 4), (4, 5), (5, 0), (4, 6), (6, 7), (7, 3)]
    tris = []
    for a, b in arestas:
        tris.append([a, b, b + n])
        tris.append([a, b + n, a + n])
    for zoff, flip in ((0, True), (n, False)):
        for tri in [(0, 1, 2), (0, 2, 3), (0, 3, 4), (0, 4, 5), (4, 3, 7), (4, 7, 6)]:
            t = [tri[0] + zoff, tri[1] + zoff, tri[2] + zoff]
            tris.append(t[::-1] if flip else t)
    return verts, np.asarray(tris, dtype=np.int32)


def _caixa_100_aberta_np(
    x0: float, y0: float, z0: float, x1: float, y1: float, z1: float
) -> tuple[np.ndarray, np.ndarray]:
    """Caixa cortada sem uma face lateral -> 0 aneis fechados, 1 cadeia aberta."""
    v, t = _caixa_np(x0, y0, z0, x1, y1, z1)
    return v, t[:-2].copy()


def _malha_sem_segmentos_corte_np(
    x0: float, y0: float, z0: float, x1: float, y1: float, z1: float
) -> tuple[np.ndarray, np.ndarray]:
    """Malha com triangulos apenas em z0 e z1 (cruza o plano, mas gera 0 segmentos no corte)."""
    verts = np.array(
        [
            [x0, y0, z0], [x1, y0, z0], [x1, y1, z0],
            [x0, y0, z1], [x1, y0, z1], [x1, y1, z1],
        ],
        dtype=np.float64,
    )
    tris = np.array([[0, 1, 2], [3, 4, 5]], dtype=np.int32)
    return verts, tris


def _transladar_malha(
    malha: tuple[np.ndarray, np.ndarray], ox: float = 0.0, oy: float = 0.0, oz: float = 0.0
) -> tuple[np.ndarray, np.ndarray]:
    v, t = malha
    v2 = v.astype(np.float64, copy=True)
    if ox:
        v2[:, 0] += float(ox)
    if oy:
        v2[:, 1] += float(oy)
    if oz:
        v2[:, 2] += float(oz)
    return v2, t.copy()


# ---------- stubs IFC leves ----------
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
        return self._classe if nome is None else (self._classe == nome)


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
    pav_guid: str = "PAV_T24F",
    threads: int | None = 1,
):
    entidades = [_FalsaEntidade(i, g, cls) for i, g, cls, _ in pecas]
    f = _FalsoIfc(pav_guid, entidades)
    elementos = [(i, g) for i, g, _, _ in pecas]
    malhas = {g: m for _, g, _, m in pecas}
    pedido = {
        "vista": {
            "tipo": "PLANTA",
            "pavimento": pav_guid,
            "escala": 1.0,
            "altura_corte_m": float(altura_corte_m),
        },
        "elementos": list(elementos),
    }
    if threads is not None:
        pedido["threads"] = threads
    return f, pedido, malhas, elementos


# ---------- parsers e metricas SVG ----------
def _extrair_polilinhas_d(d: str) -> tuple[list[str], list[np.ndarray]]:
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
    proj_groups: list[ET.Element] = []
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
                continue
            if "projection" in cls:
                proj_groups.append(elem)
            elif gid is not None:
                cut_by_guid.setdefault(gid, []).append(elem)
    return SimpleNamespace(
        root=root, proj_groups=proj_groups, cut_by_guid=cut_by_guid, all_paths=all_paths
    )


def _polilinhas_mundo(grupos: list[ET.Element], *, ox: float = 0.0, oy: float = 0.0) -> list[np.ndarray]:
    out: list[np.ndarray] = []
    for g in grupos:
        for p in g.iter():
            if p.tag.rsplit("}", 1)[-1] == "path":
                _, runs = _extrair_polilinhas_d(p.get("d") or "")
                for r in runs:
                    pts = r.copy()
                    pts[:, 0] = pts[:, 0] - float(ox)
                    pts[:, 1] = -pts[:, 1] - float(oy)
                    out.append(pts)
    return out


def _polilinhas_para_segs(polilinhas: list[np.ndarray]) -> np.ndarray:
    partes = []
    for pl in polilinhas:
        if len(pl) >= 2:
            s = np.hstack([pl[:-1], pl[1:]])
            lens = np.hypot(s[:, 2] - s[:, 0], s[:, 3] - s[:, 1])
            s = s[lens > 1e-12]
            if len(s):
                partes.append(s)
    return np.vstack(partes) if partes else np.zeros((0, 4), dtype=np.float64)


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


def _pontos_de_segs(segs: np.ndarray, *, sub_por_seg: int = 5) -> np.ndarray:
    if len(segs) == 0:
        return np.zeros((0, 2), dtype=np.float64)
    ts = np.linspace(0.0, 1.0, sub_por_seg + 1, dtype=np.float64)[:, None]
    a = segs[:, None, :2]
    d = (segs[:, 2:] - segs[:, :2])[:, None, :]
    return (a + ts[None, :, :] * d).reshape(-1, 2)


def _hausdorff_segs(segs_a: np.ndarray, segs_b: np.ndarray) -> float:
    if len(segs_a) == 0 and len(segs_b) == 0:
        return 0.0
    if len(segs_a) == 0 or len(segs_b) == 0:
        return float("inf")
    da = float(_dist_pontos_a_segs(_pontos_de_segs(segs_a), segs_b).max())
    db = float(_dist_pontos_a_segs(_pontos_de_segs(segs_b), segs_a).max())
    return max(da, db)


def _sha256(txt: str) -> str:
    return hashlib.sha256(txt.encode("utf-8")).hexdigest()


def _eh_fechada(pl: np.ndarray, tol: float = 1e-6) -> bool:
    return bool(len(pl) >= 4 and np.hypot(*(pl[0] - pl[-1])) <= tol)


# ---------- weakref helpers (memoria) ----------
class _DictRastreado(dict):
    pass


class _BufRastreado(bytearray):
    pass


def _array_rastreado(arr: np.ndarray) -> tuple[np.ndarray, weakref.ref]:
    contig = np.ascontiguousarray(arr)
    raw = _BufRastreado(contig.tobytes())
    view = np.frombuffer(raw, dtype=contig.dtype).reshape(contig.shape)
    return view, weakref.ref(raw)


# ---------- cena IFC sintetica com cache SQLite ----------
def _criar_caixa_ifc(f, body, classe: str, comp: float, esp: float, alt: float, pos: tuple[float, float, float]):
    api = ifcopenshell.api.run
    el = api("root.create_entity", f, ifc_class=classe)
    rep = api("geometry.add_wall_representation", f, context=body, length=comp, height=alt, thickness=esp)
    el.Representation = f.createIfcProductDefinitionShape(Representations=[rep])
    m = np.eye(4)
    m[:3, 3] = pos
    api("geometry.edit_object_placement", f, product=el, matrix=m, is_si=False)
    return el


def _criar_cena_ifc_4_paredes(tmp_path: Path) -> SimpleNamespace:
    api = ifcopenshell.api.run
    f = api("project.create_file", version="IFC4")
    proj = api("root.create_entity", f, ifc_class="IfcProject")
    api("unit.assign_unit", f, units=[f.createIfcSIUnit(UnitType="LENGTHUNIT", Prefix=None, Name="METRE")])
    ctx = api("context.add_context", f, context_type="Model")
    body = api(
        "context.add_context",
        f,
        context_type="Model",
        context_identifier="Body",
        target_view="MODEL_VIEW",
        parent=ctx,
    )
    site = api("root.create_entity", f, ifc_class="IfcSite")
    predio = api("root.create_entity", f, ifc_class="IfcBuilding")
    andar = api("root.create_entity", f, ifc_class="IfcBuildingStorey", name="Terreo")
    andar.Elevation = 0.0
    for filho, pai in ((site, proj), (predio, site), (andar, predio)):
        api("aggregate.assign_object", f, products=[filho], relating_object=pai)

    paredes = [
        _criar_caixa_ifc(f, body, "IfcWall", 2.0, 0.3, 2.8, (i * 5.0, 0.0, 0.0))
        for i in range(4)
    ]
    laje = _criar_caixa_ifc(f, body, "IfcSlab", 20.0, 4.0, 0.2, (0.0, -0.5, -0.2))
    api("spatial.assign_container", f, products=[*paredes, laje], relating_structure=andar)

    arq = tmp_path / "t24f_4paredes.ifc"
    f.write(str(arq))
    f = ifcopenshell.open(str(arq))
    andar = f.by_guid(andar.GlobalId)
    paredes = [f.by_guid(p.GlobalId) for p in paredes]
    laje = f.by_guid(laje.GlobalId)

    pasta = tmp_path / "cache_geo"
    doc = construtor.documento_de(arq)
    with construtor.abrir_banco(pasta) as cache:
        r = construtor.construir_lote(f, cache, construtor.fila_inicial(f), documento=doc, assinatura="s1", memo={})
        assert r["falhas"] == 0 and r["gravadas"] == 5

    todos = [*paredes, laje]
    vista = {"tipo": "PLANTA", "pavimento": andar.GlobalId, "escala": 1.0, "altura_corte_m": 1.2}
    pedido_base = {"arquivo": str(arq), "vista": vista, "elementos": [(e.id(), e.GlobalId) for e in todos], "threads": 1}
    return SimpleNamespace(
        arq=arq,
        pasta=pasta,
        andar=andar,
        paredes=paredes,
        laje=laje,
        pedido_base=pedido_base,
        pedido_cache={**pedido_base, "pasta_cache_geometria": str(pasta)},
    )


# ==========================================================================
# SANIDADE DA MALHA SINTETICA NAO-MANIFOLD EM T
# ==========================================================================
def test_sanidade_malha_em_t_nao_manifold_sem_bordas_gera_fechado_e_aberto():
    """Garante que a malha sintetica em T tem arestas com 3 tris, 0 bordas livres, 1 fechado e 1 aberto."""
    v, t = _caixas_fundidas_em_t_np()
    ec: Counter[tuple[int, int]] = Counter()
    for tri in t.tolist():
        for i in range(3):
            a, b = sorted((tri[i], tri[(i + 1) % 3]))
            ec[(a, b)] += 1
    assert 1 not in ec.values(), "malha em T nao pode ter buracos de borda"
    assert any(deg >= 3 for deg in ec.values()), "malha em T deve ter arestas nao-manifold com >= 3 tris"

    _, _, segs = corte_plano.cortar_malha_no_plano(v, t, 1.2)
    fechados, abertos = aneis.aneis_de_segmentos(segs)
    assert len(fechados) == 1 and len(abertos) == 1


# ==========================================================================
# REGRA 1: VERTICE NO PLANO -> DESLOCAMENTO GLOBAL DETERMINISTICO
# ==========================================================================
def test_regra1_vertice_no_plano_desloca_todas_as_pecas_para_mais_1e5(monkeypatch):
    """Malha grande com poucos vertices em z=1.2 + parede limpa + degrau: desloca TODAS para 1.2 + 1e-5."""
    zs_corte: list[float] = []
    real_corte = corte_plano.cortar_malha_no_plano

    def espia_corte(v, t, z):
        zs_corte.append(float(z))
        return real_corte(v, t, z)

    monkeypatch.setattr(corte_plano, "cortar_malha_no_plano", espia_corte)

    f, pedido, malhas, ev = _montar_cena_numpy(
        [
            (10, "G_MALHA_VERT", "IfcWall", _malha_grande_poucos_vertices_no_plano_np(0.0, 0.0, 0.0, 4.0, 0.3, 2.8, 1.2)),
            (11, "G_PAREDE_LIMPA", "IfcWall", _caixa_np(0.0, 2.0, 0.0, 4.0, 2.3, 2.8)),
            (12, "G_DEGRAU", "IfcWall", _degrau_no_plano_np(1.2, dx=6.0, dy=0.0)),
            (13, "G_LAJE", "IfcSlab", _caixa_np(0.0, 0.0, -0.2, 8.0, 3.0, 0.0)),
            (14, "G_VIGA_ACIMA", "IfcBeam", _caixa_np(0.0, 0.0, 2.4, 4.0, 0.3, 2.8)),
        ],
        altura_corte_m=1.2,
    )
    resp, motivo = planta_cache.desenhar_planta_cache(f, pedido, malhas, ev)
    assert motivo is None and resp is not None and resp["ok"] is True
    assert resp["secoes_parciais"] == 0 and type(resp["secoes_parciais"]) is int
    assert len(zs_corte) == 3
    assert all(z == pytest.approx(1.2 + 1e-5, abs=1e-12) for z in zs_corte), f"zs_corte={zs_corte}"

    parsed = _parse_svg(resp["svg"])
    assert set(parsed.cut_by_guid.keys()) == {"G_MALHA_VERT", "G_PAREDE_LIMPA", "G_DEGRAU"}
    assert set(resp["enviados"]) == {10, 11, 12, 13}
    for gid in ("G_MALHA_VERT", "G_PAREDE_LIMPA", "G_DEGRAU"):
        pls = _polilinhas_mundo(parsed.cut_by_guid[gid])
        assert len(pls) >= 1 and all(_eh_fechada(pl) for pl in pls)
    estilo.aplicar_estilo(resp["svg"], "1:50")


def test_regra1_peca_nao_cortada_com_vertice_no_plano_tambem_desloca(monkeypatch):
    """Mesmo se a peca com vertice em z=1.2 for nao-cortada (topo em 1.2), o plano de TODAS desloca."""
    zs_corte: list[float] = []
    real_corte = corte_plano.cortar_malha_no_plano
    monkeypatch.setattr(
        corte_plano,
        "cortar_malha_no_plano",
        lambda v, t, z: (zs_corte.append(float(z)), real_corte(v, t, z))[1],
    )

    f, pedido, malhas, ev = _montar_cena_numpy(
        [
            (10, "G_PAREDE", "IfcWall", _caixa_np(0.0, 0.0, 0.0, 4.0, 0.3, 2.8)),
            (11, "G_BANCADA_TOPO_12", "IfcFurnishingElement", _caixa_np(1.0, 1.0, 0.0, 2.0, 1.8, 1.2)),
        ],
        altura_corte_m=1.2,
    )
    resp, motivo = planta_cache.desenhar_planta_cache(f, pedido, malhas, ev)
    assert motivo is None and resp is not None and resp["ok"] is True
    assert resp["secoes_parciais"] == 0
    assert zs_corte == [pytest.approx(1.2 + 1e-5, abs=1e-12)]

    parsed = _parse_svg(resp["svg"])
    # Bancada [0, 1.2] ficou estritamente abaixo de 1.2 + 1e-5 -> projecao, nao corte
    assert set(parsed.cut_by_guid.keys()) == {"G_PAREDE"}
    assert set(resp["enviados"]) == {10, 11}
    segs_proj = _polilinhas_para_segs(_polilinhas_mundo(parsed.proj_groups))
    pts_bancada = np.array([[1.0, 1.4], [2.0, 1.4], [1.5, 1.0], [1.5, 1.8]], dtype=np.float64)
    assert float(_dist_pontos_a_segs(pts_bancada, segs_proj).max()) <= 1e-4


@pytest.mark.parametrize(
    ("bloqueados", "delta_esperado"),
    [
        pytest.param((0.0,), 1e-5, id="delta_p1e5"),
        pytest.param((0.0, 1e-5), -1e-5, id="delta_m1e5"),
        pytest.param((0.0, 1e-5, -1e-5), 3.7e-5, id="delta_p3p7e5"),
        pytest.param((0.0, 1e-5, -1e-5, 3.7e-5), -3.7e-5, id="delta_m3p7e5"),
    ],
)
def test_regra1_ordem_exata_dos_deltas_candidatos(monkeypatch, bloqueados, delta_esperado):
    """Tenta deltas na ordem (+1e-5, -1e-5, +3.7e-5, -3.7e-5) e usa o primeiro sem vertice <= eps."""
    zs_corte: list[float] = []
    real_corte = corte_plano.cortar_malha_no_plano
    monkeypatch.setattr(
        corte_plano,
        "cortar_malha_no_plano",
        lambda v, t, z: (zs_corte.append(float(z)), real_corte(v, t, z))[1],
    )

    z0 = 1.2
    peca_bloq = _caixa_com_aneis_z_np(0.0, 0.0, 0.0, 2.0, 0.3, 2.8, [z0 + d for d in bloqueados])
    f, pedido, malhas, ev = _montar_cena_numpy(
        [
            (10, "G_BLOQ", "IfcWall", peca_bloq),
            (11, "G_LIMPA", "IfcWall", _caixa_np(4.0, 0.0, 0.0, 6.0, 0.3, 2.8)),
        ],
        altura_corte_m=z0,
    )
    resp, motivo = planta_cache.desenhar_planta_cache(f, pedido, malhas, ev)
    assert motivo is None and resp is not None and resp["ok"] is True
    assert resp["secoes_parciais"] == 0
    assert len(zs_corte) == 2
    assert all(z == pytest.approx(z0 + delta_esperado, abs=1e-12) for z in zs_corte)


def test_regra1_coerencia_classificacao_acima_pula_delta_que_corta_peca_acima(monkeypatch):
    """Peca estritamente acima em z + 5e-6: delta +1e-5 a cortaria, entao escolhe -1e-5 e mantem acima."""
    zs_corte: list[float] = []
    real_corte = corte_plano.cortar_malha_no_plano
    monkeypatch.setattr(
        corte_plano,
        "cortar_malha_no_plano",
        lambda v, t, z: (zs_corte.append(float(z)), real_corte(v, t, z))[1],
    )

    z0 = 1.2
    f, pedido, malhas, ev = _montar_cena_numpy(
        [
            (10, "G_PAREDE_VERT", "IfcWall", _caixa_com_aneis_z_np(0.0, 0.0, 0.0, 2.0, 0.3, 2.8, [z0])),
            (11, "G_VIGA_LOGO_ACIMA", "IfcBeam", _caixa_np(5.0, 5.0, z0 + 5e-6, 7.0, 5.4, 2.5)),
        ],
        altura_corte_m=z0,
    )
    resp, motivo = planta_cache.desenhar_planta_cache(f, pedido, malhas, ev)
    assert motivo is None and resp is not None and resp["ok"] is True
    assert zs_corte == [pytest.approx(z0 - 1e-5, abs=1e-12)]
    assert resp["enviados"] == [10]
    parsed = _parse_svg(resp["svg"])
    assert set(parsed.cut_by_guid.keys()) == {"G_PAREDE_VERT"}
    assert "G_VIGA_LOGO_ACIMA" not in resp["svg"]


def test_regra1_vertice_impossivel_todos_deltas_ocupados_cai_secao_aberta():
    """Vertices em z, z+1e-5, z-1e-5, z+3.7e-5 e z-3.7e-5 -> nenhum delta serve -> queda secao_aberta."""
    z0 = 1.2
    todos_zs = [z0, *(z0 + d for d in _DELTAS_ORDEM)]
    f, pedido, malhas, ev = _montar_cena_numpy(
        [
            (10, "G_IMPOSSIVEL", "IfcWall", _caixa_com_aneis_z_np(0.0, 0.0, 0.0, 2.0, 0.3, 2.8, todos_zs)),
            (11, "G_LIMPA", "IfcWall", _caixa_np(4.0, 0.0, 0.0, 6.0, 0.3, 2.8)),
        ],
        altura_corte_m=z0,
    )
    resp, motivo = planta_cache.desenhar_planta_cache(f, pedido, malhas, ev)
    assert resp is None and motivo == "secao_aberta"


def test_mutante_vertice_desloca_so_peca_afetada_e_nao_todas(monkeypatch):
    """Mutante: deslocar z apenas na peca com vertice no plano deixaria parede inclinada em z=1.2."""
    zs_corte: list[float] = []
    real_corte = corte_plano.cortar_malha_no_plano
    monkeypatch.setattr(
        corte_plano,
        "cortar_malha_no_plano",
        lambda v, t, z: (zs_corte.append(float(z)), real_corte(v, t, z))[1],
    )

    z0 = 1.2
    # Parede inclinada com dx/dz = 2.0: em z=1.2 -> x_min=12.400000; em z=1.2+1e-5 -> x_min=12.400020
    f, pedido, malhas, ev = _montar_cena_numpy(
        [
            (10, "G_VERT", "IfcWall", _caixa_com_aneis_z_np(0.0, 0.0, 0.0, 2.0, 0.3, 2.8, [z0])),
            (11, "G_INCLINADA", "IfcWall", _parede_inclinada_np(10.0, 0.0, 1.0, 0.0, 2.8, esp=0.3, inclinacao_dx_dz=2.0)),
        ],
        altura_corte_m=z0,
    )
    resp, motivo = planta_cache.desenhar_planta_cache(f, pedido, malhas, ev)
    assert motivo is None and resp is not None and resp["ok"] is True
    assert len(zs_corte) == 2
    assert all(z == pytest.approx(z0 + 1e-5, abs=1e-12) for z in zs_corte)

    parsed = _parse_svg(resp["svg"])
    pls_inc = _polilinhas_mundo(parsed.cut_by_guid["G_INCLINADA"])
    xmin_inc = float(min(pl[:, 0].min() for pl in pls_inc))
    assert xmin_inc == pytest.approx(10.0 + 2.0 * (z0 + 1e-5), abs=2e-6), (
        f"parede inclinada cortada fora do plano deslocado: xmin={xmin_inc:.6f}"
    )


# ==========================================================================
# REGRA 2 E 4: ANEIS ABERTOS (MISTOS E 100% ABERTOS), TAMPA E NAO-OMISSAO
# ==========================================================================
def test_regra2_secao_mista_fechados_e_abertos_nao_manifold_tampa_e_telemetria(monkeypatch):
    """Duas caixas fundidas em T (1 fechado + 1 aberto): fechado tampa, aberto desenha M/L sem Z e nao tampa."""
    recorte_args: list[list] = []
    real_recorte = recorte.recortar_fora_dos_aneis

    def espia_recorte(pols, grupos, *a, **k):
        recorte_args.append(list(grupos))
        return real_recorte(pols, grupos, *a, **k)

    monkeypatch.setattr(recorte, "recortar_fora_dos_aneis", espia_recorte)

    # Barra de piso em x in [0.95, 1.05], y in [-0.5, 2.5]:
    # - cruza interior do anel fechado [0..2, 0..0.4] em y=0.2 (DEVE ser tampada)
    # - cruza interior do ramo aberto [0.8..1.2, 0.4..2.0] em y=1.2 (NAO pode ser tampada)
    f, pedido, malhas, ev = _montar_cena_numpy(
        [
            (10, "G_PAREDE_T", "IfcWall", _caixas_fundidas_em_t_np(0.0, 0.0, 0.0, 2.8)),
            (11, "G_BARRA_PISO", "IfcSlab", _caixa_np(0.95, -0.5, 0.0, 1.05, 2.5, 0.2)),
            (12, "G_PAREDE_B1", "IfcWall", _caixa_np(5.0, 0.0, 0.0, 7.0, 0.3, 2.8)),
            (13, "G_PAREDE_B2", "IfcWall", _caixa_np(5.0, 2.0, 0.0, 7.0, 2.3, 2.8)),
            (14, "G_PAREDE_B3", "IfcWall", _caixa_np(5.0, 4.0, 0.0, 7.0, 4.3, 2.8)),
        ],
        altura_corte_m=1.2,
    )
    resp, motivo = planta_cache.desenhar_planta_cache(f, pedido, malhas, ev, abrir_s=0.02, cache_s=0.03)
    assert motivo is None and resp is not None and resp["ok"] is True
    assert resp["secoes_parciais"] == 1 and type(resp["secoes_parciais"]) is int
    assert set(resp["enviados"]) == {10, 11, 12, 13, 14}
    assert resp["caixas"] == [] and resp["em_cache"] == [] and resp["pesados"] == [] and resp["falhas_geometria"] == []
    assert set(resp["tempos"].keys()) == {"abrir_s", "geo_s", "write_s", "finalize_s", "cache_s", "corte_s", "motor_s"}

    svg = resp["svg"]
    assert "-0.000000" not in svg
    parsed = _parse_svg(svg)
    assert set(parsed.cut_by_guid.keys()) == {"G_PAREDE_T", "G_PAREDE_B1", "G_PAREDE_B2", "G_PAREDE_B3"}

    # Verifica comandos exclusivamente M/L (sem Z) em todos os paths
    for p_el in parsed.all_paths:
        cmds, _ = _extrair_polilinhas_d(p_el.get("d") or "")
        assert cmds and set(cmds).issubset({"M", "L"})
        assert "Z" not in cmds and "z" not in cmds

    # G_PAREDE_T deve ter 1 subcaminho fechado e 1 subcaminho aberto (sem fechar!)
    pls_t = _polilinhas_mundo(parsed.cut_by_guid["G_PAREDE_T"])
    fechadas_t = [pl for pl in pls_t if _eh_fechada(pl)]
    abertas_t = [pl for pl in pls_t if not _eh_fechada(pl)]
    assert len(fechadas_t) == 1, f"esperado 1 anel fechado em G_PAREDE_T, obtido {len(fechadas_t)}"
    assert len(abertas_t) == 1, f"esperado 1 cadeia aberta em G_PAREDE_T, obtido {len(abertas_t)}"

    # A cadeia aberta liga (0.8, 0.4) -> (0.8, 2.0) -> (1.2, 2.0) -> (1.2, 0.4) sem segmento fechando a base
    segs_aberta = _polilinhas_para_segs(abertas_t)
    pts_ramo = np.array([[0.8, 1.2], [1.0, 2.0], [1.2, 1.2]], dtype=np.float64)
    assert float(_dist_pontos_a_segs(pts_ramo, segs_aberta).max()) <= 1e-4
    assert float(_dist_pontos_a_segs(np.array([[1.0, 0.4]]), segs_aberta).min()) > 0.1, (
        "cadeia aberta foi fechada indevidamente ligando extremos"
    )

    # Tampa: recortou a barra dentro do anel fechado (y=0.2), mas NAO recortou no ramo aberto (y=1.2)
    assert len(recorte_args) == 1
    segs_proj = _polilinhas_para_segs(_polilinhas_mundo(parsed.proj_groups))
    pts_tampados = np.array([[0.95, 0.2], [1.05, 0.2]], dtype=np.float64)
    assert float(_dist_pontos_a_segs(pts_tampados, segs_proj).min()) > 0.05
    pts_nao_tampados = np.array([[0.95, 1.2], [1.05, 1.2]], dtype=np.float64)
    assert float(_dist_pontos_a_segs(pts_nao_tampados, segs_proj).max()) <= 1e-3

    # Compativel com estilo.aplicar_estilo
    estilizado = estilo.aplicar_estilo(svg, "1:50")
    p_est = _parse_svg(estilizado)
    assert "cut" in (p_est.cut_by_guid["G_PAREDE_T"][0].get("class") or "").split()


def test_regra2_peca_100_porcento_aberta_aceita_sem_tampa_e_sem_omissao():
    """Peca cortada so com cadeias abertas (0 fechados): aceita como parcial, desenha aberta, nao tampa."""
    # 1) 1 unica peca cortada 100% aberta (ceil(0.25*1) == 1 -> aceita) + barra de piso atravessando
    f1, p1, m1, e1 = _montar_cena_numpy(
        [
            (10, "G_SO_ABERTA", "IfcWall", _caixa_100_aberta_np(0.0, 0.0, 0.0, 2.0, 1.0, 2.8)),
            (11, "G_BARRA", "IfcSlab", _caixa_np(0.9, -0.5, 0.0, 1.1, 1.5, 0.2)),
        ],
        altura_corte_m=1.2,
    )
    r1, mot1 = planta_cache.desenhar_planta_cache(f1, p1, m1, e1)
    assert mot1 is None and r1 is not None and r1["ok"] is True
    assert r1["secoes_parciais"] == 1 and type(r1["secoes_parciais"]) is int
    assert set(r1["enviados"]) == {10, 11}

    parsed = _parse_svg(r1["svg"])
    assert set(parsed.cut_by_guid.keys()) == {"G_SO_ABERTA"}
    pls = _polilinhas_mundo(parsed.cut_by_guid["G_SO_ABERTA"])
    assert len(pls) == 1 and not _eh_fechada(pls[0]), "subcaminho 100% aberto nao pode ser fechado"

    # Sem tampa: barra continua visivel no centro (x=0.9..1.1, y=0.5)
    segs_proj = _polilinhas_para_segs(_polilinhas_mundo(parsed.proj_groups))
    pts_centro = np.array([[0.9, 0.5], [1.1, 0.5]], dtype=np.float64)
    assert float(_dist_pontos_a_segs(pts_centro, segs_proj).max()) <= 1e-3

    # Verifica tambem ausencia de Z e compatibilidade com estilo
    for p_el in parsed.all_paths:
        cmds, _ = _extrair_polilinhas_d(p_el.get("d") or "")
        assert set(cmds).issubset({"M", "L"})
    estilo.aplicar_estilo(r1["svg"], "1:50")


def test_regra2_peca_cortada_sem_fechados_e_sem_segmentos_cai_secao_aberta():
    """Peca cortada sem nenhum anel fechado e sem nenhum segmento -> sempre cai secao_aberta (mesmo 1 de 6)."""
    pecas = [(10 + i, f"G_BOA_{i}", "IfcWall", _caixa_np(i * 4.0, 0.0, 0.0, i * 4.0 + 2.0, 0.3, 2.8)) for i in range(5)]
    pecas.append((99, "G_SEM_SEGS", "IfcWall", _malha_sem_segmentos_corte_np(30.0, 0.0, 0.0, 32.0, 0.5, 2.8)))
    f, pedido, malhas, ev = _montar_cena_numpy(pecas, altura_corte_m=1.2)
    resp, motivo = planta_cache.desenhar_planta_cache(f, pedido, malhas, ev)
    assert resp is None and motivo == "secao_aberta"


def test_regra2_cena_limpa_reporta_secoes_parciais_zero():
    """Cena sem cadeias abertas reporta resp['secoes_parciais'] == 0 (int)."""
    f, pedido, malhas, ev = _montar_cena_numpy(
        [
            (10, "G_PAREDE", "IfcWall", _caixa_np(0.0, 0.0, 0.0, 4.0, 0.3, 2.8)),
            (11, "G_LAJE", "IfcSlab", _caixa_np(0.0, 0.0, -0.2, 4.0, 3.0, 0.0)),
        ],
        altura_corte_m=1.2,
    )
    resp, motivo = planta_cache.desenhar_planta_cache(f, pedido, malhas, ev)
    assert motivo is None and resp is not None and resp["ok"] is True
    assert "secoes_parciais" in resp
    assert type(resp["secoes_parciais"]) is int and resp["secoes_parciais"] == 0


# ==========================================================================
# REGRA 3: LIMITE DE SEGURANCA DE 25% (ceil(0.25 * n_cortadas))
# ==========================================================================
@pytest.mark.parametrize(
    ("n_cortadas", "n_parciais", "deve_aceitar"),
    [
        (1, 1, True),   # ceil(0.25) = 1
        (2, 1, True),   # ceil(0.50) = 1
        (2, 2, False),  # 2 > 1
        (4, 1, True),   # ceil(1.00) = 1
        (4, 2, False),  # 2 > 1
        (5, 2, True),   # ceil(1.25) = 2
        (5, 3, False),  # 3 > 2
        (8, 2, True),   # ceil(2.00) = 2
        (8, 3, False),  # 3 > 2
    ],
)
def test_regra3_limite_25_porcento_ceil(n_cortadas: int, n_parciais: int, deve_aceitar: bool):
    """Fronteira exata de ceil(0.25 * n_cortadas): aceita <= limite, cai secao_aberta se > limite."""
    assert (n_parciais <= math.ceil(0.25 * n_cortadas)) is deve_aceitar
    pecas = []
    for i in range(n_cortadas):
        x0 = i * 4.0
        if i < n_parciais:
            malha = _caixas_fundidas_em_t_np(dx=x0, dy=0.0) if (i % 2 == 0) else _caixa_100_aberta_np(x0, 0.0, 0.0, x0 + 2.0, 0.4, 2.8)
            pecas.append((10 + i, f"G_PARC_{i:02d}", "IfcWall", malha))
        else:
            pecas.append((10 + i, f"G_BOA_{i:02d}", "IfcWall", _caixa_np(x0, 0.0, 0.0, x0 + 2.0, 0.4, 2.8)))

    f, pedido, malhas, ev = _montar_cena_numpy(pecas, altura_corte_m=1.2)
    resp, motivo = planta_cache.desenhar_planta_cache(f, pedido, malhas, ev)
    if deve_aceitar:
        assert motivo is None and resp is not None and resp["ok"] is True
        assert resp["secoes_parciais"] == n_parciais and type(resp["secoes_parciais"]) is int
        parsed = _parse_svg(resp["svg"])
        assert len(parsed.cut_by_guid) == n_cortadas, "nenhuma peca cortada pode ser omitida"
    else:
        assert resp is None and motivo == "secao_aberta"


def test_mutante_limite_25_usa_apenas_pecas_cortadas_no_denominador():
    """Mutante: incluir pecas abaixo/acima no denominador aceitaria 2/2 parciais com 10 lajes abaixo."""
    pecas = [
        (10, "G_PARC_1", "IfcWall", _caixas_fundidas_em_t_np(0.0, 0.0)),
        (11, "G_PARC_2", "IfcWall", _caixa_100_aberta_np(5.0, 0.0, 0.0, 7.0, 0.4, 2.8)),
    ]
    for i in range(10):
        pecas.append((20 + i, f"G_ABAIXO_{i:02d}", "IfcSlab", _caixa_np(i * 2.0, 5.0, -0.2, i * 2.0 + 1.0, 6.0, 0.0)))
    for i in range(4):
        pecas.append((40 + i, f"G_ACIMA_{i:02d}", "IfcBeam", _caixa_np(i * 2.0, 8.0, 2.2, i * 2.0 + 1.0, 8.4, 2.8)))

    f, pedido, malhas, ev = _montar_cena_numpy(pecas, altura_corte_m=1.2)
    resp, motivo = planta_cache.desenhar_planta_cache(f, pedido, malhas, ev)
    assert resp is None and motivo == "secao_aberta"


# ==========================================================================
# REGRA 4: NUNCA OMITIR ELEMENTO (CENA COMBINADA)
# ==========================================================================
def test_regra4_nunca_omitir_elemento_cena_combinada_shift_e_parciais():
    """Cena com vertice no plano + parcial T + parcial 100% aberta + 6 boas + 2 abaixo + 1 acima: nada omitido."""
    pecas = [
        (10, "G_VERT", "IfcWall", _caixa_com_aneis_z_np(0.0, 0.0, 0.0, 2.0, 0.3, 2.8, [1.2])),
        (11, "G_PARC_T", "IfcWall", _caixas_fundidas_em_t_np(4.0, 0.0)),
        (12, "G_PARC_AB", "IfcWall", _caixa_100_aberta_np(8.0, 0.0, 0.0, 10.0, 0.4, 2.8)),
    ]
    for i in range(5):
        x0 = 12.0 + i * 4.0
        pecas.append((13 + i, f"G_BOA_{i}", "IfcWall", _caixa_np(x0, 0.0, 0.0, x0 + 2.0, 0.3, 2.8)))
    # 8 cortadas, 2 parciais -> 2 <= ceil(0.25*8) == 2
    pecas.append((30, "G_LAJE", "IfcSlab", _caixa_np(0.0, 4.0, -0.2, 4.0, 6.0, 0.0)))
    pecas.append((31, "G_MOVEL", "IfcFurnishingElement", _caixa_np(10.0, 4.0, 0.0, 12.0, 5.5, 0.6)))
    pecas.append((32, "G_VIGA_ACIMA", "IfcBeam", _caixa_np(0.0, 8.0, 2.2, 4.0, 8.4, 2.8)))

    f, pedido, malhas, ev = _montar_cena_numpy(pecas, altura_corte_m=1.2)
    resp, motivo = planta_cache.desenhar_planta_cache(f, pedido, malhas, ev)
    assert motivo is None and resp is not None and resp["ok"] is True
    assert resp["secoes_parciais"] == 2
    assert set(resp["enviados"]) == {10, 11, 12, 13, 14, 15, 16, 17, 30, 31}

    parsed = _parse_svg(resp["svg"])
    assert set(parsed.cut_by_guid.keys()) == {
        "G_VERT", "G_PARC_T", "G_PARC_AB", "G_BOA_0", "G_BOA_1", "G_BOA_2", "G_BOA_3", "G_BOA_4"
    }
    assert "G_VIGA_ACIMA" not in resp["svg"]

    # Laje e movel abaixo presentes na projecao
    segs_proj = _polilinhas_para_segs(_polilinhas_mundo(parsed.proj_groups))
    assert float(_dist_pontos_a_segs(np.array([[2.0, 4.0], [2.0, 6.0]]), segs_proj).max()) <= 1e-3
    assert float(_dist_pontos_a_segs(np.array([[11.0, 4.0], [11.0, 5.5]]), segs_proj).max()) <= 1e-3


# ==========================================================================
# REGRA 5: TELEMETRIA INTEGRADA (desenho.processar, Planta, gerente)
# ==========================================================================
def test_regra5_desenho_processar_propaga_secoes_parciais_shift_e_queda(tmp_path, monkeypatch):
    """desenho.processar propaga secoes_parciais no sucesso (via_cache=True) e cai secao_aberta quando >25%."""
    cena = _criar_cena_ifc_4_paredes(tmp_path)
    base = desenho.processar(cena.pedido_base)
    assert base["ok"] is True
    real_ler = desenho.cache_leitura.malhas_do_cache

    # 1) 1 de 4 paredes nao-manifold em T (25%) -> via_cache=True, queda=None, secoes_parciais=1
    def ler_1_parcial(cache, doc, ids):
        malhas, falt = real_ler(cache, doc, ids)
        malhas[cena.paredes[0].GlobalId] = _caixas_fundidas_em_t_np(0.0, 0.0, 0.0, 2.8)
        return malhas, falt

    monkeypatch.setattr(desenho.cache_leitura, "malhas_do_cache", ler_1_parcial)
    r1 = desenho.processar(cena.pedido_cache)
    assert r1["ok"] is True and r1["via_cache"] is True and r1["queda"] is None
    assert type(r1["secoes_parciais"]) is int and r1["secoes_parciais"] == 1

    # 2) Parede com vertice exatamente no plano 1.2 -> via_cache=True, queda=None, secoes_parciais=0
    def ler_vertice_plano(cache, doc, ids):
        malhas, falt = real_ler(cache, doc, ids)
        malhas[cena.paredes[0].GlobalId] = _caixa_com_aneis_z_np(0.0, 0.0, 0.0, 2.0, 0.3, 2.8, [1.2])
        return malhas, falt

    monkeypatch.setattr(desenho.cache_leitura, "malhas_do_cache", ler_vertice_plano)
    r2 = desenho.processar(cena.pedido_cache)
    assert r2["ok"] is True and r2["via_cache"] is True and r2["queda"] is None
    assert type(r2["secoes_parciais"]) is int and r2["secoes_parciais"] == 0

    # 3) 2 de 4 paredes parciais (>25%) -> queda secao_aberta, via_cache=False, secoes_parciais=0
    def ler_2_parciais(cache, doc, ids):
        malhas, falt = real_ler(cache, doc, ids)
        malhas[cena.paredes[0].GlobalId] = _caixas_fundidas_em_t_np(0.0, 0.0, 0.0, 2.8)
        malhas[cena.paredes[1].GlobalId] = _caixa_100_aberta_np(5.0, 0.0, 0.0, 7.0, 0.3, 2.8)
        return malhas, falt

    monkeypatch.setattr(desenho.cache_leitura, "malhas_do_cache", ler_2_parciais)
    r3 = desenho.processar(cena.pedido_cache)
    assert r3["ok"] is True and r3["via_cache"] is False and r3["queda"] == "secao_aberta"
    assert type(r3["secoes_parciais"]) is int and r3["secoes_parciais"] == 0
    assert r3["svg"] == base["svg"]


def test_regra5_planta_e_gerente_propagam_secoes_parciais(monkeypatch, tmp_path):
    """Planta.secoes_parciais (default 0) e gerente._motor_padrao['secoes_parciais'] propagados como int."""
    sel = Selecao(
        ids=(101,),
        tipo="PLANTA",
        pavimento=10,
        faixa=None,
        ocultos_por_classe={},
        sem_geometria=0,
        caixas_envolventes={101: (0.0, 0.0, 0.0, 4.0, 0.2, 3.0)},
    )
    svg_min = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1 1"><path d="M 0,0 L 1,0"/></svg>'
    pl_def = app_planta.Planta(
        svg=svg_min,
        n_paths=1,
        selecao=sel,
        tempos={"geo_s": 0.0},
        unidade_escala=1.0,
        altura_corte=1.2,
        caixas=(),
    )
    assert type(pl_def.secoes_parciais) is int and pl_def.secoes_parciais == 0

    # gerar_planta propaga secoes_parciais da resposta do auxiliar
    class _El:
        def __init__(self, i, g, cls):
            self._i, self.GlobalId, self._cls = i, g, cls
            self.ObjectPlacement = None
            self.Elevation = 0.0

        def id(self):
            return self._i

        def is_a(self, nome=None):
            return self._cls if nome is None else self._cls == nome

    pav = _El(10, "PAV", "IfcBuildingStorey")
    ann = _El(20, "VISTA", "IfcAnnotation")
    w1 = _El(101, "W1", "IfcWall")
    ifc_fake = SimpleNamespace(
        by_id=lambda i: {10: pav, 20: ann, 101: w1}[int(i)],
        by_guid=lambda g: {"PAV": pav, "VISTA": ann, "W1": w1}[g],
    )
    monkeypatch.setattr(vistas_ifc, "ler_vista", lambda _f, _g: {"tipo": "PLANTA"})
    monkeypatch.setattr(app_planta, "_altura_corte", lambda _f, _a: 1.2)
    monkeypatch.setattr(app_planta.ifcopenshell.util.unit, "calculate_unit_scale", lambda _f: 1.0)
    monkeypatch.setattr(app_selecao, "_validar_categorias", lambda _f, _c: None)
    monkeypatch.setattr(app_selecao, "selecionar", lambda _f, _g, **kw: sel)

    arq = tmp_path / "m.ifc"
    arq.write_text("ISO-10303-21;\nEND-ISO-10303-21;\n", encoding="utf-8")
    pl = app_planta.gerar_planta(
        ifc_fake,
        "VISTA",
        caminho_ifc=arq,
        pasta_cache_geometria=tmp_path / "geo",
        executor=lambda _q: {
            "ok": True,
            "svg": svg_min,
            "n_paths": 1,
            "enviados": [101],
            "caixas": [],
            "em_cache": [],
            "pesados": [],
            "falhas_geometria": [],
            "tempos": {"abrir_s": 0.0, "geo_s": 0.0, "write_s": 0.0, "finalize_s": 0.0, "cache_s": 0.01, "motor_s": 0.02},
            "via_cache": True,
            "queda": None,
            "n_faltantes": 0,
            "secoes_parciais": 2,
        },
    )
    assert type(pl.secoes_parciais) is int and pl.secoes_parciais == 2

    # gerente._motor_padrao propaga secoes_parciais em dados
    monkeypatch.setenv("OBIM_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setattr(app_planta, "gerar_planta", lambda *a, **kw: pl)
    dados = app_gerente._motor_padrao(
        "planta",
        ifc_fake,
        "VISTA",
        {"caminho_ifc": arq},
        cancelar=threading.Event(),
        progresso=lambda _m: None,
        cache=app_cache.CacheDesenho(tmp_path / "vista"),
    )
    assert type(dados["secoes_parciais"]) is int and dados["secoes_parciais"] == 2


# ==========================================================================
# REGRA 6: DETERMINISMO, IMUTABILIDADE, UTM E LIBERACAO DE MEMORIA
# ==========================================================================
def test_regra6_determinismo_sha256_3_rodadas_embaralhada_e_threads():
    """SHA-256 do SVG identico em 3 rodadas, entrada embaralhada e threads=4 com shift + parciais."""
    pecas = [
        (10, "G_03_VERT", "IfcWall", _caixa_com_aneis_z_np(0.0, 0.0, 0.0, 2.0, 0.3, 2.8, [1.2])),
        (11, "G_01_T", "IfcWall", _caixas_fundidas_em_t_np(4.0, 0.0)),
        (12, "G_04_BOA1", "IfcWall", _caixa_np(8.0, 0.0, 0.0, 10.0, 0.3, 2.8)),
        (13, "G_02_BOA2", "IfcWall", _caixa_np(12.0, 0.0, 0.0, 14.0, 0.3, 2.8)),
        (14, "G_05_LAJE", "IfcSlab", _caixa_np(0.0, -0.5, -0.2, 15.0, 3.0, 0.0)),
    ]
    f1, p1, m1, e1 = _montar_cena_numpy(pecas, altura_corte_m=1.2, threads=1)
    shas = []
    for _ in range(3):
        r, mot = planta_cache.desenhar_planta_cache(f1, p1, m1, e1)
        assert mot is None and r is not None and r["ok"] is True and r["secoes_parciais"] == 1
        shas.append(_sha256(r["svg"]))
    assert shas[0] == shas[1] == shas[2]

    # Entrada embaralhada (reversa) -> mesmo SHA
    f_rev, p_rev, m_rev, e_rev = _montar_cena_numpy(list(reversed(pecas)), altura_corte_m=1.2, threads=1)
    r_rev, mot_rev = planta_cache.desenhar_planta_cache(f_rev, p_rev, m_rev, e_rev)
    assert mot_rev is None and _sha256(r_rev["svg"]) == shas[0]

    # threads=4 -> mesmo SHA
    f_t4, p_t4, m_t4, e_t4 = _montar_cena_numpy(pecas, altura_corte_m=1.2, threads=4)
    r_t4, mot_t4 = planta_cache.desenhar_planta_cache(f_t4, p_t4, m_t4, e_t4)
    assert mot_t4 is None and _sha256(r_t4["svg"]) == shas[0]


def test_regra6_nao_muta_malhas_mundo_nem_pedido_readonly_utm():
    """malhas_mundo (com arrays read-only) e pedido nao sao mutados mesmo com shift + parciais em UTM."""
    ox, oy = 500_000.123456, 7_500_000.654321
    pecas = [
        (10, "G_VERT", "IfcWall", _transladar_malha(_caixa_com_aneis_z_np(0.0, 0.0, 0.0, 2.0, 0.3, 2.8, [1.2]), ox, oy)),
        (11, "G_PARC_T", "IfcWall", _transladar_malha(_caixas_fundidas_em_t_np(4.0, 0.0), ox, oy)),
        (12, "G_BOA1", "IfcWall", _transladar_malha(_caixa_np(8.0, 0.0, 0.0, 10.0, 0.3, 2.8), ox, oy)),
        (13, "G_BOA2", "IfcWall", _transladar_malha(_caixa_np(12.0, 0.0, 0.0, 14.0, 0.3, 2.8), ox, oy)),
        (14, "G_BARRA", "IfcSlab", _transladar_malha(_caixa_np(4.95, -0.5, 0.0, 5.05, 2.5, 0.2), ox, oy)),
    ]
    f, pedido, malhas, ev = _montar_cena_numpy(pecas, altura_corte_m=1.2)
    copia_chaves = list(malhas.keys())
    copia_malhas = {g: (v.copy(), t.copy()) for g, (v, t) in malhas.items()}
    copia_pedido = {
        k: (dict(v) if isinstance(v, dict) else list(v) if isinstance(v, list) else v)
        for k, v in pedido.items()
    }
    for v, t in malhas.values():
        v.setflags(write=False)
        t.setflags(write=False)

    resp, motivo = planta_cache.desenhar_planta_cache(f, pedido, malhas, ev)
    assert motivo is None and resp is not None and resp["ok"] is True
    assert resp["secoes_parciais"] == 1
    assert list(malhas.keys()) == copia_chaves
    for g, (v0, t0) in copia_malhas.items():
        np.testing.assert_array_equal(malhas[g][0], v0)
        np.testing.assert_array_equal(malhas[g][1], t0)
    assert pedido == copia_pedido


@pytest.mark.parametrize(
    ("ox", "oy", "oz"),
    [
        pytest.param(500_000.123456, 7_500_000.654321, 0.0, id="utm_xy"),
        pytest.param(500_000.123456, 7_500_000.654321, 1e6, id="utm_xyz_1e6"),
    ],
)
def test_regra6_utm_equivalencia_origem_com_shift_e_parciais(ox: float, oy: float, oz: float):
    """Em UTM (e Z grande), shift de vertice no plano + secao parcial em T equivalem a origem dentro de 1e-6 m."""
    pecas_o = [
        (10, "G_VERT", "IfcWall", _caixa_com_aneis_z_np(0.0, 0.0, 0.0, 2.0, 0.3, 2.8, [1.2])),
        (11, "G_PARC_T", "IfcWall", _caixas_fundidas_em_t_np(4.0, 0.0)),
        (12, "G_BOA1", "IfcWall", _caixa_np(8.0, 0.0, 0.0, 10.0, 0.3, 2.8)),
        (13, "G_BOA2", "IfcWall", _caixa_np(12.0, 0.0, 0.0, 14.0, 0.3, 2.8)),
        (14, "G_BARRA", "IfcSlab", _caixa_np(4.95, -0.5, 0.0, 5.05, 2.5, 0.2)),
    ]
    f_o, ped_o, mal_o, ev_o = _montar_cena_numpy(pecas_o, altura_corte_m=1.2)
    r_o, mot_o = planta_cache.desenhar_planta_cache(f_o, ped_o, mal_o, ev_o)
    assert mot_o is None and r_o is not None and r_o["ok"] is True and r_o["secoes_parciais"] == 1

    pecas_u = [(i, g, cls, _transladar_malha(m, ox=ox, oy=oy, oz=oz)) for i, g, cls, m in pecas_o]
    f_u, ped_u, mal_u, ev_u = _montar_cena_numpy(pecas_u, altura_corte_m=oz + 1.2)
    r_u, mot_u = planta_cache.desenhar_planta_cache(f_u, ped_u, mal_u, ev_u)
    assert mot_u is None and r_u is not None and r_u["ok"] is True
    assert r_u["secoes_parciais"] == 1
    assert r_u["enviados"] == r_o["enviados"]

    p_o = _parse_svg(r_o["svg"])
    p_u = _parse_svg(r_u["svg"])
    assert set(p_u.cut_by_guid.keys()) == set(p_o.cut_by_guid.keys())
    for gid in sorted(p_o.cut_by_guid.keys()):
        segs_o = _polilinhas_para_segs(_polilinhas_mundo(p_o.cut_by_guid[gid]))
        segs_u = _polilinhas_para_segs(_polilinhas_mundo(p_u.cut_by_guid[gid], ox=ox, oy=oy))
        assert _hausdorff_segs(segs_o, segs_u) <= 1e-6

    segs_proj_o = _polilinhas_para_segs(_polilinhas_mundo(p_o.proj_groups))
    segs_proj_u = _polilinhas_para_segs(_polilinhas_mundo(p_u.proj_groups, ox=ox, oy=oy))
    assert _hausdorff_segs(segs_proj_o, segs_proj_u) <= 1e-6


def test_regra6_memoria_liberada_weakref_com_shift_e_parciais(monkeypatch):
    """Com shift + secao parcial, malhas_mundo e malhas originais continuam liberadas antes das etapas seguintes."""
    estado: dict[str, dict[str, bool] | None] = {"vis": None, "rec": None}
    real_multi = visibilidade.linhas_visiveis_multi
    real_rec = recorte.recortar_fora_dos_aneis

    def _construir():
        v_ac, wr_v_ac = _array_rastreado(_caixa_np(20.0, 20.0, 2.2, 22.0, 20.4, 2.8)[0])
        t_ac, wr_t_ac = _array_rastreado(_caixa_np(20.0, 20.0, 2.2, 22.0, 20.4, 2.8)[1])
        v_vt, wr_v_vt = _array_rastreado(_caixa_com_aneis_z_np(0.0, 0.0, 0.0, 2.0, 0.3, 2.8, [1.2])[0])
        t_vt, wr_t_vt = _array_rastreado(_caixa_com_aneis_z_np(0.0, 0.0, 0.0, 2.0, 0.3, 2.8, [1.2])[1])
        v_pt, wr_v_pt = _array_rastreado(_caixas_fundidas_em_t_np(4.0, 0.0)[0])
        t_pt, wr_t_pt = _array_rastreado(_caixas_fundidas_em_t_np(4.0, 0.0)[1])
        v_ab, wr_v_ab = _array_rastreado(_caixa_np(4.95, -0.5, 0.0, 5.05, 2.5, 0.2)[0])
        t_ab, wr_t_ab = _array_rastreado(_caixa_np(4.95, -0.5, 0.0, 5.05, 2.5, 0.2)[1])
        v_b1, _ = _array_rastreado(_caixa_np(8.0, 0.0, 0.0, 10.0, 0.3, 2.8)[0])
        t_b1, _ = _array_rastreado(_caixa_np(8.0, 0.0, 0.0, 10.0, 0.3, 2.8)[1])
        v_b2, _ = _array_rastreado(_caixa_np(12.0, 0.0, 0.0, 14.0, 0.3, 2.8)[0])
        t_b2, _ = _array_rastreado(_caixa_np(12.0, 0.0, 0.0, 14.0, 0.3, 2.8)[1])

        malhas = _DictRastreado(
            {
                "G_ACIMA": (v_ac, t_ac),
                "G_VERT": (v_vt, t_vt),
                "G_PARC_T": (v_pt, t_pt),
                "G_ABAIXO": (v_ab, t_ab),
                "G_BOA1": (v_b1, t_b1),
                "G_BOA2": (v_b2, t_b2),
            }
        )
        wrs = {
            "dict": weakref.ref(malhas),
            "v_acima": wr_v_ac, "t_acima": wr_t_ac,
            "v_vert": wr_v_vt, "t_vert": wr_t_vt,
            "v_parc": wr_v_pt, "t_parc": wr_t_pt,
            "v_abaixo": wr_v_ab, "t_abaixo": wr_t_ab,
        }
        entidades = [
            _FalsaEntidade(10, "G_ACIMA", "IfcBeam"),
            _FalsaEntidade(11, "G_VERT", "IfcWall"),
            _FalsaEntidade(12, "G_PARC_T", "IfcWall"),
            _FalsaEntidade(13, "G_ABAIXO", "IfcSlab"),
            _FalsaEntidade(14, "G_BOA1", "IfcWall"),
            _FalsaEntidade(15, "G_BOA2", "IfcWall"),
        ]
        f = _FalsoIfc("PAV_MEM_T24F", entidades)
        ev = [(e.id(), e.GlobalId) for e in entidades]
        pedido = {
            "vista": {"tipo": "PLANTA", "pavimento": "PAV_MEM_T24F", "escala": 1.0, "altura_corte_m": 1.2},
            "elementos": list(ev),
            "threads": 1,
        }
        return f, pedido, [malhas], ev, wrs

    f, pedido, box, ev, wrs = _construir()

    def espia_multi(pecas, *args, **kwargs):
        gc.collect()
        estado["vis"] = {k: (wr() is None) for k, wr in wrs.items()}
        return real_multi(pecas, *args, **kwargs)

    def espia_rec(pols, aneis_arg, *args, **kwargs):
        gc.collect()
        estado["rec"] = {k: (wr() is None) for k, wr in wrs.items()}
        return real_rec(pols, aneis_arg, *args, **kwargs)

    monkeypatch.setattr(visibilidade, "linhas_visiveis_multi", espia_multi)
    monkeypatch.setattr(recorte, "recortar_fora_dos_aneis", espia_rec)

    resp, motivo = planta_cache.desenhar_planta_cache(f, pedido, box.pop(), ev)
    assert motivo is None and resp is not None and resp["ok"] is True and resp["secoes_parciais"] == 1
    assert estado["vis"] is not None and estado["rec"] is not None

    assert estado["vis"]["dict"] is True
    assert estado["vis"]["v_acima"] is True and estado["vis"]["t_acima"] is True
    assert estado["vis"]["v_vert"] is True and estado["vis"]["t_vert"] is True
    assert estado["vis"]["v_parc"] is True and estado["vis"]["t_parc"] is True
    assert estado["rec"]["v_abaixo"] is True and estado["rec"]["t_abaixo"] is True
    gc.collect()
    assert all(wr() is None for wr in wrs.values())
