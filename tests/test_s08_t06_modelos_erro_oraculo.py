# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo F0-S08-T06: `scripts/gerar_modelos_erro.py` (5 arquivos de erro derivados da `casa-terrea`).
Contrato fixado no pedido do T06. O implementador não edita este arquivo."""
import atexit
import functools
import json
import re
import shutil
import socket
import sys
import tempfile
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))

NOMES = ("erro-vazio", "erro-truncado", "erro-milimetros", "erro-sem-geometria", "erro-nome-com-acentuação")
CAMPOS = ("nome", "origem", "versao_ou_commit", "data_acesso", "sha256", "tamanho_bytes", "licenca", "atribuicao",
          "pode_ir_no_git", "esquema", "programa_de_origem", "contagens", "valores_conhecidos", "cobre", "observacoes")
UNIDADE_M = "IFCSIUNIT(*,.LENGTHUNIT.,$,.METRE.)"
UNIDADE_MM = "IFCSIUNIT(*,.LENGTHUNIT.,.MILLI.,.METRE.)"


def _mod():
    import gerar_modelos_erro
    return gerar_modelos_erro


@functools.lru_cache(maxsize=None)
def _gerado():
    base = Path(tempfile.mkdtemp(prefix="s08t06_"))
    atexit.register(shutil.rmtree, base, ignore_errors=True)
    _mod().gerar_todos(base / "corpus", base / "manifestos")
    return base / "corpus", base / "manifestos"


@functools.lru_cache(maxsize=None)
def _referencia() -> bytes:
    """Bytes da `casa-terrea` gerada pelo T04 (o modelo-base dos erros)."""
    import gerar_modelos
    base = Path(tempfile.mkdtemp(prefix="s08t06ref_"))
    atexit.register(shutil.rmtree, base, ignore_errors=True)
    gerar_modelos.gerar_todos(base / "c", base / "m")
    return (base / "c" / "casa-terrea.ifc").read_bytes()


def _arq(nome) -> Path:
    return _gerado()[0] / f"{nome}.ifc"


def _manif(nome):
    return json.loads((_gerado()[1] / f"{nome}.json").read_text(encoding="utf-8"))


def _ifc(nome):
    import ifcopenshell
    return ifcopenshell.open(str(_arq(nome)))


def _sem_nome_de_arquivo(texto: str) -> list[str]:
    return [ln for ln in texto.splitlines() if not ln.startswith("FILE_NAME")]


def test_nomes_e_arquivos_exatos():
    assert tuple(_mod().NOMES) == NOMES
    corpus, manifestos = _gerado()
    assert sorted(p.name for p in corpus.iterdir()) == sorted(f"{n}.ifc" for n in NOMES)
    assert sorted(p.name for p in manifestos.iterdir()) == sorted(f"{n}.json" for n in NOMES)


def test_deterministico_bytes_iguais(tmp_path):
    _mod().gerar_todos(tmp_path / "c", tmp_path / "m")
    corpus, manifestos = _gerado()
    for n in NOMES:
        assert (tmp_path / "c" / f"{n}.ifc").read_bytes() == (corpus / f"{n}.ifc").read_bytes()
        assert (tmp_path / "m" / f"{n}.json").read_bytes() == (manifestos / f"{n}.json").read_bytes()


def test_sem_rede(monkeypatch, tmp_path):
    def _proibido(*a, **k):
        raise AssertionError("acesso a rede")
    monkeypatch.setattr(socket, "socket", _proibido)
    monkeypatch.setattr(socket, "create_connection", _proibido)
    _mod().gerar_todos(tmp_path / "c", tmp_path / "m")


def test_main_retorna_zero(tmp_path):
    assert _mod().main([str(tmp_path / "c"), str(tmp_path / "m")]) == 0
    assert (tmp_path / "c" / f"{NOMES[0]}.ifc").exists() and (tmp_path / "m" / f"{NOMES[4]}.json").exists()


def test_conferir_corpus_sem_erros():
    import conferir_corpus
    corpus, manifestos = _gerado()
    assert conferir_corpus.conferir(corpus, manifestos) == []


@pytest.mark.parametrize("nome", NOMES)
def test_manifesto_campos_e_metadados(nome):
    m = _manif(nome)
    assert set(CAMPOS) <= set(m)
    assert m["nome"] == nome and m["licenca"] == "propria"
    assert "AGPL-3.0-or-later" in m["atribuicao"]
    assert m["origem"] == "scripts/gerar_modelos_erro.py"
    assert m["programa_de_origem"].startswith("IfcOpenShell")
    assert m["pode_ir_no_git"] == "nao"
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", m["data_acesso"])
    assert "erro" in m["cobre"] and m["valores_conhecidos"] and isinstance(m["esquema"], str) and m["esquema"]
    assert m["tamanho_bytes"] < 1_000_000


def test_vazio_tem_zero_bytes():
    assert _arq("erro-vazio").stat().st_size == 0
    assert _manif("erro-vazio")["tamanho_bytes"] == 0


def test_truncado_e_prefixo_da_casa_terrea():
    ref, dados = _referencia(), _arq("erro-truncado").read_bytes()
    assert 0 < len(dados) < len(ref) and ref.startswith(dados)
    assert len(dados) == len(ref) // 2
    assert b"END-ISO-10303-21" not in dados
    v = _manif("erro-truncado")["valores_conhecidos"]
    assert v["bytes_originais"] == len(ref) and v["fracao_mantida"] == pytest.approx(0.5)


def test_milimetros_so_troca_a_unidade():
    ref = _referencia().decode("utf-8")
    assert UNIDADE_M in ref, "a referência mudou: ajuste o oráculo"
    obtido = _arq("erro-milimetros").read_text(encoding="utf-8")
    assert UNIDADE_MM in obtido and UNIDADE_M not in obtido
    assert _sem_nome_de_arquivo(obtido) == _sem_nome_de_arquivo(ref.replace(UNIDADE_M, UNIDADE_MM))
    v = _manif("erro-milimetros")["valores_conhecidos"]
    assert v["unidade_declarada"] == "MILLIMETRE" and v["fator_para_metro"] == pytest.approx(0.001)
    assert v["largura_em_unidades"] == pytest.approx(10.0)


def test_milimetros_abre_com_unidade_milli():
    unidades = [u for u in _ifc("erro-milimetros").by_type("IfcSIUnit") if u.UnitType == "LENGTHUNIT"]
    assert len(unidades) == 1 and unidades[0].Prefix == "MILLI"


def test_sem_geometria_nenhum_produto_com_representacao():
    f = _ifc("erro-sem-geometria")
    assert len(f.by_type("IfcWall", include_subtypes=False)) == 4
    produtos = f.by_type("IfcProduct")
    assert len(produtos) >= 11
    assert all(p.Representation is None for p in produtos)
    m = _manif("erro-sem-geometria")
    assert m["contagens"]["IfcWall"] == 4
    assert m["valores_conhecidos"]["elementos_com_geometria"] == 0


def test_acentuado_nome_e_projeto():
    import unicodedata
    nomes = [p.name for p in _gerado()[0].iterdir() if ord(max(p.name)) > 127]
    assert nomes == ["erro-nome-com-acentuação.ifc"] and unicodedata.is_normalized("NFC", nomes[0])
    f = _ifc("erro-nome-com-acentuação")
    assert f.by_type("IfcProject")[0].Name == "Residência São João"
    assert len(f.by_type("IfcWall", include_subtypes=False)) == 4
    m = _manif("erro-nome-com-acentuação")
    assert m["valores_conhecidos"]["nome_do_projeto"] == "Residência São João"
    assert m["contagens"]["IfcWall"] == 4


@pytest.mark.parametrize("nome", ("erro-milimetros", "erro-sem-geometria", "erro-nome-com-acentuação"))
def test_contagens_batem_com_o_arquivo(nome):
    f, m = _ifc(nome), _manif(nome)
    ifc = {k: n for k, n in m["contagens"].items() if k.startswith("Ifc")}
    assert ifc == {"IfcWall": 4, "IfcSlab": 1, "IfcDoor": 1, "IfcWindow": 2, "IfcOpeningElement": 3, "IfcBuildingStorey": 1}
    for cls, n in ifc.items():
        assert len(f.by_type(cls, include_subtypes=False)) == n, cls
