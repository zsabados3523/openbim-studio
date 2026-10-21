# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo do F0-S04-P1, parte C++ (LOTE_OPUS_69; ADR-004 §5, decisão 3C: "o obimcore recebe a sessão e confere a trava antes de soltar o
interpretador; sem trava, erro claro, não queda"). Quem implementa o P1 não edita este arquivo; os `@AINDA_NAO` (xfail estrito) saem pelo autor do oráculo.
Contrato: `obimcore.malhas(alvo, guids)` aceita, além do `ifcopenshell.file` de hoje (caminho dos protótipos, que não muda: `fluxo_a.py` é régua), uma
`SessaoModelo` (`app/openbim_app/sessao_modelo.py`). Com a sessão: COM o bloqueio, chama `alvo._obimcore_entrar()` (o erro dele, `TravaNaoSegura`, sobe
como está); solta o bloqueio só para a geometria; com o bloqueio de volta chama `alvo._obimcore_sair()` SEMPRE (também quando a geometria falha).
Outro tipo: `TypeError`. O resultado com a sessão é igual ao do arquivo. Nada de Qt aqui.
GUARDA: pula sem o obimcore; com OBIM_S04_P1_OBRIGATORIO=1 o pulo vira falha."""
import importlib.util
import os
import tempfile
import threading
import time
from pathlib import Path

import numpy as np
import pytest
import s04_fluxo_aux as aux  # noqa: F401  (põe prototypes/s04/fluxo_a, scripts e app no caminho)

AINDA_NAO = pytest.mark.xfail(strict=True, reason="P1: obimcore.malhas ainda não aceita a SessaoModelo")
OBRIGATORIO = os.environ.get("OBIM_S04_P1_OBRIGATORIO") == "1"


def _sm():
    from openbim_app import sessao_modelo
    return sessao_modelo


@pytest.fixture(scope="module")
def base():  # 5 paredes do gerador + 1 parede de 60 m com 150 aberturas (a do T15d)
    if importlib.util.find_spec("obimcore") is None:
        (pytest.fail if OBRIGATORIO else pytest.skip)("\n!!! S04-P1: módulo obimcore ausente (oráculo da porta no C++ NÃO FOI EXECUTADO) !!!\n")
    import ifcopenshell
    import lote
    import obimcore
    caminho = Path(tempfile.mkdtemp()) / "p1.ifc"
    pesada = lote.base_pesada(caminho, 5, 150)
    f = ifcopenshell.open(str(caminho))
    leves = [w.GlobalId for w in f.by_type("IfcWall") if w.GlobalId != pesada][:5]
    return obimcore, f, pesada, leves


def _iguais(a, b):
    assert set(a) == set(b)
    for g in a:
        for k in ("posicoes", "indices", "caixa", "cor"):
            assert np.array_equal(np.asarray(a[g][k]), np.asarray(b[g][k])), f"{g}.{k} difere entre sessão e arquivo"


def test_p1_caminho_do_arquivo_segue_igual_e_tipo_errado_e_typeerror(base):  # passa hoje e tem de continuar passando
    oc, f, pesada, leves = base
    m = oc.malhas(f, leves)
    assert set(m) == set(leves) and all(len(m[g]["indices"]) for g in leves)
    with pytest.raises(TypeError):
        oc.malhas(object(), leves)


@AINDA_NAO
def test_p1_sem_trava_erro_claro_e_nada_preso(base):
    oc, f, pesada, leves = base
    sm = _sm()
    s = sm.SessaoModelo(f)
    with pytest.raises(sm.TravaNaoSegura):
        oc.malhas(s, leves)
    assert s.estado()["em_uso_cpp"] == 0


@AINDA_NAO
def test_p1_com_ler_resultado_igual_ao_do_arquivo(base):
    oc, f, pesada, leves = base
    s = _sm().SessaoModelo(f)
    with s.ler():
        _iguais(oc.malhas(s, leves + [pesada]), oc.malhas(f, leves + [pesada]))
    assert s.estado()["em_uso_cpp"] == 0


@AINDA_NAO
def test_p1_escritor_ativo_bloqueia_outra_thread_e_o_emprestimo_libera(base):
    oc, f, pesada, leves = base
    sm = _sm()
    s, out = sm.SessaoModelo(f), {}

    def outra(chave):
        try:
            out[chave] = oc.malhas(s, leves)
        except BaseException as e:
            out[chave] = e
    with s.escrever() as esc:
        _iguais(oc.malhas(s, leves), oc.malhas(f, leves))  # o próprio escritor, fora do empréstimo
        th = threading.Thread(target=outra, args=("ativo",), name="p1-geometria")
        th.start()
        th.join(10)
        assert isinstance(out["ativo"], sm.TravaNaoSegura), f"outra thread com o escritor ativo: erro claro ({out['ativo']!r})"
        with esc.emprestar_leitura():
            th = threading.Thread(target=outra, args=("emprestado",), name="p1-geometria")
            th.start()
            th.join(30)
        assert isinstance(out["emprestado"], dict), f"durante o empréstimo a thread de geometria lê: {out['emprestado']!r}"
        _iguais(out["emprestado"], oc.malhas(f, leves))
    assert s.estado()["em_uso_cpp"] == 0


@AINDA_NAO
def test_p1_erro_na_geometria_ainda_chama_sair(base):
    oc, f, pesada, leves = base
    s = _sm().SessaoModelo(f)
    with s.ler():
        with pytest.raises(ValueError):
            oc.malhas(s, ["0" * 22])
        assert s.estado()["em_uso_cpp"] == 0, "a geometria falhou e o C++ não chamou _obimcore_sair"


@AINDA_NAO
def test_p1_emprestimo_que_falha_ainda_chama_sair_e_entrar_que_falha_nao(base):  # lote 70 §2.2 item 2: senão em_uso_cpp fica preso e o produto trava
    oc, f, pesada, leves = base

    class Falsa:  # não é ifcopenshell.file; a porta devolve o que `entrar` der e conta as saídas
        def __init__(s, entrar):
            s.entrar, s.saidas = entrar, 0

        def _obimcore_entrar(s):
            return s.entrar()

        def _obimcore_sair(s):
            s.saidas += 1

    class Recusada(Exception):
        pass

    def recusa():
        raise Recusada("trava recusada")
    errada, recusada = Falsa(object), Falsa(recusa)
    with pytest.raises(TypeError):
        oc.malhas(errada, leves)  # _obimcore_entrar devolve object(): o empréstimo falha
    assert errada.saidas == 1, f"o empréstimo falhou e o C++ chamou _obimcore_sair {errada.saidas} vezes (tem de ser 1)"
    with pytest.raises(Recusada):
        oc.malhas(recusada, leves)  # o erro de _obimcore_entrar sobe como está
    assert recusada.saidas == 0, f"_obimcore_entrar falhou e o C++ chamou _obimcore_sair {recusada.saidas} vezes (nada a soltar)"


@AINDA_NAO
def test_p1_bloqueio_solto_durante_a_geometria_da_sessao(base):  # R1-h, regra 4 do lote 9 §1.4, agora pelo caminho da sessão
    oc, f, pesada, leves = base
    s, marca, fim = _sm().SessaoModelo(f), [], {}

    def geo():
        with s.ler():
            fim["t0"] = time.perf_counter()
            oc.malhas(s, [pesada])
            fim["t1"] = time.perf_counter()
    th = threading.Thread(target=geo, name="p1-geometria")
    th.start()
    while th.is_alive():
        marca.append(time.perf_counter())
        sum(range(200))
    th.join()
    dur = fim["t1"] - fim["t0"]
    assert dur >= 0.1, f"a malha da parede pesada levou {dur * 1000:.0f} ms: o caso não mede nada (voltar ao líder; não mexer nas aberturas)"
    m = [t for t in marca if fim["t0"] <= t <= fim["t1"]]
    gap = max(np.diff([fim["t0"], *m, fim["t1"]]))
    assert gap < 0.05, f"a thread principal ficou {gap * 1000:.0f} ms parada durante {dur * 1000:.0f} ms de geometria: o C++ não soltou o bloqueio"


@AINDA_NAO
def test_p1_saida_do_emprestimo_espera_a_geometria_do_cpp(base):
    oc, f, pesada, leves = base
    s, fim = _sm().SessaoModelo(f), []

    def geo():
        oc.malhas(s, [pesada])
        fim.append(time.perf_counter())
    with s.escrever() as esc:
        with esc.emprestar_leitura():
            th = threading.Thread(target=geo, name="p1-geometria")
            th.start()
            t = time.perf_counter() + 5
            while s.estado()["em_uso_cpp"] == 0 and th.is_alive() and time.perf_counter() < t:
                time.sleep(0.0005)
            visto = s.estado()["em_uso_cpp"]
        depois = s.estado()["em_uso_cpp"]  # ainda dentro de escrever(), logo depois de sair do empréstimo
    th.join(30)
    assert visto == 1, "a geometria da sessão não chegou a entrar (o caso não exercitou a espera)"
    assert depois == 0 and fim, "o escritor voltou com a geometria do C++ ainda lendo o modelo (a saída do empréstimo não esperou)"
