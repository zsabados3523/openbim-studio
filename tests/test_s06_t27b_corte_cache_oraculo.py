# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oraculo F0-S06-T27b (parte 1/3): auxiliares, equivalencia e casos 1 a 3.

NAO editar este arquivo na implementacao. Partes 2 e 3 ficam em `_b.py` e `_c.py`.
Criterio de equivalencia (regra 5): mesmos `ifc:guid` e classes por grupo de tampa,
mesmo numero de `<path>` e `n_paths`, conjunto de segmentos de projecao e tampas
igual a <= 1e-5 por coordenada, e mesmos `motor_pecas`, `enviados`, `caixas` e
`falhas_geometria`.
"""
from __future__ import annotations

import math
import re
import sqlite3
import xml.etree.ElementTree as ET
from functools import reduce
from pathlib import Path
from types import SimpleNamespace

import ifcopenshell
import ifcopenshell.api
import numpy as np
import pytest
import shapely
import shapely.geometry as sg

from obim_geometria import cache_geometria as CG
from obim_geometria import caixas as geo_caixas
from obim_geometria import construtor, desenho, silhueta
from openbim_app import vistas_ifc
from openbim_app.desenho import selecao

NS_IFC = "{http://www.ifcopenshell.org/ns}"
_TOK_RE = re.compile(r"[-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?|[a-zA-Z]")
_TOL_SEG = 1e-5


# ---------------------------------------------------------------- helpers IFC sinteticos


def _novo_ifc_base():
    """Cria IFC4 minimo em metros com Project > Site > Building > Storey(Terreo)."""
    api = ifcopenshell.api.run
    f = api("project.create_file", version="IFC4")
    proj = api("root.create_entity", f, ifc_class="IfcProject", name="P_T27B")
    api("unit.assign_unit", f, units=[f.createIfcSIUnit(UnitType="LENGTHUNIT", Prefix=None, Name="METRE")])
    ctx = api("context.add_context", f, context_type="Model")
    body = api(
        "context.add_context", f, context_type="Model", context_identifier="Body", target_view="MODEL_VIEW", parent=ctx
    )
    site = api("root.create_entity", f, ifc_class="IfcSite", name="S")
    bld = api("root.create_entity", f, ifc_class="IfcBuilding", name="B")
    pav = api("root.create_entity", f, ifc_class="IfcBuildingStorey", name="Terreo")
    pav.Elevation = 0.0
    for filho, pai in ((site, proj), (bld, site), (pav, bld)):
        api("aggregate.assign_object", f, products=[filho], relating_object=pai)
    return f, body, pav


def _add_caixa(
    f,
    body,
    pav,
    classe: str,
    nome: str,
    pos: tuple[float, float, float],
    dim: tuple[float, float, float],
    *,
    conter: bool = True,
):
    """Cria caixa extrudada ocupando [x, x+dx] x [y, y+dy] x [z, z+dz]."""
    api = ifcopenshell.api.run
    el = api("root.create_entity", f, ifc_class=classe, name=nome)
    rep = api("geometry.add_wall_representation", f, context=body, length=dim[0], height=dim[2], thickness=dim[1])
    el.Representation = f.createIfcProductDefinitionShape(Representations=[rep])
    m = np.eye(4, dtype=np.float64)
    m[:3, 3] = pos
    api("geometry.edit_object_placement", f, product=el, matrix=m, is_si=False)
    if conter:
        api("spatial.assign_container", f, products=[el], relating_structure=pav)
    return el


def _add_vista_corte_ifc(
    f,
    nome: str = "C_T27B",
    origem: tuple[float, float, float] = (2.0, 0.0, 1.4),
    tamanho: tuple[float, float, float] = (8.0, 6.0, 6.0),
) -> str:
    """Grava IfcAnnotation de CORTE olhando +Y com bloco centrado em `origem`."""
    gid = vistas_ifc.criar_vista(f, nome, "CORTE", escala="1:50", origem=origem, tamanho=tamanho)
    eixo = f.by_guid(gid).ObjectPlacement.RelativePlacement
    eixo.Axis = f.create_entity("IfcDirection", DirectionRatios=(0.0, -1.0, 0.0))
    eixo.RefDirection = f.create_entity("IfcDirection", DirectionRatios=(1.0, 0.0, 0.0))
    bloco = f.by_guid(gid).Representation.Representations[0].Items[0].TreeRootExpression
    bloco.Position.Location.Coordinates = (-tamanho[0] / 2.0, -tamanho[1] / 2.0, -tamanho[2])
    return gid


def _matriz_vista(origem: tuple[float, float, float], angulo_graus: float = 0.0) -> list[list[float]]:
    """Matriz 4x4 de vista vertical: 0=olhando +Y, -90=olhando +X, 30=obliqua 30 graus."""
    rad = math.radians(angulo_graus)
    c, s = math.cos(rad), math.sin(rad)
    return [
        [c, 0.0, s, float(origem[0])],
        [s, 0.0, -c, float(origem[1])],
        [0.0, 1.0, 0.0, float(origem[2])],
        [0.0, 0.0, 0.0, 1.0],
    ]


def _pedido_corte(
    arq: Path,
    elementos: list,
    *,
    origem: tuple[float, float, float] = (3.0, 2.0, 1.5),
    angulo_graus: float = 0.0,
    largura: float = 12.0,
    altura: float = 8.0,
    prof_bloco: float = 10.0,
    profundidade_corte: float | None = None,
    caixas_coords: dict | None = None,
    pasta_cache: str | Path | None = None,
    motor_visivel: bool = True,
    extra: dict | None = None,
) -> dict:
    vista: dict = {
        "tipo": "CORTE",
        "guid": ifcopenshell.guid.new(),
        "nome": "C_T27B",
        "escala": 1.0,
        "matriz": _matriz_vista(origem, angulo_graus),
        "bloco": {
            "Location": [-largura / 2.0, -altura / 2.0, -prof_bloco],
            "XLength": float(largura),
            "YLength": float(altura),
            "ZLength": float(prof_bloco),
        },
    }
    if profundidade_corte is not None:
        vista["profundidade_corte"] = float(profundidade_corte)
    ped: dict = {
        "protocolo": 1,
        "op": "desenho",
        "arquivo": str(arq),
        "vista": vista,
        "elementos": [[int(e.id()), str(e.GlobalId)] for e in elementos],
        "threads": 1,
        "motor_visivel": motor_visivel,
    }
    if profundidade_corte is not None:
        ped["profundidade_corte"] = float(profundidade_corte)
    if caixas_coords is not None:
        ped["caixas_coords"] = {int(k): list(v) for k, v in caixas_coords.items()}
    if pasta_cache is not None:
        ped["pasta_cache_geometria"] = str(pasta_cache)
    if extra:
        ped.update(extra)
    return ped


def _salvar_e_construir(
    tmp_path: Path, f, *, nome: str = "cena.ifc", ids_cache: list[int] | None = None
) -> tuple[Path, Path, ifcopenshell.file]:
    arq = tmp_path / nome
    f.write(str(arq))
    f_lido = ifcopenshell.open(str(arq))
    pasta = tmp_path / f"cache_{arq.stem}"
    doc = construtor.documento_de(arq)
    alvo = construtor.fila_inicial(f_lido) if ids_cache is None else list(ids_cache)
    with construtor.abrir_banco(pasta) as db:
        construtor.construir_lote(f_lido, db, alvo, documento=doc, assinatura="s1", memo={})
    return arq, pasta, f_lido


def _sql(pasta: Path, consulta: str, args=()):
    con = sqlite3.connect(str(pasta / CG.NOME_BANCO))
    try:
        rows = con.execute(consulta, args).fetchall()
        con.commit()
        return rows
    finally:
        con.close()


def _cena_basica(tmp_path: Path) -> SimpleNamespace:
    """Casos 1 e 2: 6 paredes, 2 lajes, 1 pilar, 1 movel (sem aberturas), centro em (3, 2, 1.5)."""
    f, body, pav = _novo_ifc_base()
    espec = [
        ("IfcWall", "W1", (0.0, 0.0, 0.0), (6.0, 0.2, 3.0)),
        ("IfcWall", "W2", (0.0, 4.0, 0.0), (6.0, 0.2, 3.0)),
        ("IfcWall", "W3", (0.0, 0.2, 0.0), (0.2, 3.8, 3.0)),
        ("IfcWall", "W4", (5.8, 0.2, 0.0), (0.2, 3.8, 3.0)),
        ("IfcWall", "W5", (2.5, 0.2, 0.0), (0.2, 3.8, 3.0)),
        ("IfcWall", "W6", (2.7, 2.0, 0.0), (3.1, 0.2, 3.0)),
        ("IfcSlab", "L1", (0.0, 0.0, -0.2), (6.0, 4.2, 0.2)),
        ("IfcSlab", "L2", (0.0, 0.0, 3.0), (6.0, 4.2, 0.2)),
        ("IfcColumn", "P1", (1.2, 2.6, 0.0), (0.3, 0.3, 3.0)),
        ("IfcFurniture", "M1", (3.8, 2.8, 0.0), (1.0, 0.8, 0.75)),
    ]
    guids = {nome: _add_caixa(f, body, pav, cls, nome, pos, dim).GlobalId for cls, nome, pos, dim in espec}
    arq, pasta, f2 = _salvar_e_construir(tmp_path, f, nome="basica.ifc")
    els = {nome: f2.by_guid(g) for nome, g in guids.items()}
    return SimpleNamespace(arq=arq, pasta=pasta, f=f2, els=els, lista=list(els.values()))


# ---------------------------------------------------------------- parser SVG e equivalencia (regra 5)


def _segmentos_de_d(d: str) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    toks = _TOK_RE.findall(d or "")
    segs, atual, cmd, i = [], None, "", 0
    while i < len(toks):
        tok = toks[i]
        if tok.isalpha():
            cmd = tok.upper()
            i += 1
            continue
        if cmd in ("M", "L") and i + 1 < len(toks):
            p = (float(tok), float(toks[i + 1]))
            if cmd == "M" or atual is None:
                atual = p
            else:
                if math.dist(atual, p) > 1e-9:
                    segs.append((atual, p) if atual <= p else (p, atual))
                atual = p
            i += 2
        else:
            i += 1
    return segs


def _extrair_svg(svg: str) -> tuple[list, dict[str, tuple[str, list]], int]:
    """Extrai (segs_proj, {guid: (classe, segs)}, total_paths) validando XML."""
    raiz = ET.fromstring(svg)
    segs_proj: list = []
    grupos: dict[str, tuple[str, list]] = {}
    total_paths = 0
    for g in raiz.iter():
        if not g.tag.endswith("}g") and g.tag != "g":
            continue
        paths_diretos = [ch for ch in g if ch.tag.endswith("}path") or ch.tag == "path"]
        if not paths_diretos:
            continue
        total_paths += len(paths_diretos)
        cls, gid = g.get("class") or "", g.get(NS_IFC + "guid")
        segs = [s for p in paths_diretos for s in _segmentos_de_d(p.get("d") or "")]
        if cls == "projection" and not gid:
            segs_proj.extend(segs)
        elif gid:
            cls_ant, lista_ant = grupos.get(gid, (cls, []))
            grupos[gid] = (cls_ant or cls, lista_ant + segs)
    return segs_proj, grupos, total_paths


def _conjuntos_segs_iguais(a: list, b: list, tol: float = _TOL_SEG) -> bool:
    """Igualdade de conjuntos de segmentos ate `tol` por coordenada (sem artefato de borda)."""
    def _perto(s, t) -> bool:
        return (
            abs(s[0][0] - t[0][0]) <= tol
            and abs(s[0][1] - t[0][1]) <= tol
            and abs(s[1][0] - t[1][0]) <= tol
            and abs(s[1][1] - t[1][1]) <= tol
        )

    ua = []
    for s in a:
        if not any(_perto(s, u) for u in ua):
            ua.append(s)
    ub = []
    for s in b:
        if not any(_perto(s, u) for u in ub):
            ub.append(s)
    return all(any(_perto(s, t) for t in ub) for s in ua) and all(any(_perto(t, s) for s in ua) for t in ub)


def _assert_corte_equivalente(antigo: dict, novo: dict) -> None:
    assert antigo.get("ok") is True, antigo
    assert novo.get("ok") is True, novo
    assert novo["n_paths"] == antigo["n_paths"], f"n_paths: {novo['n_paths']} != {antigo['n_paths']}"
    assert sorted(novo["enviados"]) == sorted(antigo["enviados"])
    assert sorted(novo.get("motor_pecas", ())) == sorted(antigo.get("motor_pecas", ()))
    assert list(novo["caixas"]) == list(antigo["caixas"])
    assert sorted(novo["falhas_geometria"]) == sorted(antigo["falhas_geometria"])

    p_ant, g_ant, n_ant = _extrair_svg(antigo["svg"])
    p_nov, g_nov, n_nov = _extrair_svg(novo["svg"])
    assert n_nov == n_ant == novo["n_paths"]
    assert set(g_nov.keys()) == set(g_ant.keys()), f"guids diferem: {set(g_nov) ^ set(g_ant)}"
    for gid in g_ant:
        assert g_nov[gid][0] == g_ant[gid][0], f"classe de {gid}: {g_nov[gid][0]} != {g_ant[gid][0]}"
        assert _conjuntos_segs_iguais(g_ant[gid][1], g_nov[gid][1]), f"tampa de {gid} divergiu alem de 1e-5"
    assert _conjuntos_segs_iguais(p_ant, p_nov), "segmentos de projecao divergiram alem de 1e-5"


def _poligono_tampa(svg: str, gid: str):
    """Reconstroi poligono shapely (regra par-impar) da tampa de `gid` no SVG."""
    raiz = ET.fromstring(svg)
    pols = []
    for g in raiz.iter():
        if g.get(NS_IFC + "guid") != gid:
            continue
        for p in g:
            if not (p.tag.endswith("}path") or p.tag == "path"):
                continue
            for sub in (p.get("d") or "").split("M")[1:]:
                pts = [
                    (float(x), float(y))
                    for x, y in re.findall(r"(-?[\d.]+(?:e[-+]?\d+)?),(-?[\d.]+(?:e[-+]?\d+)?)", sub)
                ]
                if len(pts) >= 3:
                    pols.append(shapely.make_valid(sg.Polygon(pts)))
    assert pols, f"tampa ausente para {gid}"
    return reduce(lambda a, b: a.symmetric_difference(b), pols)


# ---------------------------------------------------------------- controle atual e casos 1 a 4


def test_sem_pasta_cache_comportamento_atual_intacto(tmp_path, monkeypatch):
    """Controle: sem pasta_cache_geometria, corte atual roda e usa silhueta.formas_do_mundo."""
    cena = _cena_basica(tmp_path)
    chamadas = []
    real_formas = silhueta.formas_do_mundo
    monkeypatch.setattr(
        silhueta, "formas_do_mundo", lambda f, els, **k: (chamadas.append(len(els)), real_formas(f, els, **k))[1]
    )
    r = desenho.processar(_pedido_corte(cena.arq, cena.lista))
    assert r["ok"] is True and r["n_paths"] > 0
    assert len(r["motor_pecas"]) == len(cena.lista)
    assert chamadas == [len(cena.lista)]


def test_caso01_equivalencia_basica(tmp_path):
    """Caso 1: 6 paredes, 2 lajes, 1 pilar, 1 movel, plano Y no centro."""
    cena = _cena_basica(tmp_path)
    antigo = desenho.processar(_pedido_corte(cena.arq, cena.lista))
    novo = desenho.processar(_pedido_corte(cena.arq, cena.lista, pasta_cache=cena.pasta))
    _assert_corte_equivalente(antigo, novo)
    assert novo["n_pecas_cache"] == len(novo["motor_pecas"]) == len(cena.lista)
    assert novo["n_pecas_fallback"] == 0
    assert novo["queda_corte"] is None


@pytest.mark.parametrize("angulo", [0.0, -90.0, 30.0])
@pytest.mark.parametrize("prof", [None, 2.0])
def test_caso02_equivalencia_varias_vistas(tmp_path, angulo, prof):
    """Caso 2: mesma cena em planos Y, X e obliquo 30 graus, profundidade None e 2.0 m."""
    cena = _cena_basica(tmp_path)
    kw = {"origem": (3.0, 2.0, 1.5), "angulo_graus": angulo, "profundidade_corte": prof}
    antigo = desenho.processar(_pedido_corte(cena.arq, cena.lista, **kw))
    novo = desenho.processar(_pedido_corte(cena.arq, cena.lista, pasta_cache=cena.pasta, **kw))
    _assert_corte_equivalente(antigo, novo)
    assert novo["n_pecas_cache"] == len(novo["motor_pecas"]) > 0
    assert novo["n_pecas_fallback"] == 0
    assert novo["queda_corte"] is None


def test_caso03_pecas_fora_da_janela_e_da_profundidade(tmp_path):
    """Caso 3: peca atras da profundidade sai na selecao; peca fora da janela e podada antes do cache."""
    f, body, pav = _novo_ifc_base()
    dentro = _add_caixa(f, body, pav, "IfcWall", "Dentro", (0.0, -0.5, 0.0), (2.0, 1.0, 2.5))
    fora_lat = _add_caixa(f, body, pav, "IfcWall", "ForaLateral", (30.0, -0.5, 0.0), (1.0, 1.0, 2.5))
    atras_prof = _add_caixa(f, body, pav, "IfcWall", "AtrasProf", (0.0, 8.0, 0.0), (2.0, 0.5, 2.5))
    gid_v = _add_vista_corte_ifc(f, "C_FORA", origem=(1.0, 0.0, 1.25), tamanho=(6.0, 6.0, 3.0))
    # So `dentro` entra no cache; `fora_lat` e podada por _na_janela antes de ler o cache
    arq, pasta, f2 = _salvar_e_construir(tmp_path, f, nome="fora.ifc", ids_cache=[dentro.id()])
    e_in, e_lat, e_prof = f2.by_guid(dentro.GlobalId), f2.by_guid(fora_lat.GlobalId), f2.by_guid(atras_prof.GlobalId)

    sel = selecao.selecionar(f2, gid_v, profundidade_corte=3.0, executor=geo_caixas.processar)
    assert e_in.id() in sel.ids and e_prof.id() not in sel.ids

    caixas = {e_in.id(): [0.0, -0.5, 0.0, 2.0, 0.5, 2.5], e_lat.id(): [30.0, -0.5, 0.0, 31.0, 0.5, 2.5]}
    kw = {"origem": (1.0, 0.0, 1.25), "largura": 6.0, "altura": 6.0, "profundidade_corte": 3.0, "caixas_coords": caixas}
    antigo = desenho.processar(_pedido_corte(arq, [e_in, e_lat], **kw))
    novo = desenho.processar(_pedido_corte(arq, [e_in, e_lat], pasta_cache=pasta, **kw))
    _assert_corte_equivalente(antigo, novo)
    assert e_lat.id() not in antigo["enviados"] and e_lat.id() not in novo["enviados"]
    assert e_prof.id() not in antigo["enviados"] and e_prof.id() not in novo["enviados"]
    assert novo["n_pecas_cache"] == 1 and novo["n_pecas_fallback"] == 0
