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


# ==========================================================================
# (a) ACHADO 1: Coordenadas georreferenciadas (UTM / grandes offsets)
# ==========================================================================
@pytest.mark.parametrize("offset", _OFFSETS_UTM)
def test_achado1_moldura_vazada_e_bloco_no_furo_em_utm(offset):
    """Moldura 3 cm x 3 cm com furo 2.2 cm x 2.2 cm + bloco 0.8 cm x 0.8 cm dentro do furo.

    Sem origem relativa:
    - em (500000.123456, 7500000.654321): corrupcao silenciosa apaga o bloco dentro do furo;
    - em (5e6, 7.5e6) e (1e9, 1e9): queda falsa com `secao_aberta`.
    """
    ox, oy = offset
    ext = [(0.0, 0.0), (0.03, 0.0), (0.03, 0.03), (0.0, 0.03)]
    furo = [(0.004, 0.004), (0.026, 0.004), (0.026, 0.026), (0.004, 0.026)]
    moldura_o = _tubo_np(ext, furo, 0.0, 2.8)
    bloco_o = _caixa_np(0.011, 0.011, 0.0, 0.019, 0.019, 0.5)

    f_o, ped_o, mal_o, ev_o = _montar_cena_numpy(
        [
            (10, "G_MOLDURA", "IfcWall", moldura_o),
            (11, "G_BLOCO_FURO", "IfcFurnishingElement", bloco_o),
        ],
        altura_corte_m=1.2,
    )
    resp_o, mot_o = planta_cache.desenhar_planta_cache(f_o, ped_o, mal_o, ev_o)
    assert mot_o is None and resp_o is not None and resp_o["ok"] is True

    f_u, ped_u, mal_u, ev_u = _montar_cena_numpy(
        [
            (10, "G_MOLDURA", "IfcWall", _transladar_malha(moldura_o, ox, oy)),
            (11, "G_BLOCO_FURO", "IfcFurnishingElement", _transladar_malha(bloco_o, ox, oy)),
        ],
        altura_corte_m=1.2,
    )
    resp_u, mot_u = planta_cache.desenhar_planta_cache(f_u, ped_u, mal_u, ev_u)
    assert mot_u is None and resp_u is not None and resp_u["ok"] is True, (
        f"queda falsa em offset={offset}: motivo={mot_u!r}"
    )

    p_u = _parse_svg(resp_u["svg"])
    pls_mold_u = _polilinhas_mundo(p_u.cut_by_guid["G_MOLDURA"], ox=ox, oy=oy)
    assert len(pls_mold_u) == 2, f"esperado externo + furo (2 aneis), obtido {len(pls_mold_u)}"

    # Bloco dentro do furo continua visivel na projecao
    segs_proj_u = _polilinhas_para_segs(_polilinhas_mundo(p_u.proj_groups, ox=ox, oy=oy))
    pts_bloco = np.array(
        [[0.011, 0.015], [0.019, 0.015], [0.015, 0.011], [0.015, 0.019]],
        dtype=np.float64,
    )
    dist_bloco = float(_dist_pontos_a_segs(pts_bloco, segs_proj_u).max())
    assert dist_bloco <= 1e-6, f"bloco dentro do furo apagado/deslocado em offset={offset}: dist={dist_bloco:.6e} m"

    # Resultado completo igual ao da origem a menos da translacao (tolerancia 1e-6 m)
    assert resp_u["enviados"] == resp_o["enviados"]
    _assert_equivalente_a_origem(resp_o["svg"], resp_u["svg"], ox, oy, tol=1e-6)


@pytest.mark.parametrize("lado_m", [0.01, 0.02, 0.03, 0.04], ids=["1cm", "2cm", "3cm", "4cm"])
@pytest.mark.parametrize("offset", _OFFSETS_UTM)
def test_achado1_perfis_solidos_pequenos_nunca_secao_aberta(lado_m, offset):
    """Perfis solidos cortados de 1 a 4 cm nunca podem cair com `secao_aberta` em UTM/1e9."""
    ox, oy = offset
    perfil_o = _caixa_np(0.0, 0.0, 0.0, lado_m, lado_m, 2.8)

    f_o, ped_o, mal_o, ev_o = _montar_cena_numpy([(10, "G_PERFIL", "IfcColumn", perfil_o)], altura_corte_m=1.2)
    resp_o, mot_o = planta_cache.desenhar_planta_cache(f_o, ped_o, mal_o, ev_o)
    assert mot_o is None and resp_o is not None and resp_o["ok"] is True

    f_u, ped_u, mal_u, ev_u = _montar_cena_numpy(
        [(10, "G_PERFIL", "IfcColumn", _transladar_malha(perfil_o, ox, oy))],
        altura_corte_m=1.2,
    )
    resp_u, mot_u = planta_cache.desenhar_planta_cache(f_u, ped_u, mal_u, ev_u)
    assert mot_u is None and resp_u is not None and resp_u["ok"] is True, (
        f"secao_aberta falsa em perfil {lado_m*100:.0f} cm offset={offset}: motivo={mot_u!r}"
    )

    _assert_equivalente_a_origem(resp_o["svg"], resp_u["svg"], ox, oy, tol=1e-6)


@pytest.mark.parametrize("offset", _OFFSETS_UTM)
def test_achado1_parede_4m_por_04m_nunca_secao_aberta(offset):
    """Parede 4.0 m x 0.4 m + laje abaixo nunca pode cair com `secao_aberta` (inclusive em 1e9)."""
    ox, oy = offset
    parede_o = _caixa_np(0.0, 0.0, 0.0, 4.0, 0.4, 2.8)
    laje_o = _caixa_np(0.0, 0.0, -0.2, 4.0, 3.0, 0.0)

    f_o, ped_o, mal_o, ev_o = _montar_cena_numpy(
        [
            (10, "G_PAREDE", "IfcWall", parede_o),
            (11, "G_LAJE", "IfcSlab", laje_o),
        ],
        altura_corte_m=1.2,
    )
    resp_o, mot_o = planta_cache.desenhar_planta_cache(f_o, ped_o, mal_o, ev_o)
    assert mot_o is None and resp_o is not None and resp_o["ok"] is True

    f_u, ped_u, mal_u, ev_u = _montar_cena_numpy(
        [
            (10, "G_PAREDE", "IfcWall", _transladar_malha(parede_o, ox, oy)),
            (11, "G_LAJE", "IfcSlab", _transladar_malha(laje_o, ox, oy)),
        ],
        altura_corte_m=1.2,
    )
    resp_u, mot_u = planta_cache.desenhar_planta_cache(f_u, ped_u, mal_u, ev_u)
    assert mot_u is None and resp_u is not None and resp_u["ok"] is True, (
        f"secao_aberta falsa em parede 4m x 0.4m offset={offset}: motivo={mot_u!r}"
    )

    _assert_equivalente_a_origem(resp_o["svg"], resp_u["svg"], ox, oy, tol=1e-6)


@pytest.mark.parametrize(
    "offset",
    [
        pytest.param((500_000.123456, 7_500_000.654321), id="utm_500k_7500k_frac"),
        pytest.param((1e9, 1e9), id="utm_1e9_1e9"),
    ],
)
def test_achado1_entrada_malhas_mundo_nao_mutada_em_utm(offset):
    """Translacao por origem relativa e liberacao local NAO podem mutar `malhas_mundo` nem `pedido`."""
    ox, oy = offset
    ext = [(0.0, 0.0), (0.03, 0.0), (0.03, 0.03), (0.0, 0.03)]
    furo = [(0.004, 0.004), (0.026, 0.004), (0.026, 0.026), (0.004, 0.026)]
    pecas = [
        (10, "G_MOLDURA", "IfcWall", _transladar_malha(_tubo_np(ext, furo, 0.0, 2.8), ox, oy)),
        (11, "G_BLOCO", "IfcFurnishingElement", _transladar_malha(_caixa_np(0.011, 0.011, 0.0, 0.019, 0.019, 0.5), ox, oy)),
        (12, "G_PAREDE", "IfcWall", _transladar_malha(_caixa_np(1.0, 0.0, 0.0, 5.0, 0.4, 2.8), ox, oy)),
        (13, "G_VIGA_ACIMA", "IfcBeam", _transladar_malha(_caixa_np(1.0, 0.0, 2.2, 5.0, 0.3, 2.8), ox, oy)),
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

    assert list(malhas.keys()) == copia_chaves
    for g, (v0, t0) in copia_malhas.items():
        v1, t1 = malhas[g]
        assert v1.dtype == v0.dtype and t1.dtype == t0.dtype
        np.testing.assert_array_equal(v1, v0)
        np.testing.assert_array_equal(t1, t0)
    assert pedido == copia_pedido


# ==========================================================================
# (b) ACHADO 2: Liberacao de malhas apos uso (ESPEC §4.1 item 7)
# ==========================================================================
def test_achado2_libera_malhas_mundo_e_pecas_por_weakref(monkeypatch):
    """Com o chamador soltando a referencia unica, `malhas_mundo` e malhas descartadas morrem antes da visibilidade."""
    estado = {"vis": None, "rec": None}
    real_multi = visibilidade.linhas_visiveis_multi
    real_rec = recorte.recortar_fora_dos_aneis

    def _construir_entrada():
        v_ac, wr_v_ac = _array_rastreado(_caixa_np(5.0, 5.0, 2.2, 7.0, 5.4, 2.8)[0])
        t_ac, wr_t_ac = _array_rastreado(_caixa_np(5.0, 5.0, 2.2, 7.0, 5.4, 2.8)[1])
        v_co, wr_v_co = _array_rastreado(_caixa_np(0.0, 1.0, 0.0, 4.0, 1.4, 2.8)[0])
        t_co, wr_t_co = _array_rastreado(_caixa_np(0.0, 1.0, 0.0, 4.0, 1.4, 2.8)[1])
        v_ab, wr_v_ab = _array_rastreado(_caixa_np(1.5, 0.0, 0.0, 2.5, 2.4, 0.2)[0])
        t_ab, wr_t_ab = _array_rastreado(_caixa_np(1.5, 0.0, 0.0, 2.5, 2.4, 0.2)[1])

        malhas = _DictRastreado(
            {
                "G_ACIMA": (v_ac, t_ac),
                "G_CORTADA": (v_co, t_co),
                "G_ABAIXO": (v_ab, t_ab),
            }
        )
        wrs = {
            "dict": weakref.ref(malhas),
            "v_acima": wr_v_ac,
            "t_acima": wr_t_ac,
            "v_cortada": wr_v_co,
            "t_cortada": wr_t_co,
            "v_abaixo": wr_v_ab,
            "t_abaixo": wr_t_ab,
        }
        entidades = [
            _FalsaEntidade(10, "G_ACIMA", "IfcBeam"),
            _FalsaEntidade(11, "G_CORTADA", "IfcWall"),
            _FalsaEntidade(12, "G_ABAIXO", "IfcSlab"),
        ]
        f = _FalsoIfc("PAV_MEM", entidades)
        ev = [(10, "G_ACIMA"), (11, "G_CORTADA"), (12, "G_ABAIXO")]
        pedido = {
            "vista": {"tipo": "PLANTA", "pavimento": "PAV_MEM", "escala": 1.0, "altura_corte_m": 1.2},
            "elementos": list(ev),
            "threads": 1,
        }
        return f, pedido, [malhas], ev, wrs

    f, pedido, box, ev, wrs = _construir_entrada()

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
    assert motivo is None and resp is not None and resp["ok"] is True
    assert estado["vis"] is not None, "linhas_visiveis_multi nao foi chamada"
    assert estado["rec"] is not None, "recortar_fora_dos_aneis nao foi chamada"

    # Antes de linhas_visiveis_multi: dict malhas_mundo, peca acima e malha original cortada ja liberados
    assert estado["vis"]["dict"] is True, "malhas_mundo ainda retido durante linhas_visiveis_multi"
    assert estado["vis"]["v_acima"] is True and estado["vis"]["t_acima"] is True, (
        "malha acima do corte ainda retida durante linhas_visiveis_multi"
    )
    assert estado["vis"]["v_cortada"] is True and estado["vis"]["t_cortada"] is True, (
        "malha original da peca cortada ainda retida durante linhas_visiveis_multi"
    )

    # Antes de recortar_fora_dos_aneis: malha abaixo tambem liberada
    assert estado["rec"]["v_abaixo"] is True and estado["rec"]["t_abaixo"] is True, (
        "malha abaixo do corte ainda retida durante recortar_fora_dos_aneis"
    )

    # Apos o retorno: nada retido em estado global
    gc.collect()
    assert all(wr() is None for wr in wrs.values())


def test_achado2_liberacao_memoria_tracemalloc_entre_etapas(monkeypatch):
    """Mede memoria viva via tracemalloc (margem folgada) para provar liberacao de malhas_mundo e malhas_proj."""
    n_verts = 400_000  # ~9.16 MiB por malha float64 (3 malhas ~= 27.5 MiB)
    mib = 1024.0 * 1024.0
    medido: dict[str, float] = {}
    real_multi = visibilidade.linhas_visiveis_multi
    real_rec = recorte.recortar_fora_dos_aneis

    ja_ativo = tracemalloc.is_tracing()
    if not ja_ativo:
        tracemalloc.start()
    try:
        gc.collect()
        base_b, _ = tracemalloc.get_traced_memory()

        def _criar():
            pecas = [
                (10, "G_ACIMA", "IfcBeam", _caixa_pesada_np(5.0, 5.0, 2.2, 7.0, 5.4, 2.8, n_verts=n_verts)),
                (11, "G_CORTADA", "IfcWall", _caixa_pesada_np(0.0, 1.0, 0.0, 4.0, 1.4, 2.8, n_verts=n_verts)),
                (12, "G_ABAIXO", "IfcSlab", _caixa_pesada_np(1.5, 0.0, 0.0, 2.5, 2.4, 0.2, n_verts=n_verts)),
            ]
            f, pedido, malhas, ev = _montar_cena_numpy(pecas, altura_corte_m=1.2)
            return f, pedido, [malhas], ev

        f, pedido, box, ev = _criar()
        gc.collect()
        antes_b, _ = tracemalloc.get_traced_memory()
        entrada_mib = (antes_b - base_b) / mib
        assert entrada_mib >= 24.0, f"alocacao de entrada abaixo do esperado: {entrada_mib:.2f} MiB"

        def espia_multi(pecas, *args, **kwargs):
            gc.collect()
            cur_b, _ = tracemalloc.get_traced_memory()
            medido["vis_mib"] = (cur_b - base_b) / mib
            return real_multi(pecas, *args, **kwargs)

        def espia_rec(pols, aneis_arg, *args, **kwargs):
            gc.collect()
            cur_b, _ = tracemalloc.get_traced_memory()
            medido["rec_mib"] = (cur_b - base_b) / mib
            return real_rec(pols, aneis_arg, *args, **kwargs)

        monkeypatch.setattr(visibilidade, "linhas_visiveis_multi", espia_multi)
        monkeypatch.setattr(recorte, "recortar_fora_dos_aneis", espia_rec)

        resp, motivo = planta_cache.desenhar_planta_cache(f, pedido, box.pop(), ev)
        assert motivo is None and resp is not None and resp["ok"] is True
        assert "vis_mib" in medido and "rec_mib" in medido

        # Na visibilidade: malhas acima (~9.16 MiB) e cortada original (~9.16 MiB) liberadas -> <= 16 MiB (vs ~27.5 MiB)
        assert medido["vis_mib"] <= 16.0, (
            f"memoria viva na visibilidade={medido['vis_mib']:.2f} MiB "
            f"(entrada={entrada_mib:.2f} MiB); malhas_mundo nao foi liberado"
        )
        # No recorte: malhas_proj (~9.16 MiB, inclusive copia transladada) e pols_por_peca liberados -> <= 4 MiB
        assert medido["rec_mib"] <= 4.0, (
            f"memoria viva no recorte={medido['rec_mib']:.2f} MiB "
            f"(entrada={entrada_mib:.2f} MiB); malhas_proj nao foi liberado"
        )
    finally:
        if not ja_ativo:
            tracemalloc.stop()


def test_achado2_desenho_processar_nao_retem_malhas_mundo_durante_visibilidade(tmp_path, monkeypatch):
    """Fluxo `desenho.processar` (`_tentar_planta_pelo_cache` -> `_desenhar_planta_cache`) solta `malhas_mundo` antes da visibilidade."""
    cena = _criar_cena_ifc_minima(tmp_path)
    real_ler = desenho.cache_leitura.malhas_do_cache
    real_multi = visibilidade.linhas_visiveis_multi
    wrs: dict[str, weakref.ref] = {}
    estado: dict[str, bool] = {}

    def ler_rastreado(cache, doc, ids):
        malhas_orig, falt = real_ler(cache, doc, ids)
        d = _DictRastreado()
        for gid, (v, t) in malhas_orig.items():
            vr, wr_v = _array_rastreado(v)
            tr, wr_t = _array_rastreado(t)
            d[gid] = (vr, tr)
            if gid == cena.viga_acima.GlobalId:
                wrs["v_acima"] = wr_v
                wrs["t_acima"] = wr_t
            elif gid == cena.parede.GlobalId:
                wrs["v_parede"] = wr_v
                wrs["t_parede"] = wr_t
        wrs["dict"] = weakref.ref(d)
        return d, falt

    def espia_multi(pecas, *args, **kwargs):
        gc.collect()
        for k, wr in wrs.items():
            estado[k] = wr() is None
        return real_multi(pecas, *args, **kwargs)

    monkeypatch.setattr(desenho.cache_leitura, "malhas_do_cache", ler_rastreado)
    monkeypatch.setattr(visibilidade, "linhas_visiveis_multi", espia_multi)

    resp = desenho.processar(cena.pedido_cache)
    assert resp["ok"] is True and resp["via_cache"] is True and resp["queda"] is None
    assert estado, "linhas_visiveis_multi nao foi chamada"
    assert estado["dict"] is True, "desenho._tentar_planta_pelo_cache ainda segura malhas_mundo durante visibilidade"
    assert estado["v_acima"] is True and estado["t_acima"] is True
    assert estado["v_parede"] is True and estado["t_parede"] is True
