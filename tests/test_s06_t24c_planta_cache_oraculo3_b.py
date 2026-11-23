# SPDX-License-Identifier: AGPL-3.0-or-later
"""Parte 2 de test_s06_t24c_planta_cache_oraculo3.py (divisao mecanica em PRs de ate 400 linhas). Auxiliares e fixtures vem das partes anteriores."""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from types import SimpleNamespace
import numpy as np
import pytest
from obim_geometria import planta_cache
from openbim_app.desenho import estilo
from test_s06_t24c_planta_cache_oraculo3 import _UTM, _assert_svg_equivalente, _caixa_np, _dist_pontos_a_segs, _hausdorff_segs, _montar_cena_numpy, _parse_svg, _polilinhas_mundo, _polilinhas_para_segs, _transladar_malha, _tubo_np  # noqa: F401



@pytest.mark.parametrize(
    "dz",
    [
        pytest.param(1e6, id="dz_p1e6"),
        pytest.param(1e8, id="dz_p1e8"),
        pytest.param(1e9, id="dz_p1e9"),
        pytest.param(-1e9, id="dz_m1e9"),
    ],
)
def test_defeito1_cena_padrao_deslocada_em_z_equivalente_a_origem(dz: float):
    """Mesma cena padrao (parede, laje abaixo, bloco abaixo e viga 1.0 m acima) deslocada em Z iguala a origem."""
    z_orig = 1.2
    parede_o = _caixa_np(0.0, 0.0, 0.0, 4.0, 0.4, 2.8)
    laje_o = _caixa_np(0.0, 0.0, -0.2, 4.0, 3.0, 0.0)
    bloco_o = _caixa_np(1.5, 1.0, 0.0, 2.5, 2.0, 0.5)
    viga_o = _caixa_np(5.0, 5.0, 2.2, 7.0, 5.4, 2.8)

    pecas_o = [
        (10, "G_PAREDE", "IfcWall", parede_o),
        (11, "G_LAJE", "IfcSlab", laje_o),
        (12, "G_BLOCO", "IfcFurnishingElement", bloco_o),
        (13, "G_VIGA_ACIMA", "IfcBeam", viga_o),
    ]
    f_o, ped_o, mal_o, ev_o = _montar_cena_numpy(pecas_o, altura_corte_m=z_orig)
    resp_o, mot_o = planta_cache.desenhar_planta_cache(f_o, ped_o, mal_o, ev_o)
    assert mot_o is None and resp_o is not None and resp_o["ok"] is True
    assert 13 not in resp_o["enviados"]

    pecas_z = [(i, g, cls, _transladar_malha(m, oz=dz)) for i, g, cls, m in pecas_o]
    f_z, ped_z, mal_z, ev_z = _montar_cena_numpy(pecas_z, altura_corte_m=dz + z_orig)
    resp_z, mot_z = planta_cache.desenhar_planta_cache(f_z, ped_z, mal_z, ev_z)
    assert mot_z is None and resp_z is not None and resp_z["ok"] is True, (
        f"queda falsa em dz={dz}: motivo={mot_z!r}"
    )

    assert resp_z["enviados"] == resp_o["enviados"]
    _assert_svg_equivalente(resp_o["svg"], resp_z["svg"], tol=1e-6)


@pytest.mark.parametrize(
    ("z_corte", "gap"),
    [
        pytest.param(11.2, 5e-9, id="z11p2_gap5e-9"),
        pytest.param(5001.2, 2e-6, id="z5001p2_gap2e-6"),
        pytest.param(1e6 + 1.2, 5e-4, id="z1e6_gap5e-4"),
        pytest.param(1e8 + 1.2, 0.05, id="z1e8_gap0p05"),
        pytest.param(1e9 + 1.2, 0.5, id="z1e9_gap0p5"),
    ],
)
def test_defeito1_zona_morta_peca_acima_gap_pequeno_sem_secao_aberta(z_corte: float, gap: float):
    """Peca acima na zona morta `eps_plano < zmin - z <= eps` nao pode gerar `secao_aberta` nem ser enviada."""
    parede_o = _caixa_np(0.0, 0.0, 0.0, 4.0, 0.4, 2.8)
    f_ref, ped_ref, mal_ref, ev_ref = _montar_cena_numpy(
        [(10, "G_PAREDE", "IfcWall", parede_o)],
        altura_corte_m=1.2,
    )
    resp_ref, mot_ref = planta_cache.desenhar_planta_cache(f_ref, ped_ref, mal_ref, ev_ref)
    assert mot_ref is None and resp_ref is not None and resp_ref["ok"] is True

    parede_z = _caixa_np(0.0, 0.0, z_corte - 1.2, 4.0, 0.4, z_corte + 1.6)
    viga_z = _caixa_np(5.0, 5.0, z_corte + gap, 7.0, 5.4, z_corte + gap + 0.6)
    f_z, ped_z, mal_z, ev_z = _montar_cena_numpy(
        [
            (10, "G_PAREDE", "IfcWall", parede_z),
            (11, "G_VIGA_ACIMA", "IfcBeam", viga_z),
        ],
        altura_corte_m=z_corte,
    )
    resp_z, mot_z = planta_cache.desenhar_planta_cache(f_z, ped_z, mal_z, ev_z)
    assert mot_z is None and resp_z is not None and resp_z["ok"] is True, (
        f"secao_aberta falsa na zona morta (z={z_corte}, gap={gap}): motivo={mot_z!r}"
    )

    assert resp_z["enviados"] == [10], f"viga acima enviada (z={z_corte}, gap={gap}): {resp_z['enviados']}"
    p_z = _parse_svg(resp_z["svg"])
    assert "G_PAREDE" in p_z.cut_by_guid and "G_VIGA_ACIMA" not in p_z.cut_by_guid
    _assert_svg_equivalente(resp_ref["svg"], resp_z["svg"], tol=1e-6)


# ==========================================================================
# (2) DEFEITO 2: (ox, oy) travado em v[0] da primeira peca em cena mista
# ==========================================================================
_MARCADORES_XY = [
    pytest.param((0.0, 0.0), id="marcador_0_0"),
    pytest.param((999.0, 0.0), id="marcador_999_0"),
]


def _cena_mista_moldura_bloco(marcador_xy: tuple[float, float], *, guid_marcador: str):
    mx, my = marcador_xy
    ox, oy = _UTM
    ext = [(0.0, 0.0), (0.03, 0.0), (0.03, 0.03), (0.0, 0.03)]
    furo = [(0.004, 0.004), (0.026, 0.004), (0.026, 0.026), (0.004, 0.026)]
    marcador = _caixa_np(mx, my, -0.2, mx + 1.0, my + 1.0, 0.0)
    moldura = _transladar_malha(_tubo_np(ext, furo, 0.0, 2.8), ox, oy)
    bloco = _transladar_malha(_caixa_np(0.011, 0.011, 0.0, 0.019, 0.019, 0.5), ox, oy)
    return _montar_cena_numpy(
        [
            (10, guid_marcador, "IfcSlab", marcador),
            (11, "G_MOLDURA", "IfcWall", moldura),
            (12, "G_BLOCO_FURO", "IfcFurnishingElement", bloco),
        ],
        altura_corte_m=1.2,
    )


@pytest.mark.parametrize("marcador_xy", _MARCADORES_XY)
def test_defeito2_cena_mista_moldura_com_furo_e_bloco_visivel_em_utm(marcador_xy):
    """Marcador em (0,0) ou (999,0) como primeira peca nao pode apagar o bloco no furo em UTM."""
    ox, oy = _UTM
    f, ped, mal, ev = _cena_mista_moldura_bloco(marcador_xy, guid_marcador="G_0_MARC")
    resp, mot = planta_cache.desenhar_planta_cache(f, ped, mal, ev)
    assert mot is None and resp is not None and resp["ok"] is True, (
        f"queda falsa em cena mista marcador={marcador_xy}: motivo={mot!r}"
    )
    assert "-0.000000" not in resp["svg"]
    estilo.aplicar_estilo(resp["svg"], "1:50")

    p = _parse_svg(resp["svg"])
    assert "G_MOLDURA" in p.cut_by_guid
    pls_mold = _polilinhas_mundo(p.cut_by_guid["G_MOLDURA"], ox=ox, oy=oy)
    assert len(pls_mold) == 2, f"esperado externo + furo (2 aneis), obtido {len(pls_mold)}"

    segs_proj = _polilinhas_para_segs(_polilinhas_mundo(p.proj_groups, ox=ox, oy=oy))
    pts_bloco = np.array(
        [[0.011, 0.015], [0.019, 0.015], [0.015, 0.011], [0.015, 0.019]],
        dtype=np.float64,
    )
    dist_bloco = float(_dist_pontos_a_segs(pts_bloco, segs_proj).max())
    assert dist_bloco <= 1e-6, (
        f"bloco dentro do furo apagado/deslocado com marcador={marcador_xy}: dist={dist_bloco:.6e} m"
    )


@pytest.mark.parametrize("marcador_xy", _MARCADORES_XY)
def test_defeito2_cena_mista_coluna_2cm_em_utm_sem_secao_aberta(marcador_xy):
    """Marcador em (0,0) ou (999,0) como primeira peca + coluna 2 cm em UTM nao pode dar `secao_aberta`."""
    mx, my = marcador_xy
    ox, oy = _UTM
    marcador = _caixa_np(mx, my, -0.2, mx + 1.0, my + 1.0, 0.0)
    col_o = _caixa_np(0.0, 0.0, 0.0, 0.02, 0.02, 2.8)
    col_u = _transladar_malha(col_o, ox, oy)

    f_o, ped_o, mal_o, ev_o = _montar_cena_numpy([(11, "G_COLUNA", "IfcColumn", col_o)], altura_corte_m=1.2)
    resp_o, mot_o = planta_cache.desenhar_planta_cache(f_o, ped_o, mal_o, ev_o)
    assert mot_o is None and resp_o is not None and resp_o["ok"] is True

    f_m, ped_m, mal_m, ev_m = _montar_cena_numpy(
        [
            (10, "G_0_MARC", "IfcSlab", marcador),
            (11, "G_COLUNA", "IfcColumn", col_u),
        ],
        altura_corte_m=1.2,
    )
    resp_m, mot_m = planta_cache.desenhar_planta_cache(f_m, ped_m, mal_m, ev_m)
    assert mot_m is None and resp_m is not None and resp_m["ok"] is True, (
        f"secao_aberta falsa em coluna 2 cm UTM com marcador={marcador_xy}: motivo={mot_m!r}"
    )

    p_o = _parse_svg(resp_o["svg"])
    p_m = _parse_svg(resp_m["svg"])
    assert "G_COLUNA" in p_m.cut_by_guid
    segs_o = _polilinhas_para_segs(_polilinhas_mundo(p_o.cut_by_guid["G_COLUNA"]))
    segs_m = _polilinhas_para_segs(_polilinhas_mundo(p_m.cut_by_guid["G_COLUNA"], ox=ox, oy=oy))
    dist = _hausdorff_segs(segs_o, segs_m)
    assert dist <= 1e-6, f"secao da coluna 2 cm divergiu em cena mista: dist={dist:.3e} m"


@pytest.mark.parametrize("marcador_xy", _MARCADORES_XY)
def test_defeito2_cena_mista_renomear_guid_primeira_peca_nao_muda_svg(marcador_xy):
    """Renomear GUID do marcador (`G_0_MARC` -> `G_Z_MARC`) nao muda o resultado geometrico do SVG."""
    f_a, ped_a, mal_a, ev_a = _cena_mista_moldura_bloco(marcador_xy, guid_marcador="G_0_MARC")
    f_b, ped_b, mal_b, ev_b = _cena_mista_moldura_bloco(marcador_xy, guid_marcador="G_Z_MARC")

    resp_a, mot_a = planta_cache.desenhar_planta_cache(f_a, ped_a, mal_a, ev_a)
    resp_b, mot_b = planta_cache.desenhar_planta_cache(f_b, ped_b, mal_b, ev_b)

    assert mot_b is None and resp_b is not None and resp_b["ok"] is True, (
        f"falha com marcador por ultimo (G_Z_MARC): motivo={mot_b!r}"
    )
    assert mot_a is None and resp_a is not None and resp_a["ok"] is True, (
        f"falha com marcador primeiro (G_0_MARC) mas passou com G_Z_MARC: motivo={mot_a!r}"
    )

    assert set(resp_a["enviados"]) == set(resp_b["enviados"])
    _assert_svg_equivalente(resp_b["svg"], resp_a["svg"], tol=1e-6)
    assert resp_a["n_paths"] == resp_b["n_paths"]
