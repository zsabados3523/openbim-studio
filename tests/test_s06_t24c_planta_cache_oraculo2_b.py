# SPDX-License-Identifier: AGPL-3.0-or-later
"""Parte 2 de test_s06_t24c_planta_cache_oraculo2.py (divisao mecanica em PRs de ate 400 linhas). Auxiliares e fixtures vem das partes anteriores."""
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
from test_s06_t24c_planta_cache_oraculo2 import _DictRastreado, _FalsaEntidade, _FalsoIfc, _OFFSETS_UTM, _array_rastreado, _assert_equivalente_a_origem, _caixa_np, _caixa_pesada_np, _criar_cena_ifc_minima, _dist_pontos_a_segs, _montar_cena_numpy, _parse_svg, _polilinhas_mundo, _polilinhas_para_segs, _transladar_malha, _tubo_np  # noqa: F401



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
