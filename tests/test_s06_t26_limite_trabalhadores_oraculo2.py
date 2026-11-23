# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oraculo F0-S06-T26 rodada 2: provas dos itens 1 a 5 da REVISAO.md.
Nao editar este arquivo na implementacao. Sem IFC real: reutiliza fakes/padroes do oraculo 1.

CONTRATO ADICIONAL (rodada 2):
1. Pedido na fila cuja geracao muda por `invalidar()`/`salvar()` rele geracao apos `_adquirir_vaga`
   e NAO leva `caminho_ifc`, `assinatura_ifc` nem `filho` velhos ao motor.
2. `_medir_rss_conjunto_mb()` tolera thread efemera (`/proc`) ou processo filho (`psutil`) que some
   entre listar e ler sem abortar a soma restante.
3. `medir_rss_mb` que falha ou devolve NaN/+inf/-inf/negativo aplica reserva conservadora:
   nunca admite 2o trabalhador sem leitura valida, `limite_trabalhadores()` sempre int >= 1 e pico <= teto.
4. `FilhoPersistente.construcao_ativa` vira `False` apos `SAIDA_MEMORIA` ociosa (processo morto)
   e apos `fechar()`/`invalidar()`/`salvar()` durante `construir()` (sem corrida que a reative).
5. Fila FIFO estrita (sem furar fila) e nenhuma medicao de RSS segura a trava de `pedir`/`cancelar`/`fechar`.
"""
from __future__ import annotations

import json, os, sys, threading, time, types
from pathlib import Path
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtCore")
from PySide6.QtCore import QCoreApplication  # noqa: E402

from openbim_app.desenho import gerente as G  # noqa: E402
from openbim_app.desenho.filho import FilhoPersistente, SAIDA_MEMORIA  # noqa: E402
from openbim_app.desenho.gerente import GerenteDesenho  # noqa: E402
from test_s06_t26_limite_trabalhadores_oraculo import (  # noqa: E402
    _PoolEspiao, _aquecer_construindo, _gerente, _girar, _motor_pool,
)


@pytest.fixture(scope="module")
def app():
    return QCoreApplication.instance() or QCoreApplication([])


def _alvo_saida_memoria_ociosa(tx, rx):
    pasta = Path(os.environ["OBIM_T26_OR2_DIR"])
    tx.send_bytes(json.dumps({"tipo": "pronto", "pid": os.getpid(), "protocolo": 1}).encode())
    while True:
        try:
            p = json.loads(rx.recv_bytes())
        except EOFError:
            return
        if p.get("op") == "encerrar":
            return
        dados = {"aceito": True, "pendentes": 5} if p.get("op") == "construir" else {"ok": True}
        tx.send_bytes(json.dumps({"tipo": "resposta", "numero": p["numero"], "dados": dados}).encode())
        if p.get("op") == "construir":
            fim = time.monotonic() + 10.0
            while time.monotonic() < fim:
                if (pasta / "sair_memoria").exists():
                    os._exit(SAIDA_MEMORIA)
                time.sleep(0.01)
            return


def _alvo_construir_pausado(tx, rx):
    pasta = Path(os.environ["OBIM_T26_OR2_DIR"])
    tx.send_bytes(json.dumps({"tipo": "pronto", "pid": os.getpid(), "protocolo": 1}).encode())
    while True:
        try:
            p = json.loads(rx.recv_bytes())
        except EOFError:
            return
        if p.get("op") == "encerrar":
            return
        if p.get("op") == "construir":
            (pasta / "no_construir").write_text("1", encoding="utf-8")
            fim = time.monotonic() + 10.0
            while time.monotonic() < fim and not (pasta / "liberar_construir").exists():
                time.sleep(0.005)
        dados = {"aceito": True, "pendentes": 5} if p.get("op") == "construir" else {"ok": True}
        tx.send_bytes(json.dumps({"tipo": "resposta", "numero": p["numero"], "dados": dados}).encode())


# --- ITEM 1: geracao relida apos adquirir vaga ---

@pytest.mark.parametrize("acao", ["invalidar", "salvar"])
def test_pedido_na_fila_invalidado_ou_salvo_nao_leva_estado_velho(app, monkeypatch, tmp_path, acao):
    entrou_v1, portao_v1, v2_na_fila = threading.Event(), threading.Event(), threading.Event()
    recebidos: dict[str, tuple[dict, object]] = {}

    def medir():
        if entrou_v1.is_set():
            v2_na_fila.set()
        return 5000.0

    def motor(tipo, ifc, guid, opcoes, *, cancelar, progresso, filho=None):
        recebidos[guid] = (dict(opcoes), filho)
        if guid == "V1":
            entrou_v1.set()
            portao_v1.wait(5.0)
        return {"vista": guid}

    try:
        with _gerente(
            monkeypatch, tmp_path, motor=motor, construir_cache=True,
            limite_construcao=2, teto_memoria_mb=6500.0, custo_trabalhador_mb=2000.0, medir_rss_mb=medir,
        ) as (g, arq, o):
            _aquecer_construindo(g, arq)
            g.pedir("planta", None, "V1", caminho_ifc=str(arq), revisao=1, revisao_salva=1)
            assert entrou_v1.wait(5.0)
            g.pedir("planta", None, "V2", caminho_ifc=str(arq), revisao=1, revisao_salva=1)
            v2_na_fila.wait(0.15)
            time.sleep(0.04)
            getattr(g, acao)()
            portao_v1.set()
            assert _girar(lambda: len(o.prontos) == 2) and o.falhas == []
            op_v1, filho_v1 = recebidos["V1"]
            assert "caminho_ifc" in op_v1 and "assinatura_ifc" in op_v1 and filho_v1 is not None
            op_v2, filho_v2 = recebidos["V2"]
            assert "caminho_ifc" not in op_v2 and "assinatura_ifc" not in op_v2 and filho_v2 is None
    finally:
        portao_v1.set()


# --- ITEM 2: medicao de RSS tolera thread efemera / filho morto ---

def test_medir_rss_proc_tolera_thread_efemera_e_filho_morto(monkeypatch, tmp_path):
    fake_proc = tmp_path / "proc"
    for d in ("100/task/101", "100/task/102", "200/task"):
        (fake_proc / d).mkdir(parents=True)
    (fake_proc / "100/status").write_text("Name:\tpy\nVmRSS:\t102400 kB\n", encoding="utf-8")
    (fake_proc / "200/status").write_text("Name:\tfilho\nVmRSS:\t256000 kB\n", encoding="utf-8")
    (fake_proc / "100/task/101/children").symlink_to(tmp_path / "thread_efemera_sumiu")
    (fake_proc / "100/task/102/children").write_text("201 200\n", encoding="utf-8")

    class _ProcPath:
        def __init__(self, p):
            s = str(p)
            self._real = fake_proc / s[6:] if s.startswith("/proc/") else Path(p)
        __fspath__ = lambda self: os.fspath(self._real)
        __truediv__ = lambda self, o: _ProcPath(self._real / o)
        is_dir = lambda self: self._real.is_dir()
        exists = lambda self: self._real.exists()
        read_text = lambda self, *a, **kw: self._real.read_text(*a, **kw)
        glob = lambda self, pat: [_ProcPath(p) for p in sorted(self._real.glob(pat), key=str)]
        iterdir = lambda self: [_ProcPath(p) for p in sorted(self._real.iterdir(), key=str)]

    orig_isdir = os.path.isdir

    def _ler_vmrss_falso(pid: int) -> float:
        with open(fake_proc / str(pid) / "status", "r", encoding="utf-8") as f:
            for linha in f:
                if linha.startswith("VmRSS:"):
                    return float(linha.split()[1]) / 1024.0
        return 0.0

    monkeypatch.setattr(os, "getpid", lambda: 100)
    monkeypatch.setattr(os.path, "isdir", lambda p: (fake_proc / str(p)[6:]).is_dir() if str(p).startswith("/proc/") else orig_isdir(p))
    monkeypatch.setattr(G, "Path", _ProcPath)
    monkeypatch.setattr(G, "_ler_vmrss_mb", _ler_vmrss_falso)
    assert G._medir_rss_conjunto_mb() == pytest.approx(350.0)


def test_medir_rss_psutil_tolera_filho_que_some(monkeypatch):
    orig_isdir = os.path.isdir
    monkeypatch.setattr(os.path, "isdir", lambda p: False if str(p).startswith("/proc/") else orig_isdir(p))

    class _Error(Exception): pass
    class _NoSuchProcess(_Error): pass
    class _ZombieProcess(_NoSuchProcess): pass
    class _AccessDenied(_Error): pass

    class _ProcErro:
        def __init__(self, exc): self._exc = exc
        def memory_info(self): raise self._exc

    class _ProcVivo:
        def __init__(self, mb: float, filhos=()): self._mb, self._filhos = mb, list(filhos)
        def memory_info(self): return types.SimpleNamespace(rss=int(self._mb * 1024 * 1024))
        def children(self, recursive=False): return list(self._filhos)

    fake_psutil = types.ModuleType("psutil")
    fake_psutil.Error, fake_psutil.NoSuchProcess = _Error, _NoSuchProcess
    fake_psutil.ZombieProcess, fake_psutil.AccessDenied = _ZombieProcess, _AccessDenied
    fake_psutil.Process = lambda pid: _ProcVivo(100.0, [_ProcErro(_NoSuchProcess("sumiu")), _ProcErro(_AccessDenied("negado")), _ProcVivo(250.0)])
    monkeypatch.setitem(sys.modules, "psutil", fake_psutil)
    assert G._medir_rss_conjunto_mb() == pytest.approx(350.0)


# --- ITEM 3: medir_rss_mb invalido -> reserva conservadora e int >= 1 ---

def test_medir_rss_invalido_limite_inteiro_um_e_nunca_admite_segundo(app, monkeypatch, tmp_path):
    ruins = [
        ("erro", lambda: (_ for _ in ()).throw(RuntimeError("falha rss"))),
        ("nan", lambda: float("nan")),
        ("inf", lambda: float("inf")),
        ("neg_inf", lambda: float("-inf")),
        ("negativo", lambda: -500.0),
    ]
    for nome, fn in ruins:
        pool = _PoolEspiao(atraso_s=0.05, base_mb=4000.0, por_trabalhador_mb=2000.0)
        with _gerente(
            monkeypatch, tmp_path / nome, motor=_motor_pool(pool), construir_cache=True,
            limite_construcao=3, teto_memoria_mb=6500.0, custo_trabalhador_mb=2000.0, medir_rss_mb=fn,
        ) as (g, arq, o):
            _aquecer_construindo(g, arq)
            lim = g.limite_trabalhadores()
            assert type(lim) is int and lim == 1, f"{nome}: limite={lim!r}"
            for i in range(3):
                g.pedir("planta", None, f"V{i}")
            assert _girar(lambda: len(o.prontos) == 3) and o.falhas == []
            assert pool.pico == 1 and pool.pico_mb <= 6500.0


@pytest.mark.parametrize("caso", ["erro", "nan", "neg_inf", "negativo"])
def test_medir_rss_falha_transitoria_reserva_conservadora_respeita_teto(app, monkeypatch, tmp_path, caso):
    teto_mb, custo_mb, base_mb = 6500.0, 2000.0, 4000.0
    entrou_v1, portao_v1 = threading.Event(), threading.Event()
    pool = _PoolEspiao(atraso_s=0.0, base_mb=base_mb, por_trabalhador_mb=custo_mb)

    def medir():
        if not entrou_v1.is_set():
            if caso == "erro":
                raise RuntimeError("erro transitorio")
            return {"nan": float("nan"), "neg_inf": float("-inf"), "negativo": -100.0}[caso]
        return base_mb

    def motor(tipo, ifc, guid, opcoes, *, cancelar, progresso):
        def _rodar():
            if guid == "V1":
                entrou_v1.set()
                portao_v1.wait(5.0)
            else:
                time.sleep(0.03)
            return {"vista": guid}
        return pool.rodar_tarefa(_rodar)

    try:
        with _gerente(
            monkeypatch, tmp_path, motor=motor, construir_cache=True,
            limite_construcao=3, teto_memoria_mb=teto_mb, custo_trabalhador_mb=custo_mb, medir_rss_mb=medir,
        ) as (g, arq, o):
            _aquecer_construindo(g, arq)
            g.pedir("planta", None, "V1")
            assert entrou_v1.wait(5.0)
            lim_durante = g.limite_trabalhadores()
            assert type(lim_durante) is int and lim_durante == 1
            g.pedir("planta", None, "V2")
            time.sleep(0.08)
            assert pool.pico == 1, f"{caso}: admitiu 2o trabalhador com reserva invalida"
            portao_v1.set()
            assert _girar(lambda: len(o.prontos) == 2) and o.falhas == []
            assert pool.pico == 1 and pool.pico_mb <= teto_mb
    finally:
        portao_v1.set()


# --- ITEM 4: FilhoPersistente.construcao_ativa apos SAIDA_MEMORIA ociosa e corrida ---

def test_filho_construcao_ativa_false_apos_saida_memoria_ociosa(tmp_path, monkeypatch):
    monkeypatch.setenv("OBIM_T26_OR2_DIR", str(tmp_path))
    arq = tmp_path / "Casa.ifc"
    arq.write_text("ifc", encoding="utf-8")
    f = FilhoPersistente(arq, ocioso_s=600.0, alvo=_alvo_saida_memoria_ociosa)
    try:
        res = f.construir(str(tmp_path / "geo"), limite_s=30)
        assert res["aceito"] is True and f.construcao_ativa is True and f.pid is not None
        (tmp_path / "sair_memoria").write_text("86", encoding="utf-8")
        fim = time.monotonic() + 5.0
        while f.pid is not None and time.monotonic() < fim:
            time.sleep(0.01)
        assert f.pid is None and f.construcao_ativa is False
    finally:
        f.fechar()


@pytest.mark.parametrize("acao", ["fechar", "invalidar", "salvar"])
def test_filho_acao_durante_construir_nao_reativa_construcao_ativa(tmp_path, monkeypatch, acao):
    monkeypatch.setenv("OBIM_T26_OR2_DIR", str(tmp_path))
    arq = tmp_path / "Casa.ifc"
    arq.write_text("ifc", encoding="utf-8")
    f = FilhoPersistente(arq, ocioso_s=600.0, alvo=_alvo_construir_pausado)
    t_acao, orig_executar = [], f.executar

    def _executar_espiado(*a, **kw):
        res = orig_executar(*a, **kw)
        if t_acao:
            t_acao[0].join(timeout=0.5)
        return res

    f.executar = _executar_espiado
    try:
        t_c = threading.Thread(target=lambda: f.construir(str(tmp_path / "geo"), limite_s=30), daemon=True)
        t_c.start()
        fim = time.monotonic() + 5.0
        while not (tmp_path / "no_construir").exists() and time.monotonic() < fim:
            time.sleep(0.005)
        assert (tmp_path / "no_construir").exists()
        ta = threading.Thread(target=getattr(f, acao), daemon=True)
        t_acao.append(ta)
        ta.start()
        time.sleep(0.03)
        (tmp_path / "liberar_construir").write_text("1", encoding="utf-8")
        t_c.join(timeout=5.0)
        ta.join(timeout=5.0)
        assert not t_c.is_alive() and not ta.is_alive() and f.pid is None and f.construcao_ativa is False
    finally:
        (tmp_path / "liberar_construir").write_text("1", encoding="utf-8")
        f.fechar()


# --- ITEM 5: FIFO estrito e medicao de RSS sem segurar trava ---

def test_fila_fifo_ordem_de_chegada_sem_furar_fila(app, monkeypatch, tmp_path):
    entrou_v0, portao_v0, ordem = threading.Event(), threading.Event(), []

    def motor(tipo, ifc, guid, opcoes, *, cancelar, progresso):
        ordem.append(guid)
        if guid == "V0":
            entrou_v0.set()
            portao_v0.wait(5.0)
        else:
            time.sleep(0.02)
        return {"vista": guid}

    try:
        with _gerente(
            monkeypatch, tmp_path, motor=motor, construir_cache=True,
            limite_construcao=1, medir_rss_mb=lambda: 1500.0,
        ) as (g, arq, o):
            _aquecer_construindo(g, arq)
            g.pedir("planta", None, "V0")
            assert entrou_v0.wait(5.0)
            for guid in ("V1", "V2", "V3"):
                g.pedir("planta", None, guid)
                time.sleep(0.04)  # apos 120 ms, V1 ja passou do timeout de 100 ms
            g.pedir("planta", None, "V4")
            portao_v0.set()
            assert _girar(lambda: len(o.prontos) == 5) and o.falhas == []
            assert ordem == ["V0", "V1", "V2", "V3", "V4"], f"furou fila: {ordem}"
    finally:
        portao_v0.set()


def test_medicao_rss_nao_segura_trava_pedir_cancelar_fechar(app, monkeypatch, tmp_path):
    em_medir, portao_medir, pausar = threading.Event(), threading.Event(), threading.Event()
    livres_na_medicao: list[bool] = []
    ref_g: list[GerenteDesenho] = []

    def medir():
        adquiriu = ref_g[0]._trava.acquire(blocking=False)
        if adquiriu:
            ref_g[0]._trava.release()
        livres_na_medicao.append(adquiriu)
        if pausar.is_set():
            em_medir.set()
            portao_medir.wait(0.6)
        return 5000.0

    with _gerente(
        monkeypatch, tmp_path, motor=lambda *a, **k: {"ok": True}, construir_cache=True,
        limite_construcao=2, teto_memoria_mb=6500.0, custo_trabalhador_mb=2000.0, medir_rss_mb=medir,
    ) as (g, arq, o):
        ref_g.append(g)
        _aquecer_construindo(g, arq)
        assert g.limite_trabalhadores() == 1

        pausar.set()
        try:
            g.pedir("planta", None, "V1")
            assert em_medir.wait(2.0)
            t0 = time.monotonic()
            k_rap = g.pedir("planta", None, "V_LIVRE")
            g.cancelar(k_rap)
            dt_pedir_cancelar = time.monotonic() - t0
        finally:
            pausar.clear()
            portao_medir.set()
        assert _girar(lambda: len(o.prontos) == 1) and o.falhas == []

        em_medir.clear()
        portao_medir.clear()
        pausar.set()
        t_fechar = None
        try:
            g.pedir("planta", None, "V_FECHAR")
            assert em_medir.wait(2.0)
            ger_antes = g._geracao
            t_fechar = threading.Thread(target=g.fechar, daemon=True)
            t_fechar.start()
            fim = time.monotonic() + 0.25
            while g._geracao == ger_antes and time.monotonic() < fim:
                time.sleep(0.005)
            fechar_passou_trava = g._geracao > ger_antes
        finally:
            pausar.clear()
            portao_medir.set()
            if t_fechar is not None:
                t_fechar.join(timeout=3.0)

        assert livres_na_medicao and all(livres_na_medicao), f"trava presa na medicao: {livres_na_medicao}"
        assert dt_pedir_cancelar < 0.25, f"pedir/cancelar bloqueou {dt_pedir_cancelar:.3f}s"
        assert fechar_passou_trava and t_fechar is not None and not t_fechar.is_alive()
