# SPDX-License-Identifier: AGPL-3.0-or-later
"""Reforço do oráculo do F0-S05-T09b (revisão da implementação, lote 84). Usa os auxiliares de `test_s05_t09b_autosave_oraculo.py`.
Quem tira os marcadores é o autor do oráculo, depois da correção. Não editar na implementação.
CONTRATO (decisões do líder, além do oráculo principal):
- R1 `parar()`: espera a thread terminar SEM prazo (join sem timeout); cada thread tem o seu próprio sinal de parada. Depois de `parar()` não resta
  thread do Autosave viva, e `iniciar()` depois de `parar()` cria exatamente 1 thread (a antiga não revive).
- R2 o `obim_sha256` que vai à base nova do diário é o do lateral do RETRATO (capturado dentro do `ler()`, junto do seq), nunca o do lateral na hora
  do `ao_concluir`. Vale também quando o resolvedor conclui a gravação fora do `ler()` (caminho de erro do `gravar_par`).
- R3 (sem teste novo aqui): `salvar()` propaga o erro de pendência irresolúvel do `gravar_par`; a chamada prévia a `resolver_gravacao_pendente` em
  `autosave.py` é redundante e sai.
Sincronização: só `Event` e `join`, sempre com prazo do lado do teste; o prazo de 15 s do R1 é maior que qualquer prazo interno plausível (o defeito
achado usava 10 s) e só é gasto pela implementação correta, que fica parada até o caso soltar o `salvar()` lento."""
import errno, hashlib, os, threading  # noqa: E401
from pathlib import Path
import pytest
import s05_conteudo_aux as R, s05_t07_aux as X7  # noqa: E401
from openbim_app.lateral import Lateral
from s05_conteudo_aux import _limpa, base_ifc  # noqa: F401
from s05_t05_aux import igual, sha
from test_s05_t05_diario_oraculo import _sem_injecao, local  # noqa: F401
from test_s05_t09b_autosave_oraculo import _base, _rec_auto, fabrica  # noqa: F401


def _threads_novas(c, antes):  # threads novas, fora o Timer do fsync do diário
    return {t for t in threading.enumerate() if getattr(getattr(t, "function", None), "__self__", None) is not c.diario} - antes


def test_r1_parar_espera_salvar_lento_e_iniciar_de_novo_cria_uma_thread(fabrica, monkeypatch):
    # M: join(timeout=...) que volta com a thread viva; _thread=None com a thread viva; Event de parada reaproveitado (a antiga revive no iniciar())
    c = fabrica(intervalo_s=0.01)
    real, write_real = type(c.auto).salvar, R.ifcopenshell.file.write
    dentro, solta, terminou, salvou2 = threading.Event(), threading.Event(), threading.Event(), threading.Event()
    voltou, fase = {}, ["lenta"]

    def write_lento(self, caminho, *a, **k):  # o 1º retrato da thread fica parado até o caso soltar
        if threading.current_thread() is not threading.main_thread() and fase[0] == "lenta" and not dentro.is_set():
            dentro.set()
            assert solta.wait(timeout=60), "o caso não soltou o salvar() lento"
        return write_real(self, caminho, *a, **k)

    def espiao(*a, **k):  # o salvar() que a thread chama
        r = real(c.auto, *a, **k)
        if threading.current_thread() is not threading.main_thread():
            if fase[0] == "lenta" and r:
                terminou.set()
            elif fase[0] == "segunda" and r:
                salvou2.set()
        return r

    def parar_em_outra_thread():
        try:
            c.auto.parar()
            voltou["ok"] = True
        except BaseException as e:  # noqa: BLE001
            voltou["erro"] = e
        voltou["salvar_terminou"] = terminou.is_set()

    monkeypatch.setattr(R.ifcopenshell.file, "write", write_lento)
    monkeypatch.setattr(c.auto, "salvar", espiao)
    c.tx(1)
    antes = set(threading.enumerate())
    try:
        c.auto.iniciar()
        assert dentro.wait(timeout=20), "a thread não chegou ao retrato"
        parador = threading.Thread(target=parar_em_outra_thread, daemon=True)
        parador.start()
        parador.join(timeout=15)  # a implementação correta continua esperando o salvar() lento
        assert parador.is_alive(), f"parar() voltou com o salvar() da thread ainda rodando: {voltou}, vivas {_threads_novas(c, antes)}"
    finally:
        solta.set()
    parador.join(timeout=60)
    assert not parador.is_alive() and voltou.get("ok") and voltou["salvar_terminou"], voltou
    assert not _threads_novas(c, antes), f"thread residual depois de parar(): {_threads_novas(c, antes)}"
    assert c.auto.salvar() is False  # o salvar() lento gravou tudo
    fase[0] = "segunda"
    c.tx(2)
    c.auto.iniciar()
    assert salvou2.wait(timeout=20), "a thread nova não salvou"
    novas = _threads_novas(c, antes)
    assert len(novas) == 1 and all(t.daemon for t in novas), f"iniciar() depois de parar(): {novas}"
    c.auto.parar()
    assert not _threads_novas(c, antes), f"thread residual depois do 2º parar(): {_threads_novas(c, antes)}"


def test_r2_sha_do_lateral_do_retrato_quando_o_resolvedor_conclui_fora_do_ler(fabrica, monkeypatch):
    # M: sha do lateral calculado no ao_concluir (depois de uma transação pós-retrato, a base aponta para outro lateral e recuperar recusa)
    c = fabrica()
    c.tx(1)
    replace_real, trocas, erros, no_resolvedor = os.replace, [], [], {}

    def tx_em_outra_thread(tag):
        def alvo():
            try: c.tx(tag)  # noqa: E701
            except BaseException as e: erros.append(e)  # noqa: BLE001, E701
        t = threading.Thread(target=alvo, daemon=True)
        t.start()
        t.join(timeout=20)
        assert not t.is_alive(), "deadlock: transação durante o resolvedor do autosave"

    def replace_falha_uma(src, dst, *a, **k):  # 1ª troca do .obim do autosave: EIO (sem nova tentativa); a 2ª é a do resolvedor, fora do ler()
        if Path(dst) == c.auto_obim:
            trocas.append(c.sessao.estado()["leitores"])
            if len(trocas) == 1:
                raise OSError(errno.EIO, "falha simulada na troca do .obim", str(dst))
            if len(trocas) == 2:
                assert trocas[1] == 0, "o resolvedor deveria rodar fora do ler()"
                no_resolvedor["seq"] = c.diario.ultimo_seq
                tx_em_outra_thread(2)  # transação pós-retrato: muda o lateral antes do ao_concluir
        return replace_real(src, dst, *a, **k)

    monkeypatch.setattr(os, "replace", replace_falha_uma)
    with pytest.raises(Exception):
        c.auto.salvar()
    monkeypatch.setattr(os, "replace", replace_real)
    assert not erros and trocas[0] == 1 and len(trocas) == 2 and no_resolvedor["seq"] == 1, (erros, trocas, no_resolvedor)
    _, objs_auto = X7.ler_obim(c.auto_obim)
    sha_lat_auto = hashlib.sha256(Lateral(objs_auto).canonico()).hexdigest()
    assert (c.pasta_auto / "gravacao.json").exists() is False and X7.sobras(c.auto_ifc, c.pasta_auto) == []
    base, resto = _base(c)
    assert base["seq"] == 1 and [(r["tipo"], r["seq"]) for r in resto] == [("transacao", 2)], (base, resto)
    assert base["obim_sha256"] == sha_lat_auto, "R2: a base do diário tem o sha do lateral da hora do ao_concluir, não o do retrato"
    assert base["ifc_sha256"] == sha(c.auto_ifc)
    foto_rec, avisos = _rec_auto(c)
    assert avisos == [], avisos
    igual(foto_rec, c.foto(), "R2: recuperar autosave + diário aplica a transação pós-retrato")
    assert c.auto.salvar() is True and c.auto.salvar() is False
