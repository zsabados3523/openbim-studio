# SPDX-License-Identifier: AGPL-3.0-or-later
"""Geração de corte 2D bruto em SVG: cliente do processo auxiliar (ADR-004 regra 9)."""
from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable

import ifcopenshell
import ifcopenshell.util.placement
import ifcopenshell.util.unit

from openbim_app import vistas_ifc
from openbim_app.desenho import auxiliar, selecao
from openbim_app.desenho.cache import CacheCancelado, assinatura_arquivo, resolver_assinatura
from openbim_app.desenho.selecao import (
    Selecao,
    SelecaoInvalida,
    _validar_profundidade_corte,
)

if TYPE_CHECKING:
    from openbim_app.desenho.cache import CacheDesenho

_SVG_VAZIO = '<svg xmlns="http://www.w3.org/2000/svg" version="1.1"></svg>'


@dataclasses.dataclass(frozen=True)
class Corte:
    svg: str
    n_paths: int
    selecao: Selecao
    tempos: dict[str, float]
    unidade_escala: float
    caixas: tuple[int, ...]


def _bloco_de(ann: Any) -> Any | None:
    """Retorna o IfcBlock da anotação de corte, se existir."""
    rep_prod = getattr(ann, "Representation", None)
    for rep in getattr(rep_prod, "Representations", ()) or ():
        for it in getattr(rep, "Items", ()) or ():
            if it.is_a("IfcCsgSolid"):
                raiz = getattr(it, "TreeRootExpression", None)
                if raiz is not None and raiz.is_a("IfcBlock"):
                    return raiz
            elif it.is_a("IfcBlock"):
                return it
    return None


def _gerar_corte_uma_vez(
    ifc: ifcopenshell.file,
    gid_vista: str,
    cats: tuple[str, ...],
    scale: float,
    threads: int | None,
    limite_triangulos: int | None,
    limite_s: float,
    cancelar,
    executor,
    caminho_ifc: str | Path | None,
    assinatura_ifc: tuple[int, int] | None,
    moveis_caixa2d: bool,
    profundidade_corte: float | None,
    faixas: int,
    cache: "CacheDesenho | None",
    motor_visivel: bool | None,
    sessao_selecao: selecao.SessaoSelecao | None,
    filho=None,
) -> Corte:
    sel = selecao.selecionar(
        ifc,
        gid_vista,
        categorias_ocultas=cats,
        executor=executor,
        limite_s=limite_s,
        cancelar=cancelar,
        sessao=sessao_selecao,
        caminho_ifc=caminho_ifc,
        profundidade_corte=profundidade_corte,
        filho=filho,
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

    anotacao = ifc.by_guid(gid_vista)
    bloco = _bloco_de(anotacao)
    pos_bloco = getattr(bloco, "Position", None) if bloco is not None else None
    loc_bloco = getattr(pos_bloco, "Location", None) if pos_bloco is not None else None
    coords_bloco = getattr(loc_bloco, "Coordinates", None) if loc_bloco is not None else None
    vista_dict: dict[str, Any] = {
        "tipo": "CORTE",
        "guid": gid_vista,
        "escala": scale,
        "matriz": [
            [float(x) for x in linha]
            for linha in ifcopenshell.util.placement.get_local_placement(anotacao.ObjectPlacement)
        ],
        "bloco": {
            "XLength": float(bloco.XLength),
            "YLength": float(bloco.YLength),
            "ZLength": float(bloco.ZLength),
            "Location": [float(x) for x in coords_bloco] if coords_bloco else [0.0, 0.0, 0.0],
        },
    }
    if getattr(anotacao, "Name", None) is not None:
        vista_dict["nome"] = str(anotacao.Name)
    if profundidade_corte is not None:
        vista_dict["profundidade_corte"] = float(profundidade_corte)

    cx_env = getattr(sel, "caixas_envolventes", None) or {}
    caixas_coords = {
        int(i): list(cx_env[i] if i in cx_env else cx_env[str(i)])
        for i in sel.ids
        if (i in cx_env or str(i) in cx_env)
    }
    pedido: dict[str, Any] = {
        "protocolo": 1,
        "op": "desenho",
        "elementos": [[i, ifc.by_id(i).GlobalId] for i in sel.ids],
        "vista": vista_dict,
        "limite_triangulos": limite_triangulos,
        "moveis_caixa2d": bool(moveis_caixa2d),
        "caixas_coords": caixas_coords,
    }
    if profundidade_corte is not None:
        pedido["profundidade_corte"] = float(profundidade_corte)
    if threads is not None:
        pedido["threads"] = threads
    if faixas != 1:
        pedido["faixas"] = faixas
    if motor_visivel is not None:
        pedido["motor_visivel"] = motor_visivel

    if cache is not None:
        kw_chave = (
            {"arquivo": caminho_ifc, "assinatura": assinatura_ifc}
            if (caminho_ifc is not None and assinatura_ifc is not None)
            else {}
        )
        try:
            ch = cache.chave(ifc, pedido, cancelar=cancelar, **kw_chave)
        except CacheCancelado as exc:
            raise auxiliar.DesenhoCancelado("Operação cancelada no cálculo da chave do cache") from exc
        r = cache.obter(ch)
        if r is None:
            kw_prep = (
                {"caminho_ifc": caminho_ifc, "assinatura": assinatura_ifc}
                if (caminho_ifc is not None and assinatura_ifc is not None)
                else {}
            )
            with auxiliar.preparar(ifc, pedido, **kw_prep) as p:
                sig_prep = p.pedido.get("assinatura")
                r = auxiliar.executar(p, limite_s=limite_s, cancelar=cancelar, executor=executor, filho=filho)
            if cancelar is not None and cancelar.is_set():
                raise auxiliar.DesenhoCancelado("Operação cancelada antes de gravar no cache")
            if caminho_ifc is None or (
                sig_prep == list(assinatura_ifc) and assinatura_arquivo(caminho_ifc) == assinatura_ifc
            ):
                cache.guardar(ch, r)
    else:
        kw_prep = (
            {"caminho_ifc": caminho_ifc, "assinatura": assinatura_ifc}
            if (caminho_ifc is not None and assinatura_ifc is not None)
            else {}
        )
        with auxiliar.preparar(ifc, pedido, **kw_prep) as p:
            r = auxiliar.executar(p, limite_s=limite_s, cancelar=cancelar, executor=executor, filho=filho)

    return Corte(
        svg=r["svg"],
        n_paths=r["n_paths"],
        selecao=sel,
        tempos=dict(r["tempos"]),
        unidade_escala=scale,
        caixas=tuple(int(x) for x in r.get("caixas") or ()),
    )


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
    caminho_ifc: str | Path | None = None,
    assinatura_ifc: tuple[int, int] | None = None,
    moveis_caixa2d: bool = False,
    profundidade_corte: float | None = None,
    faixas: int = 1,
    cache: "CacheDesenho | None" = None,
    motor_visivel: bool | None = None,
    sessao_selecao: selecao.SessaoSelecao | None = None,
    filho=None,
) -> Corte:
    selecao._validar_filho(filho)
    if sessao_selecao is not None and not isinstance(sessao_selecao, selecao.SessaoSelecao):
        raise TypeError(f"sessao_selecao inválido: {sessao_selecao!r} (esperado SessaoSelecao ou None)")
    if motor_visivel is not None and not isinstance(motor_visivel, bool):
        raise ValueError(f"motor_visivel inválido: {motor_visivel!r} (esperado bool ou None)")
    _validar_profundidade_corte(profundidade_corte)
    if isinstance(faixas, bool) or not isinstance(faixas, int) or faixas < 1:
        raise ValueError(f"número de faixas inválido: {faixas!r}")
    if ocultar_secundarias:
        cats = tuple(dict.fromkeys((*categorias_ocultas, *selecao.CATEGORIAS_PADRAO_PLANTA_OCULTAS)))
    else:
        cats = tuple(categorias_ocultas)
    selecao._validar_categorias(ifc, cats)

    info = vistas_ifc.ler_vista(ifc, gid_vista)
    if info.get("tipo") != "CORTE":
        raise SelecaoInvalida(f"Vista {gid_vista} não é do tipo CORTE (tipo={info.get('tipo')})")

    scale = float(ifcopenshell.util.unit.calculate_unit_scale(ifc))
    if caminho_ifc is None:
        arq_cache, sig_chave = None, None
    elif assinatura_ifc is not None:
        arq_cache, sig_chave = Path(caminho_ifc), tuple(int(x) for x in assinatura_ifc)
    else:
        arq_cache, sig_chave = resolver_assinatura(caminho_ifc)

    tentativas = (
        ((arq_cache, sig_chave), (None, None))
        if (arq_cache is not None and sig_chave is not None)
        else ((None, None),)
    )
    for idx, (caminho_atual, sig_atual) in enumerate(tentativas):
        try:
            return _gerar_corte_uma_vez(
                ifc, gid_vista, cats, scale, threads, limite_triangulos, limite_s,
                cancelar, executor, caminho_atual, sig_atual, moveis_caixa2d, profundidade_corte,
                faixas, cache, motor_visivel, sessao_selecao,
                filho if caminho_atual is not None else None,
            )
        except auxiliar.Divergente:
            if idx + 1 >= len(tentativas):
                raise
    raise AssertionError("unreachable")
