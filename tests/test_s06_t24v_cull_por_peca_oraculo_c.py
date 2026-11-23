# SPDX-License-Identifier: AGPL-3.0-or-later
"""Parte 3 de test_s06_t24v_cull_por_peca_oraculo.py (divisao mecanica em PRs de ate 400 linhas). Auxiliares e fixtures vem das partes anteriores."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import gc
import glob
import hashlib
import math
import os
import pickle
import statistics
import threading
import time
from unittest import mock
import numpy as np
import pytest
import obim_geometria.visibilidade as vis
from obim_geometria.visib_base import (
    _arestas_candidatas,
    _cel_caixa,
    _dedup_int64,
    _expandir_celulas,
    _fatias,
    _preparar_triangulos,
    _rle_idx,
    _subseg_cels,
)
from obim_geometria.visib_faixas import _passagem_faixas_orientadas
from obim_geometria.visib_mapa import (
    _compactar_H,
    _filtrar_e_recortar,
    _mapa_z_conservador,
    _subgrade_celulas_densas,
    _varrer_cels_triangulos,
)
from obim_geometria.visibilidade import (
    _dedup_triangulos,
    _limpar_malha,
    _resolver_trabalhadores_auto,
    _validar_trabalhadores,
    linhas_visiveis_multi,
)
from test_s06_t24v_cull_por_peca_oraculo import _DIR_DIST, _F_CAIXA  # noqa: F401
from test_s06_t24v_cull_por_peca_oraculo_b import _assert_bit_a_bit, _caixa, _cena_triangulos_ingremes, _cena_varias_pecas_espalhadas, _comprimento_total, _executar_e_validar_propriedade, _linhas_visiveis_multi_ref, _peca_uma_aresta, _quad_vertical, _sha_polilinhas, _terreno_plano, _triangulo_unico, _validar_conjunto_mantido  # noqa: F401



def _cena_pecas_sobrepostas():
    pecas = [
        _caixa(0.0, 0.0, 0.0, 20.0, 20.0, 0.2),
        _caixa(4.0, 4.0, 3.0, 12.0, 12.0, 3.3),
        _caixa(5.0, 5.0, 0.5, 11.0, 11.0, 1.2),  # escondida
        _caixa(5.0, 5.0, 0.5, 11.0, 11.0, 1.2),  # duplicata exata
        _caixa(10.0, 6.0, 1.0, 16.0, 10.0, 4.0, incl_y=0.35),  # corta teto
        _caixa(2.0, 8.0, 2.0, 8.0, 14.0, 2.8, rot_z=0.5),
        _caixa(4.5, 4.5, 4.0, 7.5, 7.5, 4.5, rot_z=0.2),
        _caixa(14.0, 14.0, 0.5, 18.0, 18.0, 2.0),
    ]
    return pecas


def _cena_peca_toca_borda_dominio():
    W, H = 40.0, 30.0
    pecas = [
        _caixa(0.0, 0.0, 0.0, 1.0, 1.0, 1.0),
        _caixa(W - 1.0, H - 1.0, 0.0, W, H, 1.0),
        # Toca exatamente as 4 bordas do dominio
        _caixa(0.0, 12.0, 0.2, 1.2, 16.0, 0.8),
        _caixa(0.0, 13.0, 1.5, 0.6, 15.0, 2.0),  # oclusor na borda x=0
        _caixa(W - 1.2, 10.0, 0.2, W, 14.0, 0.8),
        _caixa(W - 0.5, 11.0, 1.5, W, 13.0, 2.0),  # oclusor na borda x=W
        _caixa(15.0, 0.0, 0.2, 19.0, 1.2, 0.8),
        _caixa(16.0, 0.0, 1.5, 18.0, 0.5, 2.0),  # oclusor na borda y=0
        _caixa(18.0, H - 1.2, 0.2, 22.0, H, 0.8),
        _caixa(19.0, H - 0.5, 1.5, 21.0, H, 2.0),  # oclusor na borda y=H
        # Toca a borda a +-1e-7 m
        _caixa(1e-7, 20.0, 0.2, 0.8, 22.0, 0.9),
        _caixa(0.0, 20.2, 1.5, 1e-7 + 0.4, 21.8, 2.0),
    ]
    return pecas


def _cena_peca_uma_aresta():
    """Inclui pecas com exatamente 1 aresta ativa (`len(ek_idx) == 1`): uma visivel e uma ocluida."""
    pecas = [
        _caixa(0.0, 0.0, 0.0, 20.0, 20.0, 0.2),
        _peca_uma_aresta(5.0, 5.0, z_top=2.0, z_bot=0.5),
        _peca_uma_aresta(12.0, 12.0, z_top=2.0, z_bot=0.5),
        # Oclusor cobrindo a 2a peca de 1 aresta (sem tocar a 1a)
        _caixa(11.5, 11.5, 2.8, 12.5, 12.5, 3.0),
        # Peca longe para alargar o dominio
        _caixa(70.0, 70.0, 0.0, 72.0, 72.0, 1.0),
    ]
    return pecas


def _cena_triangulo_enorme_cobre_varias_pecas():
    """Triangulo gigante (100x100 m) cujos 3 vertices ficam longe de varias pecas espalhadas."""
    tri_gigante = _triangulo_unico([0.0, 0.0, 2.5], [100.0, 0.0, 2.5], [50.0, 100.0, 2.5])
    tri_gigante_inclinado = _triangulo_unico([0.0, 0.0, 0.5], [100.0, 0.0, 3.5], [50.0, 100.0, 1.8])
    pecas = [tri_gigante, tri_gigante_inclinado]
    for cx, cy, z in (
        (20.0, 15.0, 0.2),
        (50.0, 25.0, 1.0),
        (50.0, 50.0, 3.2),  # acima dos dois triangulos gigantes
        (75.0, 15.0, 1.2),
        (45.0, 70.0, 0.8),
        (5.0, 90.0, 0.5),  # fora dos triangulos gigantes
    ):
        pecas.append(_caixa(cx - 1.0, cy - 1.0, z, cx + 1.0, cy + 1.0, z + 0.6, rot_z=0.3))
    return pecas


def _cena_utm():
    off = np.array([500_000.0, 7_400_000.0, 720.0], dtype=np.float64)
    base = _cena_varias_pecas_espalhadas()[:14] + _cena_peca_toca_borda_dominio()[:6]
    return [(v + off, t.copy()) for v, t in base]


_CENAS_ESPECIAIS = {
    "varias_pecas_espalhadas": _cena_varias_pecas_espalhadas,
    "triangulos_ingremes": _cena_triangulos_ingremes,
    "pecas_sobrepostas": _cena_pecas_sobrepostas,
    "peca_toca_borda_dominio": _cena_peca_toca_borda_dominio,
    "peca_uma_aresta": _cena_peca_uma_aresta,
    "triangulo_enorme_cobre_varias_pecas": _cena_triangulo_enorme_cobre_varias_pecas,
    "coordenadas_utm": _cena_utm,
}


def _gerar_cena_fuzz(seed: int) -> list[tuple[np.ndarray, np.ndarray]]:
    """Gera cena sintetica variada com semente fixa cobrindo todos os padroes geometricos."""
    rng = np.random.default_rng(240_000 + seed)
    lado = float(rng.choice([3.0, 12.0, 40.0, 120.0]))
    usar_utm = (seed % 7 == 0)
    off = (
        np.array([500_000.0, 7_400_000.0, 700.0], dtype=np.float64)
        if usar_utm
        else np.zeros(3, dtype=np.float64)
    )
    pecas: list[tuple[np.ndarray, np.ndarray]] = []
    n_pecas = int(rng.integers(4, 13))

    # Espalhadas e sobrepostas
    for k in range(n_pecas):
        x0 = float(rng.uniform(0.0, lado * 0.85))
        y0 = float(rng.uniform(0.0, lado * 0.85))
        dx = float(rng.uniform(0.05, max(0.15, lado * 0.18)))
        dy = float(rng.uniform(0.05, max(0.15, lado * 0.18)))
        z0 = float(rng.uniform(-1.0, 3.0))
        dz = float(rng.uniform(0.05, 1.5))
        modo = int(rng.integers(0, 6))
        if modo == 0:
            # Peca tocando exatamente a borda do dominio
            borda = k % 4
            if borda == 0:
                x0 = 0.0
            elif borda == 1:
                x0 = lado - dx
            elif borda == 2:
                y0 = 0.0
            else:
                y0 = lado - dy
            v, t = _caixa(x0, y0, z0, x0 + dx, y0 + dy, z0 + dz)
        elif modo == 1:
            # Triangulo ingreme
            dxs = float(rng.uniform(1e-4, 2e-3))
            v = np.array(
                [
                    [x0, y0, z0 + dz],
                    [x0 + dxs, y0, z0],
                    [x0, y0 + dy, z0 + dz],
                    [x0 + dxs, y0 + dy, z0],
                ],
                dtype=np.float64,
            )
            t = np.array([[0, 1, 2], [1, 3, 2]], dtype=np.int64)
        elif modo == 2:
            # Quad vertical (poucas arestas, sobreposto a outras pecas)
            v, t = _quad_vertical(x0, y0, x0 + dx, y0 + dy * 0.5, z0, z0 + dz)
        elif modo == 3:
            # Triangulo enorme cobrindo varias pecas
            zt = float(rng.uniform(0.5, 4.0))
            v, t = _triangulo_unico(
                [0.0, 0.0, zt],
                [lado, 0.0, zt + float(rng.uniform(-0.3, 0.3))],
                [lado * 0.5, lado, zt + float(rng.uniform(-0.3, 0.3))],
            )
        else:
            rot = float(rng.uniform(0.0, math.pi)) if rng.random() < 0.7 else 0.0
            incl = float(rng.uniform(-0.45, 0.45)) if rng.random() < 0.35 else 0.0
            v, t = _caixa(x0, y0, z0, x0 + dx, y0 + dy, z0 + dz, rot_z=rot, incl_y=incl)
        pecas.append((v + off, t))

    # Garante sobreposicao direta em parte das seeds
    if seed % 3 == 0:
        bx, by = lado * 0.4, lado * 0.4
        pecas.append((_caixa(bx, by, 0.0, bx + 1.0, by + 1.0, 0.6)[0] + off, _F_CAIXA.copy()))
        pecas.append((_caixa(bx + 0.1, by + 0.1, 1.2, bx + 0.9, by + 0.9, 1.5)[0] + off, _F_CAIXA.copy()))
    return pecas


# ---------------------------------------------------------------------------
# (1) Igualdade bit a bit + propriedade do conjunto mantido
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("nome", list(_CENAS_ESPECIAIS.keys()))
def test_igualdade_cenas_especiais_bit_a_bit_e_propriedade(nome):
    """Cenas especiais: saida bit a bit identica a referencia e propriedade do cull preservada."""
    pecas = _CENAS_ESPECIAIS[nome]()
    ref = _linhas_visiveis_multi_ref(pecas, trabalhadores=1)
    obt, regs = _executar_e_validar_propriedade(pecas, ctx=f"especial/{nome}")
    _assert_bit_a_bit(obt, ref, ordem_exata=True, ctx=f"especial/{nome}")
    assert len(regs) > 0
    if nome == "peca_uma_aresta":
        assert any(r["n_ek"] == 1 for r in regs), "cena peca_uma_aresta deve exercitar len(ek_idx)==1"


@pytest.mark.parametrize("bloco", range(20), ids=[f"seeds_{b * 10:03d}_{b * 10 + 9:03d}" for b in range(20)])
def test_igualdade_fuzz_200_seeds_bit_a_bit_e_propriedade(bloco):
    """Fuzz com 200 seeds fixas (20 blocos x 10): bit a bit igual a referencia e propriedade do cull."""
    for seed in range(bloco * 10, bloco * 10 + 10):
        pecas = _gerar_cena_fuzz(seed)
        ref = _linhas_visiveis_multi_ref(pecas, trabalhadores=1)
        obt, _ = _executar_e_validar_propriedade(pecas, ctx=f"fuzz_{seed}")
        _assert_bit_a_bit(obt, ref, ordem_exata=True, ctx=f"fuzz_{seed}")


def test_cull_tris_direto_propriedade_superconjunto():
    """Chamada direta a `vis._cull_tris` preserva superconjunto sobre `kept` esparso, borda, 1 aresta e UTM."""
    rng = np.random.default_rng(240_999)
    for off_x, off_y in ((0.0, 0.0), (500_000.0, 7_400_000.0)):
        n_tris = 400
        x0 = off_x + rng.uniform(0.0, 100.0, n_tris)
        y0 = off_y + rng.uniform(0.0, 100.0, n_tris)
        tx0 = x0
        tx1 = x0 + rng.uniform(0.01, 2.0, n_tris)
        ty0 = y0
        ty1 = y0 + rng.uniform(0.01, 2.0, n_tris)
        # Inclui triangulo gigante e triangulo exatamente na borda
        tx0[0], tx1[0], ty0[0], ty1[0] = off_x, off_x + 100.0, off_y, off_y + 100.0
        tx0[1], tx1[1], ty0[1], ty1[1] = off_x + 49.0, off_x + 50.0, off_y + 49.0, off_y + 51.0
        # kept esparso (nao-contiguo: pula indices baixos e alterna)
        kept = np.array([0, 1, *range(5, n_tris, 2)], dtype=np.int64)
        # 1 unica aresta tocando exatamente x = off_x + 50.0
        ea_ = np.array([[off_x + 50.0, off_y + 49.5, 1.0]], dtype=np.float64)
        eb_ = np.array([[off_x + 50.0, off_y + 50.5, 1.0]], dtype=np.float64)
        mn_x, mn_y = float(tx0.min()), float(ty0.min())
        dx_dom, dy_dom = float(tx1.max() - mn_x), float(ty1.max() - mn_y)

        kept_prod = vis._cull_tris(kept, ea_, eb_, tx0, tx1, ty0, ty1, mn_x, mn_y, dx_dom, dy_dom)
        _validar_conjunto_mantido(
            kept_prod, kept, ea_, eb_, tx0, tx1, ty0, ty1, mn_x, mn_y, dx_dom, dy_dom,
            ctx=f"direto_off_{off_x:g}",
        )
        assert 0 in set(kept_prod.tolist()), "triangulo gigante descartado"
        assert 1 in set(kept_prod.tolist()), "triangulo tocando borda exata descartado"


# ---------------------------------------------------------------------------
# (2) Propriedade do cull: nunca descarta triangulo que oclui aresta
# ---------------------------------------------------------------------------

def test_propriedade_oclusor_peca_distante_nao_some():
    """Oclusor que cobre somente a aresta de uma peca distante (195, 195) nao pode sumir."""
    pecas = [
        # Massa de pecas perto da origem para dominar a cena
        *[_caixa(float(i), float(j), 0.0, float(i) + 0.6, float(j) + 0.6, 0.8) for i in range(6) for j in range(6)],
        # Peca distante em (195, 195): barra de comprimento 2.0 m em z=1.0
        _quad_vertical(195.0, 195.0, 197.0, 195.0, 0.0, 1.0),
        # Oclusor pequeno que cobre SOMENTE o trecho [195.5, 196.5] da barra distante
        _caixa(195.5, 194.8, 2.0, 196.5, 195.2, 2.3),
    ]
    ref = _linhas_visiveis_multi_ref(pecas, trabalhadores=1)
    obt, regs = _executar_e_validar_propriedade(pecas, ctx="oclusor_distante")
    _assert_bit_a_bit(obt, ref, ordem_exata=True, ctx="oclusor_distante")

    idx_barra = len(pecas) - 2
    # Barra tem topo+base (4.0 m), mas metade [195.5, 196.5] esta ocluida -> sobram 2.0 m (topo+base nas pontas)
    assert _comprimento_total(obt[idx_barra]) == pytest.approx(2.0, abs=1e-3), (
        f"oclusor da peca distante sumiu: comp={_comprimento_total(obt[idx_barra]):.4f} m"
    )
    # Verifica diretamente que o registro da barra distante manteve triangulos em x in [195.5, 196.5]
    reg_barra = regs[idx_barra]
    kp = reg_barra["kept_prod"]
    tx0, tx1, ty0, ty1 = reg_barra["tx0"], reg_barra["tx1"], reg_barra["ty0"], reg_barra["ty1"]
    toca_ocl = (tx0[kp] <= 196.5) & (tx1[kp] >= 195.5) & (ty0[kp] <= 195.2) & (ty1[kp] >= 194.8)
    assert int(toca_ocl.sum()) >= 2, "triangulos do oclusor distante nao permaneceram em kept_prod"


@pytest.mark.parametrize("lado", ["-x", "+x", "-y", "+y"])
def test_propriedade_oclusor_tangente_quatro_lados_nao_some(lado):
    """Oclusor tangente na borda exata da aresta (nos 4 lados) nunca e descartado e oclui a aresta."""
    # Peca ancora longe para ampliar o dominio (c ~ 0.16 m)
    ancora = _caixa(0.0, 0.0, 0.0, 1.0, 1.0, 1.0)
    ancora2 = _caixa(80.0, 80.0, 0.0, 81.0, 81.0, 1.0)
    if lado == "-x":
        ocl = _caixa(39.0, 40.0, 2.0, 40.0, 42.0, 2.2)  # tx1 == 40.0 == px0
        bar = _quad_vertical(40.0, 40.2, 40.0, 41.8, 0.0, 1.0)
    elif lado == "+x":
        ocl = _caixa(40.0, 40.0, 2.0, 41.0, 42.0, 2.2)  # tx0 == 40.0 == px1
        bar = _quad_vertical(40.0, 40.2, 40.0, 41.8, 0.0, 1.0)
    elif lado == "-y":
        ocl = _caixa(40.0, 39.0, 2.0, 42.0, 40.0, 2.2)  # ty1 == 40.0 == py0
        bar = _quad_vertical(40.2, 40.0, 41.8, 40.0, 0.0, 1.0)
    else:
        ocl = _caixa(40.0, 40.0, 2.0, 42.0, 41.0, 2.2)  # ty0 == 40.0 == py1
        bar = _quad_vertical(40.2, 40.0, 41.8, 40.0, 0.0, 1.0)
    pecas = [ancora, ancora2, ocl, bar]
    ref = _linhas_visiveis_multi_ref(pecas, trabalhadores=1)
    obt, _ = _executar_e_validar_propriedade(pecas, ctx=f"tangente_{lado}")
    _assert_bit_a_bit(obt, ref, ordem_exata=True, ctx=f"tangente_{lado}")
    assert len(obt[3]) == 0, f"barra tangente no lado {lado} deveria estar totalmente ocluida"


def test_propriedade_triangulo_gigante_vertices_longe_nao_some():
    """Triangulo gigante com todos os vertices > 50 m longe da peca continua ocluindo a peca."""
    tri = _triangulo_unico([0.0, 0.0, 3.0], [160.0, 0.0, 3.0], [80.0, 160.0, 3.0])
    alvo = _caixa(79.5, 59.5, 0.0, 80.5, 60.5, 1.0)
    pecas = [tri, alvo]
    ref = _linhas_visiveis_multi_ref(pecas, trabalhadores=1)
    obt, _ = _executar_e_validar_propriedade(pecas, ctx="gigante_vertices_longe")
    _assert_bit_a_bit(obt, ref, ordem_exata=True, ctx="gigante_vertices_longe")
    assert len(obt[1]) == 0, "peca totalmente sob triangulo gigante deveria ficar escondida"


# ---------------------------------------------------------------------------
# (3) Capturas reais (skipif ausente) e ganho de tempo >= 15%
# ---------------------------------------------------------------------------

def _carregar_captura(caminho_pkl: str) -> tuple[list[tuple[np.ndarray, np.ndarray]], float]:
    with open(caminho_pkl, "rb") as fh:
        pecas, meta = pickle.load(fh)
    ang = float(meta.get("angulo_graus", 0.001)) if isinstance(meta, dict) else 0.001
    return pecas, ang


@pytest.mark.parametrize(
    "nome,caminho_pkl",
    [
        pytest.param(
            nome,
            os.path.join(_DIR_DIST, f"{nome}.pkl"),
            marks=pytest.mark.skipif(
                not os.path.exists(os.path.join(_DIR_DIST, f"{nome}.pkl")),
                reason=f"captura real ausente: {os.path.join(_DIR_DIST, f'{nome}.pkl')}",
            ),
            id=nome,
        )
        for nome in ("bib_2", "bib_4", "c2x3_0", "cas_9")
    ],
)
def test_captura_real_hash_polilinhas_igual(nome, caminho_pkl):
    """Capturas reais menores (/tmp/t24e/dist/*.pkl): hash SHA-256 e bits identicos a referencia."""
    pecas, ang = _carregar_captura(caminho_pkl)
    ref = _linhas_visiveis_multi_ref(pecas, angulo_graus=ang, trabalhadores=None)
    obt = linhas_visiveis_multi(pecas, angulo_graus=ang, trabalhadores=None)
    assert _sha_polilinhas(obt) == _sha_polilinhas(ref), f"SHA-256 difere na captura real {nome}"
    _assert_bit_a_bit(obt, ref, ctx=f"captura_{nome}")


def _cena_benchmark_cull_muitas_pecas() -> list[tuple[np.ndarray, np.ndarray]]:
    """Terreno plano de 80k tris (so contorno) + 500 caixas pequenas espalhadas em 80x80 m."""
    terr = _terreno_plano(200, 200, 0.4, z0=0.0)  # 80.000 triangulos
    rng = np.random.default_rng(240_777)
    caixas = []
    for _ in range(500):
        x = float(rng.uniform(1.0, 78.0))
        y = float(rng.uniform(1.0, 78.0))
        caixas.append(_caixa(x, y, 0.25, x + 0.4, y + 0.4, 0.85))
    return [terr, *caixas]
