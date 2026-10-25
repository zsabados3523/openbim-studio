# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo do F0-S04-P1, parte Python (LOTE_OPUS_69; ADR-004 §5, decisão 3C, e §5.1, regras 3 e 4): a porta única do modelo.
Quem implementa o P1 não edita este arquivo; quem tira os `@AINDA_NAO` (xfail estrito) é o autor do oráculo, em commit próprio (só as linhas
`AINDA_NAO = ...` e `@AINDA_NAO`). Contrato (cartão `docs/state/cards/F0-S04/F0-S04-P1.md`), módulo `app/openbim_app/sessao_modelo.py`, sem Qt:
- `SessaoModelo(arquivo)` (só `ifcopenshell.file`, senão `TypeError`) é a única dona do arquivo: nenhum atributo público o devolve.
- `ler(espera=None)`: contexto que entrega o arquivo; vários leitores juntos. `escrever(espera=None)`: contexto que entrega uma `Escrita`
  (`.arquivo`, `.emprestar_leitura()`); um escritor só e nenhum leitor junto. `espera`: None = sem limite; número > 0 = segundos; 0 = não espera;
  negativo = `ValueError`. Não conseguiu = `ModeloOcupado` (subclasse de `RuntimeError`), sem mudar nada.
- Preferência do escritor: com um escritor esperando, leitor novo não entra (com `espera=0`, `ModeloOcupado` na hora).
- Reentrada proibida: a thread que já segura `ler()` ou `escrever()` (inclusive durante o empréstimo) e pede qualquer porta recebe
  `ReentradaProibida` (subclasse de `ModeloOcupado`) NA HORA, qualquer que seja `espera` (nunca trava).
- Exceção dentro do contexto solta a porta e sobe igual. `estado()` = {"leitores", "escritor" (ident da thread ou None), "esperando_escrever",
  "emprestada", "em_uso_cpp"}.
- Regra 3 do §5.1: `with esc.emprestar_leitura():` (só na thread do escritor; aninhado = `ReentradaProibida`; outra thread = `TravaNaoSegura`) marca o
  escritor parado; durante ele `esc.arquivo` levanta `TravaNaoSegura`, e a saída do empréstimo espera `em_uso_cpp` voltar a 0. Fora do contexto `escrever`,
  `esc.arquivo` levanta `TravaNaoSegura` (subclasse de `RuntimeError`).
- `_obimcore_entrar()` (chamada pelo C++ com o bloqueio do interpretador, de qualquer thread): devolve o arquivo e soma 1 a `em_uso_cpp` se a thread
  segura `ler()`, ou é o escritor fora do empréstimo, ou é OUTRA thread durante o empréstimo; senão `TravaNaoSegura`. `_obimcore_sair()` subtrai 1;
  sem entrada aberta, `RuntimeError`.
O teste da regra 9 (sem `ifcopenshell.geom` em `app/`) não tem marcador: passa hoje e tem de continuar passando."""
import threading
import time
from pathlib import Path

import ifcopenshell
import pytest

APP = Path(__file__).resolve().parent.parent / "app"
REPOUSO = {"leitores": 0, "escritor": None, "esperando_escrever": 0, "emprestada": False, "em_uso_cpp": 0}


def _sm():
    from openbim_app import sessao_modelo
    return sessao_modelo


def _nova():
    sm = _sm()
    return sm, sm.SessaoModelo(ifcopenshell.file(schema="IFC4"))


def _em_thread(fn, nome="p1-outra"):  # roda fn numa thread; devolve (thread, saída) com saída = {"ok": valor} ou {"exc": exceção}
    out = {}

    def corre():
        try:
            out["ok"] = fn()
        except BaseException as e:
            out["exc"] = e
    th = threading.Thread(target=corre, name=nome, daemon=True)
    th.start()
    return th, out


def _ate(cond, s=5.0):
    fim = time.monotonic() + s
    while not cond():
        assert time.monotonic() < fim, "condição não aconteceu em 5 s"
        time.sleep(0.002)


class _ler_fora:  # contexto: `leitor` numa outra thread, dentro de ler() até sair do contexto
    def __init__(s, leitor, dentro, solta):
        s.th, s.dentro, s.solta = _em_thread(leitor, "p1-leitor")[0], dentro, solta

    def __enter__(s):
        assert s.dentro.wait(5), "o leitor não entrou"

    def __exit__(s, *a):
        s.solta.set()
        s.th.join(5)


def _ocupado(sm, porta, espera):  # tenta a porta numa outra thread; devolve (tipo da exceção ou None, segundos)
    def fn():
        t = time.monotonic()
        try:
            with porta(espera=espera):
                return None, time.monotonic() - t
        except sm.ModeloOcupado as e:
            return type(e).__name__, time.monotonic() - t
    th, out = _em_thread(fn)
    th.join(5)
    return out["ok"]


def test_p1_tipos_hierarquia_e_dono_unico():
    sm, s = _nova()
    with pytest.raises(TypeError):
        sm.SessaoModelo(object())
    assert issubclass(sm.ReentradaProibida, sm.ModeloOcupado) and issubclass(sm.ModeloOcupado, RuntimeError) and issubclass(sm.TravaNaoSegura, RuntimeError)
    soltos = [k for k in dir(s) if not k.startswith("_") and isinstance(getattr(s, k, None), ifcopenshell.file)]
    assert not soltos, f"a sessão é a única dona do arquivo: nenhum atributo público o devolve ({soltos})"
    assert s.estado() == REPOUSO
    with pytest.raises(ValueError):
        with s.ler(espera=-1):
            pass


def test_p1_varios_leitores_ao_mesmo_tempo():
    sm, s = _nova()
    b, vistos = threading.Barrier(3, timeout=3), []

    def leitor():
        with s.ler() as arq:
            b.wait()
            vistos.append((arq.schema, s.estado()["leitores"]))
            b.wait()
    ths = [_em_thread(leitor, f"p1-leitor-{i}") for i in range(3)]
    for th, out in ths:
        th.join(5)
        assert "exc" not in out, f"três leitores juntos: {out}"
    assert vistos == [("IFC4", 3)] * 3 and s.estado() == REPOUSO


def test_p1_escritor_exclui_leitores_e_escritores():
    sm, s = _nova()
    with s.escrever() as esc:
        assert esc.arquivo.schema == "IFC4" and s.estado()["escritor"] == threading.get_ident()
        tipo, dt = _ocupado(sm, s.ler, 0)
        assert tipo == "ModeloOcupado" and dt < 0.05, f"ler(espera=0) com escritor: ocupado na hora ({tipo}, {dt:.3f} s)"
        tipo, dt = _ocupado(sm, s.ler, 0.1)
        assert tipo == "ModeloOcupado" and 0.09 <= dt < 1.0, f"ler(espera=0,1): ocupado depois de esperar ~0,1 s ({tipo}, {dt:.3f} s)"
        assert _ocupado(sm, s.escrever, 0)[0] == "ModeloOcupado"
        entrou = []

        def leitor():
            with s.ler():
                entrou.append(time.monotonic())
        th, out = _em_thread(leitor)
        time.sleep(0.2)
        assert not entrou, "leitor sem limite entrou com o escritor ativo"
        saiu = time.monotonic()
    th.join(5)
    assert entrou and entrou[0] >= saiu and "exc" not in out and s.estado() == REPOUSO, "o leitor que esperava entra depois que o escritor sai"


def test_p1_escritor_espera_o_leitor_e_tem_preferencia():
    sm, s = _nova()
    ordem, solta_r1 = [], threading.Event()

    def r1():
        with s.ler():
            ordem.append("r1")
            solta_r1.wait(5)

    def w():
        with s.escrever():
            ordem.append("w")
            time.sleep(0.05)

    def r2():
        with s.ler():
            ordem.append("r2")
    t1, _ = _em_thread(r1)
    _ate(lambda: ordem == ["r1"])
    assert _ocupado(sm, s.escrever, 0)[0] == "ModeloOcupado", "escrever(espera=0) com leitor: ocupado"
    tw, _ = _em_thread(w)
    _ate(lambda: s.estado()["esperando_escrever"] == 1)
    assert _ocupado(sm, s.ler, 0)[0] == "ModeloOcupado", "com escritor esperando, leitor novo não entra (preferência do escritor)"
    t2, _ = _em_thread(r2)
    time.sleep(0.1)
    assert ordem == ["r1"], f"leitor novo passou na frente do escritor que esperava: {ordem}"
    solta_r1.set()
    for t in (t1, tw, t2):
        t.join(5)
    assert ordem == ["r1", "w", "r2"] and s.estado() == REPOUSO, ordem


def test_p1_reentrada_proibida_na_hora_e_sem_travar():
    sm, s = _nova()
    for porta_fora in (s.ler, s.escrever):
        with porta_fora() as x:
            antes = s.estado()
            for porta, espera in ((p, e) for p in (s.ler, s.escrever) for e in (0, 0.5)):  # 0,5 s e não None: um erro aqui falha, não trava o pytest
                t = time.monotonic()
                with pytest.raises(sm.ReentradaProibida):
                    with porta(espera=espera):
                        pass
                assert time.monotonic() - t < 0.05 and s.estado() == antes, f"{porta_fora.__name__} -> {porta.__name__}: na hora, sem mudar nada"
            if porta_fora == s.escrever:
                with x.emprestar_leitura():
                    for porta in (s.ler, s.escrever):
                        with pytest.raises(sm.ReentradaProibida):
                            with porta(espera=0.5):
                                pass
                    with pytest.raises(sm.ReentradaProibida):
                        with x.emprestar_leitura():
                            pass
    assert s.estado() == REPOUSO


def test_p1_excecao_solta_a_porta_e_sobe_igual():
    sm, s = _nova()

    class Minha(Exception):
        pass
    for porta in (s.ler, s.escrever):
        with pytest.raises(Minha):
            with porta():
                raise Minha()
        assert s.estado() == REPOUSO, porta.__name__
    with pytest.raises(Minha):
        with s.escrever() as esc:
            with esc.emprestar_leitura():
                raise Minha()
    assert s.estado() == REPOUSO


def test_p1_escrita_e_emprestimo():
    sm, s = _nova()
    with s.escrever() as esc:
        assert esc.arquivo.schema == "IFC4"
        th, out = _em_thread(esc.emprestar_leitura().__enter__)
        th.join(5)
        assert isinstance(out.get("exc"), sm.TravaNaoSegura), f"empréstimo só na thread do escritor: {out}"
        with esc.emprestar_leitura():
            assert s.estado()["emprestada"] is True
            with pytest.raises(sm.TravaNaoSegura):
                esc.arquivo  # noqa: B018  (o escritor está parado: não toca no modelo)
        assert s.estado()["emprestada"] is False and esc.arquivo.schema == "IFC4"
    with pytest.raises(sm.TravaNaoSegura):
        esc.arquivo  # noqa: B018  (fora do contexto)


def test_p1_porta_do_obimcore_confere_quem_chama():
    sm, s = _nova()
    entrar = lambda: (s._obimcore_entrar(), s.estado()["em_uso_cpp"], s._obimcore_sair())[:2]  # noqa: E731
    with pytest.raises(sm.TravaNaoSegura):
        s._obimcore_entrar()
    assert s.estado() == REPOUSO, "sem porta nenhuma: erro claro e nada muda"
    with pytest.raises(RuntimeError):
        s._obimcore_sair()
    with s.ler():
        arq, n = entrar()
        assert arq.schema == "IFC4" and n == 1, "leitor: entra"
    with s.escrever() as esc:
        assert entrar()[1] == 1, "o próprio escritor fora do empréstimo: entra"
        th, out = _em_thread(s._obimcore_entrar)
        th.join(5)
        assert isinstance(out.get("exc"), sm.TravaNaoSegura), f"outra thread com o escritor ATIVO (sem empréstimo): erro claro ({out})"
        with esc.emprestar_leitura():
            th, out = _em_thread(entrar, "p1-geometria")
            th.join(5)
            assert out.get("ok", (None, None))[1] == 1, f"outra thread durante o empréstimo: entra ({out})"
            with pytest.raises(sm.TravaNaoSegura):
                s._obimcore_entrar()
    assert s.estado() == REPOUSO


def test_p1_porta_do_obimcore_recusa_outra_thread_com_leitor_ativo():  # lote 70 §2.3: o leitor sairia com o C++ de outra thread ainda lendo
    sm, s = _nova()
    dentro, solta = threading.Event(), threading.Event()

    def leitor():
        with s.ler():
            dentro.set()
            solta.wait(5)
    for quem_le in ("outra", "esta"):  # o leitor numa outra thread e o C++ nesta; depois o contrário
        with s.ler() if quem_le == "esta" else _ler_fora(leitor, dentro, solta):
            antes = s.estado()
            if quem_le == "esta":
                th, out = _em_thread(s._obimcore_entrar, "p1-geometria")
                th.join(5)
                exc = out.get("exc")
            else:
                try:
                    s._obimcore_entrar()
                    exc = None
                except BaseException as e:
                    exc = e
            assert isinstance(exc, sm.TravaNaoSegura) and s.estado() == antes, f"leitor em {quem_le}, C++ na outra thread: TravaNaoSegura sem mudar nada ({exc!r})"
    assert s.estado() == REPOUSO


def test_p1_reentrada_com_espera_none_falha_na_hora():  # lote 70 §2.3 (recomendação): numa thread com join(2), um erro aqui falha e não trava o pytest
    sm, s = _nova()

    def fn():
        r = []
        for fora in (s.ler, s.escrever):
            with fora():
                for porta in (s.ler, s.escrever):
                    try:
                        with porta(espera=None):
                            r.append("entrou")
                    except sm.ReentradaProibida:
                        r.append("na hora")
        return r
    th, out = _em_thread(fn)
    th.join(2)
    assert not th.is_alive() and out.get("ok") == ["na hora"] * 4, f"reentrada com espera=None: {out or 'travou'}"


def test_p1_saida_do_emprestimo_espera_o_cpp():
    sm, s = _nova()
    fim = []

    def geo():
        s._obimcore_entrar()
        time.sleep(0.2)
        fim.append(time.monotonic())
        s._obimcore_sair()
    with s.escrever() as esc:
        with esc.emprestar_leitura():
            th, out = _em_thread(geo, "p1-geometria")
            _ate(lambda: s.estado()["em_uso_cpp"] == 1)
        saiu = time.monotonic()
        assert fim and saiu >= fim[0], "a saída do empréstimo espera o C++ sair (o escritor não volta a escrever com a leitura em curso)"
    th.join(5)
    assert "exc" not in out and s.estado() == REPOUSO


def test_p1_carga_leitores_e_escritores_sem_mistura_nem_trava():
    sm, s = _nova()
    viol, ativo, n = [], {"w": 0, "r": 0}, threading.Lock()

    def escritor():
        for _ in range(200):
            with s.escrever():
                with n:
                    ativo["w"] += 1
                    ativo["w"] == 1 and ativo["r"] == 0 or viol.append(dict(ativo))
                time.sleep(0.0002)
                with n:
                    ativo["w"] -= 1

    def leitor():
        for _ in range(400):
            with s.ler():
                with n:
                    ativo["r"] += 1
                    ativo["w"] == 0 or viol.append(dict(ativo))
                with n:
                    ativo["r"] -= 1
    ths = [_em_thread(escritor, f"p1-w{i}") for i in range(2)] + [_em_thread(leitor, f"p1-r{i}") for i in range(4)]
    for th, out in ths:
        th.join(30)
        assert not th.is_alive() and "exc" not in out, f"travou ou falhou: {th.name} {out}"
    assert not viol and s.estado() == REPOUSO, f"{len(viol)} misturas de leitor com escritor: {viol[:3]}"


def test_p1_regra_9_nenhum_ifcopenshell_geom_no_app():  # ADR-004 §5 (3C): geometria só no obimcore e no processo auxiliar
    achados = [f"{p.relative_to(APP)}:{i}" for p in APP.rglob("*.py") for i, x in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
               if "ifcopenshell.geom" in x or "from ifcopenshell import geom" in x]
    assert not achados, f"chamada a ifcopenshell.geom fora do obimcore e do processo auxiliar: {achados}"
