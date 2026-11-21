# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oraculo F0-S06-T24c (ADR-010, P3): motor de planta pelo cache de geometria (`planta_cache.py`).

Modulo alvo (o implementador NAO edita este arquivo; somente `geometria/obim_geometria/planta_cache.py`
e a ligacao minima em `geometria/obim_geometria/desenho.py`):

CONTRATO (ESPEC_T24bcde.md §1.3, §1.4, §2.1, §2.2, §3.2; tampa = Opcao 1):
1. Funcao publica:
   `planta_cache.desenhar_planta_cache(f, pedido, malhas_mundo, elementos_validos, *, fase=None, abrir_s=0.0, cache_s=0.0) -> tuple[dict | None, str | None]`
   - `f`: modelo IFC ou stub com `.by_id(id_step)` (entidade com `.id()`, `.GlobalId`, `.is_a(...)`)
     e `.by_guid(pav_guid)` (entidade `IfcBuildingStorey`).
   - `pedido`: dict com `vista` (`tipo="PLANTA"`, `pavimento=<guid>`, `escala=float`,
     `altura_corte_m=float`), `elementos`, opcional `threads`.
   - `malhas_mundo`: `dict[str, tuple[np.ndarray, np.ndarray]]` (`gid -> (verts (N,3) float64, tris (M,3) int)`).
   - `elementos_validos`: lista de pares `(id_step: int, gid: str)`.
   - Retorno: `(resp, None)` em sucesso (`resp["ok"] is True`) ou `(None, motivo)` em queda
     (`motivo in {"malha_invalida", "secao_aberta", "erro_motor"}`).
2. Validacao e classificacao pelo plano horizontal `z = float(pedido["vista"]["altura_corte_m"])`
   (`eps = 1e-9 * max(1.0, abs(z))`, `eps_plano = max(1e-9, 1e-12 * max(1.0, abs(z)))`):
   - Qualquer peca em `elementos_validos` ausente de `malhas_mundo`, vazia, nao finita,
     `|verts| > 1e12`, shape invalido, `tris` nao inteiro ou indice fora de `[0, len(verts))`
     -> queda do pavimento inteiro `(None, "malha_invalida")`.
   - `zmin > z + eps`: acima do corte (excluida do SVG e fora de `falhas_geometria`).
   - `zmax <= z + eps`: abaixo do corte (malha inteira entra em projecao).
   - `zmin <= z + eps < zmax`: cortada. Vertice no plano (`|vz - z| <= eps_plano`) ou
     `aneis_de_segmentos(segs)` com `abertos` nao vazio ou `not fechados`
     -> queda do pavimento inteiro `(None, "secao_aberta")`.
   - Secao calculada via `corte_plano.cortar_malha_no_plano` + `aneis.aneis_de_segmentos`.
3. Visibilidade e tampa (Opcao 1):
   - Todas as pecas abaixo do corte e metades inferiores (`len(t_ab) > 0`) das cortadas entram
     juntas em UMA unica chamada `visibilidade.linhas_visiveis_multi(..., angulo_graus=0.001, trabalhadores=...)`
     (0 chamadas a `visibilidade.linhas_visiveis`).
   - Recorte 2D de projecao fora dos aneis da secao via `recorte.recortar_fora_dos_aneis(..., encolher=5e-4)`,
     com grupos separados por anel externo + respectivos furos (par-impar por grupo, uniao entre grupos).
4. Formato do SVG e resposta:
   - Raiz `<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"
     xmlns:ifc="http://www.ifcopenshell.org/ns" viewBox="...">`, valido em XML e `estilo.aplicar_estilo`.
   - Grupo `<g class="IfcBuildingStorey" ifc:guid="{pav_guid}">`.
   - Secoes cortadas em `<g class="{Classe}" ifc:guid="{gid}"><path d="..."/></g>` (ordem `GlobalId` ascendente).
   - Projecao em um unico `<g class="projection">` (SEM `ifc:guid` no `<g>`).
   - Comandos de `<path d="...">` exclusivamente `M` e `L` (SEM `Z`); aneis fecham repetindo ponto inicial;
     coordenadas em metros com Y invertido `(x, -y)` e 6 casas decimais sem `-0.000000`.
   - `resp`: `ok=True`, `svg`, `n_paths`, `enviados` (inclui todas as pecas nao excluidas),
     `caixas=[]`, `em_cache=[]`, `pesados=[]`, `falhas_geometria=[]`, sem `faltantes`/`incompleta`,
     `tempos` com `abrir_s`, `geo_s=0.0`, `write_s=0.0`, `finalize_s=0.0`, `cache_s`, `corte_s`, `motor_s`.
5. Integracao em `desenho.py`:
   - `desenho._desenhar_planta_cache` delega para `planta_cache.desenhar_planta_cache`.
   - `desenho.processar` com `pasta_cache_geometria` devolve `via_cache=True`, `queda=None`, `n_faltantes=0`
     no sucesso, e cai o pavimento inteiro (`via_cache=False`, `queda="secao_aberta"|"malha_invalida"|"erro_motor"`)
     em falha.
"""
from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace

import ifcopenshell
import ifcopenshell.api
import numpy as np
import pytest

from obim_geometria import aneis, construtor, corte_plano, desenho, recorte, visibilidade
from openbim_app.desenho import estilo

NS_SVG = "{http://www.w3.org/2000/svg}"
NS_IFC = "{http://www.ifcopenshell.org/ns}"
_CMD_RE = re.compile(r"[a-zA-Z]")
_TOK_RE = re.compile(r"[-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?|[a-zA-Z]")


def _mod():
    """Importa sob demanda para que todos os testes sejam coletados e falhem antes da implementacao."""
    from obim_geometria import planta_cache

    return planta_cache


# ---------- construtores de malhas sinteticas numpy ----------
def _caixa_np(x0: float, y0: float, z0: float, x1: float, y1: float, z1: float) -> tuple[np.ndarray, np.ndarray]:
    """Malha soldada fechada de paralelepipedo (8 verts float64, 12 tris int32, normais para fora)."""
    verts = np.array(
        [
            [x0, y0, z0], [x1, y0, z0], [x1, y1, z0], [x0, y1, z0],
            [x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1],
        ],
        dtype=np.float64,
    )
    tris = np.array(
        [
            [0, 2, 1], [0, 3, 2],  # base (-Z)
            [4, 5, 6], [4, 6, 7],  # topo (+Z)
            [0, 1, 5], [0, 5, 4],  # frente (-Y)
            [1, 2, 6], [1, 6, 5],  # direita (+X)
            [2, 3, 7], [2, 7, 6],  # tras (+Y)
            [3, 0, 4], [3, 4, 7],  # esquerda (-X)
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
    """Moldura retangular fechada com furo vazado (anel externo + furo interno, soldada)."""
    verts = np.array([(x, y, z) for z in (z0, z1) for x, y in ext + furo], dtype=np.float64)
    tris = []
    for i in range(4):
        j = (i + 1) % 4
        a, b, c, d = i, j, 4 + j, 4 + i
        tris += [(a, c, b), (a, d, c), (a + 8, b + 8, c + 8), (a + 8, c + 8, d + 8)]
        tris += [(i, j, 8 + j), (i, 8 + j, 8 + i), (4 + j, 4 + i, 12 + i), (4 + j, 12 + i, 12 + j)]
    return verts, np.array(tris, dtype=np.int32)


def _telhado_dobra_np(
    x0: float, y0: float, x1: float, y1: float, z0: float, z1: float, *, angulo_diedro_graus: float = 2.0
) -> tuple[np.ndarray, np.ndarray]:
    """Bloco fechado cuja face superior tem cumeeira central com angulo diedro controlado."""
    xm = 0.5 * (x0 + x1)
    dz = math.tan(math.radians(angulo_diedro_graus / 2.0)) * (xm - x0)
    zc = z1 + dz
    verts = np.array(
        [
            [x0, y0, z0], [xm, y0, z0], [x1, y0, z0],
            [x1, y1, z0], [xm, y1, z0], [x0, y1, z0],
            [x0, y0, z1], [xm, y0, zc], [x1, y0, z1],
            [x1, y1, z1], [xm, y1, zc], [x0, y1, z1],
        ],
        dtype=np.float64,
    )
    tris = np.array(
        [
            # base (-Z)
            [0, 4, 1], [0, 5, 4], [1, 3, 2], [1, 4, 3],
            # duas aguas no topo (+Z) com cumeeira 7-10
            [6, 7, 10], [6, 10, 11],
            [7, 8, 9], [7, 9, 10],
            # frente (-Y)
            [0, 1, 7], [0, 7, 6], [1, 2, 8], [1, 8, 7],
            # direita (+X)
            [2, 3, 9], [2, 9, 8],
            # tras (+Y)
            [3, 4, 10], [3, 10, 9], [4, 5, 11], [4, 11, 10],
            # esquerda (-X)
            [5, 0, 6], [5, 6, 11],
        ],
        dtype=np.int32,
    )
    return verts, tris


def _degrau_no_plano_np(z_corte: float) -> tuple[np.ndarray, np.ndarray]:
    """Caixa que cruza z_corte e possui anel/face horizontal exatamente em z = z_corte."""
    v1, t1 = _caixa_np(0.0, 0.0, 0.0, 2.0, 0.4, z_corte)
    v2, t2 = _caixa_np(0.0, 0.0, z_corte, 1.0, 0.4, z_corte + 1.4)
    return np.vstack([v1, v2]), np.vstack([t1, t2 + len(v1)]).astype(np.int32)


# ---------- stub IFC leve (sem ifcopenshell para testes unitarios numpy) ----------
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
    pav_guid: str = "PAV_0001",
    threads: int | None = 1,
):
    """Monta (f, pedido, malhas_mundo, elementos_validos) a partir de pecas numpy puras."""
    entidades = [_FalsaEntidade(i, g, cls) for i, g, cls, _ in pecas]
    f = _FalsoIfc(pav_guid, entidades)
    elementos = [(i, g) for i, g, _, _ in pecas]
    malhas = {g: m for _, g, _, m in pecas}
    pedido = {
        "vista": {"tipo": "PLANTA", "pavimento": pav_guid, "escala": 1.0, "altura_corte_m": float(altura_corte_m)},
        "elementos": list(elementos),
    }
    if threads is not None:
        pedido["threads"] = threads
    return f, pedido, malhas, elementos


# ---------- parsers e metricas geometricas de SVG ----------
def _extrair_polilinhas_d(d: str) -> tuple[list[str], list[np.ndarray]]:
    """Extrai lista de comandos e polilinhas 2D (K, 2) em coordenadas SVG de um atributo `d`."""
    comandos = _CMD_RE.findall(d)
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
    return comandos, [np.asarray(r, dtype=np.float64) for r in runs if len(r) >= 2]


def _parse_svg(svg: str) -> SimpleNamespace:
    root = ET.fromstring(svg)
    assert root.tag.rsplit("}", 1)[-1] == "svg"
    storeys, proj_groups = [], []
    cut_by_guid: dict[str, list[ET.Element]] = {}
    all_paths: list[ET.Element] = []
    for elem in root.iter():
        tag = elem.tag.rsplit("}", 1)[-1]
        if tag == "path":
            all_paths.append(elem)
        elif tag == "g":
            cls = (elem.get("class") or "").split()
            gid = elem.get(f"{NS_IFC}guid")
            if "IfcBuildingStorey" in cls:
                storeys.append(elem)
            elif "projection" in cls:
                proj_groups.append(elem)
            elif gid is not None:
                cut_by_guid.setdefault(gid, []).append(elem)
    return SimpleNamespace(
        root=root,
        storeys=storeys,
        proj_groups=proj_groups,
        cut_by_guid=cut_by_guid,
        all_paths=all_paths,
    )


def _polilinhas_de_elementos(grupos: list[ET.Element]) -> list[np.ndarray]:
    """Retorna polilinhas em coordenadas do mundo (x, y) revertendo Y invertido do SVG."""
    out: list[np.ndarray] = []
    for g in grupos:
        for p in g.iter():
            if p.tag.rsplit("}", 1)[-1] == "path":
                _, runs = _extrair_polilinhas_d(p.get("d") or "")
                for r in runs:
                    pts = r.copy()
                    pts[:, 1] = -pts[:, 1]
                    out.append(pts)
    return out


def _polilinhas_para_segs(polilinhas: list[np.ndarray]) -> np.ndarray:
    partes = []
    for pl in polilinhas:
        if len(pl) >= 2:
            s = np.hstack([pl[:-1], pl[1:]])
            lens = np.hypot(s[:, 2] - s[:, 0], s[:, 3] - s[:, 1])
            s = s[lens > 1e-9]
            if len(s):
                partes.append(s)
    return np.vstack(partes) if partes else np.zeros((0, 4), dtype=np.float64)


def _simplificar_anel_colinear(pl: np.ndarray, tol: float = 1e-5) -> np.ndarray:
    """Remove vertices colineares intermediarios de uma polilinha (inclusive fechada)."""
    if len(pl) < 3:
        return pl
    fechado = bool(np.hypot(*(pl[0] - pl[-1])) <= tol)
    pts = pl[:-1] if fechado else pl
    if len(pts) < 3:
        return pl
    mantidos = []
    n = len(pts)
    for i in range(n):
        if not fechado and (i == 0 or i == n - 1):
            mantidos.append(pts[i])
            continue
        p_ant = pts[(i - 1) % n]
        p_cur = pts[i]
        p_prox = pts[(i + 1) % n]
        v1 = p_cur - p_ant
        v2 = p_prox - p_cur
        n1, n2 = float(np.hypot(*v1)), float(np.hypot(*v2))
        if n1 <= tol or n2 <= tol:
            continue
        cross = abs(float(v1[0] * v2[1] - v1[1] * v2[0])) / (n1 * n2)
        dot = float(v1[0] * v2[0] + v1[1] * v2[1]) / (n1 * n2)
        if not (cross <= 1e-4 and dot > 0.0):
            mantidos.append(p_cur)
    if len(mantidos) < 2:
        return pl
    arr = np.asarray(mantidos, dtype=np.float64)
    return np.vstack([arr, arr[0:1]]) if fechado else arr


def _contagem_segmentos_corte(polilinhas: list[np.ndarray]) -> int:
    """Conta segmentos geometricos de corte (apos fundir vertices colineares de faces trianguladas)."""
    total = 0
    for pl in polilinhas:
        simp = _simplificar_anel_colinear(pl)
        segs = _polilinhas_para_segs([simp])
        total += len(segs)
    return total


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


def _amostrar_segs(segs: np.ndarray, passo: float = 0.01) -> np.ndarray:
    if len(segs) == 0:
        return np.zeros((0, 2), dtype=np.float64)
    pts = []
    for s in segs:
        comp = float(np.hypot(s[2] - s[0], s[3] - s[1]))
        n = max(1, int(math.ceil(comp / passo)))
        t = ((np.arange(n, dtype=np.float64) + 0.5) / n)[:, None]
        pts.append(s[:2] + t * (s[2:] - s[:2]))
    return np.vstack(pts)


def _cobertura_bidirecional(segs_ref: np.ndarray, segs_cand: np.ndarray, *, tol: float = 5e-3) -> tuple[float, float]:
    """Retorna (recall, precisao) por amostragem de comprimento a `tol` metros."""
    p_ref = _amostrar_segs(segs_ref)
    p_cand = _amostrar_segs(segs_cand)
    recall = 1.0 if len(p_ref) == 0 else float((_dist_pontos_a_segs(p_ref, segs_cand) <= tol).mean())
    precisao = 1.0 if len(p_cand) == 0 else float((_dist_pontos_a_segs(p_cand, segs_ref) <= tol).mean())
    return recall, precisao


# ---------- cena IFC sintetica pequena em tmp_path (sem IFC real) ----------
def _criar_caixa_ifc(f, body, classe: str, comp: float, esp: float, alt: float, pos: tuple[float, float, float]):
    api = ifcopenshell.api.run
    el = api("root.create_entity", f, ifc_class=classe)
    rep = api("geometry.add_wall_representation", f, context=body, length=comp, height=alt, thickness=esp)
    el.Representation = f.createIfcProductDefinitionShape(Representations=[rep])
    m = np.eye(4)
    m[:3, 3] = pos
    api("geometry.edit_object_placement", f, product=el, matrix=m, is_si=False)
    return el


def _criar_cena_ifc_sintetica(tmp_path: Path, *, offset: tuple[float, float] = (0.0, 0.0)) -> SimpleNamespace:
    ox, oy = offset
    api = ifcopenshell.api.run
    f = api("project.create_file", version="IFC4")
    proj = api("root.create_entity", f, ifc_class="IfcProject")
    api("unit.assign_unit", f, units=[f.createIfcSIUnit(UnitType="LENGTHUNIT", Prefix=None, Name="METRE")])
    ctx = api("context.add_context", f, context_type="Model")
    body = api(
        "context.add_context",
        f,
        context_type="Model",
        context_identifier="Body",
        target_view="MODEL_VIEW",
        parent=ctx,
    )
    site = api("root.create_entity", f, ifc_class="IfcSite")
    predio = api("root.create_entity", f, ifc_class="IfcBuilding")
    andar = api("root.create_entity", f, ifc_class="IfcBuildingStorey", name="Terreo")
    andar.Elevation = 0.0
    for filho, pai in ((site, proj), (predio, site), (andar, predio)):
        api("aggregate.assign_object", f, products=[filho], relating_object=pai)

    parede = _criar_caixa_ifc(f, body, "IfcWall", 4.0, 0.2, 2.8, (ox, oy, 0.0))
    laje = _criar_caixa_ifc(f, body, "IfcSlab", 4.0, 3.0, 0.2, (ox, oy, -0.2))
    movel = _criar_caixa_ifc(f, body, "IfcFurnishingElement", 1.0, 0.8, 0.7, (ox + 1.0, oy + 1.2, 0.0))
    viga_acima = _criar_caixa_ifc(f, body, "IfcBeam", 4.0, 0.2, 0.4, (ox, oy + 2.0, 2.4))
    api("spatial.assign_container", f, products=[parede, laje, movel, viga_acima], relating_structure=andar)

    arq = tmp_path / "planta_sintetica.ifc"
    f.write(str(arq))
    f = ifcopenshell.open(str(arq))
    andar = f.by_guid(andar.GlobalId)
    parede = f.by_guid(parede.GlobalId)
    laje = f.by_guid(laje.GlobalId)
    movel = f.by_guid(movel.GlobalId)
    viga_acima = f.by_guid(viga_acima.GlobalId)

    pasta = tmp_path / "cache_geo"
    doc = construtor.documento_de(arq)
    with construtor.abrir_banco(pasta) as cache:
        r = construtor.construir_lote(f, cache, construtor.fila_inicial(f), documento=doc, assinatura="s1", memo={})
        assert r["falhas"] == 0 and r["gravadas"] == 4

    todos = [parede, laje, movel, viga_acima]
    vista = {"tipo": "PLANTA", "pavimento": andar.GlobalId, "escala": 1.0, "altura_corte_m": 1.2}
    pedido_base = {"arquivo": str(arq), "vista": vista, "elementos": [(e.id(), e.GlobalId) for e in todos], "threads": 1}
    return SimpleNamespace(
        arq=arq,
        pasta=pasta,
        f=f,
        andar=andar,
        parede=parede,
        laje=laje,
        movel=movel,
        viga_acima=viga_acima,
        pedido_base=pedido_base,
        pedido_cache={**pedido_base, "pasta_cache_geometria": str(pasta)},
    )


# ---------- testes funcionais do modulo planta_cache ----------
def test_classificacao_pecas_pelo_plano_de_corte():
    pc = _mod()
    f, pedido, malhas, ev = _montar_cena_numpy(
        [
            (10, "G_PAREDE", "IfcWall", _caixa_np(0.0, 0.0, 0.0, 4.0, 0.2, 2.8)),
            (11, "G_LAJE", "IfcSlab", _caixa_np(0.0, 0.0, -0.2, 4.0, 3.0, 0.0)),
            (12, "G_MOVEL", "IfcFurnishingElement", _caixa_np(1.0, 1.0, 0.0, 2.0, 1.8, 0.7)),
            (13, "G_VIGA_ACIMA", "IfcBeam", _caixa_np(5.0, 5.0, 2.2, 7.0, 5.4, 2.8)),
        ],
        altura_corte_m=1.2,
    )
    resp, motivo = pc.desenhar_planta_cache(f, pedido, malhas, ev, abrir_s=0.01, cache_s=0.02)
    assert motivo is None and isinstance(resp, dict) and resp["ok"] is True

    parsed = _parse_svg(resp["svg"])
    assert set(parsed.cut_by_guid.keys()) == {"G_PAREDE"}
    assert "G_LAJE" not in parsed.cut_by_guid and "G_MOVEL" not in parsed.cut_by_guid
    assert "G_VIGA_ACIMA" not in resp["svg"]
    assert {10, 11, 12}.issubset(set(resp["enviados"]))
    assert resp["falhas_geometria"] == []

    # Nenhum segmento da viga acima (em x in [5, 7], y in [5, 5.4]) pode aparecer na projecao
    segs_proj = _polilinhas_para_segs(_polilinhas_de_elementos(parsed.proj_groups))
    assert len(segs_proj) > 0
    assert float(_dist_pontos_a_segs(np.array([[6.0, 5.2], [5.0, 5.0]]), segs_proj).min()) > 0.5


def test_secao_usa_corte_plano_e_aneis(monkeypatch):
    pc = _mod()
    corte_calls, aneis_calls = [], []
    real_corte = corte_plano.cortar_malha_no_plano
    real_aneis = aneis.aneis_de_segmentos

    def espia_corte(v, t, z):
        corte_calls.append(float(z))
        return real_corte(v, t, z)

    def espia_aneis(segs, *a, **k):
        aneis_calls.append(len(segs))
        return real_aneis(segs, *a, **k)

    monkeypatch.setattr(corte_plano, "cortar_malha_no_plano", espia_corte)
    monkeypatch.setattr(aneis, "aneis_de_segmentos", espia_aneis)

    f, pedido, malhas, ev = _montar_cena_numpy(
        [
            (10, "G_PAREDE", "IfcWall", _caixa_np(1.0, 2.0, 0.0, 5.0, 2.3, 2.8)),
            (11, "G_LAJE", "IfcSlab", _caixa_np(0.0, 0.0, -0.2, 6.0, 4.0, 0.0)),
            (12, "G_ACIMA", "IfcBeam", _caixa_np(0.0, 0.0, 2.0, 2.0, 0.3, 2.5)),
        ],
        altura_corte_m=1.2,
    )
    resp, motivo = pc.desenhar_planta_cache(f, pedido, malhas, ev)
    assert motivo is None and resp["ok"] is True
    assert corte_calls == [pytest.approx(1.2)]
    assert len(aneis_calls) == 1 and aneis_calls[0] >= 4

    parsed = _parse_svg(resp["svg"])
    pls_corte = _polilinhas_de_elementos(parsed.cut_by_guid["G_PAREDE"])
    assert len(pls_corte) == 1
    assert np.allclose(pls_corte[0][0], pls_corte[0][-1], atol=1e-6)
    assert _contagem_segmentos_corte(pls_corte) == 4
    xs, ys = pls_corte[0][:, 0], pls_corte[0][:, 1]
    assert (xs.min(), xs.max(), ys.min(), ys.max()) == pytest.approx((1.0, 5.0, 2.0, 2.3), abs=1e-5)


def test_uma_unica_chamada_linhas_visiveis_multi_com_angulo_0001(monkeypatch):
    pc = _mod()
    multi_calls, single_calls = [], []
    real_multi = visibilidade.linhas_visiveis_multi

    def espia_multi(pecas, *args, **kwargs):
        multi_calls.append((len(list(pecas)), args, dict(kwargs)))
        return real_multi(pecas, *args, **kwargs)

    def proibe_single(*args, **kwargs):
        single_calls.append((args, kwargs))
        raise AssertionError("nao deve chamar linhas_visiveis peca a peca")

    monkeypatch.setattr(visibilidade, "linhas_visiveis_multi", espia_multi)
    monkeypatch.setattr(visibilidade, "linhas_visiveis", proibe_single)

    f, pedido, malhas, ev = _montar_cena_numpy(
        [
            (10, "G_P1", "IfcWall", _caixa_np(0.0, 0.0, 0.0, 4.0, 0.2, 2.8)),
            (11, "G_P2", "IfcWall", _caixa_np(0.0, 3.0, 0.0, 4.0, 3.2, 2.8)),
            (12, "G_LAJE", "IfcSlab", _caixa_np(0.0, 0.0, -0.2, 4.0, 3.2, 0.0)),
            (13, "G_MOVEL", "IfcFurnishingElement", _caixa_np(1.0, 1.0, 0.0, 2.0, 2.0, 0.8)),
        ],
        altura_corte_m=1.2,
    )
    resp, motivo = pc.desenhar_planta_cache(f, pedido, malhas, ev)
    assert motivo is None and resp["ok"] is True
    assert single_calls == []
    assert len(multi_calls) == 1
    n_malhas, _args, kwargs = multi_calls[0]
    assert n_malhas == 4  # 2 metades inferiores das paredes + laje + movel
    assert kwargs.get("angulo_graus", 0.001) == pytest.approx(0.001)


def test_svg_comandos_ml_sem_z_projecao_e_estilo():
    pc = _mod()
    f, pedido, malhas, ev = _montar_cena_numpy(
        [
            (10, "G_PAREDE", "IfcWall", _caixa_np(0.0, 1.0, 0.0, 4.0, 1.2, 2.8)),
            (11, "G_LAJE", "IfcSlab", _caixa_np(0.0, 0.0, -0.2, 4.0, 3.0, 0.0)),
        ],
        altura_corte_m=1.2,
        pav_guid="PAV_TERREO",
    )
    resp, motivo = pc.desenhar_planta_cache(f, pedido, malhas, ev)
    assert motivo is None and resp["ok"] is True
    svg = resp["svg"]

    assert "-0.000000" not in svg
    parsed = _parse_svg(svg)
    assert len(parsed.storeys) == 1
    assert parsed.storeys[0].get(f"{NS_IFC}guid") == "PAV_TERREO"
    assert len(parsed.proj_groups) == 1
    proj_g = parsed.proj_groups[0]
    assert proj_g.get(f"{NS_IFC}guid") is None
    assert all(sub.get(f"{NS_IFC}guid") is None for sub in proj_g.iter() if sub.tag.rsplit("}", 1)[-1] == "g")

    assert len(parsed.all_paths) == resp["n_paths"] and resp["n_paths"] >= 2
    for path_el in parsed.all_paths:
        d = (path_el.get("d") or "").strip()
        cmds, runs = _extrair_polilinhas_d(d)
        assert cmds and set(cmds).issubset({"M", "L"}), f"comandos proibidos em d={d!r}"
        assert "Z" not in cmds and "z" not in cmds
        assert len(runs) >= 1

    # Compatibilidade estrita com estilo.aplicar_estilo
    estilizado = estilo.aplicar_estilo(svg, "1:50")
    p_est = _parse_svg(estilizado)
    assert "cut" in (p_est.cut_by_guid["G_PAREDE"][0].get("class") or "").split()
    assert "IfcWall" in (p_est.cut_by_guid["G_PAREDE"][0].get("class") or "").split()
    assert "cut" not in (p_est.proj_groups[0].get("class") or "").split()


def test_tampa_opcao1_recorta_projecao_fora_dos_aneis_sobreposicao_e_furo(monkeypatch):
    pc = _mod()
    recorte_calls = []
    real_recorte = recorte.recortar_fora_dos_aneis

    def espia_recorte(polilinhas, aneis_arg, *a, **k):
        recorte_calls.append((len(list(polilinhas)), k.get("encolher", 5e-4)))
        return real_recorte(polilinhas, aneis_arg, *a, **k)

    monkeypatch.setattr(recorte, "recortar_fora_dos_aneis", espia_recorte)

    # 1) Duas paredes cortadas sobrepostas no canto [1.6..2.0, 0.0..0.4] + barra abaixo passando pelo canto
    f, pedido, malhas, ev = _montar_cena_numpy(
        [
            (10, "G_PAR_A", "IfcWall", _caixa_np(0.0, 0.0, 0.0, 2.0, 0.4, 2.8)),
            (11, "G_PAR_B", "IfcWall", _caixa_np(1.6, 0.0, 0.0, 2.0, 2.0, 2.8)),
            (12, "G_BARRA", "IfcSlab", _caixa_np(1.75, -0.6, 0.0, 1.85, 1.0, 0.2)),
        ],
        altura_corte_m=1.2,
    )
    resp, motivo = pc.desenhar_planta_cache(f, pedido, malhas, ev)
    assert motivo is None and resp["ok"] is True
    assert len(recorte_calls) >= 1
    parsed = _parse_svg(resp["svg"])
    segs_proj = _polilinhas_para_segs(_polilinhas_de_elementos(parsed.proj_groups))
    # Trecho externo da barra (y=-0.3) visivel; interior da sobreposicao (x=1.8, y=0.2) sem vazamento
    assert float(_dist_pontos_a_segs(np.array([[1.75, -0.3], [1.85, -0.3]]), segs_proj).max()) <= 1e-3
    assert float(_dist_pontos_a_segs(np.array([[1.75, 0.2], [1.85, 0.2], [1.8, 0.2]]), segs_proj).min()) > 5e-3

    # 2) Moldura com furo cortada + bloco abaixo exatamente dentro do furo -> bloco permanece visivel
    ext = [(0.0, 0.0), (2.0, 0.0), (2.0, 2.0), (0.0, 2.0)]
    furo = [(0.5, 0.5), (1.5, 0.5), (1.5, 1.5), (0.5, 1.5)]
    f2, ped2, mal2, ev2 = _montar_cena_numpy(
        [
            (20, "G_MOLDURA", "IfcWall", _tubo_np(ext, furo, 0.0, 2.8)),
            (21, "G_BLOCO_FURO", "IfcFurnishingElement", _caixa_np(0.8, 0.8, 0.0, 1.2, 1.2, 0.5)),
        ],
        altura_corte_m=1.2,
    )
    resp2, motivo2 = pc.desenhar_planta_cache(f2, ped2, mal2, ev2)
    assert motivo2 is None and resp2["ok"] is True
    p2 = _parse_svg(resp2["svg"])
    pls_mold = _polilinhas_de_elementos(p2.cut_by_guid["G_MOLDURA"])
    assert len(pls_mold) == 2  # anel externo + furo
    segs_proj2 = _polilinhas_para_segs(_polilinhas_de_elementos(p2.proj_groups))
    pts_bloco = np.array([[0.8, 1.0], [1.2, 1.0], [1.0, 0.8], [1.0, 1.2]], dtype=np.float64)
    assert float(_dist_pontos_a_segs(pts_bloco, segs_proj2).max()) <= 1e-3


def test_determinismo_rodadas_ordem_e_threads():
    pc = _mod()
    pecas = [
        (10, "G_03", "IfcWall", _caixa_np(0.0, 0.0, 0.0, 4.0, 0.2, 2.8)),
        (11, "G_01", "IfcSlab", _caixa_np(0.0, 0.0, -0.2, 4.0, 3.0, 0.0)),
        (12, "G_04", "IfcFurnishingElement", _caixa_np(0.5, 0.8, 0.0, 1.5, 1.6, 0.7)),
        (13, "G_02", "IfcWall", _caixa_np(3.8, 0.0, 0.0, 4.0, 3.0, 2.8)),
    ]
    f1, p1, m1, e1 = _montar_cena_numpy(pecas, threads=1)
    r1, mot1 = pc.desenhar_planta_cache(f1, p1, m1, e1)
    r2, mot2 = pc.desenhar_planta_cache(f1, p1, m1, e1)
    r3, mot3 = pc.desenhar_planta_cache(f1, p1, m1, e1)
    assert mot1 is None and mot2 is None and mot3 is None
    assert r1["svg"] == r2["svg"] == r3["svg"]

    # Ordem embaralhada de entrada -> SVG identico byte a byte
    f_emb, p_emb, m_emb, e_emb = _montar_cena_numpy(list(reversed(pecas)), threads=1)
    r_emb, mot_emb = pc.desenhar_planta_cache(f_emb, p_emb, m_emb, e_emb)
    assert mot_emb is None and r_emb["svg"] == r1["svg"]

    # threads=4 vs threads=1 -> SVG identico byte a byte
    f_t4, p_t4, m_t4, e_t4 = _montar_cena_numpy(pecas, threads=4)
    r_t4, mot_t4 = pc.desenhar_planta_cache(f_t4, p_t4, m_t4, e_t4)
    assert mot_t4 is None and r_t4["svg"] == r1["svg"]


# ---------- testes mutantes (1 comportamento errado por teste, ESPEC §3.2) ----------
@pytest.mark.parametrize(
    "malha_ruim",
    [
        (np.zeros((0, 3), dtype=np.float64), np.zeros((0, 3), dtype=np.int32)),
        (np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]), np.zeros((0, 3), dtype=np.int32)),
        (np.array([[0.0, np.nan, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 2.0]]), np.array([[0, 1, 2]], dtype=np.int32)),
        (np.array([[0.0, np.inf, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 2.0]]), np.array([[0, 1, 2]], dtype=np.int32)),
        (np.array([[2e12, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 2.0]]), np.array([[0, 1, 2]], dtype=np.int32)),
        (np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 2.0]]), np.array([[0, 1, 5]], dtype=np.int32)),
        (np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 2.0]]), np.array([[-1, 1, 2]], dtype=np.int32)),
        (np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 2.0]]), np.array([[0.0, 1.0, 2.0]], dtype=np.float64)),
        (np.zeros((4, 2), dtype=np.float64), np.array([[0, 1, 2]], dtype=np.int32)),
    ],
)
def test_mutante_01_omissao_silenciosa_malha_invalida(malha_ruim):
    """Mutante 1: pular peca com malha invalida em vez de cair o pavimento inteiro com `malha_invalida`."""
    pc = _mod()
    f, pedido, malhas, ev = _montar_cena_numpy(
        [
            (10, "G_BOA", "IfcWall", _caixa_np(0.0, 0.0, 0.0, 3.0, 0.2, 2.8)),
            (11, "G_RUIM", "IfcSlab", malha_ruim),
        ],
        altura_corte_m=1.2,
    )
    resp, motivo = pc.desenhar_planta_cache(f, pedido, malhas, ev)
    assert resp is None and motivo == "malha_invalida"


def test_mutante_01b_gid_ausente_em_malhas_mundo_cai_malha_invalida():
    """Mutante 1b: pular peca de `elementos_validos` ausente em `malhas_mundo`."""
    pc = _mod()
    f, pedido, malhas, ev = _montar_cena_numpy(
        [
            (10, "G_BOA", "IfcWall", _caixa_np(0.0, 0.0, 0.0, 3.0, 0.2, 2.8)),
            (11, "G_FALTA", "IfcSlab", _caixa_np(0.0, 0.0, -0.2, 3.0, 2.0, 0.0)),
        ],
        altura_corte_m=1.2,
    )
    del malhas["G_FALTA"]
    resp, motivo = pc.desenhar_planta_cache(f, pedido, malhas, ev)
    assert resp is None and motivo == "malha_invalida"


def test_mutante_02_secao_aberta_ignora_ou_pula_peca():
    """Mutante 2: desenhar ou pular peca em vez de cair com `secao_aberta` nos casos acima do limite T24f."""
    pc = _mod()
    v_boa, t_boa = _caixa_np(5.0, 0.0, 0.0, 8.0, 0.2, 2.8)

    # Caso A (ajustado T24f): 2 pecas abertas em 3 cortadas (> ceil(0.25*3)=1) -> cai secao_aberta
    v_ab1, t_ab1 = _caixa_np(0.0, 0.0, 0.0, 2.0, 0.3, 2.8)
    v_ab2, t_ab2 = _caixa_np(0.0, 2.0, 0.0, 2.0, 2.3, 2.8)
    f1, p1, m1, e1 = _montar_cena_numpy(
        [
            (10, "G_BOA", "IfcWall", (v_boa, t_boa)),
            (11, "G_ABERTA_1", "IfcWall", (v_ab1, t_ab1[:-2])),
            (12, "G_ABERTA_2", "IfcWall", (v_ab2, t_ab2[:-2])),
        ],
        altura_corte_m=1.2,
    )
    r1, mot1 = pc.desenhar_planta_cache(f1, p1, m1, e1)
    assert r1 is None and mot1 == "secao_aberta"

    # Caso B (ajustado T24f): malha com vertices ocupando z=1.2 e todos os 4 deltas (+-1e-5, +-3.7e-5) -> cai secao_aberta
    zs_bloq = [0.0, 1.2 - 3.7e-5, 1.2 - 1e-5, 1.2, 1.2 + 1e-5, 1.2 + 3.7e-5, 2.8]
    v_imp = np.array(
        [[x, y, z] for z in zs_bloq for x, y in ((0.0, 0.0), (1.0, 0.0), (1.0, 0.4), (0.0, 0.4))],
        dtype=np.float64,
    )
    t_imp = [[0, 2, 1], [0, 3, 2]]
    for k in range(len(zs_bloq) - 1):
        b, top_k = 4 * k, 4 * (k + 1)
        for i in range(4):
            j = (i + 1) % 4
            t_imp.extend([[b + i, b + j, top_k + j], [b + i, top_k + j, top_k + i]])
    top_f = 4 * (len(zs_bloq) - 1)
    t_imp.extend([[top_f, top_f + 1, top_f + 2], [top_f, top_f + 2, top_f + 3]])
    f2, p2, m2, e2 = _montar_cena_numpy(
        [(10, "G_BOA", "IfcWall", (v_boa, t_boa)), (12, "G_DEGRAU_IMP", "IfcWall", (v_imp, np.asarray(t_imp, dtype=np.int32)))],
        altura_corte_m=1.2,
    )
    r2, mot2 = pc.desenhar_planta_cache(f2, p2, m2, e2)
    assert r2 is None and mot2 == "secao_aberta"


def test_mutante_03_falta_oclusao_mutua_entre_pecas():
    """Mutante 3: chamar linhas_visiveis por peca sem oclusao mutua deixaria bloco escondido vazar."""
    pc = _mod()
    f, pedido, malhas, ev = _montar_cena_numpy(
        [
            (10, "G_TAMPO", "IfcSlab", _caixa_np(0.0, 0.0, 0.6, 3.0, 3.0, 0.8)),
            (11, "G_OCULTO", "IfcFurnishingElement", _caixa_np(1.0, 1.0, 0.0, 2.0, 2.0, 0.4)),
        ],
        altura_corte_m=1.2,
    )
    resp, motivo = pc.desenhar_planta_cache(f, pedido, malhas, ev)
    assert motivo is None and resp["ok"] is True

    parsed = _parse_svg(resp["svg"])
    segs_proj = _polilinhas_para_segs(_polilinhas_de_elementos(parsed.proj_groups))
    assert len(segs_proj) >= 4
    # Arestas do bloco oculto (x=1..2, y=1..2) estao 100% sob o tampo (0..3, 0..3): 0 linhas perto
    pts_ocultos = np.array([[1.0, 1.5], [2.0, 1.5], [1.5, 1.0], [1.5, 2.0]], dtype=np.float64)
    assert float(_dist_pontos_a_segs(pts_ocultos, segs_proj).min()) > 0.2
    # Borda do tampo (0..3, 0..3) visivel
    pts_tampo = np.array([[0.0, 1.5], [3.0, 1.5], [1.5, 0.0], [1.5, 3.0]], dtype=np.float64)
    assert float(_dist_pontos_a_segs(pts_tampo, segs_proj).max()) <= 1e-3


def test_mutante_04_falta_tampa_vazamento_dentro_da_secao_cortada():
    """Mutante 4: sem recorte 2D pelos aneis da secao, aresta de piso abaixo atravessa a parede cortada."""
    pc = _mod()
    f, pedido, malhas, ev = _montar_cena_numpy(
        [
            (10, "G_PAREDE", "IfcWall", _caixa_np(0.0, 1.0, 0.0, 4.0, 1.4, 2.8)),
            (11, "G_BARRA_PISO", "IfcSlab", _caixa_np(1.5, 0.0, 0.0, 2.5, 2.4, 0.2)),
        ],
        altura_corte_m=1.2,
    )
    resp, motivo = pc.desenhar_planta_cache(f, pedido, malhas, ev)
    assert motivo is None and resp["ok"] is True

    parsed = _parse_svg(resp["svg"])
    segs_proj = _polilinhas_para_segs(_polilinhas_de_elementos(parsed.proj_groups))
    # Interior da secao da parede (y=1.2, 20 cm longe das bordas y=1.0 e y=1.4): ZERO segmentos de projecao
    pts_dentro = np.array([[1.5, 1.2], [2.5, 1.2], [2.0, 1.2]], dtype=np.float64)
    assert float(_dist_pontos_a_segs(pts_dentro, segs_proj).min()) > 0.05
    # Trechos da barra fora da parede (y=0.5 e y=1.9) permanecem visiveis
    pts_fora = np.array([[1.5, 0.5], [2.5, 0.5], [1.5, 1.9], [2.5, 1.9]], dtype=np.float64)
    assert float(_dist_pontos_a_segs(pts_fora, segs_proj).max()) <= 1e-3


def test_mutante_05_angulo_dobra_diferente_de_0001():
    """Mutante 5: usar filtro de dobra estilo Revit (ex. 15/30 graus) apagaria cumeeira de 2 graus."""
    pc = _mod()
    f, pedido, malhas, ev = _montar_cena_numpy(
        [(10, "G_TELHADO", "IfcRoof", _telhado_dobra_np(0.0, 0.0, 2.0, 1.0, 0.0, 0.5, angulo_diedro_graus=2.0))],
        altura_corte_m=1.2,
    )
    resp, motivo = pc.desenhar_planta_cache(f, pedido, malhas, ev)
    assert motivo is None and resp["ok"] is True

    parsed = _parse_svg(resp["svg"])
    segs_proj = _polilinhas_para_segs(_polilinhas_de_elementos(parsed.proj_groups))
    # Cumeeira central em x=1.0, y in [0.1..0.9] deve estar presente
    pts_cumeeira = np.column_stack([np.full(9, 1.0), np.linspace(0.1, 0.9, 9)])
    assert float(_dist_pontos_a_segs(pts_cumeeira, segs_proj).max()) <= 1e-3


def test_mutante_06_y_nao_invertido_ou_projecao_como_cut():
    """Mutante 6: nao inverter Y ou colocar projecao em `<g ifc:guid>` quebra estilo/coordenadas."""
    pc = _mod()
    # Coordenadas assimetricas em Y (+3.0 .. +4.0) para provar que SVG tem Y negativo (-4.0 .. -3.0)
    f, pedido, malhas, ev = _montar_cena_numpy(
        [
            (10, "G_PAREDE", "IfcWall", _caixa_np(1.0, 3.0, 0.0, 2.0, 3.5, 2.8)),
            (11, "G_LAJE", "IfcSlab", _caixa_np(1.0, 3.0, -0.2, 2.0, 4.0, 0.0)),
        ],
        altura_corte_m=1.2,
    )
    resp, motivo = pc.desenhar_planta_cache(f, pedido, malhas, ev)
    assert motivo is None and resp["ok"] is True

    parsed = _parse_svg(resp["svg"])
    ys_svg = []
    for p in parsed.all_paths:
        cmds, runs = _extrair_polilinhas_d(p.get("d") or "")
        assert "Z" not in cmds and "z" not in cmds
        for r in runs:
            ys_svg.extend(r[:, 1].tolist())
    assert ys_svg and max(ys_svg) <= -2.999 and min(ys_svg) >= -4.001

    estilizado = estilo.aplicar_estilo(resp["svg"], "1:50")
    assert 'class="IfcWall cut"' in estilizado
    assert 'class="projection"' in estilizado and 'class="projection cut"' not in estilizado


def test_mutante_07_nao_mutacao_entradas():
    """Mutante 7: mutar `verts`, `tris` ou `pedido` do chamador durante o desenho."""
    pc = _mod()
    f, pedido, malhas, ev = _montar_cena_numpy(
        [
            (10, "G_PAREDE", "IfcWall", _caixa_np(0.0, 0.0, 0.0, 3.0, 0.2, 2.8)),
            (11, "G_LAJE", "IfcSlab", _caixa_np(0.0, 0.0, -0.2, 3.0, 2.0, 0.0)),
        ],
        altura_corte_m=1.2,
    )
    copia_malhas = {g: (v.copy(), t.copy()) for g, (v, t) in malhas.items()}
    copia_pedido = {k: (dict(v) if isinstance(v, dict) else list(v) if isinstance(v, list) else v) for k, v in pedido.items()}

    resp, motivo = pc.desenhar_planta_cache(f, pedido, malhas, ev)
    assert motivo is None and resp["ok"] is True
    for g, (v0, t0) in copia_malhas.items():
        np.testing.assert_array_equal(malhas[g][0], v0)
        np.testing.assert_array_equal(malhas[g][1], t0)
    assert pedido == copia_pedido


def test_mutante_08_peca_acima_do_corte_nao_desenhada_nem_falha():
    """Mutante 8: desenhar peca acima do corte ou registra-la em `falhas_geometria`."""
    pc = _mod()
    f, pedido, malhas, ev = _montar_cena_numpy(
        [(10, "G_VIGA_ALTA", "IfcBeam", _caixa_np(0.0, 0.0, 2.4, 4.0, 0.3, 2.8))],
        altura_corte_m=1.2,
    )
    resp, motivo = pc.desenhar_planta_cache(f, pedido, malhas, ev)
    assert motivo is None and resp["ok"] is True
    assert resp["n_paths"] == 0
    assert resp["falhas_geometria"] == []
    assert "G_VIGA_ALTA" not in resp["svg"]
    parsed = _parse_svg(resp["svg"])
    assert len(parsed.all_paths) == 0


@pytest.mark.parametrize("offset", [(0.0, 0.0), (500_000.25, 7_500_000.75)])
def test_mutante_09_equivalencia_motor_casos_simples_e_georreferenciado(tmp_path, offset):
    """Mutante 9: divergencia geometrica (escala/matriz/eixo/float64) contra o motor nos casos simples."""
    _mod()
    cena = _criar_cena_ifc_sintetica(tmp_path, offset=offset)

    resp_motor = desenho.processar(cena.pedido_base)
    resp_cache = desenho.processar(cena.pedido_cache)

    assert resp_motor["ok"] is True
    assert resp_cache["ok"] is True
    assert resp_cache["via_cache"] is True
    assert resp_cache["queda"] is None
    assert resp_cache["n_faltantes"] == 0

    p_ref = _parse_svg(resp_motor["svg"])
    p_new = _parse_svg(resp_cache["svg"])

    # Mesmos ifc:guid de secao cortada e mesma contagem canonica de segmentos de corte
    assert set(p_new.cut_by_guid.keys()) == set(p_ref.cut_by_guid.keys()) == {cena.parede.GlobalId}
    pls_corte_ref = _polilinhas_de_elementos(p_ref.cut_by_guid[cena.parede.GlobalId])
    pls_corte_new = _polilinhas_de_elementos(p_new.cut_by_guid[cena.parede.GlobalId])
    assert _contagem_segmentos_corte(pls_corte_new) == _contagem_segmentos_corte(pls_corte_ref) == 4

    # Cobertura bidirecional >= 99.5% na secao e >= 98.0% no conjunto (5 mm reais)
    segs_corte_ref = _polilinhas_para_segs(pls_corte_ref)
    segs_corte_new = _polilinhas_para_segs(pls_corte_new)
    rec_c, pre_c = _cobertura_bidirecional(segs_corte_ref, segs_corte_new, tol=5e-3)
    assert rec_c >= 0.995 and pre_c >= 0.995, f"secao recall={rec_c:.4f} precisao={pre_c:.4f}"

    segs_all_ref = _polilinhas_para_segs(pls_corte_ref + _polilinhas_de_elementos(p_ref.proj_groups))
    segs_all_new = _polilinhas_para_segs(pls_corte_new + _polilinhas_de_elementos(p_new.proj_groups))
    rec_g, pre_g = _cobertura_bidirecional(segs_all_ref, segs_all_new, tol=5e-3)
    assert rec_g >= 0.98 and pre_g >= 0.98, f"geral recall={rec_g:.4f} precisao={pre_g:.4f}"

    # Ambos os SVGs validos no estilo
    estilo.aplicar_estilo(resp_cache["svg"], "1:50")


def test_mutante_10_pesados_caixas_vazios_e_tempos():
    """Mutante 10: preencher `pesados`/`caixas`/`faltantes` ou omitir tempos obrigatorios."""
    pc = _mod()
    f, pedido, malhas, ev = _montar_cena_numpy(
        [
            (10, "G_PAREDE", "IfcWall", _caixa_np(0.0, 0.0, 0.0, 4.0, 0.2, 2.8)),
            (11, "G_LAJE", "IfcSlab", _caixa_np(0.0, 0.0, -0.2, 4.0, 3.0, 0.0)),
        ],
        altura_corte_m=1.2,
    )
    resp, motivo = pc.desenhar_planta_cache(f, pedido, malhas, ev, abrir_s=0.05, cache_s=0.03)
    assert motivo is None and resp["ok"] is True
    assert resp["pesados"] == []
    assert resp["caixas"] == []
    assert resp["em_cache"] == []
    assert resp["falhas_geometria"] == []
    assert "faltantes" not in resp and "incompleta" not in resp

    t = resp["tempos"]
    assert t["abrir_s"] == pytest.approx(0.05)
    assert t["cache_s"] == pytest.approx(0.03)
    assert t["geo_s"] == 0.0 and t["write_s"] == 0.0 and t["finalize_s"] == 0.0
    assert isinstance(t["corte_s"], float) and t["corte_s"] >= 0.0
    assert isinstance(t["motor_s"], float) and t["motor_s"] >= 0.0


def test_erro_inesperado_no_motor_retorna_erro_motor(monkeypatch):
    pc = _mod()
    monkeypatch.setattr(
        visibilidade,
        "linhas_visiveis_multi",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("falha simulada")),
    )
    f, pedido, malhas, ev = _montar_cena_numpy(
        [(10, "G_LAJE", "IfcSlab", _caixa_np(0.0, 0.0, -0.2, 4.0, 3.0, 0.0))],
        altura_corte_m=1.2,
    )
    resp, motivo = pc.desenhar_planta_cache(f, pedido, malhas, ev)
    assert resp is None and motivo == "erro_motor"


# ---------- integracao com desenho._desenhar_planta_cache e telemetria via_cache ----------
def test_integracao_gancho_desenho_e_telemetria_via_cache(tmp_path):
    _mod()
    cena = _criar_cena_ifc_sintetica(tmp_path)

    # 1) Chamada direta ao gancho desenho._desenhar_planta_cache (nao pode ser stub erro_motor)
    f_np, ped_np, mal_np, ev_np = _montar_cena_numpy(
        [
            (10, "G_PAREDE", "IfcWall", _caixa_np(0.0, 0.0, 0.0, 4.0, 0.2, 2.8)),
            (11, "G_LAJE", "IfcSlab", _caixa_np(0.0, 0.0, -0.2, 4.0, 3.0, 0.0)),
        ],
        altura_corte_m=1.2,
    )
    r_gancho, mot_gancho = desenho._desenhar_planta_cache(f_np, ped_np, mal_np, ev_np, None, 0.01)
    assert mot_gancho is None and isinstance(r_gancho, dict) and r_gancho["ok"] is True

    # 2) Fluxo completo desenho.processar com cache real -> via_cache=True e telemetria
    resp = desenho.processar(cena.pedido_cache)
    assert resp["ok"] is True
    assert resp["via_cache"] is True
    assert resp["queda"] is None
    assert resp["n_faltantes"] == 0
    assert resp["pesados"] == [] and resp["caixas"] == [] and resp["falhas_geometria"] == []
    assert "faltantes" not in resp and "incompleta" not in resp
    t = resp["tempos"]
    assert isinstance(t["cache_s"], float) and t["cache_s"] >= 0.0
    assert isinstance(t["corte_s"], float) and t["corte_s"] >= 0.0
    assert isinstance(t["motor_s"], float) and t["motor_s"] >= 0.0
    assert t["geo_s"] == 0.0 and t["write_s"] == 0.0 and t["finalize_s"] == 0.0


def test_integracao_desenho_quedas_secao_aberta_e_malha_invalida(tmp_path, monkeypatch):
    _mod()
    cena = _criar_cena_ifc_sintetica(tmp_path)
    base = desenho.processar(cena.pedido_base)
    assert base["ok"] is True

    real_ler = desenho.cache_leitura.malhas_do_cache

    # 1) Injeta malha cortada sem nenhum segmento de corte (T24f: 1/1 aberta seria parcial aceita) -> cai secao_aberta
    def ler_secao_aberta(cache, doc, ids):
        malhas, falt = real_ler(cache, doc, ids)
        v_sem_seg = np.array(
            [[0.0, 0.0, 0.0], [4.0, 0.0, 0.0], [4.0, 0.2, 0.0], [0.0, 0.0, 2.8], [4.0, 0.0, 2.8], [4.0, 0.2, 2.8]],
            dtype=np.float64,
        )
        t_sem_seg = np.array([[0, 1, 2], [3, 4, 5]], dtype=np.int32)
        malhas[cena.parede.GlobalId] = (v_sem_seg, t_sem_seg)
        return malhas, falt

    monkeypatch.setattr(desenho.cache_leitura, "malhas_do_cache", ler_secao_aberta)
    r_ab = desenho.processar(cena.pedido_cache)
    assert r_ab["ok"] is True
    assert r_ab["via_cache"] is False
    assert r_ab["queda"] == "secao_aberta"
    assert r_ab["n_faltantes"] == 0
    assert r_ab["svg"] == base["svg"]

    # 2) Injeta malha invalida (NaN) na laje -> cai pavimento inteiro com queda="malha_invalida"
    def ler_malha_invalida(cache, doc, ids):
        malhas, falt = real_ler(cache, doc, ids)
        v_ru, t_ru = malhas[cena.laje.GlobalId]
        v_nan = v_ru.copy()
        v_nan[0, 0] = np.nan
        malhas[cena.laje.GlobalId] = (v_nan, t_ru)
        return malhas, falt

    monkeypatch.setattr(desenho.cache_leitura, "malhas_do_cache", ler_malha_invalida)
    r_inv = desenho.processar(cena.pedido_cache)
    assert r_inv["ok"] is True
    assert r_inv["via_cache"] is False
    assert r_inv["queda"] == "malha_invalida"
    assert r_inv["n_faltantes"] == 0
    assert r_inv["svg"] == base["svg"]
