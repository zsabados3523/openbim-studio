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
from test_s06_t24f_secao_tolerante_oraculo import (
    _caixa_np,
    _caixas_fundidas_em_t_np,
    _dist_pontos_a_segs,
    _extrair_polilinhas_d,
    _montar_cena_numpy,
    _parse_svg,
    _polilinhas_mundo,
    _polilinhas_para_segs,
    _pontos_de_segs,
    _sha256,
    _transladar_malha,
)
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


def test_aceitacao_a_corte_vazio_nao_gera_tampa_e_nao_infla_denominador_25(monkeypatch):
    """Peca com corte vazio nao adiciona grupo de tampa nem infla n_cortadas do limite de 25%."""
    grupos_passados: list[list] = []
    real_recorte = recorte.recortar_fora_dos_aneis
    monkeypatch.setattr(
        recorte,
        "recortar_fora_dos_aneis",
        lambda pols, grupos, *a, **k: (grupos_passados.append(list(grupos)), real_recorte(pols, grupos, *a, **k))[1],
    )
    pecas = [
        *_boas(4),
        (20, "G_VAO", "IfcFlowTerminal", _malha_com_vao_np(x_ab=(20.0, 22.0), y_ab=(0.0, 1.0))),
        (21, "G_LAJE", "IfcSlab", _caixa_np(0.0, -0.5, -0.2, 23.0, 2.0, 0.0)),
    ]
    resp, motivo = planta_cache.desenhar_planta_cache(*_montar_cena_numpy(pecas, altura_corte_m=1.2))
    assert motivo is None and resp is not None and resp["secoes_parciais"] == 0
    assert len(grupos_passados) == 1 and len(grupos_passados[0]) == 4

    # 2 cortadas parciais (100% > 25%) + 10 pecas com corte vazio -> continua caindo (nao infla denominador)
    pecas_lim = [
        (10, "G_P0", "IfcWall", _caixas_fundidas_em_t_np(0.0, 0.0)),
        (11, "G_P1", "IfcWall", _caixas_fundidas_em_t_np(5.0, 0.0)),
        *[(20 + i, f"G_VAO_{i:02d}", "IfcFlowTerminal", _malha_com_vao_np(x_ab=(20.0 + 3.0 * i, 21.0 + 3.0 * i), x_ac=(20.0 + 3.0 * i, 21.0 + 3.0 * i))) for i in range(10)],
    ]
    assert planta_cache.desenhar_planta_cache(*_montar_cena_numpy(pecas_lim, altura_corte_m=1.2)) == (None, "secao_aberta")


# ---------- (2) ACEITACAO C: ELEMENTO SO-ANOTACAO (FALHA HOJE) ----------
@pytest.mark.parametrize("rep_type", ["GeometricSet", "GeometricCurveSet"])
def test_aceitacao_c_proxy_so_anotacao_filtrado_via_cache_e_svg_identico(tmp_path, rep_type: str):
    """IfcBuildingElementProxy so com IfcGeometricCurveSet e filtrado em _elementos_validos_cache."""
    cena_sem = _criar_cena_ifc_c(tmp_path, subdir=f"sem_{rep_type}", com_proxy_anotacao=False)
    cena_com = _criar_cena_ifc_c(
        tmp_path,
        subdir=f"com_{rep_type}",
        com_proxy_anotacao=True,
        rep_type_anotacao=rep_type,
        guids_fixos=cena_sem.guids,
    )

    ev_com = desenho._elementos_validos_cache(cena_com.f, cena_com.pedido_cache)
    assert cena_com.proxy_anot.GlobalId not in {g for _, g in ev_com}
    assert {g for _, g in ev_com} == {e.GlobalId for e in cena_com.solidos}

    r_sem = desenho.processar(cena_sem.pedido_cache)
    r_com = desenho.processar(cena_com.pedido_cache)
    _checar_telemetria(r_sem, via_cache=True, queda=None, n_faltantes=0)
    _checar_telemetria(r_com, via_cache=True, queda=None, n_faltantes=0)
    assert r_com["svg"] == r_sem["svg"]
    assert r_com["n_paths"] == r_sem["n_paths"]
    assert r_com["secoes_parciais"] == r_sem["secoes_parciais"] == 0
    assert len(r_com["enviados"]) == len(r_sem["enviados"])


# ---------- (3) ACEITACAO E: ANEL FECHADO DE AREA ~0 (FALHA HOJE) ----------
def test_aceitacao_e_bom_mais_area_zero_tampa_ok_sem_linha_degenerada_e_parciais_zero(monkeypatch):
    """Peca com 1 anel bom + 1 anel de area ~0: bom na tampa, sem linha do degenerado, secoes_parciais=0."""
    grupos_passados: list[list] = []
    real_recorte = recorte.recortar_fora_dos_aneis
    monkeypatch.setattr(
        recorte,
        "recortar_fora_dos_aneis",
        lambda pols, grupos, *a, **k: (grupos_passados.append(list(grupos)), real_recorte(pols, grupos, *a, **k))[1],
    )
    boas3 = _boas(3)
    barras = [
        (14, "G_BARRA_BOM", "IfcSlab", _caixa_np(12.9, -0.5, 0.0, 13.1, 1.5, 0.2)),
        (15, "G_BARRA_DEG", "IfcSlab", _caixa_np(16.4, -0.5, 0.0, 16.6, 1.5, 0.2)),
    ]
    ref_pecas = [*boas3, (13, "G_ALVO", "IfcDoor", _caixa_np(12.0, 0.0, 0.0, 14.0, 1.0, 2.8)), *barras]
    r_ref, mot_ref = planta_cache.desenhar_planta_cache(*_montar_cena_numpy(ref_pecas, altura_corte_m=1.2, pav_guid="PAV_E"))
    assert mot_ref is None and r_ref is not None and r_ref["secoes_parciais"] == 0
    parsed_ref = _parse_svg(r_ref["svg"])
    grupos_passados.clear()

    mista = _malha_bom_mais_area_zero_np(12.0, 0.0, dx_deg=4.0, dy_deg=0.0)
    resp, motivo = planta_cache.desenhar_planta_cache(
        *_montar_cena_numpy([*boas3, (13, "G_ALVO", "IfcDoor", mista), *barras], altura_corte_m=1.2, pav_guid="PAV_E")
    )
    assert motivo is None and resp is not None and resp["ok"] is True
    assert type(resp["secoes_parciais"]) is int and resp["secoes_parciais"] == 0
    assert len(grupos_passados) == 1 and len(grupos_passados[0]) == 4
    for rings in grupos_passados[0]:
        for anel in rings:
            assert abs(aneis._area(anel)) > 1e-12 and float(np.asarray(anel)[:, 0].max()) < 15.0

    parsed = _parse_svg(resp["svg"])
    assert _xml_grupos(parsed, "G_ALVO") == _xml_grupos(parsed_ref, "G_ALVO"), "degenerado alterou secao do anel bom"
    for gid in ("G_BOA_0", "G_BOA_1", "G_BOA_2"):
        assert _xml_grupos(parsed, gid) == _xml_grupos(parsed_ref, gid)

    pls_alvo = _polilinhas_mundo(parsed.cut_by_guid["G_ALVO"])
    assert len(pls_alvo) == 1 and float(pls_alvo[0][:, 0].max()) < 15.0, "linha do degenerado apareceu na secao"

    segs_proj = _polilinhas_para_segs(_polilinhas_mundo(parsed.proj_groups))
    assert float(_dist_pontos_a_segs(np.array([[12.9, 0.5], [13.1, 0.5]]), segs_proj).min()) > 0.05, "anel bom nao tampou"
    assert float(_dist_pontos_a_segs(np.array([[16.4, 0.05], [16.6, 0.05]]), segs_proj).max()) <= 1e-3, "degenerado tampou piso"


def test_aceitacao_e_duas_pecas_bom_mais_area_zero_em_4_aceitas_com_parciais_zero():
    """2 boas + 2 com (anel bom + area zero): antes estourava 25%, com E aceita com secoes_parciais=0."""
    pecas = [
        *_boas(2),
        (12, "G_E0", "IfcFurniture", _malha_bom_mais_area_zero_np(10.0, 0.0, dx_deg=3.0)),
        (13, "G_E1", "IfcDoor", _malha_bom_mais_area_zero_np(18.0, 0.0, dx_deg=3.0)),
    ]
    resp, motivo = planta_cache.desenhar_planta_cache(*_montar_cena_numpy(pecas, altura_corte_m=1.2))
    assert motivo is None and resp is not None and resp["ok"] is True
    assert resp["secoes_parciais"] == 0
    assert set(_parse_svg(resp["svg"]).cut_by_guid.keys()) == {"G_BOA_0", "G_BOA_1", "G_E0", "G_E1"}


def test_aceitacao_determinismo_sha256_3_rodadas_e_imutabilidade_a_e_utm():
    """Cena combinando A (vao) + E (bom+area zero) em UTM: SHA-256 deterministico e malhas_mundo intacto."""
    ox, oy = 500_000.25, 7_500_000.75
    base = [
        *_boas(4),
        (20, "G_VAO", "IfcFlowTerminal", _malha_com_vao_np(x_ab=(20.0, 22.0), x_ac=(26.0, 28.0))),
        (21, "G_E_MISTA", "IfcDoor", _malha_bom_mais_area_zero_np(30.0, 0.0, dx_deg=3.5)),
        (22, "G_LAJE", "IfcSlab", _caixa_np(0.0, -0.5, -0.2, 36.0, 2.0, 0.0)),
    ]
    pecas_utm = [(i, g, c, _transladar_malha(m, ox, oy)) for i, g, c, m in base]
    f, ped, malhas, ev = _montar_cena_numpy(pecas_utm, altura_corte_m=1.2, threads=1)
    snap = _congelar_snapshot(malhas, ped)
    shas = []
    for _ in range(3):
        r, mot = planta_cache.desenhar_planta_cache(f, ped, malhas, ev)
        assert mot is None and r is not None and r["secoes_parciais"] == 0
        shas.append(_sha256(r["svg"]))
    assert shas[0] == shas[1] == shas[2]
    _checar_imutavel(malhas, ped, *snap)

    r_rev, mot_rev = planta_cache.desenhar_planta_cache(*_montar_cena_numpy(list(reversed(pecas_utm)), altura_corte_m=1.2, threads=1))
    assert mot_rev is None and _sha256(r_rev["svg"]) == shas[0]
    r_t4, mot_t4 = planta_cache.desenhar_planta_cache(*_montar_cena_numpy(pecas_utm, altura_corte_m=1.2, threads=4))
    assert mot_t4 is None and _sha256(r_t4["svg"]) == shas[0]


# ---------- (3b) CONTRATO E2 + (4) NAO-REGRESSAO (PASSAM HOJE) ----------
def test_contrato_e2_peca_so_com_aneis_area_zero_vira_linha_e_parcial_1():
    """Decisao E2: sem anel bom, aneis de area ~0 viram cadeias/linhas fora da tampa e contam 1 parcial."""
    boas3 = _boas(3)
    dois_deg = _combinar_malhas(
        _malha_anel_area_quase_zero_np(14.0, 0.0),
        _malha_anel_bowtie_area_zero_np(16.0, 0.0),
    )
    resp, motivo = planta_cache.desenhar_planta_cache(
        *_montar_cena_numpy([*boas3, (13, "G_SO_DEG", "IfcDoor", dois_deg)], altura_corte_m=1.2)
    )
    assert motivo is None and resp is not None and resp["ok"] is True
    assert type(resp["secoes_parciais"]) is int and resp["secoes_parciais"] == 1
    _verificar_linhas_peca_ruim(_parse_svg(resp["svg"]), "G_SO_DEG", dois_deg, 1.2)


def test_nao_regressao_a_peca_com_segs_sem_anel_segue_queda_secao_aberta():
    """Peca com segmentos de corte que nao formam nenhum anel/cadeia mantem queda secao_aberta."""
    pecas = [*_boas(4), (99, "G_SEGS_SEM_ANEL", "IfcWall", _malha_segs_sem_anel_np(24.0, 0.0))]
    assert planta_cache.desenhar_planta_cache(*_montar_cena_numpy(pecas, altura_corte_m=1.2)) == (None, "secao_aberta")


def test_nao_regressao_c_elementos_solido_e_misto_nao_sao_filtrados(tmp_path):
    """IfcBuildingElementProxy solido e proxy misto (Body + Annotation) nunca sao filtrados."""
    cena = _criar_cena_ifc_c(tmp_path, subdir="solido_misto", com_proxy_anotacao=False, com_proxy_solido=True, com_proxy_misto=True)
    ev = desenho._elementos_validos_cache(cena.f, cena.pedido_cache)
    gids_ev = {g for _, g in ev}
    assert cena.proxy_solido.GlobalId in gids_ev
    assert cena.proxy_misto.GlobalId in gids_ev

    r_ok = desenho.processar(cena.pedido_cache)
    _checar_telemetria(r_ok, via_cache=True, queda=None, n_faltantes=0)
    parsed = _parse_svg(r_ok["svg"])
    assert cena.proxy_solido.GlobalId in parsed.cut_by_guid
    assert cena.proxy_misto.GlobalId in parsed.cut_by_guid

    # Apagar o proxy solido do cache deve acusar cache_incompleto (prova que nao foi filtrado)
    _sql(cena.pasta, "DELETE FROM ocorrencias WHERE global_id = ?", (cena.proxy_solido.GlobalId,))
    r_falta = desenho.processar(cena.pedido_cache)
    _checar_telemetria(r_falta, via_cache=False, queda="cache_incompleto", n_faltantes=1)


def test_nao_regressao_pecas_boas_identicas_byte_a_byte():
    """Cena so com pecas boas (caixas + moldura furada + bloco no furo + laje + viga) identica byte a byte."""
    ext = [(10.0, 0.0), (12.0, 0.0), (12.0, 2.0), (10.0, 2.0)]
    furo = [(10.5, 0.5), (11.5, 0.5), (11.5, 1.5), (10.5, 1.5)]
    pecas = [
        *_boas(2),
        (12, "G_MOLDURA", "IfcWall", _tubo_np(ext, furo, 0.0, 2.8)),
        (13, "G_BLOCO", "IfcFurnishingElement", _caixa_np(10.8, 0.8, 0.0, 11.2, 1.2, 0.6)),
        (14, "G_LAJE", "IfcSlab", _caixa_np(0.0, -0.5, -0.2, 13.0, 2.5, 0.0)),
        (15, "G_VIGA_ACIMA", "IfcBeam", _caixa_np(0.0, 0.0, 2.2, 3.0, 0.3, 2.8)),
    ]
    f, ped, malhas, ev = _montar_cena_numpy(pecas, altura_corte_m=1.2, pav_guid="PAV_NR")
    svg_ref, n_paths_ref, env_ref = _svg_referencia_boas(f, ped, malhas, ev)
    resp, mot = planta_cache.desenhar_planta_cache(f, ped, malhas, ev)
    assert mot is None and resp is not None and resp["secoes_parciais"] == 0
    assert resp["svg"] == svg_ref and resp["n_paths"] == n_paths_ref and resp["enviados"] == env_ref


def test_nao_regressao_limite_25_porcento_intacto():
    """Limite ceil(0.25 * n_cortadas) permanece intacto (1/4 aceita, 2/4 cai)."""
    c1 = [*_boas(3), (13, "G_P0", "IfcWall", _caixas_fundidas_em_t_np(14.0, 0.0))]
    r1, mot1 = planta_cache.desenhar_planta_cache(*_montar_cena_numpy(c1, altura_corte_m=1.2))
    assert mot1 is None and r1 is not None and r1["secoes_parciais"] == 1

    c2 = [*_boas(2), (12, "G_P0", "IfcWall", _caixas_fundidas_em_t_np(10.0, 0.0)), (13, "G_P1", "IfcDoor", _malha_anel_area_quase_zero_np(16.0, 0.0))]
    assert planta_cache.desenhar_planta_cache(*_montar_cena_numpy(c2, altura_corte_m=1.2)) == (None, "secao_aberta")


def test_nao_regressao_determinismo_sha256_3_rodadas_e_nao_muta_malhas_mundo():
    """SHA-256 identico em 3 rodadas e malhas_mundo (read-only) intacto na cena base."""
    pecas = [
        *_boas(4),
        (14, "G_P0", "IfcDoor", _malha_anel_area_quase_zero_np(20.0, 0.0)),
        (15, "G_LAJE", "IfcSlab", _caixa_np(0.0, -0.5, -0.2, 22.0, 2.0, 0.0)),
    ]
    f, ped, malhas, ev = _montar_cena_numpy(pecas, altura_corte_m=1.2, threads=1)
    snap = _congelar_snapshot(malhas, ped)
    shas = []
    for _ in range(3):
        r, mot = planta_cache.desenhar_planta_cache(f, ped, malhas, ev)
        assert mot is None and r is not None and r["secoes_parciais"] == 1
        shas.append(_sha256(r["svg"]))
    assert shas[0] == shas[1] == shas[2]
    _checar_imutavel(malhas, ped, *snap)


# ---------- (5) MUTANTES (FALHAM HOJE) ----------
def test_mutante_01_peca_abaixo_some_da_projecao():
    """Mutante 1: dar `continue` em corte vazio sem enviar `(v_ab, t_ab)` faz a parte abaixo sumir da projecao."""
    vao = _malha_com_vao_np(x_ab=(20.0, 22.0), y_ab=(0.0, 1.0), x_ac=(26.0, 28.0), y_ac=(0.0, 1.0))
    resp, motivo = planta_cache.desenhar_planta_cache(
        *_montar_cena_numpy([*_boas(4), (20, "G_VAO_AB", "IfcFlowTerminal", vao)], altura_corte_m=1.2)
    )
    assert motivo is None and resp is not None and 20 in resp["enviados"]
    segs_proj = _polilinhas_para_segs(_polilinhas_mundo(_parse_svg(resp["svg"]).proj_groups))
    assert len(segs_proj) >= 4, "projecao da parte abaixo sumiu"
    assert float(_dist_pontos_a_segs(_contorno_retangulo_pts(20.0, 0.0, 22.0, 1.0), segs_proj).max()) <= 1e-3


def test_mutante_02_peca_acima_entra_na_projecao():
    """Mutante 2: enviar malha inteira `(v, t)` em vez de `(v_ab, t_ab)` faz parte acima entrar na projecao."""
    pecas = [
        *_boas(4),
        (20, "G_VAO", "IfcFlowTerminal", _malha_com_vao_np(x_ab=(20.0, 22.0), x_ac=(28.0, 30.0))),
        (21, "G_SO_ACIMA", "IfcBeam", _malha_toda_acima_bbox_cruza_np(35.0, 0.0, 37.0, 1.0)),
    ]
    resp, motivo = planta_cache.desenhar_planta_cache(*_montar_cena_numpy(pecas, altura_corte_m=1.2))
    assert motivo is None and resp is not None
    assert 21 not in resp["enviados"], "peca toda acima entrou em enviados"
    segs_proj = _polilinhas_para_segs(_polilinhas_mundo(_parse_svg(resp["svg"]).proj_groups))
    assert len(segs_proj) > 0
    assert float(_pontos_de_segs(segs_proj)[:, 0].max()) < 24.0, "geometria acima do plano vazou para a projecao"


def test_mutante_03_corte_vazio_conta_como_parcial():
    """Mutante 3: contar pecas de corte vazio em `secoes_parciais` estouraria 25% ou daria parciais > 0."""
    pecas = [
        *_boas(2),
        (20, "G_V0", "IfcFlowTerminal", _malha_com_vao_np(x_ab=(12.0, 13.0), x_ac=(12.0, 13.0))),
        (21, "G_V1", "IfcFlowTerminal", _malha_com_vao_np(x_ab=(15.0, 16.0), x_ac=(15.0, 16.0))),
        (22, "G_V2", "IfcFlowTerminal", _malha_com_vao_np(x_ab=(18.0, 19.0), x_ac=(18.0, 19.0))),
    ]
    resp, motivo = planta_cache.desenhar_planta_cache(*_montar_cena_numpy(pecas, altura_corte_m=1.2))
    assert motivo is None and resp is not None and resp["ok"] is True
    assert resp["secoes_parciais"] == 0, "corte vazio foi contado em secoes_parciais"


def test_mutante_04_filtro_anotacao_filtra_elemento_solido(tmp_path):
    """Mutante 4: filtro amplo demais (ex.: por classe Proxy ou por ter qualquer curva) remove solido."""
    cena = _criar_cena_ifc_c(
        tmp_path, subdir="mut4", com_proxy_anotacao=True, com_proxy_solido=True, com_proxy_misto=True
    )
    ev = desenho._elementos_validos_cache(cena.f, cena.pedido_cache)
    gids_ev = {g for _, g in ev}
    assert cena.proxy_anot.GlobalId not in gids_ev, "proxy so-anotacao nao foi filtrado"
    assert cena.proxy_solido.GlobalId in gids_ev, "proxy solido foi filtrado por engano"
    assert cena.proxy_misto.GlobalId in gids_ev, "proxy misto (Body + Annotation) foi filtrado por engano"

    resp = desenho.processar(cena.pedido_cache)
    _checar_telemetria(resp, via_cache=True, queda=None, n_faltantes=0)
    parsed = _parse_svg(resp["svg"])
    assert cena.proxy_solido.GlobalId in parsed.cut_by_guid
    assert cena.proxy_misto.GlobalId in parsed.cut_by_guid
    assert cena.proxy_anot.GlobalId not in parsed.cut_by_guid


def test_mutante_05_anel_area_zero_entra_na_tampa(monkeypatch):
    """Mutante 5: passar o anel degenerado (|area| <= 1e-12) para `grupos_secao` ou desenha-lo."""
    grupos_passados: list[list] = []
    real_recorte = recorte.recortar_fora_dos_aneis
    monkeypatch.setattr(
        recorte,
        "recortar_fora_dos_aneis",
        lambda pols, grupos, *a, **k: (grupos_passados.append(list(grupos)), real_recorte(pols, grupos, *a, **k))[1],
    )
    pecas = [
        *_boas(3),
        (13, "G_MISTA_E", "IfcDoor", _malha_bom_mais_area_zero_np(12.0, 0.0, dx_deg=4.0)),
        (14, "G_BARRA_DEG", "IfcSlab", _caixa_np(16.4, -0.5, 0.0, 16.6, 1.5, 0.2)),
    ]
    resp, motivo = planta_cache.desenhar_planta_cache(*_montar_cena_numpy(pecas, altura_corte_m=1.2))
    assert motivo is None and resp is not None and resp["secoes_parciais"] == 0
    assert len(grupos_passados) == 1 and len(grupos_passados[0]) == 4
    for rings in grupos_passados[0]:
        for anel in rings:
            assert abs(aneis._area(anel)) > 1e-12, "anel de area zero entrou em grupos_secao"
            assert float(np.asarray(anel)[:, 0].max()) < 15.0, "anel degenerado entrou na tampa"


def test_mutante_06_anel_bom_ou_furo_descartado_junto_com_degenerado():
    """Mutante 6: descartar anel bom (ou furo de area negativa) junto com o anel de area zero."""
    pecas = [
        *_boas(2),
        (12, "G_MOLDURA_E", "IfcWall", _malha_tubo_mais_area_zero_np(10.0, 0.0, dx_deg=5.0)),
        (13, "G_BLOCO_NO_FURO", "IfcFurnishingElement", _caixa_np(10.8, 0.8, 0.0, 11.2, 1.2, 0.6)),
        (14, "G_BARRA_SOB_MOLD", "IfcSlab", _caixa_np(10.1, -0.5, 0.0, 10.4, 2.5, 0.2)),
    ]
    resp, motivo = planta_cache.desenhar_planta_cache(*_montar_cena_numpy(pecas, altura_corte_m=1.2))
    assert motivo is None and resp is not None and resp["ok"] is True
    assert resp["secoes_parciais"] == 0

    parsed = _parse_svg(resp["svg"])
    assert "G_MOLDURA_E" in parsed.cut_by_guid
    pls_mold = _polilinhas_mundo(parsed.cut_by_guid["G_MOLDURA_E"])
    # Deve preservar externo + furo (2 aneis fechados) e descartar o degenerado (x ~ 15..16)
    assert len(pls_mold) == 2, f"esperados 2 aneis (externo+furo), obtidos {len(pls_mold)}"
    for pl in pls_mold:
        assert float(pl[:, 0].max()) < 13.0, "anel degenerado nao foi descartado"
        assert np.allclose(pl[0], pl[-1], atol=1e-5), "anel bom/furo virou cadeia aberta"

    segs_proj = _polilinhas_para_segs(_polilinhas_mundo(parsed.proj_groups))
    # Parede da moldura tampa a barra sob ela (x=10.25, y=1.0)
    assert float(_dist_pontos_a_segs(np.array([[10.1, 1.0], [10.4, 1.0]]), segs_proj).min()) > 0.05, "anel bom nao tampou"
    # Furo negativo preservado: bloco dentro do furo (10.8..11.2 x 0.8..1.2) continua visivel na projecao
    assert float(_dist_pontos_a_segs(_contorno_retangulo_pts(10.8, 0.8, 11.2, 1.2), segs_proj).max()) <= 1e-3, "furo negativo foi descartado"
