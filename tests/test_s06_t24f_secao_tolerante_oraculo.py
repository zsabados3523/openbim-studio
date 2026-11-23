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
