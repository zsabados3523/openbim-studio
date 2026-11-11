# SPDX-License-Identifier: AGPL-3.0-or-later
"""Refino das peças pesadas de um desenho, uma a uma (ADR-004: sem geometria no app)."""
from __future__ import annotations

from obim_geometria.processo import pecas

from openbim_app.desenho import auxiliar


def _erro(exc: Exception) -> str:
    if isinstance(exc, auxiliar.FalhaNoAuxiliar):
        return f"{exc.tipo}: {exc.mensagem}"
    return f"{type(exc).__name__}: {exc}"


def refinar_pesados(
    ifc,
    pedido: dict,
    resultado: dict,
    *,
    executor=None,
    cache=None,
    cancelar=None,
    progresso=None,
    ao_refinar=None,
    limite_s: float = 3600.0,
) -> dict:
    """Troca as silhuetas das peças pesadas pelo exato, na ordem crescente de faces."""
    out = dict(resultado)
    pesados = resultado.get("pesados") or []
    if not pesados:
        return out

    svg = resultado.get("svg") or ""
    refinadas: list[str] = []
    em_cache: list[str] = []
    falhas: list[dict] = []
    ordenados = sorted(pesados, key=lambda d: d.get("faces", 0))
    total = len(ordenados)

    for n, peca in enumerate(ordenados, 1):
        if cancelar is not None and cancelar.is_set():
            raise auxiliar.DesenhoCancelado("Operação cancelada antes de refinar a peça")
        guid, ident = peca["guid"], peca["id"]
        pedido_peca = pecas.pedido_peca(pedido, ident)
        chave = cache.chave(ifc, pedido_peca) if cache is not None else None
        dados = cache.obter(chave) if chave is not None else None
        grupo = None
        if dados is not None:
            grupo = dados.get("grupo") or dados.get("svg")
        de_cache = grupo is not None
        if not de_cache:
            try:
                with auxiliar.preparar(ifc, pedido_peca) as preparado:
                    r = auxiliar.executar(
                        preparado,
                        limite_s=limite_s,
                        cancelar=cancelar,
                        executor=executor,
                    )
                grupo = pecas.extrair_grupo(r.get("svg") or "", guid)
                if grupo is None:
                    raise ValueError(f"peça {guid} ausente no SVG da peça")
            except auxiliar.DesenhoCancelado:
                raise
            except Exception as exc:
                falhas.append({"guid": guid, "erro": _erro(exc)})
                if progresso is not None:
                    progresso(f"peça {n}/{total} falhou: {guid}")
                continue
            if cache is not None and chave is not None:
                cache.guardar(chave, {"svg": grupo, "grupo": grupo})
        svg = pecas.mesclar_pesado(svg, guid, grupo)
        refinadas.append(guid)
        if de_cache:
            em_cache.append(guid)
        if progresso is not None:
            progresso(f"peça {n}/{total} refinada: {guid}")
        if ao_refinar is not None:
            ao_refinar(svg, guid)

    out["svg"] = svg
    out["refinadas"] = refinadas
    out["em_cache"] = em_cache
    out["falhas_refino"] = falhas
    return out
