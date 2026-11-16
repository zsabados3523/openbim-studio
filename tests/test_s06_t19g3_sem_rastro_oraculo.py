# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oraculo F0-S06-T19g3: o filho de desenho nao deixa rastro no modelo aberto. Nao editar nesta tarefa.

CONTRATO (decisao do Fable, cartao T19g3)
1. `desenho._sem_rastro(f)`: gerenciador de contexto. Entrada: `f.begin_transaction()`. Saida (SEMPRE, inclusive com excecao): `f.discard_transaction()`.
   A excecao do corpo continua subindo. Desfaz `f.remove`, `create_entity` e edicao de atributo.
2. `desenho.processar` envolve o corpo (depois de `_abrir_ifc`) em `_sem_rastro(f)`: o MODELO ABERTO fica identico (`_est(f)` igual, nao so
   contagem por tipo) depois de qualquer pedido, de planta ou de corte, bem-sucedido ou que levanta excecao.
3. Gancho de reaproveitamento (o filho persistente ainda nao existe): o teste faz `desenho._abrir_ifc` devolver SEMPRE o mesmo `f`, aberto uma vez do arquivo salvo.
   O implementador nao precisa expor nada novo: basta `processar` chamar `_abrir_ifc(...)` e usar o `f` devolvido (como ja faz).
4. Repeticao no MESMO `f`: A, B, A... (planta de pavimentos diferentes, corte reto e girado) da SVG da repeticao IGUAL byte a byte a primeira e ao filho descartavel
   (que reabre o arquivo a cada pedido).
Mutantes derrubados aqui: `_sem_rastro` que nao desfaz; que faz commit em vez de discard; sem `finally`; `_isolar_pavimento` fora da transacao."""
from __future__ import annotations

import contextlib
import copy

import ifcopenshell
import ifcopenshell.geom
import ifcopenshell.util.placement
import ifcopenshell.util.unit
import numpy as np
import pytest
import s06_t07b_aux as B
import s06_t07c_aux as C
from s05_conteudo_aux import _limpa, exigir  # noqa: F401  (fixture autouse e guarda)
from s06_t15i_aux import desenho_geo

ANG = np.radians(30.0)


class _Cancelado(BaseException):
    """Cancelamento/interrupcao: nao e `Exception`, escapa do `try/except Exception` de `processar` e so o `finally` de `_sem_rastro` restaura."""


def _est(f):
    """Estado do modelo: secao DATA de `to_string()` (o cabecalho FILE_NAME leva data e hora)."""
    return f.to_string().split("DATA;", 1)[1]


# ------------------------------------------------------------------ cena
def _bloco_de(ann):
    for rep in ann.Representation.Representations:
        for it in rep.Items:
            if it.is_a("IfcCsgSolid") and it.TreeRootExpression.is_a("IfcBlock"):
                return it.TreeRootExpression
            if it.is_a("IfcBlock"):
                return it
    return None


def _vista_de(f, gid):
    a = f.by_guid(gid)
    b = _bloco_de(a)
    return {
        "tipo": "CORTE", "guid": gid, "nome": a.Name, "escala": float(ifcopenshell.util.unit.calculate_unit_scale(f)),
        "matriz": [[float(x) for x in l] for l in ifcopenshell.util.placement.get_local_placement(a.ObjectPlacement)],
        "bloco": {"XLength": float(b.XLength), "YLength": float(b.YLength), "ZLength": float(b.ZLength),
                  "Location": [float(x) for x in b.Position.Location.Coordinates]},
    }


@pytest.fixture
def cena(tmp_path):
    """(caminho do IFC salvo SEM vistas, {A: planta pav0, B: planta pav1, R: corte reto, G: corte girado, P: corte reto com profundidade})."""
    exigir()
    f, pavs, _g = B.modelo("IFC4", n_pav=2)
    salvo = tmp_path / "limpo.ifc"
    f.write(str(salvo))  # sem vistas: `_garantir_anotacao` PRECISA criar a anotacao no filho
    gr = C.corte(f, nome="CR")
    gg = C.corte(f, nome="CG")
    eixo = f.by_guid(gg).ObjectPlacement.RelativePlacement
    c, s = float(np.cos(ANG)), float(np.sin(ANG))
    eixo.Axis = f.create_entity("IfcDirection", DirectionRatios=(s, -c, 0.0))
    eixo.RefDirection = f.create_entity("IfcDirection", DirectionRatios=(c, s, 0.0))
    eixo.Location.Coordinates = (2.5 - 3.5 * c, -3.5 * s, -0.5)
    base = {"op": "desenho", "protocolo": 1, "arquivo": str(salvo), "threads": 1}

    def els(s):  # elementos do pavimento `s` (nome termina em `s`), sem aberturas
        return [[e.id(), e.GlobalId] for e in f.by_type("IfcElement") if e.Name and e.Name[-1] == str(s) and not e.is_a("IfcOpeningElement")]

    def planta(pav):
        return {**base, "elementos": els(pavs.index(pav)), "vista": {"tipo": "PLANTA", "altura_corte_m": pav.Elevation + 1.2, "origem_pav": [0.0, 0.0, 0.0],
                                  "escala": 1.0, "pavimento": pav.GlobalId}}

    def corte(gid, **extra):
        return {**base, **extra, "elementos": els(0), "vista": _vista_de(f, gid)}

    return salvo, {"A": planta(pavs[0]), "B": planta(pavs[1]), "R": corte(gr), "G": corte(gg), "P": corte(gr, profundidade_corte=0.5)}


SEQ = "ARBGPABRGP"  # cada pedido aparece de novo mais tarde, depois de os outros mutarem o modelo (R/G/P usam a mesma anotacao `CR` ou `CG`)


# ------------------------------------------------------------------ execucao
def _descartavel(pedidos, chaves):
    """Filho descartavel: reabre o arquivo a cada pedido (comportamento de hoje)."""
    saida = {}
    for k in chaves:
        r = desenho_geo.processar(copy.deepcopy(pedidos[k]))
        assert r.get("ok") and r.get("svg"), (k, r)
        saida[k] = r["svg"]
    return saida


def _no_mesmo_f(monkeypatch, salvo, pedidos, seq):
    """Roda `seq` num unico `f`; devolve [(chave, svg, antes, depois)]. `antes/depois` = `_est(f)`."""
    f = ifcopenshell.open(str(salvo))
    monkeypatch.setattr(desenho_geo, "_abrir_ifc", lambda caminho, pavimento=None: f)
    saida = []
    for k in seq:
        antes = _est(f)
        r = desenho_geo.processar(copy.deepcopy(pedidos[k]))
        saida.append((k, r, antes, _est(f)))
    return saida


def _verificar(monkeypatch, salvo, pedidos, ref):
    """Todas as exigencias de rastro e de repeticao num `f` compartilhado. Levanta AssertionError se alguma falha."""
    for k, r, antes, depois in _no_mesmo_f(monkeypatch, salvo, pedidos, SEQ):
        assert r.get("ok") and r.get("svg"), f"pedido {k} falhou num modelo reaproveitado: {r.get('erro')}"
        assert depois == antes, f"pedido {k} deixou rastro no modelo (to_string mudou)"
        assert r["svg"] == ref[k], f"pedido {k}: SVG do modelo reaproveitado difere do filho descartavel"


def _ref(cena):
    salvo, pedidos = cena
    ref = _descartavel(pedidos, "ABRGP")
    assert len({ref[k] for k in "ABRG"}) == 4, "a cena precisa distinguir pavimentos e corte reto/girado"
    assert "IfcWall" in ref["R"] and "IfcWall" in ref["G"]
    return salvo, pedidos, ref


# ------------------------------------------------------------------ 1. contrato de _sem_rastro
def test_sem_rastro_existe_e_desfaz(cena):
    salvo, pedidos = cena
    assert hasattr(desenho_geo, "_sem_rastro"), "falta desenho._sem_rastro(f)"
    f = ifcopenshell.open(str(salvo))
    antes = _est(f)
    pav1 = f.by_type("IfcBuildingStorey")[0]
    with desenho_geo._sem_rastro(f):
        desenho_geo._isolar_pavimento(f, pav1)
        desenho_geo._garantir_anotacao(f, pedidos["R"]["vista"])
        assert _est(f) != antes  # dentro, a mutacao existe
    assert _est(f) == antes


def test_sem_rastro_desfaz_e_repropaga_excecao(cena):
    salvo, pedidos = cena
    assert hasattr(desenho_geo, "_sem_rastro")
    f = ifcopenshell.open(str(salvo))
    antes = _est(f)
    with pytest.raises(KeyError):
        with desenho_geo._sem_rastro(f):
            desenho_geo._isolar_pavimento(f, f.by_type("IfcBuildingStorey")[0])
            raise KeyError("falha no meio")
    assert _est(f) == antes


# ------------------------------------------------------------------ 4. controle: as funcoes mutam sozinhas (sem _sem_rastro)
def test_controle_funcoes_mutantes_mutam_sozinhas(cena):
    salvo, pedidos = cena
    f = ifcopenshell.open(str(salvo))
    a = _est(f)
    desenho_geo._isolar_pavimento(f, f.by_type("IfcBuildingStorey")[0])
    assert _est(f) != a, "_isolar_pavimento deveria mutar (controle do oraculo)"
    f = ifcopenshell.open(str(salvo))
    a = _est(f)
    desenho_geo._garantir_anotacao(f, pedidos["R"]["vista"])
    assert _est(f) != a, "_garantir_anotacao deveria criar a anotacao (controle do oraculo)"
    p = copy.deepcopy(pedidos["R"])
    f = ifcopenshell.open(str(salvo))
    a = _est(f)
    desenho_geo._corte(f, p, None, 0.0)
    assert _est(f) != a, "_corte deveria mutar Scale/bloco (controle do oraculo)"


def test_controle_sem_sem_rastro_o_reaproveitamento_falha(cena, monkeypatch):
    """Hoje (sem transacao): reusar o `f` quebra ou deixa rastro. Neutraliza `_sem_rastro` (no-op) e exige que a verificacao FALHE."""
    salvo, pedidos, ref = _ref(cena)
    monkeypatch.setattr(desenho_geo, "_sem_rastro", _MUT["no_op"], raising=False)
    with pytest.raises(AssertionError):
        _verificar(monkeypatch, salvo, pedidos, ref)


# ------------------------------------------------------------------ 2. e 3. pedidos reais no mesmo f
def test_repeticao_no_mesmo_f_identica_ao_descartavel(cena, monkeypatch):
    assert hasattr(desenho_geo, "_sem_rastro"), "falta desenho._sem_rastro(f)"
    salvo, pedidos, ref = _ref(cena)
    _verificar(monkeypatch, salvo, pedidos, ref)


def test_modelo_identico_apos_cada_pedido_inclusive_por_to_string(cena, monkeypatch):
    assert hasattr(desenho_geo, "_sem_rastro")
    salvo, pedidos, _ref_ = _ref(cena)
    f0 = _est(ifcopenshell.open(str(salvo)))
    exec_ = _no_mesmo_f(monkeypatch, salvo, pedidos, SEQ)
    for k, r, antes, depois in exec_:
        assert r.get("ok"), (k, r)
        assert antes == depois == f0, f"pedido {k}: modelo difere do arquivo salvo"


@pytest.mark.parametrize("exc", [RuntimeError, _Cancelado], ids=["Exception", "Cancelado"])
@pytest.mark.parametrize("chave", list("ABRGP"))
def test_pedido_que_levanta_excecao_deixa_modelo_igual(cena, monkeypatch, chave, exc):
    """Injeta falha no serializador de SVG (chamado depois das mutacoes de planta e de corte). O modelo volta igual e o pedido seguinte ainda funciona."""
    assert hasattr(desenho_geo, "_sem_rastro")
    salvo, pedidos, ref = _ref(cena)
    f = ifcopenshell.open(str(salvo))
    monkeypatch.setattr(desenho_geo, "_abrir_ifc", lambda caminho, pavimento=None: f)
    antes = _est(f)
    with monkeypatch.context() as m:
        def falha(*a, **k):
            raise exc("falha injetada depois da mutacao")
        m.setattr(ifcopenshell.geom.serializers, "svg", falha)
        m.setattr(desenho_geo, "_motor_planta", falha)
        try:
            r = desenho_geo.processar(copy.deepcopy(pedidos[chave]))
        except exc:
            r = {"ok": False}
    assert not r.get("ok"), "a falha injetada deveria derrubar o pedido (ponto de injecao nao foi alcancado)"
    assert _est(f) == antes, "pedido com excecao deixou rastro no modelo"
    r2 = desenho_geo.processar(copy.deepcopy(pedidos[chave]))
    assert r2.get("ok") and r2["svg"] == ref[chave]


# ------------------------------------------------------------------ mutantes de _sem_rastro
@contextlib.contextmanager
def _no_op(f):
    yield


@contextlib.contextmanager
def _commit(f):
    f.begin_transaction()
    try:
        yield
    finally:
        f.end_transaction()


@contextlib.contextmanager
def _sem_finally(f):
    f.begin_transaction()
    yield
    f.discard_transaction()


_MUT = {"no_op": _no_op, "commit": _commit, "sem_finally": _sem_finally}


@pytest.mark.parametrize("nome", ["no_op", "commit"])
def test_mutante_sem_desfazer_e_derrubado(cena, monkeypatch, nome):
    assert hasattr(desenho_geo, "_sem_rastro")
    salvo, pedidos, ref = _ref(cena)
    monkeypatch.setattr(desenho_geo, "_sem_rastro", _MUT[nome])
    with pytest.raises(AssertionError):
        _verificar(monkeypatch, salvo, pedidos, ref)


def test_mutante_sem_finally_e_derrubado(cena, monkeypatch):
    """Sem `finally`, o pedido que falha deixa a transacao aberta e as mutacoes: o teste de excecao tem de pegar."""
    assert hasattr(desenho_geo, "_sem_rastro")
    salvo, pedidos, ref = _ref(cena)
    monkeypatch.setattr(desenho_geo, "_sem_rastro", _sem_finally)
    f = ifcopenshell.open(str(salvo))
    monkeypatch.setattr(desenho_geo, "_abrir_ifc", lambda caminho, pavimento=None: f)
    antes = _est(f)

    def falha(*a, **k):
        raise _Cancelado("cancelado depois da mutacao")
    with monkeypatch.context() as m:
        m.setattr(ifcopenshell.geom.serializers, "svg", falha)
        m.setattr(desenho_geo, "_motor_planta", falha)
        with pytest.raises(_Cancelado):
            desenho_geo.processar(copy.deepcopy(pedidos["A"]))
    assert _est(f) != antes, "o mutante sem finally deveria deixar rastro (o oraculo de excecao precisa distingui-lo)"
    # e o contrato direto de _sem_rastro tambem o derruba
    g = ifcopenshell.open(str(salvo))
    a = _est(g)
    with pytest.raises(KeyError):
        with _sem_finally(g):
            desenho_geo._isolar_pavimento(g, g.by_type("IfcBuildingStorey")[0])
            raise KeyError("x")
    assert _est(g) != a


def test_mutante_isolar_fora_da_transacao_e_derrubado(cena, monkeypatch):
    """`_isolar_pavimento` que fecha a transacao ANTES de remover (o remove fica fora dela): a repeticao tem de falhar."""
    assert hasattr(desenho_geo, "_sem_rastro")
    salvo, pedidos, ref = _ref(cena)
    original = desenho_geo._isolar_pavimento

    def fora(f, pav):
        f.end_transaction()  # confirma o que veio antes
        original(f, pav)     # remove ja sem transacao ativa

    monkeypatch.setattr(desenho_geo, "_isolar_pavimento", fora)
    with pytest.raises(Exception):  # AssertionError (rastro) ou erro ao descartar sem transacao: de qualquer forma NAO passa
        _verificar(monkeypatch, salvo, pedidos, ref)
