# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo F0-S06-T19d4: poda das peças HLR fora da janela do quadro em `desenho._corte` (T3). Cartão: docs/state/cards/F0-S06/F0-S06-T19d4-poda.md. Não editar nesta tarefa.
CONTRATO (`desenho._corte`, `pedido["motor_visivel"]` verdadeiro):
1. Toda peça de `incl` que iria ao iterator HLR (inelegível, p.ex. IfcDoor/IfcWindow/parede com abertura, ou qualquer outra não-motor) cuja caixa em `pedido["caixas_coords"]`
   ([xmin,ymin,zmin,xmax,ymax,zmax], mundo, metros, chave int ou str do id STEP) NÃO toca a janela do quadro expandida em 0,1 m sai do iterator.
   Janela = u em [-W/2-0,1, W/2+0,1], v em [-H/2-0,1, H/2+0,1] (u, v no quadro da vista, origem = posição da vista em metros), W = XLength*esc, H = YLength*esc.
2. Peça sem caixa válida (ausente, tamanho errado, não finita; `caixa_valida`) FICA. A poda é só em (u, v), nunca em w.
3. `motor_visivel` ausente/False: nada muda (todas as peças vão ao HLR). Observável: o grupo `ifc:guid` da peça podada não aparece no SVG; os `d` das que ficam são idênticos aos de uma execução sem poda.
4. Se só sobra a anotação no HLR, não levanta e devolve SVG válido com os cortes do motor."""
from __future__ import annotations

import itertools
import re
import xml.etree.ElementTree as ET

import numpy as np
import pytest
from s05_conteudo_aux import _limpa, exigir  # noqa: F401  (fixture autouse)
from test_s06_t19d2_motor_no_corte_oraculo import COM_TAMPA, _cena, _cortes, _roda

W, H = 10.0, 4.0  # bloco da cena (m), esc = 1
FOLGA = 0.1


def _caixa_uv(c, u0, u1, v0, v1, w0=-0.5, w1=0.5, esc=1.0):
    """Caixa do mundo (xmin,ymin,zmin,xmax,ymax,zmax) que cobre o retângulo (u, v, w) do quadro da vista (origem = posição da vista * esc)."""
    Q = c.Q
    cantos = np.array([Q.origem * esc + u * Q.u + v * Q.v + w * Q.w for u, v, w in itertools.product((u0, u1), (v0, v1), (w0, w1))])
    return [float(x) for x in (*cantos.min(axis=0), *cantos.max(axis=0))]


def _guids(svg, c):
    return {n for n, g in c.guids.items() if f'ifc:guid="{g}"' in svg}


def _ds(svg, guid):
    out = []
    for m in re.finditer(r'<g\b[^>]*\bifc:guid="%s"[^>]*>(.*?)</g>' % re.escape(guid), svg, re.S):
        out += re.findall(r'<path\b[^>]*\bd="([^"]*)"', m.group(1))
    return out


def _poda(c, caixas, chave=int, motor=True, **extra):
    """Roda o corte com `caixas` = {nome: caixa|valor cru}; chave = int ou str do id STEP."""
    coords = {chave(c.ids[n]): b for n, b in caixas.items()}
    if motor is None:
        return _roda(c, caixas_coords=coords, **extra)
    return _roda(c, caixas_coords=coords, motor_visivel=motor, **extra)


@pytest.fixture
def cena(tmp_path):
    c = _cena(tmp_path)
    ref = _roda(c, motor_visivel=True)
    assert ref["ok"], ref.get("erro")
    assert {"Parede", "Porta", *COM_TAMPA} <= _guids(ref["svg"], c), "a cena sem poda tem de trazer as peças HLR e as tampas do motor"
    c.ref = ref
    return c


def _dentro(c):
    return _caixa_uv(c, -4.0, 4.0, -1.5, 1.5)


# ---------------------------------------------------------------- (a) dentro da janela fica
@pytest.mark.parametrize("chave", [int, str])
def test_peca_dentro_da_janela_fica(cena, chave):
    r = _poda(cena, {"Parede": _dentro(cena), "Porta": _dentro(cena)}, chave)
    assert r["ok"], r.get("erro")
    assert {"Parede", "Porta"} <= _guids(r["svg"], cena)


# ---------------------------------------------------------------- (b) fora em u some; (c) fora em v some; (f) chave int e str
@pytest.mark.parametrize("chave", [int, str])
@pytest.mark.parametrize("lado", [-1, 1])
def test_peca_fora_em_u_some(cena, chave, lado):
    a = W / 2 + FOLGA + 0.2
    u0, u1 = (a, a + 1.0) if lado > 0 else (-a - 1.0, -a)
    fora = _caixa_uv(cena, u0, u1, -1.5, 1.5)
    r = _poda(cena, {"Parede": fora, "Porta": _dentro(cena)}, chave)
    assert r["ok"], r.get("erro")
    g = _guids(r["svg"], cena)
    assert "Parede" not in g and "Porta" in g


@pytest.mark.parametrize("chave", [int, str])
@pytest.mark.parametrize("lado", [-1, 1])
def test_peca_fora_em_v_some(cena, chave, lado):
    a = H / 2 + FOLGA + 0.2
    v0, v1 = (a, a + 1.0) if lado > 0 else (-a - 1.0, -a)
    fora = _caixa_uv(cena, -4.0, 4.0, v0, v1)
    r = _poda(cena, {"Porta": fora, "Parede": _dentro(cena)}, chave)
    assert r["ok"], r.get("erro")
    g = _guids(r["svg"], cena)
    assert "Porta" not in g and "Parede" in g


def test_as_duas_podadas_e_as_tampas_do_motor_ficam(cena):
    r = _poda(cena, {"Parede": _caixa_uv(cena, 7.0, 8.0, -1, 1), "Porta": _caixa_uv(cena, -8.0, -7.0, -1, 1)})
    g = _guids(r["svg"], cena)
    assert r["ok"] and not g & {"Parede", "Porta"}


# ---------------------------------------------------------------- (d) borda: toca a janela por menos de 0,1 m fica
@pytest.mark.parametrize("eixo", ["u", "v"])
@pytest.mark.parametrize("lado", [-1, 1])
def test_borda_dentro_da_folga_fica(cena, eixo, lado):
    meia = (W if eixo == "u" else H) / 2
    a = meia + 0.05  # entre meia e meia + 0,1: ainda toca a janela expandida
    faixa = (a, a + 1.0) if lado > 0 else (-a - 1.0, -a)
    caixa = _caixa_uv(cena, *faixa, -1.5, 1.5) if eixo == "u" else _caixa_uv(cena, -4.0, 4.0, *faixa)
    r = _poda(cena, {"Parede": caixa, "Porta": _dentro(cena)})
    assert r["ok"] and {"Parede", "Porta"} <= _guids(r["svg"], cena)


def test_borda_que_cruza_a_janela_fica(cena):
    r = _poda(cena, {"Parede": _caixa_uv(cena, 4.0, 9.0, -1.5, 1.5), "Porta": _caixa_uv(cena, -3.0, 3.0, 1.0, 6.0)})
    assert r["ok"] and {"Parede", "Porta"} <= _guids(r["svg"], cena)


# ---------------------------------------------------------------- (e) sem caixa válida fica
def test_peca_fora_sem_caixa_fica(cena):
    r = _poda(cena, {"Porta": _caixa_uv(cena, 7.0, 8.0, -1, 1)})  # Parede sem entrada em caixas_coords
    assert r["ok"] and _guids(r["svg"], cena) >= {"Parede"}
    assert "Porta" not in _guids(r["svg"], cena), "a Porta tem caixa válida e está fora: sai (garante que a poda age)"


@pytest.mark.parametrize("invalida", [[0.0, 0.0, 0.0], [1.0] * 7, [float("nan")] * 6, [0, 0, 0, float("inf")] + [1.0, 1.0], None, "abc", []])
def test_caixa_invalida_fica(cena, invalida):
    r = _poda(cena, {"Parede": invalida, "Porta": _caixa_uv(cena, 7.0, 8.0, -1, 1)})
    assert r["ok"], r.get("erro")
    g = _guids(r["svg"], cena)
    assert "Parede" in g, "caixa inválida: a peça fica"
    assert "Porta" not in g, "a Porta tem caixa válida e está fora: sai (garante que a poda age)"


# ---------------------------------------------------------------- (g) sem motor_visivel nada muda
@pytest.mark.parametrize("motor", [False, None])
def test_sem_motor_visivel_nao_poda(cena, motor):
    fora = {"Parede": _caixa_uv(cena, 7.0, 8.0, -1, 1), "Porta": _caixa_uv(cena, -3.0, 3.0, 5.0, 6.0)}
    r = _poda(cena, fora, motor=motor)
    base = _roda(cena)
    assert r["ok"] and r["svg"] == base["svg"]
    assert {"Parede", "Porta"} <= _guids(r["svg"], cena)


# ---------------------------------------------------------------- (h) as que ficam: mesmos caminhos
@pytest.mark.parametrize("chave", [int, str])
def test_caminhos_das_pecas_que_ficam_sao_identicos(cena, chave):
    r = _poda(cena, {"Parede": _dentro(cena), "Porta": _caixa_uv(cena, 7.0, 8.0, -1, 1)}, chave)
    assert r["ok"], r.get("erro")
    ref = cena.ref["svg"]
    for n in ("Parede", *COM_TAMPA):
        assert _ds(ref, cena.guids[n]) and _ds(r["svg"], cena.guids[n]) == _ds(ref, cena.guids[n]), f"caminhos de {n} mudaram"
    assert _cortes(r["svg"]).keys() >= {cena.guids[n] for n in ("Parede", *COM_TAMPA)}


# ---------------------------------------------------------------- poda é só em (u, v)
def test_poda_nao_olha_para_w(cena):
    longe = _caixa_uv(cena, -4.0, 4.0, -1.5, 1.5, w0=50.0, w1=60.0)  # dentro em (u, v), muito longe em w
    r = _poda(cena, {"Parede": longe, "Porta": longe})
    assert r["ok"] and {"Parede", "Porta"} <= _guids(r["svg"], cena)


# ---------------------------------------------------------------- (i) escala != 1: a janela continua em metros
def test_escala_diferente_de_um_janela_em_metros(tmp_path):
    esc = 0.001
    c = _cena(tmp_path)
    c.ped["vista"] = {**c.ped["vista"], "escala": esc}
    ref = _roda(c, motor_visivel=True)
    assert ref["ok"], ref.get("erro")
    visiveis = _guids(ref["svg"], c)
    assert {"Parede", "Porta"} & visiveis, "a cena em escala 0,001 não trouxe peça HLR: teste vazio"
    w, h = W * esc, H * esc  # janela: u em +-(0,005 + 0,1), v em +-(0,002 + 0,1)
    dentro = _caixa_uv(c, -0.01, 0.01, -0.01, 0.01, esc=esc)
    fora_u = _caixa_uv(c, w / 2 + FOLGA + 0.2, w / 2 + FOLGA + 1.2, -0.01, 0.01, esc=esc)
    fora_v = _caixa_uv(c, -0.01, 0.01, h / 2 + FOLGA + 0.2, h / 2 + FOLGA + 1.2, esc=esc)
    borda = _caixa_uv(c, w / 2 + 0.05, w / 2 + 1.0, -0.01, 0.01, esc=esc)  # toca a janela expandida (0,005 + 0,1): fica
    r = _poda(c, {"Parede": dentro, "Porta": fora_u}, **{"vista": c.ped["vista"]})
    assert r["ok"], r.get("erro")
    g = _guids(r["svg"], c)
    assert ("Parede" in g) == ("Parede" in visiveis) and "Porta" not in g
    r = _poda(c, {"Parede": borda, "Porta": fora_v}, **{"vista": c.ped["vista"]})
    g = _guids(r["svg"], c)
    assert ("Parede" in g) == ("Parede" in visiveis) and "Porta" not in g
    # a janela NÃO vira milímetros: 0,5 m além do quadro está fora mesmo com esc = 0,001
    assert "Parede" in visiveis


# ---------------------------------------------------------------- (j) tudo podado: só a anotação no HLR
def test_tudo_podado_devolve_svg_valido_com_os_cortes_do_motor(cena):
    r = _poda(cena, {"Parede": _caixa_uv(cena, 7.0, 8.0, -1, 1), "Porta": _caixa_uv(cena, -8.0, -7.0, -1, 1)})
    assert r["ok"], r.get("erro")
    ET.fromstring(r["svg"])
    assert not _guids(r["svg"], cena) & {"Parede", "Porta"}
    cm = _cortes(r["svg"])
    assert {cena.guids[n] for n in COM_TAMPA} <= set(cm) and all(cm[cena.guids[n]].area > 0 for n in COM_TAMPA)
    assert r["motor_pecas"] and r["n_paths"] == len(re.findall(r"<path\b", r["svg"]))
