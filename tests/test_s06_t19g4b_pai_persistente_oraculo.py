# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oraculo F0-S06-T19g4b: lado do PAI do filho persistente (`openbim_app.desenho.filho`). Nao editar nesta tarefa.

CONTRATO (para o implementador, Hydrogen)
1. Modulo novo `app/openbim_app/desenho/filho.py` com `FilhoPersistente(arquivo, *, ocioso_s=600.0, relogio=time.monotonic, alvo=None)` e
   `class FilhoIndisponivel(RuntimeError)`. Um por documento. `arquivo` = IFC salvo (str ou Path). `alvo` = funcao `(tx, rx)` de nivel de modulo
   (picklavel, spawn) que roda no filho no lugar de `obim_geometria.persistente.servir` (ganchos de teste; `None` = o `servir` real). `tx.send_bytes`
   manda ao pai, `rx.recv_bytes` recebe do pai, como em `servir`. `relogio` so serve para o ocioso; prazos e esperas usam `time.monotonic` real.
   Os erros tipados sao OS MESMOS de `openbim_app.desenho.auxiliar` (`DesenhoCancelado`, `AuxiliarEstourouTempo`, `AuxiliarCaiu`, `Divergente`,
   `FalhaNoAuxiliar`, `ProtocoloInvalido`); importe-os tarde ou deixe `auxiliar` importar `filho` tarde, para nao haver import circular.
2. `.pid` = pid do processo vivo ou `None`. NAO sobe nada na construcao (sob demanda): `.pid is None` ate o 1o `executar`.
3. `.executar(pedido: dict, *, cancelar=None, limite_s=180, ao_fase=None) -> dict`:
   - pega a trava (1 pedido por vez; quem espera a trava e cancelado com `DesenhoCancelado` SEM matar o processo de quem esta rodando);
   - sobe o filho se nao ha (spawn, `daemon=True`; as pontas do pipe do filho sao fechadas no pai, senao o filho nunca ve EOF); espera a mensagem
     `{"tipo":"pronto"}` dentro do mesmo `limite_s`;
   - manda `{**pedido, "numero": N}` com N inteiro estritamente crescente entre pedidos (contador do objeto, vale tambem depois de renascer);
   - le mensagens: `fase` com o numero do pedido chama `ao_fase(nome)`; `resposta` com o numero do pedido termina; mensagem (fase ou resposta) com
     OUTRO numero e DESCARTADA (inclusive sobras que chegam depois e so seriam lidas no pedido seguinte);
   - devolve `auxiliar._tratar_resposta(dados)`: dict ok, ou levanta o erro tipado (`Divergente` etc.). Divergente/FalhaNoAuxiliar NAO matam o processo;
   - `cancelar` disparado no meio: MATA o processo (kill + join, `.pid` vira `None`) e levanta `DesenhoCancelado`; `cancelar` ja disparado antes: levanta
     `DesenhoCancelado` sem mandar nada. Estouro de `limite_s` (spawn incluido): mata e levanta `AuxiliarEstourouTempo`.
   - antes de mandar: se o processo morreu sozinho (queda ociosa) conta como QUEDA; se `os.stat(arquivo)` (tamanho, mtime_ns) difere do gravado quando o
     processo subiu: mata e sobe outro (nao e queda); se ocioso (ver 5): mata e sobe outro.
   - queda no meio do pedido (EOF/morreu sem resposta): conta como QUEDA, descarta o processo e tenta de novo O MESMO pedido com processo novo (numero novo).
     Contador `quedas_seguidas`: +1 em cada queda, zera quando um pedido recebe resposta. Com `quedas_seguidas >= 2` e sem processo, `executar` levanta
     `FilhoIndisponivel` SEM subir outro e continua levantando nos pedidos seguintes (ate `salvar()`/`invalidar()` zerarem, nao testado). Logo: processo que
     cai sempre = 2 spawns e `FilhoIndisponivel`; queda unica = renasce transparente, `executar` devolve o resultado normal.
4. `.salvar()` e `.invalidar()`: matam o processo (se houver; `.pid` vira `None`; o proximo pedido sobe outro). `.podar()`: mata se
   `relogio() - fim_do_ultimo_pedido > ocioso_s` (estritamente maior; fim medido com `relogio` ao terminar o pedido); `executar` aplica a mesma regra
   antes de usar o processo. `.fechar()`: mata, idempotente, depois `executar` levanta `FilhoIndisponivel`.
5. Sem orfao: se o pai morrer (saida normal, `os._exit`, SIGKILL) o filho some sozinho (EOF no pipe + `daemon=True`/`atexit`).
6. Integracao: `auxiliar.executar(preparado, *, limite_s=..., cancelar=None, executor=None, previa=None, filho=None)`. `filho=None` = comportamento de hoje
   (testes antigos de auxiliar seguem verdes). Com `filho`: `filho.executar(preparado.pedido, cancelar=cancelar, limite_s=limite_s)` no lugar de
   `_executar_filho`, com `_acrescentar_tempos` no resultado; `previa` e ignorada; `FilhoIndisponivel` => cai em `_executar_filho` (descartavel); qualquer
   outro erro (DesenhoCancelado, Divergente...) sobe sem cair. `executor=` tem prioridade sobre `filho=`.
7. Equivalencia: 2+ vistas seguidas pelo filho persistente dao SVG byte a byte igual ao do descartavel e o MESMO pid.
Nao coberto aqui (fica para o implementador/revisao): memoria alta, pre-aquecimento, atexit sob Windows, renascer em segundo plano.

Mutantes (referencia `_Ref` neste arquivo, a MESMA verificacao roda na referencia boa, nos mutantes e no real): nao matar no cancelar; ignorar numero do
pedido; ignorar arquivo mudado; sem renascer apos queda; renascer sem limite; orfao apos `fechar()`; matar no `Divergente`."""
from __future__ import annotations

import functools
import inspect
import json
import multiprocessing
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

# O filho (spawn) reimporta este modulo para achar `_alvo_eco`: so o processo de teste carrega as fixtures pesadas.
if multiprocessing.current_process().name == "MainProcess" and not os.environ.get("OBIM_T19G4B_LEVE"):
    from s05_conteudo_aux import _limpa, exigir  # noqa: F401  (fixture autouse e guarda)
    from test_s06_t19g3_sem_rastro_oraculo import cena  # noqa: F401  (cena = fixture)

from openbim_app.desenho import auxiliar as A  # noqa: E402

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent
PRONTO = {"tipo": "pronto", "pid": 0, "protocolo": 1}


# ------------------------------------------------------------------ alvo de teste (roda no filho)
def _log(linha):
    p = os.environ.get("OBIM_T19G4B_LOG")
    if p:
        with open(p, "a", encoding="utf-8") as f:
            f.write(f"{linha}\n")


def _alvo_eco(tx, rx):
    """Filho de brinquedo. Campos do pedido: `dormir_s`, `marca`, `divergir`, `sair` (cai sempre), `sair_uma_vez` (caminho de marcador),
    `velho` (manda fase+resposta de numero velho antes da certa), `lixo_depois` (manda resposta velha depois da certa)."""
    def env(o):
        tx.send_bytes(json.dumps(o).encode())

    _log(str(os.getpid()))
    env({**PRONTO, "pid": os.getpid()})
    while True:
        try:
            p = json.loads(rx.recv_bytes())
        except EOFError:
            return
        if p.get("op") == "encerrar":
            return
        n = p["numero"]
        um = p.get("sair_uma_vez")
        if p.get("sair") or (um and not os.path.exists(um)):
            if um:
                open(um, "w").close()
            os._exit(3)
        if p.get("velho"):
            env({"tipo": "fase", "numero": n - 1, "fase": "velha", "tempo": 0.0})
            env({"tipo": "resposta", "numero": n - 1, "dados": {"ok": True, "marca": "velha"}})
        env({"tipo": "fase", "numero": n, "fase": "aberto", "tempo": 0.0})
        ini = time.time()
        time.sleep(p.get("dormir_s", 0))
        fim = time.time()
        env({"tipo": "fase", "numero": n, "fase": "fim", "tempo": 0.0})
        if p.get("divergir"):
            dados = {"ok": False, "erro": {"tipo": "Divergente", "mensagem": "divergiu", "rastro": ""}}
        else:
            dados = {"ok": True, "marca": p.get("marca", "nova"), "numero": n, "pid": os.getpid(), "ini": ini, "fim": fim}
        env({"tipo": "resposta", "numero": n, "dados": dados})
        if p.get("lixo_depois"):
            env({"tipo": "resposta", "numero": n - 1, "dados": {"ok": True, "marca": "lixo"}})


# ------------------------------------------------------------------ utilidades
def _vivo(pid):
    if sys.platform == "win32":
        import ctypes
        k = ctypes.windll.kernel32
        h = k.OpenProcess(0x1000, 0, pid)
        if not h:
            return False
        code = ctypes.c_ulong()
        k.GetExitCodeProcess(h, ctypes.byref(code))
        k.CloseHandle(h)
        return code.value == 259
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    try:  # zumbi (filho nao recolhido) conta como morto
        return Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0] != "Z"
    except OSError:
        return True


def _esperar_morto(pid, s=10.0):
    fim = time.monotonic() + s
    while time.monotonic() < fim:
        if not _vivo(pid):
            return True
        time.sleep(0.05)
    return not _vivo(pid)


def _matar_a_forca(pid):
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True, check=False)
    else:
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass


class Reg:
    """Registro de pids que `_alvo_eco` grava (um por spawn) e limpeza no fim do teste (mutantes deixam orfaos de proposito)."""

    def __init__(self, caminho):
        self.caminho = caminho

    def pids(self):
        try:
            return [int(x) for x in Path(self.caminho).read_text().split()]
        except OSError:
            return []

    def spawns(self):
        return len(self.pids())


@pytest.fixture
def lg(tmp_path, monkeypatch):
    r = Reg(str(tmp_path / "pids.log"))
    monkeypatch.setenv("OBIM_T19G4B_LOG", r.caminho)
    yield r
    for pid in r.pids():
        _matar_a_forca(pid)


@pytest.fixture
def arq(tmp_path):
    p = tmp_path / "doc.ifc"
    p.write_text("ISO-10303-21;\nDATA;\nENDSEC;\n")
    return str(p)


class _Rel:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def _real():
    from openbim_app.desenho import filho  # noqa: PLC0415  (falha hoje: modulo nao existe)
    return filho.FilhoPersistente


def _levanta(nome, fn):
    with pytest.raises(Exception) as e:
        fn()
    assert type(e.value).__name__ == nome, f"esperava {nome}, veio {e.value!r}"


# ------------------------------------------------------------------ referencia (boa e mutantes)
class FilhoIndisponivel(RuntimeError):
    pass


class _Ref:
    def __init__(self, arquivo, *, alvo=None, ocioso_s=600.0, relogio=time.monotonic, defeitos=()):
        self.arquivo, self.alvo, self.d = str(arquivo), alvo, set(defeitos)
        self._p = self._rx = self._tx = self._sig = None
        self._n = self._q = self._spawns = 0
        self._fechado = False
        self._ctx = multiprocessing.get_context("spawn")
        self._trava = threading.Lock()

    @property
    def pid(self):
        return self._p.pid if self._p is not None else None

    def _disco(self):
        st = os.stat(self.arquivo)
        return (int(st.st_size), int(st.st_mtime_ns))

    def _matar(self):
        p, rx, tx, self._p, self._rx, self._tx = self._p, self._rx, self._tx, None, None, None
        if p is not None:
            p.kill()
            p.join(5)
            rx.close()
            tx.close()

    def _ler(self, fim, cancelar):
        while True:
            if cancelar is not None and cancelar.is_set():
                raise A.DesenhoCancelado("cancelado")
            if time.monotonic() > fim:
                raise A.AuxiliarEstourouTempo(0, "")
            if self._rx.poll(0.05):
                try:
                    return json.loads(self._rx.recv_bytes())
                except (EOFError, OSError):
                    raise A.AuxiliarCaiu(1) from None
            if not self._p.is_alive():
                raise A.AuxiliarCaiu(1)

    def _subir(self, fim, cancelar):
        rx, tx_c = self._ctx.Pipe(duplex=False)
        rx_c, tx = self._ctx.Pipe(duplex=False)
        p = self._ctx.Process(target=self.alvo, args=(tx_c, rx_c), daemon=True)
        p.start()
        tx_c.close()
        rx_c.close()
        self._p, self._rx, self._tx, self._sig = p, rx, tx, self._disco()
        self._spawns += 1
        self._ler(fim, cancelar)  # "pronto"

    def executar(self, pedido, *, cancelar=None, limite_s=180, ao_fase=None):
        with self._trava:
            fim = time.monotonic() + limite_s
            if cancelar is not None and cancelar.is_set():
                raise A.DesenhoCancelado("cancelado antes")
            while True:
                if self._fechado:
                    raise FilhoIndisponivel("fechado")
                if self._p is not None and not self._p.is_alive():
                    self._matar()
                    self._q += 1
                if self._p is not None and "ignora_assinatura" not in self.d and self._disco() != self._sig:
                    self._matar()
                if self._p is None:
                    if (self._q >= 2 and "renasce_sempre" not in self.d) or ("sem_renascer" in self.d and self._q >= 1) or self._spawns >= 8:
                        raise FilhoIndisponivel("indisponivel")
                try:
                    if self._p is None:
                        self._subir(fim, cancelar)
                    self._n += 1
                    n = self._n
                    self._tx.send_bytes(json.dumps({**pedido, "numero": n}).encode())
                    while True:
                        m = self._ler(fim, cancelar)
                        certo = "ignora_numero" in self.d or m.get("numero") == n
                        if m.get("tipo") == "fase" and certo and ao_fase:
                            ao_fase(m["fase"])
                        elif m.get("tipo") == "resposta" and certo:
                            dados = m["dados"]
                            break
                except (A.DesenhoCancelado, A.AuxiliarEstourouTempo) as e:
                    if not ("nao_mata_cancelar" in self.d and isinstance(e, A.DesenhoCancelado)):
                        self._matar()
                    raise
                except A.AuxiliarCaiu:
                    self._matar()
                    self._q += 1
                    continue
                self._q = 0
                try:
                    return A._tratar_resposta(dados)
                except A.Divergente:
                    if "mata_divergente" in self.d:
                        self._matar()
                    raise

    def fechar(self):
        self._fechado = True
        if "orfao" not in self.d:
            self._matar()


# ------------------------------------------------------------------ verificacoes (rodam no real, na referencia boa e nos mutantes)
def chk_cancelar(mk, lg, arq):
    f = mk(arq, alvo=_alvo_eco)
    ev, iniciou, res = threading.Event(), threading.Event(), {}

    def rodar():
        try:
            f.executar({"dormir_s": 60}, cancelar=ev, ao_fase=lambda _n: iniciou.set())
        except BaseException as e:  # noqa: BLE001
            res["e"] = e

    t = threading.Thread(target=rodar)
    t.start()
    assert iniciou.wait(60), "pedido nao comecou"
    pid = f.pid
    assert pid and _vivo(pid)
    ev.set()
    t.join(15)
    assert not t.is_alive(), "cancelar nao interrompeu o pedido"
    assert isinstance(res.get("e"), A.DesenhoCancelado), res
    assert _esperar_morto(pid, 5), "cancelar nao matou o filho"
    assert f.pid is None
    d = f.executar({})
    assert d["ok"] and d["pid"] != pid and f.pid == d["pid"]
    f.fechar()


def chk_numero(mk, lg, arq):
    f = mk(arq, alvo=_alvo_eco)
    fases = []
    d1 = f.executar({"velho": True}, ao_fase=fases.append)
    assert d1["marca"] == "nova", "aceitou resposta de numero velho"
    assert fases == ["aberto", "fim"], f"fase de numero velho vazou: {fases}"
    d2 = f.executar({"lixo_depois": True})
    d3 = f.executar({})
    assert d2["marca"] == "nova" and d3["marca"] == "nova", "sobra de resposta velha contaminou o pedido seguinte"
    d4 = f.executar({"velho": True, "lixo_depois": True})
    d5 = f.executar({})
    nums = [d["numero"] for d in (d1, d2, d3, d4, d5)]
    assert all(a < b for a, b in zip(nums, nums[1:])), f"numero nao e estritamente crescente: {nums}"
    assert len({d["pid"] for d in (d1, d2, d3, d4, d5)}) == 1 and lg.spawns() == 1
    f.fechar()


def chk_arquivo_mudou(mk, lg, arq):
    f = mk(arq, alvo=_alvo_eco)
    pid1 = f.executar({})["pid"]
    assert f.executar({})["pid"] == pid1, "sem mudanca no disco o processo tem de ser reaproveitado"
    st = os.stat(arq)
    with open(arq, "ab") as h:
        h.write(b"mais\n")
    novo = st.st_mtime_ns + 5 * 10**9
    os.utime(arq, ns=(novo, novo))
    d = f.executar({})
    assert d["pid"] != pid1, "arquivo mudou no disco e o filho velho foi reaproveitado"
    assert _esperar_morto(pid1, 5), "filho velho ficou vivo"
    assert f.pid == d["pid"]
    f.fechar()


def chk_queda(mk, lg, arq):
    # (a) cai sempre: 2 spawns, depois FilhoIndisponivel, e continua indisponivel
    f = mk(arq, alvo=_alvo_eco)
    s0 = lg.spawns()
    _levanta("FilhoIndisponivel", lambda: f.executar({"sair": True}))
    assert lg.spawns() - s0 == 2, f"esperava 1 spawn + 1 renascimento, houve {lg.spawns() - s0}"
    _levanta("FilhoIndisponivel", lambda: f.executar({}))
    assert lg.spawns() - s0 == 2, "voltou a subir filho depois da 2a queda seguida"
    f.fechar()
    # (b) cai uma vez no meio do pedido: renasce e devolve o resultado normal
    g = mk(arq, alvo=_alvo_eco)
    s1 = lg.spawns()
    d = g.executar({"sair_uma_vez": str(Path(arq).parent / "marcador")})
    assert d["ok"] and d["marca"] == "nova" and lg.spawns() - s1 == 2 and g.pid == d["pid"]
    # (c) queda ociosa (kill de fora) duas vezes, com sucesso no meio: o contador zera ao receber resposta
    if sys.platform != "win32":
        for _ in range(2):
            antigo = g.pid
            os.kill(antigo, signal.SIGKILL)
            assert _esperar_morto(antigo, 5)
            d = g.executar({})
            assert d["ok"] and d["pid"] != antigo
    g.fechar()


def chk_fechar(mk, lg, arq):
    f = mk(arq, alvo=_alvo_eco)
    pid = f.executar({})["pid"]
    f.fechar()
    assert _esperar_morto(pid, 5), "processo orfao depois de fechar()"
    f.fechar()  # idempotente
    assert f.pid is None
    _levanta("FilhoIndisponivel", lambda: f.executar({}))
    assert all(_esperar_morto(p, 5) for p in lg.pids())


def chk_divergente(mk, lg, arq):
    f = mk(arq, alvo=_alvo_eco)
    pid = f.executar({})["pid"]
    with pytest.raises(A.Divergente):
        f.executar({"divergir": True})
    assert f.pid == pid and _vivo(pid), "Divergente matou o filho"
    d = f.executar({})
    assert d["ok"] and d["pid"] == pid
    f.fechar()


CASOS = {
    "cancelar": (chk_cancelar, "nao_mata_cancelar"),
    "numero": (chk_numero, "ignora_numero"),
    "arquivo_mudou": (chk_arquivo_mudou, "ignora_assinatura"),
    "sem_renascer": (chk_queda, "sem_renascer"),
    "renasce_sem_limite": (chk_queda, "renasce_sempre"),
    "fechar_orfao": (chk_fechar, "orfao"),
    "divergente": (chk_divergente, "mata_divergente"),
}


@pytest.mark.parametrize("nome", CASOS)
def test_referencia_boa_passa(nome, lg, arq):
    """Se isto falha, o oraculo e que esta errado."""
    CASOS[nome][0](_Ref, lg, arq)


@pytest.mark.parametrize("nome", CASOS)
def test_mutante_e_derrubado(nome, lg, arq):
    chk, defeito = CASOS[nome]
    with pytest.raises(Exception):  # noqa: B017  (AssertionError ou o erro que o mutante provoca)
        chk(functools.partial(_Ref, defeitos=[defeito]), lg, arq)


@pytest.mark.parametrize("nome", [n for n in CASOS if n not in ("renasce_sem_limite",)])
def test_real(nome, lg, arq):
    CASOS[nome][0](_real(), lg, arq)


# ------------------------------------------------------------------ real: o que a referencia nao cobre
def test_assinatura_publica():
    cls = _real()
    ps = inspect.signature(cls.__init__).parameters
    assert {"arquivo", "ocioso_s", "relogio", "alvo"} <= set(ps) and ps["alvo"].default is None
    pe = inspect.signature(cls.executar).parameters
    assert {"cancelar", "limite_s", "ao_fase"} <= set(pe)
    assert all(pe[k].kind is inspect.Parameter.KEYWORD_ONLY for k in ("cancelar", "limite_s", "ao_fase"))
    pa = inspect.signature(A.executar).parameters
    assert "filho" in pa and pa["filho"].default is None


def test_sobe_sob_demanda_e_reaproveita(lg, arq):
    f = _real()(arq, alvo=_alvo_eco)
    assert f.pid is None and lg.spawns() == 0, "subiu antes do primeiro pedido"
    d = f.executar({"marca": "x"})
    assert d["marca"] == "x" and lg.spawns() == 1 and f.pid == d["pid"]
    assert f.executar({})["pid"] == d["pid"] and lg.spawns() == 1
    f.fechar()


def test_ao_fase_recebe_so_as_fases_do_pedido(lg, arq):
    f = _real()(arq, alvo=_alvo_eco)
    fases = []
    f.executar({}, ao_fase=fases.append)
    assert fases == ["aberto", "fim"]
    f.fechar()


def test_estouro_de_tempo_mata(lg, arq):
    f = _real()(arq, alvo=_alvo_eco)
    t0 = time.monotonic()
    with pytest.raises(A.AuxiliarEstourouTempo):
        f.executar({"dormir_s": 60}, limite_s=3.0)
    assert time.monotonic() - t0 < 20
    assert f.pid is None and all(_esperar_morto(p, 5) for p in lg.pids())
    assert f.executar({})["ok"] and f.pid is not None
    f.fechar()


def test_cancelar_antes_de_comecar_nao_manda_nada(lg, arq):
    f = _real()(arq, alvo=_alvo_eco)
    ev = threading.Event()
    ev.set()
    with pytest.raises(A.DesenhoCancelado):
        f.executar({}, cancelar=ev)
    f.fechar()


@pytest.mark.parametrize("metodo", ["salvar", "invalidar"])
def test_salvar_e_invalidar_matam(metodo, lg, arq):
    f = _real()(arq, alvo=_alvo_eco)
    pid = f.executar({})["pid"]
    getattr(f, metodo)()
    assert f.pid is None and _esperar_morto(pid, 5), f"{metodo}() nao matou o filho"
    d = f.executar({})
    assert d["pid"] != pid and lg.spawns() == 2
    f.fechar()


def test_ocioso_com_relogio_injetado(lg, arq):
    rel = _Rel()
    f = _real()(arq, alvo=_alvo_eco, ocioso_s=5.0, relogio=rel)
    pid = f.executar({})["pid"]
    rel.t += 4.9
    f.podar()
    assert f.pid == pid and _vivo(pid), "podou antes do limite"
    assert f.executar({})["pid"] == pid  # reaproveitado a 4.9 s; o ocioso conta do fim deste pedido
    rel.t += 5.1
    f.podar()
    assert f.pid is None and _esperar_morto(pid, 5), "ocioso > ocioso_s nao matou"
    pid2 = f.executar({})["pid"]
    assert pid2 != pid
    rel.t += 6.0  # sem podar(): o proprio executar aplica a regra
    pid3 = f.executar({})["pid"]
    assert pid3 != pid2 and _esperar_morto(pid2, 5)
    f.fechar()


def test_um_pedido_por_vez_e_respostas_nao_se_misturam(lg, arq):
    f = _real()(arq, alvo=_alvo_eco)
    res = {}

    def rodar(k):
        res[k] = f.executar({"dormir_s": 0.4, "marca": k})

    ts = [threading.Thread(target=rodar, args=(k,)) for k in ("T1", "T2", "T3")]
    for t in ts:
        t.start()
    for t in ts:
        t.join(60)
    assert {k: v["marca"] for k, v in res.items()} == {"T1": "T1", "T2": "T2", "T3": "T3"}
    ordem = sorted(res.values(), key=lambda d: d["ini"])
    assert all(a["fim"] <= b["ini"] + 0.01 for a, b in zip(ordem, ordem[1:])), "dois pedidos rodaram ao mesmo tempo"
    assert len({d["pid"] for d in res.values()}) == 1 and lg.spawns() == 1
    f.fechar()


def test_cancelar_na_fila_nao_mata_o_pedido_que_roda(lg, arq):
    f = _real()(arq, alvo=_alvo_eco)
    iniciou, res = threading.Event(), {}

    def a():
        res["a"] = f.executar({"dormir_s": 3, "marca": "A"}, ao_fase=lambda _n: iniciou.set())

    ta = threading.Thread(target=a)
    ta.start()
    assert iniciou.wait(60)
    pid = f.pid
    ev = threading.Event()

    def b():
        try:
            f.executar({}, cancelar=ev)
        except BaseException as e:  # noqa: BLE001
            res["b"] = e

    tb = threading.Thread(target=b)
    tb.start()
    time.sleep(0.3)
    ev.set()
    tb.join(2.5)
    assert not tb.is_alive() and isinstance(res.get("b"), A.DesenhoCancelado), "quem espera a trava tem de poder cancelar"
    ta.join(60)
    assert res["a"]["marca"] == "A" and res["a"]["pid"] == pid and _vivo(pid), "cancelar na fila matou o pedido de outro"
    f.fechar()


@pytest.mark.parametrize("saida", ["natural", "_exit", "sigkill"])
def test_morte_do_pai_nao_deixa_orfao(saida, lg, arq, tmp_path):
    if saida == "sigkill" and sys.platform == "win32":
        pytest.skip("SIGKILL do proprio processo so em POSIX")
    destino = tmp_path / "pid.txt"
    script = tmp_path / "pai.py"
    script.write_text(
        "import os, signal, sys\n"
        f"sys.path[:0] = {[str(RAIZ / 'app'), str(RAIZ / 'geometria'), str(AQUI)]!r}\n"
        "import test_s06_t19g4b_pai_persistente_oraculo as T\n"
        "from openbim_app.desenho.filho import FilhoPersistente\n"
        "if __name__ == '__main__':\n"
        f"    f = FilhoPersistente({arq!r}, alvo=T._alvo_eco)\n"
        "    f.executar({})\n"
        f"    open({str(destino)!r}, 'w').write(str(f.pid))\n"
        f"    saida = {saida!r}\n"
        "    if saida == '_exit':\n"
        "        os._exit(0)\n"
        "    if saida == 'sigkill':\n"
        "        os.kill(os.getpid(), signal.SIGKILL)\n",
        encoding="utf-8")
    env = {**os.environ, "OBIM_T19G4B_LEVE": "1"}
    subprocess.run([sys.executable, str(script)], env=env, timeout=180, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    pid = int(destino.read_text())
    assert _esperar_morto(pid, 20), f"filho {pid} ficou orfao quando o pai saiu por '{saida}'"


# ------------------------------------------------------------------ integracao com auxiliar.executar
class _Stub:
    def __init__(self, resultado=None, erro=None):
        self.resultado, self.erro, self.chamadas = resultado, erro, []

    def executar(self, pedido, *, cancelar=None, limite_s=None, ao_fase=None):
        self.chamadas.append((pedido, cancelar, limite_s))
        if self.erro is not None:
            raise self.erro
        return self.resultado


def _prep(arq):
    return A.preparar(None, {"op": "desenho", "elementos": []}, caminho_ifc=arq)


def test_auxiliar_usa_o_filho_e_nao_o_descartavel(arq, monkeypatch):
    monkeypatch.setattr(A, "_executar_filho", lambda *a, **k: pytest.fail("usou o descartavel com filho= vivo"))
    stub = _Stub({"ok": True, "tempos": {}})
    ev = threading.Event()
    with _prep(arq) as pr:
        r = A.executar(pr, filho=stub, cancelar=ev, limite_s=7)
        assert stub.chamadas == [(pr.pedido, ev, 7)]
    assert r["ok"] and "auxiliar_s" in r["tempos"] and "copia_s" in r["tempos"]


def test_auxiliar_cai_no_descartavel_se_filho_indisponivel(arq, monkeypatch):
    from openbim_app.desenho.filho import FilhoIndisponivel  # noqa: PLC0415
    chamou = []
    monkeypatch.setattr(A, "_executar_filho", lambda *a, **k: (chamou.append(1), {"ok": True, "via": "descartavel", "tempos": {}})[1])
    with _prep(arq) as pr:
        r = A.executar(pr, filho=_Stub(erro=FilhoIndisponivel("x")))
    assert r["via"] == "descartavel" and chamou == [1]


@pytest.mark.parametrize("erro", [A.DesenhoCancelado("c"), A.Divergente("d"), A.AuxiliarEstourouTempo(1, "")])
def test_auxiliar_outros_erros_sobem_sem_cair(arq, monkeypatch, erro):
    monkeypatch.setattr(A, "_executar_filho", lambda *a, **k: pytest.fail("caiu no descartavel por erro que nao e FilhoIndisponivel"))
    with _prep(arq) as pr:
        with pytest.raises(type(erro)):
            A.executar(pr, filho=_Stub(erro=erro))


def test_auxiliar_sem_filho_mantem_o_caminho_antigo(arq, monkeypatch):
    chamou = []
    monkeypatch.setattr(A, "_executar_filho", lambda *a, **k: (chamou.append(1), {"ok": True, "tempos": {}})[1])
    with _prep(arq) as pr:
        assert A.executar(pr)["ok"] and A.executar(pr, filho=None)["ok"]
    assert chamou == [1, 1]


def test_auxiliar_filho_fechado_cai_no_descartavel(arq, lg, monkeypatch):
    f = _real()(arq, alvo=_alvo_eco)
    f.fechar()
    monkeypatch.setattr(A, "_executar_filho", lambda *a, **k: {"ok": True, "via": "descartavel", "tempos": {}})
    with _prep(arq) as pr:
        assert A.executar(pr, filho=f)["via"] == "descartavel"


# ------------------------------------------------------------------ equivalencia com o filho de verdade (servir) e o descartavel
def test_equivalencia_svg_persistente_igual_ao_descartavel_mesmo_pid(cena):
    salvo, ped = cena
    seq = "ABRA"
    ref = {}
    for k in "ABR":
        with A.preparar(None, ped[k], caminho_ifc=salvo) as pr:
            r = A.executar(pr)
        assert r["ok"] and r["svg"], (k, r)
        ref[k] = r["svg"]
    assert len(set(ref.values())) == 3
    f = _real()(str(salvo))
    try:
        pids = []
        for k in seq:
            with A.preparar(None, ped[k], caminho_ifc=salvo) as pr:
                r = A.executar(pr, filho=f)
            assert r["ok"] and r["svg"] == ref[k], f"vista {k}: SVG do persistente difere do descartavel"
            pids.append(f.pid)
        assert pids[0] and len(set(pids)) == 1, f"o filho nao foi reaproveitado: pids {pids}"
    finally:
        f.fechar()
    assert f.pid is None and _esperar_morto(pids[0], 10)
