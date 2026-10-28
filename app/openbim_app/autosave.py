# SPDX-License-Identifier: AGPL-3.0-or-later
"""Autosave local periódico e após recuperação (ADR-002 §4.5, §4.7 e §4.8)."""
import hashlib
import shutil
import threading
from pathlib import Path

from .diario import pasta_projeto
from .gravacao_par import gravar_par, resolver_gravacao_pendente

INTERVALO_AUTOSAVE_S = 300


def _sha256(caminho):
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


class Autosave:
    def __init__(self, sessao, historico, lateral, diario, lado_id, ifc_origem, intervalo_s=INTERVALO_AUTOSAVE_S):
        self._sessao = sessao
        self._historico = historico
        self._lateral = lateral
        self._diario = diario
        self._lado_id = lado_id
        self._ifc_origem = Path(ifc_origem)
        self._intervalo_s = intervalo_s

        self._sujo_lock = threading.Lock()
        self._max_anotado_seq = 0
        self._seq_salvo = 0

        self._salvar_lock = threading.Lock()
        self._thread = None
        self._thread_lock = threading.Lock()
        self._parar_ev = threading.Event()
        self._erro_thread = None

    def anotar(self, tipo, ifc, lado):
        self._diario.anotar(tipo, ifc, lado)
        with self._sujo_lock:
            self._max_anotado_seq = self._diario.ultimo_seq

    def salvar(self) -> bool:
        if threading.current_thread() is not self._thread:
            with self._thread_lock:
                err = self._erro_thread
                self._erro_thread = None
            if err is not None:
                raise err
        with self._salvar_lock:
            with self._sujo_lock:
                if self._max_anotado_seq <= self._seq_salvo:
                    return False
            pasta_auto = pasta_projeto(self._lado_id) / "autosave"
            destino_auto = pasta_auto / self._ifc_origem.name
            pasta_auto.mkdir(parents=True, exist_ok=True)
            resolver_gravacao_pendente(pasta_auto, destino_auto, ao_concluir=None)

            seq_salvo = [0]

            def ao_concluir(seq_final):
                sha_lat = hashlib.sha256(self._lateral.canonico()).hexdigest()
                self._diario.zerar(seq_final, ifc_caminho=destino_auto, obim_sha256=sha_lat)
                seq_salvo[0] = seq_final

            origem_sha = _sha256(self._ifc_origem)
            gravar_par(
                sessao=self._sessao,
                historico=self._historico,
                lateral=self._lateral,
                destino=destino_auto,
                pasta_projeto=pasta_auto,
                lado_id=self._lado_id,
                seq=lambda: self._diario.ultimo_seq,
                carimbo=False,
                ao_concluir=ao_concluir,
                autosave=True,
                origem_ifc_sha256=origem_sha,
            )
            with self._sujo_lock:
                self._seq_salvo = max(self._seq_salvo, seq_salvo[0])
            return True

    def apos_gravacao_normal(self):
        with self._salvar_lock:
            with self._sujo_lock:
                self._seq_salvo = max(self._seq_salvo, self._diario.ultimo_seq, self._max_anotado_seq)
            pasta_auto = pasta_projeto(self._lado_id) / "autosave"
            if pasta_auto.exists():
                for item in list(pasta_auto.iterdir()):
                    try:
                        if item.is_dir() and not item.is_symlink():
                            shutil.rmtree(item)
                        else:
                            item.unlink()
                    except OSError:
                        pass

    def iniciar(self):
        with self._thread_lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._parar_ev.clear()
            self._thread = threading.Thread(target=self._loop, daemon=True)
            self._thread.start()

    def _loop(self):
        while not self._parar_ev.wait(self._intervalo_s):
            if self._parar_ev.is_set():
                break
            try:
                self.salvar()
            except BaseException as e:
                with self._thread_lock:
                    if self._erro_thread is None:
                        self._erro_thread = e

    def parar(self):
        with self._thread_lock:
            t = self._thread
            self._parar_ev.set()
        if t is not None:
            t.join(timeout=10)
            with self._thread_lock:
                self._thread = None
        with self._thread_lock:
            err = self._erro_thread
            self._erro_thread = None
        if err is not None:
            raise err
