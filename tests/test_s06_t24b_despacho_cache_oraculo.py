# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oraculo F0-S06-T24b (ADR-010, P3): despacho da planta pelo cache, queda e telemetria.

Modulo alvo (o implementador NAO edita este arquivo; somente `geometria/obim_geometria/desenho.py`):
- Despacho em `desenho.processar(pedido, fase=None) -> dict`: DEPOIS de `_conferir_assinatura`,
  `_abrir_ifc`, `_sem_rastro(f)` e `_conferir_elementos`; ANTES de `n_faixas` (`_planta_em_faixas`),
  `componentes` (`_planta_por_componentes`) e `_processar_base`.

Interface fixa da T24b:
1. Chave `pedido["pasta_cache_geometria"]` (`str | Path | None`):
   - Ausente, `None` ou `""`, ou `vista.tipo == "CORTE"`, ou `pedido.get("faixa") is not None`:
     NAO entra no despacho pelo cache; resposta e chaves identicas as de hoje (sem `via_cache`,
     `queda`, `n_faltantes`, `tempos["cache_s"]`; 0 chamadas a `malhas_do_cache` e ao gancho;
     nenhum SQLite criado).
2. Gancho espiavel via monkeypatch:
   `desenho._desenhar_planta_cache(f, pedido, malhas_mundo, elementos_validos, fase, abrir_s) -> tuple[dict | None, str | None]`
   - `malhas_mundo`: saida de `cache_leitura.malhas_do_cache(cache, documento_de(arquivo), global_ids_esperados)`.
   - `elementos_validos`: pares `(id_step, guid)` de `pedido["elementos"]` sem `IfcOpeningElement`
     e sem elementos com `Representation is None` (alinhado a `construtor.fila_inicial`).
   - Retorno `(resp_ok, None)` -> sucesso (`via_cache=True`, `queda=None`, `n_faltantes=0`);
     `(None, motivo)` ou excecao -> queda do pavimento inteiro (`via_cache=False`; motivo invalido,
     vazio ou excecao vira `"erro_motor"`). Stub padrao T24b devolve queda `"erro_motor"` (ou
     `NotImplementedError` tratado como `"erro_motor"`).
3. Abertura segura do banco:
   - NUNCA chama `construtor.abrir_banco`, NUNCA chama `limpar()`, NUNCA cria pasta/arquivo SQLite
     quando `Path(pasta) / cache_geometria.NOME_BANCO` nao existe, NUNCA apaga/recria banco existente.
   - Valida integridade/esquema e cabecalho `cache_geometria.cabecalho_atual(tesselacao=construtor.TESSELACAO)`.
   - Permite a `malhas_do_cache` apagar apenas forma corrompida (`apagar_forma(somente_corrompida=True)`).
4. Telemetria (sempre presente quando o despacho pelo cache foi tentado):
   - `via_cache: bool`, `queda: str | None`, `n_faltantes: int`, `tempos["cache_s"]: float`,
     `tempos["motor_s"]: float` (>= 0.0). NUNCA sobrescrever `resp["faltantes"]` nem `incompleta` (T19i1).
5. Tabela fechada de motivos de `queda` (`n_faltantes`):
   `None` (`0`), `"sem_arquivo_salvo"` (`len(elementos_validos)`), `"opcoes_incompativeis"` (`0`),
   `"cache_ausente"` (`len(elementos_validos)`), `"cache_invalido"` (`len(elementos_validos)`),
   `"cache_incompleto"` (`len(faltantes)`), `"malha_invalida"` (`0`), `"secao_aberta"` (`0`),
   `"erro_motor"` (`0`).

Mutantes 1-11 da ESPEC_T24bcde.md §3.1; IFC sintetico em `tmp_path` e banco via `construtor.construir_lote`.
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
from obim_geometria import cache_leitura, construtor, desenho

MOTIVOS_QUEDA = frozenset({
    "sem_arquivo_salvo", "opcoes_incompativeis", "cache_ausente", "cache_invalido",
    "cache_incompleto", "malha_invalida", "secao_aberta", "erro_motor",
})


def _caixa(f, body, classe: str, comp: float, esp: float, alt: float, pos: tuple[float, float, float]):
    api = ifcopenshell.api.run
    el = api("root.create_entity", f, ifc_class=classe)
    rep = api("geometry.add_wall_representation", f, context=body, length=comp, height=alt, thickness=esp)
    el.Representation = f.createIfcProductDefinitionShape(Representations=[rep])
    m = np.eye(4)
    m[:3, 3] = pos
    api("geometry.edit_object_placement", f, product=el, matrix=m, is_si=False)
    return el


def _criar_cena(tmp_path: Path, *, com_sem_rep: bool = False) -> SimpleNamespace:
    api = ifcopenshell.api.run
    f = api("project.create_file", version="IFC4")
    proj = api("root.create_entity", f, ifc_class="IfcProject")
    api("unit.assign_unit", f, units=[f.createIfcSIUnit(UnitType="LENGTHUNIT", Prefix=None, Name="METRE")])
    ctx = api("context.add_context", f, context_type="Model")
    body = api("context.add_context", f, context_type="Model", context_identifier="Body", target_view="MODEL_VIEW", parent=ctx)
    site, predio = api("root.create_entity", f, ifc_class="IfcSite"), api("root.create_entity", f, ifc_class="IfcBuilding")
    andar = api("root.create_entity", f, ifc_class="IfcBuildingStorey", name="Terreo")
    andar.Elevation = 0.0
    for filho, pai in ((site, proj), (predio, site), (andar, predio)):
        api("aggregate.assign_object", f, products=[filho], relating_object=pai)

    parede = _caixa(f, body, "IfcWall", 5.0, 0.2, 2.8, (0.0, 0.0, 0.0))
    abertura = _caixa(f, body, "IfcOpeningElement", 1.0, 0.5, 1.2, (2.0, -0.15, 0.8))
    api("feature.add_feature", f, feature=abertura, element=parede)
    laje = _caixa(f, body, "IfcSlab", 5.0, 4.0, 0.2, (0.0, 0.0, -0.2))
    movel = _caixa(f, body, "IfcFurnishingElement", 1.0, 0.8, 0.8, (1.0, 1.5, 0.0))
    api("spatial.assign_container", f, products=[parede, laje, movel], relating_structure=andar)
    sem_rep = None
    if com_sem_rep:
        sem_rep = api("root.create_entity", f, ifc_class="IfcBuildingElementProxy")
        api("spatial.assign_container", f, products=[sem_rep], relating_structure=andar)

    arq = tmp_path / "planta.ifc"
    f.write(str(arq))
    f = ifcopenshell.open(str(arq))
    andar, parede, abertura = f.by_guid(andar.GlobalId), f.by_guid(parede.GlobalId), f.by_guid(abertura.GlobalId)
    laje, movel = f.by_guid(laje.GlobalId), f.by_guid(movel.GlobalId)
    sem_rep = f.by_guid(sem_rep.GlobalId) if sem_rep is not None else None

    pasta = tmp_path / "cache_geo"
    doc = construtor.documento_de(arq)
    with construtor.abrir_banco(pasta) as cache:
        r = construtor.construir_lote(f, cache, construtor.fila_inicial(f), documento=doc, assinatura="s1", memo={})
        assert r["falhas"] == 0 and r["gravadas"] == 3

    validos = [parede, laje, movel]
    todos = [parede, abertura, laje, movel] + ([sem_rep] if sem_rep is not None else [])
    vista = {"tipo": "PLANTA", "pavimento": andar.GlobalId, "escala": 1.0, "altura_corte_m": 1.2}
    pedido_base = {"arquivo": str(arq), "vista": vista, "elementos": [(e.id(), e.GlobalId) for e in todos], "threads": 1}
    return SimpleNamespace(
        arq=arq, pasta=pasta, doc=doc, f=f, andar=andar, parede=parede, abertura=abertura, laje=laje, movel=movel,
        sem_rep=sem_rep, validos=validos, pedido_base=pedido_base,
        pedido_cache={**pedido_base, "pasta_cache_geometria": str(pasta)},
    )


def _pedido_corte(cena: SimpleNamespace, pasta: Path) -> dict:
    mat = [[1.0, 0.0, 0.0, 2.5], [0.0, 0.0, -1.0, -2.0], [0.0, 1.0, 0.0, 1.5], [0.0, 0.0, 0.0, 1.0]]
    vista = {
        "tipo": "CORTE", "guid": ifcopenshell.guid.new(), "nome": "C1", "escala": 1.0, "matriz": mat,
        "bloco": {"Location": [-5.0, -5.0, -10.0], "XLength": 12.0, "YLength": 10.0, "ZLength": 15.0},
    }
    return {
        "arquivo": str(cena.arq), "vista": vista, "elementos": list(cena.pedido_base["elementos"]),
        "threads": 1, "pasta_cache_geometria": str(pasta),
    }


def _resp_cache_ok(elementos_validos, *, motor_s: float | None = 0.015) -> dict:
    tempos = {"abrir_s": 0.0, "geo_s": 0.0, "write_s": 0.0, "finalize_s": 0.0}
    if motor_s is not None:
        tempos["motor_s"] = motor_s
    return {
        "ok": True, "svg": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1 1"><path d="M 0,0 L 1,0"/></svg>',
        "n_paths": 1, "enviados": [int(i) for i, _ in elementos_validos], "caixas": [], "em_cache": [],
        "pesados": [], "falhas_geometria": [], "tempos": tempos,
    }


def _sql(pasta: Path, consulta: str, args=()):
    con = sqlite3.connect(str(pasta / C.NOME_BANCO))
    try:
        rows = con.execute(consulta, args).fetchall()
        con.commit()
        return rows
    finally:
        con.close()


def _checar_telemetria(resp: dict, *, via_cache: bool, queda: str | None, n_faltantes: int):
    assert resp.get("ok") is True, resp
    assert resp["via_cache"] is via_cache
    assert resp["queda"] == queda
    assert resp["queda"] is None if via_cache else resp["queda"] in MOTIVOS_QUEDA
    assert type(resp["n_faltantes"]) is int and resp["n_faltantes"] == n_faltantes
    t = resp["tempos"]
    assert isinstance(t["cache_s"], float) and t["cache_s"] >= 0.0
    assert isinstance(t["motor_s"], float) and t["motor_s"] >= 0.0


def _espiar_gancho(monkeypatch, fn):
    chamadas = []

    def wrap(f, pedido, malhas_mundo, elementos_validos, fase, abrir_s):
        chamadas.append((f, pedido, malhas_mundo, elementos_validos, fase, abrir_s))
        return fn(f, pedido, malhas_mundo, elementos_validos, fase, abrir_s)

    monkeypatch.setattr(desenho, "_desenhar_planta_cache", wrap)
    return chamadas


def test_sem_pasta_cache_resposta_identica_a_hoje(tmp_path, monkeypatch):
    cena = _criar_cena(tmp_path)
    leituras, real_ler = [], cache_leitura.malhas_do_cache
    monkeypatch.setattr(cache_leitura, "malhas_do_cache", lambda *a, **k: (leituras.append(a), real_ler(*a, **k))[1])

    r0 = desenho.processar(cena.pedido_base)
    r_none = desenho.processar({**cena.pedido_base, "pasta_cache_geometria": None})
    r_vazio = desenho.processar({**cena.pedido_base, "pasta_cache_geometria": ""})

    chaves_raiz = {"ok", "svg", "n_paths", "enviados", "caixas", "em_cache", "pesados", "falhas_geometria", "tempos"}
    chaves_tempos = {"abrir_s", "geo_s", "write_s", "finalize_s"}
    for r in (r0, r_none, r_vazio):
        assert r["ok"] is True and set(r.keys()) == chaves_raiz and set(r["tempos"].keys()) == chaves_tempos
        assert r["svg"] == r0["svg"] and r["enviados"] == r0["enviados"] and r["falhas_geometria"] == []
    assert leituras == []


def test_sucesso_filtra_abertura_e_sem_representacao_e_telemetria(tmp_path, monkeypatch):  # mutantes 5, 3, 4
    cena = _criar_cena(tmp_path, com_sem_rep=True)
    chamadas = _espiar_gancho(monkeypatch, lambda f, p, m, ev, fase, a: (_resp_cache_ok(ev, motor_s=0.015), None))

    resp = desenho.processar(cena.pedido_cache)
    _checar_telemetria(resp, via_cache=True, queda=None, n_faltantes=0)
    assert resp["tempos"]["motor_s"] == pytest.approx(0.015)
    assert "faltantes" not in resp and "incompleta" not in resp and len(chamadas) == 1
    _f, _p, malhas, ev, _fase, abrir_s = chamadas[0]
    esperados = {e.GlobalId for e in cena.validos}
    assert set(malhas.keys()) == esperados and list(malhas.keys()) == sorted(esperados)
    assert cena.abertura.GlobalId not in malhas and cena.sem_rep.GlobalId not in malhas
    assert {(int(i), g) for i, g in ev} == {(e.id(), e.GlobalId) for e in cena.validos}
    assert isinstance(abrir_s, float) and abrir_s >= 0.0

    _espiar_gancho(monkeypatch, lambda f, p, m, ev, fase, a: (_resp_cache_ok(ev, motor_s=None), None))
    resp2 = desenho.processar({**cena.pedido_base, "pasta_cache_geometria": cena.pasta})
    _checar_telemetria(resp2, via_cache=True, queda=None, n_faltantes=0)


def test_cache_incompleto_nao_chama_gancho_e_cai_pavimento_inteiro(tmp_path, monkeypatch):  # mutantes 1, 2, 3, 4
    cena = _criar_cena(tmp_path)
    base = desenho.processar(cena.pedido_base)
    chamadas = _espiar_gancho(monkeypatch, lambda f, p, m, ev, fase, a: (_resp_cache_ok(ev), None))
    vistos_base, real_base = [], desenho._processar_base
    monkeypatch.setattr(desenho, "_processar_base", lambda p, *a, **k: (vistos_base.append(list(p["elementos"])), real_base(p, *a, **k))[1])

    _sql(cena.pasta, "DELETE FROM ocorrencias WHERE global_id = ?", (cena.movel.GlobalId,))
    r1 = desenho.processar(cena.pedido_cache)
    _checar_telemetria(r1, via_cache=False, queda="cache_incompleto", n_faltantes=1)
    assert chamadas == [] and "faltantes" not in r1 and "incompleta" not in r1
    assert vistos_base == [list(cena.pedido_base["elementos"])]
    assert r1["svg"] == base["svg"] and set(r1["enviados"]) == set(base["enviados"])

    [(chave_laje,)] = _sql(cena.pasta, "SELECT chave_forma FROM ocorrencias WHERE global_id = ?", (cena.laje.GlobalId,))
    _sql(cena.pasta, "DELETE FROM formas WHERE chave = ?", (chave_laje,))
    r2 = desenho.processar(cena.pedido_cache)
    _checar_telemetria(r2, via_cache=False, queda="cache_incompleto", n_faltantes=2)
    assert chamadas == [] and "faltantes" not in r2 and vistos_base[-1] == list(cena.pedido_base["elementos"])


@pytest.mark.parametrize("motivo_gancho,esperado", [
    ("malha_invalida", "malha_invalida"), ("secao_aberta", "secao_aberta"),
    ("erro_motor", "erro_motor"), (None, "erro_motor"), ("", "erro_motor"),
])
def test_queda_do_gancho_cai_pavimento_inteiro_com_motivo_fechado(tmp_path, monkeypatch, motivo_gancho, esperado):  # mutantes 1, 3, 4
    cena = _criar_cena(tmp_path)
    base = desenho.processar(cena.pedido_base)
    chamadas = _espiar_gancho(monkeypatch, lambda *a: (None, motivo_gancho))
    vistos_base, real_base = [], desenho._processar_base
    monkeypatch.setattr(desenho, "_processar_base", lambda p, *a, **k: (vistos_base.append(list(p["elementos"])), real_base(p, *a, **k))[1])

    resp = desenho.processar(cena.pedido_cache)
    _checar_telemetria(resp, via_cache=False, queda=esperado, n_faltantes=0)
    assert len(chamadas) == 1 and "faltantes" not in resp and "incompleta" not in resp
    assert vistos_base == [list(cena.pedido_base["elementos"])] and resp["svg"] == base["svg"]


def test_excecao_no_gancho_e_stub_padrao_caem_como_erro_motor(tmp_path, monkeypatch):  # mutante 10
    cena = _criar_cena(tmp_path)
    base = desenho.processar(cena.pedido_base)

    r_stub = desenho.processar(cena.pedido_cache)
    _checar_telemetria(r_stub, via_cache=False, queda="erro_motor", n_faltantes=0)
    assert r_stub["svg"] == base["svg"] and "faltantes" not in r_stub

    chamadas = _espiar_gancho(monkeypatch, lambda *_a: (_ for _ in ()).throw(RuntimeError("falha no motor")))
    r_exc = desenho.processar(cena.pedido_cache)
    _checar_telemetria(r_exc, via_cache=False, queda="erro_motor", n_faltantes=0)
    assert len(chamadas) == 1 and "erro" not in r_exc and "faltantes" not in r_exc and r_exc["svg"] == base["svg"]


def test_queda_nao_sobrescreve_faltantes_nem_incompleta_t19i1(tmp_path, monkeypatch):  # mutante 4
    cena = _criar_cena(tmp_path)
    _sql(cena.pasta, "DELETE FROM ocorrencias WHERE global_id = ?", (cena.movel.GlobalId,))
    base = desenho.processar(cena.pedido_base)
    fake_t19 = {**base, "incompleta": True, "faltantes": [cena.parede.id()]}
    monkeypatch.setattr(desenho, "_planta_por_componentes", lambda *a, **k: dict(fake_t19))

    resp = desenho.processar({**cena.pedido_cache, "componentes": True})
    _checar_telemetria(resp, via_cache=False, queda="cache_incompleto", n_faltantes=1)
    assert resp["incompleta"] is True and resp["faltantes"] == [cena.parede.id()]


def test_sem_arquivo_salvo_e_opcoes_incompativeis(tmp_path, monkeypatch):  # mutante 3
    cena = _criar_cena(tmp_path)
    chamadas = _espiar_gancho(monkeypatch, lambda f, p, m, ev, fase, a: (_resp_cache_ok(ev), None))

    r_opc = desenho.processar({**cena.pedido_cache, "moveis_como_caixa": True})
    _checar_telemetria(r_opc, via_cache=False, queda="opcoes_incompativeis", n_faltantes=0)
    assert chamadas == [] and "faltantes" not in r_opc

    monkeypatch.setattr(desenho, "_abrir_ifc", lambda *_a, **_k: cena.f)
    r_arq = desenho.processar({**cena.pedido_cache, "arquivo": str(tmp_path / "nao_salvo.ifc")})
    _checar_telemetria(r_arq, via_cache=False, queda="sem_arquivo_salvo", n_faltantes=len(cena.validos))
    assert chamadas == [] and "faltantes" not in r_arq


def test_cache_ausente_nao_cria_arquivo_sqlite_nem_pasta(tmp_path, monkeypatch):  # mutante 7
    cena = _criar_cena(tmp_path)
    chamadas = _espiar_gancho(monkeypatch, lambda f, p, m, ev, fase, a: (_resp_cache_ok(ev), None))

    pasta_vazia = tmp_path / "vazia"
    pasta_vazia.mkdir()
    r1 = desenho.processar({**cena.pedido_base, "pasta_cache_geometria": str(pasta_vazia)})
    _checar_telemetria(r1, via_cache=False, queda="cache_ausente", n_faltantes=len(cena.validos))
    assert not (pasta_vazia / C.NOME_BANCO).exists() and list(pasta_vazia.iterdir()) == []

    pasta_inex = tmp_path / "nao_existe"
    r2 = desenho.processar({**cena.pedido_base, "pasta_cache_geometria": str(pasta_inex)})
    _checar_telemetria(r2, via_cache=False, queda="cache_ausente", n_faltantes=len(cena.validos))
    assert not pasta_inex.exists() and chamadas == []


def test_cabecalho_valido_e_divergente_nao_destroem_banco(tmp_path, monkeypatch):  # mutantes 6, 3
    cena = _criar_cena(tmp_path)
    _espiar_gancho(monkeypatch, lambda f, p, m, ev, fase, a: (_resp_cache_ok(ev), None))
    monkeypatch.setattr(construtor, "abrir_banco", lambda *a, **k: (_ for _ in ()).throw(AssertionError("nao chamar abrir_banco")))
    monkeypatch.setattr(C.CacheGeometria, "limpar", lambda *a, **k: (_ for _ in ()).throw(AssertionError("nao chamar limpar")))

    snap = lambda p: (
        _sql(p, "SELECT chave, checksum FROM formas ORDER BY chave"),
        _sql(p, "SELECT documento, global_id, chave_forma FROM ocorrencias ORDER BY global_id"),
        _sql(p, "SELECT chave, valor FROM meta ORDER BY chave"),
    )
    antes = snap(cena.pasta)
    r_ok = desenho.processar(cena.pedido_cache)
    _checar_telemetria(r_ok, via_cache=True, queda=None, n_faltantes=0)
    assert snap(cena.pasta) == antes and len(antes[0]) >= 3 and len(antes[1]) == 3

    pasta_div = tmp_path / "cab_div"
    with C.abrir_cache(pasta_div, C.cabecalho_atual(tesselacao={})) as cb:
        cb.gravar_forma("sentinela", np.zeros((3, 3), np.float64), np.array([[0, 1, 2]], np.int32))
    meta_antes = _sql(pasta_div, "SELECT chave, valor FROM meta")
    r_div = desenho.processar({**cena.pedido_base, "pasta_cache_geometria": str(pasta_div)})
    _checar_telemetria(r_div, via_cache=False, queda="cache_invalido", n_faltantes=len(cena.validos))
    assert _sql(pasta_div, "SELECT chave FROM formas") == [("sentinela",)]
    assert _sql(pasta_div, "SELECT chave, valor FROM meta") == meta_antes

    pasta_lixo = tmp_path / "lixo"
    pasta_lixo.mkdir()
    lixo = b"nao e um banco sqlite valido"
    (pasta_lixo / C.NOME_BANCO).write_bytes(lixo)
    r_lixo = desenho.processar({**cena.pedido_base, "pasta_cache_geometria": str(pasta_lixo)})
    _checar_telemetria(r_lixo, via_cache=False, queda="cache_invalido", n_faltantes=len(cena.validos))
    assert (pasta_lixo / C.NOME_BANCO).read_bytes() == lixo

    monkeypatch.setattr(cache_leitura, "malhas_do_cache", lambda *a, **k: (_ for _ in ()).throw(sqlite3.OperationalError("database is locked")))
    r_lock = desenho.processar(cena.pedido_cache)
    _checar_telemetria(r_lock, via_cache=False, queda="cache_invalido", n_faltantes=len(cena.validos))


def test_despacho_antes_de_componentes_e_faixas_e_apos_assinatura(tmp_path, monkeypatch):  # mutante 8
    cena = _criar_cena(tmp_path)
    chamadas = _espiar_gancho(monkeypatch, lambda f, p, m, ev, fase, a: (_resp_cache_ok(ev), None))
    comp_calls, faixa_calls, base_calls = [], [], []
    monkeypatch.setattr(desenho, "_planta_por_componentes", lambda *a, **k: (comp_calls.append(a), {})[1])
    monkeypatch.setattr(desenho, "_planta_em_faixas", lambda *a, **k: (faixa_calls.append(a), {})[1])
    monkeypatch.setattr(desenho, "_processar_base", lambda *a, **k: (base_calls.append(a), {})[1])

    _checar_telemetria(desenho.processar({**cena.pedido_cache, "componentes": True}), via_cache=True, queda=None, n_faltantes=0)
    assert comp_calls == [] and base_calls == [] and len(chamadas) == 1

    _checar_telemetria(desenho.processar({**cena.pedido_cache, "faixas": 2}), via_cache=True, queda=None, n_faltantes=0)
    assert faixa_calls == [] and base_calls == [] and len(chamadas) == 2

    chamadas.clear()
    r_div = desenho.processar({**cena.pedido_cache, "assinatura": [1, 1]})
    assert r_div["ok"] is False and r_div["erro"]["tipo"] == "Divergente" and chamadas == []


def test_corte_e_faixa_ignoram_despacho_de_cache(tmp_path, monkeypatch):  # mutante 9
    cena = _criar_cena(tmp_path)
    gancho_calls = _espiar_gancho(monkeypatch, lambda f, p, m, ev, fase, a: (_resp_cache_ok(ev), None))
    ler_calls, real_ler = [], cache_leitura.malhas_do_cache
    monkeypatch.setattr(cache_leitura, "malhas_do_cache", lambda *a, **k: (ler_calls.append(a), real_ler(*a, **k))[1])

    pasta_inex = tmp_path / "sem_banco_corte"
    for rc in (desenho.processar(_pedido_corte(cena, cena.pasta)), desenho.processar(_pedido_corte(cena, pasta_inex))):
        assert rc["ok"] is True and "via_cache" not in rc and "queda" not in rc
    assert not pasta_inex.exists()

    faixa = {"u0": -1.0, "u1": 10.0, "donos": [e.id() for e in cena.validos]}
    r_faixa = desenho.processar({**cena.pedido_cache, "faixa": faixa})
    assert r_faixa["ok"] is True and "via_cache" not in r_faixa and "queda" not in r_faixa
    assert gancho_calls == [] and ler_calls == []


def test_forma_corrompida_cai_incompleto_e_apaga_para_construtor_refazer(tmp_path, monkeypatch):  # mutantes 11, 2, 4
    cena = _criar_cena(tmp_path)
    [(chave_par,)] = _sql(cena.pasta, "SELECT chave_forma FROM ocorrencias WHERE global_id = ?", (cena.parede.GlobalId,))
    [(chave_laje,)] = _sql(cena.pasta, "SELECT chave_forma FROM ocorrencias WHERE global_id = ?", (cena.laje.GlobalId,))
    [(chave_mov,)] = _sql(cena.pasta, "SELECT chave_forma FROM ocorrencias WHERE global_id = ?", (cena.movel.GlobalId,))
    [(blob,)] = _sql(cena.pasta, "SELECT vertices FROM formas WHERE chave = ?", (chave_par,))
    ruim = bytearray(blob)
    ruim[0] ^= 0xFF
    _sql(cena.pasta, "UPDATE formas SET vertices = ? WHERE chave = ?", (bytes(ruim), chave_par))
    assert _sql(cena.pasta, "SELECT COUNT(*) FROM formas WHERE chave = ?", (chave_par,)) == [(1,)]

    chamadas = _espiar_gancho(monkeypatch, lambda f, p, m, ev, fase, a: (_resp_cache_ok(ev), None))
    resp = desenho.processar(cena.pedido_cache)
    _checar_telemetria(resp, via_cache=False, queda="cache_incompleto", n_faltantes=1)
    assert chamadas == [] and "faltantes" not in resp and "incompleta" not in resp
    with C.abrir_cache(cena.pasta, C.cabecalho_atual(tesselacao=construtor.TESSELACAO)) as cb:
        assert chave_par not in cb.formas_presentes([chave_par])
        assert cb.formas_presentes([chave_laje, chave_mov]) == {chave_laje, chave_mov}
    assert _sql(cena.pasta, "SELECT COUNT(*) FROM formas WHERE chave = ?", (chave_par,)) == [(0,)]
