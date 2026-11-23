# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oraculo 2 da F0-S06-T24c: achados de revisao (UTM / origem relativa e liberacao de malhas).

Cobre os dois defeitos da revisao T24c sem alterar o oraculo 1:
1. Achado 1 (georreferenciamento / origem relativa):
   - Moldura vazada com furo e bloco dentro do furo em UTM
     (500000.123456, 7500000.654321), (5e6, 7.5e6) e (1e9, 1e9):
     bloco no furo permanece visivel e geometria final igual a da origem
     a menos da translacao (tolerancia 1e-6 m).
   - Nunca `secao_aberta` falsa em perfis solidos pequenos (1 a 4 cm) e
     paredes 4 m x 0.4 m nos mesmos deslocamentos.
   - Entrada `malhas_mundo` (dict e arrays) e `pedido` nao sao mutados.
2. Achado 2 (liberacao de malhas apos uso, ESPEC §4.1 item 7):
   - Referencias fracas provam liberacao do dict `malhas_mundo` e das malhas
     descartadas/originais antes de `visibilidade.linhas_visiveis_multi`, e
     da malha abaixo antes de `recorte.recortar_fora_dos_aneis`.
   - `tracemalloc` com margem folgada prova liberacao tambem de copias
     derivadas (`malhas_proj`/`pols_por_peca`) entre etapas.
   - Fluxo `desenho.processar` nao retem `malhas_mundo` no frame durante
     a execucao da visibilidade.
"""
from __future__ import annotations

import gc
import math
import re
import tracemalloc
import weakref
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace

import ifcopenshell
import ifcopenshell.api
import numpy as np
import pytest

from obim_geometria import construtor, desenho, planta_cache, recorte, visibilidade
from openbim_app.desenho import estilo

NS_IFC = "{http://www.ifcopenshell.org/ns}"
_TOK_RE = re.compile(r"[-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?|[a-zA-Z]")

_OFFSETS_UTM = [
    pytest.param((500_000.123456, 7_500_000.654321), id="utm_500k_7500k_frac"),
    pytest.param((5e6, 7.5e6), id="utm_5e6_7p5e6"),
    pytest.param((1e9, 1e9), id="utm_1e9_1e9"),
]


# ---------- construtores sinteticos numpy ----------
def _caixa_np(
    x0: float, y0: float, z0: float, x1: float, y1: float, z1: float
) -> tuple[np.ndarray, np.ndarray]:
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


def _tubo_np(
    ext: list[tuple[float, float]],
    furo: list[tuple[float, float]],
    z0: float,
    z1: float,
) -> tuple[np.ndarray, np.ndarray]:
    verts = np.array([(x, y, z) for z in (z0, z1) for x, y in ext + furo], dtype=np.float64)
    tris = []
    for i in range(4):
        j = (i + 1) % 4
        a, b, c, d = i, j, 4 + j, 4 + i
        tris += [(a, c, b), (a, d, c), (a + 8, b + 8, c + 8), (a + 8, c + 8, d + 8)]
        tris += [(i, j, 8 + j), (i, 8 + j, 8 + i), (4 + j, 4 + i, 12 + i), (4 + j, 12 + i, 12 + j)]
    return verts, np.array(tris, dtype=np.int32)


def _transladar_malha(
    malha: tuple[np.ndarray, np.ndarray], ox: float, oy: float
) -> tuple[np.ndarray, np.ndarray]:
    v, t = malha
    v2 = v.astype(np.float64, copy=True)
    v2[:, 0] += float(ox)
    v2[:, 1] += float(oy)
    return v2, t.copy()


def _caixa_pesada_np(
    x0: float, y0: float, z0: float, x1: float, y1: float, z1: float, *, n_verts: int = 400_000
) -> tuple[np.ndarray, np.ndarray]:
    """Caixa valida com array grande de vertices float64 (~9.16 MiB para 400k verts) e 12 tris."""
    v8, tris = _caixa_np(x0, y0, z0, x1, y1, z1)
    verts = np.empty((n_verts, 3), dtype=np.float64)
    verts[:8] = v8
    verts[8:] = v8[0]
    return verts, tris


# ---------- rastreamento por referencia fraca ----------
class _DictRastreado(dict):
    """Subclasse de dict que suporta `weakref.ref` sem alterar comportamento."""


class _BufRastreado(bytearray):
    """Subclasse de bytearray que suporta `weakref.ref` como backing store de np.ndarray."""


def _array_rastreado(arr: np.ndarray) -> tuple[np.ndarray, weakref.ref]:
    """Cria `np.ndarray` exato sobre `_BufRastreado` e retorna `(array, weakref_do_buffer)`."""
    contig = np.ascontiguousarray(arr)
    raw = _BufRastreado(contig.tobytes())
    view = np.frombuffer(raw, dtype=contig.dtype).reshape(contig.shape)
    return view, weakref.ref(raw)


# ---------- stub IFC leve ----------
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
    pav_guid: str = "PAV_OR2",
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


# ---------- parser SVG e metrica geometrica ----------
def _extrair_polilinhas_d(d: str) -> list[np.ndarray]:
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
    return [np.asarray(r, dtype=np.float64) for r in runs if len(r) >= 2]


def _parse_svg(svg: str) -> SimpleNamespace:
    root = ET.fromstring(svg)
    assert root.tag.rsplit("}", 1)[-1] == "svg"
    proj_groups: list[ET.Element] = []
    cut_by_guid: dict[str, list[ET.Element]] = {}
    for elem in root.iter():
        if elem.tag.rsplit("}", 1)[-1] != "g":
            continue
        cls = (elem.get("class") or "").split()
        gid = elem.get(f"{NS_IFC}guid")
        if "IfcBuildingStorey" in cls:
            continue
        if "projection" in cls:
            proj_groups.append(elem)
        elif gid is not None:
            cut_by_guid.setdefault(gid, []).append(elem)
    return SimpleNamespace(root=root, proj_groups=proj_groups, cut_by_guid=cut_by_guid)


def _polilinhas_mundo(grupos: list[ET.Element], *, ox: float = 0.0, oy: float = 0.0) -> list[np.ndarray]:
    """Extrai polilinhas em coordenadas mundo (x - ox, -y_svg - oy)."""
    out: list[np.ndarray] = []
    for g in grupos:
        for p in g.iter():
            if p.tag.rsplit("}", 1)[-1] == "path":
                for r in _extrair_polilinhas_d(p.get("d") or ""):
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
    """Extremos e pontos internos de cada segmento para distancia Hausdorff exata."""
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


def _assert_equivalente_a_origem(
    svg_orig: str, svg_utm: str, ox: float, oy: float, *, tol: float = 1e-6
) -> None:
    """Exige igualdade geometrica (secao e projecao) a menos da translacao (ox, oy) dentro de `tol`."""
    assert "-0.000000" not in svg_utm
    estilo.aplicar_estilo(svg_utm, "1:50")

    p_orig = _parse_svg(svg_orig)
    p_utm = _parse_svg(svg_utm)

    assert set(p_utm.cut_by_guid.keys()) == set(p_orig.cut_by_guid.keys())
    for gid in sorted(p_orig.cut_by_guid.keys()):
        pls_o = _polilinhas_mundo(p_orig.cut_by_guid[gid])
        pls_u = _polilinhas_mundo(p_utm.cut_by_guid[gid], ox=ox, oy=oy)
        assert len(pls_u) == len(pls_o), f"{gid}: aneis origem={len(pls_o)} vs utm={len(pls_u)}"
        for pl in pls_u:
            assert np.allclose(pl[0], pl[-1], atol=tol), f"{gid}: anel nao fechou em UTM"
        dist_corte = _hausdorff_segs(_polilinhas_para_segs(pls_o), _polilinhas_para_segs(pls_u))
        assert dist_corte <= tol, f"{gid}: divergencia na secao = {dist_corte:.3e} m > {tol:.1e} m"

    segs_proj_o = _polilinhas_para_segs(_polilinhas_mundo(p_orig.proj_groups))
    segs_proj_u = _polilinhas_para_segs(_polilinhas_mundo(p_utm.proj_groups, ox=ox, oy=oy))
    dist_proj = _hausdorff_segs(segs_proj_o, segs_proj_u)
    assert dist_proj <= tol, f"divergencia na projecao = {dist_proj:.3e} m > {tol:.1e} m"


# ---------- cena IFC sintetica minima para teste de integracao em desenho.py ----------
def _criar_caixa_ifc(f, body, classe: str, comp: float, esp: float, alt: float, pos: tuple[float, float, float]):
    api = ifcopenshell.api.run
    el = api("root.create_entity", f, ifc_class=classe)
    rep = api("geometry.add_wall_representation", f, context=body, length=comp, height=alt, thickness=esp)
    el.Representation = f.createIfcProductDefinitionShape(Representations=[rep])
    m = np.eye(4)
    m[:3, 3] = pos
    api("geometry.edit_object_placement", f, product=el, matrix=m, is_si=False)
    return el


def _criar_cena_ifc_minima(tmp_path: Path) -> SimpleNamespace:
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

    parede = _criar_caixa_ifc(f, body, "IfcWall", 4.0, 0.2, 2.8, (0.0, 0.0, 0.0))
    laje = _criar_caixa_ifc(f, body, "IfcSlab", 4.0, 3.0, 0.2, (0.0, 0.0, -0.2))
    viga_acima = _criar_caixa_ifc(f, body, "IfcBeam", 4.0, 0.2, 0.4, (0.0, 2.0, 2.4))
    api("spatial.assign_container", f, products=[parede, laje, viga_acima], relating_structure=andar)

    arq = tmp_path / "oraculo2_mem.ifc"
    f.write(str(arq))
    f = ifcopenshell.open(str(arq))
    andar = f.by_guid(andar.GlobalId)
    parede = f.by_guid(parede.GlobalId)
    laje = f.by_guid(laje.GlobalId)
    viga_acima = f.by_guid(viga_acima.GlobalId)

    pasta = tmp_path / "cache_geo"
    doc = construtor.documento_de(arq)
    with construtor.abrir_banco(pasta) as cache:
        r = construtor.construir_lote(f, cache, construtor.fila_inicial(f), documento=doc, assinatura="s1", memo={})
        assert r["falhas"] == 0 and r["gravadas"] == 3

    todos = [parede, laje, viga_acima]
    pedido_cache = {
        "arquivo": str(arq),
        "vista": {"tipo": "PLANTA", "pavimento": andar.GlobalId, "escala": 1.0, "altura_corte_m": 1.2},
        "elementos": [(e.id(), e.GlobalId) for e in todos],
        "threads": 1,
        "pasta_cache_geometria": str(pasta),
    }
    return SimpleNamespace(
        parede=parede,
        laje=laje,
        viga_acima=viga_acima,
        pedido_cache=pedido_cache,
    )
