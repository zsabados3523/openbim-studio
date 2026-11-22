# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oraculo F0-S06-T23e (cartao e especificacao T23 §3, §4): pai do filho persistente. Nao editar nesta tarefa.
Filho de brinquedo `_alvo` imita o protocolo e anota cada mensagem em log.jsonl; relogio do pai falso. `estado.json` = {"pendentes", "parado"};
`sair.json` = {"n", "codigo"}: os proximos n pedidos `desenho` fazem o filho sair com `os._exit(codigo)` sem responder."""
from __future__ import annotations

import inspect
import json
import os
import threading
import time
from pathlib import Path

import pytest

from openbim_app.desenho import auxiliar as A
from openbim_app.desenho import cache as C
from openbim_app.desenho import filho as F
from openbim_app.desenho.filho import FilhoIndisponivel, FilhoPersistente

OCIOSO = 100.0

def _alvo(tx, rx):
    pasta = Path(os.environ["OBIM_T23E_DIR"])

    def env(o):
        tx.send_bytes(json.dumps(o).encode())

    def ler(nome):
        try:
            return json.loads((pasta / nome).read_text())
        except (OSError, ValueError):
            return {}

    env({"tipo": "pronto", "pid": os.getpid(), "protocolo": 1})
    while True:
        try:
            p = json.loads(rx.recv_bytes())
        except EOFError:
            return
        with open(pasta / "log.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps({"pid": os.getpid(), "op": p.get("op"), "msg": p}) + "\n")
        op, n = p.get("op"), p["numero"]
        if op == "encerrar":
            return
        est = ler("estado.json")
        pend = int(est.get("pendentes", 0))
        if op == "abrir":
            dados = {"ok": True, "aberto": True, "pid": os.getpid()}
        elif op == "construir":  # envelope real (persistente.py, spec §3): sem "ok"
            modo = est.get("construir")
            dados = {"ok": False, "erro": {"tipo": "X", "mensagem": "m", "rastro": ""}} if modo == "erro" else (
                {"aceito": False, "motivo": "erro"} if modo == "recusa" else (
                    {"foo": 1} if modo == "vazio" else {"aceito": True, "pendentes": pend}))
        elif op == "estado_construcao":
            dados = {"ativo": pend > 0, "pendentes": pend, "feitos": 0, "tesseladas": 0, "reaproveitadas": 0,
                     "falhas": 0, "lotes": 0, "lote_max_s": 0.0, "rss_mb": 0.0, "parado": est.get("parado"), "erro": None}
        else:
            sair = ler("sair.json")
            if int(sair.get("n", 0)) > 0:
                (pasta / "sair.json").write_text(json.dumps({**sair, "n": int(sair["n"]) - 1}))
                os._exit(int(sair["codigo"]))
            time.sleep(p.get("dormir_s", 0))
            dados = {"ok": True, "pid": os.getpid()}
        env({"tipo": "resposta", "numero": n, "dados": dados})
        if p.get("sair_depois"):
            os._exit(86)

class Amb:
    def __init__(self, pasta: Path):
        self.pasta, self.t, self.filhos = pasta, 1000.0, []
        self.arq = pasta / "Casa.ifc"
        self.arq.write_text("ifc")
        self.estado(5)

    def estado(self, pend, parado=None, construir=None):
        (self.pasta / "estado.json").write_text(json.dumps({"pendentes": pend, "parado": parado, "construir": construir}))

    def sair(self, n, codigo=86):
        (self.pasta / "sair.json").write_text(json.dumps({"n": n, "codigo": codigo}))

    def filho(self):
        f = FilhoPersistente(self.arq, ocioso_s=OCIOSO, relogio=lambda: self.t, alvo=_alvo)
        self.filhos.append(f)
        return f

    def log(self):
        try:
            linhas = (self.pasta / "log.jsonl").read_text().splitlines()
        except OSError:
            return []
        return [json.loads(x) for x in linhas if x.strip()]

    def ops(self, pid):
        return [e["op"] for e in self.log() if e["pid"] == pid]

    def msgs(self, pid, op):
        return [e["msg"] for e in self.log() if e["pid"] == pid and e["op"] == op]

    def pids(self):
        return list(dict.fromkeys(e["pid"] for e in self.log()))

    def esperar(self, cond, s=30.0):
        fim = time.monotonic() + s
        while time.monotonic() < fim:
            if cond():
                return True
            time.sleep(0.02)
        return False

    def avancar(self, x):
        self.t += x * OCIOSO

@pytest.fixture
def amb(tmp_path, monkeypatch):
    monkeypatch.setenv("OBIM_T23E_DIR", str(tmp_path))
    a = Amb(tmp_path)
    yield a
    for f in a.filhos:
        f.fechar()

def ped(**kw):
    return {"op": "desenho", **kw}

def ex(f, **kw):
    return f.executar(ped(**kw), limite_s=120)

class EspiaTx:
    """Embrulha o cano pai->filho: anota o `op` de cada envio; o resto delega."""

    def __init__(self, tx):
        self._tx, self.ops = tx, []

    def send_bytes(self, b, *a, **k):
        self.ops.append(json.loads(b)["op"])
        return self._tx.send_bytes(b, *a, **k)

    def __getattr__(self, nome):
        return getattr(self._tx, nome)

def test_interface():
    assert F.SAIDA_MEMORIA == 86
    p = inspect.signature(FilhoPersistente.construir).parameters
    assert p["lote_max"].default == 64 and p["limite_mb"].default == 6000.0
    assert p["threads"].default is None and p["cancelar"].default is None and p["limite_s"].default == F.LIMITE_PADRAO_S
    from openbim_app.desenho.gerente import GerenteDesenho
    assert inspect.signature(GerenteDesenho.__init__).parameters["construir_cache"].default is False

def test_construir_envia_parametros(amb, tmp_path):
    f = amb.filho()
    r = f.construir(str(tmp_path / "geo"), lote_max=7, limite_mb=123.5, threads=2, limite_s=120)
    assert r["aceito"] is True and r["pendentes"] == 5
    pid = amb.pids()[0]
    m = amb.msgs(pid, "construir")[-1]
    assert (m["arquivo"], m["pasta_cache"], m["lote_max"], m["limite_mb"], m["threads"]) == (
        f.arquivo, str(tmp_path / "geo"), 7, 123.5, 2) and isinstance(m["numero"], int)
    f.construir(str(tmp_path / "geo"), limite_s=120)
    m = amb.msgs(pid, "construir")[-1]
    assert (m["lote_max"], m["limite_mb"], m["threads"]) == (64, 6000.0, None)

def test_construcao_ativa_nao_morre_e_pergunta_so_em_executar(amb):
    f = amb.filho()
    f.construir("g", limite_s=120)
    pid = f.pid
    tx = f._tx = EspiaTx(f._tx)
    amb.avancar(10)
    f.podar()  # preguicoso, sem envio, sem matar
    assert f.pid == pid and tx.ops == []
    assert ex(f)["pid"] == pid, "construcao ativa: ociosidade nao mata"
    assert tx.ops == ["estado_construcao", "desenho"], "pergunta so no inicio de executar, antes do pedido"
    amb.avancar(0.5)  # relogio zerado e nao vencido: nenhuma pergunta nova
    assert ex(f)["pid"] == pid and tx.ops == ["estado_construcao", "desenho", "desenho"]
    amb.avancar(3)  # vencido de novo: pergunta de novo, ainda ha fila
    f.podar()
    assert f.pid == pid and ex(f)["pid"] == pid and tx.ops[-2:] == ["estado_construcao", "desenho"]

@pytest.mark.parametrize("fim", [(0, None), (4, "erro"), (4, "banco_ocupado")])
def test_fila_vazia_ou_parada_volta_a_morrer_por_ocioso(amb, fim):
    f = amb.filho()
    f.construir("g", limite_s=120)
    pid = f.pid
    amb.estado(*fim)
    amb.avancar(1.5)
    assert ex(f)["pid"] == pid and "estado_construcao" in amb.ops(pid), "pergunta zera o relogio, filho vive"
    amb.avancar(2)
    assert ex(f)["pid"] != pid, "sem construcao a ociosidade volta a matar (contagem comeca na pergunta)"

def test_fila_vazia_podar_mata(amb):
    f = amb.filho()
    f.construir("g", limite_s=120)
    amb.estado(0)
    amb.avancar(2)
    ex(f)  # pergunta: 0 pendentes desmarca
    pid = f.pid
    assert pid is not None
    amb.avancar(2)
    f.podar()
    assert f.pid is None

@pytest.mark.parametrize("modo", ["erro", "recusa", "vazio"])
def test_reenvio_com_falha_nao_derruba_o_pedido(amb, modo):
    f = amb.filho()
    f.construir("g", limite_s=120)
    amb.estado(5, construir=modo)
    f.salvar()
    r = ex(f)  # o reenvio de construir falha: pedido do usuario segue, construcao desmarcada
    pid = r["pid"]
    assert r["ok"] is True and amb.ops(pid) == ["construir", "desenho"] and len(amb.pids()) == 2
    amb.avancar(2)
    f.podar()
    assert f.pid is None, "construcao desmarcada: ociosidade volta a valer"


def test_filho_novo_com_zero_pendentes_nao_fica_ativo(amb):
    f = amb.filho()
    f.construir("g", limite_s=120)
    amb.estado(0)
    f.salvar()
    pid = ex(f)["pid"]
    assert amb.ops(pid) == ["construir", "desenho"]
    amb.avancar(2)
    f.podar()
    assert f.pid is None


def test_construir_direto_com_assinatura_bloqueada(amb):
    f = amb.filho()
    f.construir("g", limite_s=120)
    amb.sair(1, 86)
    pid = ex(f)["pid"]
    tx = f._tx = EspiaTx(f._tx)
    assert f.construir("g2", limite_s=120) == {"aceito": False, "motivo": "memoria"}
    assert tx.ops == [] and amb.ops(pid) == ["desenho"]


def test_construir_sem_pendentes_nao_marca_ativa(amb):
    amb.estado(0)
    f = amb.filho()
    f.construir("g", limite_s=120)
    tx = f._tx = EspiaTx(f._tx)
    amb.avancar(2)
    f.podar()
    assert f.pid is None and not tx.ops

def test_saida_86_nao_conta_como_queda(amb):
    f = amb.filho()
    amb.sair(2, 86)
    r = ex(f)  # 2 saidas 86 seguidas, o terceiro filho atende
    assert r["ok"] is True and len(amb.pids()) == 3

@pytest.mark.parametrize("codigo", [3, 85, 87])
def test_outro_codigo_e_queda(amb, codigo):
    f = amb.filho()
    amb.sair(5, codigo)
    with pytest.raises(FilhoIndisponivel):
        ex(f)
    assert len(amb.pids()) == 2

def test_86_com_processo_morto_ocioso_nao_conta(amb):
    f = amb.filho()
    ex(f, sair_depois=True)  # responde e sai com 86
    assert amb.esperar(lambda: f.pid is None)
    amb.sair(1, 3)  # o filho seguinte cai (queda comum, conta 1): so 2 quedas somadas levantariam
    assert ex(f)["ok"] is True and len(amb.pids()) == 3

def test_86_bloqueia_construir_ate_assinatura_nova(amb):
    f = amb.filho()
    f.construir("g", limite_s=120)
    amb.sair(1, 86)
    pid2 = ex(f)["pid"]
    assert pid2 != amb.pids()[0] and amb.ops(pid2) == ["desenho"], "mesma assinatura: pedido segue sem construcao"
    amb.avancar(2)  # filho novo e ocioso (sem construcao): renasce, continua bloqueado
    pid3 = ex(f)["pid"]
    assert pid3 not in (pid2, amb.pids()[0]) and amb.ops(pid3) == ["desenho"]
    amb.arq.write_text("ifc salvo com tamanho novo")  # assinatura nova desbloqueia
    pid4 = ex(f)["pid"]
    assert pid4 != pid3 and amb.ops(pid4)[:2] == ["construir", "desenho"]
    assert amb.msgs(pid4, "construir")[0]["pasta_cache"] == "g"

def test_cancelar_mata_e_filho_novo_recebe_construir(amb):
    f = amb.filho()
    f.construir("g", lote_max=9, limite_mb=77.0, threads=3, limite_s=120)
    pid1 = f.pid
    ev, erro = threading.Event(), []

    def rodar():
        try:
            f.executar(ped(dormir_s=60), cancelar=ev, limite_s=120)
        except BaseException as e:
            erro.append(e)

    t = threading.Thread(target=rodar)
    t.start()
    assert amb.esperar(lambda: amb.ops(pid1).count("desenho") == 1)
    ev.set()
    t.join(30)
    assert not t.is_alive() and isinstance(erro[0], A.DesenhoCancelado) and f.pid is None
    pid2 = ex(f)["pid"]
    assert pid2 != pid1 and amb.ops(pid2)[:2] == ["construir", "desenho"]
    m = amb.msgs(pid2, "construir")[0]
    assert (m["pasta_cache"], m["lote_max"], m["limite_mb"], m["threads"], m["arquivo"]) == ("g", 9, 77.0, 3, f.arquivo)

@pytest.mark.parametrize("como", ["salvar", "invalidar", "disco"])
def test_salvar_invalidar_e_disco_matam_e_reenviam(amb, como):
    f = amb.filho()
    f.construir("g", limite_s=120)
    pid1 = f.pid
    if como == "disco":
        amb.arq.write_text("ifc mudado no disco")
    else:
        getattr(f, como)()
        assert f.pid is None
    pid2 = ex(f)["pid"]
    assert pid2 != pid1 and amb.ops(pid2)[:2] == ["construir", "desenho"]

def test_podar_nao_espera_trava_ocupada(amb):
    f = amb.filho()
    ex(f)
    pid = f.pid
    amb.avancar(5)
    with f._trava:
        t = threading.Thread(target=f.podar)
        t.start()
        t.join(10)
        assert not t.is_alive(), "podar esperou a trava"
    assert f.pid == pid, "trava ocupada: nao poda agora"
    f.podar()  # livre e ocioso: poda
    assert f.pid is None

def test_podar_volta_rapido_com_pedido_em_voo(amb):
    f = amb.filho()
    ex(f)
    pid = f.pid
    res = []
    t = threading.Thread(target=lambda: res.append(ex(f, dormir_s=2)))
    t.start()
    assert amb.esperar(lambda: amb.ops(pid).count("desenho") == 2)
    amb.avancar(5)
    t0 = time.monotonic()
    f.podar()
    dt = time.monotonic() - t0
    assert dt < 0.15, f"podar demorou {dt:.3f}s (regua 50 ms, folga 3x; pedido dura 2 s)"
    assert f.pid == pid
    t.join(30)
    assert res and res[0]["pid"] == pid

def test_pasta_geometria(tmp_path, monkeypatch):
    amb_dir = tmp_path / "cache"
    monkeypatch.setenv("OBIM_CACHE_DIR", str(amb_dir))
    assert C.pasta_geometria() == amb_dir / "geometria" != C.pasta_padrao()
    monkeypatch.delenv("OBIM_CACHE_DIR")
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    g, p = C.pasta_geometria(), C.pasta_padrao()
    assert g != p and g.name == "geometria" and g.parent == p.parent
    assert not amb_dir.exists() and not g.exists() and not (tmp_path / "xdg").exists() and not (tmp_path / "local").exists()

class _FalsoFilho:
    eventos: list = []
    falha_aquecer = False
    solta = None  # Event: aquecer espera nele
    chamou = threading.Event()
    arqs: list = []

    def __init__(self, arquivo, **kw):
        self.arquivo = arquivo

    def _rec(self, nome, *a):
        _FalsoFilho.eventos.append((nome, threading.current_thread(), a))

    def aquecer(self, cancelar=None, limite_s=0):
        self._rec("aquecer")
        _FalsoFilho.chamou.set()
        if _FalsoFilho.solta is not None:
            _FalsoFilho.solta.wait(30)
        if _FalsoFilho.falha_aquecer:
            raise FilhoIndisponivel("x")
        return {"aberto": True}

    def construir(self, pasta_cache, **kw):
        self._rec("construir", pasta_cache)
        _FalsoFilho.arqs.append(str(self.arquivo))
        return {"aceito": True, "pendentes": 0}

    salvar = invalidar = podar = fechar = lambda self: None

def _gerente(monkeypatch, tmp_path, **kw):
    from openbim_app.desenho import gerente as G
    _FalsoFilho.eventos, _FalsoFilho.falha_aquecer, _FalsoFilho.solta, _FalsoFilho.arqs = [], False, None, []
    _FalsoFilho.chamou = threading.Event()
    monkeypatch.setattr(G, "FilhoPersistente", _FalsoFilho)
    monkeypatch.setenv("OBIM_CACHE_DIR", str(tmp_path / "cache"))
    arq = tmp_path / "Casa.ifc"
    arq.write_text("ifc")
    return G.GerenteDesenho(motor=lambda *a, **k: {}, **kw), arq

def _fundo(g):
    fim = time.monotonic() + 30
    while g._threads and time.monotonic() < fim:
        time.sleep(0.01)
    assert not g._threads

def _nomes():
    return [e[0] for e in _FalsoFilho.eventos]

@pytest.mark.parametrize("kw", [{}, {"construir_cache": False}])
def test_gerente_padrao_nao_constroi(monkeypatch, tmp_path, kw):
    g, arq = _gerente(monkeypatch, tmp_path, **kw)
    g.aquecer(str(arq), revisao=1, revisao_salva=1)
    _fundo(g)
    assert _nomes() == ["aquecer"]
    g.fechar()

def test_gerente_constroi_na_thread_de_fundo_depois_de_aquecer(monkeypatch, tmp_path):
    g, arq = _gerente(monkeypatch, tmp_path, construir_cache=True)
    g.aquecer(str(arq), revisao=1, revisao_salva=1)
    _fundo(g)
    assert _nomes() == ["aquecer", "construir"]
    (_, t_aq, _), (_, t_co, a) = _FalsoFilho.eventos
    assert a == (str(C.pasta_geometria()),) and a[0] == str(tmp_path / "cache" / "geometria")
    assert t_co is t_aq and t_co is not threading.current_thread(), "construir so da thread de fundo"
    _FalsoFilho.eventos.clear()
    g.salvar(str(arq), revisao=2, revisao_salva=2)  # salvar reaquece e reconstrui, tambem em segundo plano
    _fundo(g)
    assert _nomes() == ["aquecer", "construir"] and _FalsoFilho.eventos[1][1] is not threading.current_thread()
    g.fechar()

def test_gerente_nao_constroi_se_aquecer_falha_ou_gate_fechado(monkeypatch, tmp_path):
    g, arq = _gerente(monkeypatch, tmp_path, construir_cache=True)
    _FalsoFilho.falha_aquecer = True
    g.aquecer(str(arq), revisao=1, revisao_salva=1)
    _fundo(g)
    assert _nomes() == ["aquecer"]
    _FalsoFilho.eventos.clear()
    g.aquecer(str(arq), revisao=2, revisao_salva=1)  # documento sujo: nada
    _fundo(g)
    assert _FalsoFilho.eventos == []
    g.fechar()

def test_gerente_invalidar_no_meio_do_aquecer_nao_constroi_no_filho_velho(monkeypatch, tmp_path):
    g, arq = _gerente(monkeypatch, tmp_path, construir_cache=True)
    _FalsoFilho.solta = threading.Event()
    g.aquecer(str(arq), revisao=1, revisao_salva=1)
    assert _FalsoFilho.chamou.wait(30)
    g.invalidar()  # geracao nova + cancelamento: o filho velho nao recebe construir
    _FalsoFilho.solta.set()
    _fundo(g)
    assert _nomes() == ["aquecer"] and _FalsoFilho.arqs == []
    outro = tmp_path / "Outro.ifc"
    outro.write_text("ifc")
    _FalsoFilho.solta = None
    g.aquecer(str(outro), revisao=1, revisao_salva=1)
    _fundo(g)
    assert _FalsoFilho.arqs == [str(outro.resolve())]
    g.fechar()


# MUTANTES (numeracao do cartao): 1 test_construcao_ativa_nao_morre_*; 2 test_fila_vazia_*; 3 test_saida_86_nao_conta_como_queda e
# test_86_com_processo_morto_*; 4 test_86_bloqueia_construir_ate_assinatura_nova; 5 test_cancelar_mata_e_filho_novo_recebe_construir;
# 6 test_salvar_invalidar_e_disco_*; 7 test_gerente_padrao_nao_constroi; 8 test_gerente_constroi_na_thread_de_fundo_*;
# 9 test_podar_nao_espera_trava_ocupada e test_podar_volta_rapido_*; 10 EspiaTx (construcao_ativa_*, construir_sem_pendentes_*); 11 test_pasta_geometria.
