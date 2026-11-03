# SPDX-License-Identifier: AGPL-3.0-or-later
"""Geração de planta 2D bruta em SVG: cliente do processo auxiliar (ADR-006 §2, §3 item 0 e §4)."""
from __future__ import annotations

import dataclasses
from typing import Iterable

import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.util.placement
import ifcopenshell.util.unit

from openbim_app import vistas_ifc
from openbim_app.desenho import auxiliar, selecao
from openbim_app.desenho.selecao import Selecao, SelecaoInvalida

_SVG_VAZIO = '<svg xmlns="http://www.w3.org/2000/svg" version="1.1"></svg>'


@dataclasses.dataclass(frozen=True)
class Planta:
    svg: str
    n_paths: int
    selecao: Selecao
    tempos: dict[str, float]
    unidade_escala: float
    altura_corte: float
    caixas: tuple[int, ...]


def _altura_corte(ifc: ifcopenshell.file, anotacao) -> float:
    pset = ifcopenshell.util.element.get_pset(anotacao, "OBIM_Vista") or {}
    valor = pset.get("AlturaCorte", 1.2)
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        raise SelecaoInvalida(f"AlturaCorte inválida: {valor!r}")
    valor = float(valor)
    if valor <= 0:
        raise SelecaoInvalida(f"AlturaCorte inválida: {valor!r}")
    return valor


def _origem_pavimento(ifc: ifcopenshell.file, pav) -> tuple[float, float, float]:
    if pav.ObjectPlacement is not None:
        m = ifcopenshell.util.placement.get_local_placement(pav.ObjectPlacement)
        return float(m[0, 3]), float(m[1, 3]), float(m[2, 3])
    return 0.0, 0.0, float(getattr(pav, "Elevation", 0.0) or 0.0)


def gerar_planta(
    ifc: ifcopenshell.file,
    gid_vista: str,
    *,
    categorias_ocultas: Iterable[str] = (),
    threads: int | None = None,
    limite_triangulos: int | None = None,
    limite_s: float = auxiliar.LIMITE_PADRAO_S,
    cancelar=None,
    executor=None,
) -> Planta:
    cats = tuple(categorias_ocultas)
    selecao._validar_categorias(ifc, cats)

    info = vistas_ifc.ler_vista(ifc, gid_vista)
    if info.get("tipo") != "PLANTA":
        raise SelecaoInvalida(f"Vista {gid_vista} não é do tipo PLANTA (tipo={info.get('tipo')})")
    anotacao = ifc.by_guid(gid_vista)
    h = _altura_corte(ifc, anotacao)

    scale = float(ifcopenshell.util.unit.calculate_unit_scale(ifc))
    sel = selecao.selecionar(ifc, gid_vista, categorias_ocultas=cats)
    pav = ifc.by_id(sel.pavimento)
    ox, oy, oz = _origem_pavimento(ifc, pav)
    altura_corte = float(oz * scale + h)

    if not sel.ids:
        return Planta(
            svg=_SVG_VAZIO,
            n_paths=0,
            selecao=sel,
            tempos={"geo_s": 0.0, "write_s": 0.0, "finalize_s": 0.0},
            unidade_escala=scale,
            altura_corte=altura_corte,
            caixas=(),
        )

    pedido = {
        "protocolo": 1,
        "op": "desenho",
        "elementos": [[i, ifc.by_id(i).GlobalId] for i in sel.ids],
        "vista": {
            "tipo": "PLANTA",
            "altura_corte_m": altura_corte,
            "origem_pav": [ox, oy, oz],
            "escala": scale,
        },
        "limite_triangulos": limite_triangulos,
    }
    if threads is not None:
        pedido["threads"] = threads

    with auxiliar.preparar(ifc, pedido) as p:
        r = auxiliar.executar(p, limite_s=limite_s, cancelar=cancelar, executor=executor)

    return Planta(
        svg=r["svg"],
        n_paths=r["n_paths"],
        selecao=sel,
        tempos=dict(r["tempos"]),
        unidade_escala=scale,
        altura_corte=altura_corte,
        caixas=tuple(r["caixas"]),
    )
