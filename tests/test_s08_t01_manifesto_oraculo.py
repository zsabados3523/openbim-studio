# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo F0-S08-T01: conferência do manifesto do corpus (API fixada no cartão)."""
import hashlib
import json
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))

CAMPOS = ["nome", "origem", "versao_ou_commit", "data_acesso", "sha256", "tamanho_bytes", "licenca", "atribuicao",
          "pode_ir_no_git", "esquema", "programa_de_origem", "contagens", "valores_conhecidos", "cobre", "observacoes"]
DADOS = b"ISO-10303-21;\nDATA;\nENDSEC;\n"


def _mod():
    import conferir_corpus
    return conferir_corpus


def _cenario(tmp_path, **mudar):
    """Corpus com 1 modelo e manifesto válido; `mudar` sobrescreve campos (None remove o campo)."""
    corpus, manif = tmp_path / "corpus", tmp_path / "manifestos"
    corpus.mkdir(exist_ok=True)
    manif.mkdir(exist_ok=True)
    (corpus / "m.ifc").write_bytes(DADOS)
    m = {"nome": "m", "origem": "x", "versao_ou_commit": "v1", "data_acesso": "2026-11-14",
         "sha256": hashlib.sha256(DADOS).hexdigest(), "tamanho_bytes": len(DADOS), "licenca": "CC-BY-4.0",
         "atribuicao": "a", "pode_ir_no_git": "sim", "esquema": "IFC4", "programa_de_origem": "p",
         "contagens": {"paredes": 0}, "valores_conhecidos": {}, "cobre": ["planta"], "observacoes": ""}
    for k, v in mudar.items():
        m.pop(k) if v is None else m.__setitem__(k, v)
    (manif / "m.json").write_text(json.dumps(m), encoding="utf-8")
    return corpus, manif


def _erros(tmp_path, **mudar):
    corpus, manif = _cenario(tmp_path, **mudar)
    return _mod().conferir(corpus, manif)


def test_manifesto_valido_confere(tmp_path):
    assert _erros(tmp_path) == []


def test_carregar_manifesto_devolve_dict(tmp_path):
    _, manif = _cenario(tmp_path)
    d = _mod().carregar_manifesto(manif / "m.json")
    assert set(CAMPOS) <= set(d) and d["nome"] == "m"


def test_carregar_manifesto_json_quebrado(tmp_path):
    p = tmp_path / "x.json"
    p.write_text("{nao e json", encoding="utf-8")
    with pytest.raises(ValueError):
        _mod().carregar_manifesto(p)


@pytest.mark.parametrize("campo", CAMPOS)
def test_campo_faltando_e_rejeitado(tmp_path, campo):
    erros = _erros(tmp_path, **{campo: None})
    assert erros and any(campo in e for e in erros)


def test_licenca_fora_da_lista(tmp_path):
    erros = _erros(tmp_path, licenca="GPL-2.0-only")
    assert any("licenca" in e for e in erros)


@pytest.mark.parametrize("lic", ["CC-BY-4.0", "MIT", "Apache-2.0", "dominio-publico", "propria"])
def test_licencas_aceitas(tmp_path, lic):
    assert _erros(tmp_path, licenca=lic) == []


def test_sha256_errado(tmp_path):
    assert any("sha256" in e for e in _erros(tmp_path, sha256="0" * 64))


def test_tamanho_errado(tmp_path):
    assert any("tamanho_bytes" in e for e in _erros(tmp_path, tamanho_bytes=len(DADOS) + 1))


def test_modelo_sem_manifesto(tmp_path):
    corpus, manif = _cenario(tmp_path)
    (corpus / "outro.ifc").write_bytes(DADOS)
    erros = _mod().conferir(corpus, manif)
    assert any("sem manifesto" in e and "outro.ifc" in e for e in erros)


def test_readme_nao_e_modelo(tmp_path):
    corpus, manif = _cenario(tmp_path)
    (corpus / "README.md").write_text("oi", encoding="utf-8")
    assert _mod().conferir(corpus, manif) == []


@pytest.mark.parametrize("lic", ["CC-BY-ND-4.0", "KIT"])
def test_nd_kit_so_fora_do_git(tmp_path, lic):
    assert any("pode_ir_no_git" in e for e in _erros(tmp_path, licenca=lic, pode_ir_no_git="sim"))
    assert _erros(tmp_path, licenca=lic, pode_ir_no_git="nao") == []


def test_arquivo_ausente_so_vale_fora_do_git(tmp_path):
    corpus, manif = _cenario(tmp_path, pode_ir_no_git="nao", sha256="0" * 64, tamanho_bytes=1)
    (corpus / "m.ifc").unlink()
    assert _mod().conferir(corpus, manif) == []  # ausente + nao = so aviso, soma nao confere
    d = json.loads((manif / "m.json").read_text(encoding="utf-8"))
    d["pode_ir_no_git"] = "sim"
    (manif / "m.json").write_text(json.dumps(d), encoding="utf-8")
    assert _mod().conferir(corpus, manif)


def test_casa_simples_do_repositorio_confere():
    assert (RAIZ / "corpus/manifestos/casa-simples.json").exists()
    assert _mod().conferir(RAIZ / "tests/amostras", RAIZ / "corpus/manifestos") == []


def test_readme_do_corpus_explica_formato():
    t = (RAIZ / "corpus/README.md").read_text(encoding="utf-8")
    assert "manifesto" in t and "conferir_corpus" in t and "sha256" in t
