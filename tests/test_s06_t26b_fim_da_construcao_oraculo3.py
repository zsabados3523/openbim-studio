# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oraculo F0-S06-T26b rodada 3: corrida entre _verificar_estado_construcao()/_adquirir_vaga() e fechar().
Nao editar este arquivo na implementacao. Reutiliza fakes dos oraculos T26b 1 e 2.

CONTRATO ADICIONAL (rodada 3, escopo estreito):
1. `fechar()` concorrente com `_verificar_estado_construcao()` ou `_adquirir_vaga()` nunca levanta
   `RuntimeError` em `join()` (thread ainda nao iniciada) e encerra a thread de consulta antes de retornar.
2. `fechar()` concorrente nunca vaza o processo filho: `filho.pid is None` e PID do SO encerrado.
3. A thread de consulta de estado nao e rastreada em `GerenteDesenho._threads` antes de `start()`,
   sendo iniciada e registrada sob `self._trava` sem janela de corrida.
4. `fechar()` repetido (sequencial ou concorrente) e seguro e idempotente.
"""
from __future__ import annotations

import os, threading
from pathlib import Path
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtCore")
from PySide6.QtCore import QCoreApplication  # noqa: E402
from test_s06_t26b_fim_da_construcao_oraculo import _Relogio, _esperar, _gerente_real  # noqa: E402

@pytest.fixture(scope="module")
def app():
    return QCoreApplication.instance() or QCoreApplication([])

def _pid_vivo(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    try:
        if Path(f"/proc/{pid}/stat").read_text(encoding="utf-8").rsplit(")", 1)[-1].split()[0] == "Z":
            return False
    except OSError:
        pass
    return True

def _instalar_espiao_start(monkeypatch, g, *, esperar_s: float = 0.20):
    orig_start, trava, armado = threading.Thread.start, threading.Lock(), [False]
    est = {
        "chegou": threading.Event(), "liberar": threading.Event(),
        "thread": None, "ident_antes": "nao_capturado", "em_threads_antes": None,
    }

    def _start_espiado(self, *a, **kw):
        with trava:
            capturar = armado[0]
            armado[0] = False if capturar else armado[0]
        if capturar:
            est["thread"], est["ident_antes"], est["em_threads_antes"] = self, self.ident, (self in g._threads)
            est["chegou"].set()
            if esperar_s > 0.0:
                est["liberar"].wait(timeout=esperar_s)
        return orig_start(self, *a, **kw)

    monkeypatch.setattr(threading.Thread, "start", _start_espiado)
    def _armar():
        with trava: armado[0] = True
    def _restaurar():
        est["liberar"].set(); monkeypatch.setattr(threading.Thread, "start", orig_start)
    return _armar, _restaurar, est

def _fechar_capturando(g, erros: list[BaseException]) -> None:
    try:
        g.fechar()
    except BaseException as exc:
        erros.append(exc)

def _snap(filho, pid_antes, est):
    t = est["thread"]
    return filho.pid, _pid_vivo(pid_antes), t, (t.ident if t else None), (t.is_alive() if t else False)

def _assert_sem_vazamento(g, pid_antes, snap) -> None:
    pid_apos, vivo_apos, t_consulta, t_ident, t_viva = snap
    assert pid_apos is None and not vivo_apos, f"filho vazou: pid_antes={pid_antes} pid_apos={pid_apos} vivo={vivo_apos}"
    assert t_consulta is not None and t_ident is not None and not t_viva
    with g._trava:
        assert not g._threads

def test_fechar_concorrente_com_adquirir_vaga_nao_lanca_runtime_error_nem_vaza_filho(app, monkeypatch, tmp_path):
    relogio, v1_rodando = _Relogio(100.0), threading.Event()
    def _motor(tipo, ifc, vista_guid, opcoes, *, cancelar, progresso, **kw):
        if vista_guid == "V1":
            v1_rodando.set()
            cancelar.wait(5.0)
        return {"ok": True}

    with _gerente_real(
        monkeypatch, tmp_path, motor=_motor, pendentes=5, limite_construcao=1, relogio=relogio,
    ) as (g, filho, _o):
        pid_antes = filho.pid
        assert pid_antes is not None and _pid_vivo(pid_antes) and filho.construcao_ativa is True
        g.pedir("planta", None, "V1")
        assert v1_rodando.wait(3.0)
        g.pedir("planta", None, "V2")
        assert _esperar(lambda: len(g._fila_vagas) >= 1, 3.0)

        armar, restaurar, est = _instalar_espiao_start(monkeypatch, g, esperar_s=0.20)
        erros_fechar, nao_iniciadas, snap = [], [], None
        try:
            armar()
            relogio.avancar(5.0)
            assert est["chegou"].wait(3.0)
            if g._trava.acquire(blocking=False):
                try:
                    nao_iniciadas = [t for t in g._threads if t.ident is None]
                finally:
                    g._trava.release()
            _fechar_capturando(g, erros_fechar)
            snap = _snap(filho, pid_antes, est)
            _fechar_capturando(g, erros_fechar)  # fechar() repetido
        finally:
            restaurar()
            filho.fechar()

        assert not erros_fechar, f"fechar() falhou na corrida com _adquirir_vaga(): {erros_fechar!r} (pid_apos={snap[0]}, vivo={snap[1]})"
        assert not nao_iniciadas and est["em_threads_antes"] is False, f"thread nao iniciada exposta a fechar(): {nao_iniciadas!r}"
        _assert_sem_vazamento(g, pid_antes, snap)

def test_fechar_concorrente_com_verificar_estado_e_fechar_repetido_seguro(app, monkeypatch, tmp_path):
    relogio = _Relogio(100.0)
    with _gerente_real(monkeypatch, tmp_path, pendentes=5, relogio=relogio) as (g, filho, _o):
        pid_antes = filho.pid
        assert pid_antes is not None and _pid_vivo(pid_antes) and filho.construcao_ativa is True
        verif_pronta, iniciar_verif = threading.Event(), threading.Event()
        erros_verif, erros_fechar = [], []

        def _rodar_verif():
            verif_pronta.set()
            if iniciar_verif.wait(3.0):
                try:
                    g._verificar_estado_construcao(sincrono=False)
                except BaseException as exc:
                    erros_verif.append(exc)

        t_verif = threading.Thread(target=_rodar_verif, daemon=True)
        t_verif.start()
        assert verif_pronta.wait(3.0)

        armar, restaurar, est = _instalar_espiao_start(monkeypatch, g, esperar_s=0.20)
        t_fechar2, snap = None, None
        try:
            relogio.avancar(5.0)
            armar()
            iniciar_verif.set()
            assert est["chegou"].wait(3.0)
            t_fechar2 = threading.Thread(target=_fechar_capturando, args=(g, erros_fechar), daemon=True)
            t_fechar2.start()
            _fechar_capturando(g, erros_fechar)
            t_fechar2.join(timeout=5.0)
            snap = _snap(filho, pid_antes, est)
            _fechar_capturando(g, erros_fechar)
        finally:
            restaurar()
            t_verif.join(timeout=5.0)
            if t_fechar2 is not None:
                t_fechar2.join(timeout=5.0)
            filho.fechar()

        assert not erros_fechar, f"fechar() concorrente/repetido falhou: {erros_fechar!r} (pid_apos={snap[0]}, vivo={snap[1]})"
        assert not erros_verif, f"_verificar_estado_construcao() falhou: {erros_verif!r}"
        _assert_sem_vazamento(g, pid_antes, snap)

def test_thread_consulta_nao_rastreada_antes_de_start(app, monkeypatch, tmp_path):
    relogio = _Relogio(100.0)
    with _gerente_real(monkeypatch, tmp_path, pendentes=5, relogio=relogio) as (g, filho, _o):
        pid_antes = filho.pid
        assert pid_antes is not None and _pid_vivo(pid_antes) and filho.construcao_ativa is True
        entrou, liberar = threading.Event(), threading.Event()
        filho.consultar_estado_construcao = lambda *a, **kw: (entrou.set(), liberar.wait(3.0), True)[2]
        armar, restaurar, est = _instalar_espiao_start(monkeypatch, g, esperar_s=0.0)
        timer = snap = None
        try:
            relogio.avancar(5.0)
            armar()
            g._verificar_estado_construcao(sincrono=False)
            assert est["chegou"].wait(3.0) and entrou.wait(3.0)
            with g._trava:
                rastreada_apos_start = est["thread"] in g._threads
            timer = threading.Timer(0.05, liberar.set)
            timer.start()
            g.fechar()
            g.fechar()
            snap = _snap(filho, pid_antes, est)
        finally:
            if timer is not None: timer.cancel()
            liberar.set(); restaurar(); filho.fechar()

        assert est["ident_antes"] is None
        assert est["em_threads_antes"] is False, "thread de consulta foi rastreada em _threads antes de start()"
        assert rastreada_apos_start is True
        _assert_sem_vazamento(g, pid_antes, snap)
