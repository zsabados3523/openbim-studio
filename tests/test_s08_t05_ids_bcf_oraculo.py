# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oraculo F0-S08-T05: gerador `scripts/gerar_casos_ids_bcf.py` (casos IDS 1.0 e BCF 2.1/3.0 proprios).
Contrato fixado no cartao F0-S08-T05. O implementador NAO edita este arquivo.
ifctester e lark NAO estao instalados: o oraculo confere o IDS por XML (biblioteca padrao) e avalia as
regras com um avaliador minimo proprio (facets entity e attribute, so valores simples) sobre o IFC."""
import atexit
import functools
import json
import shutil
import socket
import sys
import tempfile
import time
import uuid
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))

NS_IDS = "{http://standards.buildingsmart.org/IDS}"
IDS_ARQUIVOS = {  # arquivo -> (modelo, o IDS inteiro passa?)
    "casa-terrea-passa.ids": ("casa-terrea", True),
    "casa-terrea-falha.ids": ("casa-terrea", False),
    "sobrado-passa.ids": ("sobrado", True),
}
BCF_ARQUIVOS = {"topicos-2-1.bcf": "2.1", "topicos-3-0.bcf": "3.0"}
MODELO_BCF = "casa-terrea"
SELECOES = [1, 2, 4]  # quantos GUIDs cada um dos 3 topicos aponta (ordenado)


def _mod():
    import gerar_casos_ids_bcf
    return gerar_casos_ids_bcf


@functools.lru_cache(maxsize=None)
def _gerado():
    """Gera os modelos do T04 e os casos uma vez; devolve (modelos, ids, bcf, segundos)."""
    import gerar_modelos
    base = Path(tempfile.mkdtemp(prefix="s08t05_"))
    atexit.register(shutil.rmtree, base, ignore_errors=True)
    gerar_modelos.gerar_todos(base / "modelos", base / "man")
    t0 = time.monotonic()
    _mod().gerar_todos(base / "modelos", base / "ids", base / "bcf")
    return base / "modelos", base / "ids", base / "bcf", time.monotonic() - t0


def _manif(pasta):
    return json.loads((pasta / "manifesto.json").read_text(encoding="utf-8"))


def _ifc(nome):
    import ifcopenshell
    return ifcopenshell.open(str(_gerado()[0] / f"{nome}.ifc"))


def _tag(e):
    return e.tag.split("}")[-1]


def _simples(facet, filho):
    """Texto de <filho><simpleValue>..</simpleValue></filho>, ou None se ausente."""
    n = facet.find(f"{NS_IDS}{filho}")
    if n is None:
        return None
    v = n.find(f"{NS_IDS}simpleValue")
    assert v is not None and v.text, f"{filho} so aceita simpleValue neste corpus"
    return v.text


def _avaliar(ids_path, modelo):
    """Avaliador minimo: {nome_da_spec: (aplicaveis, passam)}."""
    raiz = ET.parse(ids_path).getroot()
    res = {}
    for spec in raiz.find(f"{NS_IDS}specifications"):
        ent = spec.find(f"{NS_IDS}applicability/{NS_IDS}entity")
        classe = _simples(ent, "name")
        aplic = [e for e in modelo.by_type("IfcProduct") if e.is_a().upper() == classe]
        reqs = list(spec.find(f"{NS_IDS}requirements"))
        passam = 0
        for e in aplic:
            ok = True
            for r in reqs:
                assert _tag(r) == "attribute", "so facet attribute em requirements"
                val = getattr(e, _simples(r, "name"), None)
                esperado = _simples(r, "value")
                ok &= val is not None and (esperado is None or str(val) == esperado)
            passam += ok
        res[spec.get("name")] = (len(aplic), passam)
    return res


# ---------------------------------------------------------------- API
def test_api_publica():
    m = _mod()
    assert callable(m.gerar_todos) and callable(m.main)


def test_main_devolve_zero_e_so_escreve_nas_pastas(tmp_path):
    import gerar_modelos
    gerar_modelos.gerar_todos(tmp_path / "modelos", tmp_path / "man")
    assert _mod().main([str(tmp_path / "modelos"), str(tmp_path / "ids"), str(tmp_path / "bcf")]) == 0
    assert {p.name for p in (tmp_path / "ids").iterdir()} == set(IDS_ARQUIVOS) | {"manifesto.json"}
    assert {p.name for p in (tmp_path / "bcf").iterdir()} == set(BCF_ARQUIVOS) | {"manifesto.json"}


# ---------------------------------------------------------------- IDS
def test_ids_arquivos_exatos():
    ids = _gerado()[1]
    assert {p.name for p in ids.iterdir()} == set(IDS_ARQUIVOS) | {"manifesto.json"}


@pytest.mark.parametrize("arq", sorted(IDS_ARQUIVOS))
def test_ids_estrutura_xml(arq):
    raiz = ET.parse(_gerado()[1] / arq).getroot()
    assert raiz.tag == f"{NS_IDS}ids"
    assert raiz.find(f"{NS_IDS}info/{NS_IDS}title").text
    specs = raiz.find(f"{NS_IDS}specifications")
    lista = list(specs)
    assert len(lista) >= 2
    nomes = [s.get("name") for s in lista]
    assert all(nomes) and len(set(nomes)) == len(nomes)
    for s in lista:
        assert _tag(s) == "specification" and s.get("ifcVersion") == "IFC4"
        assert s.find(f"{NS_IDS}applicability/{NS_IDS}entity") is not None
        assert s.find(f"{NS_IDS}requirements") is not None and len(s.find(f"{NS_IDS}requirements")) >= 1


@pytest.mark.parametrize("arq", sorted(IDS_ARQUIVOS))
def test_ids_resultado_esperado_bate_com_o_modelo(arq):
    modelo_nome, passa = IDS_ARQUIVOS[arq]
    ids = _gerado()[1]
    res = _avaliar(ids / arq, _ifc(modelo_nome))
    caso = next(c for c in _manif(ids)["casos"] if c["arquivo"] == arq)
    assert caso["modelo"] == modelo_nome and caso["passa"] is passa
    assert set(caso["especificacoes"]) == set(res)
    for nome, (aplic, ok) in res.items():
        esp = caso["especificacoes"][nome]
        assert aplic >= 1  # nenhuma regra vazia: o resultado nao pode passar "por falta de elementos"
        assert (esp["aplicaveis"], esp["passam"]) == (aplic, ok), nome
        assert esp["passa"] is (ok == aplic)
    assert all(ok == aplic for aplic, ok in res.values()) is passa
    if not passa:  # caso de falha tem regra que passa E regra que falha
        assert any(ok == a for a, ok in res.values()) and any(ok < a for a, ok in res.values())


def test_ids_valida_com_ifctester_se_instalado():
    ifctester = pytest.importorskip("ifctester")
    for arq, (modelo_nome, passa) in IDS_ARQUIVOS.items():
        ids = ifctester.ids.open(str(_gerado()[1] / arq))
        ids.validate(_ifc(modelo_nome))
        assert all(s.status for s in ids.specifications) is passa, arq


# ---------------------------------------------------------------- BCF
def _guids_ifc(nome):
    return {e.GlobalId for e in _ifc(nome).by_type("IfcRoot")}


def _lido(zf, nome):
    return ET.fromstring(zf.read(nome))


@pytest.mark.parametrize("arq,versao", sorted(BCF_ARQUIVOS.items()))
def test_bcf_estrutura_minima(arq, versao):
    with zipfile.ZipFile(_gerado()[2] / arq) as zf:
        assert zf.testzip() is None
        nomes = zf.namelist()
        assert "bcf.version" in nomes
        ver = _lido(zf, "bcf.version")
        assert ver.get("VersionId") == versao
        pastas = {n.split("/")[0] for n in nomes if "/" in n}
        assert len(pastas) == 3
        for p in pastas:
            uuid.UUID(p)  # nome da pasta = GUID do topico
            mk = _lido(zf, f"{p}/markup.bcf")
            topico = next(e for e in mk.iter() if _tag(e) == "Topic")
            assert topico.get("Guid") == p
            assert next(e for e in topico.iter() if _tag(e) == "Title").text
            vps = [e.text for e in mk.iter() if _tag(e) == "Viewpoint" and e.text]
            assert vps and all(f"{p}/{v}" in nomes for v in vps)
            for v in vps:
                vi = _lido(zf, f"{p}/{v}")
                assert _tag(vi) == "VisualizationInfo"
                assert any(_tag(e) == "Component" and e.get("IfcGuid") for e in vi.iter())


@pytest.mark.parametrize("arq,versao", sorted(BCF_ARQUIVOS.items()))
def test_bcf_topicos_apontam_para_guids_reais(arq, versao):
    pasta = _gerado()[2]
    reais = _guids_ifc(MODELO_BCF)
    caso = next(c for c in _manif(pasta)["casos"] if c["arquivo"] == arq)
    assert caso["versao_bcf"] == versao and caso["modelo"] == MODELO_BCF and caso["quantidade_topicos"] == 3
    achados = {}
    with zipfile.ZipFile(pasta / arq) as zf:
        for n in zf.namelist():
            if n.endswith(".bcfv"):
                achados[n.split("/")[0]] = sorted(e.get("IfcGuid") for e in _lido(zf, n).iter() if _tag(e) == "Component" and e.get("IfcGuid"))
    assert sorted(len(g) for g in achados.values()) == SELECOES
    assert {g for gs in achados.values() for g in gs} <= reais
    assert {t["guid"]: sorted(t["ifc_guids"]) for t in caso["topicos"]} == achados


# ---------------------------------------------------------------- geral
def _bytes(pasta):
    return {p.name: p.read_bytes() for p in sorted(pasta.iterdir())}


def test_deterministico_byte_a_byte(tmp_path):
    modelos = _gerado()[0]
    _mod().gerar_todos(modelos, tmp_path / "ids", tmp_path / "bcf")
    assert _bytes(tmp_path / "ids") == _bytes(_gerado()[1])
    assert _bytes(tmp_path / "bcf") == _bytes(_gerado()[2])


def test_rapido_e_sem_rede(tmp_path, monkeypatch):
    assert _gerado()[3] < 60

    def _proibido(*a, **k):
        raise AssertionError("rede proibida")
    monkeypatch.setattr(socket.socket, "connect", _proibido)
    monkeypatch.setattr(socket, "getaddrinfo", _proibido)
    _mod().gerar_todos(_gerado()[0], tmp_path / "ids", tmp_path / "bcf")
