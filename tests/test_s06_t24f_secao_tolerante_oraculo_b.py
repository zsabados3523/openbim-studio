# SPDX-License-Identifier: AGPL-3.0-or-later
"""Parte 2 de test_s06_t24f_secao_tolerante_oraculo.py (divisao mecanica em PRs de ate 400 linhas). Auxiliares e fixtures vem das partes anteriores."""
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
from test_s06_t24f_secao_tolerante_oraculo import _DELTAS_ORDEM, _caixa_com_aneis_z_np, _caixa_np, _caixas_fundidas_em_t_np, _degrau_no_plano_np, _extrair_polilinhas_d, _malha_grande_poucos_vertices_no_plano_np, _montar_cena_numpy, _parede_inclinada_np, _parse_svg  # noqa: F401



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
