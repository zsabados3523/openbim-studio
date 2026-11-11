# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo F0-S06-T17 (divisão por custo): `faixas.limites/dividir(..., pesos=None)` e `desenho._pesos_planta`. Modelo: s06_t17_aux / T15o."""
from __future__ import annotations

import math
import re

import pytest
from s05_conteudo_aux import _limpa  # noqa: F401  (autouse)
from s06_t17_aux import EspiaoFilho, ExecutorEspiao, X, cortes_de, exigir_igual, modelo, planta_de

import obim_geometria.desenho as D
import obim_geometria.faixas as F


def _antigo(itens, n):
    """Regra de antes dos pesos: bordas nos quantis por contagem de centros distintos."""
    cs = sorted({(a + b) / 2.0 for _i, _g, a, b in itens})
    if len(cs) < 2 or n == 1:
        return [(None, None)]
    m = len(cs)
    pos = sorted({i for k in range(1, n) if 1 <= (i := round(k * m / n)) <= m - 1})
    bs = [None] + [(cs[i - 1] + cs[i]) / 2.0 for i in pos] + [None]
    return list(zip(bs, bs[1:]))


def _itens():
    pesados = [(i, f"p{i}", 10.0 + 0.01 * i, 10.2 + 0.01 * i) for i in range(9)]
    leves = [(100 + i, f"l{i}", i * 0.5, i * 0.5 + 0.3) for i in range(400)]
    return pesados + leves, {i: 300.0 for i in range(9)}


@pytest.mark.parametrize("n", [1, 2, 3, 4, 7, 50])
def test_sem_pesos_igual_ao_comportamento_antigo(n):
    itens, _ = _itens()
    assert F.limites(itens, n) == _antigo(itens, n) == F.limites(itens, n, pesos=None) == F.limites(itens, n, pesos={})


def test_com_pesos_nenhuma_faixa_passa_do_teto_e_bordas_crescem():
    itens, pesos = _itens()
    n, peso = 4, lambda i: pesos.get(i, 1.0)
    lims = F.limites(itens, n, pesos=pesos)
    assert len(lims) > 1 and lims[0][0] is None and lims[-1][1] is None
    bordas = [b for _a, b in lims[:-1]]
    assert all(x < y for x, y in zip(bordas, bordas[1:])) and all(a == b0 for (_, b0), (a, _) in zip(lims, lims[1:]))
    total, teto = sum(peso(i) for i, *_ in itens), None
    teto = math.ceil(total / n) + 300
    for a, b in lims:
        w = sum(peso(i) for i, _g, u0, u1 in itens if (a is None or (u0 + u1) / 2 >= a) and (b is None or (u0 + u1) / 2 < b))
        assert w <= teto, f"faixa ({a}, {b}) pesa {w} > {teto}"
    sem = max(sum(peso(i) for i, _g, u0, u1 in itens if (a is None or (u0 + u1) / 2 >= a) and (b is None or (u0 + u1) / 2 < b)) for a, b in _antigo(itens, n))
    assert sem > teto, "sem pesos os móveis empilham numa faixa só (o caso existe)"


def test_dividir_com_pesos_particiona_donos_sem_perda_nem_duplicata():
    itens, pesos = _itens()
    lims, fx = F.limites(itens, 4, pesos=pesos), F.dividir(itens, 4, pesos=pesos)
    assert len(fx) == len(lims)
    donos = []
    for (a, b), el in zip(lims, fx):
        ids = {e[0] for e in el}
        d = [i for i, _g, u0, u1 in itens if (a is None or (u0 + u1) / 2 >= a) and (b is None or (u0 + u1) / 2 < b)]
        assert set(d) <= ids and ids == {i for i, _g, u0, u1 in itens if (b is None or u0 <= b + 1e-6) and (a is None or u1 >= a - 1e-6)}
        donos += d
    assert sorted(donos) == sorted(i for i, *_ in itens)


def _grande(n_col=220, movel=True, tmp=None):
    f, pavs = X.estrutura("IFC4")
    els = [X.caixa(f, "IfcColumn", f"C{i}", i * 0.5, 6.0, 0.0, 0.2, 0.2, 2.0) for i in range(n_col)]
    if movel:
        els.append(X.caixa(f, "IfcFurniture", "Mv", 3.0, 2.0, 0.0, 1.0, 1.0, 0.5))
    X.conter(f, pavs[0], *els)
    f.write(str(tmp))
    return f, [(e.id(), e.GlobalId, e.ObjectPlacement.RelativePlacement.Location.Coordinates[0], e.ObjectPlacement.RelativePlacement.Location.Coordinates[0] + 0.2) for e in els], els


def test_pesos_planta_so_liga_com_itens_e_movel_e_arquivo_valido(tmp_path):
    arq = tmp_path / "g.ifc"
    f, itens, els = _grande(tmp=arq)
    ped = {"arquivo": str(arq)}
    assert D._pesos_planta(ped, itens) == {els[-1].id(): D.PESO_MOVEL} and D.PESO_MOVEL == 300
    assert D._pesos_planta({**ped, "moveis_como_caixa": True}, itens) is None
    assert D._pesos_planta(ped, itens[:D.MIN_ITENS_PESO - 1]) is None and D.MIN_ITENS_PESO == 200
    arq2 = tmp_path / "s.ifc"
    _f2, itens2, _ = _grande(movel=False, tmp=arq2)
    assert D._pesos_planta({"arquivo": str(arq2)}, itens2) is None
    assert D._pesos_planta({"arquivo": str(tmp_path / "nao_existe.ifc")}, itens) is None
    (tmp_path / "ruim.ifc").write_text("isto nao e IFC")
    assert D._pesos_planta({"arquivo": str(tmp_path / "ruim.ifc")}, itens) is None


def test_planta_grande_com_pesos_igual_ao_sem_faixas(monkeypatch):
    f, g, gid = modelo()
    pav = f.by_type("IfcBuildingStorey")[0]
    X.conter(f, pav, *[X.caixa(f, "IfcColumn", f"E{i}", 0.02 * i, 5.5, 0.0, 0.1, 0.1, 2.0) for i in range(210)])
    base, ex = planta_de(f, gid), ExecutorEspiao()
    esp = EspiaoFilho(monkeypatch, F)
    pesos = []
    real = D._pesos_planta
    monkeypatch.setattr(D, "_pesos_planta", lambda p, it: pesos.append(real(p, it)) or pesos[-1])
    r = planta_de(f, gid, ex, faixas=4)
    assert len(ex.pedidos_desenho[0]["elementos"]) >= 200 and pesos and pesos[0], "os pesos ligaram (móveis do modelo)"
    assert len(esp.chamadas) >= 3
    exigir_igual(base.svg, r.svg, cortes_de(esp.chamadas))
    assert r.n_paths == len(re.findall(r"<path\b", r.svg)) and r.caixas == base.caixas
