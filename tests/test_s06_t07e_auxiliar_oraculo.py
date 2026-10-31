# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo F0-S06-T07e0, parte 1 (T07e1): cliente do processo auxiliar de desenho. Especificação: `cards/F0-S06/F0-S06-T07e-especificacao.md` (§2, §3, §5 casos 1 a 6, 8, 9, 10, 11).
Não editar este arquivo nem `s06_t07e_aux.py` na implementação; quem tira o `@AINDA_NAO_E1` (xfail estrito, só por ImportError) é o autor do oráculo, em commit próprio, depois da e1.
Decisões do PO adotadas até ele responder: P1 = (a) o pedido grava uma cópia INTEIRA do modelo na hora de `preparar`; P2 = (a) 1 filho por pedido, nasce e morre.
CONTRATO (sem Qt, sem rede). [P] = escolha do oráculo que a especificação não fixa, provisória até o líder/Opus confirmar.
`geometria/obim_geometria/processo.py` (só biblioteca padrão no topo): `PROTOCOLO = 1`, `entrada(tx, pedido_json)` (alvo do `spawn`). `local.py`: `executar(pedido: dict) -> dict` (mesmo processo, só testes).
Um executor é `executor(pedido: dict) -> dict` e devolve a resposta CRUA (`{"ok": true, ...}` ou `{"ok": false, "erro": {"tipo", "mensagem", "rastro"}}`); o pai trata os dois executores igual.
`openbim_app/desenho/auxiliar.py`: `LIMITE_PADRAO_S == 180`; `preparar(ifc, pedido) -> Preparado`: `pedido` = o JSON da especificação §2 SEM `arquivo`/`protocolo` ([P] `protocolo` fornecido é
mantido, o ausente vira 1; `threads` ausente vira `min(8, os.cpu_count() or 1)`); grava a CÓPIA INTEIRA (`ifc.write`) em `tempfile.gettempdir()/obim-desenho-XXXX/` na hora de preparar e devolve
`Preparado` com `.pedido` (dict JSON puro, com `arquivo` absoluto), `.pasta` (Path), `.fechar()` (apaga a pasta; repetido não falha) e uso em `with`. Erro de protocolo (versão != 1) sobe de `preparar` ou
de `executar` (`ProtocoloInvalido`). `executar(preparado, *, limite_s=LIMITE_PADRAO_S, cancelar=None, executor=None) -> dict`: a resposta do executor se `ok`, senão levanta o erro tipado; vale
mais de um `executar` por `Preparado`. `executor=None` = filho `spawn` real (1 por pedido, no máximo 1 vivo por vez; o 2º pedido espera, a espera não conta no limite). Fim de qualquer caminho: filho
morto (`kill` + `join`), canal fechado; a pasta só sai no `fechar()`. Erros (todos `ErroAuxiliar(RuntimeError)`): `AuxiliarCaiu` (`.codigo_saida`, `.fase`), `AuxiliarEstourouTempo` (`.limite_s`, `.fase`),
`DesenhoCancelado`, `FalhaNoAuxiliar` (`.tipo`, `.mensagem`, `.rastro`; `str()` = `"<tipo>: <mensagem>"`), `ArquivoDivergente`, `ProtocoloInvalido`. Op `caixas`: resposta `{"ok": true,
"caixas_envolventes": {"<id>": [xmin, ymin, zmin, xmax, ymax, zmax]} (metros, mundo), "falhas_geometria": [ids]}`; o filho confere cada `[id, GlobalId]` (senão `ArquivoDivergente`).
Ganchos do filho (variáveis de ambiente lidas no filho, depois de `pronto`): `OBIM_TESTE_AUX_DORMIR_S`, `OBIM_TESTE_AUX_SAIR` (`os._exit`), `OBIM_TESTE_AUX_SEGV=1` (queda de verdade), `OBIM_TESTE_AUX_LEVANTAR=<texto>`.
Caso 10 (trava ampliada) não tem marcador: passa hoje e tem de continuar passando."""
import json
import multiprocessing
import os
import re
import tempfile
import threading
import time
from pathlib import Path

import pytest
import s06_t07e_aux as T

APP = Path(__file__).resolve().parent.parent / "app"
AINDA_NAO_E1 = pytest.mark.xfail(strict=True, raises=ImportError, reason="T07e1: auxiliar e obim_geometria ainda não existem")


def _x():
    from openbim_app.desenho import auxiliar  # primeira linha de cada caso @AINDA_NAO_E1: hoje é ela que dá o xfail
    return auxiliar


def _loc():
    import obim_geometria.local as L
    return L


@pytest.fixture
def tmp_aux(tmp_path, monkeypatch):
    pasta = tmp_path / "tmp"
    pasta.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(pasta))
    return pasta


def _sobras(pasta):
    return sorted(p.name for p in pasta.glob("obim-desenho-*"))


def _pedido(f, op="caixas", *nomes, **mais):
    return {"op": op, "elementos": T.elementos(f, *(nomes or ("P", "M", "falha"))), **mais}


def _limpo(pasta, f, antes):  # processo do teste vivo e intacto, nenhum filho vivo, nada em /tmp
    assert f.to_string() == antes
    assert multiprocessing.active_children() == []
    assert _sobras(pasta) == []


@AINDA_NAO_E1
@pytest.mark.parametrize("esq,off,base,k", T.MODELOS)
def test_caso1_filho_real_igual_ao_local_e_numeros_certos(tmp_aux, esq, off, base, k):
    X, L = _x(), _loc()
    f, d = T.modelo(esq, off, base, k)
    with X.preparar(f, _pedido(f)) as p:
        real, loc = X.executar(p), X.executar(p, executor=L.executar)
    assert real == loc
    assert real["falhas_geometria"] == [d["falha"].id()]
    cx = real["caixas_envolventes"]
    assert set(cx) == {str(d["P"].id()), str(d["M"].id())}
    assert cx[str(d["P"].id())] == pytest.approx([off[0], off[1], base, off[0] + 5.0, off[1] + 0.25, base + 3.0], abs=1e-6)
    assert cx[str(d["M"].id())] == pytest.approx([off[0] + 1.0, off[1] + 2.0, base, off[0] + 1.5, off[1] + 2.5, base + 1.5], abs=1e-6)


@AINDA_NAO_E1
@pytest.mark.parametrize("real", [True, False])
def test_caso2_fotografia_do_momento_do_preparar(tmp_aux, real):
    X, L = _x(), _loc()
    f, d = T.modelo()
    with X.preparar(f, _pedido(f, "caixas", "P", "Q")) as p:
        idp = d["P"].id()
        f.remove(d["P"])  # o modelo aberto muda DEPOIS do preparar; o filho usa a cópia
        r = X.executar(p) if real else X.executar(p, executor=L.executar)
    assert str(idp) in r["caixas_envolventes"]


@AINDA_NAO_E1
@pytest.mark.parametrize("gancho,valor", [("OBIM_TESTE_AUX_SAIR", "3"), ("OBIM_TESTE_AUX_SEGV", "1")])
def test_caso3_queda_do_filho_nao_derruba_a_janela(tmp_aux, monkeypatch, gancho, valor):
    X = _x()
    f, _ = T.modelo()
    antes = f.to_string()
    monkeypatch.setenv(gancho, valor)
    t0 = time.monotonic()
    with X.preparar(f, _pedido(f)) as p:
        with pytest.raises(X.AuxiliarCaiu) as e:
            X.executar(p)
    assert time.monotonic() - t0 < 10
    assert isinstance(e.value, RuntimeError) and e.value.codigo_saida != 0
    if valor == "3":
        assert e.value.codigo_saida == 3
    _limpo(tmp_aux, f, antes)


@AINDA_NAO_E1
def test_caso4_limite_de_tempo_total_mata_o_filho(tmp_aux, monkeypatch):
    X = _x()
    f, _ = T.modelo()
    antes = f.to_string()
    monkeypatch.setenv("OBIM_TESTE_AUX_DORMIR_S", "60")
    t0 = time.monotonic()
    with X.preparar(f, _pedido(f)) as p:
        with pytest.raises(X.AuxiliarEstourouTempo) as e:
            X.executar(p, limite_s=2)
    assert 2 <= time.monotonic() - t0 <= 7 and e.value.limite_s == 2
    _limpo(tmp_aux, f, antes)


@AINDA_NAO_E1
def test_caso5_cancelar_no_meio(tmp_aux, monkeypatch):
    X = _x()
    f, _ = T.modelo()
    antes = f.to_string()
    monkeypatch.setenv("OBIM_TESTE_AUX_DORMIR_S", "60")
    ev = threading.Event()
    threading.Timer(1.0, ev.set).start()
    t0 = time.monotonic()
    with X.preparar(f, _pedido(f)) as p:
        with pytest.raises(X.DesenhoCancelado):
            X.executar(p, cancelar=ev)
    assert time.monotonic() - t0 < 4
    _limpo(tmp_aux, f, antes)


@AINDA_NAO_E1
def test_caso6_erro_no_filho_chega_tipado(tmp_aux, monkeypatch):
    X = _x()
    f, _ = T.modelo()
    monkeypatch.setenv("OBIM_TESTE_AUX_LEVANTAR", "xyz")
    with X.preparar(f, _pedido(f)) as p:
        with pytest.raises(RuntimeError, match="xyz") as e:
            X.executar(p)
    err = e.value
    assert isinstance(err, X.FalhaNoAuxiliar) and err.tipo == "RuntimeError" and "xyz" in err.mensagem and err.rastro.strip()
    assert str(err) == f"RuntimeError: {err.mensagem}"


@AINDA_NAO_E1
def test_caso8_divergencia_de_id_e_protocolo(tmp_aux):
    X, L = _x(), _loc()
    f, d = T.modelo()
    ruim = {"op": "caixas", "elementos": [[d["P"].id(), d["M"].GlobalId]]}  # id de um, GlobalId de outro
    with X.preparar(f, ruim) as p:
        with pytest.raises(X.ArquivoDivergente):
            X.executar(p)
        with pytest.raises(X.ArquivoDivergente):
            X.executar(p, executor=L.executar)
    for ex in (None, L.executar):
        with pytest.raises(X.ProtocoloInvalido):
            with X.preparar(f, {**_pedido(f), "protocolo": 2}) as p:
                X.executar(p, executor=ex)


@AINDA_NAO_E1
def test_caso11_json_puro_threads_e_um_filho_por_vez(tmp_aux, monkeypatch):
    X, L = _x(), _loc()
    f, _ = T.modelo()
    with X.preparar(f, _pedido(f)) as p:
        assert json.loads(json.dumps(p.pedido)) == p.pedido and p.pedido["protocolo"] == 1
        assert p.pedido["threads"] == min(8, os.cpu_count() or 1) and Path(p.pedido["arquivo"]).is_absolute()
        r = X.executar(p, executor=L.executar)
        assert json.loads(json.dumps(r)) == r
        monkeypatch.setenv("OBIM_TESTE_AUX_DORMIR_S", "2")
        picos, fim, ok = [], threading.Event(), []
        vigia = threading.Thread(target=lambda: [picos.append(len(multiprocessing.active_children())) or time.sleep(0.05) for _ in iter(fim.is_set, True)])
        vigia.start()
        ths = [threading.Thread(target=lambda: ok.append(bool(X.executar(p)["caixas_envolventes"]))) for _ in range(2)]
        t0 = time.monotonic()
        [t.start() for t in ths]
        [t.join(60) for t in ths]
        fim.set()
        vigia.join()
    assert ok == [True, True] and max(picos) <= 1 and time.monotonic() - t0 >= 3.5


@AINDA_NAO_E1
def test_caso9_janela_nao_carrega_geometria_com_filho_real(tmp_path):
    _x()
    f, _ = T.modelo()
    assert T.janela_limpa(f, "caixas", None, tmp_path) == {"ok": True, "ruins": []}


# ---- caso 10: trava ampliada de app/ (sem marcador; o teste da regra 9 da S04 não muda) ----
PROIBIDO = re.compile(r"ifcopenshell\.geom|from ifcopenshell import geom|ifcopenshell\.draw|serializers|\.iterator\(|obim_geometria\.(?!processo\b)|from obim_geometria import|import obim_geometria\b(?!\.processo)")


def proibidos(raiz):
    return [f"{p.relative_to(raiz)}:{i}" for p in Path(raiz).rglob("*.py")
            for i, x in enumerate(p.read_text(encoding="utf-8").splitlines(), 1) if PROIBIDO.search(x)]


def test_caso10_app_sem_geometria_nem_serializador_nem_iterator():
    assert proibidos(APP) == []


@pytest.mark.parametrize("linha,barra", [("import ifcopenshell.geom", 1), ("from ifcopenshell import geom", 1), ("# ifcopenshell.draw", 1), ("x = G.serializers.svg", 1),
                                         ("it = G.iterator(s, f)", 1), ("from obim_geometria.caixas import x", 1), ("from obim_geometria import desenho", 1),
                                         ("import obim_geometria.local", 1), ("from obim_geometria.processo import entrada", 0), ("import ifcopenshell.ifcopenshell_wrapper as W", 0),
                                         ("W.schema_by_name('IFC4')", 0), ("import obim_geometria.processo", 0)])
def test_caso10_o_verificador_pega_e_deixa_passar(tmp_path, linha, barra):
    (tmp_path / "a.py").write_text(linha + "\n", encoding="utf-8")
    assert len(proibidos(tmp_path)) == barra
