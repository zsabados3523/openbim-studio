# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo R1 da S04 (cartão T02; LOTE_OPUS_9 §1.4 e §1.5): o modelo é o MESMO dos dois lados da ponte Python/C++
(`obimcore`). R1-a a R1-i (R1-j é da T17). Sem `obimcore` o que depende dele PULA com mensagem em destaque.
SUPOSIÇÕES (o Opus confere): (1) `versao()` devolve texto/dict contendo, por substring, `ifcopenshell.version`, o build
do conda-meta, `qVersion()` e a versão do `occt`; `contar(f, classe)` int com subtipos, `None` = toda instância;
`bibliotecas_carregadas()` lista de caminhos. (2) `malhas(f, guids)` devolve dict {guid: item} ou lista na ordem
pedida; item (dict/objeto) com posicoes, indices e, opcional, caixa (6 números), em coordenadas do mundo, sem soldar
vértices (opções da S03). (3) Desfazer = `undo()` do ifcopenshell-python; não-arquivo = qualquer `Exception`.
(4) R1-e só confere /proc/self/maps no Linux. (5) R1-f: o ifcopenshell 0.9 SOZINHO cresce ~0,7 MB por reabertura
(medido): os 10% valem para o que o módulo acrescenta sobre a mesma volta em Python puro. (6) LC_ALL=C basta.
"""
import importlib.util
import json
import os
import random
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest
import s04_aux as aux

AUX = Path(__file__).resolve().parent / "s04_aux.py"
TEM_MODULO = importlib.util.find_spec("obimcore") is not None
ESQ = list(aux.ESQUEMAS)

@pytest.fixture(scope="session")
def modelos(tmp_path_factory):
    return aux.gerar_modelos(tmp_path_factory.mktemp("s04"))

@pytest.fixture(scope="module")
def oc():
    if not TEM_MODULO:
        pytest.skip("\n!!! aguarda S04-T03: módulo obimcore (oráculo R1 NÃO FOI EXECUTADO) !!!\n")
    import ifcopenshell, obimcore  # noqa: E401,F401  (ifcopenshell antes do obimcore)
    aux.preparar_dono()
    return obimcore

@pytest.fixture
def malhas(oc):
    if not hasattr(oc, "malhas"):
        pytest.skip("\n!!! aguarda S04-T04: obimcore.malhas !!!\n")
    return oc.malhas

def abrir(caminho):
    import ifcopenshell
    return ifcopenshell.open(str(caminho))

def subprocesso(*args):
    env = {k: v for k, v in os.environ.items() if k != "DISPLAY"}
    env.update(QT_QPA_PLATFORM="offscreen", PYTHONPATH=os.pathsep.join(filter(None, [str(AUX.parent), env.get("PYTHONPATH")])))
    return subprocess.Popen([sys.executable, str(AUX), *map(str, args)], env=env, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True)

def resultado(p, timeout=900):
    out, err = p.communicate(timeout=timeout)
    assert p.returncode == 0, f"subprocesso caiu/falhou ({p.returncode}):\n{out}\n{err}"
    return json.loads(out.strip().splitlines()[-1])

def pedaco(f, n=60):
    g = aux.guids_com_geometria(f)[:n]
    return f, g, aux.referencia(f, g)

@pytest.mark.parametrize("esq", ESQ)
def test_modelos_gerados_por_script(modelos, esq):  # roda hoje, sem o módulo
    f, g, ref = pedaco(abrir(modelos[esq]), 5)
    assert f.schema.upper().startswith(esq[:4]) and len(f.by_type("IfcWall")) == aux.PAREDES and all(n > 0 for n, _, _ in ref.values())

def test_r1a_versao_e_build_iguais_aos_do_python(oc):
    import ifcopenshell
    from PySide6.QtCore import qVersion
    texto, build = repr(oc.versao()), aux.versao_conda("ifcopenshell", "build")
    assert ifcopenshell.version in texto and qVersion() in texto, texto
    if build is None:
        pytest.skip("\n!!! sem conda-meta do ifcopenshell: build NÃO conferido (R1-a incompleto) !!!\n")
    assert build in texto, f"build {build} ausente: {texto}"
    occt = aux.versao_conda("occt")
    assert occt is None or occt in texto, f"versão do OCCT ausente: {texto}"

@pytest.mark.parametrize("esq", ESQ)
def test_r1c_contagens_iguais_em_tres_esquemas(oc, modelos, esq):
    f = abrir(modelos[esq])
    assert oc.endereco(f) == f.file_pointer() != 0  # R1-b: vale por construção; sentinela, não prova (a prova é a R1-d)
    for classe in ("IfcWall", "IfcSlab", "IfcElement", "IfcProduct", "IfcRoot", None):
        assert oc.contar(f, classe) == aux.contagem_python(f, classe), (esq, classe)
    assert oc.contar(f, "IfcWall") == aux.PAREDES  # número de verdade, não dois zeros iguais

@pytest.mark.parametrize("esq", ESQ)
def test_r1d_mesmo_modelo_nos_dois_lados(oc, modelos, esq):
    import ifcopenshell.api
    f = abrir(modelos[esq])
    n0, t0 = oc.contar(f, "IfcWall"), oc.contar(f, None)
    f.begin_transaction()  # 1) o Python cria; o C++ conta sem reabrir
    p = ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcWall", name="Original")
    f.end_transaction()
    assert oc.contar(f, "IfcWall") == n0 + 1 and oc.contar(f, None) == aux.contagem_python(f, None) > t0
    assert oc.ler_nome(f, p.GlobalId) == "Original"
    oc.definir_nome(f, p.GlobalId, "Do C++")  # 2) o C++ muda; o Python lê o novo
    assert p.Name == f.by_guid(p.GlobalId).Name == "Do C++"
    f.begin_transaction()  # 3) o Python muda e desfaz; o C++ vê o desfeito
    p.Name = "Do Python"
    f.end_transaction()
    assert oc.ler_nome(f, p.GlobalId) == "Do Python"
    f.undo()
    assert p.Name == oc.ler_nome(f, p.GlobalId) == "Do C++"
    f.undo()  # desfaz a criação: o C++ vê o elemento sumir
    assert (oc.contar(f, "IfcWall"), oc.contar(f, None)) == (n0, t0)

@pytest.mark.parametrize("ordem", ["ifcopenshell,PySide6", "PySide6,ifcopenshell", "ifcopenshell,PySide6.QtCore"])
def test_r1e_uma_copia_de_cada_nucleo(oc, modelos, ordem):
    r = resultado(subprocesso("r1e", ordem, modelos["IFC4"].parent), 300)
    for onde in ("modulo", "real"):
        for k, caminhos in (r[onde] or {}).items():
            assert len(caminhos) == 1, f"{k}: {len(caminhos)} cópias ({onde}): {caminhos}"
    assert r["real"] is None or r["real"] == r["modulo"], "bibliotecas_carregadas() não bate com o mapa do processo"

def test_r1f_mil_voltas_sem_diferenca_nem_vazamento(oc, modelos):
    pm, pb = (subprocesso("r1f", modelos["IFC4"].parent, m) for m in ("modulo", "base"))  # em paralelo: demoram
    r, base = resultado(pm), resultado(pb)
    assert r["diferencas"] == [], r["diferencas"][:10]
    extra = ((r["rss_final"] - r["rss100"]) - (base["rss_final"] - base["rss100"])) / r["rss100"]
    assert extra <= 0.10, f"o módulo acrescentou {extra:.1%} de memória entre as voltas 100 e {r['voltas']}"

def test_r1g_posse_fechar_e_destruir_arquivo(oc, modelos):
    r = resultado(subprocesso("r1g", modelos["IFC4"].parent))  # código de saída 0 é conferido aqui
    assert r["fim"] and r["malhas_ruins"] == 0 and r["aceitos"] == [], f"não rejeitou o que não é arquivo: {r['aceitos']}"

def rodar_threads(alvos):  # cada alvo recebe a lista `erros`; devolve os erros anotados
    erros = []

    def envolve(alvo):
        try:
            alvo(erros)
        except Exception as e:  # noqa: BLE001
            erros.append(repr(e))
    ts = [threading.Thread(target=envolve, args=(a,)) for a in alvos]
    [t.start() for t in ts]
    [t.join(300) for t in ts]
    assert not any(t.is_alive() for t in ts), "thread travada"
    return erros


def test_r1h_quatro_threads_em_arquivos_diferentes(malhas, modelos, tmp_path):
    shutil.copy(modelos["IFC4"], tmp_path / "quarto.ifc")
    barreira = threading.Barrier(4)

    def trabalho(f, g, ref):
        def alvo(erros):
            barreira.wait(30)
            for _ in range(25):
                erros += aux.diferencas(aux.por_guid(malhas(f, g), g), ref)
        return alvo
    assert rodar_threads([trabalho(*pedaco(abrir(c))) for c in [*modelos.values(), tmp_path / "quarto.ifc"]]) == []


def test_r1h_principal_nao_espera_a_malha(malhas, modelos):
    f, todos, ref = pedaco(abrir(modelos["IFC4"]), 10**6)
    assert aux.diferencas(aux.por_guid(malhas(f, todos), todos), ref) == []
    k, dur = 1, 0
    while dur < 0.15 and k <= 400:  # carga: cada chamada precisa durar >= 150 ms, senão a regra 4 não é exercitada
        k *= 2
        t = time.perf_counter()
        malhas(f, todos * k)  # só carga: esta lista repetida não é conferida
        dur = time.perf_counter() - t
    assert dur >= 0.15, f"carga insuficiente ({dur * 1000:.0f} ms)"
    parar, chamadas, erros = threading.Event(), [], []

    def trabalho():
        try:
            while not parar.is_set():
                malhas(f, todos * k)
                chamadas.append(1)
        except Exception as e:  # noqa: BLE001
            erros.append(repr(e))
    t = threading.Thread(target=trabalho)
    t.start()
    pior, ultimo = 0.0, time.perf_counter()
    fim = ultimo + max(2.0, 4 * dur)
    while ultimo < fim:  # a principal só conta tempo
        time.sleep(0.001)
        agora = time.perf_counter()
        pior, ultimo = max(pior, agora - ultimo), agora
    parar.set()
    t.join(120)
    assert not t.is_alive() and erros == [] and len(chamadas) >= 2
    assert pior <= 0.050, f"a thread principal esperou {pior * 1000:.0f} ms (limite 50 ms): bloqueio não foi solto"


def test_r1h_regra_7_leitura_com_trava_enquanto_outra_thread_roda_malhas(malhas, modelos):
    f, g, ref = pedaco(abrir(modelos["IFC4"]), 20)
    esperado, trava, lidos = {x: (f.by_guid(x).Name, f.by_guid(x).is_a()) for x in g}, threading.Lock(), []

    def comando(erros):  # o comando segura a trava durante a chamada ao C++
        for n in range(1000):
            with trava:
                res = malhas(f, g)
            erros += aux.diferencas(aux.por_guid(res, g), ref) * (n % 100 == 0)
    t = threading.Thread(target=lambda: lidos.extend(rodar_threads([comando])))
    t.start()
    for _ in range(1000):  # painel de propriedades: lê o MESMO arquivo, só com a trava
        with trava:
            lidos += [x for x in g if (f.by_guid(x).Name, f.by_guid(x).is_a()) != esperado[x]]
    t.join(300)
    assert not t.is_alive() and lidos == [], lidos[:10]


def test_r1i_malhas_iguais_ao_create_shape_em_200_elementos(malhas, modelos):
    arquivos = {e: abrir(modelos[e]) for e in ESQ}
    sorteio = random.Random(20261012).sample(sorted((e, g) for e, f in arquivos.items() for g in aux.guids_com_geometria(f)), 200)
    assert {e for e, _ in sorteio} == set(ESQ)
    erros = []
    for e, f in arquivos.items():
        g = [x for esq, x in sorteio if esq == e]
        erros += aux.diferencas(aux.por_guid(malhas(f, g), g), aux.referencia(f, g))
    assert erros == [], f"{len(erros)} diferenças, ex.: {erros[:5]}"
