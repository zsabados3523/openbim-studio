# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo F0-S06-T06, parte 2 (lacunas do parecer `reports/F0-S06-T06-revisao.md`, itens 2 a 5, e decisões do líder). Mesmo contrato de
`test_s06_t06_divergencia_oraculo.py`, mais estas regras NOVAS (decisão do líder em 30/10):
(a) Manifesto do `.obim` sem `ifc_projeto_globalid`, `ifc_nome`, `ifc_sha256`, `Revisao`, ou com `Revisao` que não é inteiro (texto, decimal, booleano, nulo), ou
    sem `LadoId` quando o IFC TEM pset = `LateralRecusado` (mensagem cita o `.obim`), nunca D5/D6/D2 nem TypeError. Sem `LadoId` e IFC sem pset = normal.
(b) Erro de leitura: `.obim` ilegível por sistema (PermissionError) = `LateralRecusado`; IFC ausente, ilegível ou sem `IfcProject` = nova
    `IfcInvalido(ValueError)` com o nome do IFC na mensagem; `ifc_nome` que aponta para pasta = IFC "não achado" (D6), usar `is_file()`.
(c) Pset sem `LadoId` (ou sem `Revisao`) com `.obim` que os tem: só compara o que existe nos dois lados (globalid sempre); não vira D5 nem D3 por isso.
(d) Documento que NÃO é SHEET não conta como prancha; `DocumentId` (IFC2X3) conta como `Identification`; `ambiguas` sai ordenada; hash do IFC em blocos.
Marcadores `@AINDA_NAO` (xfail estrito) só nos casos que o código atual falha; o autor os tira depois."""
import builtins
import io
import os
import zipfile

import pytest
import s06_t06_aux as X
from s05_conteudo_aux import _limpa, exigir  # noqa: F401  (fixtures)
from test_s06_t06_divergencia_oraculo import D2, D2_OP, D3, D3_OP, D5, D5_OP, D6, D6_OP, _local, _r, dv, p  # noqa: F401

AINDA_NAO = pytest.mark.xfail(strict=True, reason="F0-S06-T06 lacunas: decisão do líder ainda não implementada")
OUTRO = "9zzzzzzzzzzzzzzzzzzzzz"


@AINDA_NAO
def test_pset_sem_revisao_nao_vira_d3_so_segue_o_hash(p):
    ifc, _ = X.fazer(p, rev=None, o_rev=5)
    _r(dv().classificar(ifc), "D1")
    X.mudar_um_byte(ifc)
    _r(dv().classificar(ifc), "D2", D2.format(0), D2_OP)


@AINDA_NAO
def test_pset_sem_ladoid_so_compara_o_globalid(p):
    ifc, _ = X.fazer(p, lado=None)
    _r(dv().classificar(ifc), "D1")
    ifc2, _ = X.fazer(p / "b", lado=None, o_gid=OUTRO)
    _r(dv().classificar(ifc2), "D5", D5, D5_OP, padrao=True, vinc=False)


def test_ifc2x3_documentid_repetido_entra_na_contagem(p):
    ifc, _ = X.fazer(p, esquema="IFC2X3", pranchas=("A-01", "A-01"))
    X.mudar_um_byte(ifc)
    r = dv().classificar(ifc)
    _r(r, "D2", D2.format(2), D2_OP, n=2)
    assert r.ambiguas == ("A-01",)


def test_documento_que_nao_e_sheet_nao_conta_como_prancha(p):
    ifc, _ = X.fazer(p, pranchas=("A-01",), docs_extra=(("A-01", "DRAWING"),))
    X.mudar_um_byte(ifc)
    r = dv().classificar(ifc)
    _r(r, "D2", D2.format(0), D2_OP)
    assert r.ambiguas == ()


def test_duas_identification_repetidas_ordenadas_e_contadas(p):
    ifc, _ = X.fazer(p, pranchas=("B-02", "B-02", "A-01", "A-01", "C-03"))
    X.mudar_um_byte(ifc)
    r = dv().classificar(ifc)
    _r(r, "D2", D2.format(4), D2_OP, n=4)
    assert r.ambiguas == ("A-01", "B-02")


def test_hash_do_ifc_e_lido_em_blocos_nunca_de_uma_vez(p, monkeypatch):
    ifc, _ = X.fazer(p)
    leituras = []

    class Prox:
        def __init__(s, f):
            s._f = f

        def read(s, n=-1):
            leituras.append(n)
            assert n is not None and 0 < n <= 16 << 20, f"leitura do IFC inteiro de uma vez (read({n}))"
            return s._f.read(n)

        def __enter__(s):
            s._f.__enter__()
            return s

        def __exit__(s, *a):
            return s._f.__exit__(*a)

        def __getattr__(s, nome):
            return getattr(s._f, nome)

    abrir = builtins.open

    def espia(arq, modo="r", *a, **k):
        f = abrir(arq, modo, *a, **k)
        return Prox(f) if str(arq).endswith(".ifc") and "b" in modo else f
    monkeypatch.setattr(builtins, "open", espia)
    monkeypatch.setattr(io, "open", espia)
    _r(dv().classificar(ifc), "D1")
    assert leituras, "o hash do IFC não passou por open().read(n)"


@pytest.mark.parametrize("quem", ["d3", "d5"])
def test_d3_e_d5_com_obim_aberto_direto(p, quem):
    ifc, ob = X.fazer(p, **({"o_rev": 3} if quem == "d3" else {"o_gid": OUTRO}))
    r = dv().classificar(ob)
    assert r.via_obim and r.ifc == ifc
    if quem == "d3":
        _r(r, "D3", D3, D3_OP)
    else:
        _r(r, "D5", D5, D5_OP, padrao=True, vinc=False)


def test_lateral_0_1_0_no_formato_exato_da_s05_com_provisorio(p):
    ifc, ob = X.fazer(p, versao="0.1.0", man={"provisorio": True, "programa_versao": "0", "data": "2026-10-24T00:00:00Z"})
    assert zipfile.ZipFile(ob).read("manifest.json").count(b"provisorio") == 1
    for entrada in (ifc, ob):
        r = dv().classificar(entrada)
        assert r.caso in ("D1", "D6") and r.versao_lateral == "0.1.0" and r.aviso is None


MANIFESTOS_RUINS = {"sem_globalid": {"ifc_projeto_globalid": X.APAGAR}, "sem_ifc_nome": {"ifc_nome": X.APAGAR}, "sem_sha": {"ifc_sha256": X.APAGAR},
                    "sem_revisao": {"Revisao": X.APAGAR}, "revisao_texto": {"Revisao": "3"}, "revisao_decimal": {"Revisao": 3.5},
                    "revisao_bool": {"Revisao": True}, "revisao_nula": {"Revisao": None}, "sem_ladoid_com_pset": {"LadoId": X.APAGAR}}


@AINDA_NAO
@pytest.mark.parametrize("entrada", ["ifc", "obim"])
@pytest.mark.parametrize("como", list(MANIFESTOS_RUINS))
def test_manifesto_incompleto_ou_com_tipo_errado_e_recusado(p, como, entrada):
    ifc, ob = X.fazer(p, man=MANIFESTOS_RUINS[como])
    antes = X.foto(p)
    with pytest.raises(dv().LateralRecusado, match="Casa.obim"):
        dv().classificar(ifc if entrada == "ifc" else ob)
    assert X.foto(p) == antes


def test_sem_ladoid_no_manifesto_e_ifc_sem_pset_e_normal(p):
    ifc, _ = X.fazer(p, pset=False, man={"LadoId": X.APAGAR})
    _r(dv().classificar(ifc), "D1", vinc=True)


@AINDA_NAO
@pytest.mark.skipif(os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0), reason="precisa de usuário comum com chmod")
def test_obim_sem_permissao_de_leitura_e_recusado(p):
    ifc, ob = X.fazer(p)
    ob.chmod(0)
    try:
        with pytest.raises(dv().LateralRecusado, match="Casa.obim"):
            dv().classificar(ifc)
    finally:
        ob.chmod(0o644)


@AINDA_NAO
@pytest.mark.parametrize("defeito", ["ausente", "lixo", "sem_projeto"])
def test_ifc_ausente_ilegivel_ou_sem_projeto_levanta_ifcinvalido(p, defeito):
    import ifcopenshell
    ifc, _ = X.fazer(p, obim=False)
    if defeito == "ausente":
        ifc.unlink()
    elif defeito == "lixo":
        ifc.write_bytes(b"isto nao e um IFC \x00\xff")
    else:
        ifcopenshell.file(schema="IFC4").write(str(ifc))
    with pytest.raises(dv().IfcInvalido, match="Casa.ifc"):
        dv().classificar(ifc)


@AINDA_NAO
def test_ifc_nome_apontando_para_pasta_e_ifc_nao_achado(p):
    ifc, ob = X.fazer(p, man={"ifc_nome": "pasta"})
    (p / "pasta").mkdir()
    r = dv().classificar(ob)
    _r(r, "D6", D6.format("pasta"), D6_OP, vistas=0, vinc=False)
    assert r.ifc is None and r.via_obim
