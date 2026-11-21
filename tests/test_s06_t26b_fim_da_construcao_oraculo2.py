# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oraculo F0-S06-T26b rodada 2: provas dos itens 1 a 5 da REVISAO.md.
Nao editar este arquivo na implementacao. Reutiliza fakes do oraculo T26b.

CONTRATO ADICIONAL (rodada 2):
1. No maximo 1 consulta `estado_construcao` em voo e 1 por intervalo, mesmo com `intervalo < 2*timeout`
   e varias threads pedindo `limite_trabalhadores()` (sem empilhar na trava do filho).
2. Orcamento unico de timeout em `consultar_estado_construcao(timeout_s)`: esperar `_trava` + IPC
   nunca passa de `timeout_s` (+ folga), nem em `limite_trabalhadores()` nem em `fechar()`.
3. `consultar_estado_construcao()` ao fim da construcao renova `_fim_ultimo` (`podar()`/`executar()`
   seguintes nao matam o filho aquecido por ociosidade).
4. `_construcao_params` gravado sob `_trava` junto de `executar()`: `salvar()`/`invalidar()`/queda
   na janela nao perde nem sobrescreve params; `construir()` com `pendentes == 0` inicial nao deixa params.
5. Thread de consulta rastreada em `_threads`, termina em `fechar()`, falha em `start()` nao prende
   `_consultando_estado`; `_relogio()` lido sob `_trava` (`_ultima_consulta_estado` nunca retrocede);
   `pendentes` nao inteiro em `estado_construcao` retorna `None` sem excecao.
"""
from __future__ import annotations

import json, os, threading, time
from pathlib import Path
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtCore")
from PySide6.QtCore import QCoreApplication  # noqa: E402

from openbim_app.desenho import gerente as G  # noqa: E402
from openbim_app.desenho.filho import FilhoPersistente  # noqa: E402
from openbim_app.desenho.gerente import GerenteDesenho  # noqa: E402
from test_s06_t26_limite_trabalhadores_oraculo import _esperar_fundo  # noqa: E402
from test_s06_t26b_fim_da_construcao_oraculo import (  # noqa: E402
    _Relogio, _alvo_t26b, _contar_consultas, _escrever_estado, _esperar, _gerente_real,
)

@pytest.fixture(scope="module")
def app():
    return QCoreApplication.instance() or QCoreApplication([])

def _alvo_pendentes_bruto(tx, rx):
    pasta = Path(os.environ["OBIM_T26B_DIR"])
    tx.send_bytes(json.dumps({"tipo": "pronto", "pid": os.getpid(), "protocolo": 1}).encode())
    while True:
        try:
            p = json.loads(rx.recv_bytes())
        except EOFError:
            return
        op, n = p.get("op"), p["numero"]
        if op == "encerrar":
            return
        est = json.loads((pasta / "estado.json").read_text(encoding="utf-8"))
        if op == "abrir":
            dados = {"aberto": True}
        elif op == "construir":
            dados = {"aceito": True, "pendentes": int(est.get("pendentes", 0))}
        elif op == "estado_construcao":
            pend = est["pendentes_bruto"] if "pendentes_bruto" in est else int(est.get("pendentes", 0))
            dados = {"ativo": True, "pendentes": pend, "parado": est.get("parado"), "erro": None}
        else:
            dados = {"ok": True}
        tx.send_bytes(json.dumps({"tipo": "resposta", "numero": n, "dados": dados}).encode())

def _novo_filho(pasta: Path, monkeypatch, *, pendentes=5, ocioso_s=600.0, relogio=time.monotonic, alvo=_alvo_t26b):
    pasta.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("OBIM_T26B_DIR", str(pasta))
    arq = pasta / "Casa.ifc"
    arq.write_text("ifc", encoding="utf-8")
    _escrever_estado(pasta, pendentes=pendentes, parado=None)
    return FilhoPersistente(arq, ocioso_s=ocioso_s, relogio=relogio, alvo=alvo)

# --- (1) No maximo 1 consulta em voo e 1 por intervalo (intervalo < 2*timeout) ---

def test_no_maximo_uma_consulta_em_voo_e_uma_por_intervalo(app, monkeypatch, tmp_path):
    relogio = _Relogio(100.0)
    with _gerente_real(
        monkeypatch, tmp_path, pendentes=5, intervalo_estado_s=0.0625, timeout_estado_s=0.60, relogio=relogio,
    ) as (g, filho, _o):
        trava_m, em_voo, pico, chamadas = threading.Lock(), [0], [0], [0]
        orig = filho.consultar_estado_construcao
        def _espiado(*a, **kw):
            with trava_m:
                em_voo[0] += 1; chamadas[0] += 1; pico[0] = max(pico[0], em_voo[0])
            try:
                return orig(*a, **kw)
            finally:
                with trava_m:
                    em_voo[0] -= 1
        filho.consultar_estado_construcao = _espiado
        _escrever_estado(tmp_path, pendentes=5, parado=None, modo="pausar")
        relogio.avancar(0.0625)
        t0 = threading.Thread(target=g.limite_trabalhadores, daemon=True)
        extras, res_extras = [], []
        try:
            t0.start()
            assert _esperar(lambda: (tmp_path / "em_estado").exists(), 3.0)
            for _ in range(5):
                relogio.avancar(0.0625)
                t = threading.Thread(target=lambda: res_extras.append(g.limite_trabalhadores()), daemon=True)
                t.start(); extras.append(t)
            g.cancelar(g.pedir("planta", None, "V_EM_VOO"))
            fim_espera = time.monotonic() + 0.18
            for t in extras:
                t.join(timeout=max(0.0, fim_espera - time.monotonic()))
            empilharam = any(t.is_alive() for t in extras)
        finally:
            (tmp_path / "liberar_estado").write_text("1", encoding="utf-8")
            t0.join(timeout=3.0)
            for t in extras:
                t.join(timeout=3.0)
        assert not empilharam, f"empilharam na trava do filho (pico={pico[0]}, chamadas={chamadas[0]})"
        assert pico[0] == 1 and chamadas[0] == 1 and _contar_consultas(tmp_path) == 1 and res_extras == [1] * 5

        for nome in ("em_estado", "liberar_estado", "estado_enviado"):
            (tmp_path / nome).unlink(missing_ok=True)
        _escrever_estado(tmp_path, pendentes=5, parado=None)
        relogio.avancar(0.125)
        assert g.limite_trabalhadores() == 1
        base_c, base_log = chamadas[0], _contar_consultas(tmp_path)
        for delta, esp in ((0.03125, 0), (0.0625, 1)):
            relogio.avancar(delta)
            bar = threading.Barrier(8)
            ts = [threading.Thread(target=lambda b=bar: (b.wait(), g.limite_trabalhadores()), daemon=True) for _ in range(8)]
            for t in ts: t.start()
            for t in ts: t.join(timeout=3.0)
            assert pico[0] == 1 and chamadas[0] == base_c + esp and _contar_consultas(tmp_path) == base_log + esp

# --- (2) Orcamento unico de timeout com trava ocupada (direto, limite_trabalhadores, fechar) ---

@pytest.mark.parametrize("modo", ["direto", "limite", "fechar"])
def test_orcamento_timeout_unico_com_trava_ocupada(app, monkeypatch, tmp_path, modo):
    timeout_s, segurar_s, teto_s, relogio = 0.30, 0.22, 0.42, _Relogio(100.0)
    with _gerente_real(
        monkeypatch, tmp_path, pendentes=5, intervalo_estado_s=5.0, timeout_estado_s=timeout_s, relogio=relogio,
    ) as (g, filho, _o):
        pid0 = filho.pid
        assert pid0 is not None and filho.construcao_ativa is True
        _escrever_estado(tmp_path, pendentes=5, parado=None, modo="pausar")
        segurando, soltar = threading.Event(), threading.Event()
        def _ocupar():
            with filho._trava:
                segurando.set(); soltar.wait(segurar_s)
        t_ocup = threading.Thread(target=_ocupar, daemon=True)
        t_ocup.start(); assert segurando.wait(2.0)
        t_consulta = None
        try:
            t0 = time.monotonic()
            if modo == "direto":
                res = filho.consultar_estado_construcao(timeout_s=timeout_s)
                dt = time.monotonic() - t0
                assert res is None and filho.construcao_ativa is True and filho.pid == pid0
            elif modo == "limite":
                relogio.avancar(5.0)
                lim = g.limite_trabalhadores()
                dt = time.monotonic() - t0
                assert lim == 1 and filho.construcao_ativa is True and filho.pid == pid0
            else:
                t_consulta = threading.Thread(target=lambda: filho.consultar_estado_construcao(timeout_s=timeout_s), daemon=True)
                t_consulta.start()
                assert _esperar(lambda: (tmp_path / "em_estado").exists() or not t_consulta.is_alive(), 1.0)
                filho.fechar()
                dt = time.monotonic() - t0
                assert filho.pid is None
        finally:
            soltar.set(); (tmp_path / "liberar_estado").write_text("1", encoding="utf-8")
            t_ocup.join(timeout=3.0)
            if t_consulta is not None: t_consulta.join(timeout=3.0)
        assert dt <= teto_s, f"modo={modo} estourou orcamento unico: {dt:.3f}s > {teto_s:.2f}s"

# --- (3) Consultar estado ao fim da construcao renova _fim_ultimo ---

@pytest.mark.parametrize("proximo", ["podar", "executar"])
def test_consultar_estado_fim_construcao_renova_fim_ultimo(tmp_path, monkeypatch, proximo):
    relogio = _Relogio(0.0)
    f = _novo_filho(tmp_path, monkeypatch, pendentes=5, ocioso_s=600.0, relogio=relogio)
    try:
        f.construir(str(tmp_path / "geo"), limite_s=30)
        pid0 = f.pid
        assert pid0 is not None and f.construcao_ativa is True
        relogio.avancar(650.0)
        _escrever_estado(tmp_path, pendentes=0, parado=None)
        assert f.consultar_estado_construcao(timeout_s=1.0) is False
        assert f.construcao_ativa is False and f.pid == pid0
        relogio.avancar(10.0)
        if proximo == "podar":
            f.podar()
        else:
            f.executar({"op": "ping", "arquivo": f.arquivo}, limite_s=10)
        assert f.pid == pid0, f"{proximo}() matou filho aquecido apos fim da construcao"
        relogio.avancar(601.0); f.podar()
        assert f.pid is None
    finally:
        f.fechar()

# --- (4) _construcao_params gravado sob trava junto de executar() ---

@pytest.mark.parametrize("cenario", ["salvar", "invalidar", "queda", "sobrescreve"])
def test_construcao_params_sob_trava_na_janela_e_pendentes_zero(tmp_path, monkeypatch, cenario):
    if cenario == "salvar":
        f0 = _novo_filho(tmp_path / "p0", monkeypatch, pendentes=0)
        try:
            f0.construir(str(tmp_path / "p0" / "geo"), limite_s=30)
            assert f0.construcao_ativa is False and f0._construcao_params is None
            _escrever_estado(tmp_path / "p0", pendentes=5, parado=None)
            f0.salvar(); f0.aquecer(limite_s=30)
            assert f0.construcao_ativa is False and f0._construcao_params is None
        finally:
            f0.fechar()
    pasta = tmp_path / cenario
    f = _novo_filho(pasta, monkeypatch, pendentes=5)
    pasta1, pasta2, orig_executar, executou_janela = pasta / "geo1", pasta / "geo2", f.executar, []

    def _acao_na_janela():
        if cenario == "salvar": f.salvar()
        elif cenario == "invalidar": f.invalidar()
        elif cenario == "queda":
            assert f._proc is not None; f._proc.kill(); f._proc.join(timeout=3.0)
        else:
            f.invalidar(); f.construir(str(pasta2), lote_max=99, limite_s=30)

    def _executar_espiado(*a, **kw):
        res = orig_executar(*a, **kw)
        if not executou_janela and a and isinstance(a[0], dict) and a[0].get("op") == "construir":
            executou_janela.append(True); _acao_na_janela()
        return res

    f.executar = _executar_espiado
    try:
        f.construir(str(pasta1), lote_max=11, limite_s=30)
        if not executou_janela: _acao_na_janela()
        assert f._construcao_params is not None
        if cenario == "sobrescreve":
            assert f._construcao_params["pasta_cache"] == str(pasta2) and f._construcao_params["lote_max"] == 99
        else:
            assert f._construcao_params["pasta_cache"] == str(pasta1) and f._construcao_params["lote_max"] == 11
            f.aquecer(limite_s=30); assert f.construcao_ativa is True
    finally:
        f.fechar()

# --- (5) Thread rastreada/fechar/start, relogio sob trava e pendentes malformado ---

def test_thread_consulta_rastreada_e_termina_em_fechar(app, monkeypatch, tmp_path):
    relogio = _Relogio(100.0)
    with _gerente_real(monkeypatch, tmp_path, pendentes=5, relogio=relogio) as (g, filho, _o):
        entrou, liberar, terminou, t_ref = threading.Event(), threading.Event(), threading.Event(), []
        def _pausado(*a, **kw):
            t_ref.append(threading.current_thread()); entrou.set()
            try:
                liberar.wait(2.0); return True
            finally:
                terminou.set()
        filho.consultar_estado_construcao = _pausado
        relogio.avancar(5.0); g.cancelar(g.pedir("planta", None, "V_TRACK"))
        assert entrou.wait(2.0)
        t_consulta = t_ref[0]
        with g._trava: rastreada = t_consulta in g._threads
        timer = threading.Timer(0.12, liberar.set); timer.start()
        try:
            g.fechar(); terminou_em_fechar = terminou.is_set() and not t_consulta.is_alive()
        finally:
            timer.cancel(); liberar.set(); t_consulta.join(timeout=2.0)
        assert rastreada and terminou_em_fechar
        with g._trava: assert t_consulta not in g._threads

def test_falha_start_thread_consulta_nao_trava_consultando_estado(app, monkeypatch, tmp_path):
    relogio = _Relogio(100.0)
    with _gerente_real(monkeypatch, tmp_path, pendentes=5, relogio=relogio) as (g, filho, _o):
        relogio.avancar(5.0)
        armado, orig_start = [True], threading.Thread.start
        def _start_falho(self, *a, **kw):
            if armado[0]:
                armado[0] = False; raise RuntimeError("falha_start_teste")
            return orig_start(self, *a, **kw)
        monkeypatch.setattr(threading.Thread, "start", _start_falho)
        try:
            g.pedir("planta", None, "V_ERR")
        except RuntimeError:
            pass
        finally:
            monkeypatch.setattr(threading.Thread, "start", orig_start)
        assert g._consultando_estado is False
        _esperar_fundo(g, timeout_s=2.0)
        with g._trava: assert not g._threads
        _escrever_estado(tmp_path, pendentes=0, parado=None); relogio.avancar(5.0)
        assert g.limite_trabalhadores() is None and filho.construcao_ativa is False

def test_relogio_lido_sob_trava_ultima_consulta_nao_retrocede(app, monkeypatch, tmp_path):
    base, t_main, g_ref = _Relogio(100.0), threading.current_thread(), []
    leituras_com_trava, injetou, pico_ultima = [], [], [0.0]
    def _relogio_espiado() -> float:
        t = base()
        if g_ref:
            g = g_ref[0]
            livre = g._trava.acquire(blocking=False)
            if livre: g._trava.release()
            leituras_com_trava.append(not livre)
            if livre and not injetou and threading.current_thread() is not t_main:
                injetou.append(True); base.avancar(10.0)
                g._verificar_estado_construcao(sincrono=False)
                with g._trava: pico_ultima[0] = max(pico_ultima[0], float(g._ultima_consulta_estado or 0.0))
        return t
    _escrever_estado(tmp_path, pendentes=5, parado=None)
    monkeypatch.setenv("OBIM_T26B_DIR", str(tmp_path))
    monkeypatch.setenv("OBIM_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setattr(G, "FilhoPersistente", lambda arq, **kw: FilhoPersistente(arq, alvo=_alvo_t26b, **kw))
    arq = tmp_path / "modelo.ifc"; arq.write_text("ifc", encoding="utf-8")
    g = GerenteDesenho(
        motor=lambda *a, **k: {"ok": True}, construir_cache=True, limite_construcao=1,
        medir_rss_mb=lambda: 1500.0, intervalo_estado_s=5.0, relogio=_relogio_espiado,
    )
    g_ref.append(g)
    try:
        g.aquecer(str(arq), revisao=1, revisao_salva=1); _esperar_fundo(g, timeout_s=10.0)
        with g._trava: ultima_pos_aquecer = g._ultima_consulta_estado
        base.avancar(5.0); assert g.limite_trabalhadores() == 1
        assert ultima_pos_aquecer is not None and ultima_pos_aquecer >= pico_ultima[0]
        assert len(leituras_com_trava) >= 2 and all(leituras_com_trava)
    finally:
        g.fechar()

@pytest.mark.parametrize("pendentes_ruim", ["abc", None, {"invalido": 1}])
def test_estado_construcao_pendentes_malformado_retorna_none(tmp_path, monkeypatch, pendentes_ruim):
    f = _novo_filho(tmp_path, monkeypatch, pendentes=5, alvo=_alvo_pendentes_bruto)
    try:
        f.construir(str(tmp_path / "geo"), limite_s=30); pid0 = f.pid
        assert pid0 is not None and f.construcao_ativa is True
        _escrever_estado(tmp_path, pendentes=5, pendentes_bruto=pendentes_ruim, parado=None)
        assert f.consultar_estado_construcao(timeout_s=1.0) is None and f.construcao_ativa is True and f.pid == pid0
        _escrever_estado(tmp_path, pendentes=0, parado=None)
        assert f.consultar_estado_construcao(timeout_s=1.0) is False and f.construcao_ativa is False and f.pid == pid0
    finally:
        f.fechar()
