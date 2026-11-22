# SPDX-License-Identifier: AGPL-3.0-or-later
"""Refino das peças pesadas de um desenho, uma a uma (ADR-004: sem geometria no app)."""
from __future__ import annotations

from pathlib import Path

import obim_geometria.pecas as pecas

from openbim_app.desenho import auxiliar
from openbim_app.desenho.cache import CacheCancelado, assinatura_arquivo, resolver_assinatura

_VERSAO_REFINO = "visibilidade-v1"


def _erro(exc: Exception) -> str:
    if isinstance(exc, auxiliar.FalhaNoAuxiliar):
        return f"{exc.tipo}: {exc.mensagem}"
    return f"{type(exc).__name__}: {exc}"


def _chave_cache(cache, ifc, pedido_peca: dict, cancelar=None, *, arquivo=None, assinatura=None) -> str | None:
    if cache is None:
        return None
    kw_chave = {"arquivo": arquivo, "assinatura": assinatura} if (arquivo is not None and assinatura is not None) else {}
    try:
        return cache.chave(
            ifc,
            {**pedido_peca, "motor": "auto", "versao_refino": _VERSAO_REFINO},
            cancelar=cancelar,
            **kw_chave,
        )
    except CacheCancelado as exc:
        raise auxiliar.DesenhoCancelado("Operação cancelada no cálculo da chave do cache") from exc


def _refinar_uma(ifc, pedido_peca: dict, ident, *, executor, limite_s: float, cancelar) -> dict:
    with auxiliar.preparar(ifc, pedido_peca) as preparado:
        interrompido: list[auxiliar.ErroAuxiliar] = []

        def _exec(q_op: dict) -> dict:
            if interrompido:
                exc = interrompido[0]
                return {"ok": False, "erro": {"tipo": type(exc).__name__, "mensagem": str(exc), "rastro": ""}}
            prep_op = auxiliar.Preparado(q_op, preparado.pasta, preparado.copia_s)
            try:
                return auxiliar.executar(
                    prep_op,
                    limite_s=limite_s,
                    cancelar=cancelar,
                    executor=executor,
                )
            except (auxiliar.DesenhoCancelado, auxiliar.AuxiliarEstourouTempo) as exc:
                interrompido.append(exc)
                raise
            except auxiliar.FalhaNoAuxiliar as exc:
                return {"ok": False, "erro": {"tipo": exc.tipo, "mensagem": exc.mensagem, "rastro": exc.rastro}}

        resp = pecas.refinar_peca(preparado.pedido, ident, executor=_exec, limite_s=limite_s)
        if interrompido:
            raise interrompido[0]
        return resp


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
    caminho_ifc=None,
    assinatura_ifc: tuple[int, int] | None = None,
) -> dict:
    """Troca as silhuetas das peças pesadas pelo exato, na ordem crescente de faces."""
    out = dict(resultado)
    pesados = resultado.get("pesados") or []
    if not pesados:
        return out

    if caminho_ifc is None:
        arquivo_cache, sig_inicial = None, None
    elif assinatura_ifc is not None:
        arquivo_cache, sig_inicial = Path(caminho_ifc), tuple(int(x) for x in assinatura_ifc)
    else:
        arquivo_cache, sig_inicial = resolver_assinatura(caminho_ifc)
    svg = resultado.get("svg") or ""
    refinadas: list[str] = []
    em_cache: list[str] = []
    falhas: list[dict] = []
    motores: dict[str, str] = {}
    motivos_hlr: dict[str, str] = {}
    ordenados = sorted(pesados, key=lambda d: d.get("faces", 0))
    total = len(ordenados)

    for n, peca in enumerate(ordenados, 1):
        if cancelar is not None and cancelar.is_set():
            raise auxiliar.DesenhoCancelado("Operação cancelada antes de refinar a peça")
        guid, ident = peca["guid"], peca["id"]
        pedido_peca = pecas.pedido_peca(pedido, ident)
        usou_arquivo = arquivo_cache is not None and sig_inicial is not None
        chave = _chave_cache(
            cache,
            ifc,
            pedido_peca,
            cancelar=cancelar,
            arquivo=arquivo_cache if usou_arquivo else None,
            assinatura=sig_inicial if usou_arquivo else None,
        )
        dados = cache.obter(chave) if chave is not None else None
        grupo = None
        motor_usado = None
        motivo_hlr = None
        if dados is not None and dados.get("motor") in ("visibilidade", "hlr"):
            grupo = dados.get("grupo") or dados.get("svg")
            motor_usado = dados["motor"]
            motivo_hlr = dados.get("motivo_hlr")
        de_cache = grupo is not None
        if not de_cache:
            try:
                resp = _refinar_uma(
                    ifc,
                    pedido_peca,
                    ident,
                    executor=executor,
                    limite_s=limite_s,
                    cancelar=cancelar,
                )
                if not resp.get("ok") or not resp.get("grupo"):
                    raise RuntimeError(resp.get("erro") or f"peça {guid} falhou no refino")
                grupo = resp["grupo"]
                motor_usado = resp.get("motor") or "hlr"
                motivo_hlr = resp.get("motivo_hlr")
            except auxiliar.DesenhoCancelado:
                raise
            except Exception as exc:
                falhas.append({"guid": guid, "erro": _erro(exc)})
                if progresso is not None:
                    progresso(f"peça {n}/{total} falhou: {guid}")
                continue
            if cache is not None and chave is not None:
                if cancelar is not None and cancelar.is_set():
                    raise auxiliar.DesenhoCancelado("Operação cancelada antes de gravar no cache")
                if not usou_arquivo or assinatura_arquivo(arquivo_cache) == sig_inicial:
                    entrada_cache = {"svg": grupo, "grupo": grupo, "motor": motor_usado}
                    if motivo_hlr is not None:
                        entrada_cache["motivo_hlr"] = motivo_hlr
                    cache.guardar(chave, entrada_cache)
        svg = pecas.mesclar_pesado(svg, guid, grupo)
        refinadas.append(guid)
        motores[guid] = motor_usado
        if motivo_hlr is not None:
            motivos_hlr[guid] = motivo_hlr
        if de_cache:
            em_cache.append(guid)
        if progresso is not None:
            progresso(f"peça {n}/{total} refinada ({motor_usado}): {guid}")
        if ao_refinar is not None:
            ao_refinar(svg, guid)

    out["svg"] = svg
    out["refinadas"] = refinadas
    out["em_cache"] = em_cache
    out["falhas_refino"] = falhas
    out["motores"] = motores
    out["motivos_hlr"] = motivos_hlr
    return out
