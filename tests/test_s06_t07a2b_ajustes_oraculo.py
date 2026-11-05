# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo F0-S06-T07a2B (ajustes pedidos pelo Argon na T07a2). Reusa os ganchos de `test_s06_t07a2_selecao_desempenho_oraculo.py`. Contrato novo:
1. `nucleos.nucleos_fisicos()`: Linux (`sys.platform.startswith("linux")`, lido na hora da chamada) lê `/proc/cpuinfo` com `open(...)` embutido: pares únicos
   (`physical id`, `core id`); sem pares ou `OSError` -> fallback. Fora do Linux -> fallback direto (não lê o arquivo). Fallback = `max(1, (os.cpu_count() or 1) // 2)`,
   NUNCA o `cpu_count` cheio. Resultado sempre >= 1.
2. `erros_iterator` pode trazer `"ids": [step ids]` por erro (sem `ids` ou vazio = vale para todos os elementos do pedido). `SessaoSelecao` guarda o erro POR elemento;
   `invalidar(ids)` esquece caixa E erro desses ids (None = tudo). `Selecao.erros_geometria` leva só erros de elementos VISÍVEIS no corte (categorias_ocultas
   tira os do elemento oculto), sem duplicar entre cortes. Com sessão == sem sessão, mesmo mudando `categorias_ocultas` entre cortes e com erro.
3. `caixas.processar`: elemento cujo `get()` devolve geometria vazia conta como VISITADO (não é reenviado; vai a `falhas_geometria`); aborto com elemento ruim na
   cabeça não reconstrói o iterator uma vez por restante: passagens <= (elementos que falham) + 2.
4. `ArvoreCaixas`: caixa ou consulta invertida em QUALQUER eixo (Y inclusive) ou com +/-inf na consulta -> ValueError. A árvore continua busca linear: é só contrato de
   resultado (o implementador documenta isso no docstring; sem teste de tempo)."""
import io
import builtins

import pytest
import s06_t07_aux as X
import s06_t07e_aux as T
from s05_conteudo_aux import _limpa, exigir  # noqa: F401
from test_s06_t07a2_selecao_desempenho_oraculo import Espia, Executor, _cx, _ok, modelo  # noqa: F401


# ---------- 1. núcleos físicos ----------
def _cpuinfo(pares, logicos=None):
    linhas = []
    for i, (p, c) in enumerate(pares if logicos is None else pares * logicos):
        linhas += [f"processor\t: {i}", f"physical id\t: {p}", f"core id\t\t: {c}", ""]
    return "\n".join(linhas)


def _ambiente(mp, plataforma, texto, cpus, falha_open=False):
    import os
    import sys
    from obim_geometria import nucleos as N
    real = builtins.open

    def falso(arq, *a, **k):
        if str(arq) == "/proc/cpuinfo":
            if falha_open or texto is None:
                raise OSError("sem /proc")
            return io.StringIO(texto)
        return real(arq, *a, **k)
    mp.setattr(sys, "platform", plataforma)
    mp.setattr(os, "cpu_count", lambda: cpus)
    mp.setattr(builtins, "open", falso)
    return N


_HT = _cpuinfo([(0, 0), (0, 1), (0, 2), (0, 3)], logicos=2)  # hyperthreads: 8 processadores, 4 pares únicos
_SOQ = _cpuinfo([(0, c) for c in range(4)] + [(1, c) for c in range(4)])  # 2 soquetes x 4 núcleos
JA_VALE = [("linux", _SOQ, 16, False, 8), ("linux", _HT, 8, False, 4), ("linux", None, 1, True, 1), ("linux", None, None, True, 1),
           ("win32", None, 1, False, 1), ("win32", None, None, False, 1)]  # regressão: já certo hoje
FALTA = [("linux", None, 16, True, 8), ("linux", None, 3, True, 1), ("linux", "model name : arm\nprocessor : 0\n", 8, False, 4),  # sem /proc ou sem ids: metade
         ("linux", "", 6, False, 3), ("win32", _cpuinfo([(0, 0), (0, 1)]), 16, False, 8), ("darwin", _cpuinfo([(0, 0)]), 10, False, 5)]  # fora do Linux: não lê o arquivo


def _confere(mp, plataforma, texto, cpus, falha, esperado):
    exigir()
    r = _ambiente(mp, plataforma, texto, cpus, falha).nucleos_fisicos()
    assert r == esperado and isinstance(r, int) and r >= 1


@pytest.mark.parametrize("plataforma,texto,cpus,falha,esperado", JA_VALE)
def test_nucleos_fisicos_casos_que_ja_valem(monkeypatch, plataforma, texto, cpus, falha, esperado):
    _confere(monkeypatch, plataforma, texto, cpus, falha, esperado)


@pytest.mark.parametrize("plataforma,texto,cpus,falha,esperado", FALTA)
def test_nucleos_fisicos_fallback_conservador(monkeypatch, plataforma, texto, cpus, falha, esperado):
    _confere(monkeypatch, plataforma, texto, cpus, falha, esperado)


# ---------- 2. sessão: erro por elemento ----------
def _com_erro(alvo, msg="boom"):
    """Executor que emite erro do iterator para `alvo` (step id) só se `alvo` está no pedido."""
    def ex(pedido):
        from obim_geometria import local
        r = local.executar(pedido)
        if any(e[0] == alvo for e in pedido["elementos"]):
            r = {**r, "erros_iterator": [{"tipo": "RuntimeError", "mensagem": msg, "ids": [alvo]}]}
        return r
    return ex


def _caso():
    exigir()
    from openbim_app.desenho import selecao
    f, pavs, dentro, fora = X.faixa("IFC4")
    ga = X.vista(f, "CORTE", pavs[0], origem=(0.0, 2.0, 0.0), tamanho=(10.0, 1.0, 6.0), nome="A")
    return selecao, f, ga, X.id_de(f, "in")


def test_erro_so_de_elemento_visivel_e_sem_duplicar():
    selecao, f, ga, alvo = _caso()
    ses, ex = selecao.SessaoSelecao(), _com_erro(alvo)
    s1 = selecao.selecionar(f, ga, executor=ex, sessao=ses)
    assert s1.erros_geometria == ("RuntimeError: boom",)
    assert selecao.selecionar(f, ga, executor=ex, sessao=ses).erros_geometria == ("RuntimeError: boom",)  # 2o corte da sessão: 1 só
    ocultar = ("IfcBuildingElementProxy",)
    s2 = selecao.selecionar(f, ga, executor=ex, sessao=ses, categorias_ocultas=ocultar)
    assert s2.erros_geometria == () and s2 == selecao.selecionar(f, ga, executor=ex, categorias_ocultas=ocultar)
    s3 = selecao.selecionar(f, ga, executor=ex, sessao=ses)  # volta a aparecer, uma vez
    assert s3.erros_geometria == ("RuntimeError: boom",) and s3 == selecao.selecionar(f, ga, executor=ex) == s1


def test_invalidar_ids_limpa_caixa_e_erro_so_desses_ids():
    selecao, f, ga, alvo = _caso()
    ses, ex = selecao.SessaoSelecao(), Executor()
    selecao.selecionar(f, ga, executor=_com_erro(alvo), sessao=ses)
    ses.invalidar([X.id_de(f, "lo")])  # outro elemento: o erro do alvo fica
    assert selecao.selecionar(f, ga, executor=ex, sessao=ses).erros_geometria == ("RuntimeError: boom",)
    assert [e[0] for e in ex.pedidos[-1]["elementos"]] == [X.id_de(f, "lo")]
    ses.invalidar([alvo])
    s = selecao.selecionar(f, ga, executor=ex, sessao=ses)
    assert s.erros_geometria == () and [e[0] for e in ex.pedidos[-1]["elementos"]] == [alvo]  # recalculou e sem o erro velho


def test_erro_sem_ids_vale_para_o_pedido_e_invalidar_tudo_limpa():
    selecao, f, ga, _ = _caso()
    from obim_geometria import local
    ses = selecao.SessaoSelecao()
    sem_ids = lambda p: {**local.executar(p), "erros_iterator": [{"tipo": "RuntimeError", "mensagem": "geral"}]}
    assert selecao.selecionar(f, ga, executor=sem_ids, sessao=ses).erros_geometria == ("RuntimeError: geral",)
    assert selecao.selecionar(f, ga, executor=local.executar, sessao=ses).erros_geometria == ("RuntimeError: geral",)
    ses.invalidar()
    assert selecao.selecionar(f, ga, executor=local.executar, sessao=ses).erros_geometria == ()


# ---------- 3. caixas: visitado e passagens ----------
class _Forma:
    def __init__(self, id_):
        self.id = id_

        class G:
            verts = []
        self.geometry = G()


class EspiaVazio(Espia):
    """Como `Espia`, mas: `vazio` = step ids cujo get() devolve geometria vazia; `ruim` levanta no get(); grava os ids VISITADOS por construção."""

    def __init__(self, mp, vazio=(), **k):
        super().__init__(mp, **k)
        self.vazio, self.visitados = set(vazio), []

    def __call__(self, settings, f, threads=1, *a, include=None, **k):
        env = super().__call__(settings, f, threads, *a, include=include, **k)
        self.visitados.append([])
        env.vis = self.visitados[-1]
        real_get = env.get

        def get():
            shape = real_get()
            if shape is not None:
                env.vis.append(shape.id)
                if shape.id in self.vazio:
                    return _Forma(shape.id)
            return shape
        env.get = get
        return env


def test_lote_so_de_geometrias_vazias_uma_passagem(modelo, monkeypatch):
    _, d, ped, _ = modelo
    esp = EspiaVazio(monkeypatch, vazio={e[0] for e in ped["elementos"]})
    r = _ok(_cx(ped, threads=1))
    assert r["caixas_envolventes"] == {} and sorted(r["falhas_geometria"]) == sorted(e[0] for e in ped["elementos"])
    assert r["passagens_iterator"] == len(esp.construcoes) == 1


def test_vazio_visitado_nao_e_reenviado_depois_de_aborto(modelo, monkeypatch):
    _, d, ped, _ = modelo
    ids = [e[0] for e in ped["elementos"]]
    vazio, ruim = d["M"].id(), d["Q"].id()
    esp = EspiaVazio(monkeypatch, vazio={vazio}, ruim={ruim})
    r = _ok(_cx(ped, threads=1))
    assert vazio in r["falhas_geometria"] and ruim in r["falhas_geometria"] and str(d["P"].id()) in r["caixas_envolventes"]
    visto = set()
    for (thr, inc), vis in zip(esp.construcoes, esp.visitados):
        assert not (set(inc or ()) & visto), "elemento já visitado foi reenviado ao iterator"
        visto |= {i for i in vis if i == vazio or str(i) in r["caixas_envolventes"]}
    assert ids  # sanidade


def _lote(tmp_path, n=50):
    exigir()
    f, pavs = X.estrutura("IFC4")
    els = [X.caixa(f, "IfcBuildingElementProxy", f"e{i}", i * 1.0, 0.0, 0.0, 0.5, 0.5, 0.5) for i in range(n + 1)]
    X.conter(f, pavs[0], *els)
    arq = tmp_path / "lote.ifc"
    f.write(str(arq))
    import ifcopenshell
    g = ifcopenshell.open(str(arq))
    return {"op": "caixas", "arquivo": str(arq), "threads": 1,
            "elementos": [[e.id(), e.GlobalId] for e in g.by_type("IfcBuildingElementProxy")]}


def test_elemento_ruim_na_cabeca_nao_reconstroi_iterator_por_elemento(tmp_path, monkeypatch):
    ped = _lote(tmp_path)
    import ifcopenshell
    import ifcopenshell.geom as G
    g = ifcopenshell.open(ped["arquivo"])
    s = G.settings()
    it = G.iterator(s, g, 1, include=[g.by_id(i) for i, _ in ped["elementos"]])
    assert it.initialize()
    cabeca = it.get().id  # o 1o que o iterator devolve vai ser o ruim
    del it
    esp = Espia(monkeypatch, ruim={cabeca}, teto=60)
    r = _ok(_cx(ped))
    assert r["falhas_geometria"] == [cabeca] and len(r["caixas_envolventes"]) == len(ped["elementos"]) - 1 and r["erros_iterator"]
    assert r["passagens_iterator"] == len(esp.construcoes) <= 3


# ---------- 4. árvore ----------
def test_arvore_inversao_em_y_e_erro():
    exigir()
    from obim_geometria.caixas import ArvoreCaixas
    with pytest.raises(ValueError):
        ArvoreCaixas({"1": [0, 2, 0, 1, 1, 1]})
    a = ArvoreCaixas({"1": [0, 0, 0, 1, 1, 1]})
    with pytest.raises(ValueError):
        a.cruzando((0, 2, 0), (1, 1, 1))


@pytest.mark.parametrize("lo,hi", [((float("-inf"), 0, 0), (1, 1, 1)), ((0, 0, 0), (float("inf"), 1, 1)), ((0, 0, 0), (1, float("inf"), 1)),
                                  ((0, float("-inf"), 0), (1, 1, 1)), ((float("-inf"),) * 3, (float("inf"),) * 3)])
def test_arvore_consulta_com_infinito_e_erro(lo, hi):
    exigir()
    from obim_geometria.caixas import ArvoreCaixas
    with pytest.raises(ValueError):
        ArvoreCaixas({"1": [0, 0, 0, 1, 1, 1]}).cruzando(lo, hi)


def test_ruim_no_fim_da_lista_de_entrada_nao_derruba_os_bons(tmp_path, monkeypatch):
    """O iterator anda na ordem do ARQUIVO, não na do pedido: o que quebra primeiro pode ser o último da lista; os bons não viram falha."""
    ped = _lote(tmp_path, 20)
    import ifcopenshell
    import ifcopenshell.geom as G
    g = ifcopenshell.open(ped["arquivo"])
    it = G.iterator(G.settings(), g, 1, include=[g.by_id(i) for i, _ in ped["elementos"]])
    assert it.initialize()
    cabeca = it.get().id
    del it
    ped = {**ped, "elementos": list(reversed(ped["elementos"]))}
    assert ped["elementos"][-1][0] == cabeca
    Espia(monkeypatch, ruim={cabeca}, teto=60)
    r = _ok(_cx(ped))
    assert r["falhas_geometria"] == [cabeca] and len(r["caixas_envolventes"]) == len(ped["elementos"]) - 1


def test_vazio_visitado_antes_do_aborto_conta_como_progresso(tmp_path, monkeypatch):
    """Só geometrias vazias visitadas antes do erro: ainda é progresso (nada de descartar bons por posição na lista do pedido)."""
    ped = _lote(tmp_path, 20)
    import ifcopenshell
    import ifcopenshell.geom as G
    g = ifcopenshell.open(ped["arquivo"])
    it = G.iterator(G.settings(), g, 1, include=[g.by_id(i) for i, _ in ped["elementos"]])
    assert it.initialize()
    primeiro = it.get().id
    assert it.next()
    segundo = it.get().id
    del it
    ped = {**ped, "elementos": list(reversed(ped["elementos"]))}
    EspiaVazio(monkeypatch, vazio={primeiro}, ruim={segundo}, teto=60)
    r = _ok(_cx(ped))
    assert sorted(r["falhas_geometria"]) == sorted([primeiro, segundo]) and len(r["caixas_envolventes"]) == len(ped["elementos"]) - 2


# ---------- exceção do iterator sem id confiável (mutantes do conserto) ----------
def _cabeca_e_outro(ped):
    import ifcopenshell
    import ifcopenshell.geom as G
    g = ifcopenshell.open(ped["arquivo"])
    it = G.iterator(G.settings(), g, 1, include=[g.by_id(i) for i, _ in ped["elementos"]])
    assert it.initialize()
    cabeca = it.get().id
    assert it.next()
    return cabeca, it.get().id


@pytest.mark.parametrize("msg,ordem", [
    (lambda i: "falhou sem numero", "arquivo"), (lambda i: "falhou sem numero", "inversa"),   # sem id na mensagem: só isolando se acha o ruim
    (lambda i: f"elemento {i} quebrou", "inversa"),                                           # id certo na mensagem
    (lambda i: f"erro 4 no elemento {i}", "inversa")])                                        # número solto + id certo
def test_ruim_com_ou_sem_id_na_mensagem_so_ele_vira_falha(tmp_path, monkeypatch, msg, ordem):
    ped = _lote(tmp_path, 20)
    cabeca, _ = _cabeca_e_outro(ped)
    if ordem == "inversa":
        ped = {**ped, "elementos": list(reversed(ped["elementos"]))}
    esp = Espia(monkeypatch, ruim={cabeca}, teto=80, msg=msg)
    r = _ok(_cx(ped))
    assert r["falhas_geometria"] == [cabeca] and len(r["caixas_envolventes"]) == 20 and r["erros_iterator"]
    assert all(e.get("ids", [cabeca]) == [cabeca] for e in r["erros_iterator"])  # `ids`, se vier, aponta o elemento certo
    assert r["passagens_iterator"] == len(esp.construcoes) <= 23


def test_mensagem_com_id_de_outro_elemento_nao_derruba_o_outro(tmp_path, monkeypatch):
    """A mensagem de uma exceção do iterator é texto livre: citar o step id de um elemento BOM não pode fazê-lo virar falha."""
    ped = _lote(tmp_path, 20)
    cabeca, bom = _cabeca_e_outro(ped)
    ped = {**ped, "elementos": list(reversed(ped["elementos"]))}
    Espia(monkeypatch, ruim={cabeca}, teto=80, msg=lambda i: f"erro interno perto do elemento {bom}")
    r = _ok(_cx(ped))
    assert r["falhas_geometria"] == [cabeca] and str(bom) in r["caixas_envolventes"] and len(r["caixas_envolventes"]) == 20
    assert all(e.get("ids", [cabeca]) == [cabeca] for e in r["erros_iterator"])


def test_dois_ruins_e_um_so_elemento(tmp_path, monkeypatch):
    ped = _lote(tmp_path, 10)
    cabeca, segundo = _cabeca_e_outro(ped)
    Espia(monkeypatch, ruim={cabeca, segundo}, teto=80, msg=lambda i: "falhou sem numero")
    r = _ok(_cx(ped))
    assert sorted(r["falhas_geometria"]) == sorted([cabeca, segundo]) and len(r["caixas_envolventes"]) == 9
    um = {**ped, "elementos": [ped["elementos"][0]]}
    Espia(monkeypatch, ruim={um["elementos"][0][0]}, teto=80, msg=lambda i: "falhou sem numero")
    r = _ok(_cx(um))
    assert r["falhas_geometria"] == [um["elementos"][0][0]] and r["caixas_envolventes"] == {} and r["erros_iterator"]


def test_erro_leva_ids_so_quando_o_elemento_e_certo(tmp_path, monkeypatch):
    """`ids` no erro só aparece quando se sabe o elemento (passagem de 1 elemento); com 2 ou mais na passagem, nunca um palpite."""
    ped = _lote(tmp_path, 10)
    cabeca, segundo = _cabeca_e_outro(ped)
    um = {**ped, "elementos": [e for e in ped["elementos"] if e[0] == cabeca]}
    Espia(monkeypatch, ruim={cabeca}, teto=80, msg=lambda i: "falhou sem numero")
    r = _ok(_cx(um))
    assert r["erros_iterator"] == [{"tipo": "RuntimeError", "mensagem": "falhou sem numero", "ids": [cabeca]}]  # 1 elemento: sabe quem foi
    dois = {**ped, "elementos": [e for e in reversed(ped["elementos"]) if e[0] in (cabeca, segundo)]}  # o bom vem primeiro no pedido
    r = _ok(_cx(dois))
    assert r["falhas_geometria"] == [cabeca]
    for e in r["erros_iterator"]:
        assert e.get("ids", [cabeca]) == [cabeca]  # nunca aponta o bom
    ped_i = {**ped, "elementos": list(reversed(ped["elementos"]))}
    r = _ok(_cx(ped_i))
    assert r["falhas_geometria"] == [cabeca] and {"ids": [cabeca]}.items() <= r["erros_iterator"][-1].items()  # a passagem isolada acusa o ruim


def test_falhas_na_ordem_do_pedido(tmp_path, monkeypatch):
    ped = _lote(tmp_path, 10)
    cabeca, segundo = _cabeca_e_outro(ped)
    Espia(monkeypatch, ruim={cabeca, segundo}, teto=80, msg=lambda i: "falhou sem numero")
    for ordem in (ped["elementos"], list(reversed(ped["elementos"]))):
        r = _ok(_cx({**ped, "elementos": ordem}))
        assert r["falhas_geometria"] == [e[0] for e in ordem if e[0] in (cabeca, segundo)]


def test_varios_abortos_de_lote_sem_ruim_sao_todos_registrados_em_ordem(modelo, monkeypatch):
    _, _, ped, _ = modelo
    ref = _ok(_cx(ped, threads=1))
    esp = Espia(monkeypatch, falhar_na_1a=2)  # as 2 primeiras passagens abortam no 2o get(); a 3a fecha
    r = _ok(_cx(ped, threads=1))
    assert r["caixas_envolventes"] == ref["caixas_envolventes"] and r["falhas_geometria"] == ref["falhas_geometria"]
    assert [e["mensagem"] for e in r["erros_iterator"]] == ["iterator abortou 0", "iterator abortou 1"]
    assert all("ids" not in e for e in r["erros_iterator"]) and r["passagens_iterator"] == len(esp.construcoes) == 3
