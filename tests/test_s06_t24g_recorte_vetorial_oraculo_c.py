# SPDX-License-Identifier: AGPL-3.0-or-later
"""Parte 3 de test_s06_t24g_recorte_vetorial_oraculo.py (divisao mecanica em PRs de ate 400 linhas). Auxiliares e fixtures vem das partes anteriores."""
from __future__ import annotations

from collections import namedtuple
import gc
import math
import statistics
import time
import tracemalloc
import numpy as np
import pytest
from obim_geometria.recorte import recortar_fora_dos_aneis
from test_s06_t24g_recorte_vetorial_oraculo import _TOL, _assert_trechos_exatos, _poligono_estrelado, _rect, _referencia_recortar  # noqa: F401
from test_s06_t24g_recorte_vetorial_oraculo_b import _gerar_cena_grande, _gerar_polilinha_aleatoria  # noqa: F401



# ==============================================================================
# (3) TESTES ATOMICOS DE DESEMPENHO RELATIVO (MESMO PROCESSO)
# ==============================================================================


def _medir_relativo(pols, grupos, encolher: float, rodadas: int = 3) -> tuple[float, float, int, int]:
    """Mede mediana de `rodadas` intercaladas (mesmo processo, time.perf_counter)."""
    t_refs: list[float] = []
    t_novos: list[float] = []
    n_ref = 0
    n_novo = 0
    for r in range(rodadas):
        # Alterna a ordem em cada rodada para cancelar vies de aquecimento/cache/CI
        ordem = ("ref", "novo") if r % 2 == 0 else ("novo", "ref")
        for qual in ordem:
            gc.collect()
            t0 = time.perf_counter()
            if qual == "ref":
                out_r = _referencia_recortar(pols, grupos, encolher=encolher)
                t_refs.append(time.perf_counter() - t0)
                n_ref = len(out_r)
            else:
                out_n = recortar_fora_dos_aneis(pols, grupos, encolher=encolher)
                t_novos.append(time.perf_counter() - t0)
                n_novo = len(out_n)
    return statistics.median(t_refs), statistics.median(t_novos), n_ref, n_novo


def test_desempenho_relativo_cena_grande_encolher_padrao():
    """Versao nova deve levar no maximo 40% do tempo da referencia (encolher=5e-4)."""
    pols, grupos = _gerar_cena_grande()
    med_ref, med_novo, n_ref, n_novo = _medir_relativo(pols, grupos, encolher=5e-4, rodadas=3)
    assert n_novo == n_ref, f"qtd trechos divergente no benchmark: {n_novo} != {n_ref}"
    razao = med_novo / med_ref
    assert med_novo <= 0.40 * med_ref, (
        f"lento demais (encolher=5e-4): novo={med_novo:.4f}s vs ref={med_ref:.4f}s "
        f"({100.0 * razao:.1f}% > 40.0%)"
    )


def test_desempenho_relativo_cena_grande_encolher_zero():
    """Versao nova deve levar no maximo 40% do tempo da referencia (encolher=0.0)."""
    pols, grupos = _gerar_cena_grande()
    med_ref, med_novo, n_ref, n_novo = _medir_relativo(pols, grupos, encolher=0.0, rodadas=3)
    assert n_novo == n_ref, f"qtd trechos divergente no benchmark: {n_novo} != {n_ref}"
    razao = med_novo / med_ref
    assert med_novo <= 0.40 * med_ref, (
        f"lento demais (encolher=0.0): novo={med_novo:.4f}s vs ref={med_ref:.4f}s "
        f"({100.0 * razao:.1f}% > 40.0%)"
    )


# ==============================================================================
# (4) NAO MUTAR ENTRADAS, DETERMINISMO E USO DE MEMORIA LIMITADO
# ==============================================================================


def test_nao_muta_entradas_nem_compartilha_memoria():
    """Nao muta polilinhas nem aneis (plano e grupos), e saida nao compartilha buffer."""
    pols = [
        np.array([(-2.0, 5.0), (8.0, 5.0)], dtype=float),              # toda fora
        np.array([(-1.0, 1.0), (2.0, 1.0), (2.0, 3.0), (6.0, 3.0)], dtype=float),  # cortada
        np.array([(1.0, 1.0), (3.0, 1.0)], dtype=float),               # toda dentro
    ]
    grupos = [[_rect(0.0, 0.0, 4.0, 2.0)], [_rect(3.0, 0.0, 5.0, 4.0)]]
    plano = [_rect(0.0, 0.0, 4.0, 2.0)]

    pols_snap = [p.copy() for p in pols]
    grupos_snap = [[a.copy() for a in g] for g in grupos]
    plano_snap = [a.copy() for a in plano]

    res_g = recortar_fora_dos_aneis(pols, grupos, encolher=5e-4)
    res_p = recortar_fora_dos_aneis(pols, plano, encolher=0.0)

    for orig, snap in zip(pols, pols_snap):
        np.testing.assert_array_equal(orig, snap)
    for g_orig, g_snap in zip(grupos, grupos_snap):
        assert len(g_orig) == len(g_snap)
        for a_orig, a_snap in zip(g_orig, g_snap):
            np.testing.assert_array_equal(a_orig, a_snap)
    for a_orig, a_snap in zip(plano, plano_snap):
        np.testing.assert_array_equal(a_orig, a_snap)

    # Mutar a saida nao pode afetar a entrada
    for arr in res_g + res_p:
        arr[:] = -999.0
    for orig, snap in zip(pols, pols_snap):
        np.testing.assert_array_equal(orig, snap)

    # Mutar a entrada apos a chamada nao pode afetar a saida
    pol_mut = np.array([(-3.0, 8.0), (7.0, 8.0)], dtype=float)
    res_mut = recortar_fora_dos_aneis([pol_mut], plano, encolher=5e-4)
    pol_mut[:] = 0.0
    np.testing.assert_allclose(res_mut[0], [(-3.0, 8.0), (7.0, 8.0)], rtol=0.0, atol=_TOL)


def test_determinismo_chamadas_repetidas():
    """Chamadas repetidas produzem saida identica bit a bit."""
    rng = np.random.default_rng(8008)
    grupos = [
        [_rect(0.0, 0.0, 10.0, 10.0), _rect(2.5, 2.5, 7.5, 7.5, horario=True)],
        [_poligono_estrelado(rng, 8.0, 6.0, 1.5, 4.0, 9)],
    ]
    pols = [_gerar_polilinha_aleatoria(rng, 25, (-2.0, 14.0), (-2.0, 12.0)) for _ in range(30)]

    for encolher in (5e-4, 0.0):
        r1 = recortar_fora_dos_aneis(pols, grupos, encolher=encolher)
        r2 = recortar_fora_dos_aneis(pols, grupos, encolher=encolher)
        r3 = recortar_fora_dos_aneis(pols, grupos, encolher=encolher)
        assert len(r1) == len(r2) == len(r3) > 0
        for a, b, c in zip(r1, r2, r3):
            np.testing.assert_array_equal(a, b)
            np.testing.assert_array_equal(a, c)


def test_uso_memoria_limitado_cena_grande():
    """Pico de memoria alocada na cena grande deve ficar abaixo de 300 MiB."""
    pols, grupos = _gerar_cena_grande()
    limite_bytes = 300 * 1024 * 1024
    gc.collect()
    tracemalloc.start()
    try:
        tracemalloc.reset_peak()
        res = recortar_fora_dos_aneis(pols, grupos, encolher=5e-4)
        _, pico = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    assert len(res) > 100
    assert pico < limite_bytes, f"pico de memoria {pico / (1024 * 1024):.1f} MiB >= 300.0 MiB"


# ==============================================================================
# (5) MUTANTES: UM TESTE POR COMPORTAMENTO ERRADO PLAUSIVEL
# ==============================================================================


def test_mutante_perder_trecho_na_fronteira():
    """Mutante: descartar trecho colinear com a borda ou apenas tocando a fronteira."""
    ret = [_rect(0.0, 0.0, 4.0, 2.0)]
    for encolher in (0.0, 5e-4):
        # Colinear atravessando a borda inferior inteira
        res1 = recortar_fora_dos_aneis([np.array([(-1.0, 0.0), (5.0, 0.0)])], ret, encolher=encolher)
        _assert_trechos_exatos(res1, [[(-1.0, 0.0), (5.0, 0.0)]], msg=f"borda_estendida e={encolher}")

        # Inteiramente contida sobre a aresta da fronteira
        res2 = recortar_fora_dos_aneis([np.array([(1.0, 0.0), (3.0, 0.0)])], ret, encolher=encolher)
        _assert_trechos_exatos(res2, [[(1.0, 0.0), (3.0, 0.0)]], msg=f"borda_interna e={encolher}")

        # Apenas encosta no ponto (0, 1) da fronteira e volta para fora
        res3 = recortar_fora_dos_aneis([np.array([(-1.0, 1.0), (0.0, 1.0), (-1.0, 2.0)])], ret, encolher=encolher)
        _assert_trechos_exatos(res3, [[(-1.0, 1.0), (0.0, 1.0), (-1.0, 2.0)]], msg=f"toca_borda e={encolher}")


def test_mutante_juntar_trechos_que_nao_deveriam():
    """Mutante: fundir trechos separados por corte em uma unica polilinha."""
    ret = [_rect(0.0, 0.0, 4.0, 2.0)]

    # 1) Unico segmento atravessando o retangulo: devem sair 2 trechos separados
    res1 = recortar_fora_dos_aneis([np.array([(-1.0, 1.0), (5.0, 1.0)])], ret, encolher=0.0)
    _assert_trechos_exatos(res1, [[(-1.0, 1.0), (0.0, 1.0)], [(4.0, 1.0), (5.0, 1.0)]], msg="corte_simples")

    # 2) Polilinha de 4 pontos com segmento intermediario todo removido
    res2 = recortar_fora_dos_aneis(
        [np.array([(-1.0, 1.0), (0.0, 1.0), (4.0, 1.0), (5.0, 1.0)])], ret, encolher=0.0
    )
    _assert_trechos_exatos(res2, [[(-1.0, 1.0), (0.0, 1.0)], [(4.0, 1.0), (5.0, 1.0)]], msg="meio_removido")

    # 3) Dois retangulos separados por fenda estreita de 1 cm: 3 trechos distintos
    dois_rets = [[_rect(0.0, 0.0, 2.0, 2.0)], [_rect(2.01, 0.0, 4.0, 2.0)]]
    res3 = recortar_fora_dos_aneis([np.array([(-1.0, 1.0), (5.0, 1.0)])], dois_rets, encolher=0.0)
    _assert_trechos_exatos(
        res3,
        [[(-1.0, 1.0), (0.0, 1.0)], [(2.0, 1.0), (2.01, 1.0)], [(4.0, 1.0), (5.0, 1.0)]],
        msg="fenda_estreita",
    )


def test_mutante_inverter_par_impar():
    """Mutante: inverter par-impar dentro de um grupo ou confundir uniao entre grupos com par-impar."""
    # Externo + furo: so o furo permanece
    ext_furo = [_rect(0.0, 0.0, 10.0, 10.0), _rect(3.0, 3.0, 7.0, 7.0, horario=True)]
    res_furo = recortar_fora_dos_aneis([np.array([(1.0, 5.0), (9.0, 5.0)])], ext_furo, encolher=0.0)
    _assert_trechos_exatos(res_furo, [[(3.0, 5.0), (7.0, 5.0)]], msg="furo_mantido")

    # Externo + furo + ilha: 3 niveis de paridade
    tres_niveis = [
        _rect(0.0, 0.0, 10.0, 10.0),
        _rect(2.0, 2.0, 8.0, 8.0, horario=True),
        _rect(4.0, 4.0, 6.0, 6.0),
    ]
    res_3 = recortar_fora_dos_aneis([np.array([(-1.0, 5.0), (11.0, 5.0)])], tres_niveis, encolher=0.0)
    _assert_trechos_exatos(
        res_3,
        [[(-1.0, 5.0), (0.0, 5.0)], [(2.0, 5.0), (4.0, 5.0)], [(6.0, 5.0), (8.0, 5.0)], [(10.0, 5.0), (11.0, 5.0)]],
        msg="ilha_no_furo",
    )

    # Sobreposicao: plano (par-impar mantem miolo) vs grupos (uniao remove miolo)
    a = _rect(0.0, 0.0, 5.0, 2.0)
    b = _rect(3.0, 0.0, 8.0, 2.0)
    lin = [np.array([(-1.0, 1.0), (9.0, 1.0)])]
    res_plano = recortar_fora_dos_aneis(lin, [a, b], encolher=0.0)
    _assert_trechos_exatos(
        res_plano,
        [[(-1.0, 1.0), (0.0, 1.0)], [(3.0, 1.0), (5.0, 1.0)], [(8.0, 1.0), (9.0, 1.0)]],
        msg="sobreposicao_plano_par_impar",
    )
    res_grupos = recortar_fora_dos_aneis(lin, [[a], [b]], encolher=0.0)
    _assert_trechos_exatos(
        res_grupos,
        [[(-1.0, 1.0), (0.0, 1.0)], [(8.0, 1.0), (9.0, 1.0)]],
        msg="sobreposicao_grupos_uniao",
    )


def test_mutante_ignorar_encolher():
    """Mutante: ignorar `encolher` em aresta externa, furo ou arco de vertice reentrante."""
    ret = [_rect(0.0, 0.0, 4.0, 2.0)]
    lin = [np.array([(-1.0, 1.0), (5.0, 1.0)])]

    # Aresta externa recuada em encolher=1e-2 e padrao 5e-4
    _assert_trechos_exatos(
        recortar_fora_dos_aneis(lin, ret, encolher=1e-2),
        [[(-1.0, 1.0), (0.01, 1.0)], [(3.99, 1.0), (5.0, 1.0)]],
        msg="encolher_1e2",
    )
    _assert_trechos_exatos(
        recortar_fora_dos_aneis(lin, ret),
        [[(-1.0, 1.0), (5e-4, 1.0)], [(4.0 - 5e-4, 1.0), (5.0, 1.0)]],
        msg="encolher_padrao",
    )

    # Furo cresce `encolher` para dentro do material
    ext_furo = [_rect(0.0, 0.0, 10.0, 10.0), _rect(4.0, 4.0, 6.0, 6.0, horario=True)]
    _assert_trechos_exatos(
        recortar_fora_dos_aneis([np.array([(1.0, 5.0), (9.0, 5.0)])], ext_furo, encolher=1e-2),
        [[(3.99, 5.0), (6.01, 5.0)]],
        msg="furo_cresce_encolher",
    )

    # Vertice reentrante do L (1, 1): corte no arco de raio 5e-4 em y = 1 - 3e-4 -> x = 1 - 4e-4
    forma_l = [np.array([(0, 0), (2, 0), (2, 1), (1, 1), (1, 2), (0, 2)], dtype=float)]
    _assert_trechos_exatos(
        recortar_fora_dos_aneis([np.array([(0.5, 1.0 - 3e-4), (1.5, 1.0 - 3e-4)])], forma_l, encolher=5e-4),
        [[(1.0 - 4e-4, 1.0 - 3e-4), (1.5, 1.0 - 3e-4)]],
        msg="arco_vertice_reentrante",
    )


def test_mutante_descartar_polilinha_de_2_pontos():
    """Mutante: descartar polilinhas de exatamente 2 pontos por off-by-one."""
    ret = [_rect(0.0, 0.0, 4.0, 2.0)]
    pols = [
        np.array([(-2.0, 5.0), (6.0, 5.0)], dtype=float),              # 2 pts toda fora
        np.array([(-1.0, 1.0), (2.0, 1.0)], dtype=float),              # 2 pts metade fora
        np.array([(-1.0, 1.5), (5.0, 1.5)], dtype=float),              # 2 pts atravessa -> 2 trechos de 2 pts
        np.array([(10.0, 10.0), (10.0 + 1e-8, 10.0)], dtype=float),    # 2 pts curta (> _EPS) fora
    ]
    res = recortar_fora_dos_aneis(pols, ret, encolher=0.0)
    _assert_trechos_exatos(
        res,
        [
            [(-2.0, 5.0), (6.0, 5.0)],
            [(-1.0, 1.0), (0.0, 1.0)],
            [(-1.0, 1.5), (0.0, 1.5)],
            [(4.0, 1.5), (5.0, 1.5)],
            [(10.0, 10.0), (10.0 + 1e-8, 10.0)],
        ],
        msg="polilinhas_2_pontos",
    )
