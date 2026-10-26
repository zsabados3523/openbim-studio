# SPDX-License-Identifier: AGPL-3.0-or-later
"""Testes de oráculo do F0-S05-T09a: endurecimento do diário de transações (`app/openbim_app/diario.py`, ADR-002 §4.4, §4.7 e §4.8).
Não editar este arquivo na implementação; quem tira os `@AINDA_NAO` (xfail estrito) é o autor do oráculo depois da implementação.
CONTRATO:
1. `Diario.abrir` sobre diário existente não trunca no lugar: troca atômica (arquivo novo e rename), guarda o conteúdo antigo em
   `diario-descartado.obimlog` na mesma pasta (se já existir um, não o sobrescreve: guarda os dois) e queda no meio do `abrir` deixa o antigo íntegro.
2. Erro de `os.fsync` na thread do temporizador é guardado e levantado no próximo `anotar`, `sincronizar` ou `fechar`, e o diário fica quebrado
   (`HistoricoQuebrado` nos passos seguintes).
3. `recuperar` confere `obim_sha256` da base contra o `lateral` informado (sha diferente: não aplica nada e avisa) e rejeita registro com `tipo`
   desconhecido (para ali, com aviso, como no buraco em `seq`).
4. `Diario.__init__`: se o disco enche ao gravar o registro `base`, o arquivo é fechado e o erro sobe (pode ser apagado/renomeado logo depois).
5. Erro que não é `OSError` dentro de `_cortar` não esconde o erro original (o original sobe, o segundo fica como contexto).
6. `Diario.zerar(seq)`: remove registros com `seq <= seq_dado`, mantém os de `seq > seq_dado` (`seq` continua crescente), usa a trava do diário
   (não mistura com `anotar` concorrente) e é idempotente.
MUTANTES PENSADOS: M1.1..M1.4 (abrir/descartado/atomicidade), M2.1..M2.4 (fsync no timer), M3.1..M3.6 (obim_sha256 e tipo inválido),
M4.1..M4.2 (__init__ fecha no ENOSPC), M5.1..M5.2 (_cortar com erro não-OSError), M6.1..M6.5 (zerar e trava)."""
import builtins
import errno
import hashlib
import io
import json
import os
import threading
import time
import zlib
from pathlib import Path

import pytest
import s05_t05_aux as X
from s05_conteudo_aux import _limpa, base_ifc  # noqa: F401  (fixtures)
from s05_t05_aux import LADO, caminho_diario, igual, mod, recuperar, sha
from test_s05_t05_diario_oraculo import _sem_injecao, casa, local, registros_crus, sessoes  # noqa: F401  (fixtures)
from test_s05_t05_enospc_oraculo import CABE, _tx

AINDA_NAO = pytest.mark.xfail(strict=True, reason="T09a: endurecimento do diário ainda não implementado em diario.py")


class DiscoDiario:
    livre, erro_escrita, erro_corte, ao_escrever, abertos = None, None, None, None, []


def _escrever_lim(real, b):
    if DiscoDiario.ao_escrever is not None: return DiscoDiario.ao_escrever(real, b)  # noqa: E701
    if DiscoDiario.livre is None: return real(b)  # noqa: E701
    if DiscoDiario.livre <= 0:
        if DiscoDiario.erro_escrita is not None: raise DiscoDiario.erro_escrita  # noqa: E701
        raise OSError(errno.ENOSPC, "No space left on device (ensaio)")
    n = real(bytes(memoryview(b)[:DiscoDiario.livre]))
    DiscoDiario.livre -= n
    return n


def _cortar_lim(real, *a):
    if DiscoDiario.erro_corte is not None: raise DiscoDiario.erro_corte  # noqa: E701
    return real(*a)


class _RawDiario(io.FileIO):
    _pasta = None

    def _eh_diario(self):
        return _RawDiario._pasta is not None and Path(str(self.name)).resolve().parent == _RawDiario._pasta

    def write(self, b):
        return _escrever_lim(super().write, b) if self._eh_diario() else super().write(b)

    def truncate(self, size=None):
        return _cortar_lim(super().truncate, size) if self._eh_diario() else super().truncate(size)


@pytest.fixture
def disco_diario(monkeypatch, local):
    abrir, wr, ftr, pasta = builtins.open, os.write, os.ftruncate, caminho_diario(local).parent
    pasta.mkdir(parents=True, exist_ok=True)
    _RawDiario._pasta, DiscoDiario.abertos = pasta.resolve(), []

    def open_(f, mode="r", buffering=-1, *a, **k):
        if not ("b" in mode and bool(set(mode) & set("wax+")) and Path(str(f)).resolve().parent == _RawDiario._pasta):
            return abrir(f, mode, buffering, *a, **k)
        raw = _RawDiario(f, mode.replace("b", ""))
        DiscoDiario.abertos.append(raw)
        return raw if buffering == 0 else (io.BufferedRandom if "+" in mode else io.BufferedWriter)(raw)

    def eh_fd(fd):
        return any(os.path.exists(p) and os.path.samestat(os.fstat(fd), os.stat(p)) for p in pasta.iterdir())

    for alvo, nome, v in ((builtins, "open", open_), (io, "open", open_), (io, "FileIO", _RawDiario),
                          (os, "write", lambda fd, b: _escrever_lim(lambda x: wr(fd, x), b) if eh_fd(fd) else wr(fd, b)),
                          (os, "ftruncate", lambda fd, n: _cortar_lim(ftr, fd, n) if eh_fd(fd) else ftr(fd, n))):
        monkeypatch.setattr(alvo, nome, v)
    yield DiscoDiario
    DiscoDiario.livre = DiscoDiario.erro_escrita = DiscoDiario.erro_corte = DiscoDiario.ao_escrever = None
    DiscoDiario.abertos, _RawDiario._pasta = [], None


def _recalcular_linha(linha_bytes, **trocas):
    reg = {**json.loads(linha_bytes.split(b" ", 1)[1].decode("utf-8")), **trocas}
    raw = json.dumps(reg, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return b"%08x " % (zlib.crc32(raw) & 0xFFFFFFFF) + raw


def test_regua_auxiliares_e_diario_basico(local, casa, sessoes):
    D, s, cam = mod(), sessoes(casa), caminho_diario(local)
    s.passo("transacao")
    nova = _recalcular_linha(cam.read_bytes()[:-1].split(b"\n")[1], tipo="refazer")
    assert nova.startswith(b"%08x " % (zlib.crc32(nova.split(b" ", 1)[1]) & 0xFFFFFFFF)) and len(D.ler_diario(str(cam))[0]) == 2


@AINDA_NAO
def test_1a_abrir_sobre_existente_preserva_descartados(local, casa, sessoes):
    """M1.1 e M1.2: abrir não trunca sem guardar em diario-descartado.obimlog; se já existir um, guarda os dois."""
    D, cam = mod(), caminho_diario(local)
    descartado = cam.parent / "diario-descartado.obimlog"
    s1 = sessoes(casa)
    for k in ("transacao", "transacao", "desfazer"):
        s1.passo(k)
    f1 = s1.foto()
    s1.fechar()
    b1, (regs1, av1) = cam.read_bytes(), D.ler_diario(str(cam))
    assert av1 == [] and len(regs1) == 4
    s2 = sessoes(casa)
    assert descartado.exists() and descartado.read_bytes() == b1 and D.ler_diario(str(descartado)) == (regs1, [])
    igual(recuperar(casa, descartado)[0], f1, "recuperar a partir do primeiro diario-descartado.obimlog")
    assert [r["tipo"] for r in registros_crus(cam)] == ["base"]
    s2.passo("transacao")
    s2.fechar()
    b2, (regs2, av2) = cam.read_bytes(), D.ler_diario(str(cam))
    assert av2 == [] and len(regs2) == 2 and b2 != b1
    sessoes(casa).fechar()
    arqs_desc = [p for p in cam.parent.iterdir() if p.name != "diario.obimlog" and "descartado" in p.name]
    assert descartado.exists() and {b1, b2}.issubset({p.read_bytes() for p in arqs_desc})
    for b, esp in ((b1, regs1), (b2, regs2)):
        assert D.ler_diario(str(next(x for x in arqs_desc if x.read_bytes() == b))) == (esp, [])


@AINDA_NAO
@pytest.mark.parametrize("livre, erro", [(0, None), (CABE, None), (CABE, SystemExit(99))])
def test_1b_abrir_atomico_queda_no_meio_mantem_diario_antigo_integro(local, casa, sessoes, disco_diario, livre, erro):
    """M1.3 e M1.4: queda/erro no meio do abrir não trunca nem perde o diário antigo."""
    D, cam, s1 = mod(), caminho_diario(local), sessoes(casa)
    s1.passo("transacao"), s1.passo("transacao")
    f1 = s1.foto()
    s1.fechar()
    b1, (regs1, _) = cam.read_bytes(), D.ler_diario(str(cam))
    disco_diario.livre, disco_diario.erro_escrita = livre, erro
    with pytest.raises(SystemExit if erro is not None else OSError):
        D.Diario.abrir(LADO, str(casa))
    disco_diario.livre = disco_diario.erro_escrita = None
    assert all(r.closed for r in disco_diario.abertos), "arquivo temporário ficou aberto após falha no abrir"
    assert cam.exists() and cam.read_bytes() == b1 and D.ler_diario(str(cam)) == (regs1, [])
    igual(recuperar(casa, cam)[0], f1, "recuperar diário antigo após queda no abrir")


@AINDA_NAO
def test_2_erro_fsync_no_temporizador_propaga_e_quebra(local, casa, sessoes, monkeypatch):
    """M2.1..M2.4: erro de os.fsync na thread do timer sobe no próximo anotar, sincronizar ou fechar, e quebra o diário."""
    D = mod()
    import openbim_app.transacao as T

    s_anotar = sessoes(casa)
    d_sinc, d_fech = D.Diario.abrir("lado-sinc", str(casa)), D.Diario.abrir("lado-fech", str(casa))
    cam_an, cam_si, cam_fech = caminho_diario(local), caminho_diario(local, "lado-sinc"), caminho_diario(local, "lado-fech")
    caminhos = (cam_an, cam_si, cam_fech)
    real_fsync, falhar, threads_timer, pronto, vistos = os.fsync, True, [], threading.Event(), set()

    def fsync(fd):
        st = os.fstat(fd)
        qual = next((i for i, c in enumerate(caminhos) if c.exists() and os.path.samestat(st, os.stat(c))), None)
        if falhar and qual is not None and threading.current_thread() is not threading.main_thread():
            threads_timer.append(threading.current_thread())
            vistos.add(qual)
            len(vistos) == len(caminhos) and pronto.set()
            raise OSError(errno.EIO, "falha de fsync no temporizador (ensaio)")
        return real_fsync(fd)

    monkeypatch.setattr(os, "fsync", fsync)
    try:
        s_anotar.passo("transacao")
        f1, tam1 = s_anotar.foto(), cam_an.stat().st_size
        d_sinc.anotar("transacao", [], []), d_fech.anotar("transacao", [], [])
        assert pronto.wait(timeout=8), f"temporizador de fsync não disparou para os 3 diários: {len(vistos)}/3"
        for t in threads_timer:
            t.join(timeout=2)
        falhar = False  # prova que o erro levantado a seguir foi guardado do timer, não de um novo fsync
        with pytest.raises(OSError) as e_an:
            _tx(s_anotar, "nome")
        assert e_an.value.errno == errno.EIO and cam_an.stat().st_size == tam1
        igual(s_anotar.foto(), f1, "erro do timer no anotar: a transação não voltou")
        for k in ("transacao", "desfazer"):
            with pytest.raises(T.HistoricoQuebrado):
                s_anotar.passo(k)
        assert cam_an.stat().st_size == tam1
        with pytest.raises(OSError) as e_si:
            d_sinc.sincronizar()
        assert e_si.value.errno == errno.EIO
        with pytest.raises(T.HistoricoQuebrado):
            d_sinc.anotar("transacao", [], [])
        with pytest.raises(OSError) as e_fe:
            d_fech.fechar()
        assert e_fe.value.errno == errno.EIO
        renomeado = cam_fech.with_name("fechado-check.obimlog")
        os.replace(cam_fech, renomeado)
        os.unlink(renomeado)
    finally:
        falhar = False
        try:
            d_sinc.fechar()
        except OSError:
            pass


@AINDA_NAO
def test_3a_recuperar_confere_obim_sha256_contra_lateral(local, casa):
    """M3.1..M3.3: recuperar confere obim_sha256 da base contra o lateral informado; se diferir, não aplica nada e avisa."""
    D = mod()
    from openbim_app.lateral import Lateral
    from test_s05_t04_transacao_oraculo import Real

    objs_base = {"notas": {"n0": {"texto": "inicial", "v": 1}}}
    sha_base = hashlib.sha256(Lateral(objs_base).canonico()).hexdigest()
    f, c, plano = X.preparar(casa)
    d = D.Diario.abrir(LADO, str(casa), obim_sha256=sha_base)
    r = Real(f, c, lateral=Lateral(objs_base), codificar=D.codificar_ifc, anotar=d.anotar)
    try:
        r.tx([plano.op("nome"), ("lado_alterar", "notas", "n0", [plano.paredes[0]])])
        r.tx([plano.op("mover"), plano.op("lado_criar")])
        foto_final = r.foto()
    finally:
        d.fechar(), r.h.encerrar()
    cam = caminho_diario(local)
    foto_ifc_puro = X.R.foto(X.R.ifcopenshell.open(str(casa)), Lateral(objs_base))

    f_ok, av_ok, _, _ = recuperar(casa, cam, lateral=Lateral(objs_base))
    assert av_ok == []
    igual(f_ok, foto_final, "recuperar com lateral de sha igual ao obim_sha256 da base")

    objs_outro = {"notas": {"n0": {"texto": "alterado por fora", "v": 2}}}
    f_dif, av_dif, _, lat_dif = recuperar(casa, cam, lateral=Lateral(objs_outro))
    assert av_dif and lat_dif.obter("notas", "n0") == {"texto": "alterado por fora", "v": 2}
    igual(f_dif, X.R.foto(X.R.ifcopenshell.open(str(casa)), Lateral(objs_outro)), "aplicou diário com lateral divergente")

    f_sem, av_sem, _, _ = recuperar(casa, cam, lateral=None)
    assert av_sem
    igual(f_sem, X.R.foto(X.R.ifcopenshell.open(str(casa)), Lateral()), "aplicou diário quando faltava o lateral da base")

    d2 = D.Diario.abrir("lado-sem-obim", str(casa), obim_sha256=None)
    f2, c2, plano2 = X.preparar(casa)
    r2 = Real(f2, c2, codificar=D.codificar_ifc, anotar=d2.anotar)
    try:
        r2.tx([plano2.op("nome")])
    finally:
        d2.fechar(), r2.h.encerrar()
    f_inv, av_inv, _, _ = recuperar(casa, caminho_diario(local, "lado-sem-obim"), lateral=Lateral(objs_base))
    assert av_inv
    igual(f_inv, foto_ifc_puro, "aplicou diário com obim_sha256=None sobre lateral com dados")


@AINDA_NAO
@pytest.mark.parametrize("tipo_ruim", ["desconhecido", "base", "salvar", "", None, 42])
def test_3b_tipo_desconhecido_para_com_aviso(local, casa, sessoes, tmp_path, tipo_ruim):
    """M3.4..M3.6: registro com tipo desconhecido após a base para ali com aviso, igual ao buraco em seq."""
    D, s = mod(), sessoes(casa)
    fotos = [s.foto()]
    for k in ("transacao", "transacao", "desfazer", "transacao", "transacao"):
        s.passo(k)
        fotos.append(s.foto())
    ls, j, falso = caminho_diario(local).read_bytes()[:-1].split(b"\n"), 3, tmp_path / "falso.obimlog"
    falso.write_bytes(b"\n".join(ls[:j] + [_recalcular_linha(ls[j], tipo=tipo_ruim)] + ls[j + 1 :]) + b"\n")
    regs, av = D.ler_diario(str(falso))
    assert len(regs) == j and av, f"tipo={tipo_ruim!r}: ler_diario devolveu {len(regs)} registros e avisos={av}"
    f_rec, av_rec, _, _ = recuperar(casa, falso)
    assert av_rec
    igual(f_rec, fotos[j - 1], f"tipo={tipo_ruim!r}: recuperar não parou no registro {j}")


@AINDA_NAO
@pytest.mark.parametrize("livre", [0, CABE])
@pytest.mark.parametrize("via_abrir", [False, True])
def test_4_init_disco_cheio_fecha_arquivo_e_permite_remover(local, casa, disco_diario, livre, via_abrir):
    """M4.1 e M4.2: se o disco enche ao gravar o registro base em __init__, o arquivo é fechado e o erro sobe."""
    D, cam = mod(), caminho_diario(local)
    base = {"v": 1, "seq": 0, "tipo": "base", "hora": "2026-10-26T00:00:00+00:00", "ifc_sha256": sha(casa),
            "ifc_tamanho": casa.stat().st_size, "ifc_caminho": str(casa), "obim_sha256": None, "lado_id": LADO}
    disco_diario.livre = livre
    with pytest.raises(OSError) as e:
        D.Diario.abrir(LADO, str(casa)) if via_abrir else D.Diario(cam, LADO, base)
    disco_diario.livre = None
    assert e.value.errno == errno.ENOSPC and disco_diario.abertos and all(r.closed for r in disco_diario.abertos)
    for p in list(cam.parent.iterdir()):
        destino = p.with_name(p.name + ".renomeado")
        os.replace(p, destino)
        os.unlink(destino)


@AINDA_NAO
@pytest.mark.parametrize("erro_corte", [RuntimeError("falha interna em truncate"), ValueError("seek/truncate inválido")])
def test_5_erro_nao_oserror_em_cortar_preserva_erro_original_e_contexto(local, casa, sessoes, disco_diario, erro_corte):
    """M5.1 e M5.2: erro não-OSError em _cortar não esconde o erro original; original sobe, segundo fica como contexto e diário quebra."""
    import openbim_app.transacao as T

    s, cam = sessoes(casa), caminho_diario(local)
    s.passo("transacao"), s.passo("transacao")
    f0, disco_diario.livre, disco_diario.erro_corte = s.foto(), CABE, erro_corte
    with pytest.raises(OSError) as e:
        _tx(s, "nome")
    disco_diario.livre = disco_diario.erro_corte = None
    assert e.value.errno == errno.ENOSPC, f"erro original foi escondido por: {e.value!r}"
    ctx = e.value.__context__ or e.value.__cause__
    assert ctx is erro_corte or (isinstance(ctx, type(erro_corte)) and str(erro_corte) in str(ctx)), (e.value.__context__, e.value.__cause__)
    igual(s.foto(), f0, "passo não foi revertido após falha dupla na escrita e no corte")
    tam = cam.stat().st_size
    with pytest.raises(T.HistoricoQuebrado):
        s.passo("transacao")
    assert cam.stat().st_size == tam


@AINDA_NAO
def test_6a_zerar_mantem_maiores_seq_crescente_e_idempotente(local, casa, sessoes):
    """M6.1..M6.4: zerar(seq) remove seq <= dado, mantém seq > dado sem renumerar, mantém seq crescente e é idempotente."""
    D, s, cam = mod(), sessoes(casa), caminho_diario(local)
    for k in ("transacao", "transacao", "desfazer", "transacao", "transacao"):
        s.passo(k)
    ops_4_5 = [(r["tipo"], r["ifc"], r["lado"]) for r in registros_crus(cam)[4:6]]
    s.d.zerar(0)
    regs_0, av_0 = D.ler_diario(str(cam))
    assert av_0 == [] and [r["seq"] for r in regs_0[1:]] == [1, 2, 3, 4, 5]
    s.d.zerar(3)
    regs_z1, av_z1 = D.ler_diario(str(cam))
    assert av_z1 == [] and regs_z1[0]["tipo"] == "base" and [r["seq"] for r in regs_z1[1:]] == [4, 5]
    assert [(r["tipo"], r["ifc"], r["lado"]) for r in regs_z1[1:]] == ops_4_5 and not list(cam.parent.glob("*descartado*"))
    s.d.zerar(3), s.d.zerar(2)
    assert D.ler_diario(str(cam)) == (regs_z1, []), "zerar(seq) não foi idempotente"
    s.passo("transacao"), s.passo("desfazer")
    regs_novos, av_novos = D.ler_diario(str(cam))
    assert av_novos == [] and [r["seq"] for r in regs_novos[1:]] == [4, 5, 6, 7]
    s.d.zerar(7), s.d.zerar(7)
    regs_vazio, av_vazio = D.ler_diario(str(cam))
    assert av_vazio == [] and len(regs_vazio) == 1 and regs_vazio[0]["tipo"] == "base"
    s.passo("transacao")
    regs_fim, av_fim = D.ler_diario(str(cam))
    assert av_fim == [] and len(regs_fim) == 2 and regs_fim[1]["seq"] == 8


@AINDA_NAO
def test_6b_zerar_usa_trava_e_nao_mistura_com_anotar_concorrente(local, casa, disco_diario):
    """M6.5: zerar(seq) usa a trava do diário (espera anotar em curso terminar e não corrompe em concorrência)."""
    D, cam = mod(), caminho_diario(local)
    d = D.Diario.abrir(LADO, str(casa))
    ev_no_meio, ev_liberar, erros_z, t_anotar, t_zerar = threading.Event(), threading.Event(), [], None, None
    try:
        d.anotar("transacao", [], [["notas", "n1", None, {"v": 1}]])
        d.anotar("transacao", [], [["notas", "n2", None, {"v": 2}]])

        def write_pausado(real, b):
            disco_diario.ao_escrever, meio = None, max(1, len(b) // 2)
            n1 = real(bytes(memoryview(b)[:meio]))
            ev_no_meio.set()
            assert ev_liberar.wait(timeout=5)
            return n1 + real(bytes(memoryview(b)[meio:]))

        def rodar(fn, lista_erros):
            try:
                fn()
            except BaseException as e:  # noqa: BLE001
                lista_erros.append(e)

        disco_diario.ao_escrever = write_pausado
        t_anotar = threading.Thread(target=lambda: d.anotar("transacao", [], [["notas", "n3", None, {"v": 3}]]))
        t_anotar.start()
        assert ev_no_meio.wait(timeout=5)
        t_zerar = threading.Thread(target=rodar, args=(lambda: d.zerar(1), erros_z))
        t_zerar.start()
        t_zerar.join(timeout=0.15)
        if erros_z:
            raise erros_z[0]
        assert t_zerar.is_alive(), "zerar(seq) não esperou a trava do diário durante anotar concorrente"
        ev_liberar.set()
        t_anotar.join(timeout=5), t_zerar.join(timeout=5)
        assert not erros_z and D.ler_diario(str(cam))[1] == [] and [r["seq"] for r in D.ler_diario(str(cam))[0][1:]] == [2, 3]

        erros = []
        t1 = threading.Thread(target=rodar, args=(lambda: [d.anotar("transacao", [], [["notas", f"n{i}", None, {"v": i}]]) for i in range(4, 34)], erros))
        t2 = threading.Thread(target=rodar, args=(lambda: [(d.zerar(s), time.sleep(0.002)) for s in range(2, 25, 2)], erros))
        t1.start(), t2.start()
        t1.join(timeout=10), t2.join(timeout=10)
        assert not erros and D.ler_diario(str(cam))[1] == [] and [r["seq"] for r in D.ler_diario(str(cam))[0][1:]] == list(range(25, 34))
    finally:
        disco_diario.ao_escrever = None
        ev_liberar.set()
        t_anotar is not None and t_anotar.join(timeout=2)
        t_zerar is not None and t_zerar.join(timeout=2)
        d.fechar()
