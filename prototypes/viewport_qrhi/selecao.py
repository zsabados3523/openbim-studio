# SPDX-License-Identifier: AGPL-3.0-or-later
"""Seleção por clique na CPU (sem GPU, sem Qt): raio x triângulos com caixas delimitadoras.

Uma `Malha` é uma lista de objetos (id, vértices, triângulos). O `pick` lança o raio, testa a caixa
de cada objeto (vetorizado em numpy), ordena pela entrada do raio e só testa triângulos dos objetos
cuja caixa pode ainda vencer o melhor acerto (parada antecipada).
"""
from __future__ import annotations

import numpy as np

_EPS = 1e-9


class Malha:
    """Objetos com id. Triângulos de cada objeto ficam contíguos em um só vetor (T, 3, 3)."""

    def __init__(self, objetos):
        """`objetos`: iterável de (id, vertices (N,3), indices (M,3) ou (3M,))."""
        tris, ids, ini, fim = [], [], [], []
        n = 0
        for oid, v, idx in objetos:
            v = np.asarray(v, dtype=np.float32).reshape(-1, 3)
            t = v[np.asarray(idx, dtype=np.int64).reshape(-1, 3)]
            if len(t) == 0:
                continue
            tris.append(t)
            ids.append(oid)
            ini.append(n)
            n += len(t)
            fim.append(n)
        self.triangulos = np.concatenate(tris) if tris else np.zeros((0, 3, 3), np.float32)
        self.ids = ids
        self.ini = np.array(ini, dtype=np.int64)
        self.fim = np.array(fim, dtype=np.int64)
        if ids:  # caixa de cada objeto (reduceat sobre os intervalos contíguos)
            self.caixa_min = np.minimum.reduceat(self.triangulos.min(axis=1), self.ini)
            self.caixa_max = np.maximum.reduceat(self.triangulos.max(axis=1), self.ini)
        else:
            self.caixa_min = self.caixa_max = np.zeros((0, 3), np.float32)

    @property
    def n_triangulos(self) -> int:
        return len(self.triangulos)


def malha_de_ifc(caminho) -> Malha:
    """Constrói a malha de um IFC pelo iterador do IfcOpenShell (um objeto por produto, sem threads)."""
    import ifcopenshell
    import ifcopenshell.geom

    f = ifcopenshell.open(str(caminho))
    cfg = ifcopenshell.geom.settings()
    cfg.set("use-world-coords", True)
    it = ifcopenshell.geom.iterator(cfg, f, 1)
    objetos = []
    if it.initialize():
        while True:
            s = it.get()
            g = s.geometry
            objetos.append((s.guid, np.array(g.verts, dtype=np.float32), np.array(g.faces, dtype=np.int64)))
            if not it.next():
                break
    return Malha(objetos)


def raio_da_tela(camera, x, y, largura, altura, modelo_inversa=None):
    """Raio (origem, direção unitária) para o pixel (x, y), com y crescendo para baixo.

    Use as mesmas unidades de `x, y` e `largura, altura` (pixels lógicos ou do dispositivo: só a
    razão importa). `modelo_inversa` (4x4) leva o raio ao espaço do modelo, se o desenho girar o objeto.
    """
    camera.proporcao = largura / max(altura, 1)
    inv = np.linalg.inv(camera.matriz_projecao() @ camera.matriz_vista())
    nx, ny = 2.0 * x / largura - 1.0, 1.0 - 2.0 * y / altura
    pts = []
    for nz in (-1.0, 1.0):
        p = inv @ np.array([nx, ny, nz, 1.0])
        pts.append(p[:3] / p[3])
    if modelo_inversa is not None:
        pts = [(modelo_inversa @ np.append(p, 1.0))[:3] for p in pts]
    d = pts[1] - pts[0]
    return pts[0], d / np.linalg.norm(d)


def _caixas(malha, o, d):
    """Distância de entrada do raio em cada caixa (inf se erra)."""
    with np.errstate(divide="ignore", invalid="ignore"):
        inv = 1.0 / d
        t1 = (malha.caixa_min - o) * inv
        t2 = (malha.caixa_max - o) * inv
    # raio paralelo ao eixo e fora da laje gera nan/inf: tratar abaixo
    tmin = np.fmax.reduce(np.fmin(t1, t2), axis=1)
    tmax = np.fmin.reduce(np.fmax(t1, t2), axis=1)
    paralelo = np.abs(d) < _EPS
    if paralelo.any():
        fora = ((o[paralelo] < malha.caixa_min[:, paralelo]) | (o[paralelo] > malha.caixa_max[:, paralelo])).any(axis=1)
    else:
        fora = np.zeros(len(tmin), bool)
    ok = (tmax >= np.maximum(tmin, 0.0)) & ~fora
    return np.where(ok, np.maximum(tmin, 0.0), np.inf)


def _distancia_tri(tris, o, d):
    """Möller-Trumbore: menor t > 0 entre os triângulos (inf se nenhum). Dupla face."""
    a = tris[:, 0].astype(np.float64)
    e1 = tris[:, 1] - tris[:, 0]
    e2 = tris[:, 2] - tris[:, 0]
    p = np.cross(d, e2)
    det = np.einsum("ij,ij->i", e1, p)
    with np.errstate(divide="ignore", invalid="ignore"):
        inv = 1.0 / det
        s = o - a
        u = np.einsum("ij,ij->i", s, p) * inv
        q = np.cross(s, e1)
        v = (q @ d) * inv
        t = np.einsum("ij,ij->i", e2, q) * inv
    with np.errstate(invalid="ignore"):
        ok = (np.abs(det) > _EPS) & (u >= 0) & (v >= 0) & (u + v <= 1) & (t > 0)
    return float(t[ok].min()) if ok.any() else np.inf


def pick_raio(malha: Malha, origem, direcao):
    """Id do objeto mais próximo atingido pelo raio, ou None. Devolve também a distância: (id, t)."""
    if not malha.ids:
        return None, np.inf
    o = np.asarray(origem, dtype=np.float64)
    d = np.asarray(direcao, dtype=np.float64)
    d = d / np.linalg.norm(d)
    entrada = _caixas(malha, o, d)
    cand = np.flatnonzero(np.isfinite(entrada))
    melhor, melhor_id = np.inf, None
    for i in cand[np.argsort(entrada[cand], kind="stable")]:
        if entrada[i] > melhor:  # as demais caixas só começam depois do melhor acerto
            break
        t = _distancia_tri(malha.triangulos[malha.ini[i]:malha.fim[i]], o, d)
        if t < melhor:
            melhor, melhor_id = t, malha.ids[i]
    return melhor_id, melhor


def pick(malha: Malha, camera, x, y, largura, altura, modelo_inversa=None):
    """Id do objeto sob o pixel (x, y) ou None."""
    o, d = raio_da_tela(camera, x, y, largura, altura, modelo_inversa)
    return pick_raio(malha, o, d)[0]
