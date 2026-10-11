# SPDX-License-Identifier: AGPL-3.0-or-later
"""Carregador de malhas do IFC em thread de trabalho (S03-T05, parte A). Python puro, sem Qt.

Especificação: docs/state/reports/LOTE_OPUS_4.md §1.2 e §1.3. A thread de trabalho abre o IFC, lista
os produtos, gera os triângulos com `ifcopenshell.geom.iterator` (um iterador por bloco, com `include=`)
e entrega `LoteMalha` (só numpy) por uma fila limitada. Só essa thread toca no `ifcopenshell.file`
enquanto a carga roda; nenhum objeto do IfcOpenShell entra em lote.
"""
from __future__ import annotations

import os
import queue
import threading
import time
from dataclasses import dataclass, field

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


class _Cancelado(Exception):
    pass


def _unitarias(n):
    c = np.linalg.norm(n, axis=1, keepdims=True)
    return np.where(c > 1e-12, n / np.where(c > 1e-12, c, 1.0), np.array([0.0, 0.0, 1.0]))


def _produto_para_numpy(geo, paleta):
    """Geometria do iterador -> (pos float64 (n,3), normal float32 (n,3), cor uint8 (n,4), indices uint32 (3m,)) ou None."""
    faces = np.asarray(geo.faces, dtype=np.int64).reshape(-1, 3)
    if len(faces) == 0:
        return None
    pos = np.asarray(geo.verts, dtype=np.float64).reshape(-1, 3)
    normais = np.asarray(geo.normals, dtype=np.float64).reshape(-1, 3)
    mids = np.asarray(geo.material_ids, dtype=np.int64)
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


def _agrupar(prods):
    """Parte a lista em grupos de no máximo ~8 MB de vértices, sempre em fronteira de produto."""
    grupos, atual, bytes_ = [], [], 0
    for p in prods:
        b = len(p[2]) * DTYPE_VERTICE.itemsize
        if atual and bytes_ + b > MAX_BYTES_LOTE:
            grupos.append(atual)
            atual, bytes_ = [], 0
        atual.append(p)
        bytes_ += b
    if atual:
        grupos.append(atual)
    return grupos


class CarregadorMalhas:
    def __init__(self, caminho, threads=None, tamanho_bloco=4000, fila_max=4,
                 excluir=("IfcFeatureElementSubtraction", "IfcSpace")):
        self.caminho = str(caminho)
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
            try:
                return self._fila.get(timeout=min(FATIA_S, max(0.0, fim - time.perf_counter())) or None) \
                    if timeout else self._fila.get_nowait()
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
        except queue.Empty:
            pass

    def _entregar_resumo(self):
        with self._lock:
            if self._entregue:
                return None
            self._entregue = True
            return self._resumo

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
        t0 = time.perf_counter()
        est = {"estado": "erro", "erro": None, "produtos_total": 0, "com_malha": 0, "tri": 0, "vert": 0,
               "lotes": 0, "sem": [], "t": {"abrir_s": 0.0, "listar_s": 0.0, "geometria_s": 0.0}}
        try:
            self._rodar(est)
            est["estado"] = "concluido"
        except _Cancelado:
            est["estado"] = "cancelado"
        except BaseException as e:  # nenhuma exceção escapa da thread
            est["estado"], est["erro"] = "erro", f"{type(e).__name__}: {e}" or "erro desconhecido"
        try:
            import ifcopenshell
            msgs = str(ifcopenshell.get_log()).splitlines()[-50:]
        except Exception:
            msgs = []
        est["t"]["total_s"] = time.perf_counter() - t0
        self._resumo = ResumoCarga(
            est["estado"], est["erro"], est["produtos_total"], est["com_malha"], est["tri"], est["vert"],
            est["lotes"], est["sem"], est["t"], self.threads, self.tamanho_bloco, msgs)
        self._pronto.set()

    def _rodar(self, est):
        import ifcopenshell
        import ifcopenshell.geom

        t = time.perf_counter()
        arq = ifcopenshell.open(self.caminho)
        est["t"]["abrir_s"] = time.perf_counter() - t
        t = time.perf_counter()
        produtos = [p for p in arq.by_type("IfcProduct")
                    if p.Representation is not None and not any(p.is_a(c) for c in self.excluir)]
        produtos.sort(key=lambda p: p.id())
        est["produtos_total"] = total = len(produtos)
        est["t"]["listar_s"] = time.perf_counter() - t
        cfg = ifcopenshell.geom.settings()
        cfg.set("use-world-coords", True)
        cfg.set("weld-vertices", False)
        tb = self.tamanho_bloco if self.tamanho_bloco > 0 else max(total, 1)
        desl, feitos = None, 0
        t = time.perf_counter()
        try:
            for ini in range(0, total, tb):
                bloco = produtos[ini:ini + tb]
                prods = self._bloco(ifcopenshell.geom, cfg, arq, bloco, est)
                feitos += len(bloco)
                for grupo in _agrupar(prods):
                    if desl is None:  # centro da caixa do primeiro lote, em float64, arredondado ao metro
                        mn = np.min([p[2].min(axis=0) for p in grupo], axis=0)
                        mx = np.max([p[2].max(axis=0) for p in grupo], axis=0)
                        desl = np.rint((mn + mx) / 2.0).astype(np.float64)
                    lote = _montar_lote(est["lotes"], grupo, desl, feitos, total)
                    est["lotes"] += 1
                    self._lotes_produzidos += 1
                    est["com_malha"] += len(grupo)
                    est["tri"] += len(lote.indices) // 3
                    est["vert"] += len(lote.vertices)
                    self._colocar(lote)
        finally:
            est["t"]["geometria_s"] = time.perf_counter() - t
            if not self._cancelar.is_set():
                self._arquivo = arq
        self._arquivo = arq

    def _bloco(self, geom, cfg, arq, bloco, est):
        """Gera e converte os produtos de um bloco. Devolve lista ordenada por id; falhas vão a est['sem']."""
        porid = {p.id(): p for p in bloco}
        achados = {}

        def sem(ids, motivo):
            for i in ids:
                p = porid[i]
                est["sem"].append((i, p.GlobalId, p.is_a(), motivo))

        try:
            it = geom.iterator(cfg, arq, self.threads, include=bloco, geometry_library="opencascade")
            try:
                if it.initialize():
                    while True:
                        s = it.get()
                        r = _produto_para_numpy(s.geometry, _paleta(s.geometry))
                        if r is not None and s.id in porid:
                            achados[s.id] = r
                        self._checar()
                        if not it.next():
                            break
            finally:
                del it
        except _Cancelado:
            raise
        except Exception as e:
            sem([i for i in porid if i not in achados], f"erro no iterador: {type(e).__name__}: {e}")
        else:
            sem([i for i in porid if i not in achados], "o iterador não devolveu geometria")
        self._checar()
        return [(i, porid[i].GlobalId, *achados[i]) for i in sorted(achados)]
