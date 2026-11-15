# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo F0-S08-T04: gerador `scripts/gerar_modelos.py` (5 modelos IFC4 próprios, sem rede, determinísticos).
Contrato (API, nomes e valores) fixado no cartão F0-S08-T04. O implementador não edita este arquivo."""
import atexit
import functools
import json
import math
import re
import shutil
import socket
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))

NOMES = ("casa-terrea", "sobrado", "moveis-repetidos", "parede-curva", "laje-com-furo")
# contagens exatas exigidas por modelo (além delas, TODA chave "Ifc*" de `contagens` deve bater com o arquivo)
CONTAGENS = {
    "casa-terrea": {"IfcWall": 4, "IfcSlab": 1, "IfcDoor": 1, "IfcWindow": 2, "IfcOpeningElement": 3, "IfcBuildingStorey": 1},
    "sobrado": {"IfcBuildingStorey": 2, "IfcStair": 1, "IfcRoof": 1},
    "moveis-repetidos": {"IfcFurniture": 8, "IfcRepresentationMap": 1, "IfcMappedItem": 8},
    "parede-curva": {"IfcWall": 1},
    "laje-com-furo": {"IfcSlab": 1, "IfcOpeningElement": 1},
}
VALORES = {  # chaves numéricas obrigatórias em `valores_conhecidos`
    "casa-terrea": ("area_piso_m2", "pe_direito_m", "largura_m", "profundidade_m"),
    "sobrado": ("pe_direito_m", "elevacao_pavimento_superior_m", "aguas_telhado"),
    "moveis-repetidos": ("quantidade_moveis",),
    "parede-curva": ("raio_m", "angulo_graus", "flecha_m", "altura_m"),
    "laje-com-furo": ("area_bruta_m2", "area_furo_m2", "area_liquida_m2"),
}


def _mod():
    import gerar_modelos
    return gerar_modelos


@functools.lru_cache(maxsize=None)
def _gerado():
    """Gera os 5 modelos uma vez numa pasta temporária; devolve (corpus, manifestos, segundos)."""
    base = Path(tempfile.mkdtemp(prefix="s08t04_"))
    atexit.register(shutil.rmtree, base, ignore_errors=True)
    t0 = time.monotonic()
    _mod().gerar_todos(base / "corpus", base / "manifestos")
    return base / "corpus", base / "manifestos", time.monotonic() - t0


def _ifc(nome):
    import ifcopenshell
    return ifcopenshell.open(str(_gerado()[0] / f"{nome}.ifc"))


def _manif(nome):
    return json.loads((_gerado()[1] / f"{nome}.json").read_text(encoding="utf-8"))


def _malha(*elementos):
    """Vértices (N,3) e triângulos (M,3) em coordenadas de mundo, em metros, de todos os elementos com geometria."""
    import ifcopenshell.geom
    cfg = ifcopenshell.geom.settings()
    cfg.set("use-world-coords", True)
    verts, faces, base = [], [], 0
    for el in elementos:
        if getattr(el, "Representation", None) is None:
            continue
        g = ifcopenshell.geom.create_shape(cfg, el).geometry
        v = np.array(g.verts, dtype=float).reshape(-1, 3)
        verts.append(v)
        faces.append(np.array(g.faces, dtype=int).reshape(-1, 3) + base)
        base += len(v)
    assert verts, "nenhum elemento com geometria"
    return np.vstack(verts), np.vstack(faces)


def _partes(el):
    import ifcopenshell.util.element as ue
    return [el, *ue.get_decomposition(el)]


def _normais_areas(v, f):
    t = v[f]
    n = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
    norma = np.linalg.norm(n, axis=1)
    ok = norma > 1e-12
    return t[ok], n[ok] / norma[ok, None], norma[ok] / 2


def _extensao(v):
    return v.max(axis=0) - v.min(axis=0)


def _area_xy_bbox(v):
    e = _extensao(v)
    return e[0] * e[1]


def _inclinacoes(v, f):
    """Agrupa normais voltadas para cima e inclinadas (telhado em águas); tolerância ~2,5 graus."""
    _, n, _ = _normais_areas(v, f)
    grupos = []
    for k in n[(n[:, 2] > 0.05) & (n[:, 2] < 0.99)]:
        if not any(float(np.dot(k, g)) > 0.999 for g in grupos):
            grupos.append(k)
    return grupos


def _flecha(v):
    """Maior distância (planta) de um vértice à corda entre os dois vértices mais afastados."""
    xy = np.unique(np.round(v[:, :2], 6), axis=0)
    d = np.linalg.norm(xy[:, None] - xy[None], axis=2)
    i, j = np.unravel_index(d.argmax(), d.shape)
    u = (xy[j] - xy[i]) / d[i, j]
    r = xy - xy[i]
    return float(np.abs(u[0] * r[:, 1] - u[1] * r[:, 0]).max())


# --- gerais ---------------------------------------------------------------------------------------------

def test_api_do_modulo():
    m = _mod()
    assert tuple(m.NOMES) == NOMES
    assert callable(m.gerar_todos) and callable(m.main)


def test_gera_arquivos_pequenos_e_rapido():
    corpus, manif, seg = _gerado()
    for n in NOMES:
        arq = corpus / f"{n}.ifc"
        assert arq.is_file() and 0 < arq.stat().st_size < 1_000_000, n
        assert (manif / f"{n}.json").is_file(), n
    assert {p.name for p in corpus.iterdir()} == {f"{n}.ifc" for n in NOMES}  # nada além dos 5 modelos
    assert seg < 60, f"geração levou {seg:.1f} s"


@pytest.mark.parametrize("nome", NOMES)
def test_abre_no_ifcopenshell_em_ifc4(nome):
    f = _ifc(nome)
    assert f.schema == "IFC4"
    assert len(f.by_type("IfcProject")) == 1 and f.by_type("IfcBuildingStorey")


def test_manifestos_passam_na_conferencia_da_t01():
    import conferir_corpus
    corpus, manif, _ = _gerado()
    assert conferir_corpus.conferir(corpus, manif) == []


@pytest.mark.parametrize("nome", NOMES)
def test_manifesto_campos_e_licenca(nome):
    m = _manif(nome)
    assert m["nome"] == nome
    assert m["licenca"] == "propria" and "AGPL-3.0-or-later" in m["atribuicao"]
    assert m["esquema"] == "IFC4" and m["programa_de_origem"].startswith("IfcOpenShell")
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", m["data_acesso"])  # data fixa (determinismo), nunca "hoje"
    assert m["origem"] == "scripts/gerar_modelos.py"
    assert isinstance(m["valores_conhecidos"], dict) and m["valores_conhecidos"]
    assert isinstance(m["cobre"], list) and m["cobre"]
    for k in VALORES[nome]:
        assert isinstance(m["valores_conhecidos"][k], (int, float)), k


@pytest.mark.parametrize("nome", NOMES)
def test_contagens_batem_com_o_arquivo(nome):
    f, m = _ifc(nome), _manif(nome)
    c = m["contagens"]
    for classe, n in CONTAGENS[nome].items():
        assert c[classe] == n, f"manifesto {classe}"
    for classe, n in c.items():
        if classe.startswith("Ifc"):
            assert len(f.by_type(classe, include_subtypes=False)) == n, classe


def test_geracao_repetida_e_identica_byte_a_byte_e_sem_rede(monkeypatch):
    def sem_rede(*a, **k):
        raise AssertionError("o gerador tentou usar a rede")
    monkeypatch.setattr(socket.socket, "connect", sem_rede)
    base = Path(tempfile.mkdtemp(prefix="s08t04b_"))
    try:
        _mod().gerar_todos(base / "corpus", base / "manifestos")
        c1, m1, _ = _gerado()
        for n in NOMES:
            assert (base / "corpus" / f"{n}.ifc").read_bytes() == (c1 / f"{n}.ifc").read_bytes(), n
            assert (base / "manifestos" / f"{n}.json").read_bytes() == (m1 / f"{n}.json").read_bytes(), n
    finally:
        shutil.rmtree(base, ignore_errors=True)


# --- por modelo -----------------------------------------------------------------------------------------

def test_casa_terrea_60m2_e_pe_direito():
    f, v = _ifc("casa-terrea"), _manif("casa-terrea")["valores_conhecidos"]
    assert v["area_piso_m2"] == pytest.approx(60.0, abs=0.1)
    assert v["largura_m"] * v["profundidade_m"] == pytest.approx(v["area_piso_m2"], abs=0.1)
    laje = f.by_type("IfcSlab")[0]
    assert _area_xy_bbox(_malha(laje)[0]) == pytest.approx(60.0, abs=0.1)  # medido no IFC, não no manifesto
    assert v["pe_direito_m"] == pytest.approx(2.8, abs=0.01)
    for p in f.by_type("IfcWall"):
        assert _extensao(_malha(p)[0])[2] == pytest.approx(v["pe_direito_m"], abs=0.02), p.Name
    assert len(f.by_type("IfcRelVoidsElement")) == 3 and len(f.by_type("IfcRelFillsElement")) == 3


def test_sobrado_escada_e_telhado_de_4_aguas():
    f, v = _ifc("sobrado"), _manif("sobrado")["valores_conhecidos"]
    c = _manif("sobrado")["contagens"]
    assert c["IfcWall"] >= 8 and c["IfcSlab"] >= 2  # 4 paredes e 1 laje por pavimento, no mínimo
    elev = sorted(s.Elevation for s in f.by_type("IfcBuildingStorey"))
    assert elev[0] == pytest.approx(0.0, abs=0.01)
    assert elev[1] == pytest.approx(v["elevacao_pavimento_superior_m"], abs=0.01) and elev[1] > 2.0
    assert v["aguas_telhado"] == 4
    telhado = _malha(*_partes(f.by_type("IfcRoof")[0]))
    assert len(_inclinacoes(*telhado)) == 4  # 4 planos inclinados distintos voltados para cima
    escada = _malha(*_partes(f.by_type("IfcStair")[0]))[0]
    assert _extensao(escada)[2] >= 0.9 * elev[1]  # a escada vence o desnível entre os pavimentos


def test_moveis_repetidos_compartilham_uma_representacao():
    f = _ifc("moveis-repetidos")
    import ifcopenshell.util.placement as up
    moveis = f.by_type("IfcFurniture", include_subtypes=False)
    assert len(moveis) == 8 and _manif("moveis-repetidos")["valores_conhecidos"]["quantidade_moveis"] == 8
    fontes = set()
    for m in moveis:
        itens = [i for r in m.Representation.Representations for i in r.Items]
        assert itens and all(i.is_a("IfcMappedItem") for i in itens), m.Name
        fontes |= {i.MappingSource.id() for i in itens}
    assert len(fontes) == 1 and len(f.by_type("IfcRepresentationMap")) == 1
    posicoes = {tuple(np.round(up.get_local_placement(m.ObjectPlacement)[:3, 3], 3)) for m in moveis}
    assert len(posicoes) == 8  # cada móvel em lugar diferente


def test_parede_curva_e_curva_de_verdade():
    f, v = _ifc("parede-curva"), _manif("parede-curva")["valores_conhecidos"]
    arco = any(s.is_a("IfcArcIndex") for c in f.by_type("IfcIndexedPolyCurve") for s in c.Segments)
    poligonal = any(len(c.Segments) >= 8 for c in f.by_type("IfcIndexedPolyCurve"))
    assert arco or f.by_type("IfcTrimmedCurve") or poligonal, "sem arco IFC nem poligonal com 8 segmentos ou mais"
    esperada = v["raio_m"] * (1 - math.cos(math.radians(v["angulo_graus"]) / 2))
    assert v["flecha_m"] == pytest.approx(esperada, abs=0.01)  # manifesto coerente com a construção
    verts = _malha(f.by_type("IfcWall")[0])[0]
    medida = _flecha(verts)
    assert medida > 0.5 and medida == pytest.approx(v["flecha_m"], abs=0.25)  # parede reta daria < 0,3
    assert _extensao(verts)[2] == pytest.approx(v["altura_m"], abs=0.02)


def test_laje_com_furo():
    f, v = _ifc("laje-com-furo"), _manif("laje-com-furo")["valores_conhecidos"]
    laje, furo = f.by_type("IfcSlab")[0], f.by_type("IfcOpeningElement")[0]
    rel = f.by_type("IfcRelVoidsElement")
    assert len(rel) == 1 and rel[0].RelatingBuildingElement == laje and rel[0].RelatedOpeningElement == furo
    assert v["area_furo_m2"] >= 0.5
    assert v["area_liquida_m2"] == pytest.approx(v["area_bruta_m2"] - v["area_furo_m2"], abs=0.01)
    verts, faces = _malha(laje)  # a geometria já vem com o furo subtraído
    t, n, area = _normais_areas(verts, faces)
    topo = (n[:, 2] > 0.99) & (np.abs(t[:, :, 2].mean(axis=1) - verts[:, 2].max()) < 1e-6)
    assert area[topo].sum() == pytest.approx(v["area_liquida_m2"], abs=0.1)
    assert _area_xy_bbox(verts) == pytest.approx(v["area_bruta_m2"], abs=0.1)
