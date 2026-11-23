# SPDX-License-Identifier: AGPL-3.0-or-later
"""Parte 2 de test_s06_t24c_planta_cache_oraculo.py (divisao mecanica em PRs de ate 400 linhas). Auxiliares e fixtures vem das partes anteriores."""
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
from test_s06_t24c_planta_cache_oraculo import NS_IFC, _caixa_np, _contagem_segmentos_corte, _criar_caixa_ifc, _dist_pontos_a_segs, _extrair_polilinhas_d, _mod, _montar_cena_numpy, _parse_svg, _polilinhas_de_elementos, _polilinhas_para_segs, _tubo_np  # noqa: F401



def _criar_cena_ifc_sintetica(tmp_path: Path, *, offset: tuple[float, float] = (0.0, 0.0)) -> SimpleNamespace:
    ox, oy = offset
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

    parede = _criar_caixa_ifc(f, body, "IfcWall", 4.0, 0.2, 2.8, (ox, oy, 0.0))
    laje = _criar_caixa_ifc(f, body, "IfcSlab", 4.0, 3.0, 0.2, (ox, oy, -0.2))
    movel = _criar_caixa_ifc(f, body, "IfcFurnishingElement", 1.0, 0.8, 0.7, (ox + 1.0, oy + 1.2, 0.0))
    viga_acima = _criar_caixa_ifc(f, body, "IfcBeam", 4.0, 0.2, 0.4, (ox, oy + 2.0, 2.4))
    api("spatial.assign_container", f, products=[parede, laje, movel, viga_acima], relating_structure=andar)

    arq = tmp_path / "planta_sintetica.ifc"
    f.write(str(arq))
    f = ifcopenshell.open(str(arq))
    andar = f.by_guid(andar.GlobalId)
    parede = f.by_guid(parede.GlobalId)
    laje = f.by_guid(laje.GlobalId)
    movel = f.by_guid(movel.GlobalId)
    viga_acima = f.by_guid(viga_acima.GlobalId)

    pasta = tmp_path / "cache_geo"
    doc = construtor.documento_de(arq)
    with construtor.abrir_banco(pasta) as cache:
        r = construtor.construir_lote(f, cache, construtor.fila_inicial(f), documento=doc, assinatura="s1", memo={})
        assert r["falhas"] == 0 and r["gravadas"] == 4

    todos = [parede, laje, movel, viga_acima]
    vista = {"tipo": "PLANTA", "pavimento": andar.GlobalId, "escala": 1.0, "altura_corte_m": 1.2}
    pedido_base = {"arquivo": str(arq), "vista": vista, "elementos": [(e.id(), e.GlobalId) for e in todos], "threads": 1}
    return SimpleNamespace(
        arq=arq,
        pasta=pasta,
        f=f,
        andar=andar,
        parede=parede,
        laje=laje,
        movel=movel,
        viga_acima=viga_acima,
        pedido_base=pedido_base,
        pedido_cache={**pedido_base, "pasta_cache_geometria": str(pasta)},
    )


# ---------- testes funcionais do modulo planta_cache ----------
def test_classificacao_pecas_pelo_plano_de_corte():
    pc = _mod()
    f, pedido, malhas, ev = _montar_cena_numpy(
        [
            (10, "G_PAREDE", "IfcWall", _caixa_np(0.0, 0.0, 0.0, 4.0, 0.2, 2.8)),
            (11, "G_LAJE", "IfcSlab", _caixa_np(0.0, 0.0, -0.2, 4.0, 3.0, 0.0)),
            (12, "G_MOVEL", "IfcFurnishingElement", _caixa_np(1.0, 1.0, 0.0, 2.0, 1.8, 0.7)),
            (13, "G_VIGA_ACIMA", "IfcBeam", _caixa_np(5.0, 5.0, 2.2, 7.0, 5.4, 2.8)),
        ],
        altura_corte_m=1.2,
    )
    resp, motivo = pc.desenhar_planta_cache(f, pedido, malhas, ev, abrir_s=0.01, cache_s=0.02)
    assert motivo is None and isinstance(resp, dict) and resp["ok"] is True

    parsed = _parse_svg(resp["svg"])
    assert set(parsed.cut_by_guid.keys()) == {"G_PAREDE"}
    assert "G_LAJE" not in parsed.cut_by_guid and "G_MOVEL" not in parsed.cut_by_guid
    assert "G_VIGA_ACIMA" not in resp["svg"]
    assert {10, 11, 12}.issubset(set(resp["enviados"]))
    assert resp["falhas_geometria"] == []

    # Nenhum segmento da viga acima (em x in [5, 7], y in [5, 5.4]) pode aparecer na projecao
    segs_proj = _polilinhas_para_segs(_polilinhas_de_elementos(parsed.proj_groups))
    assert len(segs_proj) > 0
    assert float(_dist_pontos_a_segs(np.array([[6.0, 5.2], [5.0, 5.0]]), segs_proj).min()) > 0.5


def test_secao_usa_corte_plano_e_aneis(monkeypatch):
    pc = _mod()
    corte_calls, aneis_calls = [], []
    real_corte = corte_plano.cortar_malha_no_plano
    real_aneis = aneis.aneis_de_segmentos

    def espia_corte(v, t, z):
        corte_calls.append(float(z))
        return real_corte(v, t, z)

    def espia_aneis(segs, *a, **k):
        aneis_calls.append(len(segs))
        return real_aneis(segs, *a, **k)

    monkeypatch.setattr(corte_plano, "cortar_malha_no_plano", espia_corte)
    monkeypatch.setattr(aneis, "aneis_de_segmentos", espia_aneis)

    f, pedido, malhas, ev = _montar_cena_numpy(
        [
            (10, "G_PAREDE", "IfcWall", _caixa_np(1.0, 2.0, 0.0, 5.0, 2.3, 2.8)),
            (11, "G_LAJE", "IfcSlab", _caixa_np(0.0, 0.0, -0.2, 6.0, 4.0, 0.0)),
            (12, "G_ACIMA", "IfcBeam", _caixa_np(0.0, 0.0, 2.0, 2.0, 0.3, 2.5)),
        ],
        altura_corte_m=1.2,
    )
    resp, motivo = pc.desenhar_planta_cache(f, pedido, malhas, ev)
    assert motivo is None and resp["ok"] is True
    assert corte_calls == [pytest.approx(1.2)]
    assert len(aneis_calls) == 1 and aneis_calls[0] >= 4

    parsed = _parse_svg(resp["svg"])
    pls_corte = _polilinhas_de_elementos(parsed.cut_by_guid["G_PAREDE"])
    assert len(pls_corte) == 1
    assert np.allclose(pls_corte[0][0], pls_corte[0][-1], atol=1e-6)
    assert _contagem_segmentos_corte(pls_corte) == 4
    xs, ys = pls_corte[0][:, 0], pls_corte[0][:, 1]
    assert (xs.min(), xs.max(), ys.min(), ys.max()) == pytest.approx((1.0, 5.0, 2.0, 2.3), abs=1e-5)


def test_uma_unica_chamada_linhas_visiveis_multi_com_angulo_0001(monkeypatch):
    pc = _mod()
    multi_calls, single_calls = [], []
    real_multi = visibilidade.linhas_visiveis_multi

    def espia_multi(pecas, *args, **kwargs):
        multi_calls.append((len(list(pecas)), args, dict(kwargs)))
        return real_multi(pecas, *args, **kwargs)

    def proibe_single(*args, **kwargs):
        single_calls.append((args, kwargs))
        raise AssertionError("nao deve chamar linhas_visiveis peca a peca")

    monkeypatch.setattr(visibilidade, "linhas_visiveis_multi", espia_multi)
    monkeypatch.setattr(visibilidade, "linhas_visiveis", proibe_single)

    f, pedido, malhas, ev = _montar_cena_numpy(
        [
            (10, "G_P1", "IfcWall", _caixa_np(0.0, 0.0, 0.0, 4.0, 0.2, 2.8)),
            (11, "G_P2", "IfcWall", _caixa_np(0.0, 3.0, 0.0, 4.0, 3.2, 2.8)),
            (12, "G_LAJE", "IfcSlab", _caixa_np(0.0, 0.0, -0.2, 4.0, 3.2, 0.0)),
            (13, "G_MOVEL", "IfcFurnishingElement", _caixa_np(1.0, 1.0, 0.0, 2.0, 2.0, 0.8)),
        ],
        altura_corte_m=1.2,
    )
    resp, motivo = pc.desenhar_planta_cache(f, pedido, malhas, ev)
    assert motivo is None and resp["ok"] is True
    assert single_calls == []
    assert len(multi_calls) == 1
    n_malhas, _args, kwargs = multi_calls[0]
    assert n_malhas == 4  # 2 metades inferiores das paredes + laje + movel
    assert kwargs.get("angulo_graus", 0.001) == pytest.approx(0.001)


def test_svg_comandos_ml_sem_z_projecao_e_estilo():
    pc = _mod()
    f, pedido, malhas, ev = _montar_cena_numpy(
        [
            (10, "G_PAREDE", "IfcWall", _caixa_np(0.0, 1.0, 0.0, 4.0, 1.2, 2.8)),
            (11, "G_LAJE", "IfcSlab", _caixa_np(0.0, 0.0, -0.2, 4.0, 3.0, 0.0)),
        ],
        altura_corte_m=1.2,
        pav_guid="PAV_TERREO",
    )
    resp, motivo = pc.desenhar_planta_cache(f, pedido, malhas, ev)
    assert motivo is None and resp["ok"] is True
    svg = resp["svg"]

    assert "-0.000000" not in svg
    parsed = _parse_svg(svg)
    assert len(parsed.storeys) == 1
    assert parsed.storeys[0].get(f"{NS_IFC}guid") == "PAV_TERREO"
    assert len(parsed.proj_groups) == 1
    proj_g = parsed.proj_groups[0]
    assert proj_g.get(f"{NS_IFC}guid") is None
    assert all(sub.get(f"{NS_IFC}guid") is None for sub in proj_g.iter() if sub.tag.rsplit("}", 1)[-1] == "g")

    assert len(parsed.all_paths) == resp["n_paths"] and resp["n_paths"] >= 2
    for path_el in parsed.all_paths:
        d = (path_el.get("d") or "").strip()
        cmds, runs = _extrair_polilinhas_d(d)
        assert cmds and set(cmds).issubset({"M", "L"}), f"comandos proibidos em d={d!r}"
        assert "Z" not in cmds and "z" not in cmds
        assert len(runs) >= 1

    # Compatibilidade estrita com estilo.aplicar_estilo
    estilizado = estilo.aplicar_estilo(svg, "1:50")
    p_est = _parse_svg(estilizado)
    assert "cut" in (p_est.cut_by_guid["G_PAREDE"][0].get("class") or "").split()
    assert "IfcWall" in (p_est.cut_by_guid["G_PAREDE"][0].get("class") or "").split()
    assert "cut" not in (p_est.proj_groups[0].get("class") or "").split()


def test_tampa_opcao1_recorta_projecao_fora_dos_aneis_sobreposicao_e_furo(monkeypatch):
    pc = _mod()
    recorte_calls = []
    real_recorte = recorte.recortar_fora_dos_aneis

    def espia_recorte(polilinhas, aneis_arg, *a, **k):
        recorte_calls.append((len(list(polilinhas)), k.get("encolher", 5e-4)))
        return real_recorte(polilinhas, aneis_arg, *a, **k)

    monkeypatch.setattr(recorte, "recortar_fora_dos_aneis", espia_recorte)

    # 1) Duas paredes cortadas sobrepostas no canto [1.6..2.0, 0.0..0.4] + barra abaixo passando pelo canto
    f, pedido, malhas, ev = _montar_cena_numpy(
        [
            (10, "G_PAR_A", "IfcWall", _caixa_np(0.0, 0.0, 0.0, 2.0, 0.4, 2.8)),
            (11, "G_PAR_B", "IfcWall", _caixa_np(1.6, 0.0, 0.0, 2.0, 2.0, 2.8)),
            (12, "G_BARRA", "IfcSlab", _caixa_np(1.75, -0.6, 0.0, 1.85, 1.0, 0.2)),
        ],
        altura_corte_m=1.2,
    )
    resp, motivo = pc.desenhar_planta_cache(f, pedido, malhas, ev)
    assert motivo is None and resp["ok"] is True
    assert len(recorte_calls) >= 1
    parsed = _parse_svg(resp["svg"])
    segs_proj = _polilinhas_para_segs(_polilinhas_de_elementos(parsed.proj_groups))
    # Trecho externo da barra (y=-0.3) visivel; interior da sobreposicao (x=1.8, y=0.2) sem vazamento
    assert float(_dist_pontos_a_segs(np.array([[1.75, -0.3], [1.85, -0.3]]), segs_proj).max()) <= 1e-3
    assert float(_dist_pontos_a_segs(np.array([[1.75, 0.2], [1.85, 0.2], [1.8, 0.2]]), segs_proj).min()) > 5e-3

    # 2) Moldura com furo cortada + bloco abaixo exatamente dentro do furo -> bloco permanece visivel
    ext = [(0.0, 0.0), (2.0, 0.0), (2.0, 2.0), (0.0, 2.0)]
    furo = [(0.5, 0.5), (1.5, 0.5), (1.5, 1.5), (0.5, 1.5)]
    f2, ped2, mal2, ev2 = _montar_cena_numpy(
        [
            (20, "G_MOLDURA", "IfcWall", _tubo_np(ext, furo, 0.0, 2.8)),
            (21, "G_BLOCO_FURO", "IfcFurnishingElement", _caixa_np(0.8, 0.8, 0.0, 1.2, 1.2, 0.5)),
        ],
        altura_corte_m=1.2,
    )
    resp2, motivo2 = pc.desenhar_planta_cache(f2, ped2, mal2, ev2)
    assert motivo2 is None and resp2["ok"] is True
    p2 = _parse_svg(resp2["svg"])
    pls_mold = _polilinhas_de_elementos(p2.cut_by_guid["G_MOLDURA"])
    assert len(pls_mold) == 2  # anel externo + furo
    segs_proj2 = _polilinhas_para_segs(_polilinhas_de_elementos(p2.proj_groups))
    pts_bloco = np.array([[0.8, 1.0], [1.2, 1.0], [1.0, 0.8], [1.0, 1.2]], dtype=np.float64)
    assert float(_dist_pontos_a_segs(pts_bloco, segs_proj2).max()) <= 1e-3


def test_determinismo_rodadas_ordem_e_threads():
    pc = _mod()
    pecas = [
        (10, "G_03", "IfcWall", _caixa_np(0.0, 0.0, 0.0, 4.0, 0.2, 2.8)),
        (11, "G_01", "IfcSlab", _caixa_np(0.0, 0.0, -0.2, 4.0, 3.0, 0.0)),
        (12, "G_04", "IfcFurnishingElement", _caixa_np(0.5, 0.8, 0.0, 1.5, 1.6, 0.7)),
        (13, "G_02", "IfcWall", _caixa_np(3.8, 0.0, 0.0, 4.0, 3.0, 2.8)),
    ]
    f1, p1, m1, e1 = _montar_cena_numpy(pecas, threads=1)
    r1, mot1 = pc.desenhar_planta_cache(f1, p1, m1, e1)
    r2, mot2 = pc.desenhar_planta_cache(f1, p1, m1, e1)
    r3, mot3 = pc.desenhar_planta_cache(f1, p1, m1, e1)
    assert mot1 is None and mot2 is None and mot3 is None
    assert r1["svg"] == r2["svg"] == r3["svg"]

    # Ordem embaralhada de entrada -> SVG identico byte a byte
    f_emb, p_emb, m_emb, e_emb = _montar_cena_numpy(list(reversed(pecas)), threads=1)
    r_emb, mot_emb = pc.desenhar_planta_cache(f_emb, p_emb, m_emb, e_emb)
    assert mot_emb is None and r_emb["svg"] == r1["svg"]

    # threads=4 vs threads=1 -> SVG identico byte a byte
    f_t4, p_t4, m_t4, e_t4 = _montar_cena_numpy(pecas, threads=4)
    r_t4, mot_t4 = pc.desenhar_planta_cache(f_t4, p_t4, m_t4, e_t4)
    assert mot_t4 is None and r_t4["svg"] == r1["svg"]


# ---------- testes mutantes (1 comportamento errado por teste, ESPEC §3.2) ----------
@pytest.mark.parametrize(
    "malha_ruim",
    [
        (np.zeros((0, 3), dtype=np.float64), np.zeros((0, 3), dtype=np.int32)),
        (np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]), np.zeros((0, 3), dtype=np.int32)),
        (np.array([[0.0, np.nan, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 2.0]]), np.array([[0, 1, 2]], dtype=np.int32)),
        (np.array([[0.0, np.inf, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 2.0]]), np.array([[0, 1, 2]], dtype=np.int32)),
        (np.array([[2e12, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 2.0]]), np.array([[0, 1, 2]], dtype=np.int32)),
        (np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 2.0]]), np.array([[0, 1, 5]], dtype=np.int32)),
        (np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 2.0]]), np.array([[-1, 1, 2]], dtype=np.int32)),
        (np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 2.0]]), np.array([[0.0, 1.0, 2.0]], dtype=np.float64)),
        (np.zeros((4, 2), dtype=np.float64), np.array([[0, 1, 2]], dtype=np.int32)),
    ],
)
def test_mutante_01_omissao_silenciosa_malha_invalida(malha_ruim):
    """Mutante 1: pular peca com malha invalida em vez de cair o pavimento inteiro com `malha_invalida`."""
    pc = _mod()
    f, pedido, malhas, ev = _montar_cena_numpy(
        [
            (10, "G_BOA", "IfcWall", _caixa_np(0.0, 0.0, 0.0, 3.0, 0.2, 2.8)),
            (11, "G_RUIM", "IfcSlab", malha_ruim),
        ],
        altura_corte_m=1.2,
    )
    resp, motivo = pc.desenhar_planta_cache(f, pedido, malhas, ev)
    assert resp is None and motivo == "malha_invalida"


def test_mutante_01b_gid_ausente_em_malhas_mundo_cai_malha_invalida():
    """Mutante 1b: pular peca de `elementos_validos` ausente em `malhas_mundo`."""
    pc = _mod()
    f, pedido, malhas, ev = _montar_cena_numpy(
        [
            (10, "G_BOA", "IfcWall", _caixa_np(0.0, 0.0, 0.0, 3.0, 0.2, 2.8)),
            (11, "G_FALTA", "IfcSlab", _caixa_np(0.0, 0.0, -0.2, 3.0, 2.0, 0.0)),
        ],
        altura_corte_m=1.2,
    )
    del malhas["G_FALTA"]
    resp, motivo = pc.desenhar_planta_cache(f, pedido, malhas, ev)
    assert resp is None and motivo == "malha_invalida"


def test_mutante_02_secao_aberta_ignora_ou_pula_peca():
    """Mutante 2: desenhar ou pular peca em vez de cair com `secao_aberta` nos casos acima do limite T24f."""
    pc = _mod()
    v_boa, t_boa = _caixa_np(5.0, 0.0, 0.0, 8.0, 0.2, 2.8)

    # Caso A (ajustado T24f): 2 pecas abertas em 3 cortadas (> ceil(0.25*3)=1) -> cai secao_aberta
    v_ab1, t_ab1 = _caixa_np(0.0, 0.0, 0.0, 2.0, 0.3, 2.8)
    v_ab2, t_ab2 = _caixa_np(0.0, 2.0, 0.0, 2.0, 2.3, 2.8)
    f1, p1, m1, e1 = _montar_cena_numpy(
        [
            (10, "G_BOA", "IfcWall", (v_boa, t_boa)),
            (11, "G_ABERTA_1", "IfcWall", (v_ab1, t_ab1[:-2])),
            (12, "G_ABERTA_2", "IfcWall", (v_ab2, t_ab2[:-2])),
        ],
        altura_corte_m=1.2,
    )
    r1, mot1 = pc.desenhar_planta_cache(f1, p1, m1, e1)
    assert r1 is None and mot1 == "secao_aberta"

    # Caso B (ajustado T24f): malha com vertices ocupando z=1.2 e todos os 4 deltas (+-1e-5, +-3.7e-5) -> cai secao_aberta
    zs_bloq = [0.0, 1.2 - 3.7e-5, 1.2 - 1e-5, 1.2, 1.2 + 1e-5, 1.2 + 3.7e-5, 2.8]
    v_imp = np.array(
        [[x, y, z] for z in zs_bloq for x, y in ((0.0, 0.0), (1.0, 0.0), (1.0, 0.4), (0.0, 0.4))],
        dtype=np.float64,
    )
    t_imp = [[0, 2, 1], [0, 3, 2]]
    for k in range(len(zs_bloq) - 1):
        b, top_k = 4 * k, 4 * (k + 1)
        for i in range(4):
            j = (i + 1) % 4
            t_imp.extend([[b + i, b + j, top_k + j], [b + i, top_k + j, top_k + i]])
    top_f = 4 * (len(zs_bloq) - 1)
    t_imp.extend([[top_f, top_f + 1, top_f + 2], [top_f, top_f + 2, top_f + 3]])
    f2, p2, m2, e2 = _montar_cena_numpy(
        [(10, "G_BOA", "IfcWall", (v_boa, t_boa)), (12, "G_DEGRAU_IMP", "IfcWall", (v_imp, np.asarray(t_imp, dtype=np.int32)))],
        altura_corte_m=1.2,
    )
    r2, mot2 = pc.desenhar_planta_cache(f2, p2, m2, e2)
    assert r2 is None and mot2 == "secao_aberta"
