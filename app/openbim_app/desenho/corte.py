# SPDX-License-Identifier: AGPL-3.0-or-later
"""Geração de corte 2D bruto em SVG: cliente do processo auxiliar (ADR-004 regra 9)."""
from __future__ import annotations

import dataclasses
from typing import Iterable

import ifcopenshell
import ifcopenshell.util.unit

from openbim_app import vistas_ifc
from openbim_app.desenho import auxiliar, selecao
from openbim_app.desenho.selecao import Selecao, SelecaoInvalida

_SVG_VAZIO = '<svg xmlns="http://www.w3.org/2000/svg" version="1.1"></svg>'


@dataclasses.dataclass(frozen=True)
class Corte:
    svg: str
    n_paths: int
    selecao: Selecao
    tempos: dict[str, float]
    unidade_escala: float
    caixas: tuple[int, ...]


def gerar_corte(
    ifc: ifcopenshell.file,
    gid_vista: str,
    *,
    categorias_ocultas: Iterable[str] = (),
    ocultar_secundarias: bool = True,
    threads: int | None = None,
    limite_triangulos: int | None = None,
    limite_s: float = auxiliar.LIMITE_PADRAO_S,
    cancelar=None,
    executor=None,
) -> Corte:
    if ocultar_secundarias:
        cats = tuple(dict.fromkeys((*categorias_ocultas, *selecao.CATEGORIAS_PADRAO_PLANTA_OCULTAS)))
    else:
        cats = tuple(categorias_ocultas)
    selecao._validar_categorias(ifc, cats)

    info = vistas_ifc.ler_vista(ifc, gid_vista)
    if info.get("tipo") != "CORTE":
        raise SelecaoInvalida(f"Vista {gid_vista} não é do tipo CORTE (tipo={info.get('tipo')})")

    scale = float(ifcopenshell.util.unit.calculate_unit_scale(ifc))
    sel = selecao.selecionar(
        ifc,
        gid_vista,
        categorias_ocultas=cats,
        executor=executor,
        limite_s=limite_s,
        cancelar=cancelar,
    )
    if not sel.ids:
        return Corte(
            svg=_SVG_VAZIO,
            n_paths=0,
            selecao=sel,
            tempos={"geo_s": 0.0, "write_s": 0.0, "finalize_s": 0.0},
            unidade_escala=scale,
            caixas=(),
        )

    pedido = {
        "protocolo": 1,
        "op": "desenho",
        "elementos": [[i, ifc.by_id(i).GlobalId] for i in sel.ids],
        "vista": {
            "tipo": "CORTE",
            "guid": gid_vista,
            "escala": scale,
        },
        "limite_triangulos": limite_triangulos,
    }
    if threads is not None:
        pedido["threads"] = threads

    with auxiliar.preparar(ifc, pedido) as p:
        r = auxiliar.executar(p, limite_s=limite_s, cancelar=cancelar, executor=executor)

    return Corte(
        svg=r["svg"],
        n_paths=r["n_paths"],
        selecao=sel,
        tempos=dict(r["tempos"]),
        unidade_escala=scale,
        caixas=tuple(r["caixas"]),
    )
