# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo T19j4c: janelas e portas pelo motor (`motor_janelas`) entregam a SEÇÃO como contorno fechado (preenchimento de corte).
Contrato (cartão F0-S06-T19j4c): além das linhas, cada anel fechado da seção (externos e furos) vai no grupo SVG da peça como
caminho fechado (ponto inicial repetido no fim); externo e furo no MESMO `<path>` (o estilo usa evenodd por elemento: em `<path>` separados o furo seria pintado). Oráculo:
(1) cada anel esperado (a mão) aparece como subcaminho fechado; (2) área preenchida (rasterizada com preenchimento evenodd por
elemento `<path>`, como o estilo `cut`) do motor == HLR do mesmo pedido (IoU >= 0,99) e == área calculada à mão; (3) cobertura de
linhas da j4b segue; (4) `motor_janelas` False => SVG idêntico. Modelo: porta x 1..2 com folha 1 x 0,25 e LEQUE (setor de quarto de
disco de raio 0,9 e 12 lados, centro (2; 0,30), z 0..2, cruza o corte 1,2) e janela x 3..4 com moldura (furo 0,05 de borda)."""
from __future__ import annotations

import re

import numpy as np
import pytest
import s06_t07_aux as X
from s05_conteudo_aux import _limpa, exigir  # noqa: F401  (autouse)
from test_s06_t19j4b_janelas_motor_oraculo import PORTA, TOL, VAOS, amostras, B, cena, dist, pedido, pelo_motor, roda, segs

R, NSEG = 0.9, 12
ARCO = [(2.0 + R * np.cos(a), 0.30 + R * np.sin(a)) for a in np.linspace(0, np.pi / 2, NSEG + 1)]
LEQUE = [(2.0, 0.30)] + ARCO  # vértices do setor (mundo)
AREA_LEQUE = 0.5 * R * R * NSEG * np.sin(np.pi / 2 / NSEG)  # soma dos 12 triângulos do centro, a mão
AREA_PORTA = 1.0 * 0.25 + AREA_LEQUE
AREA_JANELA = 1.0 * 0.25 - 0.9 * 0.15


def _poli(f, pts):
    return f.create_entity("IfcPolyline", Points=[f.create_entity("IfcCartesianPoint", Coordinates=(float(a), float(b))) for a, b in pts])


def extra_porta(f, pav, g):
    porta = f.by_guid(g["porta0"])
    sol = f.create_entity("IfcExtrudedAreaSolid", SweptArea=f.create_entity("IfcArbitraryClosedProfileDef", ProfileType="AREA", OuterCurve=_poli(f, [(x - 1.0, y) for x, y in LEQUE + [LEQUE[0]]])),
                          Position=f.create_entity("IfcAxis2Placement3D", Location=X._pt(f, 0, 0, 0)), Depth=2.0,
                          ExtrudedDirection=f.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0)))
    rep = porta.Representation.Representations[0]
    rep.Items = list(rep.Items) + [sol]  # coordenadas locais: a porta está em x=1


def extra_janela(f, pav, g):
    ret = lambda x0, y0, x1, y1: _poli(f, [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)])
    f.by_guid(g["jan0"]).Representation.Representations[0].Items[0].SweptArea = f.create_entity(
        "IfcArbitraryProfileDefWithVoids", ProfileType="AREA", OuterCurve=ret(0, 0, 1, 0.25), InnerCurves=[ret(0.05, 0.05, 0.95, 0.2)])


CENAS = {"porta0": (extra_porta, PORTA), "jan0": (extra_janela, VAOS[1:])}


# ---------- leitura e rasterização do SVG ----------
def caminhos(r, guid):
    """Lista (por elemento `<path>`) de listas de subcaminhos (n,2) em coordenadas do mundo."""
    txt = B.grupo(r["svg"], guid) or ""
    saida = []
    for d in re.findall(r'<path d="([^"]*)"', txt):
        subs = []
        for parte in re.split(r"M", d)[1:]:
            n = np.array([float(v) for v in re.findall(r"-?\d+(?:\.\d+)?(?:e-?\d+)?", parte)], float).reshape(-1, 2)
            subs.append(n * [1.0, -1.0])
        saida.append(subs)
    return saida


def preenche(caminhos_, janela, h=0.005):
    """Máscara da área pintada: par-ímpar (fill-rule evenodd do estilo `.cut path`) dentro de cada `<path>`, união entre elementos."""
    x0, y0, x1, y1 = janela
    gx, gy = np.meshgrid(x0 + (np.arange(int((x1 - x0) / h)) + 0.5) * h, y0 + (np.arange(int((y1 - y0) / h)) + 0.5) * h)
    px, py = gx.ravel(), gy.ravel()
    total = np.zeros(px.shape, bool)
    for subs in caminhos_:
        w = np.zeros(px.shape, int)  # paridade de cruzamentos (evenodd, como `.cut path` em estilo.py)
        for pts in subs:
            if len(pts) < 3:
                continue
            a, b = pts, np.roll(pts, -1, axis=0)  # fecha implicitamente, como o SVG
            for (ax, ay), (bx, by) in zip(a, b):
                w += ((ay <= py) != (by <= py)) & (px < ax + (py - ay) * (bx - ax) / np.where(by == ay, 1.0, by - ay))
        total |= (w & 1) == 1
    return total, h * h


def esperado(nome):
    return (("jan0", (2.9, -0.1, 4.1, 0.35), AREA_JANELA), ("porta0", (0.9, -0.1, 3.0, 1.3), AREA_PORTA))[nome != "jan0"]


def anel_fechado_com(caminhos_, vertices):
    """Existe subcaminho fechado (1º ponto repetido no fim) que passa por todos os `vertices` (mundo)?"""
    for subs in caminhos_:
        for pts in subs:
            if len(pts) >= 4 and np.allclose(pts[0], pts[-1], atol=1e-5) and \
                    all(np.min(np.hypot(*(pts - v).T)) < 1e-5 for v in vertices):
                return True
    return False


def rodar(tmp_path, nome):
    f, g, gid = cena(*CENAS[nome])
    p = pedido(f, gid, tmp_path / "p")
    return f, g, roda(p), roda(p, motor_janelas=True), roda(p, motor_janelas=False)


# ---------- casos ----------
def test_porta_com_leque_aneis_fechados(tmp_path):
    f, g, base, com, _ = rodar(tmp_path, "porta0")
    assert pelo_motor(f, g, com, "porta0")
    porta = caminhos(com, g["porta0"])
    assert anel_fechado_com(porta, [(1, 0), (2, 0), (2, 0.25), (1, 0.25)])  # folha
    assert anel_fechado_com(porta, LEQUE)  # leque inteiro, com os 13 pontos do arco


def test_janela_com_batente_externo_e_furo_fechados_no_mesmo_path(tmp_path):
    f, g, base, com, _ = rodar(tmp_path, "jan0")
    assert pelo_motor(f, g, com, "jan0")
    jan = caminhos(com, g["jan0"])
    assert anel_fechado_com(jan, [(3, 0), (4, 0), (4, 0.25), (3, 0.25)])  # externo
    assert anel_fechado_com(jan, [(3.05, 0.05), (3.95, 0.05), (3.95, 0.2), (3.05, 0.2)])  # furo
    assert [c for c in jan if len(c) == 2], "externo e furo têm de estar no mesmo <path> (evenodd por elemento; em <path> separados o furo seria pintado)"


@pytest.mark.parametrize("nome", ["porta0", "jan0"])
def test_area_pintada_do_motor_igual_ao_hlr_e_a_mao(tmp_path, nome):
    f, g, base, com, _ = rodar(tmp_path, nome)
    janela, area_mao = esperado(nome)[1:]
    m_hlr, cel = preenche(caminhos(base, g[nome]), janela)
    m_mot, _ = preenche(caminhos(com, g[nome]), janela)
    assert m_hlr.sum() * cel > 0.9 * area_mao  # o HLR realmente pinta (modelo válido)
    iou = (m_hlr & m_mot).sum() / max((m_hlr | m_mot).sum(), 1)
    assert iou >= 0.99, f"IoU {iou:.3f}"
    assert abs(m_mot.sum() * cel - area_mao) <= 0.01 * area_mao  # incl. o leque (0,63 m2) na porta e o furo aberto na janela


@pytest.mark.parametrize("nome", ["porta0", "jan0"])
def test_linhas_e_cobertura_da_j4b_seguem(tmp_path, nome):
    f, g, base, com, _ = rodar(tmp_path, nome)
    hlr = [p for subs in caminhos(base, g[nome]) for p in subs]
    mot = [p for subs in caminhos(com, g[nome]) for p in subs]
    assert (dist(amostras(hlr), segs(mot)) <= TOL).mean() >= 0.999
    assert (dist(amostras(mot), segs(hlr)) <= TOL).all()


@pytest.mark.parametrize("nome", ["porta0", "jan0"])
def test_flag_false_svg_identico(tmp_path, nome):
    f, g, base, _com, falso = rodar(tmp_path, nome)
    assert base["svg"] == falso["svg"] and base.get("motor_pecas") == falso.get("motor_pecas")
