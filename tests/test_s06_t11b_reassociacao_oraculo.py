# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo do F0-S06-T11, parte B (reprovação do Argon, T11B/T11C: fraco x forte, escala, caixa que estoura, guid ausente, mutantes).
Contrato no docstring de `test_s06_t11_reassociacao_oraculo.py`. Ajudantes em `_reassociacao_ajudantes.py`."""
import pytest
from _reassociacao_ajudantes import P, _mod, antigos, atuais_ok, el, ids  # noqa: F401


def test_forte_vence_fraco_nao_vira_ambiguo():
    v = {"V1": [el("a1", tag="T1", nome="P1")]}
    r = P(v, [el("n1", tag="T1", nome="Z", x=1.5), el("n2", tag="T9", nome="P1", x=0.0)])
    assert r["alta"] == [] and ids(r["baixa"]) == [("V1", "a1", "n1")] and r["orfaos"] == []
    r = P(v, [el("n1", tag="T1", nome="Z", x=0.1), el("n2", tag="T9", nome="P1", x=0.0), el("n3", tag=None, nome="P1")])
    assert ids(r["alta"]) == [("V1", "a1", "n1")]


def test_fraco_so_vale_sem_forte_e_nunca_e_alta():
    v = {"V1": [el("a1", tag="T1", nome="P1")]}
    r = P(v, [el("n1", tag="T1", nome="Z", x=9.0), el("n2", tag="T9", nome="P1", x=0.0)])  # forte fora de tol_baixa
    assert r["alta"] == [] and ids(r["baixa"]) == [("V1", "a1", "n2")]
    r = P(v, [el("n2", tag="T9", nome="P1"), el("n3", tag=None, nome="P1")])  # 2 fracos
    assert r["alta"] == r["baixa"] == [] and r["orfaos"][0]["motivo"] == "ambiguo"


def test_disputa_forte_nao_e_derrubada_por_fraco():
    v = {"V1": [el("a1", tag="T1", nome="P1"), el("b1", tag="T9", nome="Q", x=0.0)]}
    r = P(v, [el("n1", tag="T1", nome="Q")])  # a1 forte (Tag), b1 fraco (Name Q, Tag diferente)
    assert ids(r["alta"]) == [("V1", "a1", "n1")] and r["baixa"] == []
    assert r["orfaos"] == [{"vista": "V1", "guid_antigo": "b1", "motivo": "disputado"}]


@pytest.mark.parametrize("t_old,t_new", [("T1", None), (None, "T1"), ("T1", ""), ("", "T1")])
def test_tag_so_de_um_lado_com_name_igual_e_baixa(t_old, t_new):
    v = {"V1": [el("a1", tag=t_old, nome="P1")]}
    r = P(v, [el("n1", tag=t_new, nome="P1")])
    assert r["alta"] == [] and ids(r["baixa"]) == [("V1", "a1", "n1")]
    for nome in (None, ""):  # sem Name igual e não vazio: continua sem identidade
        r = P({"V1": [el("a1", tag=t_old, nome=nome)]}, [el("n1", tag=t_new, nome=nome)])
        assert r["alta"] == r["baixa"] == [] and r["orfaos"][0]["motivo"] == "sem_candidato"
    r = P(v, [el("n1", tag=t_new, nome="P1", x=9.0)])
    assert r["baixa"] == [] and r["orfaos"][0]["motivo"] == "sem_candidato"


class _Conta(tuple):  # caixa que conta quantas vezes é lida
    lidas = 0

    def __iter__(self):
        _Conta.lidas += 1
        return super().__iter__()


@pytest.mark.parametrize("por", ["tag", "nome"])
def test_propor_nao_e_quadratico(por):
    n = 600
    k = {"tag": lambda i: dict(tag=f"T{i}", nome="N"), "nome": lambda i: dict(tag=None, nome=f"N{i}")}[por]
    v = {"V1": [el(f"a{i}", x=float(i) * 5, **k(i)) for i in range(n)]}
    a = [el(f"n{i}", x=float(i) * 5, caixa=_Conta((float(i) * 5, 0.0, 0.0, float(i) * 5 + 1, 1.0, 1.0)), **k(i)) for i in range(n)]
    _Conta.lidas = 0
    r = P(v, a)
    assert len(r["alta"]) == n
    assert _Conta.lidas <= 10 * n  # ingênuo: ~n*n = 360 mil leituras


@pytest.mark.parametrize("c", [(1e308, 0, 0, 1.5e308, 1, 1), (-1.5e308, 0, 0, -1.3e308, 1, 1), (0, 1e308, 0, 1, 1.5e308, 1)])
def test_caixa_que_estoura_nao_vira_inf_silencioso(c):
    r = P({"V1": [el("a1", caixa=c)]}, [el("n1", caixa=c)])
    assert ids(r["alta"]) == [("V1", "a1", "n1")] or r["orfaos"] == [{"vista": "V1", "guid_antigo": "a1", "motivo": "caixa_invalida"}]


def test_bloqueado_novo_ja_referenciado_intacto_nao_e_candidato():
    v = {"V1": [el("a1", tag="T1")], "V2": [el("n1", tag="T1")]}
    r = P(v, [el("n1", tag="T1")])
    assert r["alta"] == r["baixa"] == [] and ids(r["orfaos"]) == [("V1", "a1", None)] and r["orfaos"][0]["motivo"] == "sem_candidato"


@pytest.mark.parametrize("ref", [{"classe": "IfcWall", "nome": "P1", "tag": "T1", "caixa": (0, 0, 0, 1, 1, 1)}, el(None)])
def test_guid_ausente_ou_none_nunca_e_intacto(ref):
    m = _mod()
    v = {"V1": [ref]}
    a = [el(None), el("n1")]
    assert m.contar_quebradas(v, a) == {"V1": 1}
    r = m.propor(v, a)
    assert r["alta"] == r["baixa"] == [] and r["orfaos"] == [{"vista": "V1", "guid_antigo": None, "motivo": "sem_guid"}]
    with pytest.raises(ValueError):
        m.aplicar(v, r, [("V1", None)])
    assert m.aplicar(v, r, []) == v


def test_mesmo_guid_com_dados_diferentes_em_vistas_diferentes_decide_por_vista():
    v = {"V1": [el("a1", tag="T1", nome="P1")], "V2": [el("a1", tag="T2", nome="P2", x=5.0)]}
    r = P(v, [el("n1", tag="T1", nome="P1"), el("n2", tag="T2", nome="P2", x=5.0)])
    assert ids(r["alta"]) == [("V1", "a1", "n1"), ("V2", "a1", "n2")] and r["orfaos"] == []
    novo = _mod().aplicar(v, r, [("V1", "a1"), ("V2", "a1")])
    assert [novo["V1"][0]["guid"], novo["V2"][0]["guid"]] == ["n1", "n2"]


# --- item 6: lacunas de mutantes (devem passar hoje) ---
@pytest.mark.parametrize("ruim", [123, 1.5, (True, 0, 0, 1, 1, 1), ("0", 0, 0, 1, 1, 1), (0, 0, 0, 1, 1, None), "012345"])
def test_caixa_de_tipo_errado_e_invalida(ruim):
    r = P({"V1": [el("a1", caixa=ruim)]}, [el("n1")])
    assert r["orfaos"] == [{"vista": "V1", "guid_antigo": "a1", "motivo": "caixa_invalida"}]
    r = P({"V1": [el("a1")]}, [el("n1", caixa=ruim)])
    assert r["alta"] == r["baixa"] == [] and r["orfaos"][0]["motivo"] == "sem_candidato"


@pytest.mark.parametrize("d,lista", [((0, 0.4, 0.4), "baixa"), ((0.3, 0.3, 0.3), "baixa"), ((0, 1.5, 1.5), "orfaos"),
                                     ((1.2, 1.2, 1.2), "orfaos"), ((0.3, 0.0, 0.4), "alta"), ((0.0, 0.3, 0.4), "alta")])
def test_diagonais_3d(d, lista):
    r = P({"V1": [el("a1")]}, [el("n1", x=d[0], y=d[1], z=d[2])])
    assert len(r[lista]) == 1 and sum(len(r[k]) for k in r) == 1


@pytest.mark.parametrize("kw", [{"tol_alta": None}, {"tol_baixa": None}, {"tol_alta": "0.5"}, {"tol_baixa": "2"}, {"tol_baixa": True},
                                {"tol_alta": -0.5}, {"tol_alta": -1e-9}, {"tol_baixa": -0.5}, {"tol_baixa": -1e-9}, {"tol_alta": True, "tol_baixa": 3.0}])
def test_tolerancia_invalida_variantes(kw):
    with pytest.raises(ValueError):
        P({"V1": [el("a1")]}, [el("n1")], **kw)


# --- T11C: mutantes vivos do código corrigido ---
@pytest.mark.parametrize("x,lista", [(2.0, "baixa"), (2.0000001, "orfaos")])
def test_borda_de_tol_baixa_vale_tambem_para_fraco(x, lista):
    r = P({"V1": [el("a1", tag="T1", nome="P1")]}, [el("n1", tag="T9", nome="P1", x=x)])
    assert len(r[lista]) == 1 and sum(len(r[k]) for k in r) == 1


def test_fraco_bloqueado_nao_e_candidato():
    v = {"V1": [el("a1", tag="T1", nome="P1")], "V2": [el("n2", tag="T9", nome="P1")]}
    r = P(v, [el("n2", tag="T9", nome="P1")])
    assert r["alta"] == r["baixa"] == [] and r["orfaos"][0]["motivo"] == "sem_candidato"


def test_atual_duplicado_usa_a_menor_distancia():
    r = P({"V1": [el("a1")]}, [el("n1", x=1.0), el("n1", x=0.1)])
    assert ids(r["alta"]) == [("V1", "a1", "n1")]


def test_mesmo_antigo_forte_numa_vista_e_fraco_noutra_mantem_forca_forte():
    v = {"V1": [el("a1", tag="T1", nome="P1")], "V2": [el("a1", tag="T9", nome="P1")], "V3": [el("b1", tag="T8", nome="P1")]}
    r = P(v, [el("n1", tag="T1", nome="P1")])
    assert ids(r["alta"]) == [("V1", "a1", "n1")] and ids(r["baixa"]) == [("V2", "a1", "n1")]
    assert r["orfaos"] == [{"vista": "V3", "guid_antigo": "b1", "motivo": "disputado"}]


def test_dois_fracos_disputam_o_mesmo_novo():
    v = {"V1": [el("a1", tag="T8", nome="P1"), el("a2", tag="T9", nome="P1")]}
    r = P(v, [el("n1", tag="T1", nome="P1")])
    assert r["alta"] == r["baixa"] == [] and [(o["guid_antigo"], o["motivo"]) for o in r["orfaos"]] == [("a1", "disputado"), ("a2", "disputado")]


def test_orfao_sem_guid_vem_depois_dos_com_guid():
    sem = {"classe": "IfcWall", "nome": "P1", "tag": "T1", "caixa": (0, 0, 0, 1, 1, 1)}
    for refs in ([sem, el("a1", classe="X")], [el("a1", classe="X"), sem], [el("b9", classe="X"), sem, el("a1", classe="X")]):
        r = P({"V1": refs}, [])
        assert [o["guid_antigo"] for o in r["orfaos"]] == sorted(o["guid_antigo"] for o in r["orfaos"] if o["guid_antigo"]) + [None]


def test_atual_sem_guid_nunca_e_candidato():
    r = P({"V1": [el("a1", tag="T1")]}, [el(None, tag="T1")])
    assert r["alta"] == r["baixa"] == [] and r["orfaos"][0]["motivo"] == "sem_candidato"
    r = P({"V1": [el("a1", tag="T1")]}, [{"classe": "IfcWall", "nome": "P1", "tag": "T1", "caixa": (0, 0, 0, 1, 1, 1)}])
    assert r["alta"] == r["baixa"] == []
