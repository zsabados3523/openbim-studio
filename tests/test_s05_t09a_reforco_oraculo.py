# SPDX-License-Identifier: AGPL-3.0-or-later
"""Reforço de oráculo do F0-S05-T09a (`app/openbim_app/diario.py`): 1 teste determinístico por defeito achado na revisão da v1 (R1..R4)."""
import errno
import os
import threading
from pathlib import Path

import pytest
from openbim_app.transacao import HistoricoQuebrado
from s05_conteudo_aux import _limpa, base_ifc  # noqa: F401  (fixtures)
from s05_t05_aux import LADO, caminho_diario, mod
from test_s05_t05_diario_oraculo import _sem_injecao, casa, local, registros_crus, sessoes  # noqa: F401  (fixtures)
from test_s05_t09a_diario_oraculo import _RawDiario, disco_diario  # noqa: F401  (fixture)


class _TravaEspia:
    def __init__(self, real, ao_entrar):
        self._real, self._ao_entrar = real, ao_entrar

    def __enter__(self):
        self._ao_entrar(threading.current_thread().name)
        return self._real.__enter__()

    def __exit__(self, *a):
        return self._real.__exit__(*a)


def test_r1_anotar_concorrente_com_zerar_nao_le_seq_fora_da_trava(local, casa):
    """R1: duas threads anotando enquanto outra faz zerar; ler_diario sem aviso de buraco e seq estritamente crescente sem duplicata."""
    D, cam = mod(), caminho_diario(local)
    d = D.Diario.abrir(LADO, str(casa))
    ev_a_na_trava, ev_b_na_porta, ev_z_na_porta = threading.Event(), threading.Event(), threading.Event()
    erros = []
    try:
        d.anotar("transacao", [], [["notas", "n1", None, {"v": 1}]])
        d.anotar("transacao", [], [["notas", "n2", None, {"v": 2}]])
        escrever_real = d._escrever

        def ao_entrar(nome):
            if nome == "B":
                ev_b_na_porta.set()
            elif nome == "Z":
                ev_z_na_porta.set()

        def escrever_a_bloqueada(dados):
            escrever_real(dados)
            if threading.current_thread().name == "A":
                ev_a_na_trava.set()
                assert ev_b_na_porta.wait(timeout=5) and ev_z_na_porta.wait(timeout=5)

        d._lock = _TravaEspia(d._lock, ao_entrar)
        d._escrever = escrever_a_bloqueada

        def rodar(fn):
            try:
                fn()
            except BaseException as e:  # noqa: BLE001
                erros.append(e)

        t_a = threading.Thread(name="A", target=rodar, args=(lambda: d.anotar("transacao", [], [["notas", "a", None, {"v": 3}]]),))
        t_b = threading.Thread(name="B", target=rodar, args=(lambda: d.anotar("transacao", [], [["notas", "b", None, {"v": 4}]]),))
        t_z = threading.Thread(name="Z", target=rodar, args=(lambda: d.zerar(1),))
        t_a.start()
        assert ev_a_na_trava.wait(timeout=5)
        t_b.start(), t_z.start()
        for t in (t_a, t_b, t_z):
            t.join(timeout=5)
        assert not erros, f"erros nas threads: {erros!r}"
        regs, avisos = D.ler_diario(str(cam))
        seqs = [r["seq"] for r in regs]
        assert avisos == [], f"ler_diario acusou aviso: {avisos}"
        assert seqs == [1, 2, 3, 4] and len(seqs) == len(set(seqs)), f"seq fora de ordem ou duplicado: {seqs}"
        assert [r["seq"] for r in registros_crus(cam)] == [1, 2, 3, 4]
    finally:
        ev_b_na_porta.set(), ev_z_na_porta.set()
        d.fechar()


def test_r2_timer_apos_sincronizar_falhar_nao_relanca_erro_fsync(local, casa, monkeypatch):
    """R2: após sincronizar() falhar no fsync, disparar o timer pendente não relança o erro 2ª vez; anotar/sincronizar levantam HistoricoQuebrado e fechar() é silencioso."""
    D, cam = mod(), caminho_diario(local)
    d = D.Diario.abrir(LADO, str(casa))
    real_fsync, falhar = os.fsync, False

    def fsync_falho(fd):
        if falhar and cam.exists() and os.path.samestat(os.fstat(fd), os.stat(cam)):
            raise OSError(errno.EIO, "falha de fsync em sincronizar (ensaio)")
        return real_fsync(fd)

    monkeypatch.setattr(os, "fsync", fsync_falho)
    try:
        d.anotar("transacao", [], [["notas", "n1", None, {"v": 1}]])
        assert d._timer is not None
        falhar = True
        with pytest.raises(OSError) as exc:
            d.sincronizar()
        assert exc.value.errno == errno.EIO and d._quebrado
        d._acordar()
        with pytest.raises(HistoricoQuebrado):
            d.anotar("transacao", [], [["notas", "n2", None, {"v": 2}]])
        with pytest.raises(HistoricoQuebrado):
            d.sincronizar()
        d._acordar()
        assert d._timer is None and d._erro_fsync is None
        d.fechar()
        assert d._f.closed
    finally:
        falhar = False
        try:
            d.fechar()
        except OSError:
            pass


def test_r3_abrir_falha_no_replace_unico_preserva_antigo_sem_orfaos(local, casa, sessoes, monkeypatch):
    """R3: falha em os.replace(tmp, caminho) (único replace) mantém diario.obimlog antigo íntegro, sem tmp nem diario-descartado* órfão; caminho feliz preserva conteúdo antigo."""
    D, cam = mod(), caminho_diario(local)
    s1 = sessoes(casa)
    s1.passo("transacao"), s1.passo("transacao"), s1.fechar()
    b_antigo, (regs_antigos, av_antigos) = cam.read_bytes(), D.ler_diario(str(cam))
    assert av_antigos == [] and len(regs_antigos) == 3

    real_replace, chamadas = os.replace, []

    def replace_falha_no_destino(src, dst):
        chamadas.append((Path(src).name, Path(dst).name))
        if Path(dst) == cam:
            raise OSError(errno.EACCES, "falha simulada em os.replace(tmp, caminho)")
        return real_replace(src, dst)

    monkeypatch.setattr(os, "replace", replace_falha_no_destino)
    with pytest.raises(OSError) as exc:
        D.Diario.abrir(LADO, str(casa))
    assert exc.value.errno == errno.EACCES
    assert cam.exists() and cam.read_bytes() == b_antigo and D.ler_diario(str(cam)) == (regs_antigos, [])
    assert not list(cam.parent.glob("*.tmp*")) and not list(cam.parent.glob("diario-descartado*"))
    assert chamadas == [(f"{cam.name}.tmp", cam.name)]

    monkeypatch.setattr(os, "replace", real_replace)
    d2 = D.Diario.abrir(LADO, str(casa))
    try:
        descartado = cam.parent / "diario-descartado.obimlog"
        assert descartado.exists() and descartado.read_bytes() == b_antigo
        assert D.ler_diario(str(descartado)) == (regs_antigos, [])
    finally:
        d2.fechar()




@pytest.mark.parametrize("subcaso", ["a_enospc", "b_eio_read", "c_crc_base"])
def test_r4_zerar_falhas_escrita_leitura_e_crc_base(local, casa, disco_diario, monkeypatch, subcaso):
    """R4: (a, revisto no T09a2) ENOSPC em zerar sobe, o diário no disco fica com os mesmos bytes, sem temporário, não quebra e segue anotando;
    (b) EIO em read quebra e anotar levanta HistoricoQuebrado sem sobrescrever base; (c) CRC errado na base levanta HistoricoQuebrado."""
    D, cam = mod(), caminho_diario(local)
    d = D.Diario.abrir(LADO, str(casa))
    try:
        d.anotar("transacao", [], [["notas", "n1", None, {"v": 1}]])
        d.anotar("transacao", [], [["notas", "n2", None, {"v": 2}]])
        assert d._base["seq"] == 0
        if subcaso == "a_enospc":
            bruto_antes, regs_antes = cam.read_bytes(), D.ler_diario(str(cam))
            disco_diario.livre = 16
            with pytest.raises(OSError) as exc_a:
                d.zerar(1)
            disco_diario.livre = None
            assert exc_a.value.errno == errno.ENOSPC and not d._quebrado and d._base["seq"] == 0
            assert cam.read_bytes() == bruto_antes and D.ler_diario(str(cam)) == regs_antes and regs_antes[1] == []
            assert sorted(p.name for p in cam.parent.iterdir()) == [cam.name], "sobrou temporário na pasta do diário"
            d.anotar("transacao", [], [])
            assert [r["seq"] for r in D.ler_diario(str(cam))[0]] == [0, 1, 2, 3]
        elif subcaso == "b_eio_read":
            bruto_antes = cam.read_bytes()
            linha_base_antes = bruto_antes.splitlines(keepends=True)[0]
            real_read = _RawDiario.read

            def read_eio(self, *a, **k):
                if getattr(self, "_no_diario", False):
                    raise OSError(errno.EIO, "falha simulada de leitura em zerar")
                return real_read(self, *a, **k)

            monkeypatch.setattr(_RawDiario, "read", read_eio)
            with pytest.raises(OSError) as exc_b:
                d.zerar(1)
            monkeypatch.setattr(_RawDiario, "read", real_read)
            assert exc_b.value.errno == errno.EIO and d._base["seq"] == 0
            with pytest.raises(HistoricoQuebrado):
                d.anotar("transacao", [], [["notas", "n3", None, {"v": 3}]])
            assert d._quebrado and cam.read_bytes() == bruto_antes and cam.read_bytes().splitlines(keepends=True)[0] == linha_base_antes
        else:
            d._f.seek(0)
            b0 = d._f.read(1)
            d._f.seek(0)
            d._f.write(b"1" if b0 == b"0" else b"0")
            d._f.seek(0, os.SEEK_END)
            with pytest.raises(HistoricoQuebrado):
                d.zerar(1)
            assert d._quebrado and d._base["seq"] == 0
    finally:
        disco_diario.livre = None
        d.fechar()
