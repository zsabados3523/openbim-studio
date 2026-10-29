# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo do F0-S05-T11, protótipo de merge por GlobalId (ADR-002 §4.1 e §4.7; `v2/02` §6.7; insumo para a 2.0, não é portão). Quem tira os
`@AINDA_NAO` é o autor deste oráculo, em commit próprio. Auxiliar: `tests/s05_t11_aux.py`.
CONTRATO (pacote `prototypes/s05/merge/`, sem Qt, sem `obimcore`; o teste faz `sys.path.insert(0, <raiz>/prototypes/s05)` e `import merge`):
- `juntar(base, a, b) -> Resultado`. `base`, `a`, `b` = pares `(arquivo, lateral)`: `arquivo` = `ifcopenshell.file`, `lateral` = `openbim_app.lateral.Lateral`.
  `a` e `b` saem da MESMA base gravada (ids STEP da base iguais nas três); os ids STEP NOVOS de `a` e `b` colidem (criam o mesmo número com conteúdo diferente).
- `Resultado`: `.modelo` (`ifcopenshell.file` NOVO), `.lateral` (`Lateral` NOVO), `.conflitos` (lista de str sem repetição, qualquer ordem: GlobalId do elemento IFC, ou
  `"<coleção>/<id>"` do objeto do lateral). As entradas não mudam. Aceita a ordem (a, b) e (b, a) com o mesmo resultado.
- Por estado, não por operação (ADR §4.7): elemento mudado (criado, alterado, apagado) por UMA cópia vem dessa cópia; por NENHUMA, fica como na base. Mudado nas DUAS (mesmo só atributos
  diferentes, nomes diferentes, apagar contra alterar, criar contra criar com conteúdo diferente) = conflito: nada é aplicado, o elemento fica como na base (ausente, se a base
  não o tem). Relação nunca é dona (ADR §4.1 regra 2): duas cópias que põem paredes diferentes no mesmo pavimento NÃO dão conflito e a relação junta as duas listas; membro de relação
  que mudou por causa de um elemento em conflito volta a ser o da base (sem parede fora da relação do pavimento).
- Igualdade = a régua por conteúdo do T04 (`s05_conteudo_aux.foto/diferencas`): por GlobalId, multiconjunto sem GlobalId (ids STEP não contam) e `lateral.canonico()`.
- Criação idêntica (mesmo GlobalId, mesmo conteúdo) nas duas cópias: UM elemento só. Conflito ou não, o caso aceita as duas respostas (a escolha vai ao ADR-002 na T12).
NÃO COBERTO (vai ao ADR-002 na T12): dono do pset (§4.1 regra 3): pset editado em A e nome do mesmo elemento em B; aqui isso NÃO é conflito nem é exigido.
CENÁRIO (`cenario`): base `gerar_modelo_grande` com 600 paredes em 6 andares + lateral de 80 objetos; A edita os andares 0 a 2 e B os 3 a 5; 200 edições por cópia (semente 20261023):
nome, mover, pset criar e editar, apagar, criar parede com geometria e pavimento, e criar, alterar e apagar no lateral. O cenário é conferido antes da API (a interseção dos tocados
por foto é exatamente a planejada, pisos por tipo, 100+ ids STEP novos colidindo). GUARDA: sem ifcopenshell pula; com OBIM_S05_OBRIGATORIO=1 vira falha."""
import pytest
import s05_conteudo_aux as R
import s05_t11_aux as X
from s05_conteudo_aux import _limpa, base_ifc  # noqa: F401  (fixtures)

AINDA_NAO = pytest.mark.xfail(strict=True, raises=ImportError, reason="T11: prototypes/s05/merge ainda não existe")


@AINDA_NAO
def test_200_edicoes_disjuntas_juntam(tmp_path):  # casos 1 e 2 do cartão (a ordem inversa está em test_ordem_nao_importa)
    c = X.cenario(tmp_path, com_conflitos=False)
    assert c.conflitos == [] and all(x["criar"] >= 15 and x["apagar"] >= 15 for x in c.cont)
    X.confere(X.juntar_fn()(c.base, c.a, c.b), c, tmp_path, "juntar(base, A, B)")


@AINDA_NAO
@pytest.mark.parametrize("com_conflitos", [False, True])
def test_ordem_nao_importa(tmp_path, com_conflitos):
    c = X.cenario(tmp_path, com_conflitos)
    juntar = X.juntar_fn()
    ab, ba = juntar(c.base, c.a, c.b), juntar(c.base, c.b, c.a)
    X.confere(ba, c, tmp_path, "juntar(base, B, A)")
    assert R.diferencas(X.foto((ab.modelo, ab.lateral)), X.foto((ba.modelo, ba.lateral))) == [] and sorted(ab.conflitos) == sorted(ba.conflitos)


@AINDA_NAO
def test_20_elementos_nas_duas_copias_sao_exatamente_os_conflitos(tmp_path):  # caso 3: 10 com o mesmo atributo, 10 com atributos diferentes (granularidade: o elemento)
    c = X.cenario(tmp_path, com_conflitos=True)
    assert len(c.conflitos) == 20 and all("/" not in g for g in c.conflitos)
    r = X.juntar_fn()(c.base, c.a, c.b)
    assert sorted(r.conflitos) == sorted(c.conflitos), f"conflitos: {sorted(r.conflitos)}"
    for g in c.conflitos:  # nada aplicado sozinho: o nome e a descrição são os da base
        w, w0 = r.modelo.by_guid(g), c.base[0].by_guid(g)
        assert (w.Name, w.Description) == (w0.Name, w0.Description), f"{g}: aplicou sozinho {w.Name!r}"
    X.confere(r, c, tmp_path, "20 conflitos")


@AINDA_NAO
def test_criar_contra_criar_e_alterar_contra_alterar_sao_conflitos(base_ifc, tmp_path):  # mesmo GlobalId criado com conteúdo diferente; mesmo objeto do lateral
    base, A, B = X.duas(base_ifc)
    for g in X.CONF_ADD:
        A.parede(None, guid=g, nome="conflito"), B.parede(None, guid=g, nome="conflito")
    A.lado["notas"]["n1"], B.lado["notas"]["n1"] = {"texto": "A"}, {"texto": "B"}  # alterar contra alterar
    A.lado["cotas"], B.lado["cotas"] = {"zz": {"texto": "A"}}, {"zz": {"texto": "B"}}  # criar contra criar
    c = X.fechar(base, A, B, X.CONF_ADD, [("notas", "n1"), ("cotas", "zz")])
    r = X.juntar_fn()(c.base, c.a, c.b)
    assert not [w for w in r.modelo.by_type("IfcWall") if w.GlobalId in X.CONF_ADD], "criação em conflito foi aplicada"
    assert r.lateral.obter("notas", "n1") == base[1].obter("notas", "n1") and r.lateral.obter("cotas", "zz") is None
    X.confere(r, c, tmp_path, "criar/alterar contra o mesmo")


@AINDA_NAO
def test_editar_contra_apagar_e_conflito_e_nada_muda(base_ifc, tmp_path):  # nos dois sentidos, no IFC e no lateral; sem outra edição o resultado é a própria base
    base, A, B = X.duas(base_ifc)
    w, rel = A.paredes(A.andares()[0]), A.andares()[0].ContainsElements[0].GlobalId
    A.apagar(w[0]), B.nome(w[0], "B renomeou")  # A apaga, B edita
    A.nome(w[1], "A renomeou"), B.apagar(w[1])  # A edita, B apaga (a relação do pavimento é tocada pelas duas cópias)
    A.lado["notas"].pop("n1"), B.lado["notas"].__setitem__("n1", {"texto": "B"})
    A.lado["notas"]["n2"], _ = {"texto": "A2"}, B.lado["notas"].pop("n2")
    c = X.fechar(base, A, B, conf_ifc=w[:2], conf_lado=[("notas", "n1"), ("notas", "n2")], inter_ifc=[rel], esperada=X.foto(base))
    X.confere(X.juntar_fn()(c.base, c.a, c.b), c, tmp_path, "editar contra apagar")


@AINDA_NAO
def test_criacao_identica_nas_duas_copias_nao_duplica(base_ifc, tmp_path):
    base, A, B = X.duas(base_ifc)
    gid = "0criacaoIdenticaGemea1"
    A.parede(None, guid=gid, nome="gêmea", exato=True), B.parede(None, guid=gid, nome="gêmea", exato=True)  # sem geometria: não cria entidade sem GlobalId
    A.parede(A.andares()[0], nome="só A"), B.parede(B.andares()[1], nome="só B")
    c = X.fechar(base, A, B, inter_ifc=[gid])
    r = X.juntar_fn()(c.base, c.a, c.b)
    assert sorted(r.conflitos) in ([], [gid]), f"conflitos inesperados: {r.conflitos}"
    ok = X.esp(c, [gid] if r.conflitos else [])
    X.confere(r, c._replace(conflitos=r.conflitos, esperada=ok), tmp_path, "criação idêntica")
    assert [e.GlobalId for e in r.modelo.by_type("IfcWall")].count(gid) == (0 if r.conflitos else 1)


@AINDA_NAO
def test_mesmo_pavimento_nao_e_conflito_e_a_relacao_junta_as_duas_listas(base_ifc, tmp_path):  # ADR §4.1 regra 2: a relação nunca é dona
    base, A, B = X.duas(base_ifc)
    andar = A.andares()[0]
    rel, w = andar.ContainsElements[0], A.paredes(andar)
    novas = [A.parede(andar) for _ in range(3)], [B.parede(B.andares()[0]) for _ in range(3)]
    A.apagar(w[0]), A.apagar(w[1]), A.nome(w[2]), A.mover(w[3])
    B.apagar(w[4]), B.apagar(w[5]), B.nome(w[6])
    c = X.fechar(base, A, B, inter_ifc=[rel.GlobalId])
    r = X.juntar_fn()(c.base, c.a, c.b)
    X.confere(r, c, tmp_path, "mesmo pavimento", ignorar=[rel.GlobalId])  # tudo menos a relação do pavimento, que é conferida abaixo
    membros = {e.GlobalId for e in r.modelo.by_guid(rel.GlobalId).RelatedElements}
    assert membros == (set(w) - set(w[:2]) - set(w[4:6])) | set(novas[0]) | set(novas[1]), "a relação do pavimento não juntou as duas listas"
    assert r.modelo.by_guid(rel.GlobalId).RelatingStructure.GlobalId == andar.GlobalId


@AINDA_NAO
def test_copia_igual_a_base_e_identidade(base_ifc, tmp_path):
    base, A, B = X.duas(base_ifc)
    A.parede(A.andares()[0]), A.apagar(A.paredes(A.andares()[1])[0]), A.nome(A.paredes(A.andares()[0])[0]), A.lado["notas"].pop("n1")
    c = X.fechar(base, A, B)  # B = cópia sem edição nenhuma
    juntar = X.juntar_fn()
    X.confere(juntar(c.base, c.a, c.b), c._replace(esperada=c.fotos[1]), tmp_path, "juntar(base, A, base)")
    X.confere(juntar(c.base, c.b, c.a), c._replace(esperada=c.fotos[1]), tmp_path, "juntar(base, base, A)")
    X.confere(juntar(c.base, c.b, c.b), c._replace(esperada=c.fotos[0]), tmp_path, "juntar(base, base, base)")
