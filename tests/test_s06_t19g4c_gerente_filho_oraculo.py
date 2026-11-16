# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oraculo F0-S06-T19g4c: o gerente usa o filho persistente (chave desligada por padrao). Nao editar nesta tarefa.

CONTRATO (decisoes do oraculo; o cartao deixou detalhes em aberto)
1. `GerenteDesenho(cache=None, *, motor=None, chave_estado=None, filho_persistente: bool = False, parent=None)`.
2. Gate = o da T19g2 (`caminho_ifc` dado, `revisao is not None and revisao == revisao_salva`, arquivo existe). So com `filho_persistente=True` E gate
   aberto o gerente cria (na thread de `pedir`, sob demanda, 1 vez) um `openbim_app.desenho.filho.FilhoPersistente(caminho_resolvido)` por documento;
   chave = `Path(caminho_ifc).resolve()` (grafias diferentes do mesmo arquivo = o MESMO filho; arquivos diferentes = filhos DIFERENTES, nunca compartilhados).
   Usar a classe real (o oraculo espia `FilhoPersistente.__init__/executar/salvar/invalidar/podar/fechar` na classe, qualquer estilo de import serve).
3. Entrega ao motor: o gerente passa `filho=<instancia>` como kwarg ao motor SO se a assinatura do motor aceitar `filho` ou `**kw` (como ja faz com
   `previa` e `sessao_selecao`). Sem filho (chave desligada, gate fechado) o kwarg e omitido ou `None`. `filho` e `filho_persistente` NUNCA aparecem em
   `opcoes` do motor (e `revisao`, `revisao_salva` continuam fora, como na T19g2; `caminho_ifc` so com o gate aberto).
4. `_motor_padrao(..., previa=None, sessao_selecao=None, filho=None)` repassa `filho=` a `gerar_corte`/`gerar_planta` (com `filho=None` o kwarg e omitido ou
   `None`). `gerar_corte`, `gerar_planta` e `selecao.selecionar` ganham `filho=None` keyword-only; validacao: `None` ou objeto com `executar` chamavel, senao
   `TypeError` (antes de qualquer trabalho); repassam a `auxiliar.executar(..., filho=filho)` (inclusive o pedido `caixas` da selecao e o retry sem `caminho_ifc`).
5. Ciclo de vida: `invalidar(ifc=None, ids=None)` (qualquer forma) chama `.invalidar()` em TODOS os filhos (o objeto fica; o processo morre; o proximo
   pedido reaproveita o mesmo objeto, sem criar outro). Novo `salvar()` publico (sem argumentos) chama `.salvar()` em todos. Novo `fechar()` publico:
   faz o que `encerrar()` faz hoje (cancela pedidos, junta threads) e depois, para cada filho, `.podar()` e `.fechar()`; esquece os filhos; idempotente.
   `encerrar()` passa a ser o mesmo que `fechar()` (nenhum caminho de saida deixa filho vivo).
6. `podar()` de todos os filhos e chamado a cada `pedir` (depois de resolver o filho do pedido) e uma vez no `fechar`, antes do `.fechar()` do filho.
7. Cancelar um pedido que roda no filho segue o contrato do `FilhoPersistente`: `cancelar=` mata o processo; o pedido seguinte renasce (pid novo).
8. Chave desligada (padrao) = comportamento atual e NENHUM `FilhoPersistente` e criado, nem com gate aberto.

Estrutura: (a) `_unit` roda o contrato com motor espiao; a MESMA verificacao roda na referencia boa (`_Ref`, um gerente de teste que implementa o contrato),
nos mutantes (filho com gate fechado; filho nao fechado no fechar; filho compartilhado; chave ignorada; invalidar sem matar; sem podar; salvar sem matar) e no gerente
real (HOJE FALHA: `filho_persistente` nao existe). (b) `_motor_padrao`/`gerar_*`/`selecionar` com filho falso em processo. (c) ponta a ponta com processo REAL
(cena sintetica leve): 2 cortes de vistas diferentes mesmo pid, SVG byte a byte igual ao descartavel, cancelar mata e o seguinte renasce, fechar nao deixa orfao."""
from __future__ import annotations

import copy
import functools
import itertools
import os
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
import s06_t07b_aux as B
import s06_t07c_aux as C
from s05_conteudo_aux import _limpa, exigir  # noqa: F401  (fixture autouse e guarda)
from s06_t15i_aux import corte, local, planta, selecao  # noqa: F401

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtCore")
from PySide6.QtCore import QCoreApplication, QEventLoop, QTimer  # noqa: E402

from openbim_app.desenho import auxiliar as A  # noqa: E402
from openbim_app.desenho import gerente as G  # noqa: E402
from openbim_app.desenho.filho import FilhoPersistente  # noqa: E402
from openbim_app.desenho.gerente import GerenteDesenho  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QCoreApplication.instance() or QCoreApplication([])


# ------------------------------------------------------------------ espiao da classe real
class Espia:
    """Espia `FilhoPersistente` na classe: instancias criadas e chamadas (nome, instancia) em ordem. Delega sempre ao original."""

    def __init__(self, mp):
        self.instancias, self.eventos, self.pids = [], [], []
        orig = {n: getattr(FilhoPersistente, n) for n in ("__init__", "executar", "salvar", "invalidar", "podar", "fechar")}

        def ini(me, *a, **k):
            self.instancias.append(me)
            return orig["__init__"](me, *a, **k)

        mp.setattr(FilhoPersistente, "__init__", ini)
        for n in ("salvar", "invalidar", "podar", "fechar"):
            mp.setattr(FilhoPersistente, n, self._embrulho(n, orig[n]))

        def exe(me, *a, **k):
            try:
                return orig["executar"](me, *a, **k)
            finally:
                self.pids.append((me, me.pid))

        mp.setattr(FilhoPersistente, "executar", exe)

    def _embrulho(self, nome, f):
        def w(me, *a, **k):
            self.eventos.append((nome, me))
            return f(me, *a, **k)
        return w

    def n(self, nome, inst=None):
        return sum(1 for x, i in self.eventos if x == nome and (inst is None or i is inst))


@pytest.fixture
def espia(monkeypatch):
    return Espia(monkeypatch)


# ------------------------------------------------------------------ (a) contrato com motor espiao
class Motor:
    def __init__(self):
        self.chamadas = []  # (opcoes, kw)

    def __call__(self, tipo, ifc, guid, opcoes, *, cancelar, progresso, **kw):
        self.chamadas.append((dict(opcoes), dict(kw)))
        return {"svg": "<svg/>", "n_paths": 0, "tempos": {}, "caixas": [], "em_cache": []}


class _Ref(GerenteDesenho):
    """Gerente de referencia (so o contrato; `bug` liga um mutante). Usa o motor injetado e a classe real FilhoPersistente (espiada)."""
    bug = None

    def __init__(self, *a, filho_persistente=False, **k):
        super().__init__(*a, **k)
        self._fp, self._filhos, self._tl = bool(filho_persistente) or self.bug == "chave_ignorada", {}, threading.local()
        base = self._motor

        def m(tipo, ifc, guid, opcoes, *, cancelar, progresso, **kw):
            kw["filho"] = getattr(self._tl, "filho", None)
            return base(tipo, ifc, guid, opcoes, cancelar=cancelar, progresso=progresso, **kw)

        self._motor = m

    def pedir(self, tipo, ifc, vista_guid, *, caminho_ifc=None, revisao_salva=None, revisao=None, **opcoes):
        aberto = bool(caminho_ifc) and revisao is not None and revisao == revisao_salva and Path(caminho_ifc).is_file()
        if self.bug == "gate_fechado_cria":
            aberto = bool(caminho_ifc)
        filho = None
        if self._fp and aberto:
            k = "unico" if self.bug == "compartilha" else str(Path(caminho_ifc).resolve())
            if k not in self._filhos:
                self._filhos[k] = FilhoPersistente(Path(caminho_ifc).resolve())
            filho = self._filhos[k]
        if self.bug != "sem_podar":
            for f in self._filhos.values():
                f.podar()
        if aberto:
            opcoes["__filho__"] = filho
        return super().pedir(tipo, ifc, vista_guid, caminho_ifc=caminho_ifc, revisao_salva=revisao_salva, revisao=revisao, **opcoes)

    def _rodar(self, ped, tipo, ifc, vista_guid, opcoes, sessao=None):
        opcoes = dict(opcoes)
        self._tl.filho = opcoes.pop("__filho__", None)
        return super()._rodar(ped, tipo, ifc, vista_guid, opcoes, sessao)

    def invalidar(self, ifc=None, ids=None):
        super().invalidar(ifc, ids)
        if self.bug != "invalidar_sem_matar":
            for f in self._filhos.values():
                f.invalidar()

    def salvar(self):
        if self.bug != "salvar_sem_matar":
            for f in self._filhos.values():
                f.salvar()

    def fechar(self):
        GerenteDesenho.encerrar(self)
        for f in self._filhos.values():
            f.podar()
            if self.bug != "nao_fecha":
                f.fechar()
        self._filhos.clear()

    def encerrar(self):
        self.fechar()


def _mut(nome):
    return type(f"Ref_{nome}", (_Ref,), {"bug": nome})


def _gerente(cls, motor, **kw):
    c = itertools.count()
    return cls(motor=motor, chave_estado=lambda t, i, g, o: f"{t}|{g}|{next(c)}", **kw)


def _esperar_n(motor, n, s=10.0):
    fim = time.monotonic() + s
    while len(motor.chamadas) < n and time.monotonic() < fim:
        time.sleep(0.01)
    assert len(motor.chamadas) == n, f"esperava {n} chamadas ao motor, vieram {len(motor.chamadas)}"


def _p(g, motor, n_antes, guid, ifc=None, **kw):
    g.pedir("corte", ifc if ifc is not None else object(), guid, **kw)
    _esperar_n(motor, n_antes + 1)
    return motor.chamadas[-1]


def _unit(cls, espia, tmp_path):
    a, b = tmp_path / "a.ifc", tmp_path / "b.ifc"
    for x in (a, b):
        x.write_text("ISO-10303-21;")
    (tmp_path / "sub").mkdir()
    a_alias = tmp_path / "sub" / ".." / "a.ifc"
    aberto = dict(revisao=1, revisao_salva=1)
    outros = []

    # chave desligada (padrao e explicita): nenhum FilhoPersistente, kwarg ausente ou None, mesmo com gate aberto
    for kw in ({}, {"filho_persistente": False}):
        m = Motor()
        g = _gerente(cls, m, **kw)
        op, k = _p(g, m, 0, "V1", caminho_ifc=a, **aberto)
        assert k.get("filho") is None and "caminho_ifc" in op
        g.fechar()
    assert espia.instancias == [], "chave desligada nao pode criar FilhoPersistente"

    m = Motor()
    g = _gerente(cls, m, filho_persistente=True)
    # gate fechado (revisao != salva; sem revisao; arquivo ausente; sem caminho): descartavel, nada criado
    for kw in (dict(caminho_ifc=a, revisao=2, revisao_salva=1), dict(caminho_ifc=a), dict(caminho_ifc=tmp_path / "nao.ifc", **aberto), dict(**aberto)):
        op, k = _p(g, m, len(m.chamadas), f"F{len(m.chamadas)}", **kw)
        assert k.get("filho") is None, kw
    assert espia.instancias == [], "gate fechado nao pode criar filho"

    # gate aberto: um filho por documento, o mesmo em vistas diferentes e em grafias diferentes do caminho
    op1, k1 = _p(g, m, len(m.chamadas), "V1", caminho_ifc=a, **aberto)
    assert len(espia.instancias) == 1 and k1["filho"] is espia.instancias[0]
    assert Path(espia.instancias[0].arquivo).resolve() == a.resolve()
    _, k2 = _p(g, m, len(m.chamadas), "V2", caminho_ifc=a, **aberto)
    _, k3 = _p(g, m, len(m.chamadas), "V3", caminho_ifc=a_alias, **aberto)
    assert k2["filho"] is k1["filho"] is k3["filho"] and len(espia.instancias) == 1
    # outro documento: outro filho, nunca compartilhado
    _, kb = _p(g, m, len(m.chamadas), "V4", caminho_ifc=b, **aberto)
    assert len(espia.instancias) == 2 and kb["filho"] is not k1["filho"] and Path(kb["filho"].arquivo).resolve() == b.resolve()
    # gate fecha depois de ter aberto: este pedido e descartavel; nada novo e criado
    _, kf = _p(g, m, len(m.chamadas), "V5", caminho_ifc=a, revisao=2, revisao_salva=1)
    assert kf.get("filho") is None and len(espia.instancias) == 2
    # nada vaza em opcoes
    for op, _ in m.chamadas:
        assert not ({"filho", "filho_persistente", "revisao", "revisao_salva", "__filho__"} & set(op)), op

    # podar a cada pedir (so ha filhos a partir do 1o aberto)
    antes = espia.n("podar")
    _p(g, m, len(m.chamadas), "V6", caminho_ifc=a, **aberto)
    assert espia.n("podar") - antes >= 2, "podar() de todos os filhos a cada pedir"

    # invalidar (todas as formas) e salvar matam todos; o objeto fica
    for chamada in (lambda: g.invalidar(), lambda: g.invalidar(object()), lambda: g.invalidar(None, [1, 2])):
        antes = [espia.n("invalidar", i) for i in espia.instancias]
        chamada()
        assert [espia.n("invalidar", i) - x for i, x in zip(espia.instancias, antes)] == [1, 1]
    antes = [espia.n("salvar", i) for i in espia.instancias]
    g.salvar()
    assert [espia.n("salvar", i) - x for i, x in zip(espia.instancias, antes)] == [1, 1]
    _, kr = _p(g, m, len(m.chamadas), "V7", caminho_ifc=a, **aberto)
    assert kr["filho"] is k1["filho"] and len(espia.instancias) == 2

    # fechar: poda e fecha todos, nesta ordem; idempotente
    ev0 = len(espia.eventos)
    g.fechar()
    ev = espia.eventos[ev0:]
    for i in espia.instancias:
        nomes = [x for x, j in ev if j is i]
        assert "fechar" in nomes, "filho nao fechado no fechar do gerente"
        assert "podar" in nomes and nomes.index("podar") < nomes.index("fechar")
    g.fechar()

    # encerrar tambem fecha (nenhum caminho de saida deixa filho)
    m2 = Motor()
    g2 = _gerente(cls, m2, filho_persistente=True)
    _, kk = _p(g2, m2, 0, "W1", caminho_ifc=a, **aberto)
    n0 = espia.n("fechar", kk["filho"])
    g2.encerrar()
    assert espia.n("fechar", kk["filho"]) == n0 + 1


def test_referencia_boa_passa(app, espia, tmp_path):
    _unit(_Ref, espia, tmp_path)


@pytest.mark.parametrize("nome", ["gate_fechado_cria", "nao_fecha", "compartilha", "chave_ignorada", "invalidar_sem_matar", "sem_podar", "salvar_sem_matar"])
def test_mutante_e_derrubado(nome, app, espia, tmp_path):
    with pytest.raises(AssertionError):
        _unit(_mut(nome), espia, tmp_path)


def test_real(app, espia, tmp_path):
    """HOJE FALHA (TypeError: `filho_persistente` inexistente). Passa quando o gerente cumprir o contrato."""
    _unit(GerenteDesenho, espia, tmp_path)


def test_assinatura_publica():
    import inspect
    p = inspect.signature(GerenteDesenho.__init__).parameters["filho_persistente"]
    assert p.default is False and p.kind is inspect.Parameter.KEYWORD_ONLY
    for nome in ("salvar", "fechar"):
        assert callable(getattr(GerenteDesenho, nome)), nome
    for f in (selecao.selecionar, corte.gerar_corte, planta.gerar_planta):
        q = inspect.signature(f).parameters["filho"]
        assert q.default is None and q.kind is inspect.Parameter.KEYWORD_ONLY


# ------------------------------------------------------------------ (b) motor padrao e gerar_* com filho falso
def _args_motor(**kw):
    return dict(cancelar=threading.Event(), progresso=lambda m: None, cache=None, **kw)


@pytest.mark.parametrize("tipo,modulo,nome", [("corte", "openbim_app.desenho.corte", "gerar_corte"), ("planta", "openbim_app.desenho.planta", "gerar_planta")])
def test_motor_padrao_repassa_filho(tipo, modulo, nome, monkeypatch):
    visto = []

    def falso(ifc, guid, **kw):
        visto.append(kw)
        return SimpleNamespace(svg="<svg/>", n_paths=0, tempos={}, caixas=(), em_cache=(), pesados=(), pedido={})

    monkeypatch.setattr(f"{modulo}.{nome}", falso)
    sentinela = object()
    G._motor_padrao(tipo, object(), "G", {}, **_args_motor(filho=sentinela))
    assert visto[-1]["filho"] is sentinela
    G._motor_padrao(tipo, object(), "G", {}, **_args_motor())
    assert visto[-1].get("filho") is None


class FilhoFalso:
    """Filho em processo: delega ao executor local, anota as ops. Mesmo formato de retorno do `FilhoPersistente.executar`."""

    def __init__(self):
        self.ops = []

    def executar(self, pedido, *, cancelar=None, limite_s=180, ao_fase=None):
        self.ops.append(pedido.get("op"))
        return A._tratar_resposta(local.executar(copy.deepcopy(pedido)))


@pytest.fixture
def cena(tmp_path):
    exigir()
    f, pavs, _g = B.modelo("IFC4", n_pav=1)
    gp = B.planta(f, pavs[0])
    gc = C.corte(f)
    salvo = tmp_path / "salvo.ifc"
    f.write(str(salvo))
    return f, gp, gc, salvo


def test_gerar_corte_e_planta_usam_o_filho_e_dao_o_mesmo_svg(cena):
    f, gp, gc, salvo = cena
    ref_c = corte.gerar_corte(f, gc, executor=local.executar, caminho_ifc=salvo).svg
    ref_p = planta.gerar_planta(f, gp, executor=local.executar, caminho_ifc=salvo).svg
    ff = FilhoFalso()
    assert corte.gerar_corte(f, gc, caminho_ifc=salvo, filho=ff).svg == ref_c
    assert "caixas" in ff.ops and "desenho" in ff.ops, f"selecao e desenho devem passar pelo filho: {ff.ops}"
    ff = FilhoFalso()
    assert planta.gerar_planta(f, gp, caminho_ifc=salvo, filho=ff).svg == ref_p
    assert "desenho" in ff.ops
    ff = FilhoFalso()
    selecao.selecionar(f, gc, caminho_ifc=salvo, filho=ff)
    assert ff.ops == ["caixas"]


@pytest.mark.parametrize("ruim", [object(), "x", 5])
def test_filho_invalido_levanta_typeerror(cena, ruim):
    f, gp, gc, salvo = cena
    for chamada in (lambda: corte.gerar_corte(f, gc, filho=ruim), lambda: planta.gerar_planta(f, gp, filho=ruim), lambda: selecao.selecionar(f, gc, filho=ruim)):
        with pytest.raises(TypeError):
            chamada()


# ------------------------------------------------------------------ (c) ponta a ponta com processo real
def _vivo(pid):
    if sys.platform == "win32":  # os.kill(pid, 0) nao serve no Windows (WinError 87)
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
    try:  # zumbi conta como morto
        return Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0] != "Z"
    except OSError:
        return True


def _esperar_morto(pid, s=10.0):
    fim = time.monotonic() + s
    while time.monotonic() < fim and _vivo(pid):
        time.sleep(0.05)
    return not _vivo(pid)


def _esperar(g, chaves, s=180.0):
    """Roda o loop Qt ate `pronto` ou `falhou` de todas as `chaves`. Devolve {chave: ("pronto", dados) | ("falhou", msg)}."""
    res, loop = {}, QEventLoop()

    def fim(tipo):
        def f(c, d):
            res[c] = (tipo, d)
            if all(k in res for k in chaves):
                loop.quit()
        return f

    g.pronto.connect(fim("pronto"))
    g.falhou.connect(fim("falhou"))
    QTimer.singleShot(int(s * 1000), loop.quit)
    loop.exec()
    return res


@pytest.fixture(scope="module")
def trilha(app, tmp_path_factory):
    """Uma vez: 3 vistas de corte no mesmo modelo salvo, pelo gerente real com a chave ligada e o motor padrao (processo real).
    Passos: P1 e P2 (vistas diferentes), P3 cancelado no meio (gancho em `_ler`), P4 = a vista de P3 de novo, fechar."""
    exigir()
    tmp = tmp_path_factory.mktemp("g4c")
    f, _pavs, _g = B.modelo("IFC4", n_pav=1)
    gids = [C.corte(f, nome="C1"), C.corte(f, nome="C2", olhar="-Y"), C.corte(f, nome="C3", origem=(-0.5, 0.3, -0.5))]
    salvo = tmp / "salvo.ifc"
    f.write(str(salvo))
    from openbim_app.desenho.cache import CacheDesenho
    mp = pytest.MonkeyPatch()
    esp = Espia(mp)
    gatilho = {"armado": False, "chave": None, "g": None}
    orig_ler = FilhoPersistente._ler

    def ler(self, *a, **k):
        if gatilho["armado"]:
            gatilho["armado"] = False
            fim = time.monotonic() + 10
            while gatilho["chave"] is None and time.monotonic() < fim:
                time.sleep(0.01)
            gatilho["g"].cancelar(gatilho["chave"])
        return orig_ler(self, *a, **k)

    mp.setattr(FilhoPersistente, "_ler", ler)
    try:
        ref = [corte.gerar_corte(f, gid, caminho_ifc=salvo, motor_visivel=True).svg for gid in gids]  # filho descartavel de hoje
        g = GerenteDesenho(CacheDesenho(tmp / "cache"), filho_persistente=True)
        gatilho["g"] = g
        kw = dict(caminho_ifc=salvo, revisao=1, revisao_salva=1)
        out = {"ref": ref, "esp": esp}
        res = {}
        for i in (0, 1):
            c = g.pedir("corte", f, gids[i], **kw)
            res.update(_esperar(g, [c]))
            out[f"c{i}"] = res[c]
            out[f"pid{i}"] = esp.pids[-1][1] if esp.pids else None
        # P3: cancelado no meio (o filho ja esta vivo)
        out["instancias_antes"] = len(esp.instancias)
        gatilho["armado"], gatilho["chave"] = True, None
        c3 = g.pedir("corte", f, gids[2], **kw)
        gatilho["chave"] = c3
        loop = QEventLoop()
        QTimer.singleShot(8000, loop.quit)  # tempo para o cancelamento agir; nenhum pronto/falhou pode chegar
        extra = []
        g.pronto.connect(lambda c, d: extra.append(c))
        g.falhou.connect(lambda c, d: extra.append(c))
        loop.exec()
        out["emitiu_cancelado"] = c3 in extra
        inst = esp.instancias[0]
        out["pid_apos_cancelar"] = inst.pid
        # P4: mesma vista, de novo
        c4 = g.pedir("corte", f, gids[2], **kw)
        res.update(_esperar(g, [c4]))
        out["c3"] = res[c4]
        out["pid3"] = inst.pid
        out["instancias_fim"] = len(esp.instancias)
        out["pids_vistos"] = [p for _, p in esp.pids if p]
        g.fechar()
        out["pid_apos_fechar"] = inst.pid
        out["inst"] = inst
        yield out
    finally:
        g.fechar() if "g" in locals() else None
        mp.undo()
        for _, p in esp.pids:
            if p and _vivo(p):
                try:
                    os.kill(p, 9)
                except OSError:
                    pass


def test_real_dois_cortes_de_vistas_diferentes_mesmo_pid(trilha):
    assert trilha["c0"][0] == "pronto" and trilha["c1"][0] == "pronto", (trilha["c0"], trilha["c1"])
    assert trilha["pid0"] and trilha["pid0"] == trilha["pid1"], f"filho nao reaproveitado: {trilha['pid0']} vs {trilha['pid1']}"
    assert trilha["instancias_antes"] == 1


def test_real_svg_igual_ao_descartavel_byte_a_byte(trilha):
    for i in (0, 1):
        assert trilha[f"c{i}"][1]["svg"] == trilha["ref"][i], f"vista {i}: SVG do filho persistente difere do descartavel"
    assert trilha["c3"][0] == "pronto" and trilha["c3"][1]["svg"] == trilha["ref"][2]


def test_real_cancelar_mata_o_filho_e_o_seguinte_renasce(trilha):
    assert trilha["emitiu_cancelado"] is False, "pedido cancelado nao pode emitir pronto/falhou"
    assert trilha["pid_apos_cancelar"] is None, "cancelar no meio do pedido deve matar o filho"
    assert _esperar_morto(trilha["pid1"], 10), "processo do pedido cancelado continua vivo"
    assert trilha["pid3"] and trilha["pid3"] != trilha["pid1"], "o pedido seguinte deve subir um filho novo"
    assert trilha["instancias_fim"] == 1, "o objeto filho e o mesmo; so o processo renasce"


def test_real_fechar_nao_deixa_orfao(trilha):
    assert trilha["pid_apos_fechar"] is None
    assert _esperar_morto(trilha["pid3"], 10)
    assert all(_esperar_morto(p, 10) for p in set(trilha["pids_vistos"]))
    assert trilha["esp"].n("fechar", trilha["inst"]) >= 1
