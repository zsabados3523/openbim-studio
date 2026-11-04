# SPDX-License-Identifier: AGPL-3.0-or-later
"""Cálculo de caixas envolventes (bbox) de produtos IFC em metros (mundo)."""
import math
import traceback

import ifcopenshell
import ifcopenshell.geom
from obim_geometria import nucleos


class ArvoreCaixas:
    """Consulta de caixas envolventes por interseção fechada. A busca é linear: só o
    contrato de resultado importa (a poda espacial fica para a T07c)."""

    def __init__(self, caixas: dict):
        self._itens = []
        for chave, bruta in caixas.items():
            try:
                c = [float(v) for v in bruta]
            except (TypeError, ValueError) as e:
                raise ValueError(f"Caixa inválida para {chave!r}: {bruta!r}") from e
            if len(c) != 6 or not all(math.isfinite(v) for v in c):
                raise ValueError(f"Caixa inválida para {chave!r}: {bruta!r}")
            if c[0] > c[3] or c[1] > c[4] or c[2] > c[5]:
                raise ValueError(f"Caixa com mínimo maior que máximo para {chave!r}: {bruta!r}")
            self._itens.append((int(chave), c))

    def __len__(self) -> int:
        return len(self._itens)

    def cruzando(self, minimo, maximo) -> list[int]:
        lo, hi = [float(v) for v in minimo], [float(v) for v in maximo]
        if len(lo) != 3 or len(hi) != 3 or not all(math.isfinite(v) for v in lo + hi):
            raise ValueError(f"Consulta inválida: {minimo!r}, {maximo!r}")
        if lo[0] > hi[0] or lo[1] > hi[1] or lo[2] > hi[2]:
            raise ValueError(f"Consulta com mínimo maior que máximo: {minimo!r}, {maximo!r}")
        return sorted(
            chave
            for chave, c in self._itens
            if c[0] <= hi[0] and c[3] >= lo[0]
            and c[1] <= hi[1] and c[4] >= lo[1]
            and c[2] <= hi[2] and c[5] >= lo[2]
        )


def _caixa(shape) -> list[float] | None:
    verts = shape.geometry.verts if shape else None
    if not verts:
        return None
    xs, ys, zs = verts[0::3], verts[1::3], verts[2::3]
    return [float(min(xs)), float(min(ys)), float(min(zs)),
            float(max(xs)), float(max(ys)), float(max(zs))]


def processar(pedido: dict) -> dict:
    try:
        threads = nucleos.limitar_threads(pedido.get("threads"))
        f = ifcopenshell.open(pedido.get("arquivo"))
        elementos = pedido.get("elementos", [])
        for id_step, guid in elementos:
            try:
                el = f.by_id(id_step)
            except Exception:
                el = None
            if el is None or getattr(el, "GlobalId", None) != guid:
                return {"ok": False, "erro": {"tipo": "ArquivoDivergente", "mensagem": f"ID {id_step} diverge do arquivo", "rastro": ""}}

        if not elementos:
            return {"ok": True, "caixas_envolventes": {}, "falhas_geometria": [], "passagens_iterator": 0, "erros_iterator": []}

        s = ifcopenshell.geom.settings()
        s.set(s.USE_WORLD_COORDS, True)
        caixas: dict[str, list[float]] = {}
        visitados: set[int] = set()
        erros: list[dict] = []
        erros_multi: list[dict] = []
        passagens = 0

        def passagem(sub):
            nonlocal passagens
            passagens += 1
            it = ifcopenshell.geom.iterator(s, f, threads, include=[f.by_id(i) for i, _ in sub])
            if not it.initialize():
                return False, 0, None
            progresso, abortada, id_falha = 0, False, None

            def _falha(e):
                nonlocal id_falha, abortada
                if len(sub) == 1:
                    id_falha = int(sub[0][0])
                    erros.append({"tipo": type(e).__name__, "mensagem": str(e), "ids": [id_falha]})
                else:
                    erros_multi.append({"tipo": type(e).__name__, "mensagem": str(e)})
                abortada = True

            while True:
                try:
                    shape = it.get()
                except Exception as e:
                    _falha(e)
                    break
                if shape is not None:
                    visitados.add(int(shape.id))
                    progresso += 1
                    caixa = _caixa(shape)
                    if caixa is not None:
                        caixas[str(shape.id)] = caixa
                try:
                    if not it.next():
                        break
                except Exception as e:
                    _falha(e)
                    break
            return abortada, progresso, id_falha

        restantes = list(elementos)
        while restantes:
            abortada, progresso, id_falha = passagem(restantes)
            if not abortada:
                break
            if id_falha is not None:
                visitados.add(id_falha)
            restantes = [e for e in restantes if int(e[0]) not in visitados]
            if not restantes:
                break
            if progresso or id_falha is not None:
                continue
            for elem in list(restantes):
                sub_abortada, _, sub_falha = passagem([elem])
                if sub_abortada:
                    visitados.add(sub_falha if sub_falha is not None else int(elem[0]))
                    break
            restantes = [e for e in restantes if int(e[0]) not in visitados]

        falhas = [id_step for id_step, _ in elementos if str(id_step) not in caixas]
        if not erros:
            erros.extend(erros_multi)
        return {"ok": True, "caixas_envolventes": caixas, "falhas_geometria": falhas,
                "passagens_iterator": passagens, "erros_iterator": erros}
    except Exception as e:
        return {"ok": False, "erro": {"tipo": type(e).__name__, "mensagem": str(e), "rastro": traceback.format_exc()}}
