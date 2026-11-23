# SPDX-License-Identifier: AGPL-3.0-or-later
"""Parte 2 de test_s06_t24t_xor_corte_oraculo.py (divisao mecanica em PRs de ate 400 linhas). Auxiliares e fixtures vem das partes anteriores."""
from __future__ import annotations

import numpy as np
import pytest
from obim_geometria import aneis, corte_plano, planta_cache, recorte
from openbim_app.desenho import estilo
from test_s06_t19j1_corte_plano_oraculo import anel_quadrado, octaedro, piramide
from test_s06_t24c_planta_cache_oraculo import _tubo_np
from test_s06_t24f_secao_tolerante_oraculo import _caixa_np, _montar_cena_numpy, _parse_svg, _transladar_malha  # noqa: F401
from test_s06_t24f_secao_tolerante_oraculo_b import _dist_pontos_a_segs, _eh_fechada, _polilinhas_mundo, _polilinhas_para_segs, _sha256  # noqa: F401
from test_s06_t24h_aneis_nao_agrupaveis_oraculo import _boas, _checar_imutavel, _congelar_snapshot
from test_s06_t24t_xor_corte_oraculo import _assert_igual_bit_a_bit, _blocos_em_fila_soldados_np, _caixa_com_face_mult_np, _combinar_malhas, _malha_aleatoria_bem_formada, _perimetro_anel, _permutar_malha, _prisma_l_np, _ref_cortar  # noqa: F401



# ---------- (1) ACEITACAO (FALHAM HOJE; PASSAM COM D) ----------
@pytest.mark.parametrize(
    ("xs", "y0", "y1", "z0", "z1", "z_corte"),
    [
        pytest.param((0.0, 1.0, 2.0), 0.0, 1.0, 0.0, 2.0, 1.0, id="dois_cubos_unitarios"),
        pytest.param((0.0, 1.5, 4.0), 0.0, 0.4, 0.0, 2.8, 1.2, id="dois_blocos_parede"),
    ],
)
def test_aceitacao_dois_cubos_justapostos_fecha_em_um_anel_area_soma(xs, y0, y1, z0, z1, z_corte):
    """Dois cubos justapostos com face comum: hoje anel aberto; com D fecha em 1 anel de area=soma."""
    v, t = _blocos_em_fila_soldados_np(xs, y0, y1, z0, z1)
    v0, t0 = v.copy(), t.copy()
    v.setflags(write=False)
    t.setflags(write=False)
    _, _, segs_ref = _ref_cortar(v, t, z_corte)
    _, ab_ref = aneis.aneis_de_segmentos(segs_ref)
    assert len(ab_ref) >= 1 and len(segs_ref) == 14, "sanidade: hoje mantem face interna e abre anel"

    res = corte_plano.cortar_malha_no_plano(v, t, z_corte)
    for _ in range(2):
        _assert_igual_bit_a_bit(corte_plano.cortar_malha_no_plano(v, t, z_corte), res)
    assert np.array_equal(v, v0) and np.array_equal(t, t0)
    _, _, segs = res
    assert len(segs) == 12
    fechados, abertos = aneis.aneis_de_segmentos(segs)
    assert len(fechados) == 1 and abertos == []
    area_esp = (xs[-1] - xs[0]) * (y1 - y0)
    perim_esp = 2.0 * ((xs[-1] - xs[0]) + (y1 - y0))
    assert abs(aneis._area(fechados[0])) == pytest.approx(area_esp, abs=1e-9)
    assert _perimetro_anel(fechados[0]) == pytest.approx(perim_esp, abs=1e-9)


def test_aceitacao_tres_blocos_em_fila_fecha_em_um_anel_area_soma():
    """Tres blocos soldados em fila: 2 faces internas canceladas -> 1 anel fechado de area=soma."""
    xs, y0, y1 = (0.0, 1.0, 2.5, 4.0), 0.0, 0.5
    v, t = _blocos_em_fila_soldados_np(xs, y0, y1, 0.0, 2.8)
    _, _, segs_ref = _ref_cortar(v, t, 1.2)
    _, ab_ref = aneis.aneis_de_segmentos(segs_ref)
    assert len(ab_ref) >= 1 and len(segs_ref) == 20

    _, _, segs = corte_plano.cortar_malha_no_plano(v, t, 1.2)
    assert len(segs) == 16
    fechados, abertos = aneis.aneis_de_segmentos(segs)
    assert len(fechados) == 1 and abertos == []
    assert abs(aneis._area(fechados[0])) == pytest.approx(2.0, abs=1e-9)
    assert _perimetro_anel(fechados[0]) == pytest.approx(9.0, abs=1e-9)


def test_aceitacao_planta_cache_justapostos_zera_parciais_e_ganha_tampa(monkeypatch):
    """Em `desenhar_planta_cache`, parede justaposta deixa de contar em `secoes_parciais` e ganha tampa."""
    grupos_passados: list[list] = []
    real_recorte = recorte.recortar_fora_dos_aneis
    monkeypatch.setattr(
        recorte,
        "recortar_fora_dos_aneis",
        lambda pols, grupos, *a, **k: (grupos_passados.append(list(grupos)), real_recorte(pols, grupos, *a, **k))[1],
    )
    parede_2 = _blocos_em_fila_soldados_np((0.0, 2.0, 4.0), 0.0, 0.4, 0.0, 2.8)
    pecas = [
        (10, "G_JUSTA", "IfcWall", parede_2),
        *_boas(3, id0=11, x0=6.0),
        (20, "G_BARRA_1", "IfcSlab", _caixa_np(0.9, -0.5, 0.0, 1.1, 1.0, 0.2)),
        (21, "G_BARRA_2", "IfcSlab", _caixa_np(2.9, -0.5, 0.0, 3.1, 1.0, 0.2)),
    ]
    resp, motivo = planta_cache.desenhar_planta_cache(*_montar_cena_numpy(pecas, altura_corte_m=1.2))
    assert motivo is None and resp is not None and resp["ok"] is True
    assert type(resp["secoes_parciais"]) is int and resp["secoes_parciais"] == 0
    assert len(grupos_passados) == 1 and len(grupos_passados[0]) == 4

    parsed = _parse_svg(resp["svg"])
    pls_j = _polilinhas_mundo(parsed.cut_by_guid["G_JUSTA"])
    assert len(pls_j) == 1 and _eh_fechada(pls_j[0])
    assert abs(aneis._area(pls_j[0][:-1])) == pytest.approx(1.6, abs=1e-4)

    segs_proj = _polilinhas_para_segs(_polilinhas_mundo(parsed.proj_groups))
    # Ambos os blocos tampam as barras de piso sob a parede (y=0.2), mantendo fora (y=-0.3, y=0.8) visivel
    assert float(_dist_pontos_a_segs(np.array([[0.9, 0.2], [1.1, 0.2], [2.9, 0.2], [3.1, 0.2]]), segs_proj).min()) > 0.05
    assert float(_dist_pontos_a_segs(np.array([[0.9, -0.3], [1.1, 0.8], [2.9, -0.3], [3.1, 0.8]]), segs_proj).max()) <= 1e-3
    estilo.aplicar_estilo(resp["svg"], "1:50")

    # 2 boas + 2 paredes de 3 blocos em fila (antes 50% > 25% -> caia secao_aberta; com D passa com 0 parciais)
    pecas_4 = [
        *_boas(2, id0=10, x0=0.0),
        (12, "G_FILA_1", "IfcWall", _blocos_em_fila_soldados_np((10.0, 11.0, 12.5, 14.0), 0.0, 0.4, 0.0, 2.8)),
        (13, "G_FILA_2", "IfcWall", _blocos_em_fila_soldados_np((16.0, 17.0, 18.5, 20.0), 0.0, 0.4, 0.0, 2.8)),
    ]
    r4, mot4 = planta_cache.desenhar_planta_cache(*_montar_cena_numpy(pecas_4, altura_corte_m=1.2))
    assert mot4 is None and r4 is not None and r4["secoes_parciais"] == 0


# ---------- (2) NAO-REGRESSAO (PASSAM HOJE E PASSAM COM D) ----------
def test_nao_regressao_solidos_canonicos_bordas_e_degenerado_bit_a_bit():
    """Cubo, L, anel com furo, piramide, octaedro, nao-cruzamento e degenerado: identico bit a bit a `_ref_cortar`."""
    ext = [(0.0, 0.0), (4.0, 0.0), (4.0, 4.0), (0.0, 4.0)]
    furo = [(1.0, 1.0), (3.0, 1.0), (3.0, 3.0), (1.0, 3.0)]
    tri_deg_v = np.array([[0.0, 0.0, 0.0], [2.0, 0.0, 2.0]], dtype=np.float64)
    tri_deg_t = np.array([[0, 0, 1], [0, 1, 1]], dtype=np.int32)
    casos = [
        ("cubo_meio", *_caixa_np(0.0, 0.0, 0.0, 3.0, 2.0, 4.0), 1.5, True),
        ("prisma_l", *_prisma_l_np(0.0, 2.8), 1.2, True),
        ("anel_furo_tubo", *_tubo_np(ext, furo, 0.0, 2.8), 1.2, True),
        ("anel_quadrado", *anel_quadrado(4.0, 2.0, 0.0, 2.0), 1.0, True),
        ("piramide", *piramide(), 1.0, True),
        ("octaedro_equador", *octaedro(), 0.0, True),
        ("plano_acima", *_caixa_np(0.0, 0.0, 0.0, 2.0, 2.0, 2.0), 5.0, False),
        ("plano_abaixo", *_caixa_np(0.0, 0.0, 3.0, 2.0, 2.0, 5.0), 1.0, False),
        ("vazio", np.zeros((0, 3), dtype=np.float64), np.zeros((0, 3), dtype=np.int32), 1.0, False),
        ("degenerado_idx_igual", tri_deg_v, tri_deg_t, 1.0, False),
    ]
    for nome, v, t, z, checar_area in casos:
        v0, t0 = v.copy(), t.copy()
        v.setflags(write=False)
        t.setflags(write=False)
        ref = _ref_cortar(v, t, z)
        obt = corte_plano.cortar_malha_no_plano(v, t, z)
        _assert_igual_bit_a_bit(obt, ref)
        assert np.array_equal(v, v0) and np.array_equal(t, t0), nome
        if checar_area:
            f_ref, ab_ref = aneis.aneis_de_segmentos(ref[2])
            f_obt, ab_obt = aneis.aneis_de_segmentos(obt[2])
            assert ab_ref == [] and ab_obt == [] and len(f_obt) == len(f_ref), nome
            assert sum(aneis._area(a) for a in f_obt) == pytest.approx(sum(aneis._area(a) for a in f_ref), abs=1e-12)


def test_nao_regressao_fuzz_360_solidos_bem_formados_bit_a_bit():
    """Fuzz seed fixa (360 malhas aleatorias de solido bem formado): saida bit a bit igual a `_ref_cortar`."""
    rng = np.random.default_rng(20260424)
    n_cruzou = 0
    for idx in range(360):
        v, t, z = _malha_aleatoria_bem_formada(rng, idx)
        v0, t0 = v.copy(), t.copy()
        v.setflags(write=False)
        t.setflags(write=False)
        ref = _ref_cortar(v, t, z)
        obt = corte_plano.cortar_malha_no_plano(v, t, z)
        _assert_igual_bit_a_bit(obt, ref)
        assert np.array_equal(v, v0) and np.array_equal(t, t0)
        if len(ref[2]) > 0:
            n_cruzou += 1
    assert n_cruzou >= 250


# ---------- (3) SOBREPOSICAO SEM COINCIDENCIA (PASSA HOJE E PASSA COM D) ----------
@pytest.mark.parametrize(
    ("caixa_a", "caixa_b"),
    [
        pytest.param((0.0, 0.0, 0.0, 2.0, 1.0, 2.8), (1.0, 0.2, 0.0, 3.0, 1.2, 2.8), id="deslocados"),
        pytest.param((0.0, 0.0, 0.0, 2.0, 1.0, 2.8), (0.5, -0.5, 0.0, 1.5, 1.5, 2.8), id="em_cruz"),
    ],
)
def test_sobreposicao_sem_coincidencia_mantem_segmentos_e_nao_piora_fechadas(caixa_a, caixa_b):
    """Dois cubos com volumes interpenetrando SEM faces coincidentes:

    Comportamento esperado de D: nenhum segmento coincide (multiplicidade 1 para todos), logo
    todos os segmentos ficam exatamente como hoje e nenhuma intersecao 2D e inventada.
    Pecas que hoje fecham em 2 aneis fechados continuam fechando sem piorar (secoes_parciais=0).
    """
    v, t = _combinar_malhas(_caixa_np(*caixa_a), _caixa_np(*caixa_b))
    ref = _ref_cortar(v, t, 1.2)
    obt = corte_plano.cortar_malha_no_plano(v, t, 1.2)
    _assert_igual_bit_a_bit(obt, ref)
    assert len(obt[2]) == 16

    fech, ab = aneis.aneis_de_segmentos(obt[2])
    assert len(fech) == 2 and ab == []
    assert sum(abs(aneis._area(a)) for a in fech) == pytest.approx(4.0, abs=1e-9)

    resp, mot = planta_cache.desenhar_planta_cache(
        *_montar_cena_numpy([(10, "G_SOBRE", "IfcWall", (v, t))], altura_corte_m=1.2)
    )
    assert mot is None and resp is not None and resp["secoes_parciais"] == 0


# ---------- (4) ORDEM INVERTIDA E MULTIPLICIDADES 2, 3, 4 ----------
def test_ordem_invertida_e_multiplicidades_2_3_4():
    """Segmentos com ordem invertida contam como o mesmo; mult 2 e 4 descartam; mult 3 mantem 1."""
    v = np.array([[0.0, 0.0, 0.0], [2.0, 0.0, 2.0], [0.0, 2.0, 2.0]], dtype=np.float64)
    # 1) Ordem invertida (mult=2) -> descartado
    _, _, segs_inv2 = corte_plano.cortar_malha_no_plano(v, np.array([[0, 1, 2], [0, 2, 1]], dtype=np.int32), 1.0)
    assert segs_inv2.shape == (0, 4)

    # 2) Multiplicidade 3 (com inversoes) -> mantem 1
    _, _, segs_3 = corte_plano.cortar_malha_no_plano(
        v, np.array([[0, 1, 2], [0, 2, 1], [0, 1, 2]], dtype=np.int32), 1.0
    )
    assert segs_3.shape == (1, 4)
    pts_3 = {(round(float(segs_3[0, 0]), 9), round(float(segs_3[0, 1]), 9)),
             (round(float(segs_3[0, 2]), 9), round(float(segs_3[0, 3]), 9))}
    assert pts_3 == {(1.0, 0.0), (0.0, 1.0)}

    # 3) Multiplicidade 4 (mesma ordem e alternada) -> descartado
    for tris_4 in (
        np.array([[0, 1, 2], [0, 1, 2], [0, 1, 2], [0, 1, 2]], dtype=np.int32),
        np.array([[0, 1, 2], [0, 2, 1], [0, 1, 2], [0, 2, 1]], dtype=np.int32),
    ):
        _, _, segs_4 = corte_plano.cortar_malha_no_plano(v, tris_4, 1.0)
        assert segs_4.shape == (0, 4)

    # 4) Em solido: face +X com mult=3 fecha (area=2.0); face +X com mult=4 some (6 segs, aberto)
    v3, t3 = _caixa_com_face_mult_np(3, inverter=True)
    _, _, s_c3 = corte_plano.cortar_malha_no_plano(v3, t3, 1.2)
    f3, a3 = aneis.aneis_de_segmentos(s_c3)
    assert len(s_c3) == 8 and len(f3) == 1 and a3 == [] and abs(aneis._area(f3[0])) == pytest.approx(2.0, abs=1e-9)

    v4, t4 = _caixa_com_face_mult_np(4, inverter=True)
    _, _, s_c4 = corte_plano.cortar_malha_no_plano(v4, t4, 1.2)
    f4, a4 = aneis.aneis_de_segmentos(s_c4)
    assert len(s_c4) == 6 and f4 == [] and len(a4) == 1


# ---------- (5) MUTANTES (1 TESTE POR ERRO PLAUSIVEL) ----------
def test_mutante_01_descartar_todo_duplicado_inclusive_impar():
    """Mutante 1: usar `count == 1` em vez de `count % 2 == 1` descartaria face externa de mult=3."""
    v, t = _blocos_em_fila_soldados_np((0.0, 1.0, 2.0), 0.0, 1.0, 0.0, 2.0)
    # Duplica 2x a face externa esquerda (-X do 1o cubo, indices 10 e 11 de `t`) -> mult=3 nessa face, mult=2 na interna
    face_ext = t[10:12]
    t_m = np.vstack([t, face_ext[:, ::-1], face_ext]).astype(np.int32)
    _, _, segs = corte_plano.cortar_malha_no_plano(v, t_m, 1.0)
    fech, ab = aneis.aneis_de_segmentos(segs)
    assert len(segs) == 12 and len(fech) == 1 and ab == []
    assert abs(aneis._area(fech[0])) == pytest.approx(2.0, abs=1e-9)


def test_mutante_02_ignorar_ordem_invertida():
    """Mutante 2: contar chave orientada `(ia, ib)` em vez de nao-orientada deixa pares invertidos vivos."""
    v = np.array([[0.0, 0.0, 0.0], [2.0, 0.0, 2.0], [0.0, 2.0, 2.0]], dtype=np.float64)
    _, _, s_a = _ref_cortar(v, np.array([[0, 1, 2]], dtype=np.int32), 1.0)
    _, _, s_b = _ref_cortar(v, np.array([[0, 2, 1]], dtype=np.int32), 1.0)
    assert np.array_equal(s_a[0, :2], s_b[0, 2:]) and np.array_equal(s_a[0, 2:], s_b[0, :2])

    _, _, segs_par = corte_plano.cortar_malha_no_plano(v, np.array([[0, 1, 2], [0, 2, 1]], dtype=np.int32), 1.0)
    assert len(segs_par) == 0

    v2, t2 = _blocos_em_fila_soldados_np((0.0, 1.0, 2.0), 0.0, 1.0, 0.0, 2.0)
    _, _, segs_cubos = corte_plano.cortar_malha_no_plano(v2, t2, 1.0)
    fech, ab = aneis.aneis_de_segmentos(segs_cubos)
    assert len(segs_cubos) == 12 and len(fech) == 1 and ab == []


def test_mutante_03_manter_os_dois_de_multiplicidade_2():
    """Mutante 3: manter os dois (ou um) segmentos de multiplicidade 2 (mesma orientacao ou oposta)."""
    v = np.array([[0.0, 0.0, 0.0], [2.0, 0.0, 2.0], [0.0, 2.0, 2.0]], dtype=np.float64)
    _, _, segs_dup = corte_plano.cortar_malha_no_plano(v, np.array([[0, 1, 2], [0, 1, 2]], dtype=np.int32), 1.0)
    assert len(segs_dup) == 0

    v2, t2 = _blocos_em_fila_soldados_np((0.0, 1.0, 2.0), 0.0, 1.0, 0.0, 2.0)
    _, _, segs = corte_plano.cortar_malha_no_plano(v2, t2, 1.0)
    assert len(segs) == 12
    # Nenhum segmento da face interna x=1.0 pode restar
    eh_interno = (np.abs(segs[:, 0] - 1.0) < 1e-9) & (np.abs(segs[:, 2] - 1.0) < 1e-9)
    assert not np.any(eh_interno)


def test_mutante_04_mexer_em_solido_unico():
    """Mutante 4: alterar ordem, direcao `(ia, ib)` ou parte abaixo num solido unico bem formado."""
    ext = [(0.0, 0.0), (4.0, 0.0), (4.0, 4.0), (0.0, 4.0)]
    furo = [(1.0, 1.0), (3.0, 1.0), (3.0, 3.0), (1.0, 3.0)]
    for v, t, z in (
        (*_caixa_np(0.0, 0.0, 0.0, 3.0, 2.0, 4.0), 1.2),
        (*_prisma_l_np(0.0, 2.8), 1.2),
        (*_tubo_np(ext, furo, 0.0, 2.8), 1.2),
        (*octaedro(), 0.0),
    ):
        _assert_igual_bit_a_bit(corte_plano.cortar_malha_no_plano(v, t, z), _ref_cortar(v, t, z))


def test_mutante_05_perder_ordem_estavel():
    """Mutante 5: usar `set`, `sorted(chaves)` ou trocar `(ia, ib)` por `(min, max)` quebra ordem estavel."""
    rng = np.random.default_rng(1337)
    v, t = _permutar_malha(*_blocos_em_fila_soldados_np((0.0, 1.0, 2.0), 0.0, 1.0, 0.0, 2.0), rng)
    _, _, segs_ref = _ref_cortar(v, t, 1.0)
    mask_int = (np.abs(segs_ref[:, 0] - 1.0) < 1e-9) & (np.abs(segs_ref[:, 2] - 1.0) < 1e-9)
    assert int(np.sum(mask_int)) == 2
    segs_esp = segs_ref[~mask_int]

    _, _, segs_obt = corte_plano.cortar_malha_no_plano(v, t, 1.0)
    assert segs_obt.shape == segs_esp.shape and np.array_equal(segs_obt, segs_esp)

    # Tambem checa solido unico embaralhado contra `_ref_cortar`
    vc, tc = _permutar_malha(*_caixa_np(0.0, 0.0, 0.0, 3.0, 2.0, 4.0), rng)
    _assert_igual_bit_a_bit(corte_plano.cortar_malha_no_plano(vc, tc, 1.2), _ref_cortar(vc, tc, 1.2))


# ---------- (6) INTEGRACAO DESENHO: SHA 3 RODADAS E MALHAS_MUNDO INTACTO ----------
@pytest.mark.parametrize(
    "offset",
    [pytest.param((0.0, 0.0), id="origem"), pytest.param((500_000.25, 7_500_000.75), id="utm")],
)
def test_integracao_desenho_sha256_3_rodadas_e_malhas_mundo_nao_mutado(offset):
    """Cena com paredes justapostas + boas + furo: SHA identico 3 rodadas, reversa, threads=4; `malhas_mundo` intacto."""
    ox, oy = offset
    ext = [(16.0, 0.0), (18.0, 0.0), (18.0, 2.0), (16.0, 2.0)]
    furo = [(16.5, 0.5), (17.5, 0.5), (17.5, 1.5), (16.5, 1.5)]
    base = [
        (10, "G_JUSTA_2", "IfcWall", _blocos_em_fila_soldados_np((0.0, 1.5, 3.0), 0.0, 0.4, 0.0, 2.8)),
        (11, "G_JUSTA_3", "IfcWall", _blocos_em_fila_soldados_np((5.0, 6.0, 7.5, 9.0), 0.0, 0.4, 0.0, 2.8)),
        *_boas(2, id0=12, x0=11.0, passo=2.5),
        (14, "G_FURO", "IfcWall", _tubo_np(ext, furo, 0.0, 2.8)),
        (15, "G_LAJE", "IfcSlab", _caixa_np(0.0, -0.5, -0.2, 19.0, 2.5, 0.0)),
    ]
    pecas = [(i, g, c, _transladar_malha(m, ox, oy)) for i, g, c, m in base]
    f, ped, malhas, ev = _montar_cena_numpy(pecas, altura_corte_m=1.2, threads=1)
    snap = _congelar_snapshot(malhas, ped)
    shas = []
    for _ in range(3):
        r, mot = planta_cache.desenhar_planta_cache(f, ped, malhas, ev)
        assert mot is None and r is not None and r["ok"] is True and r["secoes_parciais"] == 0
        shas.append(_sha256(r["svg"]))
    assert shas[0] == shas[1] == shas[2]
    _checar_imutavel(malhas, ped, *snap)

    r_rev, mot_rev = planta_cache.desenhar_planta_cache(*_montar_cena_numpy(list(reversed(pecas)), altura_corte_m=1.2, threads=1))
    assert mot_rev is None and _sha256(r_rev["svg"]) == shas[0]
    r_t4, mot_t4 = planta_cache.desenhar_planta_cache(*_montar_cena_numpy(pecas, altura_corte_m=1.2, threads=4))
    assert mot_t4 is None and _sha256(r_t4["svg"]) == shas[0]


# ---------- (7) DEFEITOS REV1: ARESTAS_PLANO COM CONTADORES E CHAVE XOR POR COORDENADAS ----------
def _quad_tris(a: int, b: int, c: int, d: int) -> list[list[int]]:
    return [[a, b, c], [a, c, d]]


def test_defeito_1a_face_dupla_com_aresta_no_plano_deve_cancelar():
    """Face vertical dupla (mult=2) com aresta horizontal em z=1.0: 0 segs; mult=3: 1 seg."""
    v = np.array(
        [[0.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0], [0.0, 1.0, 1.0], [0.0, 0.0, 2.0], [0.0, 1.0, 2.0]],
        dtype=np.float64,
    )
    t_par = np.array([[2, 3, 0], [2, 4, 3], [3, 2, 0], [3, 4, 2]], dtype=np.int32)
    _, _, s_fora = corte_plano.cortar_malha_no_plano(v, t_par, 0.5)
    assert len(s_fora) == 0  # sanidade fora do plano
    _, _, s_no = corte_plano.cortar_malha_no_plano(v, t_par, 1.0)
    assert len(s_no) == 0, f"arestas_plano ignorou multiplicidade par: retornou {len(s_no)} seg(s)"

    # Multiplicidade impar (3) em aresta no plano z=1.0 deve manter 1 segmento
    t_impar = np.array([[2, 3, 0], [2, 4, 3], [3, 2, 0], [3, 4, 2], [2, 3, 0], [2, 4, 3]], dtype=np.int32)
    _, _, s_imp = corte_plano.cortar_malha_no_plano(v, t_impar, 1.0)
    assert len(s_imp) == 1
