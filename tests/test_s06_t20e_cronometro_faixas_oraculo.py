# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oraculo F0-S06-T20e: cronometro das faixas da planta (T1/T2). Nao editar nesta tarefa.
CONTRATO (`desenho._planta_em_faixas`, e `_planta_por_componentes` quando o megagrupo vai a faixas):
 1. Quando o bloco de faixas RODA (faixas despachadas a `faixas.rodar_filho`), `resp["tempos"]` ganha:
    `n_faixas` (int, = faixas despachadas), `faixas_s` (list[float] com o relogio de CADA faixa, na ORDEM DAS FAIXAS, esquerda para direita, nao na de termino),
    `faixas_total_s` (float, relogio do bloco inteiro: max(faixas_s) <= total <= soma(faixas_s) + folga) e `faixas_abrir_s` (list[float], uma por faixa na mesma ordem:
    `tempos["abrir_s"]` que o filho devolveu, ou 0.0 quando nao informa). Vale tambem quando alguma faixa falha e cai no `normal()` (o tempo gasto foi real).
 2. Quando o bloco NAO roda (sem `faixas`, `faixas == 1`, so 1 faixa possivel, sem itens, ou caminho de componentes sem megagrupo) essas 4 chaves ficam AUSENTES (nada de 0/[] enganoso).
 3. Componentes + megagrupo direto em faixas (`_planta_em_faixas(..., sem_normal=True)`): as 4 chaves aparecem no `tempos` final (uma execucao de faixas: listas dessa execucao; mais de uma: concatenadas na ordem de execucao,
    `faixas_total_s` somado); vale tambem se o megagrupo falhar.
 4. `n_timeouts` conta o timeout de faixa (resposta de erro com "tempo" no tipo), inclusive quando o refazer do megagrupo em faixas falha (hoje esse timeout se perde: 0).
 5. Nenhuma mudanca de resultado: SVG, enviados, falhas e as chaves antigas de `tempos` (abrir_s, geo_s, write_s, finalize_s, pesados_s...) iguais.
MUTANTES que os testes matam: chaves ausentes; lista na ordem de termino (nao a das faixas); `n_timeouts` sem contar faixas; total menor que o maior; faixas_abrir_s ignorando o filho; chaves criadas no caminho sem faixas."""
from __future__ import annotations

import copy
import time

import pytest

import obim_geometria.desenho as D
import obim_geometria.faixas as F
from test_s06_t19h_componentes_oraculo import _caixa, _cena, _guids
from test_s06_t20c_megagrupo_oraculo import _cena_mega, _limiares

NOVAS = ("faixas_total_s", "faixas_s", "n_faixas", "faixas_abrir_s")
ANTIGAS = ("abrir_s", "geo_s", "write_s", "finalize_s", "pesados_s", "formas_s", "agrupar_s", "max_lote_s", "n_timeouts", "n_grupos", "maior_grupo")


class FakeFaixas:
    """Substitui `faixas.rodar_filho`. Faixa identificada pelo indice da 1a peca que ela possui (`faixa["donos"]`) dentro de `ids`.
    `atraso[i]` (s) dorme; `timeout_em` = indices que respondem erro de Tempo; `abrir[i]` vira `tempos["abrir_s"]` da resposta. Lote/avulso: roda em processo."""

    def __init__(self, mp, ids, atraso=None, timeout_em=(), abrir=None):
        self.ids, self.atraso, self.timeout_em, self.abrir = list(ids), atraso or {}, set(timeout_em), abrir or {}
        self.faixas = []
        mp.setattr(F, "rodar_filho", self)

    def __call__(self, pedido, *a, **k):
        if pedido.get("op") == "desenho_lote":
            return {"ok": True, "resultados": [D.processar(copy.deepcopy(q)) for q in pedido["pedidos"]]}
        fx = pedido.get("faixa")
        if fx is None:
            return D.processar(copy.deepcopy(pedido))
        idx = self.ids.index(min(fx["donos"])) if fx["donos"] else -1
        self.faixas.append(idx)
        time.sleep(self.atraso.get(idx, 0.0))
        if idx in self.timeout_em:
            return {"ok": False, "erro": {"tipo": "AuxiliarEstourouTempo", "mensagem": "estourou", "rastro": ""}}
        r = D.processar(copy.deepcopy(pedido))
        if idx in self.abrir and isinstance(r.get("tempos"), dict):
            r["tempos"]["abrir_s"] = self.abrir[idx]
        return r


def _cena_faixas(tmp_path, n=6):
    """n caixas separadas (x = 3k), `faixas=3` => 3 faixas com 2 caixas cada (donos 0-1, 2-3, 4-5)."""
    ped, ids = _cena(tmp_path, [_caixa(3 * k, 0, 0, 3 * k + 1, 1, 1) for k in range(n)], corte=0.5)
    ped.update({"faixas": 3, "threads": 3})
    return ped, ids


def _roda(ped):
    t0 = time.perf_counter()
    r = D.processar(copy.deepcopy(ped))
    return r, time.perf_counter() - t0


def test_a_chaves_e_tipos(monkeypatch, tmp_path):
    ped, ids = _cena_faixas(tmp_path)
    FakeFaixas(monkeypatch, ids)
    r, _ = _roda(ped)
    t = r["tempos"]
    assert r["ok"] and all(k in t for k in NOVAS), [k for k in NOVAS if k not in t]
    assert isinstance(t["n_faixas"], int) and not isinstance(t["n_faixas"], bool) and t["n_faixas"] == 3
    assert isinstance(t["faixas_total_s"], float) and t["faixas_total_s"] > 0.0
    for k in ("faixas_s", "faixas_abrir_s"):
        assert isinstance(t[k], list) and len(t[k]) == t["n_faixas"] and all(isinstance(x, float) and x >= 0.0 for x in t[k]), k
    assert all(x > 0.0 for x in t["faixas_s"])
    for k in ANTIGAS:
        assert k in t, f"chave antiga {k} sumiu"


def test_b_ordem_das_faixas_total_e_limites(monkeypatch, tmp_path):
    ped, ids = _cena_faixas(tmp_path)
    atraso = {0: 0.4, 2: 0.1, 4: 0.8}  # ordem de termino (1o dono 2, 0, 4) difere da ordem das faixas (0, 2, 4)
    fk = FakeFaixas(monkeypatch, ids, atraso=atraso)
    r, total = _roda(ped)
    t = r["tempos"]
    assert sorted(fk.faixas) == [0, 2, 4], "premissa: faixas com donos 0-1, 2-3, 4-5"
    assert len(t["faixas_s"]) == 3
    for s, esperado in zip(t["faixas_s"], (0.4, 0.1, 0.8)):
        assert esperado <= s <= esperado + 0.6, t["faixas_s"]
    assert t["faixas_s"][0] > t["faixas_s"][1], f"fora da ordem das faixas (ordem de termino?): {t['faixas_s']}"
    assert t["faixas_total_s"] >= max(t["faixas_s"]) - 1e-3
    assert t["faixas_total_s"] <= sum(t["faixas_s"]) + 0.5 and t["faixas_total_s"] <= total + 1e-6


def test_c_faixas_abrir_s_na_ordem_das_faixas(monkeypatch, tmp_path):
    ped, ids = _cena_faixas(tmp_path)
    FakeFaixas(monkeypatch, ids, atraso={0: 0.2, 2: 0.0, 4: 0.1}, abrir={0: 1.5, 2: 2.5, 4: 3.5})
    r, _ = _roda(ped)
    assert r["tempos"]["faixas_abrir_s"] == [1.5, 2.5, 3.5]
    FakeFaixas(monkeypatch, ids)  # filho que nao informa: 0.0 (ou o que processar devolver sem cronometro)
    r, _ = _roda(ped)
    assert all(x == 0.0 or isinstance(x, float) for x in r["tempos"]["faixas_abrir_s"]) and len(r["tempos"]["faixas_abrir_s"]) == 3


def test_d_timeout_em_faixa_conta_e_o_tempo_fica_registrado(monkeypatch, tmp_path):
    ped, ids = _cena_faixas(tmp_path)
    FakeFaixas(monkeypatch, ids, atraso={2: 0.3}, timeout_em={2})
    r, _ = _roda(ped)  # faixa 2 estoura: o pedido cai no caminho normal em processo, resultado completo
    t = r["tempos"]
    assert r["ok"] and set(_guids(r["svg"])) == {g for _, g in ped["elementos"]}
    assert t["n_timeouts"] == 1
    assert t["n_faixas"] == 3 and len(t["faixas_s"]) == 3 and t["faixas_s"][1] >= 0.3 and t["faixas_total_s"] >= max(t["faixas_s"]) - 1e-3


def test_e_svg_e_chaves_antigas_iguais_com_e_sem_instrumentacao(monkeypatch, tmp_path):
    ped, ids = _cena_faixas(tmp_path)
    FakeFaixas(monkeypatch, ids)
    base, _ = _roda(ped)
    FakeFaixas(monkeypatch, ids, atraso={0: 0.2, 4: 0.1}, abrir={2: 9.0})
    outro, _ = _roda(ped)
    assert outro["svg"] == base["svg"] and set(outro) == set(base)
    for k in ("enviados", "falhas_geometria", "caixas", "pesados"):
        assert outro[k] == base[k], k
    assert set(outro["tempos"]) == set(base["tempos"]) and set(NOVAS) <= set(outro["tempos"])
    assert set(_guids(base["svg"])) == {g for _, g in ped["elementos"]}


def test_f_sem_bloco_de_faixas_nao_ha_chaves(monkeypatch, tmp_path):
    ped, ids = _cena_faixas(tmp_path)
    FakeFaixas(monkeypatch, ids)
    sem = {k: v for k, v in ped.items() if k != "faixas"}
    r, _ = _roda(sem)  # caminho normal
    assert r["ok"] and not any(k in r["tempos"] for k in NOVAS)
    r, _ = _roda({**ped, "faixas": 1})
    assert r["ok"] and not any(k in r["tempos"] for k in NOVAS)
    uma, ids1 = _cena(tmp_path, [_caixa(0, 0, 0, 1, 1, 1)], corte=0.5)
    uma.update({"faixas": 3, "threads": 3})
    r, _ = _roda(uma)  # 1 so faixa possivel: volta ao normal sem despachar faixas
    assert r["ok"] and not any(k in r["tempos"] for k in NOVAS)


def test_g_componentes_sem_megagrupo_nao_tem_chaves(monkeypatch, tmp_path):
    from test_s06_t19i1_nunca_descartar_oraculo import _cena3
    ped, ids, _ = _cena3(tmp_path)
    FakeFaixas(monkeypatch, ids)
    _limiares(monkeypatch)
    r, _ = _roda(ped)
    assert r["ok"] and not any(k in r["tempos"] for k in NOVAS)


def test_h_megagrupo_direto_registra_faixas_no_tempos_final(monkeypatch, tmp_path):
    ped, mega, peq = _cena_mega(tmp_path)
    ids = mega + peq
    _limiares(monkeypatch)
    FakeFaixas(monkeypatch, ids, atraso={0: 0.2})
    r, _ = _roda(ped)
    t = r["tempos"]
    assert r["ok"] and t["megagrupo_direto"] is True and t["n_timeouts"] == 0
    assert all(k in t for k in NOVAS), [k for k in NOVAS if k not in t]
    assert t["n_faixas"] >= 2 and len(t["faixas_s"]) == len(t["faixas_abrir_s"]) == t["n_faixas"]
    assert t["faixas_total_s"] >= max(t["faixas_s"]) - 1e-3 and t["faixas_total_s"] <= sum(t["faixas_s"]) + 0.5


def test_i_timeout_de_faixa_do_megagrupo_e_contado_mesmo_quando_o_refazer_falha(monkeypatch, tmp_path):
    ped, mega, peq = _cena_mega(tmp_path)
    ids = mega + peq
    _limiares(monkeypatch)
    FakeFaixas(monkeypatch, ids, timeout_em={0})  # 1a faixa do megagrupo estoura: faixas falham, megagrupo vira faltante
    r, _ = _roda(ped)
    t = r["tempos"]
    assert r["ok"] and r["incompleta"] is True and sorted(r["faltantes"]) == sorted(mega)
    assert t["n_timeouts"] >= 1, "timeout dentro das faixas se perdeu"
    assert all(k in t for k in NOVAS) and len(t["faixas_s"]) == t["n_faixas"] >= 1
