# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oraculo F0-S06-T23d: laco do filho com construcao entre pedidos (`persistente.servir(tx, rx, *, construtor=None)`). Nao editar nesta tarefa.
Canal: 2 `multiprocessing.Pipe` reais (o laco usa `rx.poll`); `servir` roda numa thread; `os._exit` vira excecao `BaseException`. Construtor FALSO
(`abrir_banco`, `documento_de`, `fila_inicial`, `priorizar`, `construir_lote`, `rss_mb`; banco falso: `memo_ler`, `gravar_lote`, `fechar`); lote falso dorme
200 ms. Regua de tempo do cartao (1 lote + 200 ms) com folga 2x. Mutantes no fim do arquivo."""
from __future__ import annotations

import json
import multiprocessing
import os
import sqlite3
import sys
import threading
import time

import ifcopenshell
import pytest
from obim_geometria import persistente
from s05_conteudo_aux import _limpa, exigir  # noqa: F401  (fixture autouse e guarda)
from test_s06_t19g3_sem_rastro_oraculo import _est, cena  # noqa: F401  (cena = fixture)

LOTE_S = 0.2


class _Saiu(BaseException):
    def __init__(self, codigo):
        self.codigo = codigo


class Banco:
    def __init__(self, ctor):
        self.c = ctor
    def memo_ler(self, documento, assinatura):
        self.c.memo_lido.append((documento, assinatura))
        return {7: "chave-memo"}
    def gravar_lote(self, ids):
        self.c.eventos.append(("gravar", list(ids)))
    def fechar(self):
        self.c.eventos.append(("fechar",))
        if self.c.fechar_erro:
            raise OSError("fechar falhou")


class Falso:
    def __init__(self, fila, dorme=LOTE_S, rss=123.5, ret=(3, 1, 0), falhar=None, antes=None, em_memoria=False, prior_erro=False, fechar_erro=False):
        self.fila, self.dorme, self.rss, self.ret, self.falhar, self.antes = list(fila), dorme, rss, ret, falhar, antes
        self.eventos, self.memo_lido, self.pastas, self.abertos, self.lotes = [], [], [], [], []
        self.em_memoria, self.prior_erro, self.fechar_erro, self.banco = em_memoria, prior_erro, fechar_erro, Banco(self)

    def abrir_banco(self, pasta):
        self.pastas.append(pasta)
        if self.em_memoria:
            raise ValueError("banco_em_memoria")
        return self.banco

    def documento_de(self, caminho):
        return "doc:" + str(caminho)
    def fila_inicial(self, f):
        self.abertos.append(f)
        return list(self.fila)

    def priorizar(self, fila, primeiro):
        self.eventos.append(("prior", list(primeiro)))
        if self.prior_erro:
            raise RuntimeError("priorizar falhou")
        p = set(primeiro)
        return [i for i in fila if i in p] + [i for i in fila if i not in p]

    def construir_lote(self, f, cache, ids, *, documento, assinatura, memo, threads=None):
        reg = {"ids": list(ids), "documento": documento, "assinatura": assinatura, "memo": dict(memo), "threads": threads, "t": time.monotonic(),
               "cache": cache}
        self.lotes.append(reg)
        self.eventos.append(("lote", reg))
        if self.antes:
            self.antes(f, reg)
        time.sleep(self.dorme)
        if self.falhar:
            self.falhar(len(self.lotes), reg)
        cache.gravar_lote(ids)
        t, r, fa = self.ret
        return {"tesseladas": t, "reaproveitadas": r, "falhas": fa, "gravadas": len(ids), "segundos": self.dorme}

    def rss_mb(self):
        self.eventos.append(("rss",))
        return self.rss(self) if callable(self.rss) else self.rss

    def gravados(self):
        return [i for e in self.eventos if e[0] == "gravar" for i in e[1]]


class Espia:  # conta `poll` da ponta de leitura do laco (D)
    def __init__(self, r):
        self.r, self.polls = r, 0

    def poll(self, *a):
        self.polls += 1
        return self.r.poll(*a)

    def __getattr__(self, nome):
        return getattr(self.r, nome)


class Filho:
    def __init__(self, ctor, mp):
        self.ctor, self.n, self.saida, self.erro, self.enviados, self.ultimo_t = ctor, 0, None, None, set(), 0.0
        r1, self.w1 = multiprocessing.Pipe(False)
        self.rx = r1 = Espia(r1)
        self.r2, w2 = multiprocessing.Pipe(False)

        mp.setattr(os, "_exit", lambda c: (_ for _ in ()).throw(_Saiu(c)))

        def alvo():
            try:
                persistente.servir(w2, r1, construtor=ctor)
            except _Saiu as e:
                self.saida = e.codigo
            except BaseException as e:  # noqa: BLE001
                self.erro = repr(e)

        self.th = threading.Thread(target=alvo, daemon=True)
        self.th.start()
        assert self.ler(10)["tipo"] == "pronto"

    def ler(self, t):
        fim = time.monotonic() + t
        while time.monotonic() < fim:
            if self.r2.poll(0.05):
                m = json.loads(self.r2.recv_bytes())
                if m.get("tipo") != "pronto":
                    assert m.get("tipo") in ("resposta", "fase") and m.get("numero") in self.enviados, f"mensagem nao pedida: {m}"
                return m
            assert self.th.is_alive() or self.saida is not None, f"filho morreu: {self.erro}"
        raise AssertionError("sem mensagem do filho no prazo")

    def pedir(self, op, t=10, numero=None, **campos):
        if numero is None:
            self.n += 1
        n = numero or self.n
        self.n = max(self.n, n)
        self.enviados.add(n)
        t0 = time.monotonic()
        self.w1.send_bytes(json.dumps({"op": op, "numero": n, "protocolo": 1, **campos}).encode())
        while True:
            m = self.ler(t)
            if m["tipo"] == "resposta" and m["numero"] == n:
                self.ultimo_t = time.monotonic() - t0
                return m["dados"]

    def silencio(self, s):
        assert not self.r2.poll(s), "filho mandou mensagem sem pedido"
    def fim(self):
        if self.th.is_alive():
            self.w1.send_bytes(json.dumps({"op": "encerrar"}).encode())
            self.th.join(10)
        assert not self.th.is_alive()


@pytest.fixture
def novo(monkeypatch):
    fs = []

    def f(ctor):
        fs.append(Filho(ctor, monkeypatch))
        return fs[-1]

    yield f
    for x in fs:
        x.fim()


def esperar(cond, t=10):
    fim = time.monotonic() + t
    while time.monotonic() < fim and not cond():
        time.sleep(0.02)
    assert cond(), "condicao nao atendida no prazo"


def estado(fi, arq):
    return fi.pedir("estado_construcao", arquivo=arq)


def sig(arq):
    return f"{os.stat(arq).st_size}:{os.stat(arq).st_mtime_ns}"


def terminar(fi, arq, t=15):
    esperar(lambda: estado(fi, arq)["pendentes"] == 0, t)


# ------------------------------------------------------------------ testes
def test_estado_sem_construcao_e_campos(cena, novo):
    salvo, _ = cena
    ctor = Falso(range(10))
    d = estado(novo(ctor), str(salvo))
    assert d["ativo"] is False and d["pendentes"] == 0 and d["parado"] is None and d["erro"] is None
    assert {"feitos", "tesseladas", "reaproveitadas", "falhas", "lotes", "lote_max_s", "rss_mb"} <= set(d)
    assert ctor.pastas == [] and ctor.lotes == []


def test_construir_responde_antes_do_primeiro_lote_e_passa_parametros(cena, novo, tmp_path):  # mutante 2
    salvo, _ = cena
    ctor = Falso(range(200))
    fi = novo(ctor)
    d = fi.pedir("construir", arquivo=str(salvo), pasta_cache=str(tmp_path), lote_max=4, limite_mb=1000.0, threads=3, t=3)
    assert d == {"aceito": True, "pendentes": 200}, "resposta so depois de um lote (ou da fila)"
    outro = str(tmp_path / "outro.ifc")
    open(outro, "wb").write(open(salvo, "rb").read())
    assert estado(fi, outro)["ativo"] is False and estado(fi, str(salvo))["ativo"] is True  # C: estado de outro arquivo
    esperar(lambda: ctor.lotes)
    l0 = ctor.lotes[0]
    assert ctor.pastas == [str(tmp_path)] and len(ctor.abertos) == 1 and ctor.abertos[0].__class__.__name__ == "file"
    assert l0["ids"] == [0, 1, 2, 3] and l0["documento"] == "doc:" + str(salvo) and l0["threads"] == 3
    assert l0["assinatura"] == sig(salvo) and ctor.memo_lido[0] == ("doc:" + str(salvo), sig(salvo)) and l0["memo"] == {7: "chave-memo"}


def test_banco_em_memoria_recusa(cena, novo, tmp_path):
    salvo, _ = cena
    ctor = Falso(range(10), em_memoria=True)
    fi = novo(ctor)
    assert fi.pedir("construir", arquivo=str(salvo), pasta_cache=str(tmp_path)) == {"aceito": False, "motivo": "banco_em_memoria"}
    assert ctor.lotes == [] and estado(fi, str(salvo))["ativo"] is False


def test_desenho_passa_a_frente_do_lote(cena, novo, tmp_path):  # mutantes 1 e 3
    salvo, pedidos = cena
    est0, ped = _est(ifcopenshell.open(str(salvo))), pedidos["A"]
    el = [i for i, _g in ped["elementos"]]
    assert el
    fila = [900000 + i for i in range(200 - len(el))] + el  # pecas do desenho no fim da fila
    intacto = []
    ctor = Falso(fila, antes=lambda f, reg: intacto.append(_est(f) == est0))
    fi = novo(ctor)
    base_arq = {k: v for k, v in ped.items() if k not in ("op", "protocolo")}
    fi.pedir("desenho", **base_arq)
    fi.pedir("desenho", **base_arq)
    base = fi.ultimo_t  # desenho com o modelo ja aberto, sem construcao
    fi.pedir("construir", arquivo=str(salvo), pasta_cache=str(tmp_path), lote_max=4)
    esperar(lambda: ctor.lotes)
    antes = len(ctor.lotes)
    d = fi.pedir("desenho", **base_arq)
    assert d.get("ok") and d.get("svg")
    # 1 lote em andamento + 200 ms, folga 2x; sem passar a frente a fila inteira levaria ~10 s
    assert fi.ultimo_t <= base + 2 * (LOTE_S + 0.2), f"desenho esperou lotes: {fi.ultimo_t:.2f}s (base {base:.2f}s)"
    esperar(lambda: any(e[0] == "prior" for e in ctor.eventos))
    ev = [e for e in ctor.eventos if e[0] == "prior"]
    assert ev[0][1] == el, "priorizar nao recebeu os ids de `elementos`"
    pos = ctor.eventos.index(ev[0])
    esperar(lambda: any(e[0] == "lote" for e in ctor.eventos[pos:]))
    prox = next(e[1] for e in ctor.eventos[pos:] if e[0] == "lote")
    k = min(4, len(el))
    assert set(prox["ids"][:k]) <= set(el), f"proximo lote nao comeca pelos elementos do desenho: {prox['ids']}"
    assert len(ctor.lotes) < antes + 6 and all(intacto), "modelo alterado quando o lote roda (lote fica fora de _sem_rastro)"


def _memoria(cena, novo, tmp_path, rss, limite_kw, **kw):
    salvo, ctor = cena[0], Falso(range(24), dorme=0.02, rss=rss, **kw)
    fi = novo(ctor)
    fi.pedir("construir", arquivo=str(salvo), pasta_cache=str(tmp_path), lote_max=4, **limite_kw)
    return ctor, fi, salvo


def test_memoria_estourada_sai_86_depois_do_lote(cena, novo, tmp_path):  # mutante 4
    def rss(c):
        return 9999.0 if len([e for e in c.eventos if e[0] == "gravar"]) >= 2 else 50.0

    ctor, fi, _ = _memoria(cena, novo, tmp_path, rss, {"limite_mb": 1000.0})
    esperar(lambda: fi.saida is not None)
    assert persistente.SAIDA_MEMORIA == 86 and fi.saida == 86
    tags = [e[0] for e in ctor.eventos if e[0] in ("lote", "gravar", "fechar")]
    assert tags == ["lote", "gravar", "lote", "gravar", "fechar"], tags  # confere depois do gravar_lote; fecha o banco antes de sair
    assert ("rss",) in ctor.eventos[ctor.eventos.index(("gravar", [4, 5, 6, 7])):]


def test_memoria_limite_padrao_6000_e_abaixo_do_limite_nao_sai(cena, novo, tmp_path):
    ctor, fi, _ = _memoria(cena, novo, tmp_path, 7000.0, {}, fechar_erro=True)  # G: fechar() com excecao ainda sai com 86
    esperar(lambda: fi.saida is not None)
    assert fi.saida == 86 and len(ctor.lotes) == 1 and ctor.eventos[-1] == ("fechar",)
    ctor2, fi2, salvo = _memoria(cena, novo, tmp_path, 900.0, {"limite_mb": 1000.0})
    terminar(fi2, str(salvo))
    assert fi2.saida is None and len(ctor2.lotes) == 6


def test_arquivo_reaberto_zera_a_construcao(cena, novo, tmp_path):  # mutantes 5 e 7 (banco uma vez por vida)
    salvo, _ = cena
    ctor = Falso(range(200))
    fi = novo(ctor)
    d1 = fi.pedir("construir", arquivo=str(salvo), pasta_cache=str(tmp_path), lote_max=4)
    esperar(lambda: ctor.lotes)
    st = os.stat(salvo)
    os.utime(salvo, ns=(st.st_atime_ns, st.st_mtime_ns + 5_000_000_000))  # mudou no disco
    assert fi.pedir("abrir", arquivo=str(salvo))["aberto"] is True
    time.sleep(LOTE_S + 0.3)
    n = len(ctor.lotes)
    e = estado(fi, str(salvo))
    assert e["ativo"] is False and e["pendentes"] == 0, f"construcao continuou depois de reabrir: {e}"
    time.sleep(0.8)
    assert len(ctor.lotes) == n, "lotes continuam depois do arquivo reaberto"
    d2 = fi.pedir("construir", arquivo=str(salvo), pasta_cache=str(tmp_path), lote_max=4)
    assert d1["pendentes"] == d2["pendentes"] == 200, "fila nova tem de partir do zero"
    esperar(lambda: len(ctor.lotes) > n)
    assert ctor.lotes[n]["assinatura"] == sig(salvo) and ctor.lotes[n]["assinatura"] != ctor.lotes[0]["assinatura"]
    assert ctor.lotes[n]["ids"] == [0, 1, 2, 3] and len(ctor.pastas) == 1, "banco abre uma vez por vida do filho"
    outro = str(tmp_path / "outro.ifc")
    open(outro, "wb").write(open(salvo, "rb").read())
    fi.pedir("abrir", arquivo=outro)  # outro caminho tambem zera
    time.sleep(LOTE_S + 0.3)
    n = len(ctor.lotes)
    time.sleep(0.8)
    assert len(ctor.lotes) == n and estado(fi, str(salvo))["pendentes"] == 0


def test_construir_repetido_nao_duplica_a_fila(cena, novo, tmp_path):  # mutante 7
    salvo, _ = cena
    ctor = Falso(range(20), dorme=0.05)
    fi = novo(ctor)
    fi.pedir("construir", arquivo=str(salvo), pasta_cache=str(tmp_path), lote_max=2)
    d = fi.pedir("construir", arquivo=str(salvo), pasta_cache=str(tmp_path), lote_max=2)
    assert d["aceito"] is True and 0 < d["pendentes"] <= 20
    terminar(fi, str(salvo))
    assert sorted(ctor.gravados()) == list(range(20)), "peca feita duas vezes ou perdida"
    assert len(ctor.pastas) == 1


def _banco_ocupado(n, reg):
    raise sqlite3.OperationalError("database is locked")

def test_banco_ocupado_uma_vez_repete_o_lote_sem_perder_pecas(cena, novo, tmp_path):  # mutante 6
    salvo, _ = cena
    ctor = Falso(range(12), dorme=0.02, falhar=lambda n, reg: _banco_ocupado(n, reg) if n in (2, 4, 6) else None)  # A: nao seguidos, contador zera
    fi = novo(ctor)
    fi.pedir("construir", arquivo=str(salvo), pasta_cache=str(tmp_path), lote_max=3)
    esperar(lambda: len(ctor.lotes) >= 3)
    assert ctor.lotes[2]["ids"] == ctor.lotes[1]["ids"] == [3, 4, 5], "lote que falhou tem de voltar ao comeco da fila"
    assert ctor.lotes[2]["t"] - ctor.lotes[1]["t"] >= 0.8, "sem espera entre as tentativas (rx.poll(1.0))"
    terminar(fi, str(salvo))
    assert sorted(ctor.gravados()) == list(range(12)) and estado(fi, str(salvo))["parado"] is None


def test_banco_ocupado_tres_seguidas_para_e_o_laco_segue(cena, novo, tmp_path):  # mutante 6
    salvo, _ = cena
    ctor = Falso(range(12), dorme=0.01, falhar=_banco_ocupado)
    fi = novo(ctor)
    fi.pedir("construir", arquivo=str(salvo), pasta_cache=str(tmp_path), lote_max=3)
    time.sleep(4.0)
    e = estado(fi, str(salvo))
    assert e["parado"] == "banco_ocupado" and len(ctor.lotes) == 3 and all(x["ids"] == [0, 1, 2] for x in ctor.lotes), (e, len(ctor.lotes))
    assert fi.pedir("abrir", arquivo=str(salvo))["aberto"] is True  # atende pedidos
    time.sleep(1.3)
    assert len(ctor.lotes) == 3, "tentou de novo depois de parar"


def test_outra_excecao_para_com_erro_e_o_laco_segue(cena, novo, tmp_path):  # mutante 6
    def boom(n, reg):
        raise RuntimeError("boom-xyz")

    salvo, _ = cena
    ctor = Falso(range(12), dorme=0.01, falhar=boom)
    fi = novo(ctor)
    fi.pedir("construir", arquivo=str(salvo), pasta_cache=str(tmp_path), lote_max=3)
    esperar(lambda: estado(fi, str(salvo))["parado"] == "erro")
    assert "boom-xyz" in estado(fi, str(salvo))["erro"]
    time.sleep(1.2)
    assert len(ctor.lotes) == 1 and fi.pedir("abrir", arquivo=str(salvo))["aberto"] is True


def test_filho_nao_manda_mensagem_sem_pedido(cena, novo, tmp_path):  # mutante 8
    salvo, _ = cena
    ctor = Falso(range(20), dorme=0.05)
    fi = novo(ctor)
    fi.pedir("construir", arquivo=str(salvo), pasta_cache=str(tmp_path), lote_max=2)
    fi.silencio(1.0)  # a construcao inteira (10 lotes, 0,5 s) roda sem o pai ler nada; nada e empurrado
    assert estado(fi, str(salvo))["pendentes"] == 0
    time.sleep(0.2)
    n = fi.rx.polls
    time.sleep(1.0)  # D: fila vazia = recv bloqueante, sem girar
    assert fi.rx.polls - n <= 3, f"laco gira com a fila vazia: {fi.rx.polls - n} polls em 1 s"


def test_regra_do_numero_vale_para_as_ops_novas(cena, novo, tmp_path):  # mutante 9
    salvo, pedidos = cena
    ctor = Falso(range(40), dorme=0.05)
    fi = novo(ctor)
    fi.pedir("construir", numero=5, arquivo=str(salvo), pasta_cache=str(tmp_path), lote_max=4)
    ped = {k: v for k, v in pedidos["A"].items() if k not in ("op", "protocolo")}
    for op, num, campos in (("construir", 5, {"arquivo": str(salvo), "pasta_cache": str(tmp_path / "x")}), ("estado_construcao", 3, {"arquivo": str(salvo)}),
                            ("desenho", 4, ped)):
        d = fi.pedir(op, numero=num, **campos)
        assert d["ok"] is False and d["erro"]["tipo"] == "PedidoVelho", (op, d)
    assert ctor.pastas == [str(tmp_path)] and not any(e[0] == "prior" for e in ctor.eventos), "pedido velho foi executado"
    assert estado(fi, str(salvo))["ativo"] is True  # numero 6 ainda e aceito: o velho nao mudou o ultimo


def test_estado_contagens(cena, novo, tmp_path):  # mutante 10
    salvo, _ = cena
    ctor = Falso(range(20), dorme=0.05, ret=(3, 1, 0))
    fi = novo(ctor)
    fi.pedir("construir", arquivo=str(salvo), pasta_cache=str(tmp_path), lote_max=4)
    vistos = []
    while True:
        e = estado(fi, str(salvo))
        vistos.append(e["lotes"])
        assert e["feitos"] == 4 * e["lotes"] and e["pendentes"] == 20 - e["feitos"], e
        assert e["tesseladas"] == 3 * e["lotes"] and e["reaproveitadas"] == e["lotes"] and e["falhas"] == 0, e
        assert e["rss_mb"] == 123.5 and e["parado"] is None and e["erro"] is None and e["lote_max_s"] >= (0.04 if e["lotes"] else 0)
        if e["pendentes"] == 0:
            break
        assert e["ativo"] is True
    assert e["lotes"] == 5 and e["feitos"] == 20 and len(set(vistos)) > 1


def test_estado_falhas_e_lote_max_padrao_64(cena, novo, tmp_path):  # mutante 10
    salvo, _ = cena
    ctor = Falso(range(130), dorme=0.01, ret=(2, 1, 1))
    fi = novo(ctor)
    fi.pedir("construir", arquivo=str(salvo), pasta_cache=str(tmp_path))
    terminar(fi, str(salvo))
    e = estado(fi, str(salvo))
    assert (e["lotes"], e["tesseladas"], e["reaproveitadas"], e["falhas"]) == (3, 6, 3, 3), e
    assert [len(x["ids"]) for x in ctor.lotes] == [64, 64, 2]


def test_pedido_corta_a_espera_do_banco_ocupado(cena, novo, tmp_path):  # B: poll(1.0), nao sleep(1.0)
    salvo, _ = cena
    ctor = Falso(range(12), dorme=0.05, falhar=lambda n, reg: _banco_ocupado(n, reg) if n == 1 else None)
    fi = novo(ctor)
    fi.pedir("construir", arquivo=str(salvo), pasta_cache=str(tmp_path), lote_max=3)
    esperar(lambda: ctor.lotes)
    time.sleep(0.15)  # dentro da espera de 1 s
    fi.pedir("abrir", arquivo=str(salvo))
    assert fi.ultimo_t <= 0.4, f"pedido esperou o banco ocupado: {fi.ultimo_t:.2f}s"


@pytest.mark.parametrize("msg", ["cache fechado", "disk I/O error"])
def test_operational_error_que_nao_e_banco_ocupado_vira_erro(cena, novo, tmp_path, msg):  # E
    def falha(n, reg):
        raise sqlite3.OperationalError(msg)

    salvo, _ = cena
    ctor = Falso(range(12), dorme=0.01, falhar=falha)
    fi = novo(ctor)
    fi.pedir("construir", arquivo=str(salvo), pasta_cache=str(tmp_path), lote_max=3)
    time.sleep(0.5)  # sem espera de 1 s nem repeticao
    e = estado(fi, str(salvo))
    assert e["parado"] == "erro" and msg in e["erro"] and len(ctor.lotes) == 1, (e, len(ctor.lotes))


def test_priorizar_com_excecao_nao_derruba_o_laco(cena, novo, tmp_path):  # F1
    salvo, pedidos = cena
    ctor = Falso(range(40), dorme=0.05, prior_erro=True)
    fi = novo(ctor)
    fi.pedir("construir", arquivo=str(salvo), pasta_cache=str(tmp_path), lote_max=2)
    assert fi.pedir("desenho", **{k: v for k, v in pedidos["A"].items() if k not in ("op", "protocolo")}).get("ok")
    assert any(e[0] == "prior" for e in ctor.eventos)
    assert fi.pedir("abrir", arquivo=str(salvo))["aberto"] is True
    terminar(fi, str(salvo))
    assert sorted(ctor.gravados()) == list(range(40)), "fila perdida depois da excecao em priorizar"


def test_construtor_que_nao_importa_responde_erro_e_o_laco_segue(cena, novo, tmp_path, monkeypatch):  # F2: {"aceito": False, "motivo": "erro"}
    salvo, _ = cena
    monkeypatch.setitem(sys.modules, "obim_geometria.construtor", None)  # import_module levanta ImportError
    fi = novo(None)
    d = fi.pedir("construir", arquivo=str(salvo), pasta_cache=str(tmp_path))
    assert d.get("aceito") is False and d.get("motivo") == "erro", d
    assert fi.pedir("abrir", arquivo=str(salvo))["aberto"] is True


def test_rss_com_excecao_vira_parado_erro(cena, novo, tmp_path):  # F3
    def rss(c):
        if c.gravados():
            raise OSError("rss indisponivel")
        return 10.0

    salvo = cena[0]
    fi = novo(Falso(range(12), dorme=0.01, rss=rss))
    fi.pedir("construir", arquivo=str(salvo), pasta_cache=str(tmp_path), lote_max=3)
    esperar(lambda: estado(fi, str(salvo)).get("parado") == "erro")
    assert fi.pedir("abrir", arquivo=str(salvo))["aberto"] is True


@pytest.mark.parametrize("lote_max", [0, -3])
def test_lote_max_invalido_nao_gira_em_vazio(cena, novo, tmp_path, lote_max):  # H: lote >= 1, fila avanca
    salvo, _ = cena
    ctor = Falso(range(6), dorme=0.01)
    fi = novo(ctor)
    fi.pedir("construir", arquivo=str(salvo), pasta_cache=str(tmp_path), lote_max=lote_max)
    terminar(fi, str(salvo), 5)
    assert sorted(ctor.gravados()) == list(range(6)) and all(len(x["ids"]) >= 1 for x in ctor.lotes)


# MUTANTES: 1 e 3 test_desenho_passa_a_frente_do_lote; 2 test_construir_responde_antes...; 4 test_memoria_*; 5 test_arquivo_reaberto_zera_*;
# A-H (revisao Opus): A test_banco_ocupado_uma_vez, B test_pedido_corta_a_espera, C test_construir_responde_antes, D test_filho_nao_manda, E test_operational_error_*,
# test_priorizar_com_excecao, test_construtor_que_nao_importa, test_rss_com_excecao, test_memoria_limite_padrao (G), test_lote_max_invalido
# 6 test_banco_ocupado_*, test_outra_excecao_*; 7 test_construir_repetido_*; 8 test_filho_nao_manda_*;
# 9 test_regra_do_numero_*; 10 test_estado_contagens, test_estado_falhas_*  (`Filho.ler` tambem rejeita mensagem sem pedido)
