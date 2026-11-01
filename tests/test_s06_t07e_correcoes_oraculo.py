# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo F0-S06-T07e0, correções pedidas pelo Opus na T07e1 (LOTE_OPUS_86, item 1, bugs 1 a 10). Não editar este arquivo nem `s06_t07e_corr_aux.py` na implementação; quem tira o `@AINDA_NAO_CORR`
(xfail estrito) é o autor do oráculo, em commit próprio, depois da correção. Complementa `test_s06_t07e_auxiliar_oraculo.py` (nada ali muda). CONTRATO novo ([P] = escolha do oráculo):
1. `processo.entrada`: o gancho de queda `OBIM_TESTE_AUX_SEGV` roda FORA de qualquer `try` da função e sem `ctypes.string_at` (no Windows o ctypes vira `OSError` e o `except` o entregaria como `FalhaNoAuxiliar`); use `faulthandler._sigsegv()`.
2. O filho é `daemon=True` (fechar o programa durante um desenho não espera o filho).
3. `preparar` não deixa a pasta `obim-desenho-*` se `ifc.write` levantar (o erro original sobe).
4. `caixas` calcula com `ifcopenshell.geom.iterator(settings, f, threads, include=...)`, com `threads` do pedido (espião no mesmo processo).
5. [P] `preparar` apaga as pastas `obim-desenho-*` de `tempfile.gettempdir()` com mtime de mais de 1 dia (e só elas).
6. `Preparado.fechar` que desiste da pasta depois das tentativas registra um aviso (`logging.WARNING`) e não levanta.
7. Mensagem do filho que não é JSON, ou resposta cujo `dados` não é dict -> `ProtocoloInvalido` (filho morto, pasta e canal fechados).
8. Filho que sai com código 0 sem resposta -> `AuxiliarCaiu` com `codigo_saida == 0` ou `ProtocoloInvalido`; nunca um código inventado.
10. Se `proc.start()` falhar, as duas pontas do canal ficam fechadas e o erro original sobe.
(O bug 9, `join(5)` com aviso, não tem caso: depende de um filho que não morre ao `kill`.)"""
import ast
import logging
import multiprocessing
import os
import shutil
import threading
import time
from pathlib import Path

import pytest
import s06_t07e_aux as T
from test_s06_t07e_auxiliar_oraculo import _loc, _pedido, _sobras, _x, tmp_aux  # noqa: F401

RAIZ = Path(__file__).resolve().parent.parent


def test_bug1_gancho_segv_fora_do_try_e_sem_ctypes():
    texto = (RAIZ / "geometria" / "obim_geometria" / "processo.py").read_text(encoding="utf-8")
    arvore = ast.parse(texto)
    entrada = next(n for n in ast.walk(arvore) if isinstance(n, ast.FunctionDef) and n.name == "entrada")
    for t in (n for n in ast.walk(entrada) if isinstance(n, ast.Try)):
        dentro = [c.value for b in t.body for c in ast.walk(b) if isinstance(c, ast.Constant) and isinstance(c.value, str)]
        assert not any("OBIM_TESTE_AUX_SEGV" in v for v in dentro), "gancho SEGV dentro de um try: no Windows o except o engole"
    assert "OBIM_TESTE_AUX_SEGV" in texto and "string_at" not in texto, "queda de verdade, não ctypes.string_at (OSError no Windows)"


def test_bug2_filho_e_daemon(tmp_aux, monkeypatch):
    X = _x()
    f, _ = T.modelo()
    monkeypatch.setenv("OBIM_TESTE_AUX_DORMIR_S", "20")
    ev, vistos = threading.Event(), []
    with X.preparar(f, _pedido(f)) as p:
        th = threading.Thread(target=lambda: pytest.raises(X.DesenhoCancelado, X.executar, p, cancelar=ev))
        th.start()
        fim = time.monotonic() + 15
        while not multiprocessing.active_children() and time.monotonic() < fim:
            time.sleep(0.02)
        vistos = [c.daemon for c in multiprocessing.active_children()]
        ev.set()
        th.join(30)
    assert vistos == [True]


def test_bug3_preparar_nao_deixa_pasta_se_a_gravacao_falha(tmp_aux):
    X = _x()

    class Disco:
        def write(self, caminho):
            raise OSError("disco cheio")
    with pytest.raises(OSError, match="disco cheio"):
        X.preparar(Disco(), {"op": "caixas", "elementos": []})
    assert _sobras(tmp_aux) == []


def test_bug4_caixas_usa_iterator_com_as_threads_do_pedido(tmp_aux, monkeypatch):
    import ifcopenshell.geom as G
    X, L = _x(), _loc()
    f, d = T.modelo()
    chamadas, original = [], G.iterator
    monkeypatch.setattr(G, "iterator", lambda *a, **k: chamadas.append((a, k)) or original(*a, **k))
    with X.preparar(f, _pedido(f, "caixas", "P", "M", threads=3)) as p:
        r = X.executar(p, executor=L.executar)
    assert chamadas and all((a[2] if len(a) > 2 else k.get("num_threads")) == 3 and k.get("include") for a, k in chamadas)
    assert set(r["caixas_envolventes"]) == {str(d["P"].id()), str(d["M"].id())}


def test_bug5_preparar_apaga_so_as_pastas_velhas(tmp_aux):
    X = _x()
    f, _ = T.modelo()
    velha, nova, outra = (tmp_aux / n for n in ("obim-desenho-velha", "obim-desenho-nova", "outra-pasta"))
    for p in (velha, nova, outra):
        p.mkdir()
    dois_dias = time.time() - 2 * 86400
    os.utime(velha, (dois_dias, dois_dias))
    os.utime(outra, (dois_dias, dois_dias))
    with X.preparar(f, _pedido(f)):
        assert not velha.exists() and nova.exists() and outra.exists()


def test_bug6_fechar_que_desiste_avisa_no_log(tmp_aux, monkeypatch, caplog):
    X = _x()
    f, _ = T.modelo()
    p = X.preparar(f, _pedido(f))

    def nao(*a, **k):
        raise OSError("em uso")
    monkeypatch.setattr(shutil, "rmtree", nao)
    with caplog.at_level(logging.WARNING):
        p.fechar()  # não levanta
    assert any(r.levelno >= logging.WARNING for r in caplog.records)
    monkeypatch.undo()
    shutil.rmtree(p.pasta, ignore_errors=True)


@pytest.mark.parametrize("alvo", ["entrada_lixo", "entrada_dados_lista"])
def test_bug7_resposta_que_nao_e_protocolo_vira_protocolo_invalido(tmp_aux, monkeypatch, alvo):
    X = _x()
    import s06_t07e_corr_aux as C
    f, _ = T.modelo()
    monkeypatch.setattr(X, "entrada", getattr(C, alvo))
    with X.preparar(f, _pedido(f)) as p:
        with pytest.raises(X.ProtocoloInvalido):
            X.executar(p)
    assert multiprocessing.active_children() == [] and _sobras(tmp_aux) == []


def test_bug8_saida_zero_sem_resposta_nao_inventa_codigo(tmp_aux, monkeypatch):
    X = _x()
    import s06_t07e_corr_aux as C
    f, _ = T.modelo()
    monkeypatch.setattr(X, "entrada", C.entrada_muda)
    with X.preparar(f, _pedido(f)) as p:
        with pytest.raises((X.AuxiliarCaiu, X.ProtocoloInvalido)) as e:
            X.executar(p)
    if isinstance(e.value, X.AuxiliarCaiu):
        assert e.value.codigo_saida == 0


def test_bug10_start_que_falha_fecha_as_pontas(tmp_aux, monkeypatch):
    X = _x()
    f, _ = T.modelo()
    pontas, real = [], multiprocessing.get_context

    class Ctx:
        def Pipe(self, duplex=True):
            rx, tx = real("spawn").Pipe(duplex=duplex)
            pontas.extend([rx, tx])
            return rx, tx

        def Process(self, *a, **k):
            class P:
                def start(self):
                    raise OSError("sem recursos")

                def is_alive(self):
                    return False

                def join(self, *a, **k):
                    pass

                def kill(self):
                    pass
            return P()
    monkeypatch.setattr(multiprocessing, "get_context", lambda *a, **k: Ctx())
    with X.preparar(f, _pedido(f)) as p:
        with pytest.raises(OSError, match="sem recursos"):
            X.executar(p)
    assert len(pontas) == 2 and all(c.closed for c in pontas)
