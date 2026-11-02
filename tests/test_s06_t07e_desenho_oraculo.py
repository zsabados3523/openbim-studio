# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo F0-S06-T07e0, parte 2 (T07e2 e T07e3): `selecionar` (CORTE) e `gerar_planta` pelo auxiliar. Especificação: `cards/F0-S06/F0-S06-T07e-especificacao.md` (§2, §4, §5 casos 1, 2, 7, 9).
Não editar este arquivo nem `s06_t07e_aux.py` na implementação; quem tira os `@AINDA_NAO_E2`/`@AINDA_NAO_E3` (xfail estrito, só por ImportError) é o autor do oráculo, em commit próprio, depois da e2/e3.
Parte 1 (contrato do cliente `auxiliar`, ganchos, erros) em `test_s06_t07e_auxiliar_oraculo.py`. Aqui, além dele:
- `selecao.selecionar(ifc, gid, *, categorias_ocultas=(), pavimento=None, executor=None, limite_s=LIMITE_PADRAO_S, cancelar=None)` e `planta.gerar_planta(ifc, gid, *, categorias_ocultas=(), threads=None,
  limite_triangulos=None, limite_s=LIMITE_PADRAO_S, cancelar=None, executor=None)`: os parâmetros novos são só os do fim; o resto é o contrato da T07a/T07b (não muda). `executor=None` = filho real;
  `executor=obim_geometria.local.executar` = mesmo processo. Tudo o que dá para validar sem geometria (vista, tipo, pavimento, `AlturaCorte`, categorias) é validado NO PAI, com as mesmas classes de erro
  de hoje (`selecao.SelecaoInvalida`, `vistas_ifc.VistaInexistente`) e SEM chamar o executor (nem criar processo).
- `obim_geometria/desenho.py`: op `desenho` do pedido: `{"op": "desenho", "elementos": [[id, GlobalId], ...], "vista": {"tipo": "PLANTA", "altura_corte_m": h, "origem_pav": [x, y, z], "escala": e}}` com `h` ABSOLUTA no
  mundo em metros, `origem_pav` no posicionamento do pavimento (unidade do arquivo), `e` = metros por unidade do arquivo ([P], mesmos números de `Planta.altura_corte` e `unidade_escala`). Resposta crua
  `{"ok": true, "svg": str, "n_paths": int, "enviados": [ids], "caixas": [ids], "falhas_geometria": [ids], "tempos": {"abrir_s", "geo_s", "write_s", "finalize_s"}}`; o pai acrescenta `copia_s` e `auxiliar_s` a `tempos`.
[P] (aprovadas na revisão do Opus): unidades de `desenho` acima; vista CORTE em `gerar_planta` e `AlturaCorte` ruim (0, negativa, texto, booleano) -> `SelecaoInvalida`; ver também as [P] do docstring da parte 1."""
import inspect

import pytest
import s06_t07e_aux as T
from test_s06_t07e_auxiliar_oraculo import _loc, _x, tmp_aux  # noqa: F401  (a fixture `tmp_aux` vem junto)

AINDA_NAO_E2 = pytest.mark.xfail(strict=True, raises=ImportError, reason="T07e2: selecao pelo auxiliar ainda não existe")
AINDA_NAO_E3 = pytest.mark.xfail(strict=True, raises=ImportError, reason="T07e3: obim_geometria.desenho e planta pelo auxiliar ainda não existem")


def _p():
    import obim_geometria.desenho  # noqa: F401  (primeira linha de cada caso @AINDA_NAO_E3)
    from openbim_app.desenho import planta
    return planta


def _s():
    import obim_geometria.local  # noqa: F401  (primeira linha de cada caso @AINDA_NAO_E2)
    from openbim_app.desenho import selecao
    return selecao


@AINDA_NAO_E2
@pytest.mark.parametrize("esq,off,base,k", T.MODELOS)
def test_caso1_corte_pelo_filho_igual_ao_local(tmp_aux, esq, off, base, k):
    S, L = _s(), _loc()
    f, d = T.modelo(esq, off, base, k)
    real, loc = S.selecionar(f, d["vc"]), S.selecionar(f, d["vc"], executor=L.executar)
    assert real.ids == loc.ids and real.falhas_geometria == loc.falhas_geometria and real == loc
    assert set(real.ids) >= {d["P"].id(), d["M"].id()} and d["falha"].id() in real.falhas_geometria
    assert not list(tmp_aux.glob("obim-desenho-*"))  # a cópia não vaza
    assert inspect.signature(S.selecionar).parameters["limite_s"].default == 180


@AINDA_NAO_E3
@pytest.mark.parametrize("esq,off,base,k", T.MODELOS)
def test_caso1_planta_pelo_filho_igual_ao_local(tmp_aux, esq, off, base, k):
    P_, L = _p(), _loc()
    f, d = T.modelo(esq, off, base, k)
    antes = f.to_string()
    real, loc = P_.gerar_planta(f, d["vp"]), P_.gerar_planta(f, d["vp"], executor=L.executar)
    assert real.svg == loc.svg and real.n_paths == loc.n_paths > 0 and real.caixas == loc.caixas and real.selecao == loc.selecao
    assert f"ifc:guid=\"{d['P'].GlobalId}\"" in real.svg and real.tempos.keys() >= {"geo_s", "write_s", "finalize_s", "copia_s", "auxiliar_s"}
    assert f.to_string() == antes and not list(tmp_aux.glob("obim-desenho-*"))
    assert inspect.signature(P_.gerar_planta).parameters["limite_s"].default == 180


@AINDA_NAO_E3
@pytest.mark.parametrize("real", [True, False])
def test_caso2_fotografia_a_parede_apagada_depois_do_preparar_sai_no_svg(tmp_aux, real):
    X, L = _x(), _loc()
    _p()
    f, d = T.modelo()
    gid_p = d["P"].GlobalId
    vista = {"tipo": "PLANTA", "altura_corte_m": 1.2, "origem_pav": [0.0, 0.0, 0.0], "escala": 1.0}
    with X.preparar(f, {"op": "desenho", "elementos": T.elementos(f, "P"), "vista": vista}) as p:
        f.remove(d["P"])
        r = X.executar(p) if real else X.executar(p, executor=L.executar)
    assert f"ifc:guid=\"{gid_p}\"" in r["svg"] and r["n_paths"] > 0 and r["tempos"].keys() >= {"abrir_s", "geo_s", "write_s", "finalize_s", "copia_s", "auxiliar_s"}


def _espiao(pedido):
    raise AssertionError("executor chamado: a validação devia parar antes")


@pytest.fixture
def sem_copia(tmp_aux, monkeypatch):  # a validação no pai não grava cópia nem chama o executor
    X = _x()

    def nao(*a, **k):
        raise AssertionError("auxiliar.preparar chamado: a validação devia parar antes da cópia")
    monkeypatch.setattr(X, "preparar", nao)
    yield tmp_aux
    assert not list(tmp_aux.glob("obim-desenho-*"))


@AINDA_NAO_E3
def test_caso7_validacao_no_pai_sem_chamar_executor(sem_copia):
    P_ = _p()
    import ifcopenshell.guid
    from openbim_app import vistas_ifc as V
    from openbim_app.desenho import selecao as S
    f, d = T.modelo()
    with pytest.raises(V.VistaInexistente):
        P_.gerar_planta(f, ifcopenshell.guid.new(), executor=_espiao)
    with pytest.raises(S.SelecaoInvalida):
        P_.gerar_planta(f, d["vc"], executor=_espiao)  # CORTE em gerar_planta
    with pytest.raises(S.SelecaoInvalida):
        P_.gerar_planta(f, d["vp"], categorias_ocultas=["IfcNaoExiste"], executor=_espiao)


@AINDA_NAO_E3
@pytest.mark.parametrize("ruim", [0, -1.0, "alto", True])
def test_caso7_altura_de_corte_invalida_no_pai(sem_copia, ruim):
    P_ = _p()
    import ifcopenshell.api
    from openbim_app.desenho import selecao as S
    f, d = T.modelo()
    ps = ifcopenshell.api.run("pset.add_pset", f, product=f.by_guid(d["vp"]), name="OBIM_Vista")
    ifcopenshell.api.run("pset.edit_pset", f, pset=ps, properties={"AlturaCorte": ruim})
    with pytest.raises(S.SelecaoInvalida):
        P_.gerar_planta(f, d["vp"], executor=_espiao)


@AINDA_NAO_E3
def test_caso9_janela_nao_carrega_geometria_na_planta(tmp_path):
    _p()
    f, d = T.modelo()
    assert T.janela_limpa(f, "planta", d["vp"], tmp_path) == {"ok": True, "ruins": []}
