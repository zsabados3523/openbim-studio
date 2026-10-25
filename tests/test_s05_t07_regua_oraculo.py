# SPDX-License-Identifier: AGPL-3.0-or-later
"""Régua do teste de gravação do par (`tests/s05_t07_aux.py`), validada sem o módulo do par (sem `@AINDA_NAO`).
Prova que `estado_par` aceita o par antigo inteiro e o par novo inteiro e pega cada mistura ou incoerência. Guarda: sem ifcopenshell, pula (falha
com OBIM_S05_OBRIGATORIO=1)."""
import json
import zipfile

import pytest
import s05_t07_aux as X
from s05_conteudo_aux import _limpa, base_ifc, exigir  # noqa: F401  (fixtures)


@pytest.fixture
def pares(tmp_path, base_ifc):  # noqa: F811
    """Par antigo A (Revisao 1) e par novo B (Revisao 2, depois de `mudar`), escritos pelo escritor falso, e o esperado de B."""
    exigir()
    import ifcopenshell
    objs = {"notas": {"n1": {"texto": "antiga"}}}
    (tmp_path / "A").mkdir(), (tmp_path / "B").mkdir()
    X.escrever_par_falso(tmp_path / "A" / "Casa.ifc", base_ifc, objs, 1)
    f, objs_b = ifcopenshell.open(base_ifc), json.loads(json.dumps(objs))
    X.mudar(f, lambda c, i, o: objs_b.setdefault(c, {}).__setitem__(i, o), 2)
    f.write(str(tmp_path / "mudado.ifc"))
    X.escrever_par_falso(tmp_path / "B" / "Casa.ifc", tmp_path / "mudado.ifc", objs_b, 2)
    a = X.Antigo((tmp_path / "A" / "Casa.ifc").read_bytes(), (tmp_path / "A" / "Casa.obim").read_bytes())
    return tmp_path, a, X.esperado(base_ifc, objs, 2, 2), objs_b


def montar(tmp_path, ifc, obim):
    d = tmp_path / "M"
    d.mkdir(exist_ok=True)
    (d / "Casa.ifc").write_bytes(ifc), (d / "Casa.obim").write_bytes(obim)
    return d / "Casa.ifc"


def test_regua_aceita_antigo_e_novo(pares):
    t, a, novo, _ = pares
    assert X.estado_par(t / "A" / "Casa.ifc", a, novo, t / "projeto") == ("antigo", [])
    assert X.estado_par(t / "B" / "Casa.ifc", a, novo, t / "projeto") == ("novo", [])
    assert X.estado_par(t / "nada" / "Casa.ifc", a, novo) == ("nada", [])


def test_regua_pega_cada_mistura(pares):
    t, a, novo, objs_b = pares
    bi, bo = (t / "B" / "Casa.ifc").read_bytes(), (t / "B" / "Casa.obim").read_bytes()
    falsos = {"ifc antigo e lateral novo": (a.ifc, bo), "ifc novo e lateral antigo": (bi, a.obim), "ifc cortado": (bi[: len(bi) // 2], bo),
              "um byte trocado no ifc": (bi[:-40] + bytes([bi[-40] ^ 1]) + bi[-39:], bo)}
    for nome, (i, o) in falsos.items():
        e, prob = X.estado_par(montar(t, i, o), a, novo)
        assert prob, f"{nome}: a régua não pegou ({e})"
    outro = X.esperado(t / "A" / "Casa.ifc", {}, 3, 2)  # modelo com outra mudança
    assert X.estado_par(t / "B" / "Casa.ifc", a, outro)[1], "modelo diferente do esperado passou"
    assert X.estado_par(t / "B" / "Casa.ifc", a, novo._replace(revisao=3))[1], "Revisao errada passou"
    assert X.estado_par(t / "B" / "Casa.ifc", a, novo._replace(lado=X.canon({})))[1], "lateral diferente passou"
    assert X.estado_par(t / "B" / "Casa.ifc", a, novo._replace(lado_id="outro"))[1], "LadoId errado passou"


@pytest.mark.parametrize("campo,valor", [("Revisao", 3), ("ifc_sha256", "0" * 64), ("ifc_tamanho", 1), ("LadoId", "x"), ("provisorio", None),
                                         ("formato", "zip"), ("ifc_projeto_globalid", "0" * 22), ("ifc_nome", "Outra.ifc")])
def test_regua_pega_manifesto_errado(pares, campo, valor):
    t, a, novo, objs_b = pares
    d = t / "C" / "Casa.ifc"
    d.parent.mkdir()
    X.escrever_par_falso(d, t / "mudado.ifc", objs_b, 2, manifesto={campo: valor})
    assert X.estado_par(d, a, novo)[1], f"manifesto com {campo}={valor!r} passou"


def test_regua_pega_zip_estranho_metade_e_sobra(pares):
    t, a, novo, _ = pares
    d = t / "B" / "Casa.ifc"
    with zipfile.ZipFile(d.with_suffix(".obim"), "a") as z:
        z.writestr("solto.txt", "x")
    assert X.estado_par(d, a, novo)[1], "entrada estranha no ZIP passou"
    d.with_suffix(".obim").unlink()
    assert X.estado_par(d, a, novo)[0] == "?", "par pela metade passou"
    (t / "A" / "Casa.obim.tmp").write_bytes(b"x")
    (t / "projeto").mkdir()
    (t / "projeto" / "gravacao.json").write_text("{}")
    assert X.estado_par(t / "A" / "Casa.ifc", a, novo, t / "projeto") == ("antigo", ["sobrou Casa.obim.tmp", "sobrou projeto/gravacao.json"])
