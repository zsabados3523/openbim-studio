# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo do F0-S05-T11, parte 2: defeitos de PERDA DE DADO achados na revisão da implementação (LOTE_OPUS_84, revisão Sonnet). Mesmo contrato e auxiliar
da parte 1 (`test_s05_t11_merge_oraculo.py`, `tests/s05_t11_aux.py`). Marcadores `@AINDA_NAO` já retirados pelo autor. NÃO cobertos (vão ao ADR-002 na T12): referência única
pendente virar `$` em geral, dono do pset (§4.1 regra 3) como regra geral, convergência (apagar ou alterar igual nas duas), conflito herdado, relações binárias.
CONTRATO NOVO (além da parte 1):
1. Nada some em `juntar(base, base, base)`: entidade sem GlobalId que só APONTA para o subgrafo de um elemento (estilo/cor, camada, aspecto de forma) e a georreferência
   (`IfcMapConversion`, `IfcProjectedCRS`) continuam no resultado. Entidade nova SEM nenhuma referência (solta) continua fora (parte 1).
2. Relação nunca é dona: a lista final de membros é calculada ANTES (união, ADR §4.1 regra 2); vazia = a relação é descartada; senão a relação fica, mesmo que uma cópia a tenha
   apagado (a API apaga a relação quando sai o último membro). Parede nova numa cópia não fica sem pavimento só porque a outra apagou a única parede dele.
3. Nenhuma relação de contenção, agregação ou definição fica com zero membros ou sem o objeto relacionador. Elemento criado numa cópia dentro de um pavimento que a outra apagou:
   ou o resultado o tem com pavimento válido, ou ele fica fora e há conflito (o elemento ou o pavimento) na lista; nunca some em silêncio.
4. Pset criado numa cópia em elemento apagado na outra = conflito do elemento (dono do pset): o elemento fica como na base e o resultado inteiro é a base.
5. `IfcRelNests.RelatedObjects` é LIST (a ordem conta): membros da base na ordem da base, depois os novos ORDENADOS POR GLOBALID, igual em juntar(A,B) e juntar(B,A)."""
import sys

import pytest
import s05_conteudo_aux as R
import s05_t11_aux as X
from s05_conteudo_aux import _limpa, base_ifc  # noqa: F401  (fixtures)

CLASSES_RICAS = ("IfcStyledItem", "IfcSurfaceStyle", "IfcSurfaceStyleRendering", "IfcColourRgb", "IfcPresentationLayerAssignment", "IfcShapeAspect", "IfcMapConversion", "IfcProjectedCRS")
NESTS = ("3NestAAAAAAAAAAAAAAAAA", "0NestBBBBBBBBBBBBBBBBB", "1NestBaseBBBBBBBBBBBBB")  # A (depois na ordem de GlobalId), B (antes), parte da base


def preparar(tmp, paredes, por_andar, extra=None):  # base pequena gravada (com `extra(f)` aplicado antes de gravar): (par da base, cópia A, cópia B)
    R.exigir()
    sys.path.insert(0, str(X.RAIZ / "scripts"))
    import gerar_modelo_grande
    caminho = tmp / "base.ifc"
    gerar_modelo_grande.gerar(str(caminho), paredes=paredes, por_andar=por_andar)
    if extra:
        f = R.ifcopenshell.open(str(caminho))
        extra(f)
        caminho = tmp / "rica.ifc"
        f.write(str(caminho))
    return X.duas(str(caminho))


def rica(f):  # cor (cadeia IfcStyledItem), camada, aspecto de forma e georreferência: tudo apontando PARA o subgrafo, ninguém aponta para eles
    w = f.by_type("IfcWall")[0]
    rep = w.Representation.Representations[0]
    est = X.api("style.add_style", f, name="Vermelho")
    X.api("style.add_surface_style", f, style=est, ifc_class="IfcSurfaceStyleRendering", attributes={
        "SurfaceColour": {"Name": None, "Red": 1.0, "Green": 0.0, "Blue": 0.0}, "Transparency": 0.0, "ReflectanceMethod": "FLAT"})
    X.api("style.assign_representation_styles", f, shape_representation=rep, styles=[est])
    X.api("layer.assign_layer", f, items=[rep], layer=X.api("layer.add_layer", f, name="Camada1"))
    f.create_entity("IfcShapeAspect", ShapeRepresentations=[rep], Name="Aspecto", ProductDefinitional=True, PartOfProductDefinitionShape=w.Representation)
    X.api("georeference.add_georeferencing", f)
    X.api("georeference.edit_georeferencing", f, coordinate_operation={"Eastings": 100.0, "Northings": 200.0, "OrthogonalHeight": 0.0}, projected_crs={"Name": "EPSG:31983"})


def sem_pendencia(m):  # nenhuma relação vazia nem sem relacionador
    for cls, rel, mem in (("IfcRelContainedInSpatialStructure", "RelatingStructure", "RelatedElements"), ("IfcRelAggregates", "RelatingObject", "RelatedObjects"),
                          ("IfcRelDefinesByProperties", "RelatingPropertyDefinition", "RelatedObjects"), ("IfcRelNests", "RelatingObject", "RelatedObjects")):
        for r in m.by_type(cls):
            assert getattr(r, rel) is not None and len(getattr(r, mem)) > 0, f"{cls} {r.GlobalId}: {rel} = {getattr(r, rel)}, {len(getattr(r, mem))} membros"


def contagem(m):
    return {c: len(m.by_type(c)) for c in CLASSES_RICAS}


def test_estilo_camada_aspecto_e_georreferencia_sobrevivem(tmp_path):
    base, A, B = preparar(tmp_path, 4, 2, rica)
    assert all(n == 1 for n in contagem(base[0]).values()), f"cenário: {contagem(base[0])}"
    juntar = X.juntar_fn()
    c = X.fechar(base, A, B, esperada=X.foto(base))  # cópias sem edição: o resultado é a base
    r = juntar(c.base, c.a, c.b)
    assert contagem(r.modelo) == contagem(base[0]), f"sumiu entidade: {contagem(r.modelo)}"
    X.confere(r, c, tmp_path, "juntar(base, base, base)")
    w = A.f.by_type("IfcWall")  # com uma edição de verdade em cada cópia, em paredes diferentes, continua tudo lá
    A.nome(w[2].GlobalId), B.nome(w[3].GlobalId)
    c = X.fechar(base, A, B)
    r = juntar(c.base, c.a, c.b)
    assert contagem(r.modelo) == contagem(base[0]), f"sumiu entidade com edições: {contagem(r.modelo)}"
    X.confere(r, c, tmp_path, "com edições")


def test_pavimento_de_uma_parede_apagada_contra_parede_nova_fica_com_pavimento(tmp_path):
    base, A, B = preparar(tmp_path, 4, 1)
    andar = A.andares()[0]
    w, rel = A.paredes(andar)[0], andar.ContainsElements[0].GlobalId
    A.apagar(w)  # a API apaga a relação quando sai o último membro
    novo = B.parede(B.andares()[0])
    c = X.fechar(base, A, B, inter_ifc=[rel])
    r = X.juntar_fn()(c.base, c.a, c.b)
    X.confere(r, c, tmp_path, "pavimento de 1 parede", ignorar=[rel])  # a relação em si é conferida abaixo
    assert not [e for e in r.modelo.by_type("IfcWall") if e.GlobalId == w], "a parede apagada voltou"
    cont = r.modelo.by_guid(novo).ContainedInStructure
    assert cont and cont[0].RelatingStructure.GlobalId == andar.GlobalId, "a parede nova ficou sem pavimento"
    sem_pendencia(r.modelo)


def test_pavimento_apagado_contra_parede_nova_nao_some_em_silencio(tmp_path):
    base, A, B = preparar(tmp_path, 4, 1)
    andar = A.andares()[0]
    w, rel = A.paredes(andar)[0], andar.ContainsElements[0].GlobalId
    A.apagar(w), A.apagar(andar.GlobalId)
    novo = B.parede(B.andares()[0])
    c = X.fechar(base, A, B, inter_ifc=[rel])
    r = X.juntar_fn()(c.base, c.a, c.b)
    sem_pendencia(r.modelo)
    ids = {e.GlobalId for e in r.modelo.by_type("IfcRoot")}
    if novo in ids:  # tem o elemento: com pavimento que existe
        cont = r.modelo.by_guid(novo).ContainedInStructure
        assert cont and cont[0].RelatingStructure.GlobalId in ids, "a parede nova ficou sem pavimento"
    else:  # ficou fora: tem de estar na lista de conflitos
        assert novo in r.conflitos or andar.GlobalId in r.conflitos, f"a parede nova sumiu em silêncio (conflitos {r.conflitos})"


def test_relacao_que_termina_sem_membros_e_descartada(tmp_path):
    base, A, B = preparar(tmp_path, 4, 2)
    andar = A.andares()[0]
    w, rel = A.paredes(andar), andar.ContainsElements[0].GlobalId
    A.apagar(w[0]), B.apagar(w[1])  # cada cópia tira uma das duas paredes do pavimento
    c = X.fechar(base, A, B, inter_ifc=[rel])
    r = X.juntar_fn()(c.base, c.a, c.b)
    X.confere(r, c, tmp_path, "pavimento esvaziado", ignorar=[rel])
    assert rel not in {e.GlobalId for e in r.modelo.by_type("IfcRoot")}, "a relação ficou, sem membros"
    sem_pendencia(r.modelo)


def test_pset_novo_em_elemento_apagado_na_outra_copia_e_conflito(base_ifc, tmp_path):
    base, A, B = X.duas(base_ifc)
    w = A.paredes(A.andares()[0])[5]
    A.apagar(w)
    B.pset(w)
    ps = B.psets[w]
    c = X.fechar(base, A, B, esperada=X.foto(base))
    r = X.juntar_fn()(c.base, c.a, c.b)
    assert w in r.conflitos and set(r.conflitos) <= {w, ps.GlobalId, ps.DefinesOccurrence[0].GlobalId}, f"conflitos: {r.conflitos}"
    X.confere(r, c._replace(conflitos=r.conflitos), tmp_path, "pset em elemento apagado")  # nada aplicado: o resultado é a base
    sem_pendencia(r.modelo)


def test_nests_com_membros_novos_nas_duas_copias_tem_ordem_fixa(tmp_path):
    def parte(f, guid, w):
        p = X.api("root.create_entity", f, ifc_class="IfcBuildingElementPart")
        p.GlobalId = guid
        X.api("nest.assign_object", f, related_objects=[p], relating_object=f.by_guid(w))
    caminho = tmp_path / "ninho.ifc"
    base0, _, _ = preparar(tmp_path, 4, 2)
    w = base0[0].by_type("IfcWall")[0].GlobalId
    parte(base0[0], NESTS[2], w)
    base0[0].write(str(caminho))
    base, A, B = X.duas(str(caminho))
    rel = base[0].by_guid(NESTS[2]).Nests[0].GlobalId
    parte(A.f, NESTS[0], w), parte(B.f, NESTS[1], w)
    c = X.fechar(base, A, B, inter_ifc=[rel])
    juntar = X.juntar_fn()
    ab, ba = juntar(c.base, c.a, c.b), juntar(c.base, c.b, c.a)
    esperada = [NESTS[2], NESTS[1], NESTS[0]]  # base, depois os novos por GlobalId (o de B vem antes do de A)
    for nome, r in (("(A, B)", ab), ("(B, A)", ba)):
        assert [e.GlobalId for e in r.modelo.by_guid(rel).RelatedObjects] == esperada, f"juntar{nome}: ordem dos membros do IfcRelNests"
        sem_pendencia(r.modelo)
    X.confere(ab, c, tmp_path, "nests", ignorar=[rel])
