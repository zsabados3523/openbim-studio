# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo do F0-S06-T07b, parte 2: o que vai ao serializador, erros, pavimento vazio e a meta de custo (contrato em `test_s06_t07b_planta_oraculo.py`).
Como o teste vê a entrega: troca `ifcopenshell.geom.serializers.svg` por um espião que repassa tudo e anota cada `write(shape)`. Por isso o módulo novo tem de
chamar `ifcopenshell.geom.serializers.svg(...)` PELO ATRIBUTO DO MÓDULO no momento da chamada (nada de `from ... import svg` em tempo de importação). Conta como
entregue o que vai a `write`; o `IfcAnnotation` do motor (a anotação horizontal) não conta. Não editar na implementação."""
import time

import pytest
import s06_t04_aux as A
import s06_t07_aux as X
import s06_t07b_aux as B
from s05_conteudo_aux import _limpa, exigir  # noqa: F401  (fixture autouse)

AINDA_NAO = pytest.mark.xfail(strict=True, reason="T07b: desenho/planta.py ainda não existe")


def P():
    exigir()
    import openbim_app.desenho.planta as P_
    return P_


@pytest.fixture
def espiao(monkeypatch):
    import ifcopenshell.geom as G
    escritos, original = [], G.serializers.svg

    class Espiao:
        def __init__(self, *a, **k):
            self._r = original(*a, **k)

        def write(self, shape):
            escritos.append((shape.id, getattr(shape, "type", None)))
            return self._r.write(shape)

        def __getattr__(self, nome):
            return getattr(self._r, nome)
    monkeypatch.setattr(G.serializers, "svg", Espiao)
    return escritos


def entregues(escritos):
    return {i for i, t in escritos if t != "IfcAnnotation"}


@AINDA_NAO
@pytest.mark.parametrize("esq,off,base,k,rel", B.MODELOS)
def test_so_a_selecao_vai_ao_serializador(espiao, esq, off, base, k, rel):
    P_ = P()
    f, pavs, g = B.modelo(esq, off, base, k, rel, n_moveis=3)
    total = len([e for e in f.by_type("IfcElement") if e.Representation])
    for s in (0, 1):
        espiao.clear()
        p = P_.gerar_planta(f, B.planta(f, pavs[s], f"V{s}"))
        e = entregues(espiao)
        assert e and e <= set(p.selecao.ids) and len(e) == len(espiao) - sum(t == "IfcAnnotation" for _, t in espiao) and len(e) < total / 2 + 1
        assert not e & {f.by_guid(g[n]).id() for n in g if not n.endswith(str(s))}
    espiao.clear()
    P_.gerar_planta(f, B.planta(f, pavs[0], "Vm"), categorias_ocultas=("IfcFurnishingElement",))
    assert not entregues(espiao) & {f.by_guid(g[f"M{j}_0"]).id() for j in range(3)}  # oculto nem chega ao serializador


@AINDA_NAO
def test_meta_tres_pavimentos_trinta_moveis_ate_5_s_e_menos_de_40_por_cento(espiao):
    P_ = P()
    f, pavs, g = B.modelo("IFC4", X.GEO, 0.0, 1.0, False, n_pav=3, n_moveis=30)
    total = len([e for e in f.by_type("IfcElement") if e.Representation])
    t0 = time.perf_counter()
    p = P_.gerar_planta(f, B.planta(f, pavs[1]))
    dt = time.perf_counter() - t0
    assert dt <= 5.0 and p.n_paths > 30 and len(entregues(espiao)) < 0.4 * total, (dt, len(entregues(espiao)), total)


@AINDA_NAO
def test_erros_da_selecao_propagam():
    P_ = P()
    import openbim_app.desenho.selecao as S
    import openbim_app.vistas_ifc as V
    f, pavs, g = B.modelo("IFC4")
    with pytest.raises(V.VistaInexistente):
        P_.gerar_planta(f, "0000000000000000000000")
    with pytest.raises(V.VistaInexistente):
        P_.gerar_planta(f, g["P0"])  # existe, mas não é vista
    for ruim in (X.vista(f, "PLANTA", None, nome="solta"), X.vista(f, "CORTE", pavs[0], nome="corte"), A.annotation(f, "de outro programa").GlobalId):
        with pytest.raises(S.SelecaoInvalida):  # sem pavimento; vista de corte; sem TargetView
            P_.gerar_planta(f, ruim)
    with pytest.raises(S.SelecaoInvalida):
        P_.gerar_planta(f, B.planta(f, pavs[0]), categorias_ocultas=("IfcNaoExiste",))


@AINDA_NAO
@pytest.mark.parametrize("esq", X.ESQUEMAS)
def test_pavimento_sem_desenho_da_planta_vazia(esq):
    P_ = P()
    f, pavs = X.estrutura(esq)  # 2 pavimentos sem nenhum elemento
    gv = B.planta(f, pavs[0])
    antes = f.to_string()
    p = P_.gerar_planta(f, gv)
    assert p.n_paths == 0 and p.selecao.ids == () and B.svg_valido(p.svg) and "<path" not in p.svg
    g = B.modelo(esq, vaos=())  # tudo oculto também dá planta vazia
    p2 = P_.gerar_planta(g[0], B.planta(g[0], g[1][0]), categorias_ocultas=("IfcElement",))
    assert p2.n_paths == 0 and p2.selecao.ids == () and B.svg_valido(p2.svg) and f.to_string() == antes
