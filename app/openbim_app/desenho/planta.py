# SPDX-License-Identifier: AGPL-3.0-or-later
"""Geração de planta 2D bruta em SVG: cliente do processo auxiliar (ADR-006 §2, §3 item 0 e §4)."""
from __future__ import annotations

import dataclasses
import math
from pathlib import Path
from typing import TYPE_CHECKING, Iterable

import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.util.placement
import ifcopenshell.util.unit

from openbim_app import vistas_ifc
from openbim_app.desenho import auxiliar, selecao
from openbim_app.desenho.selecao import Selecao, SelecaoInvalida

if TYPE_CHECKING:
    from openbim_app.desenho.cache import CacheDesenho

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
    em_cache: tuple[int, ...] = ()
    pesados: tuple = ()
    pedido: dict | None = None


def _altura_corte(ifc: ifcopenshell.file, anotacao) -> float:
    pset = ifcopenshell.util.element.get_pset(anotacao, "OBIM_View") or {}
    valor = pset.get("CutHeight", 1.2)
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        raise SelecaoInvalida(f"CutHeight inválida: {valor!r}")
    valor = float(valor)
    if not math.isfinite(valor) or valor <= 0:
        raise SelecaoInvalida(f"CutHeight inválida: {valor!r}")
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
    ocultar_secundarias: bool = True,
    moveis_como_caixa: bool = False,
    cache_tipo: bool = True,
    threads: int | None = None,
    limite_triangulos: int | None = None,
    limite_s: float = auxiliar.LIMITE_PADRAO_S,
    cancelar=None,
    executor=None,
    caminho_ifc: str | Path | None = None,
    cache: "CacheDesenho | None" = None,
    faixas: int | None = None,
    pesados: str | None = None,
    limiar_pesado: int | None = None,
) -> Planta:
    if pesados not in (None, "silhueta"):
        raise ValueError(f"pesados inválido: {pesados!r} (esperado None ou 'silhueta')")
    if limiar_pesado is not None and (
        isinstance(limiar_pesado, bool) or not isinstance(limiar_pesado, int) or limiar_pesado < 1
    ):
        raise ValueError(f"limiar_pesado inválido: {limiar_pesado!r} (esperado inteiro >= 1 ou None)")
    if faixas is not None and (isinstance(faixas, bool) or not isinstance(faixas, int) or faixas < 1):
        raise ValueError(f"faixas inválidas: {faixas!r} (esperado inteiro >= 1 ou None)")
    if ocultar_secundarias:
        cats = tuple(dict.fromkeys((*categorias_ocultas, *selecao.CATEGORIAS_PADRAO_PLANTA_OCULTAS)))
    else:
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
    if getattr(pav, "Elevation", None) is None:
        raise SelecaoInvalida(f"Pavimento {pav.Name or pav.GlobalId} sem cota (Elevation); não é possível gerar a planta")
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
            em_cache=(),
        )

    cx_env = getattr(sel, "caixas_envolventes", None) or {}
    caixas_coords = {
        int(i): list(cx_env[i] if i in cx_env else cx_env[str(i)])
        for i in sel.ids
        if (i in cx_env or str(i) in cx_env)
    }
    pedido = {
        "protocolo": 1,
        "op": "desenho",
        "elementos": [[i, ifc.by_id(i).GlobalId] for i in sel.ids],
        "vista": {
            "tipo": "PLANTA",
            "guid": gid_vista,
            "altura_corte_m": altura_corte,
            "origem_pav": [ox, oy, oz],
            "escala": scale,
            "pavimento": pav.GlobalId,
        },
        "moveis_como_caixa": bool(moveis_como_caixa),
        "cache_tipo": bool(cache_tipo),
        "limite_triangulos": limite_triangulos,
        "caixas_coords": caixas_coords,
    }
    if threads is not None:
        pedido["threads"] = threads
    if faixas not in (None, 1):
        pedido["faixas"] = faixas
    if pesados:
        pedido["pesados"] = pesados
        if limiar_pesado is not None:
            pedido["limiar_pesado"] = limiar_pesado

    if cache is not None:
        ch = cache.chave(ifc, pedido)
        r = cache.obter(ch)
        if r is None:
            with auxiliar.preparar(ifc, pedido, caminho_ifc=caminho_ifc) as p:
                r = auxiliar.executar(p, limite_s=limite_s, cancelar=cancelar, executor=executor)
            cache.guardar(ch, r)
    else:
        with auxiliar.preparar(ifc, pedido, caminho_ifc=caminho_ifc) as p:
            r = auxiliar.executar(p, limite_s=limite_s, cancelar=cancelar, executor=executor)

    return Planta(
        svg=r["svg"],
        n_paths=r["n_paths"],
        selecao=sel,
        tempos=dict(r["tempos"]),
        unidade_escala=scale,
        altura_corte=altura_corte,
        caixas=tuple(int(x) for x in r.get("caixas") or ()),
        em_cache=tuple(int(x) for x in r.get("em_cache") or ()),
        pesados=tuple(dict(d) for d in (r.get("pesados") or ())),
        pedido=pedido,
    )
