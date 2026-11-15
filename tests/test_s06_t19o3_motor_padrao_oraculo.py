# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo F0-S06-T19o3: o app liga o motor de visibilidade por padrão na planta (T3, PO aprovou em 15/11 após ver as imagens). Cartão: docs/state/cards/F0-S06/F0-S06-T19o3-motor-padrao.md. Não editar nesta tarefa.
CONTRATO:
1. `planta.gerar_planta(..., motor_visivel: bool | None = None)`: só por nome, depois de `componentes`. None/False: pedido SEM a chave `motor_visivel`; True: `pedido["motor_visivel"] = True`. Não-bool (e não None) -> ValueError antes do executor.
2. `gerente._motor_padrao` (planta): `gerar_planta(..., motor_visivel=True)` por padrão; a opção do chamador (`motor_visivel=False`) prevalece. Corte não recebe a chave."""
import inspect
import threading
from types import SimpleNamespace

import pytest
from s06_t17_aux import ExecutorEspiao, Pl, modelo


def test_assinatura_e_pedido():
    assert inspect.signature(Pl.gerar_planta).parameters["motor_visivel"].default is None
    f, _g, gid = modelo()
    for valor, esperado in ((None, False), (False, False), (True, True)):
        ex = ExecutorEspiao()
        Pl.gerar_planta(f, gid, executor=ex, **({} if valor is None else {"motor_visivel": valor}))
        assert ("motor_visivel" in ex.pedidos_desenho[0]) is esperado
        if esperado:
            assert ex.pedidos_desenho[0]["motor_visivel"] is True


@pytest.mark.parametrize("ruim", [1, "sim", 0.5])
def test_rejeita_nao_bool(ruim):
    f, _g, gid = modelo()
    ex = ExecutorEspiao()
    with pytest.raises(ValueError):
        Pl.gerar_planta(f, gid, executor=ex, motor_visivel=ruim)
    assert not ex.pedidos_desenho


def _falso(monkeypatch):
    from openbim_app.desenho import planta as pmod

    est = SimpleNamespace(gerar=[])

    def gerar_planta(ifc, guid, **kw):
        est.gerar.append(kw)
        return SimpleNamespace(svg="<svg/>", n_paths=0, tempos={}, caixas=(), em_cache=(), pesados=(), pedido={})

    monkeypatch.setattr(pmod, "gerar_planta", gerar_planta)
    return est


def test_motor_padrao_liga_o_motor_e_o_chamador_desliga(monkeypatch):
    from openbim_app.desenho import corte as cmod
    from openbim_app.desenho import gerente as gmod

    est = _falso(monkeypatch)
    comum = dict(cancelar=threading.Event(), progresso=lambda m: None, cache=None)
    gmod._motor_padrao("planta", "IFC", "V", {}, **comum)
    gmod._motor_padrao("planta", "IFC", "V", {"motor_visivel": False}, **comum)
    assert est.gerar[0]["motor_visivel"] is True and est.gerar[1]["motor_visivel"] is False
    vistos = {}

    def gerar_corte(ifc, guid, **kw):
        vistos.update(kw)
        return SimpleNamespace(svg="<svg/>", n_paths=0, tempos={}, caixas=(), em_cache=())

    monkeypatch.setattr(cmod, "gerar_corte", gerar_corte)
    gmod._motor_padrao("corte", "IFC", "V", {}, **comum)
    assert "motor_visivel" not in vistos
