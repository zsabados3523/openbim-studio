# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oraculo F0-S06-T26b (T3): limite de trabalhadores volta ao padrao quando a construcao acaba.
Nao editar este arquivo na implementacao. Sem IFC real: filho real com alvo minimo e relogio injetavel.

CONTRATO DA INTERFACE (decisoes do oraculo para o implementador)
1. `GerenteDesenho.__init__(..., intervalo_estado_s: float = 5.0, timeout_estado_s: float = 0.5, relogio=time.monotonic, ...)`:
   - `intervalo_estado_s`: intervalo minimo T (s, padrao 5.0) entre consultas `estado_construcao` com `construcao_ativa`.
   - `timeout_estado_s`: timeout curto (s, padrao 0.5) da consulta; `relogio`: callable monotonico `() -> float` (padrao `time.monotonic`).
2. Atualizacao automatica: enquanto `construcao_ativa`, `limite_trabalhadores()` e `pedir()` consultam `estado_construcao` no maximo 1x por T s;
   `pendentes == 0`, qualquer `parado` nao-None (`banco_ocupado`, `erro`, etc.) ou processo morto (`SAIDA_MEMORIA` 86) desativam `construcao_ativa`
   e fazem `limite_trabalhadores()` voltar a `None`. Sem `construcao_ativa`, nenhuma consulta e feita.
3. Concorrencia/falha: consulta nunca segura `GerenteDesenho._trava` (`pedir`/`cancelar`/`fechar` livres); erro (`ok=False`/excecao) ou timeout
   mantem estado anterior (`construcao_ativa=True`, sem matar filho vivo) e tenta de novo apos novo T.
4. TOCTOU em `FilhoPersistente.construir()` (ressalva 1): nao reativa `construcao_ativa` se fechado, trocado de processo ou se `estado_construcao`
   ja mostrou fim (`pendentes == 0` ou `parado` preenchido).
"""
from __future__ import annotations

import contextlib, inspect, json, os, threading, time
from pathlib import Path
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtCore")
from PySide6.QtCore import QCoreApplication  # noqa: E402

from openbim_app.desenho import gerente as G  # noqa: E402
from openbim_app.desenho.filho import FilhoPersistente, SAIDA_MEMORIA  # noqa: E402
from openbim_app.desenho.gerente import GerenteDesenho  # noqa: E402
from test_s06_t26_limite_trabalhadores_oraculo import (  # noqa: E402
    _Ouvinte, _PoolEspiao, _esperar_fundo, _girar, _motor_pool,
)

@pytest.fixture(scope="module")
def app():
    return QCoreApplication.instance() or QCoreApplication([])

class _Relogio:
    def __init__(self, inicial: float = 100.0):
        self._trava, self._t = threading.Lock(), float(inicial)
    def __call__(self) -> float:
        with self._trava:
            return self._t
    def avancar(self, delta_s: float) -> float:
        with self._trava:
            self._t += float(delta_s)
            return self._t

def _escrever_estado(pasta: Path, **dados) -> None:
    pasta.mkdir(parents=True, exist_ok=True)
    tmp = pasta / f"estado.{os.getpid()}.{threading.get_ident()}.tmp"
    tmp.write_text(json.dumps(dados), encoding="utf-8")
    tmp.replace(pasta / "estado.json")

def _contar_consultas(pasta: Path) -> int:
    arq = pasta / "consultas.log"
    return len(arq.read_text(encoding="utf-8").splitlines()) if arq.exists() else 0

def _esperar(cond, timeout_s: float = 3.0) -> bool:
    fim = time.monotonic() + timeout_s
    while time.monotonic() < fim:
        if cond():
            return True
        time.sleep(0.01)
    return bool(cond())

def _alvo_t26b(tx, rx):
    """Processo filho minimo para validar polling de `estado_construcao` e TOCTOU sem IFC real."""
    pasta = Path(os.environ["OBIM_T26B_DIR"])
    tx.send_bytes(json.dumps({"tipo": "pronto", "pid": os.getpid(), "protocolo": 1}).encode())
    while True:
        while not rx.poll(0.01):
            if (pasta / "sair_memoria").exists():
                os._exit(SAIDA_MEMORIA)
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
            with open(pasta / "consultas.log", "a", encoding="utf-8") as f:
                f.write(f"{n}\n")
            if est.get("modo") == "erro":
                dados = {"ok": False, "erro": {"tipo": "RuntimeError", "mensagem": "falha_consulta", "rastro": ""}}
            else:
                if est.get("modo") == "pausar":
                    (pasta / "em_estado").write_text(str(n), encoding="utf-8")
                    fim = time.monotonic() + 5.0
                    while time.monotonic() < fim and not (pasta / "liberar_estado").exists():
                        time.sleep(0.005)
                dados = {"ativo": bool(est.get("ativo", True)), "pendentes": int(est.get("pendentes", 0)),
                         "parado": est.get("parado"), "erro": est.get("erro")}
        else:
            dados = {"ok": True}
        tx.send_bytes(json.dumps({"tipo": "resposta", "numero": n, "dados": dados}).encode())
        if op == "estado_construcao" and est.get("modo") == "pausar":
            (pasta / "estado_enviado").write_text(str(n), encoding="utf-8")

@contextlib.contextmanager
def _gerente_real(monkeypatch, pasta: Path, *, motor=None, pendentes=5, **kw):
    pasta.mkdir(parents=True, exist_ok=True)
    _escrever_estado(pasta, pendentes=pendentes, parado=None)
    monkeypatch.setenv("OBIM_T26B_DIR", str(pasta))
    monkeypatch.setenv("OBIM_CACHE_DIR", str(pasta / "cache"))
    instancias: list[FilhoPersistente] = []

    def _criar(arquivo, **fkw):
        f = FilhoPersistente(arquivo, alvo=fkw.pop("alvo", _alvo_t26b), **fkw)
        instancias.append(f)
        return f

    monkeypatch.setattr(G, "FilhoPersistente", _criar)
    arq = pasta / "modelo.ifc"
    arq.write_text("ifc", encoding="utf-8")
    op = {"construir_cache": True, "limite_construcao": 1, "medir_rss_mb": lambda: 1500.0, "intervalo_estado_s": 5.0, **kw}
    g = GerenteDesenho(motor=motor or (lambda *a, **k: {"ok": True}), **op)
    try:
        g.aquecer(str(arq), revisao=1, revisao_salva=1)
        _esperar_fundo(g, timeout_s=10.0)
        assert instancias
        yield g, instancias[-1], _Ouvinte(g)
    finally:
        g.fechar()

# --- Interface ---

def test_interface_t26b():
    p = inspect.signature(GerenteDesenho.__init__).parameters
    assert p["intervalo_estado_s"].default == 5.0 and p["timeout_estado_s"].default == 0.5
    assert p["relogio"].default is time.monotonic

# --- (1) Fim normal (pendentes=0) volta limite a None em ate T s ---

def test_fim_normal_pendentes_zero_volta_limite_para_none(app, monkeypatch, tmp_path):
    relogio = _Relogio(100.0)
    with _gerente_real(monkeypatch, tmp_path, pendentes=4, relogio=relogio) as (g, filho, _o):
        assert filho.construcao_ativa is True and g.limite_trabalhadores() == 1
        _escrever_estado(tmp_path, pendentes=0, parado=None)
        relogio.avancar(5.0)
        assert _esperar(lambda: g.limite_trabalhadores() is None, 3.0)
        assert filho.construcao_ativa is False and _contar_consultas(tmp_path) >= 1

def test_admitir_pedido_detecta_fim_da_construcao(app, monkeypatch, tmp_path):
    relogio, pool, opcoes_vistas = _Relogio(100.0), _PoolEspiao(atraso_s=0.04), []
    with _gerente_real(
        monkeypatch, tmp_path, motor=_motor_pool(pool, opcoes_vistas=opcoes_vistas), pendentes=4, relogio=relogio,
    ) as (g, filho, o):
        assert filho.construcao_ativa is True
        _escrever_estado(tmp_path, pendentes=0, parado=None)
        relogio.avancar(5.0)
        g.pedir("planta", None, "V0")
        assert _girar(lambda: len(o.prontos) == 1) and o.falhas == []
        assert _esperar(lambda: not filho.construcao_ativa, 3.0) and g.limite_trabalhadores() is None
        opcoes_vistas.clear()
        pool.pico = 0
        for i in range(3):
            g.pedir("corte", None, f"V{i + 1}")
        assert _girar(lambda: len(o.prontos) == 4) and o.falhas == [] and pool.pico >= 2
        assert all("threads" not in op for op in opcoes_vistas)

# --- (2) Parado (qualquer motivo) e saida 86 tambem desativam ---

@pytest.mark.parametrize("caso", ["banco_ocupado", "erro", "motivo_personalizado", "saida_86"])
def test_parado_qualquer_motivo_e_saida_86_desativa(app, monkeypatch, tmp_path, caso):
    relogio = _Relogio(100.0)
    with _gerente_real(monkeypatch, tmp_path, pendentes=5, relogio=relogio) as (g, filho, _o):
        assert filho.construcao_ativa is True and g.limite_trabalhadores() == 1
        if caso == "saida_86":
            (tmp_path / "sair_memoria").write_text("86", encoding="utf-8")
            assert _esperar(lambda: filho.pid is None, 5.0)
        else:
            _escrever_estado(tmp_path, pendentes=3, parado=caso, erro=f"detalhe:{caso}")
            relogio.avancar(5.0)
        assert _esperar(lambda: g.limite_trabalhadores() is None, 3.0) and filho.construcao_ativa is False

# --- (3) Taxa limitada a 1 por T s e sem segurar trava de pedir/cancelar/fechar ---

def test_consulta_limitada_a_uma_por_intervalo_t(app, monkeypatch, tmp_path):
    relogio = _Relogio(100.0)
    with _gerente_real(monkeypatch, tmp_path, pendentes=5, relogio=relogio) as (g, _f, o):
        assert g.limite_trabalhadores() == 1
        time.sleep(0.05)
        n0 = _contar_consultas(tmp_path)
        assert n0 <= 1

        relogio.avancar(5.0)  # t = 105.0
        for _ in range(10):
            assert g.limite_trabalhadores() == 1
        relogio.avancar(2.0)  # t = 107.0
        g.pedir("planta", None, "V1")
        assert _girar(lambda: len(o.prontos) == 1) and o.falhas == []
        relogio.avancar(2.5)  # t = 109.5 (< 110.0)
        for _ in range(5):
            assert g.limite_trabalhadores() == 1
        assert _esperar(lambda: _contar_consultas(tmp_path) >= n0 + 1, 2.0)
        time.sleep(0.05)
        assert _contar_consultas(tmp_path) == n0 + 1

        relogio.avancar(0.6)  # t = 110.1 (>= 105.0 + 5.0)
        assert g.limite_trabalhadores() == 1
        assert _esperar(lambda: _contar_consultas(tmp_path) == n0 + 2, 2.0)

def test_consulta_nao_segura_trava_pedir_cancelar_fechar(app, monkeypatch, tmp_path):
    relogio = _Relogio(100.0)
    with _gerente_real(monkeypatch, tmp_path, pendentes=5, timeout_estado_s=1.0, relogio=relogio) as (g, _f, _o):
        assert g.limite_trabalhadores() == 1
        _escrever_estado(tmp_path, pendentes=5, parado=None, modo="pausar")
        relogio.avancar(5.0)
        t_lim = threading.Thread(target=g.limite_trabalhadores, daemon=True)
        try:
            t_lim.start()
            assert _esperar(lambda: (tmp_path / "em_estado").exists(), 3.0)
            trava_livre = g._trava.acquire(blocking=False)
            if trava_livre:
                g._trava.release()
            t0 = time.monotonic()
            k = g.pedir("planta", None, "V_LIVRE")
            g.cancelar(k)
            dt_pc = time.monotonic() - t0
        finally:
            (tmp_path / "liberar_estado").write_text("1", encoding="utf-8")
            t_lim.join(timeout=3.0)
        assert trava_livre and dt_pc < 0.25, f"trava={trava_livre} dt={dt_pc:.3f}s"

        for nome in ("em_estado", "liberar_estado", "estado_enviado"):
            (tmp_path / nome).unlink(missing_ok=True)
        relogio.avancar(5.0)
        t_fechar = None
        try:
            g.pedir("planta", None, "V_FECHAR")
            assert _esperar(lambda: (tmp_path / "em_estado").exists(), 3.0)
            ger_antes = g._geracao
            t_fechar = threading.Thread(target=g.fechar, daemon=True)
            t_fechar.start()
            fechar_passou = _esperar(lambda: g._geracao > ger_antes, 0.25)
        finally:
            (tmp_path / "liberar_estado").write_text("1", encoding="utf-8")
            if t_fechar is not None:
                t_fechar.join(timeout=5.0)
        assert fechar_passou and t_fechar is not None and not t_fechar.is_alive()

# --- (4) Erro ou timeout mantem estado anterior e tenta de novo ---

@pytest.mark.parametrize("falha", ["erro", "timeout"])
def test_erro_ou_timeout_na_consulta_mantem_estado_e_tenta_de_novo(app, monkeypatch, tmp_path, falha):
    relogio = _Relogio(100.0)
    with _gerente_real(monkeypatch, tmp_path, pendentes=5, timeout_estado_s=0.15, relogio=relogio) as (g, filho, _o):
        assert g.limite_trabalhadores() == 1 and filho.pid is not None
        pid0 = filho.pid
        time.sleep(0.04)
        n0 = _contar_consultas(tmp_path)
        _escrever_estado(tmp_path, pendentes=5, parado=None, modo="pausar" if falha == "timeout" else "erro")
        relogio.avancar(5.0)
        try:
            lim = g.limite_trabalhadores()
            if falha == "timeout":
                assert _esperar(lambda: (tmp_path / "em_estado").exists(), 2.0)
                time.sleep(0.25)
            else:
                assert _esperar(lambda: _contar_consultas(tmp_path) > n0, 2.0)
                time.sleep(0.05)
            assert lim == 1 and g.limite_trabalhadores() == 1 and filho.construcao_ativa is True and filho.pid == pid0
        finally:
            if falha == "timeout":
                (tmp_path / "liberar_estado").write_text("1", encoding="utf-8")
        if falha == "timeout":
            assert _esperar(lambda: (tmp_path / "estado_enviado").exists(), 2.0)
        _escrever_estado(tmp_path, pendentes=0, parado=None)
        relogio.avancar(5.0)
        assert _esperar(lambda: g.limite_trabalhadores() is None, 3.0)
        assert filho.construcao_ativa is False and filho.pid == pid0 and _contar_consultas(tmp_path) >= n0 + 2

# --- (5) TOCTOU da ressalva 1 em construir() ---

@pytest.mark.parametrize("cenario", ["fechado", "trocado", "estado_pendentes_zero", "estado_parado"])
def test_construir_toctou_nao_reativa_construcao_ativa(tmp_path, monkeypatch, cenario):
    monkeypatch.setenv("OBIM_T26B_DIR", str(tmp_path))
    arq = tmp_path / "Casa.ifc"
    arq.write_text("ifc", encoding="utf-8")
    _escrever_estado(tmp_path, pendentes=5, parado=None)
    f = FilhoPersistente(arq, ocioso_s=600.0, alvo=_alvo_t26b)
    orig_executar, executou_janela, pids = f.executar, [], {}

    def _acao_concorrente():
        pids["antes"] = f.pid
        if cenario == "fechado":
            f.fechar()
        elif cenario == "trocado":
            _escrever_estado(tmp_path, pendentes=0, parado=None)
            f.invalidar()
            f.aquecer(limite_s=30)
            pids["depois"] = f.pid
        else:
            est = {"pendentes": 0, "parado": None} if cenario == "estado_pendentes_zero" else {"pendentes": 3, "parado": "erro", "erro": "falha"}
            _escrever_estado(tmp_path, **est)
            orig_executar({"op": "estado_construcao", "arquivo": f.arquivo}, limite_s=30)

    def _executar_espiado(*a, **kw):
        res = orig_executar(*a, **kw)
        if not executou_janela and a and isinstance(a[0], dict) and a[0].get("op") == "construir":
            executou_janela.append(True)
            _acao_concorrente()
        return res

    f.executar = _executar_espiado
    try:
        f.construir(str(tmp_path / "geo"), limite_s=30)
        if not executou_janela:
            _acao_concorrente()
        assert f.construcao_ativa is False
        assert (f.pid is None) if cenario == "fechado" else (cenario != "trocado" or (pids["depois"] is not None and pids["depois"] != pids["antes"]))
    finally:
        f.fechar()

# --- (6) Sem construcao ativa nenhuma consulta e feita ---

def test_sem_construcao_ativa_nenhuma_consulta(app, monkeypatch, tmp_path):
    relogio = _Relogio(100.0)
    for nome, construir, pend in (("sem_flag", False, 5), ("ja_pronto", True, 0)):
        pasta = tmp_path / nome
        with _gerente_real(monkeypatch, pasta, pendentes=pend, construir_cache=construir, relogio=relogio) as (g, _f, o):
            relogio.avancar(25.0)
            assert g.limite_trabalhadores() is None
            g.pedir("planta", None, "V1")
            assert _girar(lambda: len(o.prontos) == 1) and o.falhas == [] and _contar_consultas(pasta) == 0

    pasta = tmp_path / "pos_fim"
    with _gerente_real(monkeypatch, pasta, pendentes=4, relogio=relogio) as (g, _f, o):
        _escrever_estado(pasta, pendentes=0, parado=None)
        relogio.avancar(5.0)
        assert _esperar(lambda: g.limite_trabalhadores() is None, 3.0)
        n_fim = _contar_consultas(pasta)
        relogio.avancar(30.0)
        for i in range(5):
            assert g.limite_trabalhadores() is None
            g.pedir("planta", None, f"P{i}")
        assert _girar(lambda: len(o.prontos) == 5) and o.falhas == []
        time.sleep(0.05)
        assert _contar_consultas(pasta) == n_fim
