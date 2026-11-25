# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oraculo F0-S06-T27a: leitura reutilizavel do cache de geometria (base do corte).

Contrato novo, em `obim_geometria.desenho`:
    `_ler_malhas_cache(pedido, pasta_cache, global_ids, matrizes=None) -> (malhas, faltantes, motivo)`
  - `motivo` None | "sem_arquivo_salvo" | "cache_ausente" | "cache_invalido"; fora de None,
    `malhas == {}` e `faltantes == []`; nunca levanta excecao.
  - `malhas` e `faltantes` saem de `cache_leitura.malhas_do_cache` (chamada via modulo, 1 vez).
  - `matrizes` (dict opcional) e preenchido no lugar com `{gid: matriz 4x4 gravada}` dos gids lidos
    (insumo da guarda "peca movida" da T27b); sem ele, nada muda.
  - Abre e fecha o banco (1 vez), nao abre IFC, nao grava nada alem do apagar_forma ja existente.
`_tentar_planta_pelo_cache` passa a usar o auxiliar e mantem telemetria e `queda` iguais.
`cache_leitura.malhas_do_cache` mantem assinatura e retorno de 2 elementos.
"""
from __future__ import annotations

import ast
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import ifcopenshell
import ifcopenshell.api
import numpy as np
import pytest

from obim_geometria import cache_geometria as C
from obim_geometria import cache_leitura, construtor, desenho

RAIZ = Path(__file__).resolve().parents[1]


def _parede(f, body, pos, comprimento=2.0):
    api = ifcopenshell.api.run
    el = api("root.create_entity", f, ifc_class="IfcWall")
    rep = api("geometry.add_wall_representation", f, context=body, length=comprimento, height=2.8, thickness=0.2)
    el.Representation = f.createIfcProductDefinitionShape(Representations=[rep])
    m = np.eye(4)
    m[:3, 3] = pos
    api("geometry.edit_object_placement", f, product=el, matrix=m, is_si=False)
    return el


def _cena(tmp_path: Path, comprimentos=(2.0, 2.0, 2.0)) -> SimpleNamespace:
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
    paredes = [_parede(f, body, (x, 0.0, 0.0), c) for x, c in zip((0.0, 20.0, 40.0), comprimentos)]
    api("spatial.assign_container", f, products=paredes, relating_structure=andar)
    arq = tmp_path / "t27a.ifc"
    f.write(str(arq))
    f = ifcopenshell.open(str(arq))
    gids = [p.GlobalId for p in paredes]
    pasta = tmp_path / "cache_geo"
    with construtor.abrir_banco(pasta) as cache:
        r = construtor.construir_lote(f, cache, construtor.fila_inicial(f), documento=construtor.documento_de(arq), assinatura="s1", memo={})
        assert r["falhas"] == 0 and r["gravadas"] == 3
    pedido = {
        "arquivo": str(arq),
        "vista": {"tipo": "PLANTA", "pavimento": f.by_guid(andar.GlobalId).GlobalId, "escala": 1.0, "altura_corte_m": 1.2},
        "elementos": [(f.by_guid(g).id(), g) for g in gids],
        "threads": 1,
    }
    return SimpleNamespace(f=f, arq=arq, pasta=pasta, gids=gids, pedido=pedido, andar=andar)


def _sql(pasta, sql, args=()):
    con = sqlite3.connect(str(Path(pasta) / C.NOME_BANCO))
    try:
        con.execute(sql, args)
        con.commit()
    finally:
        con.close()


def _n(pasta, tabela):
    con = sqlite3.connect(str(Path(pasta) / C.NOME_BANCO))
    try:
        return con.execute(f"SELECT COUNT(*) FROM {tabela}").fetchone()[0]
    finally:
        con.close()


def _referencia(cena, gids):
    """Leitura de referencia feita direto pela API do cache (o que a planta fazia inline)."""
    cab = C._json_canonico(C.cabecalho_atual(tesselacao=construtor.TESSELACAO))
    con = C._conectar(Path(cena.pasta) / C.NOME_BANCO)
    assert C._banco_integro(con, cab)
    cache = C.CacheGeometria(Path(cena.pasta) / C.NOME_BANCO, con)
    try:
        return cache_leitura.malhas_do_cache(cache, C.documento_de(cena.arq), gids)
    finally:
        cache.fechar()


def test_equivalente_a_leitura_inline_da_planta(tmp_path):
    cena = _cena(tmp_path)
    malhas, faltantes, motivo = desenho._ler_malhas_cache(cena.pedido, cena.pasta, cena.gids)
    ref, ref_falt = _referencia(cena, cena.gids)
    assert motivo is None and faltantes == ref_falt == []
    assert sorted(malhas) == sorted(ref) == sorted(cena.gids)
    for g in cena.gids:
        assert np.array_equal(malhas[g][0], ref[g][0]) and np.array_equal(malhas[g][1], ref[g][1])
        assert malhas[g][0].dtype == np.float64 and malhas[g][1].dtype == np.int32
    xs = [malhas[g][0][:, 0].min() for g in cena.gids]
    assert xs[1] - xs[0] == pytest.approx(20.0) and xs[2] - xs[1] == pytest.approx(20.0)


def test_instancias_repetidas_uma_forma_varias_ocorrencias(tmp_path):
    cena = _cena(tmp_path)
    assert _n(cena.pasta, "formas") == 1 and _n(cena.pasta, "ocorrencias") == 3
    malhas, faltantes, motivo = desenho._ler_malhas_cache(cena.pedido, cena.pasta, cena.gids)
    assert motivo is None and not faltantes and len(malhas) == 3


def test_gid_desconhecido_e_faltante_e_nao_derruba_os_outros(tmp_path):
    cena = _cena(tmp_path)
    malhas, faltantes, motivo = desenho._ler_malhas_cache(cena.pedido, cena.pasta, [*cena.gids[:2], "NAO_EXISTE"])
    assert motivo is None and faltantes == ["NAO_EXISTE"] and sorted(malhas) == sorted(cena.gids[:2])


def test_lista_vazia_devolve_vazio_sem_motivo(tmp_path):
    cena = _cena(tmp_path)
    assert desenho._ler_malhas_cache(cena.pedido, cena.pasta, []) == ({}, [], None)


def test_cache_ausente(tmp_path):
    cena = _cena(tmp_path)
    vazia = tmp_path / "sem_banco"
    vazia.mkdir()
    assert desenho._ler_malhas_cache(cena.pedido, vazia, cena.gids) == ({}, [], "cache_ausente")
    assert desenho._ler_malhas_cache(cena.pedido, tmp_path / "nem_existe", cena.gids) == ({}, [], "cache_ausente")


@pytest.mark.parametrize("arquivo", [None, "", "inexistente.ifc"])
def test_sem_arquivo_salvo(tmp_path, arquivo):
    cena = _cena(tmp_path)
    ped = {**cena.pedido, "arquivo": arquivo}
    if arquivo is None:
        ped.pop("arquivo")
    assert desenho._ler_malhas_cache(ped, cena.pasta, cena.gids) == ({}, [], "sem_arquivo_salvo")


def test_banco_corrompido_vira_cache_invalido_sem_excecao(tmp_path):
    cena = _cena(tmp_path)
    (Path(cena.pasta) / C.NOME_BANCO).write_bytes(b"isto nao e sqlite" * 200)
    assert desenho._ler_malhas_cache(cena.pedido, cena.pasta, cena.gids) == ({}, [], "cache_invalido")


def test_cabecalho_incompativel_vira_cache_invalido(tmp_path, monkeypatch):
    cena = _cena(tmp_path)
    monkeypatch.setattr(C, "VERSAO_MOTOR", "999")
    assert desenho._ler_malhas_cache(cena.pedido, cena.pasta, cena.gids) == ({}, [], "cache_invalido")


def test_excecao_na_leitura_vira_cache_invalido_e_fecha_o_banco(tmp_path, monkeypatch):
    cena = _cena(tmp_path)
    fechou = []
    real = C.CacheGeometria.fechar
    monkeypatch.setattr(C.CacheGeometria, "fechar", lambda self: (fechou.append(1), real(self))[1])

    def quebrar(*a, **k):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(cache_leitura, "malhas_do_cache", quebrar)
    assert desenho._ler_malhas_cache(cena.pedido, cena.pasta, cena.gids) == ({}, [], "cache_invalido")
    assert fechou == [1]


def test_leitura_ok_fecha_o_banco_uma_vez_e_chama_malhas_uma_vez(tmp_path, monkeypatch):
    cena = _cena(tmp_path)
    fechou, leituras = [], []
    real_f, real_l = C.CacheGeometria.fechar, cache_leitura.malhas_do_cache
    monkeypatch.setattr(C.CacheGeometria, "fechar", lambda self: (fechou.append(1), real_f(self))[1])
    monkeypatch.setattr(cache_leitura, "malhas_do_cache", lambda *a, **k: (leituras.append(a), real_l(*a, **k))[1])
    desenho._ler_malhas_cache(cena.pedido, cena.pasta, cena.gids)
    assert fechou == [1] and len(leituras) == 1
    assert leituras[0][1] == C.documento_de(cena.arq)


def test_forma_corrompida_so_a_peca_vira_faltante_e_forma_e_apagada(tmp_path):
    cena = _cena(tmp_path)
    chave = sqlite3.connect(str(Path(cena.pasta) / C.NOME_BANCO)).execute("SELECT chave FROM formas").fetchone()[0]
    ruim = bytearray(sqlite3.connect(str(Path(cena.pasta) / C.NOME_BANCO)).execute("SELECT vertices FROM formas").fetchone()[0])
    ruim[0] ^= 0xFF
    _sql(cena.pasta, "UPDATE formas SET vertices=? WHERE chave=?", (bytes(ruim), chave))
    malhas, faltantes, motivo = desenho._ler_malhas_cache(cena.pedido, cena.pasta, cena.gids)
    assert motivo is None and sorted(faltantes) == sorted(cena.gids) and malhas == {}
    assert _n(cena.pasta, "formas") == 0 and _n(cena.pasta, "ocorrencias") == 3


def test_matrizes_preenchidas_no_lugar_e_opcionais(tmp_path):
    cena = _cena(tmp_path)
    mats: dict = {}
    malhas, _, motivo = desenho._ler_malhas_cache(cena.pedido, cena.pasta, cena.gids, mats)
    assert motivo is None and sorted(mats) == sorted(malhas)
    for g in cena.gids:
        el = cena.f.by_guid(g)
        assert np.allclose(mats[g], construtor.matriz_mundo(el, 1.0), atol=1e-9)
    sem, _, _ = desenho._ler_malhas_cache(cena.pedido, cena.pasta, cena.gids)
    assert sorted(sem) == sorted(malhas)


def test_matriz_nao_inclui_gid_faltante_nem_motivo_de_queda(tmp_path):
    cena = _cena(tmp_path)
    mats: dict = {}
    desenho._ler_malhas_cache(cena.pedido, cena.pasta, [cena.gids[0], "NAO_EXISTE"], mats)
    assert list(mats) == [cena.gids[0]]
    mats2: dict = {}
    desenho._ler_malhas_cache(cena.pedido, tmp_path / "nada", cena.gids, mats2)
    assert mats2 == {}


def test_peca_movida_banco_velho_matriz_gravada_difere_da_do_ifc_salvo(tmp_path):
    cena = _cena(tmp_path)
    api = ifcopenshell.api.run
    f2 = ifcopenshell.open(str(cena.arq))
    mover = f2.by_guid(cena.gids[1])
    m = np.eye(4)
    m[:3, 3] = (21.5, 3.0, 0.0)
    api("geometry.edit_object_placement", f2, product=mover, matrix=m, is_si=False)
    f2.write(str(cena.arq))  # salvo, banco NAO reconstruido
    f3 = ifcopenshell.open(str(cena.arq))

    mats: dict = {}
    malhas, faltantes, motivo = desenho._ler_malhas_cache(cena.pedido, cena.pasta, cena.gids, mats)
    assert motivo is None and not faltantes
    atual = construtor.matriz_mundo(f3.by_guid(cena.gids[1]), 1.0)
    assert not np.allclose(mats[cena.gids[1]], atual, atol=1e-9), "guarda precisa enxergar a diferenca"
    assert malhas[cena.gids[1]][0][:, 0].min() == pytest.approx(20.0), "malha continua na posicao gravada"
    for g in (cena.gids[0], cena.gids[2]):
        assert np.allclose(mats[g], construtor.matriz_mundo(f3.by_guid(g), 1.0), atol=1e-9)


def test_nao_reabre_o_ifc_nem_grava_no_banco(tmp_path, monkeypatch):
    cena = _cena(tmp_path)
    abertos = []
    monkeypatch.setattr(ifcopenshell, "open", lambda *a, **k: abertos.append(a) or (_ for _ in ()).throw(AssertionError("reabriu IFC")))
    monkeypatch.setattr(desenho, "_abrir_ifc", lambda *a, **k: abertos.append(a) or (_ for _ in ()).throw(AssertionError("reabriu IFC")), raising=False)
    banco = Path(cena.pasta) / C.NOME_BANCO
    antes = (banco.read_bytes(), _n(cena.pasta, "formas"), _n(cena.pasta, "ocorrencias"))
    desenho._ler_malhas_cache(cena.pedido, cena.pasta, cena.gids)
    assert abertos == []
    assert (banco.read_bytes(), _n(cena.pasta, "formas"), _n(cena.pasta, "ocorrencias")) == antes


def test_malhas_do_cache_mantem_assinatura_e_retorno_de_dois(tmp_path):
    cena = _cena(tmp_path)
    r = _referencia(cena, cena.gids)
    assert isinstance(r, tuple) and len(r) == 2 and isinstance(r[0], dict) and isinstance(r[1], list)


def test_planta_usa_o_auxiliar_e_mantem_telemetria(tmp_path, monkeypatch):
    cena = _cena(tmp_path)
    chamadas, real = [], desenho._ler_malhas_cache
    monkeypatch.setattr(desenho, "_ler_malhas_cache", lambda *a, **k: (chamadas.append(a), real(*a, **k))[1])
    resp, queda, n_falt, cache_s = desenho._tentar_planta_pelo_cache(cena.f, cena.pedido, cena.pasta, None, 0.0)
    assert len(chamadas) == 1
    assert queda is None and n_falt == 0 and cache_s >= 0.0
    assert resp["ok"] is True and resp["via_cache"] is True and resp.get("queda") is None


def test_planta_mantem_quedas_pelo_auxiliar(tmp_path):
    cena = _cena(tmp_path)
    vazia = tmp_path / "vazia"
    vazia.mkdir()
    n = len(cena.pedido["elementos"])
    r, q, nf, _ = desenho._tentar_planta_pelo_cache(cena.f, cena.pedido, vazia, None, 0.0)
    assert (r, q, nf) == (None, "cache_ausente", n)
    r, q, nf, _ = desenho._tentar_planta_pelo_cache(cena.f, {**cena.pedido, "arquivo": None}, cena.pasta, None, 0.0)
    assert (r, q, nf) == (None, "sem_arquivo_salvo", n)
    (Path(cena.pasta) / C.NOME_BANCO).write_bytes(b"lixo" * 500)
    r, q, nf, _ = desenho._tentar_planta_pelo_cache(cena.f, cena.pedido, cena.pasta, None, 0.0)
    assert (r, q, nf) == (None, "cache_invalido", n)


def test_planta_cache_incompleto_conta_faltantes(tmp_path):
    cena = _cena(tmp_path)
    _sql(cena.pasta, "DELETE FROM ocorrencias WHERE global_id=?", (cena.gids[0],))
    r, q, nf, _ = desenho._tentar_planta_pelo_cache(cena.f, cena.pedido, cena.pasta, None, 0.0)
    assert (r, q, nf) == (None, "cache_incompleto", 1)


@pytest.mark.parametrize("rel", sorted(str(p.relative_to(RAIZ)) for p in (RAIZ / "app").rglob("*.py")))
def test_processo_pai_nao_importa_banco_nem_leitura_de_cache(rel):
    arvore = ast.parse((RAIZ / rel).read_text(encoding="utf-8"))
    proibidos = {"sqlite3", "cache_geometria", "cache_leitura"}
    achados = []
    for no in ast.walk(arvore):
        if isinstance(no, ast.Import):
            achados += [a.name for a in no.names if set(a.name.split(".")) & proibidos]
        elif isinstance(no, ast.ImportFrom):
            nomes = set((no.module or "").split(".")) | {a.name for a in no.names}
            if nomes & proibidos:
                achados.append(no.module)
    assert achados == [], f"{rel} importa {achados}"


def test_matrizes_vem_da_mesma_consulta_das_malhas(tmp_path, monkeypatch):
    cena = _cena(tmp_path)
    n, real = [], C.CacheGeometria.ocorrencias_por_ids
    monkeypatch.setattr(C.CacheGeometria, "ocorrencias_por_ids", lambda self, *a, **k: (n.append(1), real(self, *a, **k))[1])
    mats: dict = {}
    malhas, _, motivo = desenho._ler_malhas_cache(cena.pedido, cena.pasta, cena.gids, mats)
    assert motivo is None and sorted(mats) == sorted(malhas) == sorted(cena.gids)
    assert len(n) == 1, "matrizes nao pode custar 2a consulta (TOCTOU, lock, CPU sob GIL)"


def test_matrizes_incompletas_nunca_com_motivo_none(tmp_path, monkeypatch):
    cena = _cena(tmp_path)
    n, real = [], C.CacheGeometria.ocorrencias_por_ids

    def so_a_primeira(self, *a, **k):
        n.append(1)
        return real(self, *a, **k) if len(n) == 1 else {}

    monkeypatch.setattr(C.CacheGeometria, "ocorrencias_por_ids", so_a_primeira)
    mats: dict = {}
    malhas, faltantes, motivo = desenho._ler_malhas_cache(cena.pedido, cena.pasta, cena.gids, mats)
    if motivo is None:
        assert sorted(mats) == sorted(malhas) == sorted(cena.gids) and not faltantes
    else:
        assert (malhas, faltantes, motivo, mats) == ({}, [], "cache_invalido", {})


def test_excecao_deixa_matrizes_intactas(tmp_path, monkeypatch):
    cena = _cena(tmp_path)
    monkeypatch.setattr(cache_leitura, "malhas_do_cache", lambda *a, **k: (_ for _ in ()).throw(sqlite3.OperationalError("locked")))
    mats: dict = {}
    assert desenho._ler_malhas_cache(cena.pedido, cena.pasta, cena.gids, mats) == ({}, [], "cache_invalido")
    assert mats == {}


def test_falha_ao_montar_cabecalho_nao_levanta(tmp_path, monkeypatch):
    cena = _cena(tmp_path)
    monkeypatch.setattr(C, "cabecalho_atual", lambda **k: (_ for _ in ()).throw(RuntimeError("x")))
    assert desenho._ler_malhas_cache(cena.pedido, cena.pasta, cena.gids) == ({}, [], "cache_invalido")


@pytest.mark.parametrize("modo", ["corrompido", "cabecalho"])
def test_conexao_fechada_uma_vez_quando_banco_e_rejeitado(tmp_path, monkeypatch, modo):
    cena = _cena(tmp_path)
    if modo == "corrompido":
        (Path(cena.pasta) / C.NOME_BANCO).write_bytes(b"lixo" * 500)
    else:
        monkeypatch.setattr(C, "VERSAO_MOTOR", "999")
    fechadas, real = [], C._fechar_con
    monkeypatch.setattr(C, "_fechar_con", lambda con: (fechadas.append(1), real(con))[1])
    assert desenho._ler_malhas_cache(cena.pedido, cena.pasta, cena.gids) == ({}, [], "cache_invalido")
    assert len(fechadas) == 1


def test_forma_corrompida_preserva_a_forma_intacta(tmp_path):
    cena = _cena(tmp_path, comprimentos=(2.0, 2.0, 3.5))
    assert _n(cena.pasta, "formas") == 2
    con = sqlite3.connect(str(Path(cena.pasta) / C.NOME_BANCO))
    try:
        chave_ruim = con.execute("SELECT chave_forma FROM ocorrencias WHERE global_id=?", (cena.gids[2],)).fetchone()[0]
        vert = bytearray(con.execute("SELECT vertices FROM formas WHERE chave=?", (chave_ruim,)).fetchone()[0])
    finally:
        con.close()
    vert[0] ^= 0xFF
    _sql(cena.pasta, "UPDATE formas SET vertices=? WHERE chave=?", (bytes(vert), chave_ruim))
    malhas, faltantes, motivo = desenho._ler_malhas_cache(cena.pedido, cena.pasta, cena.gids)
    assert motivo is None and faltantes == [cena.gids[2]] and sorted(malhas) == sorted(cena.gids[:2])
    assert _n(cena.pasta, "formas") == 1


def test_pasta_vazia_e_gerador(tmp_path):
    cena = _cena(tmp_path)
    for pasta in (None, ""):
        assert desenho._ler_malhas_cache(cena.pedido, pasta, cena.gids) == ({}, [], "cache_ausente")
    malhas, faltantes, motivo = desenho._ler_malhas_cache(cena.pedido, cena.pasta, (g for g in cena.gids))
    assert motivo is None and not faltantes and sorted(malhas) == sorted(cena.gids)


def test_planta_moveis_como_caixa_nao_le_o_cache(tmp_path, monkeypatch):
    cena = _cena(tmp_path)
    monkeypatch.setattr(desenho, "_ler_malhas_cache", lambda *a, **k: (_ for _ in ()).throw(AssertionError("nao deveria ler")))
    r, q, nf, _ = desenho._tentar_planta_pelo_cache(cena.f, {**cena.pedido, "moveis_como_caixa": True}, cena.pasta, None, 0.0)
    assert (r, q, nf) == (None, "opcoes_incompativeis", 0)
