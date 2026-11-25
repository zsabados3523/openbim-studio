# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oraculo F0-S06-T27b (parte 2/3): casos 4 a 14 (geometria especial, quedas e guarda de matriz).

NAO editar este arquivo na implementacao. Auxiliares vem de `test_s06_t27b_corte_cache_oraculo`.
"""
from __future__ import annotations

import ifcopenshell
import ifcopenshell.api
import numpy as np
import pytest

from obim_geometria import cache_geometria as CG
from obim_geometria import construtor, desenho, silhueta, visibilidade
from test_s06_t27b_corte_cache_oraculo import (
    _add_caixa,
    _assert_corte_equivalente,
    _cena_basica,
    _extrair_svg,
    _novo_ifc_base,
    _pedido_corte,
    _poligono_tampa,
    _salvar_e_construir,
    _sql,
)


def _add_laje_com_vazado_faceset(f, body, pav, nome: str = "LajeVazada"):
    """IfcSlab com vazado passante em Y via IfcTriangulatedFaceSet (sem HasOpenings).

    Externo: x in [0, 4], y in [-0.5, 0.5], z in [0, 2.0]; vazado: x in [1, 3], z in [0.5, 1.5].
    Secao em y = 0: retangulo 4x2 com furo 2x1 (area liquida = 6.0 m2).
    """
    api = ifcopenshell.api.run
    ext = [(0.0, 0.0), (4.0, 0.0), (4.0, 2.0), (0.0, 2.0)]
    furo = [(1.0, 0.5), (3.0, 0.5), (3.0, 1.5), (1.0, 1.5)]
    pts = [(x, y, z) for y in (-0.5, 0.5) for x, z in ext + furo]
    v = np.asarray(pts, dtype=np.float64)
    cx, cz = 2.0, 1.0
    quads = []
    for k in range(4):
        k2 = (k + 1) % 4
        quads += [
            ([k, k2, 8 + k2, 8 + k], "fora"),
            ([4 + k, 4 + k2, 12 + k2, 12 + k], "vao"),
            ([k, k2, 4 + k2, 4 + k], (0.0, -1.0, 0.0)),
            ([8 + k, 8 + k2, 12 + k2, 12 + k], (0.0, 1.0, 0.0)),
        ]
    tris = []
    for q, tipo in quads:
        n = np.cross(v[q[1]] - v[q[0]], v[q[2]] - v[q[0]])
        c3 = v[q].mean(axis=0)
        sai = (
            np.array([c3[0] - cx, 0.0, c3[2] - cz])
            if tipo == "fora"
            else -np.array([c3[0] - cx, 0.0, c3[2] - cz])
            if tipo == "vao"
            else np.array(tipo, dtype=np.float64)
        )
        q = q if float(n @ sai) > 0.0 else q[::-1]
        tris += [(q[0] + 1, q[1] + 1, q[2] + 1), (q[0] + 1, q[2] + 1, q[3] + 1)]

    el = api("root.create_entity", f, ifc_class="IfcSlab", name=nome)
    coord_list = f.createIfcCartesianPointList3D(CoordList=pts)
    fs = f.createIfcTriangulatedFaceSet(Coordinates=coord_list, CoordIndex=tris, Closed=True)
    rep = f.createIfcShapeRepresentation(
        ContextOfItems=body, RepresentationIdentifier="Body", RepresentationType="Tessellation", Items=[fs]
    )
    el.Representation = f.createIfcProductDefinitionShape(Representations=[rep])
    api("geometry.edit_object_placement", f, product=el, matrix=np.eye(4, dtype=np.float64), is_si=False)
    api("spatial.assign_container", f, products=[el], relating_structure=pav)
    return el


# ---------------------------------------------------------------- casos 4 a 10


def test_caso04_peca_atras_do_plano_dentro_da_profundidade(tmp_path, monkeypatch):
    """Caso 4: peca nao atravessada pelo plano gera so projecao, sem tampa (secao_plana == [])."""
    f, body, pav = _novo_ifc_base()
    cortada = _add_caixa(f, body, pav, "IfcWall", "Cortada", (0.0, -0.4, 0.0), (1.0, 0.8, 2.5))
    atras = _add_caixa(f, body, pav, "IfcColumn", "Atras", (2.5, 1.2, 0.0), (0.5, 0.5, 2.5))
    arq, pasta, f2 = _salvar_e_construir(tmp_path, f, nome="atras.ifc")
    els = [f2.by_guid(cortada.GlobalId), f2.by_guid(atras.GlobalId)]

    saidas_sec: list[int] = []
    real_sec = visibilidade.secao_plana
    monkeypatch.setattr(
        visibilidade, "secao_plana", lambda *a, **k: (r := real_sec(*a, **k), saidas_sec.append(len(r)))[0]
    )
    kw = {"origem": (1.5, 0.0, 1.25), "largura": 8.0, "altura": 6.0, "profundidade_corte": 4.0}
    antigo = desenho.processar(_pedido_corte(arq, els, **kw))
    n_ant = list(saidas_sec)
    saidas_sec.clear()
    novo = desenho.processar(_pedido_corte(arq, els, pasta_cache=pasta, **kw))
    n_nov = list(saidas_sec)

    _assert_corte_equivalente(antigo, novo)
    _, g_nov, _ = _extrair_svg(novo["svg"])
    assert cortada.GlobalId in g_nov and atras.GlobalId not in g_nov
    assert 0 in n_ant and n_nov == n_ant
    assert novo["n_pecas_cache"] == 2 and novo["n_pecas_fallback"] == 0


def test_caso05_parede_com_abertura_e_porta_seguem_no_nativo(tmp_path):
    """Caso 5: IfcWall com HasOpenings e IfcDoor ficam fora de cands e de n_pecas_cache."""
    f, body, pav = _novo_ifc_base()
    parede = _add_caixa(f, body, pav, "IfcWall", "ParedeVao", (0.0, -0.15, 0.0), (4.0, 0.3, 2.8))
    vao = _add_caixa(f, body, pav, "IfcOpeningElement", "Vao", (1.2, -0.25, 0.0), (1.0, 0.5, 2.1), conter=False)
    porta = _add_caixa(f, body, pav, "IfcDoor", "Porta", (1.2, -0.1, 0.0), (1.0, 0.2, 2.1), conter=False)
    ifcopenshell.api.run("feature.add_feature", f, feature=vao, element=parede)
    ifcopenshell.api.run("feature.add_filling", f, opening=vao, element=porta)
    pilar = _add_caixa(f, body, pav, "IfcColumn", "Pilar", (5.0, -0.2, 0.0), (0.4, 0.4, 2.8))
    arq, pasta, f2 = _salvar_e_construir(tmp_path, f, nome="abertura.ifc")
    els = [f2.by_guid(e.GlobalId) for e in (parede, vao, porta, pilar)]

    kw = {"origem": (3.0, 0.0, 1.4), "largura": 10.0, "altura": 6.0}
    antigo = desenho.processar(_pedido_corte(arq, els, **kw))
    novo = desenho.processar(_pedido_corte(arq, els, pasta_cache=pasta, **kw))
    _assert_corte_equivalente(antigo, novo)
    assert set(novo["motor_pecas"]) == {f2.by_guid(pilar.GlobalId).id()}
    assert novo["n_pecas_cache"] == 1 and novo["n_pecas_fallback"] == 0


def test_caso06_laje_com_vazado_faceset_sem_has_openings(tmp_path):
    """Caso 6: laje elegivel com furo na propria malha gera tampa com furo identica."""
    f, body, pav = _novo_ifc_base()
    laje = _add_laje_com_vazado_faceset(f, body, pav)
    arq, pasta, f2 = _salvar_e_construir(tmp_path, f, nome="vazado.ifc")
    el = f2.by_guid(laje.GlobalId)
    kw = {"origem": (2.0, 0.0, 1.0), "largura": 8.0, "altura": 6.0}
    antigo = desenho.processar(_pedido_corte(arq, [el], **kw))
    novo = desenho.processar(_pedido_corte(arq, [el], pasta_cache=pasta, **kw))
    _assert_corte_equivalente(antigo, novo)
    poly_ant = _poligono_tampa(antigo["svg"], el.GlobalId)
    poly_nov = _poligono_tampa(novo["svg"], el.GlobalId)
    assert len(poly_ant.interiors) == 1 and len(poly_nov.interiors) == 1
    assert poly_ant.area == pytest.approx(6.0, abs=1e-4)
    assert poly_nov.area == pytest.approx(6.0, abs=1e-4)
    assert novo["n_pecas_cache"] == 1 and novo["n_pecas_fallback"] == 0


def test_caso07_pecas_encostadas_coincidentes(tmp_path):
    """Caso 7: duas paredes dividindo face exata (x=2.0) dao o mesmo corte."""
    f, body, pav = _novo_ifc_base()
    w1 = _add_caixa(f, body, pav, "IfcWall", "WA", (0.0, -0.3, 0.0), (2.0, 0.6, 2.8))
    w2 = _add_caixa(f, body, pav, "IfcWall", "WB", (2.0, -0.3, 0.0), (2.0, 0.6, 2.8))
    arq, pasta, f2 = _salvar_e_construir(tmp_path, f, nome="encostadas.ifc")
    els = [f2.by_guid(w1.GlobalId), f2.by_guid(w2.GlobalId)]
    kw = {"origem": (2.0, 0.0, 1.4), "largura": 8.0, "altura": 6.0}
    antigo = desenho.processar(_pedido_corte(arq, els, **kw))
    novo = desenho.processar(_pedido_corte(arq, els, pasta_cache=pasta, **kw))
    _assert_corte_equivalente(antigo, novo)
    assert novo["n_pecas_cache"] == 2 and novo["n_pecas_fallback"] == 0


def test_caso08_vinte_instancias_repetidas(tmp_path):
    """Caso 8: 20 pilares mesma forma e matrizes diferentes -> 1 forma, 20 ocorrencias, tudo cache."""
    f, body, pav = _novo_ifc_base()
    pilares = [
        _add_caixa(f, body, pav, "IfcColumn", f"P{i:02d}", (i * 0.8, -0.15 if i % 2 == 0 else 1.0, 0.0), (0.3, 0.3, 2.5))
        for i in range(20)
    ]
    arq, pasta, f2 = _salvar_e_construir(tmp_path, f, nome="instancias.ifc")
    assert _sql(pasta, "SELECT COUNT(*) FROM formas") == [(1,)]
    assert _sql(pasta, "SELECT COUNT(*) FROM ocorrencias") == [(20,)]
    els = [f2.by_guid(p.GlobalId) for p in pilares]
    kw = {"origem": (8.0, 0.0, 1.25), "largura": 24.0, "altura": 6.0}
    antigo = desenho.processar(_pedido_corte(arq, els, **kw))
    novo = desenho.processar(_pedido_corte(arq, els, pasta_cache=pasta, **kw))
    _assert_corte_equivalente(antigo, novo)
    assert len(novo["motor_pecas"]) == 20
    assert novo["n_pecas_cache"] == 20 and novo["n_pecas_fallback"] == 0


def test_caso09_peca_com_malha_invalida_ou_vazia(tmp_path):
    """Caso 9: peca sem triangulos mantem falhas_geometria igual; malha vazia no banco cai em fallback."""
    f, body, pav = _novo_ifc_base()
    boa = _add_caixa(f, body, pav, "IfcWall", "Boa", (0.0, -0.2, 0.0), (2.0, 0.4, 2.5))
    boa2 = _add_caixa(f, body, pav, "IfcWall", "Boa2", (3.0, -0.2, 0.0), (1.8, 0.4, 2.5))
    vazia = _add_caixa(f, body, pav, "IfcWall", "Vazia", (6.0, -0.2, 0.0), (1.0, 0.4, 2.5))
    vazia.Representation.Representations[0].Items[0].ExtrudedDirection.DirectionRatios = (0.0, 0.0, 0.0)
    arq, pasta, f2 = _salvar_e_construir(tmp_path, f, nome="vazia.ifc")
    e_boa, e_boa2, e_vaz = f2.by_guid(boa.GlobalId), f2.by_guid(boa2.GlobalId), f2.by_guid(vazia.GlobalId)

    # Forma de boa2 (distinta de boa) vira malha vazia (0 tris) no banco -> _validar_malha rejeita
    [(chave_b1,)] = _sql(pasta, "SELECT chave_forma FROM ocorrencias WHERE global_id = ?", (e_boa.GlobalId,))
    [(chave_b2,)] = _sql(pasta, "SELECT chave_forma FROM ocorrencias WHERE global_id = ?", (e_boa2.GlobalId,))
    assert chave_b1 != chave_b2
    with CG.abrir_cache(pasta, CG.cabecalho_atual(tesselacao=construtor.TESSELACAO)) as db:
        db.gravar_forma(chave_b2, np.zeros((0, 3), dtype=np.float64), np.zeros((0, 3), dtype=np.int32))

    kw = {"origem": (3.0, 0.0, 1.25), "largura": 12.0, "altura": 6.0}
    antigo = desenho.processar(_pedido_corte(arq, [e_boa, e_boa2, e_vaz], **kw))
    novo = desenho.processar(_pedido_corte(arq, [e_boa, e_boa2, e_vaz], pasta_cache=pasta, **kw))
    _assert_corte_equivalente(antigo, novo)
    assert e_vaz.id() in novo["falhas_geometria"]
    assert novo["n_pecas_cache"] == 1 and novo["n_pecas_fallback"] == 2


def test_caso10_banco_ausente(tmp_path):
    """Caso 10: pasta sem cache_geometria.sqlite -> sem excecao, queda cache_ausente, nao cria banco."""
    cena = _cena_basica(tmp_path)
    pasta_vazia = tmp_path / "sem_banco"
    pasta_vazia.mkdir()
    antigo = desenho.processar(_pedido_corte(cena.arq, cena.lista))
    novo = desenho.processar(_pedido_corte(cena.arq, cena.lista, pasta_cache=pasta_vazia))
    _assert_corte_equivalente(antigo, novo)
    assert novo["n_pecas_cache"] == 0
    assert novo["n_pecas_fallback"] == len(cena.lista)
    assert novo["queda_corte"] == "cache_ausente"
    assert not (pasta_vazia / CG.NOME_BANCO).exists()


# ---------------------------------------------------------------- casos 11 a 14


def test_caso11_banco_corrompido_e_checksum_quebrado(tmp_path):
    """Caso 11: sqlite com lixo -> cache_invalido; checksum quebrado -> so 1 peca cai e forma e apagada."""
    cena = _cena_basica(tmp_path)
    antigo = desenho.processar(_pedido_corte(cena.arq, cena.lista))

    pasta_lixo = tmp_path / "lixo"
    pasta_lixo.mkdir()
    lixo = b"arquivo corrompido nao sqlite"
    (pasta_lixo / CG.NOME_BANCO).write_bytes(lixo)
    r_lixo = desenho.processar(_pedido_corte(cena.arq, cena.lista, pasta_cache=pasta_lixo))
    _assert_corte_equivalente(antigo, r_lixo)
    assert r_lixo["n_pecas_cache"] == 0 and r_lixo["n_pecas_fallback"] == len(cena.lista)
    assert r_lixo["queda_corte"] == "cache_invalido"
    assert (pasta_lixo / CG.NOME_BANCO).read_bytes() == lixo

    alvo = cena.els["M1"]
    [(chave_alvo,)] = _sql(cena.pasta, "SELECT chave_forma FROM ocorrencias WHERE global_id = ?", (alvo.GlobalId,))
    assert _sql(cena.pasta, "SELECT COUNT(*) FROM ocorrencias WHERE chave_forma = ?", (chave_alvo,)) == [(1,)]
    [(blob,)] = _sql(cena.pasta, "SELECT vertices FROM formas WHERE chave = ?", (chave_alvo,))
    corromp = bytearray(blob)
    corromp[0] ^= 0xFF
    _sql(cena.pasta, "UPDATE formas SET vertices = ? WHERE chave = ?", (bytes(corromp), chave_alvo))

    r_ck = desenho.processar(_pedido_corte(cena.arq, cena.lista, pasta_cache=cena.pasta))
    _assert_corte_equivalente(antigo, r_ck)
    assert r_ck["n_pecas_fallback"] == 1 and r_ck["n_pecas_cache"] == len(cena.lista) - 1
    assert r_ck["queda_corte"] is None
    assert _sql(cena.pasta, "SELECT COUNT(*) FROM formas WHERE chave = ?", (chave_alvo,)) == [(0,)]


def test_caso12_cabecalho_incompativel(tmp_path):
    """Caso 12: banco com versao_motor diferente -> queda cache_invalido e resultado igual."""
    cena = _cena_basica(tmp_path)
    antigo = desenho.processar(_pedido_corte(cena.arq, cena.lista))
    pasta_inv = tmp_path / "cab_inv"
    cab = CG.cabecalho_atual(versao_motor="999", tesselacao=construtor.TESSELACAO)
    with CG.abrir_cache(pasta_inv, cab) as db:
        db.gravar_forma("sentinela", np.zeros((3, 3), dtype=np.float64), np.array([[0, 1, 2]], dtype=np.int32))
    r = desenho.processar(_pedido_corte(cena.arq, cena.lista, pasta_cache=pasta_inv))
    _assert_corte_equivalente(antigo, r)
    assert r["queda_corte"] == "cache_invalido"
    assert r["n_pecas_cache"] == 0 and r["n_pecas_fallback"] == len(cena.lista)
    assert _sql(pasta_inv, "SELECT chave FROM formas") == [("sentinela",)]


def test_caso13_banco_incompleto_fallback_por_peca(tmp_path, monkeypatch):
    """Caso 13: metade das pecas no banco -> presentes via cache, ausentes via fallback."""
    f, body, pav = _novo_ifc_base()
    pecas = [_add_caixa(f, body, pav, "IfcWall", f"W{i}", (i * 2.0, -0.2, 0.0), (1.2, 0.4, 2.5)) for i in range(4)]
    arq, pasta, f2 = _salvar_e_construir(tmp_path, f, nome="incomp.ifc", ids_cache=[pecas[0].id(), pecas[1].id()])
    els = [f2.by_guid(p.GlobalId) for p in pecas]
    kw = {"origem": (3.5, 0.0, 1.25), "largura": 12.0, "altura": 6.0}
    antigo = desenho.processar(_pedido_corte(arq, els, **kw))

    fb_ids: list[list[int]] = []
    real_formas = silhueta.formas_do_mundo
    monkeypatch.setattr(
        silhueta,
        "formas_do_mundo",
        lambda f_, es, **k: (fb_ids.append([e.id() for e in es]), real_formas(f_, es, **k))[1],
    )
    novo = desenho.processar(_pedido_corte(arq, els, pasta_cache=pasta, **kw))
    _assert_corte_equivalente(antigo, novo)
    assert novo["n_pecas_cache"] == 2 and novo["n_pecas_fallback"] == 2
    assert novo["n_pecas_cache"] + novo["n_pecas_fallback"] == len(novo["motor_pecas"])
    assert novo["queda_corte"] is None
    assert [sorted(x) for x in fb_ids] == [sorted([els[2].id(), els[3].id()])]


def test_caso14_banco_velho_peca_movida_guarda_matriz(tmp_path, monkeypatch):
    """Caso 14: parede movida e salva sem reconstruir banco cai em fallback pela guarda de matriz."""
    f, body, pav = _novo_ifc_base()
    w1 = _add_caixa(f, body, pav, "IfcWall", "W1", (0.0, -0.2, 0.0), (1.0, 0.4, 2.5))
    w2 = _add_caixa(f, body, pav, "IfcWall", "W2", (2.0, -0.2, 0.0), (1.0, 0.4, 2.5))
    w3 = _add_caixa(f, body, pav, "IfcWall", "W3", (4.0, -0.2, 0.0), (1.0, 0.4, 2.5))
    arq, pasta, f_salvo = _salvar_e_construir(tmp_path, f, nome="movida.ifc")

    m_nova = np.eye(4, dtype=np.float64)
    m_nova[:3, 3] = (3.5, -0.2, 0.0)
    ifcopenshell.api.run(
        "geometry.edit_object_placement", f_salvo, product=f_salvo.by_guid(w2.GlobalId), matrix=m_nova, is_si=False
    )
    f_salvo.write(str(arq))
    f2 = ifcopenshell.open(str(arq))
    els = [f2.by_guid(e.GlobalId) for e in (w1, w2, w3)]

    kw = {"origem": (3.0, 0.0, 1.25), "largura": 12.0, "altura": 6.0}
    antigo = desenho.processar(_pedido_corte(arq, els, **kw))

    fb_ids: list[list[int]] = []
    real_formas = silhueta.formas_do_mundo
    monkeypatch.setattr(
        silhueta,
        "formas_do_mundo",
        lambda f_, es, **k: (fb_ids.append([e.id() for e in es]), real_formas(f_, es, **k))[1],
    )
    novo = desenho.processar(_pedido_corte(arq, els, pasta_cache=pasta, **kw))
    _assert_corte_equivalente(antigo, novo)
    assert novo["n_pecas_cache"] == 2 and novo["n_pecas_fallback"] == 1
    assert novo["queda_corte"] is None
    assert fb_ids == [[f2.by_guid(w2.GlobalId).id()]]
