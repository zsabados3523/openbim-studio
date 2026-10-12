# SPDX-License-Identifier: AGPL-3.0-or-later
"""Carregador de malhas do IFC (S03-T05 parte A; processo separado na S03-T08-B1). Python puro, sem Qt.

Especificação: docs/state/reports/LOTE_OPUS_4.md §1.2 e §1.3 e LOTE_OPUS_6.md §2.2 D3. Quem abre o IFC e gera
os triângulos (`ifcopenshell.geom.iterator`, um iterador por bloco) é um processo filho (`processo_malhas.py`);
a thread interna só lê as mensagens, vigia o filho e entrega `LoteMalha` (só numpy) por uma fila limitada.
Durante a carga o pai não abre o arquivo (`manter_arquivo=True` abre depois que o filho terminou).
"""
from __future__ import annotations

import multiprocessing
import os
import queue
import sys
import threading
import time
from dataclasses import dataclass, field, replace

import numpy as np

DTYPE_VERTICE = np.dtype([("pos", "<f4", (3,)), ("normal", "<f4", (3,)), ("cor", "u1", (4,))])
DTYPE_OBJETO = np.dtype([
    ("id_step", "<i4"), ("guid", "S22"),
    ("primeiro_indice", "<u4"), ("n_indices", "<u4"), ("primeiro_vertice", "<u4"), ("n_vertices", "<u4"),
    ("caixa_min", "<f4", (3,)), ("caixa_max", "<f4", (3,)),
])
MAX_BYTES_LOTE = 8 * 1024 * 1024
CINZA = (204, 204, 204, 255)
FATIA_S = 0.05


@dataclass(frozen=True)
class LoteMalha:
    indice_lote: int
    vertices: np.ndarray
    indices: np.ndarray
    objetos: np.ndarray
    deslocamento: np.ndarray
    produtos_feitos: int
    produtos_total: int


@dataclass(frozen=True)
class ResumoCarga:
    estado: str  # "concluido" | "cancelado" | "erro"
    erro: str | None
    produtos_total: int = 0
    produtos_com_malha: int = 0
    triangulos: int = 0
    vertices: int = 0
    lotes: int = 0
    sem_malha: list = field(default_factory=list)  # (id_step, guid, classe, motivo)
    tempos: dict = field(default_factory=dict)  # abrir_s, listar_s, geometria_s, total_s
    threads: int = 1
    tamanho_bloco: int = 0
    mensagens: list = field(default_factory=list)
    pico_filho_mb: float = 0.0  # pico de memória do processo filho (informado por ele)


class _Cancelado(Exception):
    pass


def _unitarias(n):
    c = np.linalg.norm(n, axis=1, keepdims=True)
    return np.where(c > 1e-12, n / np.where(c > 1e-12, c, 1.0), np.array([0.0, 0.0, 1.0]))


def _produto_para_numpy(geo, paleta):
    """Geometria do iterador -> (pos float64 (n,3), normal float32 (n,3), cor uint8 (n,4), indices uint32 (3m,)) ou None."""
    # D2 (LOTE_OPUS_6 §2.2): vetores prontos do IfcOpenShell (int32 e float64) em vez de tuplas; ~17x mais rápido.
    faces = np.frombuffer(geo.faces_buffer, dtype=np.int32).astype(np.int64).reshape(-1, 3)
    if len(faces) == 0:
        return None
    pos = np.frombuffer(geo.verts_buffer, dtype=np.float64).reshape(-1, 3).copy()  # cópia: não depende do buffer do iterador
    normais = np.frombuffer(geo.normals_buffer, dtype=np.float64).reshape(-1, 3)
    mids = np.frombuffer(geo.material_ids_buffer, dtype=np.int32).astype(np.int64)
    k = len(paleta) - 1  # última linha = cinza
    tm = np.where((mids < 0) | (mids >= k), k, mids) if len(mids) == len(faces) else np.full(len(faces), k)
    if len(normais) != len(pos):  # sem normais: normal de cada face, vértices separados
        tri = pos[faces]
        nf = _unitarias(np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]))
        return (tri.reshape(-1, 3), np.repeat(nf, 3, axis=0).astype(np.float32),
                paleta[np.repeat(tm, 3)], np.arange(3 * len(faces), dtype=np.uint32))
    normais = _unitarias(normais).astype(np.float32)
    if np.all(tm == tm[0]):
        return pos, normais, np.tile(paleta[tm[0]], (len(pos), 1)), faces.ravel().astype(np.uint32)
    p = len(paleta)  # vértice usado por cores diferentes é duplicado
    chave = (faces * p + tm[:, None]).ravel()
    uniq, inv = np.unique(chave, return_inverse=True)
    orig = uniq // p
    return pos[orig], normais[orig], paleta[uniq % p], inv.astype(np.uint32)


def _paleta(geo):
    linhas = []
    for m in geo.materials:
        try:
            d = m.diffuse
            alfa = 1.0 - float(m.transparency) if m.has_transparency() else 1.0
            rgba = [d.r(), d.g(), d.b(), alfa]
        except Exception:
            linhas.append(CINZA)
            continue
        linhas.append(tuple(int(x) for x in np.clip(np.rint(np.array(rgba) * 255.0), 0, 255)))
    linhas.append(CINZA)
    return np.array(linhas, dtype=np.uint8).reshape(-1, 4)


def _montar_lote(indice, prods, desl, feitos, total):
    """prods: lista de (id_step, guid, pos64, normal, cor, indices) em ordem de id."""
    nv = sum(len(p[2]) for p in prods)
    verts = np.empty(nv, dtype=DTYPE_VERTICE)
    objs = np.empty(len(prods), dtype=DTYPE_OBJETO)
    partes_idx = []
    iv = ii = 0
    for j, (idp, guid, pos, nor, cor, idx) in enumerate(prods):
        n = len(pos)
        p32 = (pos - desl).astype(np.float32)  # subtrai em float64, depois converte
        verts["pos"][iv:iv + n] = p32
        verts["normal"][iv:iv + n] = nor
        verts["cor"][iv:iv + n] = cor
        partes_idx.append((idx + np.uint32(iv)).astype(np.uint32))
        objs[j] = (idp, guid.encode("ascii"), ii, len(idx), iv, n, p32.min(axis=0), p32.max(axis=0))
        iv, ii = iv + n, ii + len(idx)
    indices = np.concatenate(partes_idx).astype(np.uint32)
    for a in (verts, indices, objs):
        a.flags.writeable = False
    return LoteMalha(indice, verts, indices, objs, desl, feitos, total)


class CarregadorMalhas:
    # D1 (LOTE_OPUS_6 §2.2): a híbrida tenta a biblioteca rápida e cai na "opencascade" nos recortes de abertura.
    # Curiosidade: has_geometry_library() responde falso para esse nome, mas o iterador o aceita.
    def __init__(self, caminho, threads=None, tamanho_bloco=4000, fila_max=4,
                 excluir=("IfcFeatureElementSubtraction", "IfcSpace"),
                 biblioteca="hybrid-cgal-simple-opencascade", max_bytes_lote=MAX_BYTES_LOTE, manter_arquivo=False):
        self.caminho = str(caminho)
        self.biblioteca = str(biblioteca)
        self.max_bytes_lote = int(max_bytes_lote)
        self.manter_arquivo = bool(manter_arquivo)
        self.threads = int(threads) if threads else max(1, (os.cpu_count() or 2) - 1)
        self.tamanho_bloco = int(tamanho_bloco)
        self.excluir = tuple(excluir)
        self._fila = queue.Queue(maxsize=max(1, int(fila_max)))
        self._cancelar = threading.Event()
        self._pronto = threading.Event()  # resumo montado
        self._resumo = None
        self._entregue = False
        self._lock = threading.Lock()
        self._thread = None
        self._arquivo = None
        self._lotes_produzidos = 0
        self._descartados = 0
        self._fase = None  # última fase informada pelo filho
        self._produtos = {}  # id_step -> (guid, classe, nome, família), de `inicio`
        self._concluidos = set()  # ids avisados em `feitos`

    # ---- interface pública ----
    @property
    def arquivo(self):
        return self._arquivo

    @property
    def lotes_produzidos(self):
        return self._lotes_produzidos

    def iniciar(self):
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._trabalhar, name="carregador-malhas", daemon=True)
        self._thread.start()

    def cancelar(self):
        self._cancelar.set()

    def aguardar(self, timeout=None):
        if self._thread is None:
            return True
        self._thread.join(timeout)
        return not self._thread.is_alive()

    def obter(self, timeout=0.0):
        fim = time.perf_counter() + (timeout or 0.0)
        while True:
            if self._cancelar.is_set():  # depois de cancelar() só o resumo sai
                self._esvaziar()
                if self._pronto.wait(max(0.0, fim - time.perf_counter())):
                    return self._entregar_resumo()
                return None
            restante = fim - time.perf_counter()
            try:  # nunca `timeout=None` (esperaria para sempre): sem tempo sobrando, só olha a fila
                return self._fila.get(timeout=min(FATIA_S, restante)) if restante > 0 else self._fila.get_nowait()
            except queue.Empty:
                pass
            if self._pronto.is_set() and self._fila.empty():
                return self._entregar_resumo()
            if time.perf_counter() >= fim:
                return None

    # ---- internos ----
    def _esvaziar(self):
        try:
            while True:
                self._fila.get_nowait()
                self._descartados += 1
        except queue.Empty:
            pass

    def _entregar_resumo(self):
        with self._lock:
            if self._entregue:
                return None
            self._entregue = True
            r = self._resumo
            if self._descartados and r.estado == "concluido":  # cancelar() jogou lotes fora: não é "concluido"
                r = replace(r, estado="cancelado",
                            mensagens=r.mensagens + [f"{self._descartados} lote(s) descartado(s) pelo cancelamento"])
            return r

    def _checar(self):
        if self._cancelar.is_set():
            raise _Cancelado()

    def _colocar(self, lote):
        while True:
            self._checar()
            try:
                self._fila.put(lote, timeout=FATIA_S)
                return
            except queue.Full:
                pass

    def _trabalhar(self):
        """Thread leitora e vigia: cria o filho (processo_malhas), lê as mensagens e alimenta a fila."""
        t0 = time.perf_counter()
        est = {"estado": "erro", "erro": None, "produtos_total": 0, "ids": set(), "tri": 0, "vert": 0,
               "lotes": 0, "sem": [], "t": {"abrir_s": 0.0, "listar_s": 0.0, "geometria_s": 0.0}, "msgs": [],
               "pico_filho": 0.0}
        try:
            self._ler(est)
            est["estado"] = "concluido"
        except _Cancelado:
            est["estado"] = "cancelado"
        except BaseException as e:  # nenhuma exceção escapa da thread
            est["estado"], est["erro"] = "erro", f"{type(e).__name__}: {e}" or "erro desconhecido"
        est["t"]["total_s"] = time.perf_counter() - t0
        if est["estado"] == "concluido" and self.manter_arquivo:  # só depois que o filho terminou (picos não se somam)
            try:
                import ifcopenshell
                self._arquivo = ifcopenshell.open(self.caminho)
            except Exception as e:
                est["msgs"].append(f"não foi possível manter o arquivo aberto: {e}")
        self._resumo = ResumoCarga(
            est["estado"], est["erro"], est["produtos_total"], len(est["ids"]), est["tri"], est["vert"],
            est["lotes"], est["sem"], est["t"], self.threads, self.tamanho_bloco, est["msgs"], est["pico_filho"])
        self._pronto.set()

    def _ler(self, est):
        try:
            from . import processo_malhas
        except ImportError:  # pragma: no cover
            import processo_malhas
        ctx = multiprocessing.get_context("spawn")  # também no Linux: igual nos dois sistemas, sem cópia com Qt ativo
        rx, tx = ctx.Pipe(duplex=False)  # um canal por filho; Queue seria corrompida ao matar o filho
        params = {"caminho": self.caminho, "threads": self.threads, "tamanho_bloco": self.tamanho_bloco,
                  "excluir": self.excluir, "biblioteca": self.biblioteca, "max_bytes_lote": self.max_bytes_lote}
        filho = ctx.Process(target=processo_malhas.entrada, args=(tx, params), name="obim-malhas", daemon=True)
        try:
            self._checar()
            filho.start()
            tx.close()  # só o filho guarda a ponta de escrita: se ele morrer, o pai vê o fim do canal
            fim = False
            while not fim:
                self._checar()
                if not rx.poll(FATIA_S):
                    continue
                try:
                    tipo, dados = rx.recv()
                except (EOFError, OSError):
                    filho.join(2)
                    raise RuntimeError(f"o processo de conversão terminou sem avisar (código {filho.exitcode})")
                fim = self._tratar(tipo, dados, est)
        finally:
            if filho.is_alive() and filho.pid is not None:
                try:
                    est["pico_filho"] = max(est["pico_filho"], processo_malhas.pico_memoria_mb(
                        filho.pid if sys.platform != "win32" else filho.sentinel))
                except Exception:
                    pass
            if filho.pid is not None:
                if filho.is_alive():
                    filho.kill()
                filho.join(2)
            for c in (rx, tx):
                try:
                    c.close()
                except OSError:
                    pass

    def _tratar(self, tipo, dados, est):
        """Aplica uma mensagem do filho. Devolve True na última (`fim`)."""
        if tipo == "fase":
            self._fase = dados
        elif tipo == "inicio":
            est["produtos_total"] = dados["total"]
            self._produtos = {i: (g, c, n, f) for i, g, c, n, f in dados["produtos"]}
        elif tipo == "lote":
            dados = replace(dados, vertices=dados.vertices.copy(), indices=dados.indices.copy(), objetos=dados.objetos.copy())
            for a in (dados.vertices, dados.indices, dados.objetos):  # cópia própria (o recebido aponta para o buffer do canal)
                a.flags.writeable = False
            est["lotes"] += 1
            est["ids"].update(int(i) for i in dados.objetos["id_step"])
            est["tri"] += len(dados.indices) // 3
            est["vert"] += len(dados.vertices)
            self._lotes_produzidos += 1
            self._colocar(dados)
        elif tipo == "feitos":
            self._concluidos.add(dados)
        elif tipo == "sem_malha":
            est["sem"].extend(dados)
        elif tipo == "erro":
            raise RuntimeError(dados)
        elif tipo == "fim":
            est["t"].update(dados["tempos"])
            est["msgs"] = dados["mensagens"]
            est["pico_filho"] = dados["pico_memoria_mb"]
            return True
        return False
