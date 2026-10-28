# SPDX-License-Identifier: AGPL-3.0-or-later
"""Autosave local periódico e após recuperação (ADR-002 §4.5, §4.7 e §4.8)."""
import hashlib
import shutil
import threading
from pathlib import Path

from .diario import pasta_projeto
from .gravacao_par import gravar_par

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
        self._parar_ev = None
        self._erro_thread = None

    def anotar(self, tipo, ifc, lado):
        self._diario.anotar(tipo, ifc, lado)
        with self._sujo_lock:
            self._max_anotado_seq = self._diario.ultimo_seq

    def salvar(self) -> bool:
        with self._thread_lock:
            fora_da_thread = threading.current_thread() is not self._thread
            err = self._erro_thread if fora_da_thread else None
            if fora_da_thread:
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

            seq_salvo = [0]
            sha_lat = [None]

            def obter_seq():
                sha_lat[0] = hashlib.sha256(self._lateral.canonico()).hexdigest()
                return self._diario.ultimo_seq

            def ao_concluir(seq_final):
                self._diario.zerar(seq_final, ifc_caminho=destino_auto, obim_sha256=sha_lat[0])
                seq_salvo[0] = seq_final

            origem_sha = _sha256(self._ifc_origem)
            gravar_par(
                sessao=self._sessao,
                historico=self._historico,
                lateral=self._lateral,
                destino=destino_auto,
                pasta_projeto=pasta_auto,
                lado_id=self._lado_id,
                seq=obter_seq,
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
            ev = threading.Event()
            self._parar_ev = ev
            self._thread = threading.Thread(target=self._loop, args=(ev,), daemon=True)
            self._thread.start()

    def _loop(self, parar_ev):
        while not parar_ev.wait(self._intervalo_s):
            if parar_ev.is_set():
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
            ev = self._parar_ev
            if ev is not None:
                ev.set()
        if t is not None:
            t.join()
            with self._thread_lock:
                if self._thread is t:
                    self._thread = None
                    self._parar_ev = None
        with self._thread_lock:
            err = self._erro_thread
            self._erro_thread = None
        if err is not None:
            raise err
