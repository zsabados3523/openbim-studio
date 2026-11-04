# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo do F0-S06-T05d: bug 2 e bug 4 do LOTE_OPUS_75 (parte T05). Contrato base: `test_s05_t07_par_oraculo.py` (gravar_par, E1 a E10) e
`test_s05_t09b_autosave_oraculo.py` (Autosave). Decisões [P: recomendação, o PO confirma]:
BUG 2. A troca de UM dos arquivos do par falha (ex.: `.obim` em uso, depois de esgotar as tentativas de `gravacao_atomica`), mas o resolvedor, que
`gravar_par` chama na hora, CONCLUI o par (`Casa.ifc` e `Casa.obim` novos). Isso é SUCESSO: `gravar_par` NÃO levanta; devolve os dois `Gravado` (caminho,
sha256 e tamanho dos arquivos que estão no disco); `ao_concluir(seq)` roda UMA vez, com o `gravacao.json` ainda lá; depois o `gravacao.json` some; o
carimbo (`Revisao` + 1) fica; nada de temporário. Vale para a troca do IFC e para a do `.obim`. Se o resolvedor NÃO conclui (troca recusada de vez), vale
o contrato antigo (levanta citando o temporário; `gravacao.json` fica; teste 09 da S05).
BUG 4. `ao_concluir` do usuário (no autosave: `Diario.zerar`) pode levantar quando é chamado de dentro do `except` de `gravar_par` (resolvedor na hora).
Contrato: (a) o erro do callback NÃO pode sumir: `gravar_par` levanta e o erro do callback está na exceção levantada ou na sua cadeia
(`__cause__`/`__context__`), nunca engolido; (b) o par fica novo e o `gravacao.json` fica, para o resolvedor da próxima abertura terminar (o carimbo não
volta, porque o par é novo); (c) o callback é o MESMO dos dois caminhos: no autosave o resolvedor do `except` usa o `ao_concluir` do autosave (senão o
diário não zera e o `gravacao.json` some sem ninguém ter zerado: bug); (d) no `Autosave.salvar` a troca que falha e se resolve sozinha dá `True`, zera o
diário uma vez e a 2ª chamada dá `False`; se o `zerar` levanta, `salvar` levanta (erro visível), o `gravacao.json` do `autosave/` fica e o `salvar`
seguinte conclui (`zerar_para_atual`) e grava, sem tocar no par do usuário. Marcadores retirados (T05d implementada);
casos que o código atual já cumpre NÃO levam a marca. Não editar; só o autor retira os marcadores."""
import errno
import time

import pytest
import s05_conteudo_aux as R
import s05_t07_aux as X
from s05_conteudo_aux import _limpa, base_ifc  # noqa: F401
from s05_t05_aux import sha
from test_s05_t06_gravacao_atomica_oraculo import TrocaRecusada
from test_s05_t07_par_oraculo import LADO, SEQ, proj  # noqa: F401
from test_s05_t09b_autosave_oraculo import CenaAuto, fabrica, local  # noqa: F401



def na_cadeia(exc, pred):
    visto, pilha = set(), [exc]
    while pilha:
        e = pilha.pop()
        if e is None or id(e) in visto:
            continue
        visto.add(id(e))
        if pred(e):
            return True
        pilha += [e.__cause__, e.__context__]
    return False


def boom(*a, **k):
    raise OSError(errno.ENOSPC, "callback do usuario falhou (teste)")


def eh_boom(e):
    return isinstance(e, OSError) and e.errno == errno.ENOSPC and "callback do usuario" in str(e)


def tentativas():
    import openbim_app.gravacao_atomica as GA
    return GA.TENTATIVAS_TROCA


# ---------- bug 2 ----------
@pytest.mark.parametrize("alvo", ["obim", "ifc"])
def test_01_troca_que_falha_e_o_resolvedor_conclui_e_sucesso(proj, monkeypatch, alvo):  # noqa: F811
    proj.gravar()
    um = proj.antigo()
    proj.tx(2)
    novo = proj.novo(2)
    proj.chamadas.clear()
    monkeypatch.setattr(time, "sleep", lambda s: None)
    arq = proj.destino.with_suffix(".obim") if alvo == "obim" else proj.destino
    with pytest.MonkeyPatch.context() as mp:
        recusa = TrocaRecusada(arq, tentativas())  # esgota as tentativas de UMA confirmação; o resolvedor passa
        mp.setattr(__import__("os"), "replace", recusa)
        gravados = proj.gravar()  # não levanta
    assert recusa.tentativas > tentativas(), "o teste não exercitou a falha de troca"
    assert len(gravados) == 2
    gi, go = gravados
    assert (gi.caminho, go.caminho) == (proj.destino, proj.destino.with_suffix(".obim"))
    assert (gi.sha256, gi.tamanho) == (sha(proj.destino), proj.destino.stat().st_size)
    assert (go.sha256, go.tamanho) == (sha(go.caminho), go.caminho.stat().st_size)
    assert X.estado_par(proj.destino, um, novo, proj.pasta) == ("novo", []), "par não ficou novo e limpo"
    assert [c[:2] for c in proj.chamadas] == [(SEQ, True)], f"ao_concluir tem de rodar uma vez, com o gravacao.json: {[c[:2] for c in proj.chamadas]}"
    assert not list(proj.pasta.glob("gravacao*")) and proj.pset() == (LADO, 2), "gravacao.json sobrou ou o carimbo voltou"


def test_02_sucesso_pela_via_do_resolvedor_na_primeira_gravacao_do_par(proj, monkeypatch):  # noqa: F811
    monkeypatch.setattr(time, "sleep", lambda s: None)
    alvo = proj.destino.with_suffix(".obim")  # não existe ainda: sem .bak
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(__import__("os"), "replace", TrocaRecusada(alvo, tentativas()))
        gravados = proj.gravar()
    assert len(gravados) == 2 and X.estado_par(proj.destino, None, proj.novo(1), proj.pasta) == ("novo", [])
    assert [c[0] for c in proj.chamadas] == [SEQ] and proj.pset() == (LADO, 1)


def test_03_troca_recusada_de_vez_continua_levantando_e_mantem_o_diario(proj, monkeypatch):  # noqa: F811  (cumprido hoje; trava a regra antiga)
    proj.gravar()
    proj.tx(2)
    proj.chamadas.clear()
    monkeypatch.setattr(time, "sleep", lambda s: None)
    with pytest.MonkeyPatch.context() as mp, pytest.raises(Exception) as ei:
        mp.setattr(__import__("os"), "replace", TrocaRecusada(proj.destino.with_suffix(".obim"), 10**6))
        proj.gravar()
    assert "Casa.obim.tmp" in str(ei.value)
    assert (proj.pasta / "gravacao.json").exists() and proj.chamadas == []


# ---------- bug 4: gravar_par ----------
def test_04_callback_que_levanta_no_resolvedor_do_except_nao_some(proj, monkeypatch):  # noqa: F811
    proj.gravar()
    um = proj.antigo()
    proj.tx(2)
    novo = proj.novo(2)
    proj.chamadas.clear()
    monkeypatch.setattr(time, "sleep", lambda s: None)
    with pytest.MonkeyPatch.context() as mp, pytest.raises(Exception) as ei:
        mp.setattr(__import__("os"), "replace", TrocaRecusada(proj.destino.with_suffix(".obim"), tentativas()))
        proj.gravar(ao_concluir=boom)
    assert na_cadeia(ei.value, eh_boom), f"o erro do callback sumiu; levantou {ei.value!r}"
    assert (proj.pasta / "gravacao.json").exists(), "o gravacao.json sumiu sem o callback ter terminado"
    assert X.estado_par(proj.destino, um, novo)[0:2] == ("novo", []) and proj.pset() == (LADO, 2), "o par tem de ficar novo e o carimbo também"
    gp = __import__("openbim_app.gravacao_par", fromlist=["x"])
    gp.resolver_gravacao_pendente(pasta_projeto=proj.pasta, destino=proj.destino, ao_concluir=proj.ao)  # a próxima abertura termina
    assert [c[0] for c in proj.chamadas] == [SEQ] and X.estado_par(proj.destino, um, novo, proj.pasta) == ("novo", [])


def test_05_callback_que_levanta_no_caminho_normal_sobe_o_erro_dele(proj):  # noqa: F811  (cumprido hoje; mata mutante que engole)
    proj.gravar()
    proj.tx(2)
    with pytest.raises(OSError) as ei:
        proj.gravar(ao_concluir=boom)
    assert eh_boom(ei.value), f"mascarou o erro do callback: {ei.value!r}"
    assert (proj.pasta / "gravacao.json").exists() and proj.pset() == (LADO, 2)


def test_06_callback_que_levanta_baseexception_nao_e_engolido(proj):  # noqa: F811  (cumprido hoje)
    proj.gravar()
    proj.tx(2)

    def para(seq):
        raise KeyboardInterrupt
    with pytest.raises(KeyboardInterrupt):
        proj.gravar(ao_concluir=para)
    assert (proj.pasta / "gravacao.json").exists()


# ---------- bug 4: Autosave ----------
def _tenta(c):
    try:
        return c.auto.salvar()
    except Exception as e:  # noqa: BLE001
        return e


def test_07_autosave_troca_que_se_resolve_sozinha_da_true_zera_e_nao_repete(fabrica, monkeypatch):  # noqa: F811
    from test_s05_t09b_autosave_oraculo import D, _base
    monkeypatch.setattr(time, "sleep", lambda s: None)
    c = fabrica()
    par = (sha(c.casa), sha(c.obim))
    c.tx(1)
    with pytest.MonkeyPatch.context() as mp:
        recusa = TrocaRecusada(c.auto_obim, tentativas())
        mp.setattr(__import__("os"), "replace", recusa)
        ok = _tenta(c)
    assert recusa.tentativas > tentativas(), "o teste não exercitou a falha de troca"
    assert ok is True, "troca que se resolveu sozinha tem de contar como autosave feito"
    base, resto = _base(c)
    assert base["seq"] == 1 and resto == [], "o diário não foi zerado uma vez"
    assert not (c.pasta_auto / "gravacao.json").exists() and c.auto_ifc.exists() and c.auto_obim.exists()
    assert c.auto.salvar() is False, "ficou sujo: a transação seria regravada"
    assert (sha(c.casa), sha(c.obim)) == par, "o par do usuário mudou"
    assert D.ler_diario(str(c.diario.caminho))[1] == []


def test_08_autosave_zerar_que_levanta_no_resolvedor_do_except_fica_visivel(fabrica, monkeypatch):  # noqa: F811
    monkeypatch.setattr(time, "sleep", lambda s: None)
    c = fabrica()
    c.tx(1)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(c.diario, "zerar", boom)
        mp.setattr(__import__("os"), "replace", TrocaRecusada(c.auto_obim, tentativas()))
        with pytest.raises(Exception) as ei:
            c.auto.salvar()
    assert na_cadeia(ei.value, eh_boom), f"o erro do zerar sumiu; levantou {ei.value!r}"


def test_09_autosave_zerar_que_levanta_deixa_o_gravacao_json_e_o_proximo_salvar_conclui(fabrica, monkeypatch):  # noqa: F811
    from test_s05_t09b_autosave_oraculo import _base
    monkeypatch.setattr(time, "sleep", lambda s: None)
    c = fabrica()
    par = (sha(c.casa), sha(c.obim))
    c.tx(1)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(c.diario, "zerar", boom)
        mp.setattr(__import__("os"), "replace", TrocaRecusada(c.auto_obim, tentativas()))
        with pytest.raises(Exception):
            c.auto.salvar()
    assert (c.pasta_auto / "gravacao.json").exists(), "o gravacao.json sumiu e o diário não foi zerado"
    assert c.auto.salvar() in (True, False)  # o seguinte (zerar de volta ao normal) conclui a pendência
    base, resto = _base(c)
    assert base["seq"] == 1 and resto == [], "o diário não foi zerado depois da recuperação"
    assert not (c.pasta_auto / "gravacao.json").exists() and c.auto.salvar() is False
    assert (sha(c.casa), sha(c.obim)) == par, "o par do usuário mudou"


def test_10_autosave_zerar_que_levanta_no_caminho_normal_propaga_e_mantem_sujo(fabrica, monkeypatch):  # noqa: F811  (cumprido hoje)
    c = fabrica()
    c.tx(1)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(c.diario, "zerar", boom)
        with pytest.raises(OSError) as ei:
            c.auto.salvar()
    assert eh_boom(ei.value)
    assert (c.pasta_auto / "gravacao.json").exists()
    assert c.auto.salvar() in (True, False)
    assert not (c.pasta_auto / "gravacao.json").exists()
