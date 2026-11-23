# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oraculo 3 da F0-S06-T24c: defeitos novos da revisao 2 (Z grande e cena mista origem + UTM).

Cobre os dois defeitos reproduzidos em REVISAO_ANTERIOR.md sem alterar os oraculos 1 e 2:
1. Defeito 1 (`eps` desalinhado de `eps_plano` em Z grande):
   - Classificacao silenciosa errada em `z = 1e6 + 1.2`, `1e8 + 1.2`, `1e9 + 1.2`:
     parede cortada precisa ter secao, viga acima nao pode ser enviada e nao pode haver
     `secao_aberta` falsa.
   - Mesma cena deslocada em Z (`1e6`, `1e8`, `1e9`, `-1e9`) produz resultado equivalente
     ao da origem (`enviados` iguais e geometria SVG dentro de `1e-6 m`).
   - Zona morta (`eps_plano < zmin - z <= eps`): peca acima com gap pequeno nao pode
     causar `secao_aberta` falsa nem entrar em `enviados`.
2. Defeito 2 (origem `(ox, oy)` travada em `v[0]` da primeira peca em cena mista origem + UTM):
   - Peca marcador em `(0, 0)` ou `(999, 0)` com GUID primeiro + moldura 3 cm com furo 2.2 cm
     e bloco 0.8 cm em UTM `(500000.123456, 7500000.654321)`: bloco no furo visivel, sem
     `secao_aberta`.
   - Marcador em `(0, 0)` ou `(999, 0)` + coluna 2 cm em UTM: sem `secao_aberta` falsa.
   - Resultado geometrico no SVG independe do GUID / ordem da primeira peca (renomear
     `G_0_MARC` -> `G_Z_MARC` mantem secao, projecao e `viewBox` equivalentes).
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from types import SimpleNamespace

import numpy as np
import pytest

from obim_geometria import planta_cache
from openbim_app.desenho import estilo

NS_IFC = "{http://www.ifcopenshell.org/ns}"
_TOK_RE = re.compile(r"[-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?|[a-zA-Z]")

_UTM = (500_000.123456, 7_500_000.654321)


# ---------- construtores sinteticos numpy ----------
def _caixa_np(
    x0: float, y0: float, z0: float, x1: float, y1: float, z1: float
) -> tuple[np.ndarray, np.ndarray]:
    verts = np.array(
        [
            [x0, y0, z0], [x1, y0, z0], [x1, y1, z0], [x0, y1, z0],
            [x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1],
        ],
        dtype=np.float64,
    )
    tris = np.array(
        [
            [0, 2, 1], [0, 3, 2],
            [4, 5, 6], [4, 6, 7],
            [0, 1, 5], [0, 5, 4],
            [1, 2, 6], [1, 6, 5],
            [2, 3, 7], [2, 7, 6],
            [3, 0, 4], [3, 4, 7],
        ],
        dtype=np.int32,
    )
    return verts, tris


def _tubo_np(
    ext: list[tuple[float, float]],
    furo: list[tuple[float, float]],
    z0: float,
    z1: float,
) -> tuple[np.ndarray, np.ndarray]:
    verts = np.array([(x, y, z) for z in (z0, z1) for x, y in ext + furo], dtype=np.float64)
    tris = []
    for i in range(4):
        j = (i + 1) % 4
        a, b, c, d = i, j, 4 + j, 4 + i
        tris += [(a, c, b), (a, d, c), (a + 8, b + 8, c + 8), (a + 8, c + 8, d + 8)]
        tris += [(i, j, 8 + j), (i, 8 + j, 8 + i), (4 + j, 4 + i, 12 + i), (4 + j, 12 + i, 12 + j)]
    return verts, np.array(tris, dtype=np.int32)


def _transladar_malha(
    malha: tuple[np.ndarray, np.ndarray], ox: float = 0.0, oy: float = 0.0, oz: float = 0.0
) -> tuple[np.ndarray, np.ndarray]:
    v, t = malha
    v2 = v.astype(np.float64, copy=True)
    if ox:
        v2[:, 0] += float(ox)
    if oy:
        v2[:, 1] += float(oy)
    if oz:
        v2[:, 2] += float(oz)
    return v2, t.copy()


# ---------- stub IFC leve ----------
class _FalsaEntidade:
    def __init__(self, id_step: int, guid: str, classe: str, *, elevation: float = 0.0):
        self._id = int(id_step)
        self.GlobalId = str(guid)
        self._classe = str(classe)
        self.Elevation = float(elevation)
        self.Representation = object()

    def id(self) -> int:
        return self._id

    def is_a(self, nome: str | None = None):
        if nome is None:
            return self._classe
        return self._classe == nome


class _FalsoIfc:
    def __init__(self, pav_guid: str, entidades: list[_FalsaEntidade]):
        self._pav = _FalsaEntidade(1, pav_guid, "IfcBuildingStorey", elevation=0.0)
        self._por_id = {1: self._pav, **{e.id(): e for e in entidades}}
        self._por_guid = {pav_guid: self._pav, **{e.GlobalId: e for e in entidades}}

    def by_id(self, id_step: int):
        return self._por_id.get(int(id_step))

    def by_guid(self, gid: str):
        return self._por_guid.get(str(gid))


def _montar_cena_numpy(
    pecas: list[tuple[int, str, str, tuple[np.ndarray, np.ndarray]]],
    *,
    altura_corte_m: float = 1.2,
    pav_guid: str = "PAV_OR3",
    threads: int | None = 1,
):
    entidades = [_FalsaEntidade(i, g, cls) for i, g, cls, _ in pecas]
    f = _FalsoIfc(pav_guid, entidades)
    elementos = [(i, g) for i, g, _, _ in pecas]
    malhas = {g: m for _, g, _, m in pecas}
    pedido = {
        "vista": {
            "tipo": "PLANTA",
            "pavimento": pav_guid,
            "escala": 1.0,
            "altura_corte_m": float(altura_corte_m),
        },
        "elementos": list(elementos),
    }
    if threads is not None:
        pedido["threads"] = threads
    return f, pedido, malhas, elementos


# ---------- parser SVG e metrica geometrica ----------
def _extrair_polilinhas_d(d: str) -> list[np.ndarray]:
    toks = _TOK_RE.findall(d)
    runs: list[list[tuple[float, float]]] = []
    atual: list[tuple[float, float]] | None = None
    cmd, i = "", 0
    while i < len(toks):
        tok = toks[i]
        if tok.isalpha():
            cmd = tok
            i += 1
            continue
        if cmd in ("M", "L") and i + 1 < len(toks):
            p = (float(tok), float(toks[i + 1]))
            if cmd == "M" or atual is None:
                if atual:
                    runs.append(atual)
                atual = [p]
                cmd = "L"
            else:
                atual.append(p)
            i += 2
        else:
            i += 1
    if atual:
        runs.append(atual)
    return [np.asarray(r, dtype=np.float64) for r in runs if len(r) >= 2]


def _parse_svg(svg: str) -> SimpleNamespace:
    root = ET.fromstring(svg)
    assert root.tag.rsplit("}", 1)[-1] == "svg"
    vb_raw = (root.get("viewBox") or "").split()
    viewbox = tuple(float(x) for x in vb_raw)
    proj_groups: list[ET.Element] = []
    cut_by_guid: dict[str, list[ET.Element]] = {}
    for elem in root.iter():
        if elem.tag.rsplit("}", 1)[-1] != "g":
            continue
        cls = (elem.get("class") or "").split()
        gid = elem.get(f"{NS_IFC}guid")
        if "IfcBuildingStorey" in cls:
            continue
        if "projection" in cls:
            proj_groups.append(elem)
        elif gid is not None:
            cut_by_guid.setdefault(gid, []).append(elem)
    return SimpleNamespace(root=root, viewbox=viewbox, proj_groups=proj_groups, cut_by_guid=cut_by_guid)


def _polilinhas_mundo(grupos: list[ET.Element], *, ox: float = 0.0, oy: float = 0.0) -> list[np.ndarray]:
    out: list[np.ndarray] = []
    for g in grupos:
        for p in g.iter():
            if p.tag.rsplit("}", 1)[-1] == "path":
                for r in _extrair_polilinhas_d(p.get("d") or ""):
                    pts = r.copy()
                    pts[:, 0] = pts[:, 0] - float(ox)
                    pts[:, 1] = -pts[:, 1] - float(oy)
                    out.append(pts)
    return out


def _polilinhas_para_segs(polilinhas: list[np.ndarray]) -> np.ndarray:
    partes = []
    for pl in polilinhas:
        if len(pl) >= 2:
            s = np.hstack([pl[:-1], pl[1:]])
            lens = np.hypot(s[:, 2] - s[:, 0], s[:, 3] - s[:, 1])
            s = s[lens > 1e-12]
            if len(s):
                partes.append(s)
    return np.vstack(partes) if partes else np.zeros((0, 4), dtype=np.float64)


def _dist_pontos_a_segs(pts: np.ndarray, segs: np.ndarray) -> np.ndarray:
    if len(pts) == 0:
        return np.zeros((0,), dtype=np.float64)
    if len(segs) == 0:
        return np.full(len(pts), np.inf, dtype=np.float64)
    a = segs[:, :2]
    d = segs[:, 2:] - a
    l2 = np.maximum((d * d).sum(axis=1), 1e-30)
    w = pts[:, None, :] - a[None, :, :]
    u = np.clip((w * d[None, :, :]).sum(axis=2) / l2[None, :], 0.0, 1.0)
    diff = w - u[:, :, None] * d[None, :, :]
    return np.sqrt((diff * diff).sum(axis=2)).min(axis=1)


def _pontos_de_segs(segs: np.ndarray, *, sub_por_seg: int = 5) -> np.ndarray:
    if len(segs) == 0:
        return np.zeros((0, 2), dtype=np.float64)
    ts = np.linspace(0.0, 1.0, sub_por_seg + 1, dtype=np.float64)[:, None]
    a = segs[:, None, :2]
    d = (segs[:, 2:] - segs[:, :2])[:, None, :]
    return (a + ts[None, :, :] * d).reshape(-1, 2)


def _hausdorff_segs(segs_a: np.ndarray, segs_b: np.ndarray) -> float:
    if len(segs_a) == 0 and len(segs_b) == 0:
        return 0.0
    if len(segs_a) == 0 or len(segs_b) == 0:
        return float("inf")
    da = float(_dist_pontos_a_segs(_pontos_de_segs(segs_a), segs_b).max())
    db = float(_dist_pontos_a_segs(_pontos_de_segs(segs_b), segs_a).max())
    return max(da, db)


def _assert_svg_equivalente(
    svg_ref: str,
    svg_alvo: str,
    *,
    ox: float = 0.0,
    oy: float = 0.0,
    tol: float = 1e-6,
    mapa_guid: dict[str, str] | None = None,
) -> None:
    """Exige igualdade geometrica (secao, projecao e viewBox) dentro de `tol`."""
    assert "-0.000000" not in svg_alvo
    estilo.aplicar_estilo(svg_alvo, "1:50")

    p_ref = _parse_svg(svg_ref)
    p_alvo = _parse_svg(svg_alvo)

    assert len(p_alvo.viewbox) == 4 and len(p_ref.viewbox) == 4
    vb_esperado = (
        p_ref.viewbox[0] + ox,
        p_ref.viewbox[1] - oy,
        p_ref.viewbox[2],
        p_ref.viewbox[3],
    )
    assert np.allclose(p_alvo.viewbox, vb_esperado, atol=tol, rtol=0.0), (
        f"viewBox divergente: obtido={p_alvo.viewbox}, esperado={vb_esperado}"
    )

    mapa = mapa_guid or {}
    esperado_gids = {mapa.get(g, g) for g in p_ref.cut_by_guid.keys()}
    assert set(p_alvo.cut_by_guid.keys()) == esperado_gids, (
        f"chaves de secao divergentes: obtido={sorted(p_alvo.cut_by_guid)}, esperado={sorted(esperado_gids)}"
    )

    for gid_ref in sorted(p_ref.cut_by_guid.keys()):
        gid_alvo = mapa.get(gid_ref, gid_ref)
        pls_r = _polilinhas_mundo(p_ref.cut_by_guid[gid_ref])
        pls_a = _polilinhas_mundo(p_alvo.cut_by_guid[gid_alvo], ox=ox, oy=oy)
        assert len(pls_a) == len(pls_r), f"{gid_alvo}: aneis ref={len(pls_r)} vs alvo={len(pls_a)}"
        for pl in pls_a:
            assert np.allclose(pl[0], pl[-1], atol=tol, rtol=0.0), f"{gid_alvo}: anel nao fechou"
        dist_corte = _hausdorff_segs(_polilinhas_para_segs(pls_r), _polilinhas_para_segs(pls_a))
        assert dist_corte <= tol, f"{gid_alvo}: divergencia na secao = {dist_corte:.3e} m > {tol:.1e} m"

    segs_proj_r = _polilinhas_para_segs(_polilinhas_mundo(p_ref.proj_groups))
    segs_proj_a = _polilinhas_para_segs(_polilinhas_mundo(p_alvo.proj_groups, ox=ox, oy=oy))
    dist_proj = _hausdorff_segs(segs_proj_r, segs_proj_a)
    assert dist_proj <= tol, f"divergencia na projecao = {dist_proj:.3e} m > {tol:.1e} m"


# ==========================================================================
# (1) DEFEITO 1: eps desalinhado de eps_plano em Z grande
# ==========================================================================
@pytest.mark.parametrize(
    ("dz", "topo_parede_acima", "viga_gap", "viga_topo"),
    [
        pytest.param(1e6, 5e-4, 5e-4, 9e-4, id="z_1e6p1p2"),
        pytest.param(1e8, 0.05, 0.05, 0.09, id="z_1e8p1p2"),
        pytest.param(1e9, 0.80, 0.20, 0.80, id="z_1e9p1p2"),
    ],
)
def test_defeito1_z_grande_classificacao_parede_cortada_e_viga_acima(
    dz: float, topo_parede_acima: float, viga_gap: float, viga_topo: float
):
    """Em Z grande (1e6+1.2, 1e8+1.2, 1e9+1.2): parede cortada tem secao, viga acima e excluida e resultado iguala a origem."""
    z_orig = 1.2
    parede_o = _caixa_np(0.0, 0.0, 0.0, 4.0, 0.4, z_orig + topo_parede_acima)
    viga_o = _caixa_np(5.0, 5.0, z_orig + viga_gap, 7.0, 5.4, z_orig + viga_topo)

    f_o, ped_o, mal_o, ev_o = _montar_cena_numpy(
        [
            (10, "G_PAREDE", "IfcWall", parede_o),
            (11, "G_VIGA_ACIMA", "IfcBeam", viga_o),
        ],
        altura_corte_m=z_orig,
    )
    resp_o, mot_o = planta_cache.desenhar_planta_cache(f_o, ped_o, mal_o, ev_o)
    assert mot_o is None and resp_o is not None and resp_o["ok"] is True
    assert resp_o["enviados"] == [10]

    z_alvo = dz + z_orig
    f_z, ped_z, mal_z, ev_z = _montar_cena_numpy(
        [
            (10, "G_PAREDE", "IfcWall", _transladar_malha(parede_o, oz=dz)),
            (11, "G_VIGA_ACIMA", "IfcBeam", _transladar_malha(viga_o, oz=dz)),
        ],
        altura_corte_m=z_alvo,
    )
    resp_z, mot_z = planta_cache.desenhar_planta_cache(f_z, ped_z, mal_z, ev_z)
    assert mot_z is None and resp_z is not None and resp_z["ok"] is True, (
        f"queda falsa em z={z_alvo}: motivo={mot_z!r}"
    )

    assert resp_z["enviados"] == [10], f"viga acima enviada em z={z_alvo}: enviados={resp_z['enviados']}"
    p_z = _parse_svg(resp_z["svg"])
    assert "G_PAREDE" in p_z.cut_by_guid, f"parede cortada sem secao em z={z_alvo}"
    assert "G_VIGA_ACIMA" not in p_z.cut_by_guid

    # Nenhum segmento da viga acima (x in [5, 7], y in [5, 5.4]) pode aparecer na projecao
    segs_proj_z = _polilinhas_para_segs(_polilinhas_mundo(p_z.proj_groups))
    if len(segs_proj_z) > 0:
        pts_viga = np.array([[5.0, 5.0], [7.0, 5.0], [7.0, 5.4], [5.0, 5.4]], dtype=np.float64)
        assert float(_dist_pontos_a_segs(pts_viga, segs_proj_z).min()) > 0.5, (
            f"viga acima desenhada na projecao em z={z_alvo}"
        )

    _assert_svg_equivalente(resp_o["svg"], resp_z["svg"], tol=1e-6)
