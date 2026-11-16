# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oraculo F0-S06-T19e2: o gerente reaproveita as caixas entre desenhos.
Cartao: docs/state/cards/F0-S06/F0-S06-T19e2-sessao-de-selecao.md.

CONTRATO:
A) `corte.gerar_corte(..., sessao_selecao=None)` e `planta.gerar_planta(..., sessao_selecao=None)` (keyword-only) repassam a
   `selecao.selecionar(sessao=sessao_selecao)`; valor que nao e None nem SessaoSelecao => TypeError ou ValueError.
B) `GerenteDesenho.pedir(tipo, ifc, vista_guid, *, revisao=None, **opcoes)`: `revisao` e consumida pelo gerente (o motor nao a recebe
   em `opcoes`). Com revisao: UMA SessaoSelecao por modelo (id(ifc)), reutilizada enquanto revisao == a ultima vista; nova quando muda;
   passada ao motor como kwarg `sessao_selecao` (so se o motor aceitar). Sem revisao: nao passa sessao.
   `invalidar(ifc=None, ids=None)`: sem ifc descarta todas as sessoes; com ifc so a dele; com ids chama SessaoSelecao.invalidar(ids).
C) `Historico.revisao`: int somente leitura; 0 no inicio; sobe estritamente ao fim de transacao (ok ou abortada), desfazer, refazer
   e fora_do_historico; nao sobe em leitura; durante a transacao ja difere da anterior.
D) Fiacao ponta a ponta com o gerente real e `_motor_padrao` trocado por falso.
"""
import inspect
import os
import threading
import time
from types import SimpleNamespace

import pytest
import s06_t04_aux as A
import s06_t07e_aux as T
from s05_conteudo_aux import _limpa, exigir  # noqa: F401  (fixture autouse; poe `geometria/` no sys.path via T)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QtCore = pytest.importorskip("PySide6.QtCore")
from PySide6.QtCore import QCoreApplication, QEventLoop, QTimer  # noqa: E402

from openbim_app.desenho import corte, gerente, planta, selecao  # noqa: E402
from openbim_app.desenho.selecao import SessaoSelecao  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QCoreApplication.instance() or QCoreApplication([])


def girar(cond, ms=3000):
    loop, t, fim = QEventLoop(), QTimer(), time.monotonic() + ms / 1000
    t.setInterval(5)

    def tic():
        if cond() or time.monotonic() > fim:
            loop.quit()
    t.timeout.connect(tic)
    t.start()
    loop.exec()
    t.stop()
    return cond()


# ---------------------------------------------------------------- A) corte e planta

class Espia:
    """Executor que registra os pedidos `caixas` (ids pedidos) e delega ao executor real."""

    def __init__(self):
        self.caixas = []

    def __call__(self, pedido):
        from obim_geometria import local
        if pedido.get("op") == "caixas":
            self.caixas.append([int(e[0]) for e in pedido["elementos"]])
        return local.executar(pedido)


def test_assinaturas_keyword_only_default_none():
    for fn in (corte.gerar_corte, planta.gerar_planta):
        p = inspect.signature(fn).parameters.get("sessao_selecao")
        assert p is not None, f"{fn.__name__} deve declarar sessao_selecao"
        assert p.kind == inspect.Parameter.KEYWORD_ONLY and p.default is None


def test_corte_com_sessao_compartilhada_nao_repede_caixas():
    exigir()
    f, d = T.modelo()
    esp, sessao = Espia(), SessaoSelecao()
    corte.gerar_corte(f, d["vc"], executor=esp, sessao_selecao=sessao)
    n1 = esp.caixas[0] if esp.caixas else []
    assert n1, "a 1a geracao precisa pedir caixas"
    corte.gerar_corte(f, d["vc"], executor=esp, sessao_selecao=sessao)
    pedidos2 = [i for p in esp.caixas[1:] for i in p]
    assert len(pedidos2) < len(n1) and not (set(pedidos2) & set(n1)), (
        f"2a geracao nao deve pedir de novo o que a sessao ja guarda: 1a={n1} 2a={pedidos2}")


def test_corte_sem_sessao_pede_o_mesmo_conjunto_duas_vezes():
    exigir()
    f, d = T.modelo()
    esp = Espia()
    corte.gerar_corte(f, d["vc"], executor=esp)
    corte.gerar_corte(f, d["vc"], executor=esp, sessao_selecao=None)
    assert len(esp.caixas) == 2 and sorted(esp.caixas[0]) == sorted(esp.caixas[1]) and esp.caixas[0]


def test_corte_sessao_invalidada_pede_so_os_ids_invalidados():
    exigir()
    f, d = T.modelo()
    esp, sessao = Espia(), SessaoSelecao()
    corte.gerar_corte(f, d["vc"], executor=esp, sessao_selecao=sessao)
    alvo = d["P"].id()
    assert alvo in esp.caixas[0]
    sessao.invalidar([alvo])
    corte.gerar_corte(f, d["vc"], executor=esp, sessao_selecao=sessao)
    assert [i for p in esp.caixas[1:] for i in p] == [alvo]


@pytest.mark.parametrize("ruim", [object(), 1, "sessao", {}, True])
def test_corte_sessao_invalida(ruim):
    exigir()
    assert "sessao_selecao" in inspect.signature(corte.gerar_corte).parameters  # senao o TypeError seria so de kwarg desconhecido
    f, d = T.modelo()
    with pytest.raises((TypeError, ValueError)):
        corte.gerar_corte(f, d["vc"], executor=Espia(), sessao_selecao=ruim)


@pytest.mark.parametrize("ruim", [object(), 1, "sessao", {}, True])
def test_planta_sessao_invalida(ruim):
    exigir()
    assert "sessao_selecao" in inspect.signature(planta.gerar_planta).parameters
    f, d = T.modelo()
    with pytest.raises((TypeError, ValueError)):
        planta.gerar_planta(f, d["vp"], executor=Espia(), sessao_selecao=ruim)


def _espiar_selecionar(monkeypatch):
    from obim_geometria import local
    vistos = []
    real = selecao.selecionar

    def espia(*a, **k):
        vistos.append(k.get("sessao"))
        k.setdefault("executor", local.executar)
        return real(*a, **k)
    monkeypatch.setattr(selecao, "selecionar", espia)
    return vistos


def test_planta_repassa_a_sessao_ao_selecionar(monkeypatch):
    exigir()
    from obim_geometria import local
    f, d = T.modelo()
    vistos, sessao = _espiar_selecionar(monkeypatch), SessaoSelecao()
    planta.gerar_planta(f, d["vp"], executor=local.executar, sessao_selecao=sessao)
    assert vistos == [sessao]
    planta.gerar_planta(f, d["vp"], executor=local.executar)
    assert vistos[1] is None


def test_corte_repassa_a_sessao_ao_selecionar(monkeypatch):
    exigir()
    f, d = T.modelo()
    vistos, sessao = _espiar_selecionar(monkeypatch), SessaoSelecao()
    corte.gerar_corte(f, d["vc"], executor=Espia(), sessao_selecao=sessao)
    assert vistos == [sessao]


# ---------------------------------------------------------------- B) gerente

class Motor:
    """Motor falso: registra (tipo, guid, opcoes, sessao_selecao) e devolve na hora."""

    def __init__(self):
        self.chamadas = []

    def __call__(self, tipo, ifc, guid, opcoes, *, cancelar, progresso, sessao_selecao=None):
        self.chamadas.append(SimpleNamespace(tipo=tipo, ifc=ifc, guid=guid, opcoes=dict(opcoes), sessao=sessao_selecao))
        return {"svg": "<svg/>", "n_paths": 0}


class MotorSemSessao:  # motor customizado antigo: nao conhece sessao_selecao
    def __init__(self):
        self.chamadas = []

    def __call__(self, tipo, ifc, guid, opcoes, *, cancelar, progresso):
        self.chamadas.append(dict(opcoes))
        return {"svg": "<svg/>", "n_paths": 0}


class MotorKw:  # aceita **kw: pode receber sessao_selecao
    def __init__(self):
        self.chamadas = []

    def __call__(self, tipo, ifc, guid, opcoes, *, cancelar, progresso, **kw):
        self.chamadas.append(kw)
        return {"svg": "<svg/>", "n_paths": 0}


@pytest.fixture
def gerente_com(app):
    criados = []

    def montar(motor):
        g = gerente.GerenteDesenho(motor=motor)
        criados.append(g)
        return g
    yield montar
    for g in criados:
        g.encerrar()


def _pedir(g, motor, n, *a, **k):
    """Pede e espera o motor ter n chamadas; devolve a ultima."""
    g.pedir(*a, **k)
    assert girar(lambda: len(motor.chamadas) >= n), "motor nao foi chamado"
    return motor.chamadas[n - 1]


def test_revisao_igual_reaproveita_sessao_e_muda_troca(gerente_com):
    m = Motor()
    g, ifc = gerente_com(m), SimpleNamespace()
    c1 = _pedir(g, m, 1, "corte", ifc, "v1", revisao=1)
    c2 = _pedir(g, m, 2, "planta", ifc, "v2", revisao=1)  # outra vista, mesmo modelo e revisao
    c3 = _pedir(g, m, 3, "corte", ifc, "v1", revisao=2)
    c4 = _pedir(g, m, 4, "corte", ifc, "v1", revisao=2)
    assert isinstance(c1.sessao, SessaoSelecao)
    assert c2.sessao is c1.sessao
    assert isinstance(c3.sessao, SessaoSelecao) and c3.sessao is not c1.sessao
    assert c4.sessao is c3.sessao


def test_revisao_nao_chega_ao_motor_como_opcao(gerente_com):
    m = Motor()
    g = gerente_com(m)
    c = _pedir(g, m, 1, "corte", SimpleNamespace(), "v1", revisao=7, ocultar_secundarias=False)
    assert "revisao" not in c.opcoes and c.opcoes == {"ocultar_secundarias": False}


def test_sem_revisao_nao_passa_sessao(gerente_com):
    m = Motor()
    g, ifc = gerente_com(m), SimpleNamespace()
    assert _pedir(g, m, 1, "corte", ifc, "v1").sessao is None
    assert _pedir(g, m, 2, "corte", ifc, "v1", revisao=None).sessao is None
    assert _pedir(g, m, 3, "corte", ifc, "v1", revisao=1).sessao is not None
    assert _pedir(g, m, 4, "corte", ifc, "v1").sessao is None  # sem revisao volta a nao reaproveitar


def test_modelos_diferentes_tem_sessoes_diferentes(gerente_com):
    m = Motor()
    g, a, b = gerente_com(m), SimpleNamespace(), SimpleNamespace()
    ca = _pedir(g, m, 1, "corte", a, "v1", revisao=1)
    cb = _pedir(g, m, 2, "corte", b, "v2", revisao=1)
    assert ca.sessao is not None and cb.sessao is not None and ca.sessao is not cb.sessao
    # mudar a revisao de um modelo nao mexe na sessao do outro
    cb2 = _pedir(g, m, 3, "corte", b, "v2", revisao=2)
    ca2 = _pedir(g, m, 4, "corte", a, "v1", revisao=1)
    assert cb2.sessao is not cb.sessao and ca2.sessao is ca.sessao


def test_motor_customizado_sem_o_parametro_nao_quebra(gerente_com, app):
    m = MotorSemSessao()
    g = gerente_com(m)
    falhas = []
    g.falhou.connect(lambda c, msg: falhas.append(msg))
    g.pedir("corte", SimpleNamespace(), "v1", revisao=3)
    assert girar(lambda: m.chamadas or falhas)
    assert not falhas and m.chamadas == [{}]


def test_motor_customizado_com_kwargs_recebe_a_sessao(gerente_com):
    m = MotorKw()
    g = gerente_com(m)
    g.pedir("corte", SimpleNamespace(), "v1", revisao=3)
    assert girar(lambda: m.chamadas)
    assert isinstance(m.chamadas[0].get("sessao_selecao"), SessaoSelecao)


def test_invalidar_so_o_modelo(gerente_com):
    m = Motor()
    g, a, b = gerente_com(m), SimpleNamespace(), SimpleNamespace()
    sa = _pedir(g, m, 1, "corte", a, "v1", revisao=1).sessao
    sb = _pedir(g, m, 2, "corte", b, "v2", revisao=1).sessao
    g.invalidar(ifc=a)
    assert _pedir(g, m, 3, "corte", a, "v1", revisao=1).sessao is not sa
    assert _pedir(g, m, 4, "corte", b, "v2", revisao=1).sessao is sb


def test_invalidar_tudo(gerente_com):
    m = Motor()
    g, a, b = gerente_com(m), SimpleNamespace(), SimpleNamespace()
    sa = _pedir(g, m, 1, "corte", a, "v1", revisao=1).sessao
    sb = _pedir(g, m, 2, "corte", b, "v2", revisao=1).sessao
    g.invalidar()
    assert _pedir(g, m, 3, "corte", a, "v1", revisao=1).sessao is not sa
    assert _pedir(g, m, 4, "corte", b, "v2", revisao=1).sessao is not sb


def test_invalidar_ids_troca_por_copia_sem_esses_ids(gerente_com):
    m = Motor()
    g, a = gerente_com(m), SimpleNamespace()
    s = _pedir(g, m, 1, "corte", a, "v1", revisao=1).sessao
    s._caixas.update({5: [0.0] * 6, 6: [1.0] * 6, 7: None})
    s._erros.update({5: ["x"], 6: ["y"]})
    g.invalidar(ifc=a, ids=[5, 7])
    # a instancia antiga nao e alterada (pedido em voo pode ainda grava-la)
    assert set(s._caixas) == {5, 6, 7} and set(s._erros) == {5, 6}
    n = _pedir(g, m, 2, "corte", a, "v1", revisao=1).sessao
    assert n is not s and isinstance(n, SessaoSelecao)
    assert n._caixas == {6: [1.0] * 6} and n._erros == {6: ["y"]}
    # copia independente: gravar numa nao afeta a outra
    n._caixas[9] = [2.0] * 6
    n._erros[8] = ["w"]  # dict.copy() e raso: so os dicionarios sao independentes
    assert 9 not in s._caixas and 8 not in s._erros


def test_invalidar_ids_copia_tambem_os_erros(gerente_com):
    m = Motor()
    g, a = gerente_com(m), SimpleNamespace()
    s = _pedir(g, m, 1, "corte", a, "v1", revisao=1).sessao
    s._erros.update({1: ["a"], 2: ["b"], 3: ["c"]})
    g.invalidar(ifc=a, ids=[2])
    n = _pedir(g, m, 2, "corte", a, "v1", revisao=1).sessao
    assert n is not s and n._erros == {1: ["a"], 3: ["c"]} and n._caixas == {}
    assert s._erros == {1: ["a"], 2: ["b"], 3: ["c"]}


def test_invalidar_sem_sessao_nao_levanta(gerente_com):
    g = gerente_com(Motor())
    g.invalidar()
    g.invalidar(ifc=SimpleNamespace())
    g.invalidar(ifc=SimpleNamespace(), ids=[1, 2])


# ---------------------------------------------------------------- C) Historico.revisao

_SEQ = __import__("itertools").count()  # id unico (o relogio do Windows repete valores)


def _tx(s, ok=True):
    def fn(t):
        t.lado.criar("viewports", f"vp{next(_SEQ)}", {})
        if not ok:
            raise ZeroDivisionError
    if ok:
        return s.tx(fn)
    with pytest.raises(ZeroDivisionError):
        s.tx(fn)


def test_historico_revisao_sobe_em_toda_mudanca():
    exigir()
    from s06_t04_sessao_aux import Sessao
    s = Sessao(A.novo_arquivo("IFC4"))
    try:
        h = s.h
        r0 = h.revisao
        assert r0 == 0 and isinstance(r0, int)
        assert h.revisao == r0 and h.pode_desfazer is False  # leitura nao sobe
        with pytest.raises(AttributeError):
            h.revisao = 5
        vistos = [r0]

        _tx(s)
        vistos.append(h.revisao)
        _tx(s, ok=False)
        vistos.append(h.revisao)
        assert s.desfazer() is not None
        vistos.append(h.revisao)
        assert s.refazer() is not None
        vistos.append(h.revisao)
        with s.s.escrever() as esc, h.fora_do_historico(esc):
            pass
        vistos.append(h.revisao)
        assert all(b > a for a, b in zip(vistos, vistos[1:])), f"revisao deve subir estritamente: {vistos}"
        assert all(isinstance(v, int) for v in vistos)
        h.pode_desfazer, h.pode_refazer, h.quebrado  # leituras
        assert h.revisao == vistos[-1]
    finally:
        s.encerrar()


def test_historico_revisao_ja_difere_durante_a_transacao():
    exigir()
    from s06_t04_sessao_aux import Sessao
    s = Sessao(A.novo_arquivo("IFC4"))
    try:
        antes, dentro = s.h.revisao, []

        def fn(t):
            t.lado.criar("viewports", "vp1", {})
            dentro.append(s.h.revisao)
        s.tx(fn)
        assert dentro and dentro[0] != antes, "revisao dentro da transacao deve diferir da anterior (conservador)"
        assert s.h.revisao != antes
    finally:
        s.encerrar()


# ---------------------------------------------------------------- D) fiacao ponta a ponta

def test_motor_padrao_repassa_sessao_a_gerar_corte_e_planta(monkeypatch):
    sessao, vistos = SessaoSelecao(), {}
    res = SimpleNamespace(svg="<svg/>", n_paths=0, tempos={}, caixas=(), em_cache=(), pesados=(), pedido={})

    def espia(nome):
        def f(ifc, guid, **k):
            vistos[nome] = k
            return res
        return f
    monkeypatch.setattr(corte, "gerar_corte", espia("corte"))
    monkeypatch.setattr(planta, "gerar_planta", espia("planta"))
    for tipo in ("corte", "planta"):
        gerente._motor_padrao(tipo, None, "g", {}, cancelar=threading.Event(), progresso=lambda m: None,
                              cache=None, sessao_selecao=sessao)
        assert vistos[tipo].get("sessao_selecao") is sessao, f"{tipo}: sessao deve chegar ao gerar_*"
        vistos.clear()
        gerente._motor_padrao(tipo, None, "g", {}, cancelar=threading.Event(), progresso=lambda m: None, cache=None)
        assert vistos[tipo].get("sessao_selecao") is None
        vistos.clear()


def test_ponta_a_ponta_gerente_real_com_motor_padrao_falso(monkeypatch, app):
    m = Motor()

    def falso(tipo, ifc, vista_guid, opcoes, *, cancelar, progresso, cache=None, previa=None, sessao_selecao=None):
        return m(tipo, ifc, vista_guid, opcoes, cancelar=cancelar, progresso=progresso, sessao_selecao=sessao_selecao)
    monkeypatch.setattr(gerente, "_motor_padrao", falso)
    g, ifc = gerente.GerenteDesenho(cache=object()), SimpleNamespace()
    try:
        c1 = _pedir(g, m, 1, "corte", ifc, "v1", revisao=1)
        c2 = _pedir(g, m, 2, "corte", ifc, "v1", revisao=1)
        c3 = _pedir(g, m, 3, "corte", ifc, "v1", revisao=2)
        assert isinstance(c1.sessao, SessaoSelecao)
        assert c2.sessao is c1.sessao
        assert c3.sessao is not c1.sessao and isinstance(c3.sessao, SessaoSelecao)
        assert "revisao" not in c1.opcoes
        assert _pedir(g, m, 4, "corte", ifc, "v1").sessao is None
    finally:
        g.encerrar()


# ---------------------------------------------------------------- E) reprovacao Argon: reuso de id, invalidar em voo, cache, Historico

import gc  # noqa: E402
import weakref  # noqa: E402


def _guardadas(g):
    """Sessoes que o gerente ainda guarda em qualquer dict proprio (sem depender do nome do atributo)."""
    achadas = []
    for v in vars(g).values():
        if isinstance(v, dict):
            for x in v.values():
                for y in (x if isinstance(x, tuple) else (x,)):
                    if isinstance(y, SessaoSelecao):
                        achadas.append(y)
    return achadas


class MotorSemIfc:
    """Como Motor, mas NAO guarda o ifc (para o teste de referencia fraca)."""

    def __init__(self):
        self.sessoes = []

    def __call__(self, tipo, ifc, guid, opcoes, *, cancelar, progresso, sessao_selecao=None):
        self.sessoes.append(sessao_selecao)
        return {"svg": "<svg/>", "n_paths": 0}


def test_colisao_de_id_nunca_entrega_a_sessao_de_outro_modelo(gerente_com, monkeypatch):
    # forca id() igual para objetos distintos: o gerente precisa conferir identidade, nao so o id
    monkeypatch.setattr(gerente, "id", lambda o: 12345, raising=False)
    m = MotorSemIfc()
    g, m1, m2 = gerente_com(m), SimpleNamespace(), SimpleNamespace()
    g.pedir("corte", m1, "v1", revisao=1)
    assert girar(lambda: len(m.sessoes) >= 1)
    g.pedir("corte", m2, "v2", revisao=1)
    assert girar(lambda: len(m.sessoes) >= 2)
    assert m.sessoes[0] is not None and m.sessoes[1] is not None and m.sessoes[1] is not m.sessoes[0]


def test_colisao_de_id_com_o_primeiro_modelo_morto(gerente_com, monkeypatch):
    monkeypatch.setattr(gerente, "id", lambda o: 12345, raising=False)
    m = MotorSemIfc()
    g, m1 = gerente_com(m), SimpleNamespace()
    g.pedir("corte", m1, "v1", revisao=1)
    assert girar(lambda: len(m.sessoes) >= 1 and not g._threads)
    del m1
    gc.collect()
    g.pedir("corte", SimpleNamespace(), "v2", revisao=1)
    assert girar(lambda: len(m.sessoes) >= 2)
    assert m.sessoes[1] is not m.sessoes[0]


def test_gerente_nao_segura_o_modelo_e_solta_a_sessao(gerente_com):
    class Modelo:  # SimpleNamespace nao aceita weakref
        pass
    m = MotorSemIfc()
    g, ifc = gerente_com(m), Modelo()
    ref = weakref.ref(ifc)
    g.pedir("corte", ifc, "v1", revisao=1)
    assert girar(lambda: len(m.sessoes) >= 1 and not g._threads)
    assert len(_guardadas(g)) == 1
    del ifc
    gc.collect()
    assert ref() is None, "o gerente nao pode manter referencia forte ao modelo"
    assert _guardadas(g) == [], "a entrada do modelo morto deve sumir do dicionario de sessoes"


class MotorPortao:
    """A 1a chamada espera o portao; as demais voltam na hora. Registra a sessao de cada chamada."""

    def __init__(self):
        self.sessoes, self.portao = [], threading.Event()

    def __call__(self, tipo, ifc, guid, opcoes, *, cancelar, progresso, sessao_selecao=None):
        self.sessoes.append(sessao_selecao)
        if len(self.sessoes) == 1:
            self.portao.wait(4)
        return {"svg": "<svg/>", "n_paths": 0}


def test_invalidar_ids_com_pedido_em_voo_troca_a_sessao(gerente_com):
    m = MotorPortao()
    g, ifc = gerente_com(m), SimpleNamespace()
    try:
        g.pedir("corte", ifc, "v1", revisao=1)
        assert girar(lambda: len(m.sessoes) >= 1)
        em_voo = m.sessoes[0]
        assert isinstance(em_voo, SessaoSelecao)
        g.invalidar(ifc=ifc, ids=[5])
        g.pedir("corte", ifc, "v2", revisao=1)
        assert girar(lambda: len(m.sessoes) >= 2)
        assert m.sessoes[1] is not em_voo, "gravacao tardia do pedido velho nao pode contaminar o proximo"
    finally:
        m.portao.set()


class CacheFalso:
    def __init__(self):
        self.dados = {}

    def obter(self, chave):
        return self.dados.get(chave)

    def guardar(self, chave, dados):
        self.dados[chave] = dados
        return True


def _chave(tipo, ifc, guid, opcoes):
    return f"{tipo}|{guid}|{opcoes.get('x')}"


def test_cache_hit_com_revisao_nova_descarta_a_sessao(app):
    m, cache, ifc = MotorSemIfc(), CacheFalso(), SimpleNamespace()
    g = gerente.GerenteDesenho(cache, motor=m, chave_estado=_chave)
    try:
        g.pedir("corte", ifc, "v1", x=1, revisao=1)
        assert girar(lambda: m.sessoes and cache.dados and not g._threads)
        s1 = m.sessoes[0]
        assert isinstance(s1, SessaoSelecao)
        g.pedir("corte", ifc, "v1", x=1, revisao=2)  # mesma chave: cache hit, motor nao roda
        girar(lambda: False, 100)
        assert len(m.sessoes) == 1
        assert s1 not in _guardadas(g), "revisao nova deve descartar a sessao velha mesmo com cache hit"
        g.pedir("corte", ifc, "v1", x=2, revisao=2)
        assert girar(lambda: len(m.sessoes) >= 2)
        assert m.sessoes[1] is not s1
    finally:
        g.encerrar()


def test_pedido_ativo_com_revisao_nova_descarta_a_sessao(app):
    m, ifc = MotorPortao(), SimpleNamespace()
    g = gerente.GerenteDesenho(CacheFalso(), motor=m, chave_estado=_chave)
    try:
        g.pedir("corte", ifc, "v1", x=1, revisao=1)
        assert girar(lambda: len(m.sessoes) >= 1)
        s1 = m.sessoes[0]
        g.pedir("corte", ifc, "v1", x=1, revisao=2)  # mesma chave, ainda ativo: devolve a chave
        assert s1 not in _guardadas(g)
        g.pedir("corte", ifc, "v2", x=1, revisao=2)
        assert girar(lambda: len(m.sessoes) >= 2)
        assert m.sessoes[1] is not s1
    finally:
        m.portao.set()
        g.encerrar()


def test_historico_revisao_sobe_em_encerrar():
    exigir()
    from s06_t04_sessao_aux import Sessao
    s = Sessao(A.novo_arquivo("IFC4"))
    r = s.h.revisao
    s.h.encerrar()
    assert s.h.revisao > r


def test_historico_revisao_sobe_em_quebrar():
    exigir()
    from openbim_app.transacao import HistoricoQuebrado
    from s06_t04_sessao_aux import Sessao
    s = Sessao(A.novo_arquivo("IFC4"))
    try:
        r = s.h.revisao
        with pytest.raises(HistoricoQuebrado):
            s.h._quebrar(s.f, "motivo")
        assert s.h.revisao > r
    finally:
        s.encerrar()


def test_historico_revisao_sobe_quando_terceiros_trocam_a_transacao():
    exigir()
    from openbim_app.transacao import HistoricoQuebrado
    from s06_t04_sessao_aux import Sessao
    s = Sessao(A.novo_arquivo("IFC4"))
    try:
        r = s.h.revisao
        with s.s.escrever() as esc:
            s.f.transaction = None  # terceiros trocaram a sentinela
            with pytest.raises(HistoricoQuebrado):
                with s.h.transacao(esc):
                    pass
        assert s.h.quebrado and s.h.revisao > r
    finally:
        s.encerrar()
