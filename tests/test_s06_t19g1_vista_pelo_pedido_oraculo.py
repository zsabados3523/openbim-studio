# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oraculo F0-S06-T19g1: a vista viaja no pedido; o filho abre o IFC salvo (sem a vista) e reconstroi a anotacao. Nao editar nesta tarefa.

CONTRATO
1. `corte.gerar_corte(..., modelo_limpo=True, caminho_ifc=<arquivo salvo SEM a vista>)` produz SVG IDENTICO ao `gerar_corte` normal (IFC reduzido),
   em corte reto e em corte girado (direcao diagonal). O filho recebe `pedido["arquivo"] == caminho_ifc`.
2. `pedido["vista"]` tem, alem de guid/escala: `matriz` (4x4, lista de listas, = get_local_placement da anotacao) e
   `bloco` (dict: XLength, YLength, ZLength e Location [x, y, z] do IfcBlock da vista).
3. `modelo_limpo` ausente/False: `caminho_ifc` e IGNORADO (o filho recebe o reduzido, que contem a vista). `modelo_limpo` e keyword-only, default False,
   bool validado (TypeError senao).
4. `obim_geometria.desenho._garantir_anotacao(f, vista)`, chamada no inicio de `_corte`: sem anotacao no arquivo, cria uma que `_corte` le (posicao pela matriz,
   bloco pelo `bloco`); com anotacao velha (deslocada), o pedido VENCE (sobrescreve posicao e bloco).
Os mutantes (so translacao, sem sobrescrever, sem criar, modelo_limpo ignorado) sao implementados abaixo e precisam ser derrubados pelas mesmas checagens
que a referencia passa."""
from __future__ import annotations

import copy
import inspect
from pathlib import Path

import ifcopenshell
import ifcopenshell.util.placement
import ifcopenshell.util.unit
import numpy as np
import pytest
import s06_t07c_aux as C
from s05_conteudo_aux import _limpa, exigir  # noqa: F401  (fixture autouse e guarda)
from s06_t15i_aux import ExecutorEspiao, corte, desenho_geo, local  # noqa: F401

from openbim_app import vistas_ifc

ANG = np.radians(30.0)


# ------------------------------------------------------------------ cena
def _cena(tmp_path, girado):
    """(f completo com vista, gid, caminho do IFC salvo ANTES de criar a vista)."""
    exigir()
    f, _g = C.modelo("IFC4", vaos=(C.PORTA,))
    salvo = tmp_path / ("limpo_girado.ifc" if girado else "limpo_reto.ifc")
    f.write(str(salvo))
    gid = C.corte(f)
    if girado:
        eixo = f.by_guid(gid).ObjectPlacement.RelativePlacement
        c, s = float(np.cos(ANG)), float(np.sin(ANG))
        eixo.Axis = f.create_entity("IfcDirection", DirectionRatios=(s, -c, 0.0))
        eixo.RefDirection = f.create_entity("IfcDirection", DirectionRatios=(c, s, 0.0))
        eixo.Location.Coordinates = (2.5 - 3.5 * c, -3.5 * s, -0.5)
    return f, gid, salvo


def _bloco_de(ann):
    for rep in ann.Representation.Representations:
        for it in rep.Items:
            if it.is_a("IfcCsgSolid") and it.TreeRootExpression.is_a("IfcBlock"):
                return it.TreeRootExpression
            if it.is_a("IfcBlock"):
                return it
    return None


def _vista_de(f, gid):
    """Vista como o pedido deve levar (independente da implementacao)."""
    a = f.by_guid(gid)
    b = _bloco_de(a)
    return {
        "tipo": "CORTE", "guid": gid, "nome": a.Name, "escala": float(ifcopenshell.util.unit.calculate_unit_scale(f)),
        "matriz": [[float(x) for x in l] for l in ifcopenshell.util.placement.get_local_placement(a.ObjectPlacement)],
        "bloco": {"XLength": float(b.XLength), "YLength": float(b.YLength), "ZLength": float(b.ZLength),
                  "Location": [float(x) for x in b.Position.Location.Coordinates]},
    }


class Captura:
    """Executor em processo que grava, de cada pedido de desenho, o `arquivo` e se ele contem a vista."""

    def __init__(self):
        self.desenhos = []

    def __call__(self, pedido):
        if pedido.get("op") == "desenho":
            arq = pedido["arquivo"]
            try:
                tem = ifcopenshell.open(arq).by_guid(pedido["vista"]["guid"]) is not None
            except Exception:
                tem = False
            self.desenhos.append({"pedido": copy.deepcopy(pedido), "arquivo": str(Path(arq).resolve()), "tem_vista": tem})
        return local.executar(pedido)


def _gerar(f, gid, gerar=None, **kw):
    ex = Captura()
    c = (gerar or corte.gerar_corte)(f, gid, executor=ex, **kw)
    assert len(ex.desenhos) == 1
    return c, ex.desenhos[0]


def _base(f, gid):
    c, d = _gerar(f, gid)
    assert c.n_paths >= 3 and "IfcWall" in c.svg, "a cena precisa produzir um corte nao trivial"
    return c, d


def _processar_no_arquivo(base_pedido, vista, arquivo):
    p = copy.deepcopy(base_pedido)
    p["vista"], p["arquivo"] = copy.deepcopy(vista), str(arquivo)
    r = desenho_geo.processar(p)
    assert r.get("ok"), r
    return r


# ------------------------------------------------------------------ referencia e mutantes de _garantir_anotacao
def _ref_garantir(variante=None):
    def g(f, vista):
        try:
            ann = f.by_guid(vista["guid"])
        except Exception:
            ann = None
        if ann is not None and variante == "sem_sobrescrever":
            return
        if ann is None:
            if variante == "sem_criar":
                return
            gid = vistas_ifc.criar_vista(f, "ref", "CORTE")
            ann = f.by_guid(gid)
            ann.GlobalId = vista["guid"]
        ann.Name = "nome_fixo_errado" if variante == "nome_fixo" else vista.get("nome")
        m = np.array(vista["matriz"], dtype=float)
        if variante == "so_translacao":
            t = m[:3, 3].copy()
            m = np.eye(4)
            m[:3, 3] = t
        pt = f.create_entity("IfcCartesianPoint", Coordinates=tuple(float(x) for x in m[:3, 3]))
        eixo = f.create_entity("IfcAxis2Placement3D", Location=pt,
                               Axis=f.create_entity("IfcDirection", DirectionRatios=tuple(float(x) for x in m[:3, 2])),
                               RefDirection=f.create_entity("IfcDirection", DirectionRatios=tuple(float(x) for x in m[:3, 0])))
        ann.ObjectPlacement = f.create_entity("IfcLocalPlacement", RelativePlacement=eixo)
        b, bl = _bloco_de(ann), vista["bloco"]
        b.XLength, b.YLength, b.ZLength = bl["XLength"], bl["YLength"], bl["ZLength"]
        b.Position.Location.Coordinates = tuple(bl["Location"])
    return g


def _checa_cria_e_sobrescreve(monkeypatch_ou_none, tmp_path, girado, garantir=None):
    """Checagens do filho: arquivo SEM vista e arquivo com vista VELHA; ambos precisam reproduzir o SVG do corte normal."""
    f, gid, salvo = _cena(tmp_path, girado)
    cbase, dbase = _base(f, gid)
    vista = _vista_de(f, gid)
    if garantir is not None:  # a base (cbase) sai da funcao real; so o filho usa o mutante
        monkeypatch_ou_none.setattr(desenho_geo, "_garantir_anotacao", garantir, raising=False)
    # (a) sem anotacao no arquivo
    r = _processar_no_arquivo(dbase["pedido"], vista, salvo)
    assert r["svg"] == cbase.svg, "sem anotacao no arquivo: o SVG tem de sair igual ao do reduzido"
    # (b) anotacao velha no arquivo: posicao e bloco deslocados
    a = f.by_guid(gid)
    eixo = a.ObjectPlacement.RelativePlacement
    eixo.Location.Coordinates = tuple(x + d for x, d in zip(eixo.Location.Coordinates, (1.7, 0.4, 0.3)))
    b = _bloco_de(a)
    b.XLength, b.Position.Location.Coordinates = b.XLength * 0.5, (0.3, 0.2, b.Position.Location.Coordinates[2] + 0.4)
    velho = tmp_path / ("velho_girado.ifc" if girado else "velho_reto.ifc")
    f.write(str(velho))
    r2 = _processar_no_arquivo(dbase["pedido"], vista, velho)
    assert r2["svg"] == cbase.svg, "anotacao velha no arquivo: o pedido tem de vencer"


# ------------------------------------------------------------------ (1) igualdade de SVG
@pytest.mark.parametrize("girado", [False, True])
def test_1_svg_pelo_arquivo_salvo_igual_ao_reduzido(tmp_path, girado):
    f, gid, salvo = _cena(tmp_path, girado)
    cbase, dbase = _base(f, gid)
    assert dbase["tem_vista"] and dbase["arquivo"] != str(salvo.resolve())
    c, d = _gerar(f, gid, modelo_limpo=True, caminho_ifc=salvo)
    assert d["arquivo"] == str(salvo.resolve()) and d["tem_vista"] is False, "o filho tem de abrir o arquivo salvo, que nao tem a vista"
    assert c.svg == cbase.svg and c.n_paths == cbase.n_paths and c.caixas == cbase.caixas


@pytest.mark.parametrize("girado", [False, True])
def test_1b_reduzido_e_deterministico(tmp_path, girado):
    f, gid, _ = _cena(tmp_path, girado)
    assert _base(f, gid)[0].svg == _base(f, gid)[0].svg


def test_1c_cena_girada_difere_da_reta(tmp_path):
    """Guarda da cena: o girado e de fato outro desenho (senao a prova do girado nao vale)."""
    a = _base(*_cena(tmp_path, False)[:2])[0].svg
    b = _base(*_cena(tmp_path, True)[:2])[0].svg
    assert a != b


# ------------------------------------------------------------------ (2) conteudo do pedido
@pytest.mark.parametrize("girado", [False, True])
def test_2_pedido_leva_matriz_e_bloco(tmp_path, girado):
    f, gid, salvo = _cena(tmp_path, girado)
    esperado = _vista_de(f, gid)
    for kw in ({}, {"modelo_limpo": True, "caminho_ifc": salvo}):
        _, d = _gerar(f, gid, **kw)
        v = d["pedido"]["vista"]
        assert v["nome"] == f.by_guid(gid).Name
        assert v["guid"] == gid and v["escala"] == esperado["escala"] and v["tipo"] == "CORTE"
        m = v["matriz"]
        assert isinstance(m, list) and len(m) == 4 and all(isinstance(l, list) and len(l) == 4 for l in m)
        assert np.allclose(np.array(m, dtype=float), np.array(esperado["matriz"]), atol=1e-9)
        b = v["bloco"]
        assert isinstance(b, dict) and {"XLength", "YLength", "ZLength", "Location"} <= set(b)
        for k in ("XLength", "YLength", "ZLength"):
            assert b[k] == pytest.approx(esperado["bloco"][k])
        assert list(b["Location"]) == pytest.approx(esperado["bloco"]["Location"]) and len(b["Location"]) == 3


def test_2b_pedido_e_serializavel_em_json(tmp_path):
    import json
    f, gid, _ = _cena(tmp_path, True)
    _, d = _gerar(f, gid)
    json.dumps(d["pedido"]["vista"])


# ------------------------------------------------------------------ (3) modelo_limpo
def test_3_sem_modelo_limpo_caminho_ifc_e_ignorado(tmp_path):
    f, gid, salvo = _cena(tmp_path, False)
    cbase, _ = _base(f, gid)
    for kw in ({"caminho_ifc": salvo}, {"caminho_ifc": salvo, "modelo_limpo": False}):
        c, d = _gerar(f, gid, **kw)
        assert d["arquivo"] != str(salvo.resolve()) and d["tem_vista"] is True
        assert c.svg == cbase.svg


def test_3b_assinatura_e_validacao(tmp_path):
    p = inspect.signature(corte.gerar_corte).parameters["modelo_limpo"]
    assert p.kind is inspect.Parameter.KEYWORD_ONLY and p.default is False
    f, gid, salvo = _cena(tmp_path, False)
    for ruim in (1, 0, "sim", None, 1.0):
        ex = Captura()
        with pytest.raises(TypeError):
            corte.gerar_corte(f, gid, executor=ex, modelo_limpo=ruim, caminho_ifc=salvo)
        assert ex.desenhos == []


# ------------------------------------------------------------------ (4) _garantir_anotacao no filho
@pytest.mark.parametrize("girado", [False, True])
def test_4_cria_anotacao_ausente_legivel_pelo_corte(tmp_path, girado):
    exigir()
    assert callable(getattr(desenho_geo, "_garantir_anotacao", None)), "falta obim_geometria.desenho._garantir_anotacao(f, vista)"
    f, gid, salvo = _cena(tmp_path, girado)
    vista = _vista_de(f, gid)
    g = ifcopenshell.open(str(salvo))
    with pytest.raises(Exception):
        g.by_guid(gid)
    desenho_geo._garantir_anotacao(g, copy.deepcopy(vista))
    a = g.by_guid(gid)
    assert a.is_a("IfcAnnotation")
    assert np.allclose(ifcopenshell.util.placement.get_local_placement(a.ObjectPlacement), np.array(vista["matriz"]), atol=1e-9)
    b = _bloco_de(a)
    assert b is not None
    assert (b.XLength, b.YLength, b.ZLength) == pytest.approx((vista["bloco"]["XLength"], vista["bloco"]["YLength"], vista["bloco"]["ZLength"]))
    assert list(b.Position.Location.Coordinates) == pytest.approx(vista["bloco"]["Location"])


@pytest.mark.parametrize("girado", [False, True])
def test_4b_anotacao_velha_e_sobrescrita(tmp_path, girado):
    exigir()
    assert callable(getattr(desenho_geo, "_garantir_anotacao", None))
    f, gid, _ = _cena(tmp_path, girado)
    vista = _vista_de(f, gid)
    a = f.by_guid(gid)
    eixo = a.ObjectPlacement.RelativePlacement
    eixo.Location.Coordinates = (9.0, 9.0, 9.0)
    b = _bloco_de(a)
    b.XLength, b.Position.Location.Coordinates = 1.0, (5.0, 5.0, 5.0)
    desenho_geo._garantir_anotacao(f, copy.deepcopy(vista))
    a = f.by_guid(gid)
    assert np.allclose(ifcopenshell.util.placement.get_local_placement(a.ObjectPlacement), np.array(vista["matriz"]), atol=1e-9)
    b = _bloco_de(a)
    assert b.XLength == pytest.approx(vista["bloco"]["XLength"]) and list(b.Position.Location.Coordinates) == pytest.approx(vista["bloco"]["Location"])
    assert len(f.by_type("IfcAnnotation")) == 1, "sobrescrever nao pode duplicar a anotacao"


@pytest.mark.parametrize("girado", [False, True])
def test_4c_filho_reproduz_svg_sem_e_com_anotacao_velha(tmp_path, girado):
    _checa_cria_e_sobrescreve(None, tmp_path, girado)


# ------------------------------------------------------------------ mutantes: a referencia passa, cada mutante cai
@pytest.mark.parametrize("girado", [False, True])
def test_m0_referencia_passa(monkeypatch, tmp_path, girado):
    monkeypatch.setattr(desenho_geo, "_garantir_anotacao", _ref_garantir(), raising=False)
    _checa_cria_e_sobrescreve(monkeypatch, tmp_path, girado)


@pytest.mark.parametrize("variante,girado", [("so_translacao", True), ("so_translacao", False), ("sem_sobrescrever", False), ("sem_sobrescrever", True), ("sem_criar", False), ("nome_fixo", False), ("nome_fixo", True)])
def test_m1_mutante_cai(monkeypatch, tmp_path, variante, girado):
    # a referencia precisa passar primeiro (prova que a checagem e justa)
    monkeypatch.setattr(desenho_geo, "_garantir_anotacao", _ref_garantir(), raising=False)
    _checa_cria_e_sobrescreve(monkeypatch, tmp_path, girado)
    monkeypatch.undo()
    with pytest.raises(Exception):
        _checa_cria_e_sobrescreve(monkeypatch, tmp_path, girado, garantir=_ref_garantir(variante))


def test_m2_modelo_limpo_ignorado_cai(monkeypatch, tmp_path):
    def checa(gerar):
        f, gid, salvo = _cena(tmp_path, False)
        _, d = _gerar(f, gid, gerar=gerar, caminho_ifc=salvo)
        assert d["arquivo"] != str(salvo.resolve()) and d["tem_vista"] is True

    checa(None)  # contrato real

    orig = corte.gerar_corte

    def ignora_flag(ifc, gid, **kw):
        if kw.get("caminho_ifc") is not None:
            kw["modelo_limpo"] = True
        return orig(ifc, gid, **kw)

    with pytest.raises(AssertionError):
        checa(ignora_flag)
