# SPDX-License-Identifier: AGPL-3.0-or-later
"""Auxiliar de integração do oráculo F0-S06-T18a (modelos IFC com peça densa). Não é de `app/`; o implementador não edita."""
from __future__ import annotations

import s06_t07_aux as X
import s06_t07b_aux as B
from s06_t17_aux import pedido_planta  # noqa: F401
from s06_t18a_malha import anel_de_blocos, area_aneis, cilindro  # noqa: F401


def densificar(f, el, malha):
    """Troca o corpo de `el` por IfcPolygonalFaceSet com a malha (verts locais, tris 0-based)."""
    v, t = malha
    pts = f.create_entity("IfcCartesianPointList3D", CoordList=[tuple(float(c) for c in p) for p in v])
    faces = [f.create_entity("IfcIndexedPolygonalFace", CoordIndex=[i + 1 for i in tri]) for tri in t]
    rep = el.Representation.Representations[0]
    rep.Items = [f.create_entity("IfcPolygonalFaceSet", Coordinates=pts, Closed=True, Faces=faces)]
    rep.RepresentationType = "Tessellation"
    return el


def modelo_denso(n_lados=24, off=(0.0, 0.0), k=1.0, **kw):
    """Modelo T07b (parede, vãos de `kw`, caixas, móvel `M0_0` que cruza o corte). O móvel vira cilindro de `n_lados` lados (raio 0,3, h 1,5; 4*n_lados-4 triângulos); a parede continua caixa (12).
    `off` georreferência e `k` (unidade do arquivo = 1/k m; a malha escala junto). Devolve (arquivo, {nome: guid}, vista, móvel, parede)."""
    kw.setdefault("vaos", ())
    f, pavs, g = B.modelo("IFC4", off, k=k, n_pav=1, n_moveis=1, **kw)
    mov = densificar(f, f.by_guid(g["M0_0"]), (lambda m: ([tuple(c * k for c in q) for q in m[0]], m[1]))(cilindro(0.3, n_lados)))
    return f, g, B.planta(f, pavs[0], "V"), mov, f.by_guid(g["P0"])


def com_pesadas_longe(f, g, n=5):
    """`n` proxies densos (cilindros) em x 100..., mais `Longe0` denso: sobram só pesadas na metade direita de uma divisão em 2 faixas. Devolve os elementos densos."""
    pav = f.by_type("IfcBuildingStorey")[0]
    novos = [densificar(f, X.caixa(f, "IfcBuildingElementProxy", f"H{i}", 100.0 + 3 * i, 1.0, 0.0, 0.3, 0.3, 1.5), cilindro(0.3, 24)) for i in range(n)]
    X.conter(f, pav, *novos)
    return novos + [densificar(f, f.by_guid(g["Longe0"]), cilindro(0.3, 24))]
