# SPDX-License-Identifier: AGPL-3.0-or-later
"""Auxiliar do oráculo F0-S06-T17 (planta em faixas). Não é de `app/`; o implementador não edita. Reaproveita os espiões e a régua de segmentos da T15o."""
from __future__ import annotations

import copy
import re
import xml.etree.ElementTree as ET
from collections import Counter

import s06_t07_aux as X
import s06_t07b_aux as B
from s06_t15i_aux import ExecutorEspiao, desenho_geo, planta as Pl  # noqa: F401
from s06_t15o_aux import NUM, EspiaoFilho, casar, faixas, id_de, recortar  # noqa: F401

_PROJ = re.compile(r'<g class="projection">.*?</g>', re.S)
_GRUPO = re.compile(r'<g\b(?![^>]*IfcBuildingStorey)[^>]*\bifc:guid="([^"]+)"[^>]*>.*?</g>', re.S)
_D = re.compile(r'\sd="([^"]*)"')


def modelo(off=(0.0, 0.0)):
    """Térreo com parede P0 de 5 m (porta em x 1..2, janela em 3..4: o vão fica longe do centro da parede), móvel M0_0, caixas Xc0/Xa0/Xb0, `Longe0` a 150 m, mais: viga `Vig` baixa
    cruzando tudo (só projeção), pilares `Pc1`/`Pc2` que dividem a mesma representação, móvel `ML` de forma real, em L com um lado chanfrado (cruza o corte; o traço inclinado atravessa uma borda) e `MB` igual e baixo (só projeção)."""
    f, pavs, g = B.modelo("IFC4", off, vaos=(("porta", "IfcDoor", 1.0, 0.0, 1.0, 2.0), ("jan", "IfcWindow", 3.0, 0.9, 1.0, 1.0)), n_pav=1)
    ox, oy = off

    def cx(cls, nome, x, y, z, dx, dy, dz):
        e = X.caixa(f, cls, nome, ox + x, oy + y, z, dx, dy, dz)
        g[nome] = e.GlobalId
        return e

    def ele(nome, x, y, h):
        e = cx("IfcFurniture", nome, x, y, 0.0, 1.5, 1.0, h)
        pts = [f.create_entity("IfcCartesianPoint", Coordinates=p) for p in ((0., 0.), (1.5, 0.), (1.5, .4), (.4, .4), (.4, 1.), (0., 0.))]
        sol = e.Representation.Representations[0].Items[0]
        sol.SweptArea = f.create_entity("IfcArbitraryClosedProfileDef", ProfileType="AREA", OuterCurve=f.create_entity("IfcPolyline", Points=pts))
        return e

    c1, c2 = cx("IfcColumn", "Pc1", 0.3, 3.5, 0.0, 0.3, 0.3, 2.0), cx("IfcColumn", "Pc2", 4.2, 3.5, 0.0, 0.3, 0.3, 2.0)
    c2.Representation = c1.Representation
    X.conter(f, pavs[0], cx("IfcBeam", "Vig", 0.0, 1.5, 0.5, 5.0, 0.2, 0.4), c1, c2, ele("ML", 2.3, 2.0, 1.5), ele("MB", 3.5, 4.5, 0.5))
    return f, g, B.planta(f, pavs[0], "V")


def planta_de(f, gid, executor=None, **kw):
    kw.setdefault("cache_tipo", False)  # com o cache de tipo o motor clona o corte do 1º igual e arredonda a 1e-4: fora da régua exata
    return Pl.gerar_planta(f, gid, executor=executor or ExecutorEspiao(), **kw)


def pedido_planta(f, gid, pasta, **kw):
    """Pedido de `desenho` como `gerar_planta` o monta, apontando para o IFC completo gravado em `pasta`."""
    ex = ExecutorEspiao()
    planta_de(f, gid, ex, **kw)
    p = copy.deepcopy(ex.pedidos_desenho[0])
    pasta.mkdir(exist_ok=True)
    f.write(str(pasta / "m.ifc"))
    p["arquivo"] = str(pasta / "m.ifc")
    p["threads"] = p.get("threads", 4)
    return p


def itens_de(p):
    """(id, guid, u0, u1) de cada elemento do pedido; u = x do mundo (= x do SVG da planta), pelas caixas de `caixas.processar`."""
    from obim_geometria import caixas
    r = caixas.processar({"arquivo": p["arquivo"], "elementos": p["elementos"], "threads": 1})
    cx = {int(k): v for k, v in r["caixas_envolventes"].items()}
    return [(i, g, cx[i][0], cx[i][3]) for i, g in p["elementos"] if i in cx]


def cortes_de(chamadas):
    return sorted({b for c in chamadas for b in (c["faixa"]["u0"], c["faixa"]["u1"]) if b is not None})


def _ws(t):
    return re.sub(r">\s+<", "><", re.sub(r'\s+', " ", re.sub(r'\sid="[^"]*"', "", t))).strip()


def partes(svg, aprox=False):
    """(esqueleto sem projeção/grupos de elemento, lista ordenada de (guid, grupo)). Lista, não dicionário: grupo duplicado reprova. `aprox`: (guid, caixa a 0,01 m)."""
    def g(m):
        if not aprox:
            return m.group(1), _ws(m.group(0))
        xy = [float(v) for d in _D.findall(m.group(0)) for v in re.findall(NUM, d)]
        return m.group(1), tuple(round(v, 2) for v in (min(xy[0::2]), min(xy[1::2]), max(xy[0::2]), max(xy[1::2])))
    return _ws(_GRUPO.sub("", _PROJ.sub("<PROJ/>", svg))), sorted(g(m) for m in _GRUPO.finditer(svg))


def segmentos(svg):
    m = _PROJ.search(svg)
    out = []
    for d in _D.findall(m.group(0) if m else ""):
        for sub in d.split("M")[1:]:
            pts = [(float(a), float(b)) for a, b in re.findall(rf"({NUM}),({NUM})", sub)]
            out += [tuple(sorted(s, key=lambda v: (round(v[0], 4), round(v[1], 4)))) for s in zip(pts, pts[1:]) if s[0] != s[1]]
    return out


def exigir_igual(base, svg, cortes, aprox=False):
    """Mesmo desenho: XML válido, uma só projeção, esqueleto e grupos de elemento (um por guid, texto idêntico) iguais; projeção = mesmo multiconjunto de segmentos (1e-6; 1e-3 em `aprox`)
    com a base partida nas mesmas bordas (a emenda é a única diferença permitida; traço duplicado ou faltando reprova)."""
    assert ET.fromstring(svg).tag.endswith("svg") and svg.count('class="projection"') == 1
    (e0, g0), (e1, g1) = partes(base, aprox), partes(svg, aprox)
    assert e1 == e0, "cabeçalho/estilo/pavimento mudou"
    assert g1 == g0, f"grupos diferem: faltam {list((Counter(map(str, g0)) - Counter(map(str, g1))))[:2]}, sobram {list((Counter(map(str, g1)) - Counter(map(str, g0))))[:2]}"
    so_base, so_par = casar(recortar(segmentos(base), cortes), recortar(segmentos(svg), cortes), 1e-3 if aprox else 1e-6)
    assert not so_base and not so_par, f"projeção difere: faltam {len(so_base)} (ex. {so_base[:2]}), sobram {len(so_par)} (ex. {so_par[:2]})"
