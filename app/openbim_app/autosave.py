# SPDX-License-Identifier: AGPL-3.0-or-later
"""Autosave local periódico e após recuperação (ADR-002 §4.5, §4.7 e §4.8)."""
import datetime
import hashlib
import json
import shutil
import threading
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import ifcopenshell

from .diario import Diario, codificar_ifc, lado_id_de, ler_diario, pasta_projeto, recuperar
from .gravacao_par import gravar_par, resolver_gravacao_pendente
from .lateral import Lateral
from .sessao_modelo import ModeloOcupado, ReentradaProibida, SessaoModelo
from .transacao import Historico

INTERVALO_AUTOSAVE_S = 300


def _sha256(caminho):
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def _ler_obim(caminho):
    objs = {}
    try:
        with zipfile.ZipFile(caminho) as z:
            for n in z.namelist():
                if n == "manifest.json":
                    continue
                partes = n.split("/")
                if len(partes) == 2 and partes[1].endswith(".json"):
                    objs.setdefault(partes[0], {})[partes[1][:-5]] = json.loads(z.read(n).decode("utf-8"))
    except Exception:
        pass
    return objs


def _obim_manifesto(caminho):
    try:
        with zipfile.ZipFile(caminho) as z:
            if "manifest.json" in z.namelist():
                return json.loads(z.read("manifest.json").decode("utf-8"))
    except Exception:
        pass
    return None


def _casa_lateral(base_obim_sha, lat):
    lat_sha = hashlib.sha256(lat.canonico()).hexdigest() if lat is not None else None
    if base_obim_sha is not None:
        return lat is not None and lat_sha == base_obim_sha
    return lat is None or lat.canonico() == b"{}"


@dataclass
class Projeto:
    caminho: Path
    lado_id: str
    arquivo: Any
    lateral: Lateral
    sessao: SessaoModelo
    historico: Historico
    diario: Diario
    autosave: Any
    recuperado: bool
    avisos: list[str]
    pendencia: str


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

        self._salvar_lock = threading.RLock()
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

    def gravar_normal(self):
        with self._salvar_lock:
            seq_salvo = [0]
            sha_lat = [None]

            def obter_seq():
                sha_lat[0] = hashlib.sha256(self._lateral.canonico()).hexdigest()
                s = self._diario.ultimo_seq
                seq_salvo[0] = s
                return s

            def ao_concluir(seq_final):
                self._diario.zerar(seq_final, ifc_caminho=self._ifc_origem, obim_sha256=sha_lat[0])

            g_ifc, g_obim = gravar_par(
                sessao=self._sessao,
                historico=self._historico,
                lateral=self._lateral,
                destino=self._ifc_origem,
                pasta_projeto=pasta_projeto(self._lado_id),
                lado_id=self._lado_id,
                seq=obter_seq,
                carimbo=True,
                ao_concluir=ao_concluir,
                autosave=False,
            )
            self.apos_gravacao_normal(seq_salvo[0])
            return g_ifc, g_obim

    def apos_gravacao_normal(self, seq=None):
        with self._salvar_lock:
            with self._sujo_lock:
                if seq is not None:
                    self._seq_salvo = max(self._seq_salvo, seq)
                else:
                    self._seq_salvo = max(self._seq_salvo, self._diario.ultimo_seq, self._max_anotado_seq)
            pasta_auto = pasta_projeto(self._lado_id) / "autosave"
            if pasta_auto.exists():
                for item in list(pasta_auto.iterdir()):
                    if item.is_dir() and not item.is_symlink():
                        shutil.rmtree(item)
                    else:
                        item.unlink()

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
        try:
            with self._sessao.ler(espera=0):
                pass
        except ReentradaProibida:
            raise RuntimeError("parar() não pode ser chamado dentro da sessão")
        except ModeloOcupado:
            pass

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


def abrir_projeto(ifc_caminho, perguntar) -> Projeto:
    ifc_path = Path(ifc_caminho).resolve()
    obim_path = ifc_path.with_suffix(".obim")
    avisos = []
    recuperado = False

    arq_disco = ifcopenshell.open(str(ifc_path))
    ifc_sha_disco = _sha256(ifc_path)
    lado_id = lado_id_de(arq_disco, ifc_sha_disco)
    pasta_proj = pasta_projeto(lado_id)

    # 1) Resolver gravação pendente do par do usuário em pasta_projeto(lado_id)
    def ao_concluir_usuario(seq):
        diario_caminho = pasta_proj / "diario" / "diario.obimlog"
        if diario_caminho.exists():
            regs_c, av_c = ler_diario(str(diario_caminho))
            if av_c:
                avisos.extend(av_c)
            if regs_c:
                lat_sha = None
                if obim_path.exists():
                    lat_sha = hashlib.sha256(Lateral(_ler_obim(obim_path)).canonico()).hexdigest()
                d = Diario.continuar(diario_caminho, lado_id, regs_c[0], regs_c[-1]["seq"])
                try:
                    d.zerar(seq, ifc_caminho=ifc_path, obim_sha256=lat_sha)
                finally:
                    d.fechar()

    pendencia = resolver_gravacao_pendente(pasta_proj, ifc_path, ao_concluir=ao_concluir_usuario)
    if pendencia not in ("sem_pendencia", "concluido", "desfeito"):
        avisos.append(f"gravação pendente do par não pôde ser resolvida ({pendencia})")

    # Refresh disco após resolver pendência do par
    ifc_sha_disco = _sha256(ifc_path)
    arq_disco = ifcopenshell.open(str(ifc_path))
    lateral_disco = Lateral(_ler_obim(obim_path)) if obim_path.exists() else Lateral()
    lat_sha_disco = hashlib.sha256(lateral_disco.canonico()).hexdigest() if obim_path.exists() else None

    # 2) Pendência e par do autosave em <pasta>/autosave/
    pasta_auto = pasta_proj / "autosave"
    auto_ifc = pasta_auto / ifc_path.name
    auto_obim = auto_ifc.with_suffix(".obim")
    if (pasta_auto / "gravacao.json").exists():
        res_auto = resolver_gravacao_pendente(pasta_auto, auto_ifc, ao_concluir=None)
        if res_auto not in ("sem_pendencia", "concluido", "desfeito"):
            avisos.append(f"gravação pendente do autosave não pôde ser resolvida ({res_auto}); autosave descartado")
            pasta_desc = pasta_proj / "autosave-descartado"
            if pasta_desc.exists():
                shutil.rmtree(pasta_desc)
            shutil.move(str(pasta_auto), str(pasta_desc))

    # 3) O diário
    diario_caminho = pasta_proj / "diario" / "diario.obimlog"
    regs = []
    if diario_caminho.exists():
        regs, av_d = ler_diario(str(diario_caminho))
        if av_d:
            avisos.extend(av_d)

    base_que_casa = None
    candidato_ifc = None
    candidato_lat = None

    if regs:
        base_reg = regs[0]
        base_ifc_sha = base_reg.get("ifc_sha256")
        base_obim_sha = base_reg.get("obim_sha256")

        # Candidato 1: Casa.ifc
        if base_ifc_sha == ifc_sha_disco and _casa_lateral(base_obim_sha, lateral_disco):
            base_que_casa = "casa"
            candidato_ifc = ifc_path
            candidato_lat = lateral_disco

        # Candidato 2: autosave
        if base_que_casa is None and auto_ifc.exists() and auto_obim.exists():
            man = _obim_manifesto(auto_obim)
            if man and man.get("origem_ifc_sha256") == ifc_sha_disco:
                lat_auto = Lateral(_ler_obim(auto_obim))
                if base_ifc_sha == _sha256(auto_ifc) and _casa_lateral(base_obim_sha, lat_auto):
                    base_que_casa = "autosave"
                    candidato_ifc = auto_ifc
                    candidato_lat = lat_auto

        # Candidato 3: .bak do autosave
        auto_ifc_bak = auto_ifc.with_name(auto_ifc.name + ".bak")
        auto_obim_bak = auto_obim.with_name(auto_obim.name + ".bak")
        if base_que_casa is None and auto_ifc_bak.exists() and auto_obim_bak.exists():
            man_bak = _obim_manifesto(auto_obim_bak)
            if man_bak and man_bak.get("origem_ifc_sha256") == ifc_sha_disco:
                lat_bak = Lateral(_ler_obim(auto_obim_bak))
                if base_ifc_sha == _sha256(auto_ifc_bak) and _casa_lateral(base_obim_sha, lat_bak):
                    base_que_casa = "autosave_bak"
                    candidato_ifc = auto_ifc_bak
                    candidato_lat = lat_bak

    if regs and base_que_casa is None:
        avisos.append("base do diário não confere com o modelo atual; diário descartado")
        d = Diario.abrir(lado_id, ifc_path, obim_sha256=lat_sha_disco)
        arquivo_final = arq_disco
        lateral_final = lateral_disco
        recuperado = False
        diario_obj = d
    elif regs and base_que_casa is not None:
        ha_trabalho = (len(regs) > 1) or (base_que_casa in ("autosave", "autosave_bak"))
        if ha_trabalho:
            hora_dt = datetime.datetime.fromisoformat(regs[-1]["hora"]).astimezone()
            texto_perg = f"Recuperar o trabalho de {hora_dt.strftime('%H:%M')}?"
            if perguntar(texto_perg):
                arquivo_final, lateral_final, av_rec = recuperar(candidato_ifc, diario_caminho, lateral=candidato_lat)
                if av_rec:
                    avisos.extend(av_rec)
                recuperado = True
                diario_obj = Diario.continuar(diario_caminho, lado_id, regs[0], regs[-1]["seq"])
            else:
                if pasta_auto.exists():
                    pasta_desc = pasta_proj / "autosave-descartado"
                    if pasta_desc.exists():
                        shutil.rmtree(pasta_desc)
                    shutil.move(str(pasta_auto), str(pasta_desc))
                d = Diario.abrir(lado_id, ifc_path, obim_sha256=lat_sha_disco)
                arquivo_final = arq_disco
                lateral_final = lateral_disco
                recuperado = False
                diario_obj = d
        else:
            diario_obj = Diario.continuar(diario_caminho, lado_id, regs[0], regs[-1]["seq"])
            arquivo_final = arq_disco
            lateral_final = lateral_disco
            recuperado = False
    else:
        d = Diario.abrir(lado_id, ifc_path, obim_sha256=lat_sha_disco)
        arquivo_final = arq_disco
        lateral_final = lateral_disco
        recuperado = False
        diario_obj = d

    sessao = SessaoModelo(arquivo_final)
    auto_ref = []
    historico = Historico(
        sessao,
        lateral_final,
        codificar=codificar_ifc,
        anotar=lambda tipo, ifc, lado: auto_ref[0].anotar(tipo, ifc, lado),
    )
    autosave = Autosave(
        sessao=sessao,
        historico=historico,
        lateral=lateral_final,
        diario=diario_obj,
        lado_id=lado_id,
        ifc_origem=ifc_path,
    )
    auto_ref.append(autosave)

    if recuperado and regs:
        with autosave._sujo_lock:
            autosave._seq_salvo = regs[0].get("seq", 0)
            autosave._max_anotado_seq = regs[-1]["seq"]

    return Projeto(
        caminho=ifc_path,
        lado_id=lado_id,
        arquivo=arquivo_final,
        lateral=lateral_final,
        sessao=sessao,
        historico=historico,
        diario=diario_obj,
        autosave=autosave,
        recuperado=recuperado,
        avisos=avisos,
        pendencia=pendencia,
    )
