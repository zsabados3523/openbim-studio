# SPDX-License-Identifier: AGPL-3.0-or-later
"""Parte 3 de test_s06_t24f_secao_tolerante_oraculo.py (divisao mecanica em PRs de ate 400 linhas). Auxiliares e fixtures vem das partes anteriores."""
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
from test_s06_t24f_secao_tolerante_oraculo import _caixa_100_aberta_np, _caixa_com_aneis_z_np, _caixa_np, _caixas_fundidas_em_t_np, _extrair_polilinhas_d, _montar_cena_numpy, _parse_svg  # noqa: F401
from test_s06_t24f_secao_tolerante_oraculo_b import _criar_cena_ifc_4_paredes, _dist_pontos_a_segs, _eh_fechada, _polilinhas_mundo, _polilinhas_para_segs  # noqa: F401



# ==========================================================================
# REGRA 2 E 4: ANEIS ABERTOS (MISTOS E 100% ABERTOS), TAMPA E NAO-OMISSAO
# ==========================================================================
def test_regra2_secao_mista_fechados_e_abertos_nao_manifold_tampa_e_telemetria(monkeypatch):
    """Duas caixas fundidas em T (1 fechado + 1 aberto): fechado tampa, aberto desenha M/L sem Z e nao tampa."""
    recorte_args: list[list] = []
    real_recorte = recorte.recortar_fora_dos_aneis

    def espia_recorte(pols, grupos, *a, **k):
        recorte_args.append(list(grupos))
        return real_recorte(pols, grupos, *a, **k)

    monkeypatch.setattr(recorte, "recortar_fora_dos_aneis", espia_recorte)

    # Barra de piso em x in [0.95, 1.05], y in [-0.5, 2.5]:
    # - cruza interior do anel fechado [0..2, 0..0.4] em y=0.2 (DEVE ser tampada)
    # - cruza interior do ramo aberto [0.8..1.2, 0.4..2.0] em y=1.2 (NAO pode ser tampada)
    f, pedido, malhas, ev = _montar_cena_numpy(
        [
            (10, "G_PAREDE_T", "IfcWall", _caixas_fundidas_em_t_np(0.0, 0.0, 0.0, 2.8)),
            (11, "G_BARRA_PISO", "IfcSlab", _caixa_np(0.95, -0.5, 0.0, 1.05, 2.5, 0.2)),
            (12, "G_PAREDE_B1", "IfcWall", _caixa_np(5.0, 0.0, 0.0, 7.0, 0.3, 2.8)),
            (13, "G_PAREDE_B2", "IfcWall", _caixa_np(5.0, 2.0, 0.0, 7.0, 2.3, 2.8)),
            (14, "G_PAREDE_B3", "IfcWall", _caixa_np(5.0, 4.0, 0.0, 7.0, 4.3, 2.8)),
        ],
        altura_corte_m=1.2,
    )
    resp, motivo = planta_cache.desenhar_planta_cache(f, pedido, malhas, ev, abrir_s=0.02, cache_s=0.03)
    assert motivo is None and resp is not None and resp["ok"] is True
    assert resp["secoes_parciais"] == 1 and type(resp["secoes_parciais"]) is int
    assert set(resp["enviados"]) == {10, 11, 12, 13, 14}
    assert resp["caixas"] == [] and resp["em_cache"] == [] and resp["pesados"] == [] and resp["falhas_geometria"] == []
    assert set(resp["tempos"].keys()) == {"abrir_s", "geo_s", "write_s", "finalize_s", "cache_s", "corte_s", "motor_s"}

    svg = resp["svg"]
    assert "-0.000000" not in svg
    parsed = _parse_svg(svg)
    assert set(parsed.cut_by_guid.keys()) == {"G_PAREDE_T", "G_PAREDE_B1", "G_PAREDE_B2", "G_PAREDE_B3"}

    # Verifica comandos exclusivamente M/L (sem Z) em todos os paths
    for p_el in parsed.all_paths:
        cmds, _ = _extrair_polilinhas_d(p_el.get("d") or "")
        assert cmds and set(cmds).issubset({"M", "L"})
        assert "Z" not in cmds and "z" not in cmds

    # G_PAREDE_T deve ter 1 subcaminho fechado e 1 subcaminho aberto (sem fechar!)
    pls_t = _polilinhas_mundo(parsed.cut_by_guid["G_PAREDE_T"])
    fechadas_t = [pl for pl in pls_t if _eh_fechada(pl)]
    abertas_t = [pl for pl in pls_t if not _eh_fechada(pl)]
    assert len(fechadas_t) == 1, f"esperado 1 anel fechado em G_PAREDE_T, obtido {len(fechadas_t)}"
    assert len(abertas_t) == 1, f"esperado 1 cadeia aberta em G_PAREDE_T, obtido {len(abertas_t)}"

    # A cadeia aberta liga (0.8, 0.4) -> (0.8, 2.0) -> (1.2, 2.0) -> (1.2, 0.4) sem segmento fechando a base
    segs_aberta = _polilinhas_para_segs(abertas_t)
    pts_ramo = np.array([[0.8, 1.2], [1.0, 2.0], [1.2, 1.2]], dtype=np.float64)
    assert float(_dist_pontos_a_segs(pts_ramo, segs_aberta).max()) <= 1e-4
    assert float(_dist_pontos_a_segs(np.array([[1.0, 0.4]]), segs_aberta).min()) > 0.1, (
        "cadeia aberta foi fechada indevidamente ligando extremos"
    )

    # Tampa: recortou a barra dentro do anel fechado (y=0.2), mas NAO recortou no ramo aberto (y=1.2)
    assert len(recorte_args) == 1
    segs_proj = _polilinhas_para_segs(_polilinhas_mundo(parsed.proj_groups))
    pts_tampados = np.array([[0.95, 0.2], [1.05, 0.2]], dtype=np.float64)
    assert float(_dist_pontos_a_segs(pts_tampados, segs_proj).min()) > 0.05
    pts_nao_tampados = np.array([[0.95, 1.2], [1.05, 1.2]], dtype=np.float64)
    assert float(_dist_pontos_a_segs(pts_nao_tampados, segs_proj).max()) <= 1e-3

    # Compativel com estilo.aplicar_estilo
    estilizado = estilo.aplicar_estilo(svg, "1:50")
    p_est = _parse_svg(estilizado)
    assert "cut" in (p_est.cut_by_guid["G_PAREDE_T"][0].get("class") or "").split()


def test_regra2_peca_100_porcento_aberta_aceita_sem_tampa_e_sem_omissao():
    """Peca cortada so com cadeias abertas (0 fechados): aceita como parcial, desenha aberta, nao tampa."""
    # 1) 1 unica peca cortada 100% aberta (ceil(0.25*1) == 1 -> aceita) + barra de piso atravessando
    f1, p1, m1, e1 = _montar_cena_numpy(
        [
            (10, "G_SO_ABERTA", "IfcWall", _caixa_100_aberta_np(0.0, 0.0, 0.0, 2.0, 1.0, 2.8)),
            (11, "G_BARRA", "IfcSlab", _caixa_np(0.9, -0.5, 0.0, 1.1, 1.5, 0.2)),
        ],
        altura_corte_m=1.2,
    )
    r1, mot1 = planta_cache.desenhar_planta_cache(f1, p1, m1, e1)
    assert mot1 is None and r1 is not None and r1["ok"] is True
    assert r1["secoes_parciais"] == 1 and type(r1["secoes_parciais"]) is int
    assert set(r1["enviados"]) == {10, 11}

    parsed = _parse_svg(r1["svg"])
    assert set(parsed.cut_by_guid.keys()) == {"G_SO_ABERTA"}
    pls = _polilinhas_mundo(parsed.cut_by_guid["G_SO_ABERTA"])
    assert len(pls) == 1 and not _eh_fechada(pls[0]), "subcaminho 100% aberto nao pode ser fechado"

    # Sem tampa: barra continua visivel no centro (x=0.9..1.1, y=0.5)
    segs_proj = _polilinhas_para_segs(_polilinhas_mundo(parsed.proj_groups))
    pts_centro = np.array([[0.9, 0.5], [1.1, 0.5]], dtype=np.float64)
    assert float(_dist_pontos_a_segs(pts_centro, segs_proj).max()) <= 1e-3

    # Verifica tambem ausencia de Z e compatibilidade com estilo
    for p_el in parsed.all_paths:
        cmds, _ = _extrair_polilinhas_d(p_el.get("d") or "")
        assert set(cmds).issubset({"M", "L"})
    estilo.aplicar_estilo(r1["svg"], "1:50")


def test_regra2_peca_cortada_sem_fechados_e_sem_segmentos_cai_secao_aberta():
    """Peca cortada com segmentos mas sem anel fechado nem cadeia aberta (T24s) -> sempre cai secao_aberta (mesmo 1 de 6)."""
    pecas = [(10 + i, f"G_BOA_{i}", "IfcWall", _caixa_np(i * 4.0, 0.0, 0.0, i * 4.0 + 2.0, 0.3, 2.8)) for i in range(5)]
    pecas.append((99, "G_SEM_SEGS", "IfcWall", _caixa_np(30.0, 0.0, 0.0, 30.0 + 2e-7, 2e-7, 2.8)))
    f, pedido, malhas, ev = _montar_cena_numpy(pecas, altura_corte_m=1.2)
    resp, motivo = planta_cache.desenhar_planta_cache(f, pedido, malhas, ev)
    assert resp is None and motivo == "secao_aberta"


def test_regra2_cena_limpa_reporta_secoes_parciais_zero():
    """Cena sem cadeias abertas reporta resp['secoes_parciais'] == 0 (int)."""
    f, pedido, malhas, ev = _montar_cena_numpy(
        [
            (10, "G_PAREDE", "IfcWall", _caixa_np(0.0, 0.0, 0.0, 4.0, 0.3, 2.8)),
            (11, "G_LAJE", "IfcSlab", _caixa_np(0.0, 0.0, -0.2, 4.0, 3.0, 0.0)),
        ],
        altura_corte_m=1.2,
    )
    resp, motivo = planta_cache.desenhar_planta_cache(f, pedido, malhas, ev)
    assert motivo is None and resp is not None and resp["ok"] is True
    assert "secoes_parciais" in resp
    assert type(resp["secoes_parciais"]) is int and resp["secoes_parciais"] == 0


# ==========================================================================
# REGRA 3: LIMITE DE SEGURANCA DE 25% (ceil(0.25 * n_cortadas))
# ==========================================================================
@pytest.mark.parametrize(
    ("n_cortadas", "n_parciais", "deve_aceitar"),
    [
        (1, 1, True),   # ceil(0.25) = 1
        (2, 1, True),   # ceil(0.50) = 1
        (2, 2, False),  # 2 > 1
        (4, 1, True),   # ceil(1.00) = 1
        (4, 2, False),  # 2 > 1
        (5, 2, True),   # ceil(1.25) = 2
        (5, 3, False),  # 3 > 2
        (8, 2, True),   # ceil(2.00) = 2
        (8, 3, False),  # 3 > 2
    ],
)
def test_regra3_limite_25_porcento_ceil(n_cortadas: int, n_parciais: int, deve_aceitar: bool):
    """Fronteira exata de ceil(0.25 * n_cortadas): aceita <= limite, cai secao_aberta se > limite."""
    assert (n_parciais <= math.ceil(0.25 * n_cortadas)) is deve_aceitar
    pecas = []
    for i in range(n_cortadas):
        x0 = i * 4.0
        if i < n_parciais:
            malha = _caixas_fundidas_em_t_np(dx=x0, dy=0.0) if (i % 2 == 0) else _caixa_100_aberta_np(x0, 0.0, 0.0, x0 + 2.0, 0.4, 2.8)
            pecas.append((10 + i, f"G_PARC_{i:02d}", "IfcWall", malha))
        else:
            pecas.append((10 + i, f"G_BOA_{i:02d}", "IfcWall", _caixa_np(x0, 0.0, 0.0, x0 + 2.0, 0.4, 2.8)))

    f, pedido, malhas, ev = _montar_cena_numpy(pecas, altura_corte_m=1.2)
    resp, motivo = planta_cache.desenhar_planta_cache(f, pedido, malhas, ev)
    if deve_aceitar:
        assert motivo is None and resp is not None and resp["ok"] is True
        assert resp["secoes_parciais"] == n_parciais and type(resp["secoes_parciais"]) is int
        parsed = _parse_svg(resp["svg"])
        assert len(parsed.cut_by_guid) == n_cortadas, "nenhuma peca cortada pode ser omitida"
    else:
        assert resp is None and motivo == "secao_aberta"


def test_mutante_limite_25_usa_apenas_pecas_cortadas_no_denominador():
    """Mutante: incluir pecas abaixo/acima no denominador aceitaria 2/2 parciais com 10 lajes abaixo."""
    pecas = [
        (10, "G_PARC_1", "IfcWall", _caixas_fundidas_em_t_np(0.0, 0.0)),
        (11, "G_PARC_2", "IfcWall", _caixa_100_aberta_np(5.0, 0.0, 0.0, 7.0, 0.4, 2.8)),
    ]
    for i in range(10):
        pecas.append((20 + i, f"G_ABAIXO_{i:02d}", "IfcSlab", _caixa_np(i * 2.0, 5.0, -0.2, i * 2.0 + 1.0, 6.0, 0.0)))
    for i in range(4):
        pecas.append((40 + i, f"G_ACIMA_{i:02d}", "IfcBeam", _caixa_np(i * 2.0, 8.0, 2.2, i * 2.0 + 1.0, 8.4, 2.8)))

    f, pedido, malhas, ev = _montar_cena_numpy(pecas, altura_corte_m=1.2)
    resp, motivo = planta_cache.desenhar_planta_cache(f, pedido, malhas, ev)
    assert resp is None and motivo == "secao_aberta"


# ==========================================================================
# REGRA 4: NUNCA OMITIR ELEMENTO (CENA COMBINADA)
# ==========================================================================
def test_regra4_nunca_omitir_elemento_cena_combinada_shift_e_parciais():
    """Cena com vertice no plano + parcial T + parcial 100% aberta + 6 boas + 2 abaixo + 1 acima: nada omitido."""
    pecas = [
        (10, "G_VERT", "IfcWall", _caixa_com_aneis_z_np(0.0, 0.0, 0.0, 2.0, 0.3, 2.8, [1.2])),
        (11, "G_PARC_T", "IfcWall", _caixas_fundidas_em_t_np(4.0, 0.0)),
        (12, "G_PARC_AB", "IfcWall", _caixa_100_aberta_np(8.0, 0.0, 0.0, 10.0, 0.4, 2.8)),
    ]
    for i in range(5):
        x0 = 12.0 + i * 4.0
        pecas.append((13 + i, f"G_BOA_{i}", "IfcWall", _caixa_np(x0, 0.0, 0.0, x0 + 2.0, 0.3, 2.8)))
    # 8 cortadas, 2 parciais -> 2 <= ceil(0.25*8) == 2
    pecas.append((30, "G_LAJE", "IfcSlab", _caixa_np(0.0, 4.0, -0.2, 4.0, 6.0, 0.0)))
    pecas.append((31, "G_MOVEL", "IfcFurnishingElement", _caixa_np(10.0, 4.0, 0.0, 12.0, 5.5, 0.6)))
    pecas.append((32, "G_VIGA_ACIMA", "IfcBeam", _caixa_np(0.0, 8.0, 2.2, 4.0, 8.4, 2.8)))

    f, pedido, malhas, ev = _montar_cena_numpy(pecas, altura_corte_m=1.2)
    resp, motivo = planta_cache.desenhar_planta_cache(f, pedido, malhas, ev)
    assert motivo is None and resp is not None and resp["ok"] is True
    assert resp["secoes_parciais"] == 2
    assert set(resp["enviados"]) == {10, 11, 12, 13, 14, 15, 16, 17, 30, 31}

    parsed = _parse_svg(resp["svg"])
    assert set(parsed.cut_by_guid.keys()) == {
        "G_VERT", "G_PARC_T", "G_PARC_AB", "G_BOA_0", "G_BOA_1", "G_BOA_2", "G_BOA_3", "G_BOA_4"
    }
    assert "G_VIGA_ACIMA" not in resp["svg"]

    # Laje e movel abaixo presentes na projecao
    segs_proj = _polilinhas_para_segs(_polilinhas_mundo(parsed.proj_groups))
    assert float(_dist_pontos_a_segs(np.array([[2.0, 4.0], [2.0, 6.0]]), segs_proj).max()) <= 1e-3
    assert float(_dist_pontos_a_segs(np.array([[11.0, 4.0], [11.0, 5.5]]), segs_proj).max()) <= 1e-3


# ==========================================================================
# REGRA 5: TELEMETRIA INTEGRADA (desenho.processar, Planta, gerente)
# ==========================================================================
def test_regra5_desenho_processar_propaga_secoes_parciais_shift_e_queda(tmp_path, monkeypatch):
    """desenho.processar propaga secoes_parciais no sucesso (via_cache=True) e cai secao_aberta quando >25%."""
    cena = _criar_cena_ifc_4_paredes(tmp_path)
    base = desenho.processar(cena.pedido_base)
    assert base["ok"] is True
    real_ler = desenho.cache_leitura.malhas_do_cache

    # 1) 1 de 4 paredes nao-manifold em T (25%) -> via_cache=True, queda=None, secoes_parciais=1
    def ler_1_parcial(cache, doc, ids):
        malhas, falt = real_ler(cache, doc, ids)
        malhas[cena.paredes[0].GlobalId] = _caixas_fundidas_em_t_np(0.0, 0.0, 0.0, 2.8)
        return malhas, falt

    monkeypatch.setattr(desenho.cache_leitura, "malhas_do_cache", ler_1_parcial)
    r1 = desenho.processar(cena.pedido_cache)
    assert r1["ok"] is True and r1["via_cache"] is True and r1["queda"] is None
    assert type(r1["secoes_parciais"]) is int and r1["secoes_parciais"] == 1

    # 2) Parede com vertice exatamente no plano 1.2 -> via_cache=True, queda=None, secoes_parciais=0
    def ler_vertice_plano(cache, doc, ids):
        malhas, falt = real_ler(cache, doc, ids)
        malhas[cena.paredes[0].GlobalId] = _caixa_com_aneis_z_np(0.0, 0.0, 0.0, 2.0, 0.3, 2.8, [1.2])
        return malhas, falt

    monkeypatch.setattr(desenho.cache_leitura, "malhas_do_cache", ler_vertice_plano)
    r2 = desenho.processar(cena.pedido_cache)
    assert r2["ok"] is True and r2["via_cache"] is True and r2["queda"] is None
    assert type(r2["secoes_parciais"]) is int and r2["secoes_parciais"] == 0

    # 3) 2 de 4 paredes parciais (>25%) -> queda secao_aberta, via_cache=False, secoes_parciais=0
    def ler_2_parciais(cache, doc, ids):
        malhas, falt = real_ler(cache, doc, ids)
        malhas[cena.paredes[0].GlobalId] = _caixas_fundidas_em_t_np(0.0, 0.0, 0.0, 2.8)
        malhas[cena.paredes[1].GlobalId] = _caixa_100_aberta_np(5.0, 0.0, 0.0, 7.0, 0.3, 2.8)
        return malhas, falt

    monkeypatch.setattr(desenho.cache_leitura, "malhas_do_cache", ler_2_parciais)
    r3 = desenho.processar(cena.pedido_cache)
    assert r3["ok"] is True and r3["via_cache"] is False and r3["queda"] == "secao_aberta"
    assert type(r3["secoes_parciais"]) is int and r3["secoes_parciais"] == 0
    assert r3["svg"] == base["svg"]


def test_regra5_planta_e_gerente_propagam_secoes_parciais(monkeypatch, tmp_path):
    """Planta.secoes_parciais (default 0) e gerente._motor_padrao['secoes_parciais'] propagados como int."""
    sel = Selecao(
        ids=(101,),
        tipo="PLANTA",
        pavimento=10,
        faixa=None,
        ocultos_por_classe={},
        sem_geometria=0,
        caixas_envolventes={101: (0.0, 0.0, 0.0, 4.0, 0.2, 3.0)},
    )
    svg_min = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1 1"><path d="M 0,0 L 1,0"/></svg>'
    pl_def = app_planta.Planta(
        svg=svg_min,
        n_paths=1,
        selecao=sel,
        tempos={"geo_s": 0.0},
        unidade_escala=1.0,
        altura_corte=1.2,
        caixas=(),
    )
    assert type(pl_def.secoes_parciais) is int and pl_def.secoes_parciais == 0

    # gerar_planta propaga secoes_parciais da resposta do auxiliar
    class _El:
        def __init__(self, i, g, cls):
            self._i, self.GlobalId, self._cls = i, g, cls
            self.ObjectPlacement = None
            self.Elevation = 0.0

        def id(self):
            return self._i

        def is_a(self, nome=None):
            return self._cls if nome is None else self._cls == nome

    pav = _El(10, "PAV", "IfcBuildingStorey")
    ann = _El(20, "VISTA", "IfcAnnotation")
    w1 = _El(101, "W1", "IfcWall")
    ifc_fake = SimpleNamespace(
        by_id=lambda i: {10: pav, 20: ann, 101: w1}[int(i)],
        by_guid=lambda g: {"PAV": pav, "VISTA": ann, "W1": w1}[g],
    )
    monkeypatch.setattr(vistas_ifc, "ler_vista", lambda _f, _g: {"tipo": "PLANTA"})
    monkeypatch.setattr(app_planta, "_altura_corte", lambda _f, _a: 1.2)
    monkeypatch.setattr(app_planta.ifcopenshell.util.unit, "calculate_unit_scale", lambda _f: 1.0)
    monkeypatch.setattr(app_selecao, "_validar_categorias", lambda _f, _c: None)
    monkeypatch.setattr(app_selecao, "selecionar", lambda _f, _g, **kw: sel)

    arq = tmp_path / "m.ifc"
    arq.write_text("ISO-10303-21;\nEND-ISO-10303-21;\n", encoding="utf-8")
    pl = app_planta.gerar_planta(
        ifc_fake,
        "VISTA",
        caminho_ifc=arq,
        pasta_cache_geometria=tmp_path / "geo",
        executor=lambda _q: {
            "ok": True,
            "svg": svg_min,
            "n_paths": 1,
            "enviados": [101],
            "caixas": [],
            "em_cache": [],
            "pesados": [],
            "falhas_geometria": [],
            "tempos": {"abrir_s": 0.0, "geo_s": 0.0, "write_s": 0.0, "finalize_s": 0.0, "cache_s": 0.01, "motor_s": 0.02},
            "via_cache": True,
            "queda": None,
            "n_faltantes": 0,
            "secoes_parciais": 2,
        },
    )
    assert type(pl.secoes_parciais) is int and pl.secoes_parciais == 2

    # gerente._motor_padrao propaga secoes_parciais em dados
    monkeypatch.setenv("OBIM_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setattr(app_planta, "gerar_planta", lambda *a, **kw: pl)
    dados = app_gerente._motor_padrao(
        "planta",
        ifc_fake,
        "VISTA",
        {"caminho_ifc": arq},
        cancelar=threading.Event(),
        progresso=lambda _m: None,
        cache=app_cache.CacheDesenho(tmp_path / "vista"),
    )
    assert type(dados["secoes_parciais"]) is int and dados["secoes_parciais"] == 2
