# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oraculo complementar F0-S06-T24b (rodada 2): provas dos achados 1 e 2.

Cobre:
1. `componentes=True` (e `faixas=2`) com queda (gancho ou `cache_incompleto`):
   - gancho chamado no maximo 1 vez (ou 0 em `cache_incompleto`) e `_tentar_planta_pelo_cache` so 1 vez;
   - `pasta_cache_geometria` ausente nos lotes e sub-pedidos enviados aos filhos;
   - SVG final 100% do motor HLR, sem mistura com SVG do cache;
   - telemetria de queda preservada sem mutar o `pedido` do chamador.
2. Gancho retornando `ok=False` (ou `ok` nao-booleano `True`) com `motivo=None` cai como `"erro_motor"`.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from types import SimpleNamespace

import ifcopenshell
import ifcopenshell.api
import numpy as np
import pytest

from obim_geometria import cache_geometria as C
from obim_geometria import construtor, desenho, faixas


def _parede(f, body, pos: tuple[float, float, float]):
    api = ifcopenshell.api.run
    el = api("root.create_entity", f, ifc_class="IfcWall")
    rep = api("geometry.add_wall_representation", f, context=body, length=2.0, height=2.8, thickness=0.2)
    el.Representation = f.createIfcProductDefinitionShape(Representations=[rep])
    m = np.eye(4)
    m[:3, 3] = pos
    api("geometry.edit_object_placement", f, product=el, matrix=m, is_si=False)
    return el


def _criar_cena_3_componentes(tmp_path: Path) -> SimpleNamespace:
    api = ifcopenshell.api.run
    f = api("project.create_file", version="IFC4")
    proj = api("root.create_entity", f, ifc_class="IfcProject")
    api("unit.assign_unit", f, units=[f.createIfcSIUnit(UnitType="LENGTHUNIT", Prefix=None, Name="METRE")])
    ctx = api("context.add_context", f, context_type="Model")
    body = api("context.add_context", f, context_type="Model", context_identifier="Body", target_view="MODEL_VIEW", parent=ctx)
    site = api("root.create_entity", f, ifc_class="IfcSite")
    predio = api("root.create_entity", f, ifc_class="IfcBuilding")
    andar = api("root.create_entity", f, ifc_class="IfcBuildingStorey", name="Terreo")
    andar.Elevation = 0.0
    for filho, pai in ((site, proj), (predio, site), (andar, predio)):
        api("aggregate.assign_object", f, products=[filho], relating_object=pai)

    p1 = _parede(f, body, (0.0, 0.0, 0.0))
    p2 = _parede(f, body, (20.0, 0.0, 0.0))
    p3 = _parede(f, body, (40.0, 0.0, 0.0))
    api("spatial.assign_container", f, products=[p1, p2, p3], relating_structure=andar)

    arq = tmp_path / "tres_componentes.ifc"
    f.write(str(arq))
    f = ifcopenshell.open(str(arq))
    andar = f.by_guid(andar.GlobalId)
    p1, p2, p3 = f.by_guid(p1.GlobalId), f.by_guid(p2.GlobalId), f.by_guid(p3.GlobalId)

    pasta = tmp_path / "cache_geo"
    doc = construtor.documento_de(arq)
    with construtor.abrir_banco(pasta) as cache:
        r = construtor.construir_lote(f, cache, construtor.fila_inicial(f), documento=doc, assinatura="s1", memo={})
        assert r["falhas"] == 0 and r["gravadas"] == 3

    vista = {"tipo": "PLANTA", "pavimento": andar.GlobalId, "escala": 1.0, "altura_corte_m": 1.2}
    elementos = [(e.id(), e.GlobalId) for e in (p1, p2, p3)]
    pedido_base = {"arquivo": str(arq), "vista": vista, "elementos": elementos, "threads": 1}
    return SimpleNamespace(
        arq=arq, pasta=pasta, andar=andar, p1=p1, p2=p2, p3=p3,
        pedido_base=pedido_base,
        pedido_comp={**pedido_base, "componentes": True},
        pedido_cache_comp={**pedido_base, "componentes": True, "pasta_cache_geometria": str(pasta)},
    )


def _svg_sentinela_cache(elementos_validos) -> dict:
    grupos = "".join(
        f'<g class="IfcWall" ifc:guid="{gid}" data-do-cache="1"><path d="M 0,0 L 1,0"/></g>'
        for _, gid in elementos_validos
    )
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" xmlns:ifc="http://www.ifcopenshell.org/ns" viewBox="0 0 1 1">'
        f"{grupos}</svg>"
    )
    return {
        "ok": True,
        "svg": svg,
        "n_paths": len(elementos_validos),
        "enviados": [int(i) for i, _ in elementos_validos],
        "caixas": [],
        "em_cache": [],
        "pesados": [],
        "falhas_geometria": [],
        "tempos": {"abrir_s": 0.0, "geo_s": 0.0, "write_s": 0.0, "finalize_s": 0.0, "motor_s": 0.01},
    }


def _instalar_filho_inprocess(monkeypatch):
    lotes_vistos = []
    sub_pedidos = []

    def rodar_inprocess(pedido_filho: dict, limite_s: float | None = None) -> dict:
        lotes_vistos.append(dict(pedido_filho))
        if pedido_filho.get("op") == "desenho_lote":
            for q in pedido_filho.get("pedidos") or ():
                sub_pedidos.append(dict(q))
            return desenho.processar_lote(pedido_filho)
        sub_pedidos.append(dict(pedido_filho))
        return desenho.processar(pedido_filho)

    monkeypatch.setattr(faixas, "rodar_filho", rodar_inprocess)
    return lotes_vistos, sub_pedidos


def test_componentes_queda_no_gancho_chama_so_uma_vez_sem_mistura(tmp_path, monkeypatch):
    cena = _criar_cena_3_componentes(tmp_path)
    lotes_vistos, sub_pedidos = _instalar_filho_inprocess(monkeypatch)
    base_comp = desenho.processar(cena.pedido_comp)
    assert base_comp["ok"] is True and base_comp["grupos"] == 3
    lotes_vistos.clear()
    sub_pedidos.clear()

    tentativas = []
    real_tentar = desenho._tentar_planta_pelo_cache

    def espiar_tentar(f, pedido, pasta_cache, fase, abrir_s):
        tentativas.append(len(pedido.get("elementos") or ()))
        return real_tentar(f, pedido, pasta_cache, fase, abrir_s)

    monkeypatch.setattr(desenho, "_tentar_planta_pelo_cache", espiar_tentar)

    chamadas_gancho = []

    def gancho(f, pedido, malhas_mundo, elementos_validos, fase, abrir_s):
        chamadas_gancho.append(len(elementos_validos))
        if len(chamadas_gancho) == 1:
            return None, "secao_aberta"
        return _svg_sentinela_cache(elementos_validos), None

    monkeypatch.setattr(desenho, "_desenhar_planta_cache", gancho)

    pedido = dict(cena.pedido_cache_comp)
    resp = desenho.processar(pedido)

    assert resp["ok"] is True
    assert resp["via_cache"] is False
    assert resp["queda"] == "secao_aberta"
    assert resp["n_faltantes"] == 0
    assert resp["grupos"] == 3
    assert resp["tempos"]["cache_s"] >= 0.0 and resp["tempos"]["motor_s"] >= 0.0
    assert "faltantes" not in resp and "incompleta" not in resp
    assert chamadas_gancho == [3]
    assert tentativas == [3]
    assert len(sub_pedidos) == 3
    assert all("pasta_cache_geometria" not in l for l in lotes_vistos)
    assert all("pasta_cache_geometria" not in q for q in sub_pedidos)
    assert "data-do-cache" not in resp["svg"]
    assert resp["svg"] == base_comp["svg"]
    assert pedido["pasta_cache_geometria"] == str(cena.pasta)


def test_componentes_queda_cache_incompleto_nao_reabre_cache_nem_mistura_svg(tmp_path, monkeypatch):
    cena = _criar_cena_3_componentes(tmp_path)
    lotes_vistos, sub_pedidos = _instalar_filho_inprocess(monkeypatch)
    base_comp = desenho.processar(cena.pedido_comp)
    assert base_comp["ok"] is True and base_comp["grupos"] == 3
    lotes_vistos.clear()
    sub_pedidos.clear()

    con = sqlite3.connect(str(cena.pasta / C.NOME_BANCO))
    try:
        con.execute("DELETE FROM ocorrencias WHERE global_id = ?", (cena.p3.GlobalId,))
        con.commit()
    finally:
        con.close()

    tentativas = []
    real_tentar = desenho._tentar_planta_pelo_cache
    monkeypatch.setattr(
        desenho,
        "_tentar_planta_pelo_cache",
        lambda f, p, pc, fase, a: (tentativas.append(len(p.get("elementos") or ())), real_tentar(f, p, pc, fase, a))[1],
    )
    chamadas_gancho = []
    monkeypatch.setattr(
        desenho,
        "_desenhar_planta_cache",
        lambda f, p, m, ev, fase, a: (chamadas_gancho.append(len(ev)), (_svg_sentinela_cache(ev), None))[1],
    )

    resp = desenho.processar({**cena.pedido_comp, "pasta_cache_geometria": cena.pasta})

    assert resp["ok"] is True
    assert resp["via_cache"] is False
    assert resp["queda"] == "cache_incompleto"
    assert resp["n_faltantes"] == 1
    assert resp["grupos"] == 3
    assert "faltantes" not in resp and "incompleta" not in resp
    assert chamadas_gancho == []
    assert tentativas == [3]
    assert len(sub_pedidos) == 3
    assert all("pasta_cache_geometria" not in l for l in lotes_vistos)
    assert all("pasta_cache_geometria" not in q for q in sub_pedidos)
    assert "data-do-cache" not in resp["svg"]
    assert resp["svg"] == base_comp["svg"]


def test_faixas_queda_remove_pasta_cache_dos_sub_pedidos_e_anexa_telemetria(tmp_path, monkeypatch):
    cena = _criar_cena_3_componentes(tmp_path)
    lotes_vistos, sub_pedidos = _instalar_filho_inprocess(monkeypatch)
    chamadas_gancho = []
    monkeypatch.setattr(
        desenho,
        "_desenhar_planta_cache",
        lambda f, p, m, ev, fase, a: (
            chamadas_gancho.append(len(ev)),
            (None, "malha_invalida") if len(chamadas_gancho) == 1 else (_svg_sentinela_cache(ev), None),
        )[1],
    )

    resp = desenho.processar({**cena.pedido_base, "faixas": 2, "pasta_cache_geometria": cena.pasta})

    assert resp["ok"] is True
    assert resp["via_cache"] is False
    assert resp["queda"] == "malha_invalida"
    assert resp["n_faltantes"] == 0
    assert resp["tempos"]["cache_s"] >= 0.0 and resp["tempos"]["motor_s"] >= 0.0
    assert resp["tempos"]["n_faixas"] == 2
    assert chamadas_gancho == [3]
    assert len(sub_pedidos) == 2
    assert all("pasta_cache_geometria" not in q for q in sub_pedidos)
    assert "data-do-cache" not in resp["svg"]


@pytest.mark.parametrize(
    "retorno_gancho,queda_esperada",
    [
        ({"ok": False, "erro": {"tipo": "X"}}, "erro_motor"),
        ({"ok": 1, "svg": "<svg/>"}, "erro_motor"),
        ({"ok": None, "svg": "<svg/>"}, "erro_motor"),
    ],
)
def test_gancho_ok_falso_ou_nao_bool_com_motivo_none_cai_como_erro_motor(
    tmp_path, monkeypatch, retorno_gancho, queda_esperada
):
    cena = _criar_cena_3_componentes(tmp_path)
    base = desenho.processar(cena.pedido_base)
    assert base["ok"] is True

    chamadas = []
    monkeypatch.setattr(
        desenho,
        "_desenhar_planta_cache",
        lambda *a: (chamadas.append(a), (dict(retorno_gancho), None))[1],
    )

    resp = desenho.processar({**cena.pedido_base, "pasta_cache_geometria": str(cena.pasta)})

    assert resp["ok"] is True
    assert resp["via_cache"] is False
    assert resp["queda"] == queda_esperada
    assert resp["n_faltantes"] == 0
    assert resp["tempos"]["cache_s"] >= 0.0 and resp["tempos"]["motor_s"] >= 0.0
    assert "erro" not in resp and "faltantes" not in resp and "incompleta" not in resp
    assert len(chamadas) == 1
    assert resp["svg"] == base["svg"]


def test_gancho_ok_falso_com_motivo_valido_preserva_motivo(tmp_path, monkeypatch):
    cena = _criar_cena_3_componentes(tmp_path)
    base = desenho.processar(cena.pedido_base)
    monkeypatch.setattr(
        desenho,
        "_desenhar_planta_cache",
        lambda *a: ({"ok": False, "erro": {"tipo": "X"}}, "secao_aberta"),
    )

    resp = desenho.processar({**cena.pedido_base, "pasta_cache_geometria": str(cena.pasta)})

    assert resp["ok"] is True
    assert resp["via_cache"] is False
    assert resp["queda"] == "secao_aberta"
    assert resp["n_faltantes"] == 0
    assert resp["svg"] == base["svg"]
