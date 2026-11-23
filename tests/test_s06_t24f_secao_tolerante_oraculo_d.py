# SPDX-License-Identifier: AGPL-3.0-or-later
"""Parte 4 de test_s06_t24f_secao_tolerante_oraculo.py (divisao mecanica em PRs de ate 400 linhas). Auxiliares e fixtures vem das partes anteriores."""
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
from test_s06_t24f_secao_tolerante_oraculo import _FalsaEntidade, _FalsoIfc, _caixa_com_aneis_z_np, _caixa_np, _caixas_fundidas_em_t_np, _montar_cena_numpy, _parse_svg, _transladar_malha  # noqa: F401
from test_s06_t24f_secao_tolerante_oraculo_b import _DictRastreado, _array_rastreado, _hausdorff_segs, _polilinhas_mundo, _polilinhas_para_segs, _sha256  # noqa: F401



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
