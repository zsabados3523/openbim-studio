# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oraculo F0-S06-T19g4a: laco do filho persistente (`obim_geometria.persistente.servir`). Nao editar nesta tarefa.

CONTRATO (para o implementador, Hydrogen)
1. Modulo novo `obim_geometria/persistente.py` com `servir(tx, rx)`. `tx.send_bytes(bytes)` (como em `processo.entrada`); `rx.recv_bytes()` -> bytes
   (como `multiprocessing.Connection`); `EOFError` de `rx.recv_bytes()` = fim.
2. Ao iniciar: manda `{"tipo":"pronto","pid":...,"protocolo":1}` (igual ao descartavel).
3. Cada entrada e um JSON (bytes). Pedido = pedido normal do descartavel (`op` "desenho" ou "caixas", `arquivo`, `assinatura` opcional, ...) MAIS
   `numero` (int). `{"op":"encerrar"}` (sem numero) = sair limpo: `servir` RETORNA (sem excecao) e nao atende nada que venha depois. EOFError = idem.
4. Saidas: mensagens de fase como no descartavel, MAIS `numero` do pedido (`{"tipo":"fase","numero":N,"fase":...,"tempo":...}`) e
   `{"tipo":"resposta","numero":N,"dados":<o mesmo dict que o descartavel devolve>}`. Toda mensagem depois de "pronto" leva `numero`
   (None quando nao ha numero valido).
5. Ordem: `numero` tem de ser MAIOR que o ultimo pedido aceito (pode haver saltos). Se `numero <= ultimo`: resposta com
   `dados={"ok":False,"erro":{"tipo":"PedidoVelho",...}}`, numero ecoado, NADA e executado e o ultimo nao muda.
6. Modelo: o IFC e aberto UMA vez (`ifcopenshell.open`) e mantido. So reabre se `arquivo` do pedido for diferente do aberto (um unico slot:
   X, Y, X = 3 aberturas). Pedidos reutilizam o `f` aberto (desenho: `desenho._abrir_ifc` devolve o `f` mantido durante o pedido;
   caixas: `caixas.processar(pedido, f=None)` ganha o argumento opcional `f`; com `f` nao reabre).
7. Cada pedido roda dentro de `desenho._sem_rastro(f)` chamado PELO MODULO (`desenho._sem_rastro`, nao copia importada), alem do que
   `processar` ja faz; `desenho.processar` e `caixas.processar` tambem sao chamados pelo atributo do modulo. Depois de qualquer
   pedido (ok, erro, excecao) `f.to_string()` e igual ao do arquivo salvo.
   Risco conhecido: transacao dentro de transacao (processar ja envolve em `_sem_rastro`); se o ifcopenshell nao aceitar, resolver
   no implementador (ex.: so uma camada) sem afrouxar nada aqui.
8. Assinatura/pares como no descartavel: o resultado de erro (`Divergente`, `ArquivoDivergente`) e o MESMO tipo que o descartavel da.
9. Pedido invalido (bytes que nao sao JSON, JSON que nao e objeto, sem `numero`, `op` desconhecida, arquivo que nao abre) ou excecao no
   meio do pedido NAO derrubam o laco: resposta `ok False` com `erro.tipo` (excecao => `type(e).__name__`; sem numero => `PedidoInvalido`;
   op desconhecida => `OperacaoDesconhecida`), numero ecoado se houver (None se nao), e o proximo pedido sai correto com o modelo intacto.

Mutantes (implementacoes de referencia mutadas dentro deste arquivo, `_sim`): sem `_sem_rastro`; reabre a cada pedido; ignora `numero`;
excecao derruba o laco; nao reabre quando o arquivo muda. Cada um e derrubado por pelo menos uma verificacao `chk_*`.
A mesma verificacao roda no `servir` real e na referencia boa (`_sim()` sem defeito): se a referencia boa falhar, o oraculo e que esta errado."""
from __future__ import annotations

import contextlib
import copy
import json
import os
import shutil

import ifcopenshell
import pytest
from obim_geometria import caixas, desenho, processo
from s05_conteudo_aux import _limpa, exigir  # noqa: F401  (fixture autouse e guarda)
from test_s06_t19g3_sem_rastro_oraculo import SEQ, _est, cena  # noqa: F401  (cena = fixture)

PRONTO = json.dumps({"tipo": "pronto", "pid": 0, "protocolo": 1}).encode()


# ------------------------------------------------------------------ canal falso
class FakeTx:
    def __init__(self, abertos):
        self.msgs, self.estados, self._abertos = [], [], abertos

    def send_bytes(self, b):
        m = json.loads(b)
        self.msgs.append(m)
        if m.get("tipo") == "resposta" and self._abertos:  # estado do modelo mantido no instante da resposta
            self.estados.append(_est(self._abertos[-1][1]))

    def close(self):
        pass

    @property
    def respostas(self):
        return [m for m in self.msgs if m.get("tipo") == "resposta"]


class FakeRx:
    def __init__(self, entradas):
        self._q = [e if isinstance(e, bytes) else json.dumps(e).encode() for e in entradas]
        self.restantes = lambda: len(self._q)

    def recv_bytes(self):
        if not self._q:
            raise EOFError
        return self._q.pop(0)


def _espiar(mp):
    abertos, orig = [], ifcopenshell.open

    def aberto(*a, **k):
        f = orig(*a, **k)
        abertos.append((str(a[0]) if a else None, f))
        return f

    mp.setattr(ifcopenshell, "open", aberto)
    return abertos


def _entrada(p):
    """Filho descartavel de verdade (`processo.entrada`, em processo) -> `dados` da resposta."""
    tx = FakeTx([])
    processo.entrada(tx, json.dumps(p))
    return tx.respostas[-1]["dados"]


def _rodar(fn, entradas, mp):
    abertos = _espiar(mp)
    tx, rx = FakeTx(abertos), FakeRx(entradas)
    fn(tx, rx)  # tem de retornar sem excecao
    return tx, abertos, rx


# ------------------------------------------------------------------ contexto
class Ctx:
    pass


@pytest.fixture
def ctx(cena, tmp_path, monkeypatch):
    salvo, pedidos = cena
    c = Ctx()
    c.mp, c.pedidos, c.salvo = monkeypatch, pedidos, str(salvo)
    c.outro = str(tmp_path / "outro.ifc")
    shutil.copy(salvo, c.outro)
    c.est0 = _est(ifcopenshell.open(c.salvo))
    pedidos["C"] = {"op": "caixas", "protocolo": 1, "arquivo": c.salvo, "threads": 1, "elementos": pedidos["A"]["elementos"]}
    c.ref = {k: _entrada(copy.deepcopy(pedidos[k])) for k in "ABRGPC"}
    for k in "ABRGP":
        assert c.ref[k].get("ok") and c.ref[k].get("svg"), (k, c.ref[k])
    assert c.ref["C"].get("ok") and c.ref["C"]["caixas_envolventes"]
    assert len({c.ref[k]["svg"] for k in "ABRG"}) == 4
    return c


def P(c, k, n, arquivo=None, **extra):
    p = copy.deepcopy(c.pedidos[k])
    p["numero"] = n
    if arquivo:
        p["arquivo"] = arquivo
    p.update(extra)
    return p


def _igual(k, dados, c):
    if k == "C":
        assert dados.get("ok") and dados["caixas_envolventes"] == c.ref["C"]["caixas_envolventes"] and dados["falhas_geometria"] == c.ref["C"]["falhas_geometria"], k
    else:
        assert dados.get("ok") and dados["svg"] == c.ref[k]["svg"], f"pedido {k}: SVG difere do filho descartavel"


ENC = {"op": "encerrar"}


# ------------------------------------------------------------------ verificacoes (rodam no real e nas referencias)
def chk_equivalencia(fn, c, com_caixas):
    seq = SEQ + ("CAC" if com_caixas else "")
    tx, abertos, rx = _rodar(fn, [P(c, k, i) for i, k in enumerate(seq, 1)] + [ENC], c.mp)
    rs = tx.respostas
    assert [r["numero"] for r in rs] == list(range(1, len(seq) + 1)), "numero nao ecoado/ordem das respostas"
    for k, r in zip(seq, rs):
        _igual(k, r["dados"], c)
    assert all("numero" in m for m in tx.msgs if m.get("tipo") != "pronto"), "mensagem de fase/resposta sem numero"
    assert tx.msgs[0].get("tipo") == "pronto"
    assert len(abertos) == 1, f"arquivo aberto {len(abertos)} vezes (esperado 1)"
    assert tx.estados and all(e == c.est0 for e in tx.estados), "modelo mantido difere do arquivo salvo depois de um pedido"
    assert _est(abertos[-1][1]) == c.est0


def chk_abertura(fn, c):
    seq = [("A", c.salvo), ("B", c.salvo), ("A", c.outro), ("B", c.outro), ("A", c.salvo)]
    tx, abertos, _ = _rodar(fn, [P(c, k, i, a) for i, (k, a) in enumerate(seq, 1)] + [ENC], c.mp)
    for (k, _a), r in zip(seq, tx.respostas):
        _igual(k, r["dados"], c)
    assert [a for a, _f in abertos] == [c.salvo, c.outro, c.salvo], f"aberturas: {[a for a, _f in abertos]}"
    assert all(e == c.est0 for e in tx.estados)


def chk_numero(fn, c):
    chamadas = []
    real = desenho.processar
    c.mp.setattr(desenho, "processar", lambda p, fase=None: (chamadas.append(p["numero"]), real(p, fase))[1])
    seq = [("A", 1), ("B", 2), ("A", 2), ("B", 1), ("A", 5), ("B", 4)]
    tx, _a, _ = _rodar(fn, [P(c, k, n) for k, n in seq] + [ENC], c.mp)
    rs = tx.respostas
    assert [r["numero"] for r in rs] == [n for _k, n in seq], "numero ecoado errado"
    ok = [True, True, False, False, True, False]
    assert [bool(r["dados"].get("ok")) for r in rs] == ok
    for r, o in zip(rs, ok):
        if not o:
            assert r["dados"]["erro"]["tipo"] == "PedidoVelho"
    assert chamadas == [1, 2, 5], f"pedido velho foi executado: {chamadas}"
    _igual("A", rs[4]["dados"], c)


def chk_excecao(fn, c, k4="C"):
    """Injeta falha no 2o pedido DEPOIS de mutar o modelo; so a transacao do laco (nao a de `processar`) desfaz."""
    real, n = desenho.processar, []

    def com_falha(p, fase=None):
        n.append(1)
        if len(n) == 2:
            f = [f for _a, f in abertos][-1]
            desenho._isolar_pavimento(f, f.by_type("IfcBuildingStorey")[0])
            raise RuntimeError("falha injetada")
        return real(p, fase)

    abertos = _espiar(c.mp)
    c.mp.setattr(desenho, "processar", com_falha)
    tx, rx = FakeTx(abertos), FakeRx([P(c, "A", 1), P(c, "B", 2), P(c, "A", 3), P(c, k4, 4), ENC])
    fn(tx, rx)  # nao pode levantar
    rs = tx.respostas
    assert [r["numero"] for r in rs] == [1, 2, 3, 4], "laco morreu ou perdeu pedidos"
    assert not rs[1]["dados"].get("ok") and rs[1]["dados"]["erro"]["tipo"] == "RuntimeError"
    _igual("A", rs[0]["dados"], c)
    _igual("A", rs[2]["dados"], c)
    _igual(k4, rs[3]["dados"], c)
    assert all(e == c.est0 for e in tx.estados), "excecao deixou rastro no modelo mantido"
    assert len(abertos) == 1


def chk_fim(fn, c):
    # encerrar: retorna e nao atende o que vem depois
    tx, _a, rx = _rodar(fn, [P(c, "A", 1), ENC, P(c, "B", 2)], c.mp)
    assert [r["numero"] for r in tx.respostas] == [1] and rx.restantes() == 1
    # EOF sem encerrar
    tx, _a, _ = _rodar(fn, [P(c, "A", 1)], c.mp)
    assert [r["numero"] for r in tx.respostas] == [1]
    # nenhum pedido
    tx, abertos, _ = _rodar(fn, [], c.mp)
    assert tx.respostas == [] and tx.msgs and tx.msgs[0]["tipo"] == "pronto" and abertos == []


# ------------------------------------------------------------------ referencia (boa e mutantes)
def _sim(mp, reabre_sempre=False, ignora_numero=False, sem_rastro=False, derruba=False, nao_reabre_se_muda=False):
    def servir(tx, rx):
        estado = {"f": None, "arq": None, "ultimo": 0}
        mp.setattr(desenho, "_abrir_ifc", lambda caminho, pavimento=None: estado["f"])
        tx.send_bytes(PRONTO)

        def resp(n, dados):
            tx.send_bytes(json.dumps({"tipo": "resposta", "numero": n, "dados": dados}).encode())

        def erro(n, tipo):
            resp(n, {"ok": False, "erro": {"tipo": tipo, "mensagem": tipo, "rastro": ""}})

        while True:
            try:
                p = json.loads(rx.recv_bytes())
            except EOFError:
                return
            if p.get("op") == "encerrar":
                return
            n = p["numero"]
            if not ignora_numero and n <= estado["ultimo"]:
                erro(n, "PedidoVelho")
                continue
            estado["ultimo"] = n
            if estado["f"] is None or reabre_sempre or (p["arquivo"] != estado["arq"] and not nao_reabre_se_muda):
                estado["f"], estado["arq"] = ifcopenshell.open(p["arquivo"]), p["arquivo"]
            f = estado["f"]
            try:
                with (contextlib.nullcontext() if sem_rastro else desenho._sem_rastro(f)):
                    if p["op"] == "caixas":
                        d = caixas.processar(p, f=f)
                    else:
                        d = desenho.processar(p, lambda nome: tx.send_bytes(json.dumps({"tipo": "fase", "numero": n, "fase": nome, "tempo": 0.0}).encode()))
            except Exception as e:
                if derruba:
                    raise
                erro(n, type(e).__name__)
                continue
            resp(n, d)

    return servir


def _real():
    from obim_geometria import persistente  # noqa: PLC0415  (falha hoje: modulo nao existe)
    return persistente.servir


# ------------------------------------------------------------------ testes no servir real
def test_modulo_existe():
    assert callable(_real())


def test_equivalencia_com_descartavel_e_modelo_intacto(ctx):
    chk_equivalencia(_real(), ctx, com_caixas=True)


def test_abre_uma_vez_e_reabre_so_quando_arquivo_muda(ctx):
    chk_abertura(_real(), ctx)


def test_numero_ecoado_e_pedido_velho_recusado(ctx):
    chk_numero(_real(), ctx)


def test_excecao_no_pedido_nao_derruba_e_modelo_intacto(ctx):
    chk_excecao(_real(), ctx)


def test_encerrar_e_eof_terminam_limpo(ctx):
    chk_fim(_real(), ctx)


def test_assinatura_e_pares_dao_o_mesmo_erro_do_descartavel(ctx):
    st = os.stat(ctx.salvo)
    certa = [int(st.st_size), int(st.st_mtime_ns)]
    ruim = [certa[0] + 1, certa[1]]
    guid_ruim = [[ctx.pedidos["A"]["elementos"][0][0], "GUID-ERRADO"]] + ctx.pedidos["A"]["elementos"][1:]
    casos = [("A", {"assinatura": ruim}), ("C", {"assinatura": ruim}), ("A", {"elementos": guid_ruim}), ("C", {"elementos": guid_ruim}),
             ("A", {"assinatura": certa, "elementos": guid_ruim})]
    esperado = [_entrada({**copy.deepcopy(ctx.pedidos[k]), **ex}) for k, ex in casos]
    assert all(not e.get("ok") for e in esperado)
    assert esperado[0]["erro"]["tipo"] == "Divergente"
    entradas = [P(ctx, k, i, **ex) for i, (k, ex) in enumerate(casos, 1)] + [P(ctx, "A", 9, assinatura=certa), P(ctx, "A", 10), ENC]
    tx, _a, _ = _rodar(_real(), entradas, ctx.mp)
    rs = tx.respostas
    assert [r["numero"] for r in rs] == [1, 2, 3, 4, 5, 9, 10]
    for r, e in zip(rs, esperado):
        assert not r["dados"].get("ok") and r["dados"]["erro"]["tipo"] == e["erro"]["tipo"]
    _igual("A", rs[5]["dados"], ctx)
    _igual("A", rs[6]["dados"], ctx)
    assert all(e == ctx.est0 for e in tx.estados)


def test_pedidos_invalidos_nao_derrubam_o_laco(ctx):
    entradas = [b"isto nao e json", b"[1, 2]", {"op": "desenho", "arquivo": ctx.salvo}, {"numero": 7, "op": "naoexiste"},
                P(ctx, "A", 8, arquivo=ctx.outro + ".inexistente"), P(ctx, "A", 9), ENC]
    tx, abertos, _ = _rodar(_real(), entradas, ctx.mp)
    rs = tx.respostas
    assert len(rs) == 6, f"cada entrada invalida tem de ter 1 resposta: {rs}"
    assert [r["numero"] for r in rs] == [None, None, None, 7, 8, 9]
    assert all(not r["dados"].get("ok") for r in rs[:5])
    assert rs[2]["dados"]["erro"]["tipo"] == "PedidoInvalido" and rs[3]["dados"]["erro"]["tipo"] == "OperacaoDesconhecida"
    _igual("A", rs[5]["dados"], ctx)
    assert _est(abertos[-1][1]) == ctx.est0


def test_sem_sem_rastro_do_modulo_o_real_e_derrubado(ctx):
    """Neutraliza `desenho._sem_rastro` (no-op): o laco real tem de deixar rastro e a verificacao tem de falhar."""
    @contextlib.contextmanager
    def no_op(f):
        yield

    ctx.mp.setattr(desenho, "_sem_rastro", no_op)
    with pytest.raises(AssertionError):
        chk_excecao(_real(), ctx)


# ------------------------------------------------------------------ referencia boa passa; mutantes caem
def test_referencia_boa_passa_nas_verificacoes(ctx):
    """Controle do oraculo: `_sim()` (sem defeito) satisfaz o contrato. Usa so desenho (a referencia nao tem `caixas(f=)`)."""
    chk_equivalencia(_sim(ctx.mp), ctx, com_caixas=False)
    chk_abertura(_sim(ctx.mp), ctx)
    chk_numero(_sim(ctx.mp), ctx)
    chk_fim(_sim(ctx.mp), ctx)


def test_referencia_boa_excecao(ctx):
    chk_excecao(_sim(ctx.mp), ctx, k4="A")


@pytest.mark.parametrize("defeito,verif", [
    ("sem_rastro", "excecao"), ("reabre_sempre", "equivalencia"), ("ignora_numero", "numero"),
    ("derruba", "excecao"), ("nao_reabre_se_muda", "abertura"),
])
def test_mutante_e_derrubado(ctx, defeito, verif):
    fn = _sim(ctx.mp, **{defeito: True})
    with pytest.raises(Exception):  # AssertionError, ou a excecao que escapou do laco
        if verif == "excecao":
            chk_excecao(fn, ctx, k4="A")
        elif verif == "equivalencia":
            chk_equivalencia(fn, ctx, com_caixas=False)
        elif verif == "numero":
            chk_numero(fn, ctx)
        else:
            chk_abertura(fn, ctx)
