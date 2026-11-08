# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo F0-S06-T15i (parte b): caixas 2D de móveis no corte e na planta.
Ref: docs/state/cards/F0-S06/F0-S06-T15i-caixas2d-moveis.md.
"""
from __future__ import annotations

import pytest
from s06_t15i_aux import *  # noqa: F401,F403


@pytest.mark.parametrize("chave", ["int", "str"])
def test_planta_posicao_absoluta_assimetrica_e_equivale_ao_fallback(monkeypatch, chave):
    """Posição absoluta do retângulo 2D: X nunca troca com Y, ordem [xmin,ymin,zmin,xmax,ymax,zmax]."""
    f, movel, pav = _modelo_planta_assimetrico()
    caixa = [1.0, 2.0, 0.0, 4.0, 7.0, 1.0]
    k = movel.id() if chave == "int" else str(movel.id())
    chamadas_cs = _espia_cs(monkeypatch)

    res = _rodar_planta(f, _pedido_planta(f, movel, pav, 0.5, {k: caixa}))
    assert res["ok"] is True and movel.id() not in chamadas_cs
    pts, _cls = _grupo_path(res["svg"], movel.GlobalId)
    # y do SVG = -y do mundo: x em [1,4], y em [-7,-2]; sequência exata dos cantos
    esperado = [(1.0, -7.0), (4.0, -7.0), (4.0, -2.0), (1.0, -2.0), (1.0, -7.0)]
    _pts_aprox(pts, esperado, tol=1e-3)
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    assert (min(xs), max(xs)) == pytest.approx((1.0, 4.0), abs=1e-3)
    assert (min(ys), max(ys)) == pytest.approx((-7.0, -2.0), abs=1e-3)

    # Equivalência com o caminho antigo (create_shape sobre o mesmo elemento/geometria)
    chamadas_cs.clear()
    res_fb = _rodar_planta(f, _pedido_planta(f, movel, pav, 0.5, {}))
    assert res_fb["ok"] is True and movel.id() in chamadas_cs
    pts_fb, _ = _grupo_path(res_fb["svg"], movel.GlobalId)
    _pts_aprox(pts, pts_fb)


@pytest.mark.parametrize("alt, incluido", [
    (0.5, True),    # zmin(0) <= alt < zmax(1)
    (0.0, True),    # alt == zmin: ainda incluído (excluir só se zmin > alt)
    (1.2, True),    # alt > zmax: caixa abaixo do corte continua desenhada (igual ao fallback)
    (-0.5, False),  # zmin > alt: excluído
])
def test_planta_faixa_z_usa_zmin_e_nao_zmax(monkeypatch, alt, incluido):
    f, movel, pav = _modelo_planta_assimetrico()
    caixa = [1.0, 2.0, 0.0, 4.0, 7.0, 1.0]
    chamadas_cs = _espia_cs(monkeypatch)
    res = _rodar_planta(f, _pedido_planta(f, movel, pav, alt, {movel.id(): caixa}))
    assert res["ok"] is True and movel.id() not in chamadas_cs
    if incluido:
        assert movel.id() in res["caixas"] and movel.GlobalId in res["svg"]
    else:
        assert movel.id() not in res["caixas"] and movel.GlobalId not in res["svg"]
    # o fallback decide igual (mesma geometria)
    res_fb = _rodar_planta(f, _pedido_planta(f, movel, pav, alt, {}))
    assert (movel.id() in res_fb["caixas"]) is incluido


def test_planta_zmin_zmax_invertidos_na_ordem_dos_campos(monkeypatch):
    """zmin/zmax distintos de x/y: caixa alta com zmin=0.3 > alt=0.2 é excluída; com alt=0.4 é incluída."""
    f, movel, pav = _modelo_planta_assimetrico()
    caixa = [1.0, 2.0, 0.3, 4.0, 7.0, 9.0]
    r1 = _rodar_planta(f, _pedido_planta(f, movel, pav, 0.2, {movel.id(): caixa}))
    assert movel.id() not in r1["caixas"]
    r2 = _rodar_planta(f, _pedido_planta(f, movel, pav, 0.4, {movel.id(): caixa}))
    assert movel.id() in r2["caixas"]
    pts, _ = _grupo_path(r2["svg"], movel.GlobalId)
    _pts_aprox(pts, [(1.0, -7.0), (4.0, -7.0), (4.0, -2.0), (1.0, -2.0), (1.0, -7.0)], tol=1e-3)


@pytest.mark.parametrize("ycam, classe", [(1.2, "cut"), (3.0, "boundary"), (-1.0, "boundary")])
@pytest.mark.parametrize("chave", ["int", "str"])
def test_corte_coordenadas_absolutas_equivalem_ao_fallback(monkeypatch, ycam, classe, chave):
    """Câmera fora da origem + caixa não cúbica: <path> idêntico ao do create_shape; 'cruza' correto."""
    f, gid, movel = _modelo_corte_deslocado(ycam)
    k = movel.id() if chave == "int" else str(movel.id())
    chamadas_cs = _espia_cs(monkeypatch)

    res = desenho_geo._corte(f, _pedido_corte(gid, movel, {k: _CAIXA_C}), None, 0.0)
    assert res["ok"] is True and movel.id() not in chamadas_cs
    pts, cls = _grupo_path(res["svg"], movel.GlobalId)

    chamadas_cs.clear()
    res_fb = desenho_geo._corte(f, _pedido_corte(gid, movel, None), None, 0.0)
    assert movel.id() in chamadas_cs
    pts_fb, cls_fb = _grupo_path(res_fb["svg"], movel.GlobalId)

    _pts_aprox(pts, pts_fb)
    assert cls == cls_fb == classe
    if classe == "boundary":
        assert "cut" not in cls
    # dimensões: largura = dx (2.0), altura = dz (0.9)
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    assert max(xs) - min(xs) == pytest.approx(2.0, abs=2e-3)
    assert max(ys) - min(ys) == pytest.approx(0.9, abs=2e-3)


def test_corte_posicao_acompanha_origem_da_camera():
    """Deslocar a câmera 0.5 m em X desloca o retângulo -0.5 no SVG (orig_cam_m não pode ser zerada/invertida)."""
    f1, gid1, m1 = _modelo_corte_deslocado(1.2)
    r1 = desenho_geo._corte(f1, _pedido_corte(gid1, m1, {m1.id(): _CAIXA_C}), None, 0.0)
    p1, _ = _grupo_path(r1["svg"], m1.GlobalId)

    # mesma caixa, caixa deslocada +0.5 m em X (mesmo plano de câmera) => retângulo desloca +0.5
    caixa_dx = [_CAIXA_C[0] + 0.5, _CAIXA_C[1], _CAIXA_C[2], _CAIXA_C[3] + 0.5, _CAIXA_C[4], _CAIXA_C[5]]
    r2 = desenho_geo._corte(f1, _pedido_corte(gid1, m1, {m1.id(): caixa_dx}), None, 0.0)
    p2, _ = _grupo_path(r2["svg"], m1.GlobalId)
    assert min(p[0] for p in p2) - min(p[0] for p in p1) == pytest.approx(0.5, abs=2e-3)
    assert min(p[1] for p in p2) == pytest.approx(min(p[1] for p in p1), abs=2e-3)

    # deslocar +0.4 m em Z move o retângulo no eixo vertical do SVG em módulo 0.4
    caixa_dz = [_CAIXA_C[0], _CAIXA_C[1], _CAIXA_C[2] + 0.4, _CAIXA_C[3], _CAIXA_C[4], _CAIXA_C[5] + 0.4]
    r3 = desenho_geo._corte(f1, _pedido_corte(gid1, m1, {m1.id(): caixa_dz}), None, 0.0)
    p3, _ = _grupo_path(r3["svg"], m1.GlobalId)
    assert abs(min(p[1] for p in p3) - min(p[1] for p in p1)) == pytest.approx(0.4, abs=2e-3)
    assert min(p[0] for p in p3) == pytest.approx(min(p[0] for p in p1), abs=2e-3)


def test_corte_caixa_que_nao_cruza_plano_nao_gera_cut():
    """Caixa inteiramente de um lado do plano de corte: classe boundary, nunca cut."""
    f, gid, movel = _modelo_corte_deslocado(1.2)
    # plano em y=1.2; caixa falsa totalmente em y>1.2 (e outra em y<1.2)
    for caixa in ([1.5, 1.5, 0.2, 3.5, 2.0, 1.1], [1.5, 0.1, 0.2, 3.5, 1.0, 1.1]):
        res = desenho_geo._corte(f, _pedido_corte(gid, movel, {movel.id(): caixa}), None, 0.0)
        _pts, cls = _grupo_path(res["svg"], movel.GlobalId)
        assert cls == "boundary" and "cut" not in cls
    # e a que atravessa o plano é cut
    res = desenho_geo._corte(f, _pedido_corte(gid, movel, {movel.id(): [1.5, 0.7, 0.2, 3.5, 2.0, 1.1]}), None, 0.0)
    assert _grupo_path(res["svg"], movel.GlobalId)[1] == "cut"
