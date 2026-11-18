# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oraculo F0-S06-T20d1: previa provisoria da planta, sem HLR (T3). Modulo novo `geometria/obim_geometria/previa_planta.py`. Nao editar nesta tarefa.

ASSINATURA (a definir aqui; o implementador segue):
    gerar_previa_planta(pecas, z_corte, destino=None, *, moveis_como_caixa=False, ao_fase=None, limiar_tris=2000) -> dict
  pecas: lista de dict {"guid": str, "classe": str ("IfcWall"...), "verts": (N,3) float | None, "tris": (M,3) int | None,
         "movel": bool (opcional, False; quem chama decide pela classe), "caixa": (x0, y0, x1, y1) mundo (opcional; usada na falha)}.
         Malha em coordenadas do mundo, soldada (indices compartilhados), como `silhueta.formas_do_mundo`.
  destino: caminho do SVG (escrita atomica: `destino + ".tmp"` completo e depois `os.replace`); None = nao grava.
  ao_fase: callable; chamado UMA vez, como `ao_fase("previa")`, tambem sem destino.
  Devolve {"svg": str, "auditoria": {"cortada": set[str], "vista": set[str], "acima": set[str], "falha": set[str]}} (conjuntos de GUID).

CONTRATO (z = z_corte; zmin/zmax da malha):
 1. CORTADA (zmin <= z < zmax): secao exata (`cortar_malha_no_plano` + `aneis_de_segmentos`); UM `<path fill-rule="evenodd">` por peca com externos e furos juntos,
    dentro de `<g class="{classe} cut" ifc:guid="{guid}">`.
 2. VISTA (zmax <= z): `movel` e moveis_como_caixa => caixa XY; senao malha com <= limiar_tris triangulos => `silhueta.silhueta_xy`; senao casco convexo 2D.
    `<g class="{classe} projection" ifc:guid=...>`; NUNCA `cut` (senao o estilo pinta de preto).
 3. ACIMA (zmin > z): fora do SVG, mas na auditoria.
 4. FALHA: malha ausente/None, ou degenerada (area XY nula, silhueta vazia): caixa provisoria (`caixa` da peca) como `projection`; GUID em "falha", nao em "vista".
 5. Auditoria: cortada | vista | acima | falha == conjunto pedido (zero omissao silenciosa); conjuntos disjuntos; cada GUID desenhado aparece UMA vez no SVG, na ordem de `pecas`.
 6. Vertice exatamente em z: nao abre anel. Uso de jitter para CIMA (z + 1e-7 m): assim tambem a peca com zmin == z (cortada) tem secao.
 7. Escrita atomica e `ao_fase("previa")` uma vez. O SVG tem `xmlns:ifc` na raiz.
MUTANTES MENTAIS que os testes matam: (a) peca abaixo do corte marcada `cut`; (b) peca omitida (da auditoria ou do SVG); (c) furo preenchido (anel em `<path>`
separado ou so externos); (d) casco convexo usado em peca pequena (laje em L: area 3,0 vira 3,5); (e) silhueta em peca grande; (f) acima desenhada;
(g) vertice no plano abre anel / jitter para baixo; (h) escrita direta sem .tmp; (i) fase chamada 0 ou 2 vezes.
Areas conferidas rasterizando EVENODD por `<path>` (como o estilo `.cut path` e tests/test_s06_t19j4c_secao_fechada_oraculo.py)."""
from __future__ import annotations

import os
import re

import numpy as np
import pytest

try:
    from obim_geometria.previa_planta import gerar_previa_planta
except ImportError as e:  # noqa: F841
    raise ImportError(f"previa_planta inexistente: criar geometria/obim_geometria/previa_planta.py com gerar_previa_planta (T20d1): {e}") from e

Z = 1.2


# ---------- malhas sinteticas (soldadas) ----------
def prisma(poly, z0, z1, caps, dx=0.0, dy=0.0):
    n = len(poly)
    v = [(x + dx, y + dy, z0) for x, y in poly] + [(x + dx, y + dy, z1) for x, y in poly]
    t = [(i, k, j) for i, j, k in caps] + [(n + i, n + j, n + k) for i, j, k in caps]
    for i in range(n):
        a, b = i, (i + 1) % n
        t += [(a, b, n + b), (a, n + b, n + a)]
    return np.array(v, float), np.array(t, int)


QUAD = [(0, 1, 2), (0, 2, 3)]
L_POLI = [(0, 0), (2, 0), (2, 1), (1, 1), (1, 2), (0, 2)]
L_CAPS = [(0, 1, 2), (0, 2, 3), (0, 3, 4), (0, 4, 5)]  # area 3,0; casco convexo 3,5


def caixa(x0, y0, z0, x1, y1, z1):
    return prisma([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], z0, z1, QUAD)


def moldura(x0, y0, x1, y1, h, z0, z1):
    """Anel quadrado com furo passante (furo a `h` da borda)."""
    o = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    i = [(x0 + h, y0 + h), (x1 - h, y0 + h), (x1 - h, y1 - h), (x0 + h, y1 - h)]
    v = [(x, y, z0) for x, y in o + i] + [(x, y, z1) for x, y in o + i]  # 0-3 o_b, 4-7 i_b, 8-11 o_t, 12-15 i_t
    t = []
    for k in range(4):
        a, b = k, (k + 1) % 4
        for base in (0, 8):  # tampas: faixa entre externo e interno
            t += [(base + a, base + b, base + 4 + b), (base + a, base + 4 + b, base + 4 + a)]
        t += [(a, b, 8 + b), (a, 8 + b, 8 + a)]  # lado externo
        t += [(4 + a, 4 + b, 12 + b), (4 + a, 12 + b, 12 + a)]  # lado do furo
    return np.array(v, float), np.array(t, int)


def cilindro(cx, cy, r, z0, z1, n=24):
    ang = np.linspace(0, 2 * np.pi, n, endpoint=False)
    v = [(cx + r * np.cos(a), cy + r * np.sin(a), z) for z in (z0, z1) for a in ang] + [(cx, cy, z0), (cx, cy, z1)]
    t = []
    for k in range(n):
        a, b = k, (k + 1) % n
        t += [(2 * n, b, a), (2 * n + 1, n + a, n + b), (a, b, n + b), (a, n + b, n + a)]
    return np.array(v, float), np.array(t, int)


def caixa_anel_no_corte(x0, y0, x1, y1, z0, zm, z1):
    """Pele de caixa com um anel de vertices em z = zm (aresta exatamente no plano de corte)."""
    r = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    v = [(x, y, z) for z in (z0, zm, z1) for x, y in r]
    t = [(0, 2, 1), (0, 3, 2), (8, 9, 10), (8, 10, 11)]
    for k in range(4):
        a, b = k, (k + 1) % 4
        for lo in (0, 4):
            t += [(lo + a, lo + b, lo + 4 + b), (lo + a, lo + 4 + b, lo + 4 + a)]
    return np.array(v, float), np.array(t, int)


def repete(vt, n_tris):
    """Mesma malha com triangulos duplicados ate ter `n_tris` (nao muda a forma; so a contagem)."""
    v, t = vt
    mais = np.vstack([t] * (n_tris // len(t) + 1))[:n_tris]
    return v, mais


def peca(guid, classe, vt, **kw):
    return {"guid": guid, "classe": classe, "verts": None if vt is None else vt[0], "tris": None if vt is None else vt[1], **kw}


def pecas():
    return [
        peca("PAREDE", "IfcWall", moldura(0, 0, 2, 2, 0.5, 0.0, 3.0)),
        peca("PILAR", "IfcColumn", cilindro(5, 1, 0.3, 0.0, 3.0)),
        peca("MEIO", "IfcWall", caixa_anel_no_corte(8, 0, 9, 1, 0.0, Z, 2.4)),
        peca("BASE", "IfcWall", caixa(11, 0, Z, 12, 1, Z + 1.0)),  # zmin == z: cortada
        peca("LAJE", "IfcSlab", prisma(L_POLI, 0.0, 0.2, L_CAPS, 0, 4)),
        peca("MOVEL", "IfcFurniture", prisma(L_POLI, 0.0, 0.8, L_CAPS, 4, 4), movel=True),
        peca("GRANDE", "IfcSlab", repete(prisma(L_POLI, 0.0, 0.2, L_CAPS, 8, 4), 2400)),
        peca("TOPO", "IfcWall", caixa(11, 4, 0.0, 12, 5, Z)),  # zmax == z: vista
        peca("ACIMA", "IfcBeam", caixa(14, 0, 2.0, 15, 1, 3.0)),
        peca("FALHA", "IfcWall", None, caixa=(14, 4, 15, 5)),
        peca("DEGEN", "IfcWall", (np.array([(16, 4, 0.0), (17, 4, 0.0), (18, 4, 0.0)]), np.array([[0, 1, 2]])), caixa=(16, 4, 18, 4.5)),
    ]


AREA = {"PAREDE": 3.0, "PILAR": 0.5 * 24 * 0.3 ** 2 * np.sin(2 * np.pi / 24), "MEIO": 1.0, "BASE": 1.0,
        "LAJE": 3.0, "MOVEL": 3.0, "GRANDE": 3.5, "TOPO": 1.0, "FALHA": 1.0, "DEGEN": 1.0}
CORTADA, VISTA, ACIMA, FALHA = {"PAREDE", "PILAR", "MEIO", "BASE"}, {"LAJE", "MOVEL", "GRANDE", "TOPO"}, {"ACIMA"}, {"FALHA", "DEGEN"}


# ---------- leitura e rasterizacao do SVG (evenodd por <path>) ----------
def grupos(svg):
    """[(classes, guid, [subcaminhos (n,2) em coordenadas do mundo por <path>])] na ordem do SVG."""
    saida = []
    for m in re.finditer(r"<g\b([^>]*)>(.*?)</g>", svg, re.S):
        cls, g = re.search(r'class="([^"]*)"', m.group(1)), re.search(r'ifc:guid="([^"]+)"', m.group(1))
        if not g:
            continue
        paths = []
        for d in re.findall(r'<path\b[^>]*\bd="([^"]*)"', m.group(2)):
            subs = []
            for parte in d.replace("Z", " ").split("M")[1:]:
                n = np.array([float(x) for x in re.findall(r"-?\d+(?:\.\d+)?(?:e[-+]?\d+)?", parte)], float).reshape(-1, 2)
                subs.append(n * [1.0, -1.0])
            paths.append(subs)
        saida.append((cls.group(1).split() if cls else [], g.group(1), paths, m.group(2)))
    return saida


def pinta(paths, px, py):
    total = np.zeros(px.shape, bool)
    for subs in paths:
        w = np.zeros(px.shape, int)
        for pts in subs:
            if len(pts) < 3:
                continue
            for (ax, ay), (bx, by) in zip(pts, np.roll(pts, -1, axis=0)):
                w += ((ay <= py) != (by <= py)) & (px < ax + (py - ay) * (bx - ax) / np.where(by == ay, 1.0, by - ay))
        total |= (w & 1) == 1
    return total


def area_pintada(g, h=0.005):
    pts = np.vstack([s for p in g[2] for s in p])
    (x0, y0), (x1, y1) = pts.min(0) - 0.1, pts.max(0) + 0.1
    gx, gy = np.meshgrid(x0 + (np.arange(int((x1 - x0) / h)) + 0.5) * h, y0 + (np.arange(int((y1 - y0) / h)) + 0.5) * h)
    return pinta(g[2], gx.ravel(), gy.ravel()).sum() * h * h


@pytest.fixture(scope="module")
def res(tmp_path_factory):
    destino = tmp_path_factory.mktemp("previa") / "previa.svg"
    fases = []
    r = gerar_previa_planta(pecas(), Z, str(destino), ao_fase=fases.append)
    return r, {g[1]: g for g in grupos(r["svg"])}, destino, fases


# ---------- casos ----------
def test_auditoria_uniao_exata_e_disjunta(res):
    aud = res[0]["auditoria"]
    assert set(aud) == {"cortada", "vista", "acima", "falha"}
    assert {k: set(v) for k, v in aud.items()} == {"cortada": CORTADA, "vista": VISTA, "acima": ACIMA, "falha": FALHA}
    todos = [g for v in aud.values() for g in v]
    assert len(todos) == len(set(todos)) == len(pecas()), "GUID duplicado ou omitido"


def test_classes_cut_so_nas_cortadas_e_projection_nas_vistas(res):
    gs = res[1]
    for guid, g in gs.items():
        classe = next(p["classe"] for p in pecas() if p["guid"] == guid)
        assert g[0] == [classe, "cut" if guid in CORTADA else "projection"], (guid, g[0])
    assert "xmlns:ifc=" in res[0]["svg"].split(">")[0] + ">" or "xmlns:ifc=" in res[0]["svg"][:400]


def test_cada_guid_desenhado_uma_vez_na_ordem_e_acima_fora(res):
    ordem = [g[1] for g in grupos(res[0]["svg"])]
    assert ordem == [p["guid"] for p in pecas() if p["guid"] not in ACIMA], "ordem de `pecas`, sem duplicar, sem a peca acima do corte"
    assert "ACIMA" not in res[0]["svg"]


@pytest.mark.parametrize("guid", sorted(CORTADA))
def test_secao_exata_um_path_evenodd_por_peca(res, guid):
    g = res[1][guid]
    assert len(g[2]) == 1 and 'fill-rule="evenodd"' in g[3], "externo e furo no MESMO <path> evenodd"
    assert abs(area_pintada(g) - AREA[guid]) <= 0.02 * AREA[guid], f"{guid}: {area_pintada(g):.4f} != {AREA[guid]:.4f}"


def test_furo_da_moldura_aberto_e_aneis_externo_e_furo(res):
    g = res[1]["PAREDE"]
    assert len(g[2][0]) == 2, "externo + furo no mesmo path"
    px, py = np.array([1.0, 0.25, 1.75]), np.array([1.0, 1.0, 1.0])
    assert pinta(g[2], px, py).tolist() == [False, True, True], "furo (1,1) tem de ficar aberto; faixa da moldura pintada"


def test_vertice_exatamente_no_corte_nao_abre_anel(res):
    assert Z in {v for v in pecas()[2]["verts"][:, 2]}, "premissa: ha vertice em z_corte"
    for guid in ("MEIO", "BASE"):
        g = res[1][guid]
        assert guid in res[0]["auditoria"]["cortada"] and len(g[2]) == 1 and all(len(s) >= 4 for s in g[2][0])
        assert abs(area_pintada(g) - 1.0) <= 0.02


@pytest.mark.parametrize("guid", ["LAJE", "MOVEL", "GRANDE", "TOPO"])
def test_vistas_area_silhueta_ou_casco(res, guid):
    g = res[1][guid]
    assert abs(area_pintada(g) - AREA[guid]) <= 0.02 * AREA[guid], f"{guid}: {area_pintada(g):.4f} != {AREA[guid]}"
    assert "cut" not in g[0]


def test_movel_como_caixa_usa_caixa_xy_e_so_o_movel_muda():
    gs = {g[1]: g for g in grupos(gerar_previa_planta(pecas(), Z, moveis_como_caixa=True)["svg"])}
    assert abs(area_pintada(gs["MOVEL"]) - 4.0) <= 0.08  # caixa 2 x 2 do L
    assert abs(area_pintada(gs["LAJE"]) - 3.0) <= 0.06  # nao movel: silhueta


@pytest.mark.parametrize("n_tris, area", [(2000, 3.0), (2001, 3.5)])
def test_limite_de_triangulos_silhueta_ate_2000_casco_acima(n_tris, area):
    p = [peca("X", "IfcSlab", repete(prisma(L_POLI, 0.0, 0.2, L_CAPS), n_tris))]
    assert len(p[0]["tris"]) == n_tris
    g = grupos(gerar_previa_planta(p, Z)["svg"])[0]
    assert abs(area_pintada(g) - area) <= 0.02 * area


def test_falha_vira_caixa_provisoria_projection_e_conta_em_falha(res):
    for guid in ("FALHA", "DEGEN"):
        g = res[1][guid]
        assert "projection" in g[0] and "cut" not in g[0] and guid in res[0]["auditoria"]["falha"] and guid not in res[0]["auditoria"]["vista"]
        assert abs(area_pintada(g) - 1.0) <= 0.03


def test_escrita_atomica_e_fase_uma_vez(res, tmp_path, monkeypatch):
    r, _, destino, fases = res
    assert fases == ["previa"] and destino.read_text(encoding="utf-8") == r["svg"] and not os.path.exists(f"{destino}.tmp")
    vistos, orig = [], os.replace

    def espia(src, dst, *a, **k):
        vistos.append((str(src), str(dst), os.path.exists(str(dst)), open(src, encoding="utf-8").read()))
        return orig(src, dst, *a, **k)
    monkeypatch.setattr(os, "replace", espia)
    alvo, fases2 = tmp_path / "sub.svg", []
    r2 = gerar_previa_planta(pecas(), Z, str(alvo), ao_fase=fases2.append)
    assert fases2 == ["previa"]
    assert vistos == [(f"{alvo}.tmp", str(alvo), False, r2["svg"])], "gravar `destino.tmp` completo e so entao os.replace"
    assert alvo.read_text(encoding="utf-8") == r2["svg"]
    monkeypatch.undo()
    fases3 = []
    gerar_previa_planta(pecas(), Z, ao_fase=fases3.append)  # sem destino: nao grava, fase ainda uma vez
    assert fases3 == ["previa"]


# ---------- lacunas da revisao Argon (A a G) ----------
def solido_degrau():
    """Perfil em degrau no plano XZ extrudado em y 0..1: base 2 x Z, parte alta 1 x (2,4-Z). Face horizontal EXATAMENTE em z = Z (topo da base, x 1..2)."""
    v, t = prisma([(0, 0), (2, 0), (2, Z), (1, Z), (1, 2.4), (0, 2.4)], 0.0, 1.0, L_CAPS)  # colunas (x, z, y)
    return v[:, [0, 2, 1]], t


def caixa_aberta(x0, y0, x1, y1, z0, z1):
    """Caixa sem uma parede lateral: secao em z intermediario e cadeia ABERTA."""
    v, t = caixa(x0, y0, z0, x1, y1, z1)
    return v, np.delete(t, [4, 5], axis=0)


def viewbox(svg):
    x, y, w, h = map(float, re.search(r'viewBox="([^"]+)"', svg).group(1).split())
    return x, y, x + w, y + h  # coordenadas SVG (y invertido)


def uma(p, z=Z, **kw):
    r = gerar_previa_planta([p], z, **kw)
    return r, {g[1]: g for g in grupos(r["svg"])}


def test_A_degrau_horizontal_em_z_corte_secao_so_da_parte_alta():
    r, gs = uma(peca("D", "IfcWall", solido_degrau()))
    assert r["auditoria"]["cortada"] == {"D"} and not r["auditoria"]["falha"], "face horizontal em z_corte nao pode virar falha"
    g = gs["D"]
    assert g[0] == ["IfcWall", "cut"] and len(g[2]) == 1
    assert abs(area_pintada(g) - 1.0) <= 0.02, f"secao acima do degrau = 1 x 1, deu {area_pintada(g):.4f}"


def test_B_vista_com_furo_um_path_evenodd_furo_aberto_projection():
    r, gs = uma(peca("V", "IfcSlab", moldura(0, 0, 2, 2, 0.5, 0.0, 1.0)))  # zmax 1,0 <= Z
    g = gs["V"]
    assert r["auditoria"]["vista"] == {"V"} and g[0] == ["IfcSlab", "projection"]
    assert len(g[2]) == 1 and 'fill-rule="evenodd"' in g[3] and len(g[2][0]) == 2
    assert abs(area_pintada(g) - 3.0) <= 0.06
    assert pinta(g[2], np.array([1.0, 0.25]), np.array([1.0, 1.0])).tolist() == [False, True]


@pytest.mark.parametrize("nome, vt, area", [
    ("aberta", caixa_aberta(0, 0, 1, 1, 0.0, 2.0), 1.0),  # cruza Z, secao aberta
    ("colinear_cruza", (np.array([(0, 0, 0.0), (2, 2, 0.0), (1, 1, 2.0)]), np.array([[0, 1, 2]])), 4.0),  # cruza Z, triangulo vertical degenerado (secao 1 segmento); bbox 2 x 2
    ("degenerada_vista", (np.array([(16, 4, 0.0), (17, 5, 0.0), (18, 6, 0.0)]), np.array([[0, 1, 2]])), 4.0),  # area XY nula, bbox 2 x 2
])
def test_C_falha_sem_chave_caixa_aparece_no_svg_pela_bbox_dos_verts(nome, vt, area):
    p = peca("F", "IfcWall", vt)
    assert "caixa" not in p
    r, gs = uma(p)
    assert r["auditoria"]["falha"] == {"F"} and not (r["auditoria"]["cortada"] | r["auditoria"]["vista"])
    assert "F" in gs, "peca em falha sumiu do SVG"
    g = gs["F"]
    assert "projection" in g[0] and "cut" not in g[0]
    x, y = vt[0][:, 0], vt[0][:, 1]
    assert abs(area_pintada(g) - (x.max() - x.min()) * (y.max() - y.min())) <= 0.02 * max(area, 1.0)


def test_C_malha_ausente_sem_caixa_nao_levanta_e_fica_na_auditoria():
    r = gerar_previa_planta([peca("N", "IfcWall", None), peca("OK", "IfcWall", caixa(0, 0, 0, 1, 1, 3))], Z)
    assert r["auditoria"]["falha"] == {"N"} and r["auditoria"]["cortada"] == {"OK"}  # sem bbox nao ha o que desenhar; so nao pode quebrar nem sumir da auditoria


def test_D_movel_acima_do_limiar_com_moveis_como_caixa_usa_caixa_nao_casco():
    vt = repete(prisma(L_POLI, 0.0, 0.8, L_CAPS), 2400)
    r, gs = uma(peca("M", "IfcFurniture", vt, movel=True), moveis_como_caixa=True)
    assert r["auditoria"]["vista"] == {"M"} and abs(area_pintada(gs["M"]) - 4.0) <= 0.08, "caixa XY do L = 4,0 (casco seria 3,5)"
    r, gs = uma(peca("M", "IfcFurniture", vt, movel=True), moveis_como_caixa=False)
    assert abs(area_pintada(gs["M"]) - 3.5) <= 0.07  # controle: sem a opcao, grande => casco


def test_E_viewbox_cobre_todas_as_pecas_desenhadas(res):
    x0, y0, x1, y1 = viewbox(res[0]["svg"])
    # desenhadas: x 0..18, y mundo 0..6 (laje, movel e grande em y 4..6) => SVG y -6..0
    assert x0 <= 0 + 1e-6 and y0 <= -6 + 1e-6 and x1 >= 18 - 1e-6 and y1 >= 0 - 1e-6, (x0, y0, x1, y1)
    assert x1 - x0 <= 18 * 1.1 and y1 - y0 <= 6 * 1.1 + 0.5, "viewBox folgado demais"
    for g in res[1].values():
        pts = np.vstack([s for p in g[2] for s in p]) * [1, -1]
        assert pts[:, 0].min() >= x0 - 1e-6 and pts[:, 0].max() <= x1 + 1e-6 and pts[:, 1].min() >= y0 - 1e-6 and pts[:, 1].max() <= y1 + 1e-6, g[1]


def test_E_viewbox_ignora_peca_acima_do_corte():
    r = gerar_previa_planta([peca("A", "IfcWall", caixa(0, 0, 0, 1, 1, 3)), peca("Z", "IfcBeam", caixa(100, 100, 2.0, 101, 101, 3.0))], Z)
    assert viewbox(r["svg"])[2] < 50 and r["auditoria"]["acima"] == {"Z"}


def test_F_erro_de_ponto_flutuante_no_topo_nao_vira_corte():
    vt = caixa(0, 0, 0.4, 1, 1, 0.4 + 0.8)  # zmax = 1,2000000000000002 > 1,2
    assert vt[0][:, 2].max() > Z
    r, gs = uma(peca("T", "IfcWall", vt))
    assert r["auditoria"]["vista"] == {"T"} and not r["auditoria"]["cortada"] | r["auditoria"]["falha"]
    assert gs["T"][0] == ["IfcWall", "projection"] and abs(area_pintada(gs["T"]) - 1.0) <= 0.02


def test_F_erro_de_ponto_flutuante_na_base_nao_vira_acima():
    vt = caixa(0, 0, Z + 2.2e-16, 1, 1, 2.4)  # zmin = z_corte + 1 ulp: toca o plano => cortada
    assert vt[0][:, 2].min() > Z
    r, gs = uma(peca("B", "IfcWall", vt))
    assert r["auditoria"]["cortada"] == {"B"} and abs(area_pintada(gs["B"]) - 1.0) <= 0.02


@pytest.mark.parametrize("z_solto", [0.1, 5.0])
def test_G_casco_e_classificacao_ignoram_vertices_soltos(z_solto):
    v, t = repete(prisma(L_POLI, 0.0, 0.2, L_CAPS), 2400)
    v = np.vstack([v, [(100.0, 100.0, z_solto), (-50.0, 80.0, z_solto)]])  # nenhum triangulo usa estes dois
    r, gs = uma(peca("G", "IfcSlab", (v, t)))
    assert r["auditoria"]["vista"] == {"G"}, "vertice solto em z alto nao pode mudar a classe"
    assert abs(area_pintada(gs["G"], h=0.01) - 3.5) <= 0.07, "casco so dos vertices usados"
    x0, y0, x1, y1 = viewbox(r["svg"])
    assert x1 - x0 < 10, "viewBox nao pode incluir vertice solto"
