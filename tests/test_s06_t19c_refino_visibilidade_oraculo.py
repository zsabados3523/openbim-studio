# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo F0-S06-T19c: `pecas.refinar_peca(pedido, id, executor, limite_s, motor="auto"|"hlr")` usa o motor `visibilidade.linhas_visiveis`
(op "peca_visivel", módulo `obim_geometria.peca_visivel`, roteada em `local.executar` e `processo.entrada`) para peça sem aberturas, sem item mapeado,
que não é porta/janela e fica INTEIRA abaixo do corte; senão (ou se o motor falhar) cai no HLR. Resposta traz `motor` ("visibilidade"|"hlr") e, no HLR
por queda, `motivo_hlr`. Referência: HLR da mesma malha (helper da T19b2), 0,1 mm de papel em 1:50, cobertura >= 99% nos dois sentidos. Especificação: cartão T19."""
from __future__ import annotations

import re

import numpy as np
import pytest
import s06_t07_aux as X
from s06_t17_aux import pedido_planta
from s06_t18a_aux import cilindro, densificar, modelo_denso
from test_s06_t19b1_visibilidade_oraculo import TOL, _amostra, _cobertura, _dist
from test_s06_t19b2_visibilidade_hlr_oraculo import CASOS, _pseg, _referencia

import obim_geometria.local as L
import obim_geometria.pecas as P
import obim_geometria.visibilidade as V
from s05_conteudo_aux import _limpa  # noqa: F401  (autouse)

OFF = (1.0, 3.0)


def _peca(tmp, malha, cls="IfcFurniture", z0=0.0, depois=None):
    """Modelo T07b mais uma peça `cls` com a malha (verts locais) em (OFF, z0), contida no pavimento; corte em 1,2 m. Devolve (pedido, peça)."""
    f, g, v, mov, par = modelo_denso(24)
    pav = f.by_type("IfcBuildingStorey")[0]
    el = X.caixa(f, cls, "PecaT19c", OFF[0], OFF[1], z0, 0.5, 0.5, 0.5)
    X.conter(f, pav, el)
    densificar(f, el, (np.asarray(malha[0]).tolist(), np.asarray(malha[1]).tolist()))
    if depois:
        depois(f, el)
    return pedido_planta(f, v, tmp), el


def _abertura(f, el):
    o = X.caixa(f, "IfcOpeningElement", "Ab", OFF[0], OFF[1], 0.0, 0.1, 0.1, 0.1)
    f.create_entity("IfcRelVoidsElement", GlobalId=X.A.ifcopenshell.guid.new(), RelatingBuildingElement=el, RelatedOpeningElement=o, **X.kw(f))


def _mapear(f, el):
    rep = el.Representation.Representations[0]
    base = f.create_entity("IfcShapeRepresentation", ContextOfItems=rep.ContextOfItems, RepresentationIdentifier="Body", RepresentationType="Tessellation", Items=rep.Items)
    mapa = f.create_entity("IfcRepresentationMap", MappingOrigin=f.create_entity("IfcAxis2Placement3D", Location=X._pt(f, 0, 0, 0)), MappedRepresentation=base)
    alvo = f.create_entity("IfcCartesianTransformationOperator3D", LocalOrigin=X._pt(f, 0, 0, 0))
    rep.Items = [f.create_entity("IfcMappedItem", MappingSource=mapa, MappingTarget=alvo)]
    rep.RepresentationType = "MappedRepresentation"


def _espiao():
    ops = []

    def ex(q):
        ops.append(q["op"])
        return L.executar(q)
    return ex, ops


def _segs_grupo(g):
    """Segmentos do grupo SVG com y devolvido ao mundo (o SVG inverte y)."""
    s = []
    for d in re.findall(r'<path\b[^>]*\bd="([^"]*)"', g):
        pts = [(float(a), -float(b)) for a, b in re.findall(r"(-?[\d.]+(?:e[-+]?\d+)?),(-?[\d.]+(?:e[-+]?\d+)?)", d)]
        s += list(zip(pts, pts[1:]))
    return np.array(s, float).reshape(-1, 2, 2)


def _mundo(nome):
    v, t = CASOS[nome]
    return v + np.array([OFF[0], OFF[1], 0.0]), t


@pytest.mark.parametrize("nome", ["cadeira", "caixa45", "placa_furo"])
def test_grupo_do_motor_igual_ao_hlr_nos_dois_sentidos(nome, tmp_path):
    p, el = _peca(tmp_path, CASOS[nome])
    ex, ops = _espiao()
    r = P.refinar_peca(p, el.id(), executor=ex)
    assert r["ok"] and r["motor"] == "visibilidade" and ops == ["peca_visivel"], r
    got = _segs_grupo(r["grupo"])
    ref = _referencia(_mundo(nome))
    assert len(got) and _cobertura(ref, got) >= 0.99, "linha do HLR sem par no motor"
    pg, wg = _amostra(got)
    assert float(wg[_dist(pg, _pseg(ref)) <= TOL].sum() / wg.sum()) >= 0.99, "linha do motor sem par no HLR"


def test_formato_do_grupo_igual_ao_do_hlr(tmp_path):
    p, el = _peca(tmp_path, CASOS["cadeira"])
    g = P.refinar_peca(p, el.id(), executor=L.executar)["grupo"]
    assert re.match(r'<g\b[^>]*\bclass="IfcFurniture"[^>]*\bifc:guid="%s"[^>]*>' % re.escape(el.GlobalId), g) and g.rstrip().endswith("</g>")
    assert "data-silhueta" not in g and g.count("<g") == 1
    ds = re.findall(r'<path\b[^>]*\bd="([^"]*)"', g)
    assert ds and all(re.fullmatch(r"M ?-?[\d.e+-]+,-?[\d.e+-]+( L ?-?[\d.e+-]+,-?[\d.e+-]+)+", d.strip()) for d in ds), "path no estilo M x,y L x,y"
    xs = np.array([float(n) for d in re.findall(r'\bd="([^"]*)"', g) for n in re.findall(r"-?[\d.]+(?:e[-+]?\d+)?", d)]).reshape(-1, 2)
    v = _mundo("cadeira")[0]
    assert abs(xs[:, 0].min() - v[:, 0].min()) < 1e-3 and abs(xs[:, 1].max() + v[:, 1].min()) < 1e-3, "y invertido (-y) e sem escala extra"


def test_mesclar_pesado_com_grupo_do_motor_nao_duplica(tmp_path):
    p, el = _peca(tmp_path, CASOS["cadeira"])
    p.update(pesados="silhueta", limiar_pesado=20)
    sil = L.executar(p)
    assert sil["ok"] and re.search(r'ifc:guid="%s"[^>]*data-silhueta|data-silhueta[^>]*ifc:guid="%s"' % ((re.escape(el.GlobalId),) * 2), sil["svg"])
    r = P.refinar_peca(p, el.id(), executor=L.executar)
    assert r["ok"] and r["motor"] == "visibilidade"
    final = P.mesclar_pesado(sil["svg"], el.GlobalId, r["grupo"])
    assert final.count('ifc:guid="%s"' % el.GlobalId) == 1 and not re.search(r'ifc:guid="%s"[^>]*data-silhueta' % re.escape(el.GlobalId), final)  # a outra peca pesada segue silhueta
    assert P.mesclar_pesado(final, el.GlobalId, r["grupo"]) == final


@pytest.mark.parametrize("caso,motivo", [("aberturas", "aberturas"), ("porta", "porta_janela"), ("janela", "porta_janela"), ("mapeada", "mapeada")])
def test_inelegivel_vai_ao_hlr_com_motivo(caso, motivo, tmp_path):
    cls = {"porta": "IfcDoor", "janela": "IfcWindow"}.get(caso, "IfcFurniture")
    depois = {"aberturas": _abertura, "mapeada": _mapear}.get(caso)
    p, el = _peca(tmp_path, CASOS["cadeira"], cls=cls, depois=depois)
    ex, ops = _espiao()
    r = P.refinar_peca(p, el.id(), executor=ex)
    assert r["motor"] == "hlr" and r["motivo_hlr"] == motivo and ops == ["peca_visivel", "desenho"], r
    esperado = P.refinar_peca(p, el.id(), executor=L.executar, motor="hlr")
    assert (r["ok"], r["grupo"]) == (esperado["ok"], esperado["grupo"])


def test_peca_que_cruza_o_corte_vai_ao_hlr_e_traz_grupo(tmp_path):
    p, el = _peca(tmp_path, cilindro(0.3, 24))  # altura 1,5 m: passa do corte (1,2 m); contorno do corte vem do HLR
    r = P.refinar_peca(p, el.id(), executor=L.executar)
    assert r["ok"] and r["motor"] == "hlr" and r["motivo_hlr"] == "cruza_corte" and r["grupo"].count("<path") >= 1


def test_falha_do_motor_cai_no_hlr_sem_levantar(tmp_path, monkeypatch):
    p, el = _peca(tmp_path, CASOS["cadeira"])
    hlr = P.refinar_peca(p, el.id(), executor=L.executar, motor="hlr")
    assert hlr["motor"] == "hlr" and "motivo_hlr" not in hlr
    monkeypatch.setattr(V, "linhas_visiveis", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom-motor")))
    ex, ops = _espiao()
    r = P.refinar_peca(p, el.id(), executor=ex)
    assert r["motor"] == "hlr" and "boom-motor" in r["motivo_hlr"] and ops == ["peca_visivel", "desenho"]
    assert (r["ok"], r["grupo"]) == (hlr["ok"], hlr["grupo"])


def test_executor_falso_motor_com_erro_ou_excecao_cai_no_hlr_e_motor_hlr_pula_o_motor():
    s = '<svg><g class="IfcFurniture" ifc:guid="GB"><path d="M 0,0 L 1,0"/></g></svg>'
    ped = {"op": "desenho", "arquivo": "x.ifc", "elementos": [[2, "GB"]], "caixas_coords": {}, "vista": {"altura_corte_m": 1.2}}
    for motor_resp in ({"ok": False, "erro": {"tipo": "X", "mensagem": "m", "rastro": ""}}, RuntimeError("quebrou")):
        ops = []

        def ex(q, motor_resp=motor_resp):
            ops.append(q["op"])
            assert [e[0] for e in q["elementos"]] == [2]
            if q["op"] == "peca_visivel":
                if isinstance(motor_resp, Exception):
                    raise motor_resp
                return motor_resp
            return {"ok": True, "svg": s}
        r = P.refinar_peca(ped, 2, executor=ex)
        assert r["ok"] and r["motor"] == "hlr" and "grupo" in r and ops == ["peca_visivel", "desenho"] and r["motivo_hlr"]
    ops = []
    r = P.refinar_peca(ped, 2, executor=lambda q: ops.append(q["op"]) or {"ok": True, "svg": s}, motor="hlr")
    assert r["ok"] and r["motor"] == "hlr" and ops == ["desenho"]


def test_op_peca_visivel_direta_resposta(tmp_path):
    p, el = _peca(tmp_path, CASOS["cadeira"])
    q = P.pedido_peca(p, el.id())
    q["op"] = "peca_visivel"
    r = L.executar(q)
    assert r["ok"] is True and r["grupo"].startswith("<g") and isinstance(r.get("tempos"), dict)
    q["vista"]["altura_corte_m"] = 0.3  # corte baixo: a cadeira (0,9 m) cruza
    r = L.executar(q)
    assert r["ok"] is False and r["elegivel"] is False and r["motivo"] == "cruza_corte"
