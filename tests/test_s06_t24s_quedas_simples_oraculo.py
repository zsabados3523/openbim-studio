# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oraculo F0-S06-T24s (ADR-010, P3): correcoes A, C e E das quedas simples da planta pelo cache.

Alvos (o implementador NAO edita este arquivo; somente producao:
`geometria/obim_geometria/planta_cache.py` e `geometria/obim_geometria/desenho.py`):

CONTRATO (diag_t24r_quedas.md + especificacao T24s):
(A) Corte vazio em `planta_cache.desenhar_planta_cache`:
  - Peca cuja caixa cruza o plano de corte `z_ef` (`zmin_loc <= z_ef + eps_ef < zmax_loc`),
    mas NENHUM triangulo cruza (`cortar_malha_no_plano` devolve `len(segs) == 0`):
    * NAO derruba o pavimento (nao retorna `(None, "secao_aberta")`).
    * Nao gera secao, nao gera tampa (`grupos_secao`), nao incrementa `secoes_parciais`
      e nao infla o denominador `n_cortadas` do limite de 25%.
    * Classificada pela posicao dos seus triangulos:
      - Triangulos abaixo (`len(t_ab) > 0`): `(v_ab, t_ab)` entra na projecao (`malhas_proj`,
        com ajuste `dx_g, dy_g` em coordenadas grandes/UTM) e a peca permanece em `enviados`.
      - Todos os triangulos acima (`len(t_ab) == 0`): nao entra em `malhas_proj`, nao entra
        no SVG e nao entra em `enviados` (igual as pecas acima do corte).
  - Peca com `len(segs) > 0`, mas `aneis.aneis_de_segmentos(segs)` devolve `not fechados and not abertos`
    (segs sem anel, ex.: segmentos menores que `tol=1e-6` colapsados): mantem a regra atual
    de queda `(None, "secao_aberta")`.

(C) Filtro de elemento so-anotacao em `desenho._elementos_validos_cache`:
  - Criterio: elemento cuja `Representation` possui representacoes (`Representations`) todas
    compostas exclusivamente por itens sem corpo solido/malha (curvas/anotacao 2D: ex.
    `IfcGeometricCurveSet`, `IfcGeometricSet` sem superficies, `IfcCurve`, `IfcPoint`,
    `IfcTextLiteral`, `IfcAnnotationFillArea`, ou `IfcMappedItem` contendo apenas esses itens)
    e filtrado fora de `_elementos_validos_cache`.
  - Consequencia: nao e exigido do cache, nao conta em `n_faltantes`, nao produz `cache_incompleto`
    nem queda; `via_cache=True`, `queda=None`, `n_faltantes=0`, e resposta/SVG identicos ao IFC
    sem esse elemento.
  - Elemento com qualquer item solido/malha (ex.: `IfcBuildingElementProxy` com `IfcExtrudedAreaSolid`,
    ou elemento misto com `Body` solido + `Annotation`/`IfcGeometricCurveSet`, ou stub sem
    `.Representations`) NAO e filtrado.

(E) Aneis fechados de area ~0 (`|area| <= 1e-12`) em `planta_cache.desenhar_planta_cache`:
  - Antes de `oclusores._agrupar_aneis(fechados)`, separa `fechados` usando `abs(aneis._area(a)) <= 1e-12`:
    * Se sobram aneis bons (`|area| > 1e-12`, preservando externos positivos e furos negativos):
      os aneis bons seguem para `oclusores._agrupar_aneis`, tampa e secao fechada; os aneis
      degenerados sao descartados SEM linha (area zero nao tem extensao); sem `abertos`,
      `secoes_parciais` nao incrementa (0).
    * Se NAO sobra nenhum anel bom (peca so com aneis fechados de area ~0): os aneis degenerados
      viram cadeias abertas desenhadas como linha (`M/L` sem `Z`, fechando a ultima aresta), fora
      da tampa (`grupos_secao`), e a peca conta 1 em `secoes_parciais` (preservando os oraculos T24h).
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace

import ifcopenshell
import ifcopenshell.api
import numpy as np
import pytest

from obim_geometria import (
    aneis,
    construtor,
    corte_plano,
    desenho,
    oclusores,
    planta_cache,
    recorte,
)
from openbim_app.desenho import estilo
from test_s06_t24b_despacho_cache_oraculo import _caixa, _checar_telemetria, _sql
from test_s06_t24c_planta_cache_oraculo import _tubo_np
from test_s06_t24f_secao_tolerante_oraculo import _caixa_np, _caixas_fundidas_em_t_np, _extrair_polilinhas_d, _montar_cena_numpy, _parse_svg, _transladar_malha  # noqa: F401
from test_s06_t24f_secao_tolerante_oraculo_b import _dist_pontos_a_segs, _polilinhas_mundo, _polilinhas_para_segs, _pontos_de_segs, _sha256  # noqa: F401
from test_s06_t24h_aneis_nao_agrupaveis_oraculo import (
    _boas,
    _checar_imutavel,
    _congelar_snapshot,
    _malha_anel_area_quase_zero_np,
    _malha_anel_bowtie_area_zero_np,
    _svg_referencia_boas,
    _verificar_linhas_peca_ruim,
    _xml_grupos,
)


# ---------- construtores sinteticos numpy ----------
def _combinar_malhas(*malhas: tuple[np.ndarray, np.ndarray]) -> tuple[np.ndarray, np.ndarray]:
    verts, tris, off = [], [], 0
    for v, t in malhas:
        verts.append(np.asarray(v, dtype=np.float64))
        tris.append(np.asarray(t, dtype=np.int32) + off)
        off += len(v)
    return np.vstack(verts), np.vstack(tris).astype(np.int32)


def _malha_com_vao_np(
    x_ab: tuple[float, float] = (20.0, 22.0),
    y_ab: tuple[float, float] = (0.0, 1.0),
    z_ab: tuple[float, float] = (0.0, 0.7),
    x_ac: tuple[float, float] = (26.0, 28.0),
    y_ac: tuple[float, float] = (0.0, 1.0),
    z_ac: tuple[float, float] = (1.9, 2.6),
) -> tuple[np.ndarray, np.ndarray]:
    """Peca unica com 2 componentes fechados (um abaixo e um acima de z=1.2): 0 triangulos cruzam."""
    return _combinar_malhas(
        _caixa_np(x_ab[0], y_ab[0], z_ab[0], x_ab[1], y_ab[1], z_ab[1]),
        _caixa_np(x_ac[0], y_ac[0], z_ac[0], x_ac[1], y_ac[1], z_ac[1]),
    )


def _malha_toda_abaixo_bbox_cruza_np(
    x0: float = 20.0, y0: float = 0.0, x1: float = 22.0, y1: float = 1.0, *, z_alto: float = 2.5
) -> tuple[np.ndarray, np.ndarray]:
    """Todos os triangulos abaixo de z=1.2, mas 1 vertice orfao acima faz a bbox cruzar o plano."""
    v, t = _caixa_np(x0, y0, 0.0, x1, y1, 0.7)
    return np.vstack([v, np.array([[x0, y0, z_alto]], dtype=np.float64)]), t


def _malha_toda_acima_bbox_cruza_np(
    x0: float = 26.0, y0: float = 0.0, x1: float = 28.0, y1: float = 1.0, *, z_baixo: float = 0.2
) -> tuple[np.ndarray, np.ndarray]:
    """Todos os triangulos acima de z=1.2, mas 1 vertice orfao abaixo faz a bbox cruzar o plano."""
    v, t = _caixa_np(x0, y0, 1.9, x1, y1, 2.6)
    return np.vstack([v, np.array([[x0, y0, z_baixo]], dtype=np.float64)]), t


def _malha_segs_sem_anel_np(
    x0: float = 24.0, y0: float = 0.0, z0: float = 0.0, z1: float = 2.8, lado: float = 2e-7
) -> tuple[np.ndarray, np.ndarray]:
    """Micro-caixa (< tol=1e-6): gera segmentos no corte, mas aneis_de_segmentos devolve ([], [])."""
    return _caixa_np(x0, y0, z0, x0 + lado, y0 + lado, z1)


def _malha_bom_mais_area_zero_np(
    x0: float = 12.0, y0: float = 0.0, *, dx_deg: float = 4.0, dy_deg: float = 0.0
) -> tuple[np.ndarray, np.ndarray]:
    """Mesma peca com 1 caixa boa (area=2.0) + 1 prisma fechado de area ~5e-14 separado em XY."""
    return _combinar_malhas(
        _caixa_np(x0, y0, 0.0, x0 + 2.0, y0 + 1.0, 2.8),
        _malha_anel_area_quase_zero_np(x0 + dx_deg, y0 + dy_deg, 0.0, 2.8),
    )


def _malha_tubo_mais_area_zero_np(
    x0: float = 10.0, y0: float = 0.0, *, dx_deg: float = 5.0
) -> tuple[np.ndarray, np.ndarray]:
    """Moldura com furo (area externa > 0, furo < 0) + 1 anel fechado de area ~0."""
    ext = [(x0, y0), (x0 + 2.0, y0), (x0 + 2.0, y0 + 2.0), (x0, y0 + 2.0)]
    furo = [(x0 + 0.5, y0 + 0.5), (x0 + 1.5, y0 + 0.5), (x0 + 1.5, y0 + 1.5), (x0 + 0.5, y0 + 1.5)]
    return _combinar_malhas(
        _tubo_np(ext, furo, 0.0, 2.8),
        _malha_anel_area_quase_zero_np(x0 + dx_deg, y0, 0.0, 2.8),
    )


def _contorno_retangulo_pts(x0: float, y0: float, x1: float, y1: float) -> np.ndarray:
    """Pontos representativos (vertices e meios de aresta) das 4 arestas do retangulo."""
    xm, ym = 0.5 * (x0 + x1), 0.5 * (y0 + y1)
    return np.array(
        [[x0, y0], [xm, y0], [x1, y0], [x1, ym], [x1, y1], [xm, y1], [x0, y1], [x0, ym]],
        dtype=np.float64,
    )


# ---------- helper IFC sintetico para C (baseado em T24b) ----------
def _criar_cena_ifc_c(
    tmp_path: Path,
    *,
    subdir: str = "cena",
    com_proxy_anotacao: bool = False,
    rep_type_anotacao: str = "GeometricSet",
    com_proxy_solido: bool = False,
    com_proxy_misto: bool = False,
    guids_fixos: dict[str, str] | None = None,
) -> SimpleNamespace:
    pasta_base = tmp_path / subdir
    pasta_base.mkdir(parents=True, exist_ok=True)
    api = ifcopenshell.api.run
    f = api("project.create_file", version="IFC4")
    proj = api("root.create_entity", f, ifc_class="IfcProject")
    api("unit.assign_unit", f, units=[f.createIfcSIUnit(UnitType="LENGTHUNIT", Prefix=None, Name="METRE")])
    ctx = api("context.add_context", f, context_type="Model")
    body = api("context.add_context", f, context_type="Model", context_identifier="Body", target_view="MODEL_VIEW", parent=ctx)
    annot_ctx = api(
        "context.add_context", f, context_type="Model", context_identifier="Annotation", target_view="MODEL_VIEW", parent=ctx
    )
    site = api("root.create_entity", f, ifc_class="IfcSite")
    predio = api("root.create_entity", f, ifc_class="IfcBuilding")
    andar = api("root.create_entity", f, ifc_class="IfcBuildingStorey", name="Terreo")
    andar.Elevation = 0.0
    for filho, pai in ((site, proj), (predio, site), (andar, predio)):
        api("aggregate.assign_object", f, products=[filho], relating_object=pai)

    parede = _caixa(f, body, "IfcWall", 5.0, 0.2, 2.8, (0.0, 0.0, 0.0))
    abertura = _caixa(f, body, "IfcOpeningElement", 1.0, 0.5, 1.2, (2.0, -0.15, 0.8))
    api("feature.add_feature", f, feature=abertura, element=parede)
    laje = _caixa(f, body, "IfcSlab", 5.0, 4.0, 0.2, (0.0, 0.0, -0.2))
    movel = _caixa(f, body, "IfcFurnishingElement", 1.0, 0.8, 0.8, (1.0, 1.5, 0.0))

    if guids_fixos:
        andar.GlobalId = guids_fixos["andar"]
        parede.GlobalId = guids_fixos["parede"]
        abertura.GlobalId = guids_fixos["abertura"]
        laje.GlobalId = guids_fixos["laje"]
        movel.GlobalId = guids_fixos["movel"]

    contidos = [parede, laje, movel]
    solidos = [parede, laje, movel]

    proxy_anot = None
    if com_proxy_anotacao:
        proxy_anot = api("root.create_entity", f, ifc_class="IfcBuildingElementProxy", name="Model Lines: Eixo")
        p1 = f.createIfcCartesianPoint((0.0, 0.0, 0.0))
        p2 = f.createIfcCartesianPoint((4.0, 0.0, 0.0))
        poly = f.createIfcPolyline([p1, p2])
        cset = f.createIfcGeometricCurveSet([poly])
        rep_a = f.createIfcShapeRepresentation(annot_ctx, "Annotation", rep_type_anotacao, [cset])
        proxy_anot.Representation = f.createIfcProductDefinitionShape(Representations=[rep_a])
        api("geometry.edit_object_placement", f, product=proxy_anot, matrix=np.eye(4), is_si=False)
        contidos.append(proxy_anot)

    proxy_solido = None
    if com_proxy_solido:
        proxy_solido = _caixa(f, body, "IfcBuildingElementProxy", 0.6, 0.6, 2.8, (6.0, 0.5, 0.0))
        proxy_solido.Name = "Pilar Proxy Solido"
        contidos.append(proxy_solido)
        solidos.append(proxy_solido)

    proxy_misto = None
    if com_proxy_misto:
        proxy_misto = _caixa(f, body, "IfcBuildingElementProxy", 0.6, 0.6, 2.8, (8.0, 0.5, 0.0))
        proxy_misto.Name = "Proxy Misto Corpo + Curva"
        p1 = f.createIfcCartesianPoint((0.0, 0.0, 0.0))
        p2 = f.createIfcCartesianPoint((0.6, 0.0, 0.0))
        cset_m = f.createIfcGeometricCurveSet([f.createIfcPolyline([p1, p2])])
        rep_m = f.createIfcShapeRepresentation(annot_ctx, "Annotation", "GeometricSet", [cset_m])
        proxy_misto.Representation.Representations = list(proxy_misto.Representation.Representations) + [rep_m]
        contidos.append(proxy_misto)
        solidos.append(proxy_misto)

    api("spatial.assign_container", f, products=contidos, relating_structure=andar)

    arq = pasta_base / "planta.ifc"
    f.write(str(arq))
    f2 = ifcopenshell.open(str(arq))
    resolver = lambda e: f2.by_guid(e.GlobalId) if e is not None else None
    andar, parede, abertura = resolver(andar), resolver(parede), resolver(abertura)
    laje, movel = resolver(laje), resolver(movel)
    proxy_anot, proxy_solido, proxy_misto = resolver(proxy_anot), resolver(proxy_solido), resolver(proxy_misto)
    solidos_f = [resolver(e) for e in solidos]

    pasta_cache = pasta_base / "cache_geo"
    doc = construtor.documento_de(arq)
    with construtor.abrir_banco(pasta_cache) as cache:
        r = construtor.construir_lote(f2, cache, construtor.fila_inicial(f2), documento=doc, assinatura="s1", memo={})
        assert r["gravadas"] == len(solidos_f)

    todos = [parede, abertura, laje, movel]
    for extra in (proxy_anot, proxy_solido, proxy_misto):
        if extra is not None:
            todos.append(extra)
    vista = {"tipo": "PLANTA", "pavimento": andar.GlobalId, "escala": 1.0, "altura_corte_m": 1.2}
    pedido_base = {"arquivo": str(arq), "vista": vista, "elementos": [(e.id(), e.GlobalId) for e in todos], "threads": 1}
    return SimpleNamespace(
        arq=arq,
        pasta=pasta_cache,
        f=f2,
        andar=andar,
        parede=parede,
        abertura=abertura,
        laje=laje,
        movel=movel,
        proxy_anot=proxy_anot,
        proxy_solido=proxy_solido,
        proxy_misto=proxy_misto,
        solidos=solidos_f,
        guids={
            "andar": andar.GlobalId,
            "parede": parede.GlobalId,
            "abertura": abertura.GlobalId,
            "laje": laje.GlobalId,
            "movel": movel.GlobalId,
        },
        pedido_base=pedido_base,
        pedido_cache={**pedido_base, "pasta_cache_geometria": str(pasta_cache)},
    )


# ---------- SANIDADE (PASSA HOJE) ----------
def test_sanidade_malhas_sinteticas_t24s():
    """Confirma que cada malha sintetica ativa exatamente a condicao geometrica alvo."""
    v_ab, t_ab, segs = corte_plano.cortar_malha_no_plano(*_malha_com_vao_np(), 1.2)
    assert len(segs) == 0 and len(t_ab) == 12 and float(v_ab[:, 2].max()) < 1.2

    _, t_ab2, segs2 = corte_plano.cortar_malha_no_plano(*_malha_toda_abaixo_bbox_cruza_np(), 1.2)
    assert len(segs2) == 0 and len(t_ab2) == 12

    _, t_ab3, segs3 = corte_plano.cortar_malha_no_plano(*_malha_toda_acima_bbox_cruza_np(), 1.2)
    assert len(segs3) == 0 and len(t_ab3) == 0

    _, _, segs4 = corte_plano.cortar_malha_no_plano(*_malha_segs_sem_anel_np(), 1.2)
    assert len(segs4) > 0 and aneis.aneis_de_segmentos(segs4) == ([], [])

    _, _, segs5 = corte_plano.cortar_malha_no_plano(*_malha_bom_mais_area_zero_np(), 1.2)
    fech5, ab5 = aneis.aneis_de_segmentos(segs5)
    assert len(fech5) == 2 and ab5 == []
    areas5 = sorted(abs(aneis._area(a)) for a in fech5)
    assert areas5[0] <= 1e-12 and areas5[1] > 1.0
    assert oclusores._agrupar_aneis(fech5) is None


# ---------- (1) ACEITACAO A: CORTE VAZIO (FALHA HOJE) ----------
def test_aceitacao_a_malha_com_vao_projeta_abaixo_ignora_acima_e_boas_inalteradas():
    """4 boas + 1 peca com vao: aceita, abaixo projeta, acima nao, boas identicas, parciais inalterado."""
    boas = [*_boas(4), (14, "G_LAJE", "IfcSlab", _caixa_np(0.0, -0.5, -0.2, 14.5, 2.0, 0.0))]
    r_base, mot_base = planta_cache.desenhar_planta_cache(*_montar_cena_numpy(boas, altura_corte_m=1.2, pav_guid="PAV_A"))
    assert mot_base is None and r_base is not None and r_base["secoes_parciais"] == 0
    parsed_base = _parse_svg(r_base["svg"])

    vao = _malha_com_vao_np(x_ab=(20.0, 22.0), y_ab=(0.0, 1.0), x_ac=(26.0, 28.0), y_ac=(0.0, 1.0))
    resp, motivo = planta_cache.desenhar_planta_cache(
        *_montar_cena_numpy([*boas, (20, "G_VAO", "IfcFlowTerminal", vao)], altura_corte_m=1.2, pav_guid="PAV_A")
    )
    assert motivo is None and resp is not None and resp["ok"] is True
    assert type(resp["secoes_parciais"]) is int and resp["secoes_parciais"] == 0
    assert 20 in resp["enviados"] and "-0.000000" not in resp["svg"]

    parsed = _parse_svg(resp["svg"])
    assert "G_VAO" not in parsed.cut_by_guid
    assert set(parsed.cut_by_guid.keys()) == {"G_BOA_0", "G_BOA_1", "G_BOA_2", "G_BOA_3"}
    for gid in ("G_BOA_0", "G_BOA_1", "G_BOA_2", "G_BOA_3"):
        assert _xml_grupos(parsed, gid) == _xml_grupos(parsed_base, gid), f"peca boa {gid} alterada"

    segs_proj = _polilinhas_para_segs(_polilinhas_mundo(parsed.proj_groups))
    assert float(_dist_pontos_a_segs(_contorno_retangulo_pts(20.0, 0.0, 22.0, 1.0), segs_proj).max()) <= 1e-3
    assert float(_pontos_de_segs(segs_proj)[:, 0].max()) < 24.0, "componente acima entrou na projecao"

    # Com 1 parcial pre-existente (T24f), adicionar peca com vao mantem secoes_parciais == 1
    boas_com_parcial = [*_boas(3), (13, "G_PARCIAL", "IfcWall", _caixas_fundidas_em_t_np(14.0, 0.0))]
    r_p, mot_p = planta_cache.desenhar_planta_cache(
        *_montar_cena_numpy([*boas_com_parcial, (20, "G_VAO", "IfcFlowTerminal", vao)], altura_corte_m=1.2)
    )
    assert mot_p is None and r_p is not None and r_p["secoes_parciais"] == 1
    estilo.aplicar_estilo(resp["svg"], "1:50")


def test_aceitacao_a_toda_abaixo_e_toda_acima_com_bbox_cruzando_plano():
    """Bbox cruza z_ef com 0 triangulos cruzando: toda abaixo projeta; toda acima nao entra."""
    boas = _boas(4)
    r_base, mot_base = planta_cache.desenhar_planta_cache(*_montar_cena_numpy(boas, altura_corte_m=1.2, pav_guid="PAV_A2"))
    assert mot_base is None and r_base is not None
    parsed_base = _parse_svg(r_base["svg"])

    # Toda abaixo (vertice orfao acima)
    r_ab, mot_ab = planta_cache.desenhar_planta_cache(
        *_montar_cena_numpy(
            [*boas, (21, "G_SO_ABAIXO", "IfcFurnishingElement", _malha_toda_abaixo_bbox_cruza_np(20.0, 0.0, 22.0, 1.0))],
            altura_corte_m=1.2,
            pav_guid="PAV_A2",
        )
    )
    assert mot_ab is None and r_ab is not None and r_ab["secoes_parciais"] == 0
    assert 21 in r_ab["enviados"]
    parsed_ab = _parse_svg(r_ab["svg"])
    assert "G_SO_ABAIXO" not in parsed_ab.cut_by_guid
    for gid in ("G_BOA_0", "G_BOA_1", "G_BOA_2", "G_BOA_3"):
        assert _xml_grupos(parsed_ab, gid) == _xml_grupos(parsed_base, gid)
    segs_ab = _polilinhas_para_segs(_polilinhas_mundo(parsed_ab.proj_groups))
    assert float(_dist_pontos_a_segs(_contorno_retangulo_pts(20.0, 0.0, 22.0, 1.0), segs_ab).max()) <= 1e-3

    # Toda acima (vertice orfao abaixo): nao entra na projecao, nao entra em enviados, SVG identico a base
    r_ac, mot_ac = planta_cache.desenhar_planta_cache(
        *_montar_cena_numpy(
            [*boas, (22, "G_SO_ACIMA", "IfcBeam", _malha_toda_acima_bbox_cruza_np(26.0, 0.0, 28.0, 1.0))],
            altura_corte_m=1.2,
            pav_guid="PAV_A2",
        )
    )
    assert mot_ac is None and r_ac is not None and r_ac["secoes_parciais"] == 0
    assert 22 not in r_ac["enviados"]
    assert r_ac["svg"] == r_base["svg"]
