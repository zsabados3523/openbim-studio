# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo F0-S08-T04b: `scripts/gerar_modelos_extra.py` (2 modelos IFC4 próprios: estrutura e paredes em camadas).
Contrato fixado no pedido do T04b. O implementador não edita este arquivo."""
import atexit
import functools
import json
import re
import shutil
import socket
import sys
import tempfile
from pathlib import Path

import numpy as np
import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))

NOMES = ("estrutura-pilares-vigas", "paredes-com-camadas")
CONTAGENS = {
    "estrutura-pilares-vigas": {"IfcColumn": 4, "IfcBeam": 4, "IfcBuildingStorey": 1},
    "paredes-com-camadas": {"IfcWall": 4, "IfcMaterialLayerSet": 1, "IfcMaterialLayer": 3, "IfcBuildingStorey": 1},
}
VALORES = {
    "estrutura-pilares-vigas": {"quantidade_pilares": 4, "quantidade_vigas": 4, "altura_pilar_m": 3.0,
                                "vao_x_m": 6.0, "vao_y_m": 4.0, "secao_pilar_m": 0.3},
    "paredes-com-camadas": {"espessura_total_m": 0.18, "camadas": 3, "pe_direito_m": 2.8},
}
CAMPOS = ("nome", "origem", "versao_ou_commit", "data_acesso", "sha256", "tamanho_bytes", "licenca", "atribuicao",
          "pode_ir_no_git", "esquema", "programa_de_origem", "contagens", "valores_conhecidos", "cobre", "observacoes")


def _mod():
    import gerar_modelos_extra
    return gerar_modelos_extra


@functools.lru_cache(maxsize=None)
def _gerado():
    base = Path(tempfile.mkdtemp(prefix="s08t04b_"))
    atexit.register(shutil.rmtree, base, ignore_errors=True)
    _mod().gerar_todos(base / "corpus", base / "manifestos")
    return base / "corpus", base / "manifestos"


def _ifc(nome):
    import ifcopenshell
    return ifcopenshell.open(str(_gerado()[0] / f"{nome}.ifc"))


def _manif(nome):
    return json.loads((_gerado()[1] / f"{nome}.json").read_text(encoding="utf-8"))


def _bbox(el):
    import ifcopenshell.geom
    cfg = ifcopenshell.geom.settings()
    cfg.set("use-world-coords", True)
    v = np.array(ifcopenshell.geom.create_shape(cfg, el).geometry.verts, dtype=float).reshape(-1, 3)
    return v.min(axis=0), v.max(axis=0)


def _uniao(elementos):
    caixas = [_bbox(e) for e in elementos]
    return np.min([c[0] for c in caixas], axis=0), np.max([c[1] for c in caixas], axis=0)


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
    assert (tmp_path / "c" / f"{NOMES[0]}.ifc").exists() and (tmp_path / "m" / f"{NOMES[1]}.json").exists()


def test_conferir_corpus_sem_erros():
    import conferir_corpus
    corpus, manifestos = _gerado()
    assert conferir_corpus.conferir(corpus, manifestos) == []


@pytest.mark.parametrize("nome", NOMES)
def test_manifesto_campos_e_metadados(nome):
    m = _manif(nome)
    assert set(CAMPOS) <= set(m)
    assert m["nome"] == nome and m["licenca"] == "propria" and m["esquema"] == "IFC4"
    assert "AGPL-3.0-or-later" in m["atribuicao"]
    assert m["origem"] == "scripts/gerar_modelos_extra.py"
    assert m["programa_de_origem"].startswith("IfcOpenShell")
    assert m["pode_ir_no_git"] == "nao"
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", m["data_acesso"])
    assert m["cobre"] and m["valores_conhecidos"]
    assert m["tamanho_bytes"] < 1_000_000


@pytest.mark.parametrize("nome", NOMES)
def test_contagens_batem_com_o_arquivo(nome):
    f, m = _ifc(nome), _manif(nome)
    for cls, n in CONTAGENS[nome].items():
        assert m["contagens"][cls] == n, cls
        assert len(f.by_type(cls, include_subtypes=False)) == n, cls
    for cls, n in m["contagens"].items():
        if cls.startswith("Ifc"):
            assert len(f.by_type(cls, include_subtypes=False)) == n, cls


@pytest.mark.parametrize("nome", NOMES)
def test_valores_conhecidos(nome):
    v = _manif(nome)["valores_conhecidos"]
    for k, esperado in VALORES[nome].items():
        assert v[k] == pytest.approx(esperado), k


@pytest.mark.parametrize("nome", NOMES)
def test_unidade_metro(nome):
    unidades = [u for u in _ifc(nome).by_type("IfcSIUnit") if u.UnitType == "LENGTHUNIT"]
    assert len(unidades) == 1 and unidades[0].Prefix is None


def test_pilares_geometria():
    f = _ifc("estrutura-pilares-vigas")
    cantos = []
    for p in f.by_type("IfcColumn", include_subtypes=False):
        lo, hi = _bbox(p)
        e = hi - lo
        assert e[2] == pytest.approx(3.0, abs=0.01) and e[0] == pytest.approx(0.3, abs=0.01) and e[1] == pytest.approx(0.3, abs=0.01)
        cantos.append(((lo + hi) / 2)[:2])
    cantos = np.array(cantos)
    assert np.ptp(cantos[:, 0]) == pytest.approx(6.0, abs=0.01) and np.ptp(cantos[:, 1]) == pytest.approx(4.0, abs=0.01)
    assert len({tuple(np.round(c, 2)) for c in cantos}) == 4


def test_vigas_geometria():
    f = _ifc("estrutura-pilares-vigas")
    vigas = f.by_type("IfcBeam", include_subtypes=False)
    comprimentos = sorted(float(max((hi - lo)[:2])) for lo, hi in map(_bbox, vigas))
    assert comprimentos[:2] == pytest.approx([3.7, 3.7], abs=0.3)  # vigas do vão de 4 m
    assert comprimentos[2:] == pytest.approx([5.7, 5.7], abs=0.3)  # vigas do vão de 6 m
    lo, hi = _uniao(vigas)
    assert hi[2] == pytest.approx(3.0, abs=0.01) and (hi - lo)[2] <= 3.0 / 4  # no topo dos pilares
    lo_t, hi_t = _uniao(f.by_type("IfcColumn", include_subtypes=False) + vigas)
    assert hi_t[0] - lo_t[0] == pytest.approx(6.3, abs=0.05) and hi_t[1] - lo_t[1] == pytest.approx(4.3, abs=0.05)


def test_camadas_do_material():
    f = _ifc("paredes-com-camadas")
    camadas = f.by_type("IfcMaterialLayer", include_subtypes=False)
    assert sum(c.LayerThickness for c in camadas) == pytest.approx(0.18)
    assert all(c.LayerThickness > 0 and c.Material is not None for c in camadas)
    assert len({c.Material.Name for c in camadas}) >= 2
    conjunto = f.by_type("IfcMaterialLayerSet", include_subtypes=False)[0]
    assert len(conjunto.MaterialLayers) == 3


def test_toda_parede_usa_o_conjunto_de_camadas():
    import ifcopenshell.util.element as ue
    f = _ifc("paredes-com-camadas")
    for p in f.by_type("IfcWall", include_subtypes=False):
        mat = ue.get_material(p)
        conjunto = getattr(mat, "ForLayerSet", mat)
        assert conjunto is not None and conjunto.is_a("IfcMaterialLayerSet"), p.Name


def test_paredes_geometria():
    f = _ifc("paredes-com-camadas")
    for p in f.by_type("IfcWall", include_subtypes=False):
        lo, hi = _bbox(p)
        e = hi - lo
        assert e[2] == pytest.approx(2.8, abs=0.01)
        assert min(e[0], e[1]) == pytest.approx(0.18, abs=0.005), p.Name
    lo, hi = _uniao(f.by_type("IfcWall", include_subtypes=False))
    assert sorted((hi - lo)[:2]) == pytest.approx([4.0, 5.0], abs=0.25)
