# SPDX-License-Identifier: AGPL-3.0-or-later
"""Testes de carga de malhas em processo separado, casos P1 a P12, sem tela.

Números congelados: não afrouxar número nem remover caso.
As guardas de ativação (requer_processo, requer_limite) saíram na RG-03: módulo ou parâmetro ausente agora FALHA, não pula.
Peça lenta injetada no filho: OBIM_TESTE_PECA_LENTA="<guid>=<s>[,...]"; filho que cai: OBIM_TESTE_MATAR_FILHO="<guid>".
Teste lento (P6): OBIM_TESTES_LENTOS=1.

P13 a P18 (defeitos achados em revisão). Cada um é `xfail(strict=True)` até a
a correção: quando passar, o xfail estrito vira falha e avisa para tirar a marca. Gancho de teste novo:
OBIM_TESTE_FALHAR_CAIXA="<guid>" (o filho da caixa falha nessa peça). As guardas `requer_caixa_falha` e `OBIM_FORCAR_GUARDAS`
saíram com a abertura por processo: o recurso já está no código principal.
"""
import inspect
import multiprocessing
import os
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pytest

import ifcopenshell
import ifcopenshell.api

sys.path.insert(0, str(Path(__file__).resolve().parent))
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "viewport"))

from test_viewport_adaptador import _ViewportFalso  # noqa: E402
from test_viewport_carregador import (  # noqa: E402,F401  (modelos e fixtures compartilhados)
    CarregadorMalhas, LoteMalha, ResumoCarga, _carregar, _novo, _percorrer, _por_produto, m600, m3000,
    _caixa, mab,
)
from test_viewport_responsivo import MAX_MS, P95_MS, _medir, _publicar, app  # noqa: E402,F401

_PARAMS = inspect.signature(CarregadorMalhas.__init__).parameters
assert "limite_peca_s" in _PARAMS and "max_bytes_lote" in _PARAMS, "CarregadorMalhas sem limite_peca_s/max_bytes_lote"


def _aguarda_e(item):
    return pytest.mark.xfail(strict=True, reason=f"aguarda correção: {item}")


def _lento_ou_pular():
    if os.environ.get("OBIM_TESTES_LENTOS") != "1":
        pytest.skip("teste lento: defina OBIM_TESTES_LENTOS=1 (lentidão real, só local)")


def _kw_sem_limite():
    return {"limite_peca_s": None}


# ---------- modelos gerados no próprio teste ----------
MM = 1000.0  # o projeto de teste está em milímetros: as medidas abaixo são em metros


def _caixa_malha(f, dx, dy, dz):
    """Caixa fechada como IfcPolygonalFaceSet (malha de 6 faces, 12 triângulos)."""
    pts = f.createIfcCartesianPointList3D(CoordList=[(x * dx * MM, y * dy * MM, z * dz * MM) for z in (0, 1) for y in (0, 1) for x in (0, 1)])
    quads = [(1, 3, 4, 2), (5, 6, 8, 7), (1, 2, 6, 5), (3, 7, 8, 4), (1, 5, 7, 3), (2, 4, 8, 6)]
    faces = [f.createIfcIndexedPolygonalFace(CoordIndex=list(q)) for q in quads]
    return f.createIfcPolygonalFaceSet(Coordinates=pts, Closed=True, Faces=faces)


def _mapa(f, corpo, dx, dy, dz):
    rep = f.createIfcShapeRepresentation(corpo, "Body", "Tessellation", [_caixa_malha(f, dx, dy, dz)])
    origem = f.createIfcAxis2Placement3D(Location=f.createIfcCartesianPoint((0.0, 0.0, 0.0)))
    return f.createIfcRepresentationMap(MappingOrigin=origem, MappedRepresentation=rep)


def _instancia(f, corpo, mapa, pos, nome):
    """Produto cuja geometria é um item mapeado (a malha vem atrás de um IfcMappedItem)."""
    api = ifcopenshell.api.run
    alvo = f.createIfcCartesianTransformationOperator3D(LocalOrigin=f.createIfcCartesianPoint((1.0 * MM, 0.5 * MM, 0.25 * MM)))
    item = f.createIfcMappedItem(MappingSource=mapa, MappingTarget=alvo)
    rep = f.createIfcShapeRepresentation(corpo, "Body", "MappedRepresentation", [item])
    p = api("root.create_entity", f, ifc_class="IfcWall", name=nome)
    api("geometry.assign_representation", f, product=p, representation=rep)
    m = np.eye(4)
    m[:3, 3] = pos  # a API recebe a posição em metros
    api("geometry.edit_object_placement", f, product=p, matrix=m)
    return p


def _gerar_mapeadas(caminho, normais=12, lentas=1):
    """`normais` cópias de um cubo 1x1x1 (mesmo item mapeado) e `lentas` cópias de uma caixa 2x1x3 (outro item
    mapeado, a família da peça lenta). Devolve (caminho, [(id_step, guid) das lentas])."""
    f, corpo = _novo()
    cubo, grande = _mapa(f, corpo, 1.0, 1.0, 1.0), _mapa(f, corpo, 2.0, 1.0, 3.0)
    for i in range(normais):
        _instancia(f, corpo, cubo, (i * 3.0, 0.0, 0.0), f"normal {i}")
    lentos = [_instancia(f, corpo, grande, (k * 5.0, 10.0, 0.0), f"lenta {k}") for k in range(lentas)]
    f.write(str(caminho))
    return caminho, [(p.id(), p.GlobalId) for p in lentos]


def _gerar_grade(caminho, n=120):
    """Único produto: grade de n x n faces poligonais (n*n*2 triângulos). Lenta na biblioteca opencascade."""
    f, corpo = _novo()
    pts = f.createIfcCartesianPointList3D(CoordList=[(i * 0.1 * MM, j * 0.1 * MM, 0.0) for j in range(n + 1) for i in range(n + 1)])
    faces = [f.createIfcIndexedPolygonalFace(CoordIndex=[j * (n + 1) + i + 1, j * (n + 1) + i + 2,
                                                         (j + 1) * (n + 1) + i + 2, (j + 1) * (n + 1) + i + 1])
             for j in range(n) for i in range(n)]
    rep = f.createIfcShapeRepresentation(corpo, "Body", "Tessellation",
                                         [f.createIfcPolygonalFaceSet(Coordinates=pts, Closed=False, Faces=faces)])
    p = ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcWall", name="grade")
    ifcopenshell.api.run("geometry.assign_representation", f, product=p, representation=rep)
    f.write(str(caminho))
    return caminho, p.id()


@pytest.fixture(scope="session")
def mapeadas1(tmp_path_factory):
    return _gerar_mapeadas(tmp_path_factory.mktemp("map1") / "map1.ifc", lentas=1)


@pytest.fixture(scope="session")
def mapeadas2(tmp_path_factory):
    return _gerar_mapeadas(tmp_path_factory.mktemp("map2") / "map2.ifc", lentas=2)


@pytest.fixture(scope="session")
def grade(tmp_path_factory):
    return _gerar_grade(tmp_path_factory.mktemp("grade") / "grade.ifc")


@pytest.fixture(autouse=True)
def sem_filhos_sobrando():
    """Nenhum filho sobra entre os testes (um teste que falha não deixa processo para o seguinte)."""
    yield
    for p in multiprocessing.active_children():
        p.kill()
        p.join(5)


def _lentas(monkeypatch, *pares):
    monkeypatch.setenv("OBIM_TESTE_PECA_LENTA", ",".join(f"{g}={s}" for g, s in pares))


def _esperar_filho(limite_s=30.0):
    fim = time.perf_counter() + limite_s
    while time.perf_counter() < fim:
        if multiprocessing.active_children():
            return multiprocessing.active_children()
        time.sleep(0.02)
    raise AssertionError("o filho não apareceu (o carregador não usa processo separado?)")


def _resumo_final(car):
    saida = []
    while (x := car.obter(timeout=0.2)) is not None:
        saida.append(x)
    return saida


def _triangulos(lotes):
    return {i: v[0] for i, v in _por_produto(lotes).items()}


def _regra_de_ouro(r):
    assert r.produtos_com_malha + len(r.sem_malha) == r.produtos_total


# ---------- P1 a P3, P7, P9 a P12: exigem o processo ----------
@pytest.mark.parametrize("modelo, tri, produtos", [("m600", 7200, 600), ("m3000", 36000, 3000)])
def test_p1_numeros_da_t05_pelo_processo(modelo, tri, produtos, request):
    _, r, car = _carregar(request.getfixturevalue(modelo))
    assert r.estado == "concluido" and r.erro is None and r.sem_malha == []
    assert r.triangulos == tri and r.produtos_com_malha == produtos
    assert car.aguardar(timeout=5.0)


def test_p2_diagnostico_do_filho(mapeadas1, monkeypatch):
    caminho, [(_, guid)] = mapeadas1
    _lentas(monkeypatch, (guid, 6))  # mantém o filho vivo para ser inspecionado
    car = CarregadorMalhas(str(caminho))
    car.iniciar()
    try:
        filhos = _esperar_filho()
        assert all(type(p).__name__ == "SpawnProcess" for p in filhos), "o contexto deve ser 'spawn' (também no Linux)"
        if sys.platform.startswith("linux"):
            time.sleep(1.0)
            mapas = Path(f"/proc/{filhos[0].pid}/maps").read_text()
            assert "PySide6" not in mapas, "o filho carregou o Qt"
    finally:
        car.cancelar()
        car.aguardar(timeout=5.0)
    codigo = ("import sys, json, locale; sys.path.insert(0, sys.argv[1]); "
              "import viewport_qrhi.processo_malhas as m; "
              "print(json.dumps([any(k.startswith('PySide6') for k in sys.modules), locale.localeconv()['decimal_point']]))")
    saida = subprocess.run([sys.executable, "-c", codigo, str(RAIZ / "viewport")], capture_output=True, text=True,
                           env={**os.environ, "LC_ALL": "C"}, timeout=120)
    assert saida.returncode == 0, saida.stderr
    assert saida.stdout.strip().splitlines()[-1] == '[false, "."]'


def test_p3_janela_responsiva_com_peca_de_3s(app, mapeadas1, monkeypatch, capsys, record_property):
    caminho, [(_, guid)] = mapeadas1
    _lentas(monkeypatch, (guid, 3))
    lista = []
    atrasos, resumo = _medir(caminho, lista.append, **_kw_sem_limite())
    p95 = float(np.percentile(atrasos, 95))
    _publicar(capsys, record_property, "P3", f"atraso max={atrasos.max():.1f} ms, p95={p95:.1f} ms, amostras={len(atrasos)}")
    assert resumo.estado == "concluido" and resumo.produtos_com_malha == 13 and resumo.sem_malha == []
    assert atrasos.max() <= MAX_MS and p95 <= P95_MS
    assert getattr(resumo, "simplificadas", []) == []
    assert _triangulos(lista)[mapeadas1[1][0][0]] == 12 and sum(len(x.indices) // 3 for x in lista) == 13 * 12


def test_p7_cancelar_durante_peca_de_30s(mapeadas1, monkeypatch):
    caminho, [(_, guid)] = mapeadas1
    _lentas(monkeypatch, (guid, 30))
    car = CarregadorMalhas(str(caminho))
    car.iniciar()
    _esperar_filho()
    time.sleep(1.0)
    t = time.perf_counter()
    car.cancelar()
    assert car.aguardar(timeout=2.0) and time.perf_counter() - t < 1.0
    saida = [x for x in _resumo_final(car) if isinstance(x, ResumoCarga)]
    assert len(saida) == 1 and saida[0].estado == "cancelado"
    assert multiprocessing.active_children() == []


def test_p9_consumidor_parado(m3000):
    car = CarregadorMalhas(str(m3000), tamanho_bloco=200, fila_max=2)
    car.iniciar()
    time.sleep(1.0)
    assert car.lotes_produzidos <= 2 + 2  # fila_max + 2
    time.sleep(3.0)  # o filho já subiu: a contrapressão segura a produção
    assert car.lotes_produzidos <= 2 + 2  # fila_max + 2
    lotes, r = _percorrer(car)
    assert r.estado == "concluido" and r.triangulos == 36000


def test_p10_adaptador_cancela_peca_de_30s(app, mapeadas1, monkeypatch):
    from viewport_qrhi.adaptador import AdaptadorCarga
    caminho, [(_, guid)] = mapeadas1
    _lentas(monkeypatch, (guid, 30))
    ad = AdaptadorCarga(_ViewportFalso())
    ad.abrir(caminho)
    _esperar_filho()
    time.sleep(1.0)
    t = time.perf_counter()
    assert ad.cancelar() is True
    assert time.perf_counter() - t < 1.0


def test_p11_medicao_de_memoria():
    from viewport_qrhi.medir import pico_memoria_mb
    assert pico_memoria_mb() > 0
    assert inspect.signature(pico_memoria_mb).parameters, "pico_memoria_mb sem parâmetro (pico de um processo filho)"
    filho = multiprocessing.get_context("spawn").Process(target=time.sleep, args=(5,), daemon=True)
    filho.start()
    try:
        time.sleep(1.0)
        ident = filho.pid if sys.platform != "win32" else filho.sentinel  # Windows: identificador do processo
        assert pico_memoria_mb(ident) > 0
    finally:
        filho.kill()
        filho.join(5)


def test_p12_peca_maior_que_o_lote(grade):
    caminho, id_grade = grade
    lotes, r, _ = _carregar(caminho, max_bytes_lote=64 * 1024)
    assert r.estado == "concluido" and r.produtos_com_malha == 1 and r.produtos_total == 1
    assert len(lotes) > 1
    for lt in lotes:  # nenhum lote passa do limite por mais de 1 triângulo (3 vértices)
        assert lt.vertices.nbytes <= 64 * 1024 + 3 * lt.vertices.dtype.itemsize
    assert sum(len(lt.indices) // 3 for lt in lotes) == 28800 and r.triangulos == 28800
    linhas = [int(i) for lt in lotes for i in lt.objetos["id_step"]]
    assert len(linhas) > 1 and set(linhas) == {id_grade}  # mesmo id_step em várias linhas


# ---------- P4, P5, P6, P8: exigem o limite por peça ----------
def _tempo_carga(caminho, **kw):
    t = time.perf_counter()
    lotes, r, _ = _carregar(caminho, **kw)
    return lotes, r, time.perf_counter() - t


def _caixa_de(lotes, i):
    _, mn, mx = _por_produto(lotes)[i]
    return mn, mx


def test_p4_peca_lenta_vira_caixa(mapeadas1, monkeypatch, tmp_path):
    caminho, [(id_l, guid)] = mapeadas1
    ref_lotes, ref, _ = _tempo_carga(caminho)  # sem injeção
    assert ref.estado == "concluido" and getattr(ref, "simplificadas", []) == []
    _lentas(monkeypatch, (guid, 5))
    lotes, r, dt = _tempo_carga(caminho, limite_peca_s=1.0)
    assert dt <= 15.0 and r.estado == "concluido"
    assert [s[0] for s in r.simplificadas] == [id_l]
    _, g, _, _, motivo, segundos = r.simplificadas[0]
    assert g == guid and "limite" in motivo.lower() and segundos >= 1.0
    tri, tri_ref = _triangulos(lotes), _triangulos(ref_lotes)
    assert tri[id_l] == 12
    mn, mx = _caixa_de(lotes, id_l)
    rmn, rmx = _caixa_de(ref_lotes, id_l)
    assert np.allclose(mn, rmn, rtol=0, atol=0.01) and np.allclose(mx, rmx, rtol=0, atol=0.01)
    assert {i: n for i, n in tri.items() if i != id_l} == {i: n for i, n in tri_ref.items() if i != id_l}
    assert r.produtos_com_malha == 13 and r.sem_malha == []
    _regra_de_ouro(r)


def test_p5_copias_da_mesma_familia(mapeadas1, mapeadas2, monkeypatch):
    (c1, [(_, g1)]), (c2, lentas2) = mapeadas1, mapeadas2
    _lentas(monkeypatch, (g1, 5))
    _, r1, dt1 = _tempo_carga(c1, limite_peca_s=1.0)  # P4, medido nesta execução
    assert r1.estado == "concluido"
    _lentas(monkeypatch, *[(g, 5) for _, g in lentas2])
    _, r2, dt2 = _tempo_carga(c2, limite_peca_s=1.0)
    assert r2.estado == "concluido" and {s[0] for s in r2.simplificadas} == {i for i, _ in lentas2}
    assert len(r2.simplificadas) == 2
    assert dt2 <= dt1 + 0.5 * 1.0 + 3.0, f"{dt2:.1f} s > {dt1:.1f} s + 0,5 x limite + 3 s: a segunda cópia foi esperada de novo"
    _regra_de_ouro(r2)


def test_p6_lentidao_real_na_grade(grade):
    _lento_ou_pular()
    caminho, id_grade = grade
    _, r, _ = _carregar(caminho, biblioteca="opencascade", limite_peca_s=1.0)
    assert r.estado == "concluido" and [s[0] for s in r.simplificadas] == [id_grade] and r.triangulos == 12
    _, r, _ = _carregar(caminho, limite_peca_s=20.0)  # híbrida (padrão)
    assert r.estado == "concluido" and r.triangulos == 28800 and r.simplificadas == []


def test_p8_filho_que_cai(mapeadas1, monkeypatch):
    caminho, [(id_l, guid)] = mapeadas1
    ref_lotes, _, _ = _tempo_carga(caminho)
    monkeypatch.setenv("OBIM_TESTE_MATAR_FILHO", guid)
    lotes, r, _ = _tempo_carga(caminho)
    assert r.estado == "concluido" and [s[0] for s in r.simplificadas] == [id_l]
    assert any(p in r.simplificadas[0][4].lower() for p in ("caiu", "queda"))
    tri, tri_ref = _triangulos(lotes), _triangulos(ref_lotes)
    assert {i: n for i, n in tri.items() if i != id_l} == {i: n for i, n in tri_ref.items() if i != id_l}
    assert tri[id_l] == 12 and r.produtos_com_malha == 13
    _regra_de_ouro(r)


# ---------- P13 a P18: defeitos de revisão ----------
def _mundo(lotes):
    """id_step -> (mínimo, máximo) no mundo (caixa do lote + deslocamento; peça dividida: união dos pedaços)."""
    saida = {}
    for lt in lotes:
        for o in lt.objetos:
            mn, mx = o["caixa_min"].astype(np.float64) + lt.deslocamento, o["caixa_max"].astype(np.float64) + lt.deslocamento
            i = int(o["id_step"])
            saida[i] = (np.minimum(mn, saida[i][0]), np.maximum(mx, saida[i][1])) if i in saida else (mn, mx)
    return saida


def _confere_caixas(lotes, ref_lotes, ids, atol=0.01):
    a, b = _mundo(lotes), _mundo(ref_lotes)
    for i in ids:
        assert i in a, f"a peça {i} não foi mostrada"
        assert np.allclose(a[i][0], b[i][0], rtol=0, atol=atol) and np.allclose(a[i][1], b[i][1], rtol=0, atol=atol), \
            f"caixa da peça {i}: {a[i]} contra a real {b[i]} (mais de 1 cm)"


@pytest.fixture(scope="session")
def copias1(tmp_path_factory):
    return _gerar_mapeadas(tmp_path_factory.mktemp("cop1") / "cop1.ifc", normais=0, lentas=1)


@pytest.fixture(scope="session")
def copias12(tmp_path_factory):
    return _gerar_mapeadas(tmp_path_factory.mktemp("cop12") / "cop12.ifc", normais=0, lentas=12)


def test_p13_copias_da_mesma_familia_em_blocos_diferentes(copias1, copias12, monkeypatch):
    (c1, [(_, g1)]), (c12, lentas12) = copias1, copias12
    _lentas(monkeypatch, (g1, 5))
    _, r1, dt1 = _tempo_carga(c1, limite_peca_s=1.0, tamanho_bloco=1)  # uma cópia, medida nesta execução
    assert r1.estado == "concluido" and len(r1.simplificadas) == 1
    _lentas(monkeypatch, *[(g, 5) for _, g in lentas12])
    _, r, dt12 = _tempo_carga(c12, limite_peca_s=1.0, tamanho_bloco=1)
    assert r.estado == "concluido", f"estado {r.estado}: {r.erro}"
    assert len(r.simplificadas) == 12 and {s[0] for s in r.simplificadas} == {i for i, _ in lentas12}
    assert dt12 <= dt1 + 0.5 * 1.0 + 3.0, f"{dt12:.1f} s > {dt1:.1f} s + 0,5 x limite + 3 s: as cópias foram esperadas de novo"
    assert r.sem_malha == [] and r.produtos_com_malha == 12
    _regra_de_ouro(r)


def _gerar_sem_geometria(caminho):
    """3 cubos, uma parede sem geometria (retângulo com XDim = 0) e DEPOIS uma peça lenta: id sem geometria < id lenta."""
    f, corpo = _novo()
    cubo, grande = _mapa(f, corpo, 1.0, 1.0, 1.0), _mapa(f, corpo, 2.0, 1.0, 3.0)
    for i in range(3):
        _instancia(f, corpo, cubo, (i * 3.0, 0.0, 0.0), f"normal {i}")
    ruim = ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcWall", name="sem geometria")
    perfil = f.create_entity("IfcRectangleProfileDef", ProfileType="AREA", XDim=0.0, YDim=0.15)
    solido = f.create_entity(
        "IfcExtrudedAreaSolid", SweptArea=perfil, Depth=2.8,
        Position=f.create_entity("IfcAxis2Placement3D", Location=f.create_entity("IfcCartesianPoint", Coordinates=(0.0, 0.0, 0.0))),
        ExtrudedDirection=f.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0)))
    rep = f.create_entity("IfcShapeRepresentation", ContextOfItems=corpo, RepresentationIdentifier="Body",
                          RepresentationType="SweptSolid", Items=[solido])
    ifcopenshell.api.run("geometry.assign_representation", f, product=ruim, representation=rep)
    lenta = _instancia(f, corpo, grande, (20.0, 10.0, 0.0), "lenta")
    f.write(str(caminho))
    assert ruim.id() < lenta.id()
    return caminho, ruim.id(), (lenta.id(), lenta.GlobalId)


def test_p14_produto_sem_geometria_nao_e_acusado(tmp_path, monkeypatch):
    caminho, id_ruim, (id_l, guid) = _gerar_sem_geometria(tmp_path / "semgeo.ifc")
    _lentas(monkeypatch, (guid, 5))
    _, r, _ = _tempo_carga(caminho, limite_peca_s=1.0)
    assert r.estado == "concluido", f"estado {r.estado}: {r.erro}"
    assert [s[0] for s in r.simplificadas] == [id_l], f"simplificadas: {[s[0] for s in r.simplificadas]}"
    assert [s[0] for s in r.sem_malha] == [id_ruim] and "caixa" not in r.sem_malha[0][3].lower()
    assert r.produtos_com_malha == 4 and r.produtos_total == 5
    _regra_de_ouro(r)


def _perfil_retangular(f, corpo, nome, pos, deslocar_perfil, solido_sem_posicao):
    """Parede de perfil retangular extrudado; opcionalmente com posição própria do perfil e `Position` do sólido vazio."""
    api = ifcopenshell.api.run
    p2 = f.create_entity("IfcAxis2Placement2D", Location=f.create_entity("IfcCartesianPoint", Coordinates=(1.5 * MM, 0.7 * MM))) if deslocar_perfil else None
    perfil = f.create_entity("IfcRectangleProfileDef", ProfileType="AREA", XDim=3.0 * MM, YDim=0.2 * MM, Position=p2)  # o arquivo está em mm
    solido = f.create_entity(
        "IfcExtrudedAreaSolid", SweptArea=perfil, Depth=2.8 * MM, ExtrudedDirection=f.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0)),
        Position=None if solido_sem_posicao else f.create_entity("IfcAxis2Placement3D", Location=f.create_entity("IfcCartesianPoint", Coordinates=(0.0, 0.0, 0.0))))
    rep = f.create_entity("IfcShapeRepresentation", ContextOfItems=corpo, RepresentationIdentifier="Body", RepresentationType="SweptSolid", Items=[solido])
    p = api("root.create_entity", f, ifc_class="IfcWall", name=nome)
    api("geometry.assign_representation", f, product=p, representation=rep)
    m = np.eye(4)
    c, s = np.cos(np.radians(30)), np.sin(np.radians(30))
    m[:2, :2] = [[c, -s], [s, c]]
    m[:3, 3] = pos
    api("geometry.edit_object_placement", f, product=p, matrix=m)
    return p


def _gerar_retangulares(caminho):
    f, corpo = _novo()
    _caixa(f, corpo, "IfcWall", (0.0, 0.0, 0.0))
    a = _perfil_retangular(f, corpo, "perfil deslocado", (10.0, 5.0, 0.0), True, False)
    b = _perfil_retangular(f, corpo, "posição vazia", (20.0, 5.0, 0.0), False, True)
    f.write(str(caminho))
    return caminho, [(a.id(), a.GlobalId), (b.id(), b.GlobalId)]


@pytest.mark.parametrize("modelo", ["paredes_e_aberturas", "perfil_retangular", "posicao_vazia"])
def test_p15_caixa_do_solido_extrudado_dentro_de_1cm(modelo, mab, tmp_path, monkeypatch):
    if modelo == "paredes_e_aberturas":  # paredes de perfil IfcArbitraryClosedProfileDef com IfcIndexedPolyCurve
        caminho = mab
        f = ifcopenshell.open(str(caminho))
        paredes = sorted(f.by_type("IfcWall"), key=lambda p: p.id())
        lentas = [(p.id(), p.GlobalId) for p in (paredes[0], paredes[1], paredes[7], paredes[-1])]  # a última é a de 60 m
        assert paredes[0].Representation.Representations[0].Items[0].SweptArea.is_a("IfcArbitraryClosedProfileDef")
    else:
        caminho, lentas = _gerar_retangulares(tmp_path / "retangulares.ifc")
        lentas = lentas[:1] if modelo == "perfil_retangular" else lentas[1:]  # perfil com posição própria / `Position` vazio
    ref_lotes, ref, _ = _tempo_carga(caminho)  # geometria real, sem injeção
    assert ref.estado == "concluido" and ref.sem_malha == []
    _lentas(monkeypatch, *[(g, 5) for _, g in lentas])
    lotes, r, _ = _tempo_carga(caminho, limite_peca_s=1.0)
    assert r.estado == "concluido", f"estado {r.estado}: {r.erro}"
    assert {s[0] for s in r.simplificadas} == {i for i, _ in lentas}
    _confere_caixas(lotes, ref_lotes, [i for i, _ in lentas])
    assert r.sem_malha == []
    _regra_de_ouro(r)


@pytest.mark.parametrize("modelo", [
    "com_reinicio", "so_caixa"])
def test_p16_deslocamento_nao_gravavel_em_todo_lote(modelo, mapeadas1, copias1, monkeypatch):
    caminho, [(_, guid)] = mapeadas1 if modelo == "com_reinicio" else copias1  # só_caixa: o primeiro lote é uma caixa
    _lentas(monkeypatch, (guid, 5))
    lotes, r, _ = _tempo_carga(caminho, limite_peca_s=1.0)
    assert r.estado == "concluido" and len(r.simplificadas) == 1 and lotes
    for lt in lotes:
        assert not lt.deslocamento.flags.writeable, f"lote {lt.indice_lote}: deslocamento gravável"
        assert not any(a.flags.writeable for a in (lt.vertices, lt.indices, lt.objetos))
    with pytest.raises(ValueError):
        lotes[-1].deslocamento[0] = 1.0


def test_p18_filho_da_caixa_que_falha(mapeadas1, monkeypatch):
    caminho, [(id_l, guid)] = mapeadas1
    ref_lotes, _, _ = _tempo_carga(caminho)
    _lentas(monkeypatch, (guid, 5))
    monkeypatch.setenv("OBIM_TESTE_FALHAR_CAIXA", guid)
    lotes, r, _ = _tempo_carga(caminho, limite_peca_s=1.0)
    assert r.estado == "concluido", f"estado {r.estado}: {r.erro}"
    assert [s[0] for s in r.sem_malha] == [id_l] and len(r.sem_malha[0][3]) > 10, f"sem_malha: {r.sem_malha}"
    assert r.simplificadas == []
    assert r.produtos_com_malha == 12 and id_l not in _mundo(lotes)
    _confere_caixas(lotes, ref_lotes, [i for i in _mundo(lotes)])  # nenhum cubo na origem esticando a cena
    _regra_de_ouro(r)
