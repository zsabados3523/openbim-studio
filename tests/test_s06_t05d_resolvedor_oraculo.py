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
    assert (gi.bak, go.bak) == (proj.destino.with_name("Casa.ifc.bak"), proj.destino.with_name("Casa.obim.bak")), (gi.bak, go.bak)
    assert gi.bak.read_bytes() == um.ifc and go.bak.read_bytes() == um.obim, "o .bak não é o par de antes"
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
    assert gravados[0].bak is None and gravados[1].bak is None, "primeira gravação não tem .bak"
    assert (gravados[0].caminho, gravados[1].caminho) == (proj.destino, alvo)
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
    assert eh_boom(ei.value), f"sobe o erro do callback (do resolvedor), não o da troca: {ei.value!r}"
    import openbim_app.gravacao_atomica as GA
    assert isinstance(ei.value.__cause__, GA.FalhaGravacao) and "Casa.obim" in str(ei.value.__cause__), "falta `from erro` (a falha original é a causa)"
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
    assert c.auto.salvar() is True  # o seguinte (zerar de volta ao normal) conclui a pendência e grava
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
    assert c.auto.salvar() is True
    assert not (c.pasta_auto / "gravacao.json").exists()


# ---------- achados do Argon (T05e) ----------
INTERRUPCOES = [KeyboardInterrupt, SystemExit]


def _interrompe_na_2a_confirmacao(mp, exc):  # a troca do .obim é interrompida; o temporário fica, o resolvedor consegue concluir
    import openbim_app.gravacao_atomica as GA
    real, n = GA.confirmar, [0]

    def confirmar(prep):
        n[0] += 1
        if n[0] == 2:
            raise exc()
        return real(prep)
    mp.setattr(GA, "confirmar", confirmar)


def _prepara(proj, monkeypatch):
    proj.gravar()
    um = proj.antigo()
    proj.tx(2)
    novo = proj.novo(2)
    proj.chamadas.clear()
    monkeypatch.setattr(time, "sleep", lambda s: None)
    return um, novo


@pytest.mark.parametrize("exc", INTERRUPCOES, ids=lambda e: e.__name__)
def test_11_interrupcao_com_o_resolvedor_concluindo_e_relancada(proj, monkeypatch, exc):  # noqa: F811
    """Achado 1: Ctrl+C (KeyboardInterrupt/SystemExit) depois do gravacao.json nunca vira sucesso: relança. O par pode terminar novo."""
    um, novo = _prepara(proj, monkeypatch)
    with pytest.MonkeyPatch.context() as mp, pytest.raises(exc):
        _interrompe_na_2a_confirmacao(mp, exc)
        proj.gravar()
    import openbim_app.gravacao_par as gp
    gp.resolver_gravacao_pendente(pasta_projeto=proj.pasta, destino=proj.destino, ao_concluir=proj.ao)  # a próxima abertura (idempotente)
    assert X.estado_par(proj.destino, um, novo, proj.pasta) == ("novo", [])
    assert [c[0] for c in proj.chamadas] == [SEQ], "ao_concluir tem de rodar exatamente uma vez no total"


@pytest.mark.parametrize("exc", INTERRUPCOES, ids=lambda e: e.__name__)
def test_12_interrupcao_original_prevalece_sobre_erro_do_resolvedor(proj, monkeypatch, exc):  # noqa: F811
    """Achado 2: erro original BaseException + resolvedor que levanta Exception (callback): sobe a interrupção, não a Exception."""
    um, novo = _prepara(proj, monkeypatch)
    with pytest.MonkeyPatch.context() as mp:
        _interrompe_na_2a_confirmacao(mp, exc)
        with pytest.raises(BaseException) as ei:
            proj.gravar(ao_concluir=boom)
    assert type(ei.value) is exc, f"a interrupção foi trocada por {ei.value!r}"
    assert (proj.pasta / "gravacao.json").exists(), "o callback não terminou: o gravacao.json fica"
    assert X.estado_par(proj.destino, um, novo)[0:2] == ("novo", [])


def test_13_unlink_do_gravacao_json_falha_depois_do_ao_concluir_nao_repete_o_callback(proj, monkeypatch):  # noqa: F811
    """Achado 3. Contrato [P: recomendação]: par novo no disco e ao_concluir já rodou; só a limpeza do gravacao.json falhou (ex.: PermissionError no
    Windows). `gravar_par` NÃO chama o callback de novo (nem pelo resolvedor do except). Pode concluir ou levantar; o par fica novo e o carimbo fica.
    Recomendado: tentar só apagar o gravacao.json (sem callback) e concluir; se ainda falhar, levantar com o gravacao.json no lugar."""
    import os
    um, novo = _prepara(proj, monkeypatch)
    real, falhou = os.unlink, [0]

    def unlink(p, *a, **k):
        if str(p).endswith("gravacao.json") and not falhou[0]:
            falhou[0] = 1
            raise PermissionError(errno.EACCES, "arquivo em uso (teste)", str(p))
        return real(p, *a, **k)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(os, "unlink", unlink)
        try:
            proj.gravar()
        except Exception:  # noqa: BLE001  (levantar também vale)
            pass
    assert falhou[0] == 1, "o teste não exercitou a falha do unlink"
    assert [c[0] for c in proj.chamadas] == [SEQ], f"ao_concluir rodou {len(proj.chamadas)} vezes"
    assert X.estado_par(proj.destino, um, novo)[0:2] == ("novo", []) and proj.pset() == (LADO, 2)


# ---------- limpeza do gravacao.json (etapa "trocado") ----------
def _unlink_falho(os_, falhas, exc_fabrica):  # falha as `falhas` primeiras vezes em que apaga o gravacao.json
    real, n = os_.unlink, [0]

    def unlink(p, *a, **k):
        if str(p).endswith("gravacao.json") and n[0] < falhas:
            n[0] += 1
            raise exc_fabrica(str(p))
        return real(p, *a, **k)
    return unlink, n


def test_14_unlink_do_gravacao_json_falha_sempre_levanta_com_o_callback_uma_vez(proj, monkeypatch):  # noqa: F811
    import os
    um, novo = _prepara(proj, monkeypatch)
    unlink, n = _unlink_falho(os, 10**6, lambda p: PermissionError(errno.EACCES, "em uso (teste)", p))
    with pytest.MonkeyPatch.context() as mp, pytest.raises(PermissionError):
        mp.setattr(os, "unlink", unlink)
        proj.gravar()
    assert [c[0] for c in proj.chamadas] == [SEQ], f"ao_concluir rodou {len(proj.chamadas)} vezes"
    assert (proj.pasta / "gravacao.json").exists(), "a pendência tem de ficar para a próxima abertura"
    assert X.estado_par(proj.destino, um, novo)[0:2] == ("novo", []) and proj.pset() == (LADO, 2), "par ou carimbo mudou"


@pytest.mark.parametrize("exc", INTERRUPCOES, ids=lambda e: e.__name__)
def test_15_interrupcao_no_unlink_do_gravacao_json_nao_vira_sucesso(proj, monkeypatch, exc):  # noqa: F811
    import os
    um, novo = _prepara(proj, monkeypatch)
    unlink, n = _unlink_falho(os, 1, lambda p: exc())
    with pytest.MonkeyPatch.context() as mp, pytest.raises(exc):
        mp.setattr(os, "unlink", unlink)
        proj.gravar()
    assert n[0] == 1 and [c[0] for c in proj.chamadas] == [SEQ]
    assert X.estado_par(proj.destino, um, novo)[0:2] == ("novo", [])


def test_16_unlink_falha_uma_vez_conclui_e_nao_deixa_gravacao(proj, monkeypatch):  # noqa: F811  (contrato recomendado do achado 3)
    import os
    um, novo = _prepara(proj, monkeypatch)
    unlink, n = _unlink_falho(os, 1, lambda p: PermissionError(errno.EACCES, "em uso (teste)", p))
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(os, "unlink", unlink)
        gravados = proj.gravar()
    assert n[0] == 1 and len(gravados) == 2 and [c[0] for c in proj.chamadas] == [SEQ]
    assert X.estado_par(proj.destino, um, novo, proj.pasta) == ("novo", []) and proj.pset() == (LADO, 2)
