# SPDX-License-Identifier: AGPL-3.0-or-later
"""Testes do carregador de malhas, casos O1 a O10: carregador de malhas do IFC, sem Qt e sem tela.

Números congelados: não afrouxar número nem remover caso.
Sem o carregador os testes pulam. Testes lentos (M1M): OBIM_TESTES_LENTOS=1.
"""
import gc
import hashlib
import os
import sys
import threading
import time
import types
from functools import lru_cache
from pathlib import Path

import numpy as np
import pytest

import ifcopenshell
import ifcopenshell.api
import ifcopenshell.geom

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "viewport"))
sys.path.insert(0, str(RAIZ / "scripts"))

from gerar_modelo_grande import gerar  # noqa: E402

# Importação direta (RG-03): se o módulo sumir ou for renomeado, a coleta FALHA; antes o teste só pulava.
from viewport_qrhi.carregador import CarregadorMalhas, LoteMalha, ResumoCarga  # noqa: E402
import viewport_qrhi.processo_malhas  # noqa: E402,F401
M1M_CAMINHO = RAIZ / "corpus" / "modelo-grande-1m.ifc"


@lru_cache(maxsize=1)
def _sha_m1m():
    h = hashlib.sha256()
    with open(M1M_CAMINHO, "rb") as a:
        for bloco in iter(lambda: a.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def _m1m_ou_pular():
    """Caminho do M1M, ou pula com mensagem (teste lento: só local, com o arquivo certo)."""
    if os.environ.get("OBIM_TESTES_LENTOS") != "1":
        pytest.skip("teste lento: defina OBIM_TESTES_LENTOS=1 (M1M, só na máquina de referência)")
    if not M1M_CAMINHO.exists():
        pytest.skip(f"teste lento: falta {M1M_CAMINHO}")
    if not _sha_m1m().startswith("0d4639449d5a18f1"):
        pytest.skip("teste lento: SHA-256 do modelo-grande-1m.ifc não começa por 0d4639449d5a18f1")
    return M1M_CAMINHO


# ---------- modelos gerados no próprio teste ----------
def _novo():
    api = ifcopenshell.api.run
    f = api("project.create_file", version="IFC4")
    api("root.create_entity", f, ifc_class="IfcProject", name="Teste")
    api("unit.assign_unit", f)
    ctx = api("context.add_context", f, context_type="Model")
    corpo = api("context.add_context", f, context_type="Model", context_identifier="Body", target_view="MODEL_VIEW", parent=ctx)
    return f, corpo


def _caixa(f, corpo, classe, pos, comprimento=3.0, altura=2.8, espessura=0.15):
    api = ifcopenshell.api.run
    p = api("root.create_entity", f, ifc_class=classe, name=classe)
    rep = api("geometry.add_wall_representation", f, context=corpo, length=comprimento, height=altura, thickness=espessura)
    api("geometry.assign_representation", f, product=p, representation=rep)
    m = np.eye(4)
    m[:3, 3] = pos
    api("geometry.edit_object_placement", f, product=p, matrix=m)
    return p, rep


def _gerar_mab(caminho):
    """MAB: 20 paredes simples + 1 parede com 150 aberturas + 1 IfcSpace com geometria."""
    f, corpo = _novo()
    for i in range(20):
        _caixa(f, corpo, "IfcWall", (i * 4.0, 0.0, 0.0))
    grande, _ = _caixa(f, corpo, "IfcWall", (0.0, 10.0, 0.0), 60.0, 3.0, 0.3)
    for k in range(150):
        a, _ = _caixa(f, corpo, "IfcOpeningElement", (1 + (k % 50) * 1.1, 9.7, 0.4 + (k // 50) * 0.8), 0.3, 0.3, 0.9)
        ifcopenshell.api.run("feature.add_feature", f, feature=a, element=grande)
    _caixa(f, corpo, "IfcSpace", (0.0, 30.0, 0.0), 4.0, 3.0, 2.8)
    f.write(str(caminho))
    return caminho


def _gerar_cor(caminho):
    """Parede 0 sem estilo; parede 1 com estilo de superfície vermelho puro."""
    api = ifcopenshell.api.run
    f, corpo = _novo()
    _caixa(f, corpo, "IfcWall", (0.0, 0.0, 0.0))
    _, rep = _caixa(f, corpo, "IfcWall", (5.0, 0.0, 0.0))
    estilo = api("style.add_style", f)
    api("style.add_surface_style", f, style=estilo, ifc_class="IfcSurfaceStyleShading",
        attributes={"SurfaceColour": {"Name": None, "Red": 1.0, "Green": 0.0, "Blue": 0.0}, "Transparency": 0.0})
    api("style.assign_representation_styles", f, shape_representation=rep, styles=[estilo])
    f.write(str(caminho))
    return caminho


def _gerar_defeito(caminho):
    """2 paredes boas e 1 defeituosa (retângulo com XDim = 0 extrudado)."""
    f, corpo = _novo()
    _caixa(f, corpo, "IfcWall", (0.0, 0.0, 0.0))
    _caixa(f, corpo, "IfcWall", (5.0, 0.0, 0.0))
    ruim = ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcWall", name="defeituosa")
    perfil = f.create_entity("IfcRectangleProfileDef", ProfileType="AREA", XDim=0.0, YDim=0.15)
    solido = f.create_entity(
        "IfcExtrudedAreaSolid", SweptArea=perfil, Depth=2.8,
        Position=f.create_entity("IfcAxis2Placement3D", Location=f.create_entity("IfcCartesianPoint", Coordinates=(0.0, 0.0, 0.0))),
        ExtrudedDirection=f.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0)),
    )
    rep = f.create_entity("IfcShapeRepresentation", ContextOfItems=corpo, RepresentationIdentifier="Body",
                          RepresentationType="SweptSolid", Items=[solido])
    ifcopenshell.api.run("geometry.assign_representation", f, product=ruim, representation=rep)
    f.write(str(caminho))
    return caminho, ruim.id()


def _contar_simples(caminho, id_step):
    """Triângulos que o iterador simples dá para um produto (e quantos produtos ele devolve)."""
    f = ifcopenshell.open(str(caminho))
    s = ifcopenshell.geom.settings()
    s.set("use-world-coords", True)
    s.set("weld-vertices", False)
    it = ifcopenshell.geom.iterator(s, f, 1, include=[f.by_id(id_step)])
    n = 0
    if it.initialize():
        while True:
            n += len(it.get().geometry.faces) // 3
            if not it.next():
                break
    return n


@pytest.fixture(scope="session")
def m600(tmp_path_factory):
    c = tmp_path_factory.mktemp("m600") / "m600.ifc"
    gerar(c, paredes=600, por_andar=200)
    return c


@pytest.fixture(scope="session")
def m3000(tmp_path_factory):
    c = tmp_path_factory.mktemp("m3000") / "m3000.ifc"
    gerar(c, paredes=3000, por_andar=200)
    return c


@pytest.fixture(scope="session")
def mab(tmp_path_factory):
    return _gerar_mab(tmp_path_factory.mktemp("mab") / "mab.ifc")


def _percorrer(car, limite_s=600.0):
    """Roda o carregador até o resumo. Devolve (lotes, resumo)."""
    lotes, fim = [], time.perf_counter() + limite_s
    car.iniciar()
    while time.perf_counter() < fim:
        x = car.obter(timeout=0.05)
        if isinstance(x, ResumoCarga):
            return lotes, x
        if x is not None:
            lotes.append(x)
    car.cancelar()
    raise AssertionError("carga não terminou no tempo")


def _carregar(caminho, **kw):
    car = CarregadorMalhas(str(caminho), **kw)
    lotes, resumo = _percorrer(car)
    return lotes, resumo, car


@pytest.fixture
def excecoes_em_thread(monkeypatch):
    """Captura exceções não tratadas em qualquer thread (P0b-2). O teste exige a lista vazia."""
    capturadas = []
    monkeypatch.setattr(threading, "excepthook", lambda args: capturadas.append(args))
    return capturadas


# ---------- O1 a O11 ----------
def test_o1_contagem_m600(m600, excecoes_em_thread):
    lotes, r, car = _carregar(m600)
    assert car.aguardar(timeout=5.0) and excecoes_em_thread == [], "exceção não tratada na thread do carregador"
    assert r.estado == "concluido" and r.erro is None
    assert r.triangulos == 7200 and r.produtos_com_malha == 600 and r.sem_malha == []
    assert sum(len(lt.indices) for lt in lotes) == 21600  # soma dos n_indices
    assert sum(int(lt.objetos["n_indices"].sum()) for lt in lotes) == 21600


@pytest.mark.parametrize("bloco", [4000, 0])
def test_o2_contagem_referencia_m1m(bloco):
    caminho = _m1m_ou_pular()
    _, r, _ = _carregar(caminho, tamanho_bloco=bloco)
    print(f"O2 bloco={bloco}: estado={r.estado} triangulos={r.triangulos} produtos={r.produtos_com_malha} tempos={r.tempos}")
    assert r.triangulos == 1000008 and r.produtos_com_malha == 83334 and r.sem_malha == []


def _por_produto(lotes):
    d = {}
    for lt in lotes:
        for o in lt.objetos:
            a, b = int(o["primeiro_vertice"]), int(o["primeiro_vertice"] + o["n_vertices"])
            pos = lt.vertices["pos"][a:b].astype(np.float64) + lt.deslocamento
            d[int(o["id_step"])] = (int(o["n_indices"]) // 3, pos.min(axis=0), pos.max(axis=0))
    return d


@pytest.mark.parametrize("modelo", ["m600", "mab"])
def test_o3_threads_e_blocos_dao_o_mesmo(modelo, request):
    caminho = request.getfixturevalue(modelo)
    l1, r1, _ = _carregar(caminho, threads=1)
    l4, r4, _ = _carregar(caminho, threads=4)
    assert r1.estado == r4.estado == "concluido" and len(l1) == len(l4)
    for a, b in zip(l1, l4):
        assert a.indice_lote == b.indice_lote
        assert a.objetos.tobytes() == b.objetos.tobytes()  # ids, guids e faixas
        assert np.array_equal(a.indices, b.indices)
        assert np.array_equal(a.vertices["cor"], b.vertices["cor"])
        assert np.allclose(a.vertices["pos"], b.vertices["pos"], rtol=0, atol=1e-6)
        assert np.allclose(a.vertices["normal"], b.vertices["normal"], rtol=0, atol=1e-6)
        assert np.array_equal(a.deslocamento, b.deslocamento)
    ref = _por_produto(l1)
    for bloco in (0, 200, 4000):
        lb, rb, _ = _carregar(caminho, tamanho_bloco=bloco)
        assert rb.estado == "concluido"
        outro = _por_produto(lb)
        assert outro.keys() == ref.keys()
        for k, (n, mn, mx) in ref.items():
            assert outro[k][0] == n, f"bloco {bloco}, produto {k}"
            assert np.allclose(outro[k][1], mn, rtol=0, atol=1e-5) and np.allclose(outro[k][2], mx, rtol=0, atol=1e-5)


def test_o4_filtro_e_aberturas_mab(mab):
    lotes, r, car = _carregar(mab)
    f = ifcopenshell.open(str(mab))
    paredes = {p.id() for p in f.by_type("IfcWall")}
    ids = [int(i) for lt in lotes for i in lt.objetos["id_step"]]
    assert len(ids) == 21 and set(ids) == paredes  # nenhuma abertura, nenhum espaço
    assert r.produtos_com_malha == 21
    por = {i: n for i, (n, _, _) in _por_produto(lotes).items()}
    grande = max(por, key=por.get)
    assert por[grande] > 12
    assert por[grande] == _contar_simples(mab, grande)


@pytest.mark.parametrize("bloco", [4000, 200])  # 200 gera vários lotes: confere também as regras entre lotes
def test_o5_invariantes_de_cada_lote_m600(m600, bloco):
    lotes, r, _ = _carregar(m600, tamanho_bloco=bloco)
    assert (len(lotes) > 1 or bloco == 4000) and [lt.indice_lote for lt in lotes] == list(range(len(lotes)))
    ultimo, linhas, desl = -1, [], lotes[0].deslocamento
    assert desl.dtype == np.float64 and desl.shape == (3,)
    for lt in lotes:
        v, ix, ob = lt.vertices, lt.indices, lt.objetos
        assert v.dtype.itemsize == 28 and v.dtype.names == ("pos", "normal", "cor")
        assert v.dtype["pos"].base == np.float32 and v.dtype["pos"].shape == (3,)
        assert v.dtype["normal"].base == np.float32 and v.dtype["normal"].shape == (3,)
        assert v.dtype["cor"].base == np.uint8 and v.dtype["cor"].shape == (4,)
        assert ix.dtype == np.uint32 and ix.ndim == 1 and len(ix) % 3 == 0
        assert ob["id_step"].dtype == np.int32 and ob.dtype["guid"].itemsize == 22
        for campo in ("primeiro_indice", "n_indices", "primeiro_vertice", "n_vertices"):
            assert ob[campo].dtype == np.uint32
        for campo in ("caixa_min", "caixa_max"):
            assert ob.dtype[campo].base == np.float32 and ob.dtype[campo].shape == (3,)
        for a in (v, ix, ob):
            assert a.flags["C_CONTIGUOUS"] and a.flags["OWNDATA"]
        assert ix.max() < len(v)
        assert np.array_equal(lt.deslocamento, desl)
        # faixas contíguas, sem buraco nem sobreposição, cobrindo tudo
        fim_i = fim_v = 0
        for o in ob:
            assert o["primeiro_indice"] == fim_i and o["primeiro_vertice"] == fim_v
            fim_i, fim_v = fim_i + int(o["n_indices"]), fim_v + int(o["n_vertices"])
            pos = v["pos"][o["primeiro_vertice"]:fim_v]
            assert np.all(pos >= o["caixa_min"] - 1e-5) and np.all(pos <= o["caixa_max"] + 1e-5)
            linhas.append((o["caixa_min"].astype(np.float64) + desl, o["caixa_max"].astype(np.float64) + desl))
        assert fim_i == len(ix) and fim_v == len(v)
        ids = ob["id_step"]
        assert np.all(np.diff(ids) > 0) and ids[0] > ultimo
        ultimo = int(ids[-1])
        assert np.all(np.abs(np.linalg.norm(v["normal"], axis=1) - 1.0) <= 1e-3)
    assert len(linhas) == 600
    colunas = 14  # fórmula do gerador (por_andar=200)
    for i in (0, 1, 599):
        k = i % 200
        x0, y0, z0 = (k % colunas) * 4.0, (k // colunas) * 4.0, (i // 200) * 3.0
        assert np.allclose(linhas[i][0], [x0, y0, z0], rtol=0, atol=1e-3)
        assert np.allclose(linhas[i][1], [x0 + 3.0, y0 + 0.15, z0 + 2.8], rtol=0, atol=1e-3)


def test_o6_cor(tmp_path):
    caminho = _gerar_cor(tmp_path / "cor.ifc")
    lotes, r, _ = _carregar(caminho)
    assert r.estado == "concluido" and len(lotes) == 1
    lt, esperado = lotes[0], [(230, 230, 230, 255), (255, 0, 0, 255)]
    assert len(lt.objetos) == 2
    for o, cor in zip(lt.objetos, esperado):
        c = lt.vertices["cor"][o["primeiro_vertice"]:o["primeiro_vertice"] + o["n_vertices"]].astype(int)
        assert np.all(np.abs(c - np.array(cor)) <= 1), (cor, np.unique(c, axis=0))
    c1 = lt.vertices["cor"][lt.objetos[1]["primeiro_vertice"]:].astype(int)
    assert np.all(c1 == (255, 0, 0, 255))  # vermelho puro: exato


def test_o7_cancelamento_m3000(m3000):
    car = CarregadorMalhas(str(m3000), tamanho_bloco=200)
    car.iniciar()
    entregues, primeiro = [], None
    fim = time.perf_counter() + 120
    while primeiro is None and time.perf_counter() < fim:
        primeiro = car.obter(timeout=0.05)
    assert isinstance(primeiro, LoteMalha)
    entregues.append(primeiro)
    t = time.perf_counter()
    car.cancelar()
    assert time.perf_counter() - t < 0.05
    assert car.aguardar(timeout=2.0) and time.perf_counter() - t < 2.0
    saida = []
    while (x := car.obter(timeout=0.2)) is not None:
        saida.append(x)
    assert len(saida) == 1 and isinstance(saida[0], ResumoCarga), "depois de cancelar() só o resumo sai"
    assert saida[0].estado == "cancelado"
    assert sum(len(lt.indices) // 3 for lt in entregues) < 36000
    _, novo, _ = _carregar(m3000, tamanho_bloco=200)
    assert novo.estado == "concluido" and novo.triangulos == 36000


@pytest.mark.parametrize("modo", ["inexistente", "texto"])
def test_o8_arquivo_invalido(tmp_path, modo, excecoes_em_thread):
    caminho = tmp_path / "nada.ifc"
    if modo == "texto":
        caminho.write_text("isto não é um IFC\n")
    car = CarregadorMalhas(str(caminho))
    lotes, r = _percorrer(car)
    assert lotes == [] and r.estado == "erro" and r.erro
    assert car.aguardar(timeout=5.0)  # a thread terminou...
    assert excecoes_em_thread == [], f"...mas com exceção: {excecoes_em_thread}"  # ...sem exceção


def test_foto_do_arquivo_detecta_tamanho_data_e_conteudo(tmp_path):
    """A foto (tamanho, data, soma) acusa qualquer mudança no arquivo e diz o que mudou."""
    from viewport_qrhi import foto_arquivo as fa
    c = tmp_path / "a.ifc"
    c.write_bytes(b"abcdef")
    foto = fa.tirar(c)
    assert foto["tamanho"] == 6 and len(foto["soma"]) == 32 and fa.mudou(c, foto, com_soma=True) is None
    os.utime(c, ns=(foto["data_ns"] + 10**9, foto["data_ns"] + 10**9))
    assert "data de modificação" in fa.mudou(c, foto)
    c.write_bytes(b"abcdefg")
    assert "tamanho 6 -> 7" in fa.mudou(c, foto)
    c.write_bytes(b"abcdeX")
    os.utime(c, ns=(foto["data_ns"], foto["data_ns"]))  # mesmo tamanho e data: só a soma pega
    assert fa.mudou(c, foto) is None and "conteúdo" in fa.mudou(c, foto, com_soma=True)
    assert fa.tirar(tmp_path / "nao_existe.ifc") is None and fa.mudou(tmp_path / "x", None) is None


def test_arquivo_trocado_durante_a_carga_para_com_mensagem_clara(tmp_path, monkeypatch, excecoes_em_thread):
    """O filho recebe a foto tirada pelo pai; se o arquivo já não bate, a carga termina em erro (não mistura versões)."""
    from viewport_qrhi import carregador as cr
    c = _gerar_cor(tmp_path / "cor.ifc")
    boa = cr.foto_arquivo.tirar(c)
    monkeypatch.setattr(cr.foto_arquivo, "tirar", lambda caminho, com_soma=True: {**boa, "tamanho": boa["tamanho"] + 1})
    lotes, r, car = _carregar(c)
    assert lotes == [] and r.estado == "erro" and "mudou durante a carga" in r.erro
    assert car.aguardar(timeout=5.0) and excecoes_em_thread == []


def test_manter_arquivo_recusa_arquivo_com_conteudo_trocado(tmp_path, monkeypatch):
    """Mesmo tamanho e data, conteúdo diferente: a carga conclui, mas o arquivo NÃO é mantido aberto e a mensagem diz por quê."""
    from viewport_qrhi import carregador as cr
    c = _gerar_cor(tmp_path / "cor.ifc")
    real = cr.foto_arquivo
    boa = real.tirar(c)
    assert boa["soma"]
    falsa = types.SimpleNamespace(tirar=lambda caminho, com_soma=True: {**boa, "soma": "0" * 32}, mudou=real.mudou)
    monkeypatch.setattr(cr, "foto_arquivo", falsa)  # só o carregador vê a foto com a soma errada; mudou() relê a soma de verdade
    lotes, r, car = _carregar(c, manter_arquivo=True)
    assert r.estado == "concluido" and lotes
    assert any("não foi possível manter o arquivo aberto: o arquivo mudou durante a carga (o conteúdo mudou)" in m for m in r.mensagens)
    assert car.arquivo is None


def test_soma_so_com_manter_arquivo(tmp_path, monkeypatch):
    """Sem manter_arquivo a carga não lê o arquivo inteiro só para a soma (não dá para cancelar essa leitura)."""
    from viewport_qrhi import carregador as cr
    pedidos = []
    original = cr.foto_arquivo.tirar
    monkeypatch.setattr(cr.foto_arquivo, "tirar", lambda caminho, com_soma=True: pedidos.append(com_soma) or original(caminho, com_soma))
    _carregar(_gerar_cor(tmp_path / "cor.ifc"))
    assert pedidos == [False]


def test_o8_produto_defeituoso(tmp_path):
    caminho, id_ruim = _gerar_defeito(tmp_path / "defeito.ifc")
    assert _contar_simples(caminho, id_ruim) == 0, "o iterador simples passou a devolver a parede defeituosa: refazer a receita"
    lotes, r, _ = _carregar(caminho)
    assert r.estado == "concluido" and r.produtos_total == 3
    assert r.produtos_com_malha == 2 and [s[0] for s in r.sem_malha] == [id_ruim]
    assert r.produtos_com_malha + len(r.sem_malha) == r.produtos_total
    assert r.triangulos == 24 and sum(len(lt.objetos) for lt in lotes) == 2


def test_o9_fila_limitada_m3000(m3000):
    car = CarregadorMalhas(str(m3000), tamanho_bloco=200, fila_max=2)
    car.iniciar()
    time.sleep(1.0)  # ninguém consumindo
    assert car.lotes_produzidos <= 3  # 2 na fila e 1 na mão
    lotes, r = [], None
    fim = time.perf_counter() + 120
    while r is None and time.perf_counter() < fim:
        x = car.obter(timeout=0.05)
        if isinstance(x, ResumoCarga):
            r = x
        elif x is not None:
            lotes.append(x)
    assert r is not None and r.estado == "concluido" and r.triangulos == 36000
    assert car.lotes_produzidos == 15


def _soma(lotes):
    h = hashlib.sha256()
    for lt in lotes:
        h.update(lt.vertices.tobytes() + lt.indices.tobytes() + lt.objetos.tobytes() + lt.deslocamento.tobytes())
    return h.hexdigest()


def test_o10_vida_dos_dados_m600(m600):
    # com o processo separado, o arquivo só é aberto no pai se pedido (manter_arquivo)
    car = CarregadorMalhas(str(m600), manter_arquivo=True)
    car.iniciar()
    assert car.arquivo is None  # durante a carga
    lotes, r = [], None
    fim = time.perf_counter() + 120
    while r is None and time.perf_counter() < fim:
        x = car.obter(timeout=0.05)
        if isinstance(x, ResumoCarga):
            r = x
        elif x is not None:
            lotes.append(x)
    assert r is not None and car.aguardar(timeout=5.0)
    assert isinstance(car.arquivo, ifcopenshell.file)  # depois do fim
    antes = _soma(lotes)
    del car
    gc.collect()
    assert _soma(lotes) == antes and all(lt.vertices["pos"].size for lt in lotes)


@pytest.mark.parametrize("t", [0.0, 1e-9, 0.01, 0.05])
def test_o11_obter_com_timeout_sempre_volta(tmp_path, t):
    """P0b-3: com o trabalhador terminado e a fila vazia, obter(timeout=t) volta em < t + 0,1 s (pega o defeito A-1)."""
    caminho = _gerar_cor(tmp_path / "cor.ifc")
    car = CarregadorMalhas(str(caminho))
    lotes, r = _percorrer(car)
    assert r.estado == "concluido" and car.aguardar(timeout=5.0)
    while car.obter(timeout=0.2) is not None:  # fila vazia e resumo já entregue
        pass
    resultado = {}

    def chamar():
        t0 = time.perf_counter()
        resultado["x"] = car.obter(timeout=t)
        resultado["dt"] = time.perf_counter() - t0

    th = threading.Thread(target=chamar, daemon=True)  # daemon: se travar, o teste falha em vez de pendurar o CI
    th.start()
    th.join(timeout=2.0)
    assert not th.is_alive(), f"obter(timeout={t}) travou (não voltou em 2 s)"
    assert resultado["x"] is None and resultado["dt"] < t + 0.1, f"voltou em {resultado['dt']:.3f} s para timeout={t}"
