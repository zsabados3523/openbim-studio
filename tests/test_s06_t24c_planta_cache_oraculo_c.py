# SPDX-License-Identifier: AGPL-3.0-or-later
"""Parte 3 de test_s06_t24c_planta_cache_oraculo.py (divisao mecanica em PRs de ate 400 linhas). Auxiliares e fixtures vem das partes anteriores."""
from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace
import ifcopenshell
import ifcopenshell.api
import numpy as np
import pytest
from obim_geometria import aneis, construtor, corte_plano, desenho, recorte, visibilidade
from openbim_app.desenho import estilo
from test_s06_t24c_planta_cache_oraculo import _caixa_np, _cobertura_bidirecional, _contagem_segmentos_corte, _dist_pontos_a_segs, _extrair_polilinhas_d, _mod, _montar_cena_numpy, _parse_svg, _polilinhas_de_elementos, _polilinhas_para_segs, _telhado_dobra_np  # noqa: F401
from test_s06_t24c_planta_cache_oraculo_b import _criar_cena_ifc_sintetica  # noqa: F401



def test_mutante_03_falta_oclusao_mutua_entre_pecas():
    """Mutante 3: chamar linhas_visiveis por peca sem oclusao mutua deixaria bloco escondido vazar."""
    pc = _mod()
    f, pedido, malhas, ev = _montar_cena_numpy(
        [
            (10, "G_TAMPO", "IfcSlab", _caixa_np(0.0, 0.0, 0.6, 3.0, 3.0, 0.8)),
            (11, "G_OCULTO", "IfcFurnishingElement", _caixa_np(1.0, 1.0, 0.0, 2.0, 2.0, 0.4)),
        ],
        altura_corte_m=1.2,
    )
    resp, motivo = pc.desenhar_planta_cache(f, pedido, malhas, ev)
    assert motivo is None and resp["ok"] is True

    parsed = _parse_svg(resp["svg"])
    segs_proj = _polilinhas_para_segs(_polilinhas_de_elementos(parsed.proj_groups))
    assert len(segs_proj) >= 4
    # Arestas do bloco oculto (x=1..2, y=1..2) estao 100% sob o tampo (0..3, 0..3): 0 linhas perto
    pts_ocultos = np.array([[1.0, 1.5], [2.0, 1.5], [1.5, 1.0], [1.5, 2.0]], dtype=np.float64)
    assert float(_dist_pontos_a_segs(pts_ocultos, segs_proj).min()) > 0.2
    # Borda do tampo (0..3, 0..3) visivel
    pts_tampo = np.array([[0.0, 1.5], [3.0, 1.5], [1.5, 0.0], [1.5, 3.0]], dtype=np.float64)
    assert float(_dist_pontos_a_segs(pts_tampo, segs_proj).max()) <= 1e-3


def test_mutante_04_falta_tampa_vazamento_dentro_da_secao_cortada():
    """Mutante 4: sem recorte 2D pelos aneis da secao, aresta de piso abaixo atravessa a parede cortada."""
    pc = _mod()
    f, pedido, malhas, ev = _montar_cena_numpy(
        [
            (10, "G_PAREDE", "IfcWall", _caixa_np(0.0, 1.0, 0.0, 4.0, 1.4, 2.8)),
            (11, "G_BARRA_PISO", "IfcSlab", _caixa_np(1.5, 0.0, 0.0, 2.5, 2.4, 0.2)),
        ],
        altura_corte_m=1.2,
    )
    resp, motivo = pc.desenhar_planta_cache(f, pedido, malhas, ev)
    assert motivo is None and resp["ok"] is True

    parsed = _parse_svg(resp["svg"])
    segs_proj = _polilinhas_para_segs(_polilinhas_de_elementos(parsed.proj_groups))
    # Interior da secao da parede (y=1.2, 20 cm longe das bordas y=1.0 e y=1.4): ZERO segmentos de projecao
    pts_dentro = np.array([[1.5, 1.2], [2.5, 1.2], [2.0, 1.2]], dtype=np.float64)
    assert float(_dist_pontos_a_segs(pts_dentro, segs_proj).min()) > 0.05
    # Trechos da barra fora da parede (y=0.5 e y=1.9) permanecem visiveis
    pts_fora = np.array([[1.5, 0.5], [2.5, 0.5], [1.5, 1.9], [2.5, 1.9]], dtype=np.float64)
    assert float(_dist_pontos_a_segs(pts_fora, segs_proj).max()) <= 1e-3


def test_mutante_05_angulo_dobra_diferente_de_0001():
    """Mutante 5: usar filtro de dobra estilo Revit (ex. 15/30 graus) apagaria cumeeira de 2 graus."""
    pc = _mod()
    f, pedido, malhas, ev = _montar_cena_numpy(
        [(10, "G_TELHADO", "IfcRoof", _telhado_dobra_np(0.0, 0.0, 2.0, 1.0, 0.0, 0.5, angulo_diedro_graus=2.0))],
        altura_corte_m=1.2,
    )
    resp, motivo = pc.desenhar_planta_cache(f, pedido, malhas, ev)
    assert motivo is None and resp["ok"] is True

    parsed = _parse_svg(resp["svg"])
    segs_proj = _polilinhas_para_segs(_polilinhas_de_elementos(parsed.proj_groups))
    # Cumeeira central em x=1.0, y in [0.1..0.9] deve estar presente
    pts_cumeeira = np.column_stack([np.full(9, 1.0), np.linspace(0.1, 0.9, 9)])
    assert float(_dist_pontos_a_segs(pts_cumeeira, segs_proj).max()) <= 1e-3


def test_mutante_06_y_nao_invertido_ou_projecao_como_cut():
    """Mutante 6: nao inverter Y ou colocar projecao em `<g ifc:guid>` quebra estilo/coordenadas."""
    pc = _mod()
    # Coordenadas assimetricas em Y (+3.0 .. +4.0) para provar que SVG tem Y negativo (-4.0 .. -3.0)
    f, pedido, malhas, ev = _montar_cena_numpy(
        [
            (10, "G_PAREDE", "IfcWall", _caixa_np(1.0, 3.0, 0.0, 2.0, 3.5, 2.8)),
            (11, "G_LAJE", "IfcSlab", _caixa_np(1.0, 3.0, -0.2, 2.0, 4.0, 0.0)),
        ],
        altura_corte_m=1.2,
    )
    resp, motivo = pc.desenhar_planta_cache(f, pedido, malhas, ev)
    assert motivo is None and resp["ok"] is True

    parsed = _parse_svg(resp["svg"])
    ys_svg = []
    for p in parsed.all_paths:
        cmds, runs = _extrair_polilinhas_d(p.get("d") or "")
        assert "Z" not in cmds and "z" not in cmds
        for r in runs:
            ys_svg.extend(r[:, 1].tolist())
    assert ys_svg and max(ys_svg) <= -2.999 and min(ys_svg) >= -4.001

    estilizado = estilo.aplicar_estilo(resp["svg"], "1:50")
    assert 'class="IfcWall cut"' in estilizado
    assert 'class="projection"' in estilizado and 'class="projection cut"' not in estilizado


def test_mutante_07_nao_mutacao_entradas():
    """Mutante 7: mutar `verts`, `tris` ou `pedido` do chamador durante o desenho."""
    pc = _mod()
    f, pedido, malhas, ev = _montar_cena_numpy(
        [
            (10, "G_PAREDE", "IfcWall", _caixa_np(0.0, 0.0, 0.0, 3.0, 0.2, 2.8)),
            (11, "G_LAJE", "IfcSlab", _caixa_np(0.0, 0.0, -0.2, 3.0, 2.0, 0.0)),
        ],
        altura_corte_m=1.2,
    )
    copia_malhas = {g: (v.copy(), t.copy()) for g, (v, t) in malhas.items()}
    copia_pedido = {k: (dict(v) if isinstance(v, dict) else list(v) if isinstance(v, list) else v) for k, v in pedido.items()}

    resp, motivo = pc.desenhar_planta_cache(f, pedido, malhas, ev)
    assert motivo is None and resp["ok"] is True
    for g, (v0, t0) in copia_malhas.items():
        np.testing.assert_array_equal(malhas[g][0], v0)
        np.testing.assert_array_equal(malhas[g][1], t0)
    assert pedido == copia_pedido


def test_mutante_08_peca_acima_do_corte_nao_desenhada_nem_falha():
    """Mutante 8: desenhar peca acima do corte ou registra-la em `falhas_geometria`."""
    pc = _mod()
    f, pedido, malhas, ev = _montar_cena_numpy(
        [(10, "G_VIGA_ALTA", "IfcBeam", _caixa_np(0.0, 0.0, 2.4, 4.0, 0.3, 2.8))],
        altura_corte_m=1.2,
    )
    resp, motivo = pc.desenhar_planta_cache(f, pedido, malhas, ev)
    assert motivo is None and resp["ok"] is True
    assert resp["n_paths"] == 0
    assert resp["falhas_geometria"] == []
    assert "G_VIGA_ALTA" not in resp["svg"]
    parsed = _parse_svg(resp["svg"])
    assert len(parsed.all_paths) == 0


@pytest.mark.parametrize("offset", [(0.0, 0.0), (500_000.25, 7_500_000.75)])
def test_mutante_09_equivalencia_motor_casos_simples_e_georreferenciado(tmp_path, offset):
    """Mutante 9: divergencia geometrica (escala/matriz/eixo/float64) contra o motor nos casos simples."""
    _mod()
    cena = _criar_cena_ifc_sintetica(tmp_path, offset=offset)

    resp_motor = desenho.processar(cena.pedido_base)
    resp_cache = desenho.processar(cena.pedido_cache)

    assert resp_motor["ok"] is True
    assert resp_cache["ok"] is True
    assert resp_cache["via_cache"] is True
    assert resp_cache["queda"] is None
    assert resp_cache["n_faltantes"] == 0

    p_ref = _parse_svg(resp_motor["svg"])
    p_new = _parse_svg(resp_cache["svg"])

    # Mesmos ifc:guid de secao cortada e mesma contagem canonica de segmentos de corte
    assert set(p_new.cut_by_guid.keys()) == set(p_ref.cut_by_guid.keys()) == {cena.parede.GlobalId}
    pls_corte_ref = _polilinhas_de_elementos(p_ref.cut_by_guid[cena.parede.GlobalId])
    pls_corte_new = _polilinhas_de_elementos(p_new.cut_by_guid[cena.parede.GlobalId])
    assert _contagem_segmentos_corte(pls_corte_new) == _contagem_segmentos_corte(pls_corte_ref) == 4

    # Cobertura bidirecional >= 99.5% na secao e >= 98.0% no conjunto (5 mm reais)
    segs_corte_ref = _polilinhas_para_segs(pls_corte_ref)
    segs_corte_new = _polilinhas_para_segs(pls_corte_new)
    rec_c, pre_c = _cobertura_bidirecional(segs_corte_ref, segs_corte_new, tol=5e-3)
    assert rec_c >= 0.995 and pre_c >= 0.995, f"secao recall={rec_c:.4f} precisao={pre_c:.4f}"

    segs_all_ref = _polilinhas_para_segs(pls_corte_ref + _polilinhas_de_elementos(p_ref.proj_groups))
    segs_all_new = _polilinhas_para_segs(pls_corte_new + _polilinhas_de_elementos(p_new.proj_groups))
    rec_g, pre_g = _cobertura_bidirecional(segs_all_ref, segs_all_new, tol=5e-3)
    assert rec_g >= 0.98 and pre_g >= 0.98, f"geral recall={rec_g:.4f} precisao={pre_g:.4f}"

    # Ambos os SVGs validos no estilo
    estilo.aplicar_estilo(resp_cache["svg"], "1:50")


def test_mutante_10_pesados_caixas_vazios_e_tempos():
    """Mutante 10: preencher `pesados`/`caixas`/`faltantes` ou omitir tempos obrigatorios."""
    pc = _mod()
    f, pedido, malhas, ev = _montar_cena_numpy(
        [
            (10, "G_PAREDE", "IfcWall", _caixa_np(0.0, 0.0, 0.0, 4.0, 0.2, 2.8)),
            (11, "G_LAJE", "IfcSlab", _caixa_np(0.0, 0.0, -0.2, 4.0, 3.0, 0.0)),
        ],
        altura_corte_m=1.2,
    )
    resp, motivo = pc.desenhar_planta_cache(f, pedido, malhas, ev, abrir_s=0.05, cache_s=0.03)
    assert motivo is None and resp["ok"] is True
    assert resp["pesados"] == []
    assert resp["caixas"] == []
    assert resp["em_cache"] == []
    assert resp["falhas_geometria"] == []
    assert "faltantes" not in resp and "incompleta" not in resp

    t = resp["tempos"]
    assert t["abrir_s"] == pytest.approx(0.05)
    assert t["cache_s"] == pytest.approx(0.03)
    assert t["geo_s"] == 0.0 and t["write_s"] == 0.0 and t["finalize_s"] == 0.0
    assert isinstance(t["corte_s"], float) and t["corte_s"] >= 0.0
    assert isinstance(t["motor_s"], float) and t["motor_s"] >= 0.0


def test_erro_inesperado_no_motor_retorna_erro_motor(monkeypatch):
    pc = _mod()
    monkeypatch.setattr(
        visibilidade,
        "linhas_visiveis_multi",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("falha simulada")),
    )
    f, pedido, malhas, ev = _montar_cena_numpy(
        [(10, "G_LAJE", "IfcSlab", _caixa_np(0.0, 0.0, -0.2, 4.0, 3.0, 0.0))],
        altura_corte_m=1.2,
    )
    resp, motivo = pc.desenhar_planta_cache(f, pedido, malhas, ev)
    assert resp is None and motivo == "erro_motor"


# ---------- integracao com desenho._desenhar_planta_cache e telemetria via_cache ----------
def test_integracao_gancho_desenho_e_telemetria_via_cache(tmp_path):
    _mod()
    cena = _criar_cena_ifc_sintetica(tmp_path)

    # 1) Chamada direta ao gancho desenho._desenhar_planta_cache (nao pode ser stub erro_motor)
    f_np, ped_np, mal_np, ev_np = _montar_cena_numpy(
        [
            (10, "G_PAREDE", "IfcWall", _caixa_np(0.0, 0.0, 0.0, 4.0, 0.2, 2.8)),
            (11, "G_LAJE", "IfcSlab", _caixa_np(0.0, 0.0, -0.2, 4.0, 3.0, 0.0)),
        ],
        altura_corte_m=1.2,
    )
    r_gancho, mot_gancho = desenho._desenhar_planta_cache(f_np, ped_np, mal_np, ev_np, None, 0.01)
    assert mot_gancho is None and isinstance(r_gancho, dict) and r_gancho["ok"] is True

    # 2) Fluxo completo desenho.processar com cache real -> via_cache=True e telemetria
    resp = desenho.processar(cena.pedido_cache)
    assert resp["ok"] is True
    assert resp["via_cache"] is True
    assert resp["queda"] is None
    assert resp["n_faltantes"] == 0
    assert resp["pesados"] == [] and resp["caixas"] == [] and resp["falhas_geometria"] == []
    assert "faltantes" not in resp and "incompleta" not in resp
    t = resp["tempos"]
    assert isinstance(t["cache_s"], float) and t["cache_s"] >= 0.0
    assert isinstance(t["corte_s"], float) and t["corte_s"] >= 0.0
    assert isinstance(t["motor_s"], float) and t["motor_s"] >= 0.0
    assert t["geo_s"] == 0.0 and t["write_s"] == 0.0 and t["finalize_s"] == 0.0


def test_integracao_desenho_quedas_secao_aberta_e_malha_invalida(tmp_path, monkeypatch):
    _mod()
    cena = _criar_cena_ifc_sintetica(tmp_path)
    base = desenho.processar(cena.pedido_base)
    assert base["ok"] is True

    real_ler = desenho.cache_leitura.malhas_do_cache

    # 1) Injeta malha cortada com segmentos sem anel/cadeia (T24s: corte vazio nao derruba) -> cai secao_aberta
    def ler_secao_aberta(cache, doc, ids):
        malhas, falt = real_ler(cache, doc, ids)
        malhas[cena.parede.GlobalId] = _caixa_np(0.0, 0.0, 0.0, 2e-7, 2e-7, 2.8)
        return malhas, falt

    monkeypatch.setattr(desenho.cache_leitura, "malhas_do_cache", ler_secao_aberta)
    r_ab = desenho.processar(cena.pedido_cache)
    assert r_ab["ok"] is True
    assert r_ab["via_cache"] is False
    assert r_ab["queda"] == "secao_aberta"
    assert r_ab["n_faltantes"] == 0
    assert r_ab["svg"] == base["svg"]

    # 2) Injeta malha invalida (NaN) na laje -> cai pavimento inteiro com queda="malha_invalida"
    def ler_malha_invalida(cache, doc, ids):
        malhas, falt = real_ler(cache, doc, ids)
        v_ru, t_ru = malhas[cena.laje.GlobalId]
        v_nan = v_ru.copy()
        v_nan[0, 0] = np.nan
        malhas[cena.laje.GlobalId] = (v_nan, t_ru)
        return malhas, falt

    monkeypatch.setattr(desenho.cache_leitura, "malhas_do_cache", ler_malha_invalida)
    r_inv = desenho.processar(cena.pedido_cache)
    assert r_inv["ok"] is True
    assert r_inv["via_cache"] is False
    assert r_inv["queda"] == "malha_invalida"
    assert r_inv["n_faltantes"] == 0
    assert r_inv["svg"] == base["svg"]
