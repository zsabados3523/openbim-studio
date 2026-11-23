# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oraculo F0-S06-T26 (T3): limitar processos de trabalho do desenho durante construcao do cache.
Nao editar este arquivo na implementacao. Sem IFC real: usa pool/memoria espiao e filho fake.

CONTRATO DA INTERFACE (decisoes do oraculo para o implementador)
1. `FilhoPersistente.construcao_ativa -> bool` (property publica em `openbim_app.desenho.filho`):
   - `True` enquanto construcao ativa (`aceito=True`, `pendentes > 0`, `parado is None`);
     `False` antes de `construir()`, apos `fechar()`, apos `SAIDA_MEMORIA`, ou quando termina/para.
   - `executar({"op": "estado_construcao", ...})` atualiza esse estado pela resposta.
2. `GerenteDesenho.__init__(cache=None, *, motor=None, chave_estado=None, filho_persistente=True,
   construir_cache=False, limite_construcao=None, teto_memoria_mb=6500.0, custo_trabalhador_mb=2000.0,
   medir_rss_mb=None, parent=None)`:
   - `limite_construcao`: `None` (padrao: 1, ate 2 se memoria livre permitir) ou inteiro (bool -> TypeError/ValueError; <1 -> clamp 1).
   - `teto_memoria_mb` (6500.0) e `custo_trabalhador_mb` (2000.0): teto total e custo estimado por trabalhador (MB).
   - `medir_rss_mb`: callable opcional `() -> float` (RSS do conjunto em MB); `None` mede RSS real (erro -> fallback 1).
3. `GerenteDesenho.limite_trabalhadores() -> int | None`:
   - Sem filho do gerente com `construcao_ativa` verdadeira -> `None` (padrao atual).
   - Com construcao ativa -> `N = max(1, min(teto_n, vagas_em_uso + adicionais))`, onde:
     `teto_n = max(1, int(limite_construcao))` se configurado senao `2`;
     `rss_efetivo = max(rss_medido, rss_reservado)` (evita corrida antes da alocacao de RAM);
     `adicionais = int(max(0.0, teto_memoria_mb - rss_efetivo) // custo_trabalhador_mb)`.
4. Admissao e repasse (`GerenteDesenho._rodar`):
   - Construcao inativa: sem espera de limite e sem injetar `threads` em `opcoes`.
   - Construcao ativa: adquire vaga(s) antes de `self._motor(...)` e libera em `finally` notificando a fila.
     Admite se `vagas_em_uso == 0` (garante N>=1) ou `vagas_em_uso < limite_trabalhadores()`.
   - Repassa `opcoes["threads"] = cota` (`1 <= cota <= N`, `<= opcoes["threads"]` se ja informado),
     com soma das cotas simultaneas `<= N`. `chave_estado` recebe `opcoes` originais (sem `threads` imposto).
   - Cancelar (`cancelar`, novo pedido da mesma vista ou `fechar`) acorda quem espera imediatamente sem chamar o motor e sem travar;
     fim da construcao tambem libera quem espera.
"""
from __future__ import annotations

import contextlib, inspect, json, os, threading, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtCore")
from PySide6.QtCore import QCoreApplication  # noqa: E402

from openbim_app.desenho import gerente as G  # noqa: E402
from openbim_app.desenho.auxiliar import DesenhoCancelado  # noqa: E402
from openbim_app.desenho.filho import FilhoPersistente  # noqa: E402
from openbim_app.desenho.gerente import GerenteDesenho  # noqa: E402

@pytest.fixture(scope="module")
def app():
    return QCoreApplication.instance() or QCoreApplication([])

def _girar(cond, timeout_s: float = 10.0) -> bool:
    fim = time.monotonic() + timeout_s
    while time.monotonic() < fim:
        QCoreApplication.processEvents()
        if cond():
            return True
        time.sleep(0.005)
    QCoreApplication.processEvents()
    return bool(cond())

def _esperar_fundo(g: GerenteDesenho, timeout_s: float = 5.0) -> None:
    fim = time.monotonic() + timeout_s
    while g._threads and time.monotonic() < fim:
        time.sleep(0.01)
    assert not g._threads

class _Ouvinte:
    def __init__(self, g: GerenteDesenho):
        self.prontos, self.falhas = [], []
        g.pronto.connect(lambda c, d: self.prontos.append((c, d)))
        g.falhou.connect(lambda c, m: self.falhas.append((c, m)))


class _FilhoFake:
    instancias: list[_FilhoFake] = []
    pendentes_inicial: int = 5

    def __init__(self, arquivo, **kw):
        self.arquivo, self.construcao_ativa = Path(arquivo), False
        _FilhoFake.instancias.append(self)

    aquecer = lambda self, cancelar=None, limite_s=0: {"aberto": True}
    podar = lambda self: None

    def construir(self, pasta_cache, **kw):
        self.construcao_ativa = _FilhoFake.pendentes_inicial > 0
        return {"aceito": True, "pendentes": _FilhoFake.pendentes_inicial}

    def _parar(self):
        self.construcao_ativa = False

    salvar = invalidar = fechar = _parar


class _PoolEspiao:
    """Fake de pool de processos de trabalho do desenho com espiao de concorrencia e RSS simulado."""

    def __init__(self, *, atraso_s: float = 0.05, base_mb: float = 0.0, por_trabalhador_mb: float = 0.0):
        self._trava, self._atraso_s = threading.Lock(), atraso_s
        self.base_mb, self.por_trabalhador_mb = float(base_mb), float(por_trabalhador_mb)
        self.ativos = self.pico = 0
        self.pico_mb = self.base_mb

    def rss_atual(self) -> float:
        with self._trava:
            return self.base_mb + self.ativos * self.por_trabalhador_mb

    def rodar_tarefa(self, fn):
        with self._trava:
            self.ativos += 1
            self.pico = max(self.pico, self.ativos)
            self.pico_mb = max(self.pico_mb, self.base_mb + self.ativos * self.por_trabalhador_mb)
        try:
            time.sleep(self._atraso_s)
            return fn()
        finally:
            with self._trava:
                self.ativos -= 1

    def executar_faixas(self, itens: list, workers: int) -> list:
        workers = max(1, int(workers))
        fatias = [itens[i::workers] for i in range(min(workers, max(1, len(itens))))]
        if workers == 1 or len(fatias) <= 1:
            return self.rodar_tarefa(lambda: [f"el:{x}" for x in itens])
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futs = [ex.submit(self.rodar_tarefa, lambda fl=fl: [f"el:{x}" for x in fl]) for fl in fatias]
            return [item for fut in futs for item in fut.result()]


def _motor_pool(pool: _PoolEspiao, *, padrao_w: int = 4, opcoes_vistas: list | None = None, itens_por_vista: dict | None = None):
    def motor(tipo, ifc, guid, opcoes, *, cancelar, progresso):
        if opcoes_vistas is not None:
            opcoes_vistas.append(dict(opcoes))
        itens = itens_por_vista[guid] if itens_por_vista is not None else list(range(8))
        saida = sorted(pool.executar_faixas(itens, workers=opcoes.get("threads") or padrao_w))
        return {"vista": guid, "elementos": saida, "n_paths": len(saida), "svg": "<svg>" + "".join(saida) + "</svg>"}
    return motor


@contextlib.contextmanager
def _gerente(monkeypatch, tmp_path, *, motor, **kw):
    _FilhoFake.instancias, _FilhoFake.pendentes_inicial = [], 5
    monkeypatch.setattr(G, "FilhoPersistente", _FilhoFake)
    tmp_path.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("OBIM_CACHE_DIR", str(tmp_path / "cache"))
    arq = tmp_path / "modelo.ifc"
    arq.write_text("ifc", encoding="utf-8")
    g = GerenteDesenho(motor=motor, **kw)
    try:
        yield g, arq, _Ouvinte(g)
    finally:
        g.fechar()


def _aquecer_construindo(g: GerenteDesenho, arq: Path) -> _FilhoFake:
    g.aquecer(str(arq), revisao=1, revisao_salva=1)
    _esperar_fundo(g)
    assert _FilhoFake.instancias and _FilhoFake.instancias[-1].construcao_ativa is True
    return _FilhoFake.instancias[-1]


def _alvo_t26(tx, rx):
    """Processo filho minimo para validar `FilhoPersistente.construcao_ativa` sem IFC real."""
    pasta = Path(os.environ["OBIM_T26_DIR"])
    tx.send_bytes(json.dumps({"tipo": "pronto", "pid": os.getpid(), "protocolo": 1}).encode())
    while True:
        try:
            p = json.loads(rx.recv_bytes())
        except EOFError:
            return
        op, n = p.get("op"), p["numero"]
        if op == "encerrar":
            return
        est = json.loads((pasta / "estado.json").read_text())
        pend, parado = int(est.get("pendentes", 0)), est.get("parado")
        dados = (
            {"aceito": True, "pendentes": pend} if op == "construir" else
            {"ativo": pend > 0 and parado is None, "pendentes": pend, "parado": parado, "erro": None} if op == "estado_construcao" else
            {"ok": True}
        )
        tx.send_bytes(json.dumps({"tipo": "resposta", "numero": n, "dados": dados}).encode())


def test_interface_gerente_e_filho(tmp_path):
    p = inspect.signature(GerenteDesenho.__init__).parameters
    assert p["construir_cache"].default is False and p["limite_construcao"].default is None
    assert p["teto_memoria_mb"].default == 6500.0 and p["custo_trabalhador_mb"].default == 2000.0
    assert p["medir_rss_mb"].default is None and callable(getattr(GerenteDesenho, "limite_trabalhadores", None))
    arq = tmp_path / "vazio.ifc"
    arq.write_text("ifc", encoding="utf-8")
    f = FilhoPersistente(arq)
    try:
        assert f.construcao_ativa is False
    finally:
        f.fechar()
    assert f.construcao_ativa is False


@pytest.mark.parametrize("limite", [1, 2])
def test_construcao_ativa_limita_trabalhadores_a_n(app, monkeypatch, tmp_path, limite):
    pool, opcoes_vistas = _PoolEspiao(atraso_s=0.06), []
    with _gerente(
        monkeypatch, tmp_path, motor=_motor_pool(pool, opcoes_vistas=opcoes_vistas), construir_cache=True,
        limite_construcao=limite, teto_memoria_mb=6500.0, custo_trabalhador_mb=1500.0, medir_rss_mb=lambda: 1500.0,
    ) as (g, arq, o):
        _aquecer_construindo(g, arq)
        assert g.limite_trabalhadores() == limite
        for i in range(4):
            g.pedir("planta", None, f"V{i}", **({"threads": 6} if i == 0 else {}))
        assert _girar(lambda: len(o.prontos) == 4) and o.falhas == []
        assert 1 <= pool.pico <= limite and pool.pico == limite and len(opcoes_vistas) == 4
        assert all(isinstance(op.get("threads"), int) and 1 <= op["threads"] <= limite for op in opcoes_vistas)


def test_construcao_ativa_limita_pedido_unico_com_faixas(app, monkeypatch, tmp_path):
    pool, recebido = _PoolEspiao(atraso_s=0.04), []
    with _gerente(
        monkeypatch, tmp_path, motor=_motor_pool(pool, padrao_w=6, opcoes_vistas=recebido),
        construir_cache=True, limite_construcao=1, medir_rss_mb=lambda: 2000.0,
    ) as (g, arq, o):
        _aquecer_construindo(g, arq)
        assert g.limite_trabalhadores() == 1
        g.pedir("planta", None, "V1")
        assert _girar(lambda: len(o.prontos) == 1) and o.falhas == []
        assert pool.pico == 1 and recebido[0].get("threads") == 1


def test_construcao_parada_ou_terminada_volta_ao_padrao(app, monkeypatch, tmp_path):
    pool, opcoes_vistas = _PoolEspiao(atraso_s=0.06), []
    with _gerente(
        monkeypatch, tmp_path, motor=_motor_pool(pool, opcoes_vistas=opcoes_vistas),
        construir_cache=True, limite_construcao=1, medir_rss_mb=lambda: 1500.0,
    ) as (g, arq, o):
        assert g.limite_trabalhadores() is None
        filho = _aquecer_construindo(g, arq)
        assert g.limite_trabalhadores() == 1
        g.pedir("planta", None, "VA")
        assert _girar(lambda: len(o.prontos) == 1) and pool.pico == 1 and opcoes_vistas[-1].get("threads") == 1
        filho.construcao_ativa = False
        assert g.limite_trabalhadores() is None
        opcoes_vistas.clear()
        pool.pico = 0
        for i in range(3):
            g.pedir("corte", None, f"VB{i}")
        assert _girar(lambda: len(o.prontos) == 4) and o.falhas == [] and pool.pico >= 2
        assert all("threads" not in op for op in opcoes_vistas)


@pytest.mark.parametrize("fim", [(0, None), (3, "erro")])
def test_filho_construcao_ativa_acompanha_estado_construcao(tmp_path, monkeypatch, fim):
    monkeypatch.setenv("OBIM_T26_DIR", str(tmp_path))
    arq = tmp_path / "Casa.ifc"
    arq.write_text("ifc", encoding="utf-8")
    (tmp_path / "estado.json").write_text(json.dumps({"pendentes": 4, "parado": None}))
    f = FilhoPersistente(arq, ocioso_s=600.0, alvo=_alvo_t26)
    try:
        assert f.construcao_ativa is False
        assert f.construir(str(tmp_path / "geo"), limite_s=60)["aceito"] is True and f.construcao_ativa is True
        (tmp_path / "estado.json").write_text(json.dumps({"pendentes": fim[0], "parado": fim[1]}))
        est = f.executar({"op": "estado_construcao", "arquivo": f.arquivo}, limite_s=60)
        assert est["pendentes"] == fim[0] and est["parado"] == fim[1] and f.construcao_ativa is False
    finally:
        f.fechar()
    assert f.construcao_ativa is False


def test_nenhum_pedido_perdido_e_mesmos_resultados_com_e_sem_limite(app, monkeypatch, tmp_path):
    elementos_por_vista = {f"V{i}": [f"{i}-{j}" for j in range(12)] for i in range(5)}
    chaves_opcoes: list[dict] = []

    def chave_estado(tipo, ifc, guid, opcoes):
        chaves_opcoes.append(dict(opcoes))
        return f"{tipo}|{guid}|{sorted(opcoes.items())}"

    def rodar_rodada(construir: bool):
        pool = _PoolEspiao(atraso_s=0.03)
        with _gerente(
            monkeypatch, tmp_path / ("lim" if construir else "pad"),
            motor=_motor_pool(pool, itens_por_vista=elementos_por_vista), chave_estado=chave_estado,
            construir_cache=construir, limite_construcao=1, medir_rss_mb=lambda: 1500.0,
        ) as (g, arq, o):
            if construir:
                _aquecer_construindo(g, arq)
                assert g.limite_trabalhadores() == 1
            else:
                assert g.limite_trabalhadores() is None
            for guid in elementos_por_vista:
                g.pedir("planta", None, guid)
            assert _girar(lambda: len(o.prontos) == len(elementos_por_vista)) and o.falhas == []
            return {d["vista"]: d for _, d in o.prontos}, pool.pico

    res_padrao, pico_padrao = rodar_rodada(False)
    chaves_opcoes.clear()
    res_lim1, pico_lim1 = rodar_rodada(True)
    assert pico_padrao > 1 and pico_lim1 == 1 and res_lim1 == res_padrao
    assert set(res_lim1) == set(elementos_por_vista) and all(len(d["elementos"]) == 12 for d in res_lim1.values())
    assert all("threads" not in op for op in chaves_opcoes)


def test_cancelar_pedido_durante_espera_nao_trava(app, monkeypatch, tmp_path):
    entrou_v1, portao_v1, chamadas = threading.Event(), threading.Event(), []

    def motor(tipo, ifc, guid, opcoes, *, cancelar, progresso):
        chamadas.append(guid)
        if guid == "V1":
            entrou_v1.set()
            portao_v1.wait(5.0)
        if cancelar.is_set():
            raise DesenhoCancelado("cancelado")
        return {"vista": guid}

    try:
        with _gerente(monkeypatch, tmp_path, motor=motor, construir_cache=True, limite_construcao=1, medir_rss_mb=lambda: 1500.0) as (g, arq, o):
            _aquecer_construindo(g, arq)
            k1 = g.pedir("planta", None, "V1")
            assert entrou_v1.wait(5.0)
            k2, k3 = g.pedir("planta", None, "V2"), g.pedir("planta", None, "V3")
            t_v2 = g._ativos[k2].thread
            time.sleep(0.05)
            t0 = time.monotonic()
            g.cancelar(k2)
            assert time.monotonic() - t0 < 0.5
            t_v2.join(timeout=2.0)
            assert not t_v2.is_alive(), "cancelar durante espera nao liberou a thread de V2"
            portao_v1.set()
            assert _girar(lambda: len(o.prontos) == 2)
            assert {c for c, _ in o.prontos} == {k1, k3} and o.falhas == [] and "V2" not in chamadas
    finally:
        portao_v1.set()


def test_fechar_com_pedidos_esperando_nao_trava(app, monkeypatch, tmp_path):
    entrou, chamadas = threading.Event(), []

    def motor(tipo, ifc, guid, opcoes, *, cancelar, progresso):
        chamadas.append(guid)
        entrou.set()
        cancelar.wait(5.0)
        raise DesenhoCancelado("cancelado")

    with _gerente(monkeypatch, tmp_path, motor=motor, construir_cache=True, limite_construcao=1, medir_rss_mb=lambda: 1500.0) as (g, arq, _o):
        _aquecer_construindo(g, arq)
        g.pedir("planta", None, "V1")
        assert entrou.wait(5.0)
        for i in range(2, 5):
            g.pedir("planta", None, f"V{i}")
        time.sleep(0.05)
        t0 = time.monotonic()
        g.fechar()
        assert time.monotonic() - t0 < 2.0 and not g._threads and chamadas == ["V1"]


def test_limite_configuravel_e_n_sempre_pelo_menos_um(app, monkeypatch, tmp_path):
    casos = [
        ({"limite_construcao": 1, "medir_rss_mb": lambda: 500.0}, 1),
        ({"limite_construcao": 2, "medir_rss_mb": lambda: 500.0}, 2),
        ({"limite_construcao": 3, "teto_memoria_mb": 9000.0, "custo_trabalhador_mb": 1500.0, "medir_rss_mb": lambda: 500.0}, 3),
        ({"limite_construcao": None, "teto_memoria_mb": 6500.0, "custo_trabalhador_mb": 2000.0, "medir_rss_mb": lambda: 2000.0}, 2),
        ({"limite_construcao": None, "teto_memoria_mb": 6500.0, "custo_trabalhador_mb": 2000.0, "medir_rss_mb": lambda: 3500.0}, 1),
        ({"limite_construcao": None, "teto_memoria_mb": 6500.0, "custo_trabalhador_mb": 500.0, "medir_rss_mb": lambda: 200.0}, 2),
        ({"limite_construcao": 0, "medir_rss_mb": lambda: 500.0}, 1),
        ({"limite_construcao": -4, "medir_rss_mb": lambda: 500.0}, 1),
        ({"limite_construcao": 2, "teto_memoria_mb": 6500.0, "custo_trabalhador_mb": 2000.0, "medir_rss_mb": lambda: 7000.0}, 1),
    ]
    for idx, (kw, esperado) in enumerate(casos):
        with _gerente(monkeypatch, tmp_path / f"c{idx}", motor=lambda *a, **k: {"ok": True}, construir_cache=True, **kw) as (g, arq, o):
            _aquecer_construindo(g, arq)
            assert g.limite_trabalhadores() == esperado, f"caso {idx}: {kw}"
            g.pedir("planta", None, "V1")
            assert _girar(lambda: len(o.prontos) == 1) and o.falhas == []
    for invalido in (True, False):
        with pytest.raises((TypeError, ValueError)):
            GerenteDesenho(motor=lambda *a, **k: {}, limite_construcao=invalido)


@pytest.mark.parametrize("base_mb,pico_esperado", [(2600.0, 2), (4200.0, 1)])
def test_admissao_por_memoria_nunca_passa_teto(app, monkeypatch, tmp_path, base_mb, pico_esperado):
    teto_mb, custo_mb = 6500.0, 1800.0
    pool = _PoolEspiao(atraso_s=0.06, base_mb=base_mb, por_trabalhador_mb=custo_mb)
    with _gerente(
        monkeypatch, tmp_path, motor=_motor_pool(pool), construir_cache=True,
        limite_construcao=3, teto_memoria_mb=teto_mb, custo_trabalhador_mb=custo_mb, medir_rss_mb=pool.rss_atual,
    ) as (g, arq, o):
        _aquecer_construindo(g, arq)
        for i in range(5):
            g.pedir("planta", None, f"V{i}")
        assert _girar(lambda: len(o.prontos) == 5) and o.falhas == []
        assert pool.pico_mb <= teto_mb, f"RSS simulado {pool.pico_mb} MB passou teto {teto_mb} MB"
        assert pool.pico == pico_esperado
