# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo F0-S06-T17: planta em faixas paralelas (T3). Ref: docs/state/cards/F0-S06/F0-S06-T17-planta-em-faixas.md; modelo: T15o (corte). Não editar nesta tarefa.
CONTRATO:
1. `planta.gerar_planta(..., faixas: int | None = None)` (só por nome, depois de `cache`). None (padrão) e 1: pedido SEM `faixas` ou com 1, nenhum filho. N>1 int: `pedido["faixas"] = N`. Inválido
   (<1, bool, não int): ValueError antes do executor.
2. `desenho.processar` de PLANTA com `pedido["faixas"]` inválido (inclui None presente) -> {"ok": False, "erro": {"tipo": "FaixasInvalidas"}}, sem filhos; 1 ou ausente = caminho atual.
3. Com N>1: itens (id, guid, u0, u1) = x mínimo/máximo da caixa de cada elemento do pedido no mundo (= x do SVG da planta, sem deslocamento: a planta não tem viewBox). A planta NÃO traz
   `caixas_coords`: o motor as calcula (`obim_geometria.caixas.processar`); sem caixa de algum elemento -> caminho sem faixas. `faixas.limites/dividir` SEM `so_primeira`; para cada faixa
   `faixas.rodar_filho(pedido_filho)` (consultado a cada chamada), no máximo min(nº de faixas, threads) juntos, cada um com `threads = max(1, threads // simultâneos)`.
4. Pedido do filho = pedido sem `faixas`, `elementos` = quem encosta na faixa (halo, igual à T15o), `faixa = {"u0", "u1", "donos"}`; donos = centro em [u0, u1) (TODO elemento, também móvel em
   caixa e abertura): partição de `elementos`. O filho devolve o SVG com a projeção recortada em [u0, u1] (x direto, sem soma) e só os grupos `ifc:guid` dos donos (cortados, caixas, clones de cache).
5. União = o SVG sem faixas: mesmo esqueleto, um grupo por guid (texto idêntico), uma projeção, mesmo conjunto de segmentos (bordas recortadas sem lacuna nem traço duplo). Vale com origem em
   (0,0) e georreferenciada (x ~ 324550: o recorte não pode perder casas decimais), com o vão da parede fora da faixa dona da parede, móvel em L real, LC_NUMERIC pt_BR nos filhos.
6. Falha de qualquer filho (levanta, ok False, morre) -> o SVG exato do caminho sem faixas; nunca parcial. `Planta.caixas` igual; `n_paths` = `<path` do SVG final."""
from __future__ import annotations

import copy
import inspect
import re

import pytest
from s05_conteudo_aux import _limpa  # noqa: F401  (autouse)
from s06_t17_aux import (B, EspiaoFilho, ExecutorEspiao, Pl, X, cortes_de, desenho_geo, exigir_igual, faixas, id_de, itens_de, modelo, partes, pedido_planta, planta_de, segmentos)

import obim_geometria.nucleos as N


@pytest.fixture(params=[(0.0, 0.0), X.GEO], ids=["origem", "georref"])
def mod(request):
    return modelo(request.param)


def _par(p, n=4, **extra):
    return desenho_geo.processar({**copy.deepcopy(p), "faixas": n, **extra})


def test_assinatura_faixas_so_por_nome_padrao_none():
    par = inspect.signature(Pl.gerar_planta).parameters["faixas"]
    assert par.kind is inspect.Parameter.KEYWORD_ONLY and par.default is None


@pytest.mark.parametrize("n", [4, 50])
def test_faixas_igual_ao_sem_faixas_com_peca_e_vao_cruzando_bordas(monkeypatch, mod, n):
    F = faixas()
    f, g, gid = mod
    base = planta_de(f, gid)
    assert base.n_paths > 0 and {"P0", "porta0", "jan0", "M0_0", "ML", "Longe0"} <= {x for x in g if B.grupo(base.svg, g[x]) is not None}
    esp, ex = EspiaoFilho(monkeypatch, F), ExecutorEspiao()
    r = planta_de(f, gid, ex, faixas=n)
    assert ex.pedidos_desenho[0]["faixas"] == n and 3 <= len(esp.chamadas) <= len(ex.pedidos_desenho[0]["elementos"])
    exigir_igual(base.svg, r.svg, cortes_de(esp.chamadas))
    assert r.n_paths == len(re.findall(r"<path\b", r.svg)) and r.caixas == base.caixas and r.selecao == base.selecao and r.altura_corte == base.altura_corte
    for nome in ("P0", "Vig", "ML"):  # as peças que cruzam fronteiras vieram a mais de um filho
        assert sum(id_de(f, g, nome) in [e[0] for e in c["elementos"]] for c in esp.chamadas) >= 2
    if n == 50:  # uma faixa por centro: a dona da parede não é a da porta nem a da janela, e a parede tem de sair furada igual (o grupo de elemento é comparado acima)
        dono = next(c for c in esp.chamadas if id_de(f, g, "P0") in c["faixa"]["donos"])
        assert not {id_de(f, g, "porta0"), id_de(f, g, "jan0")} & set(dono["faixa"]["donos"])
    cs, xs = cortes_de(esp.chamadas), [x for s in segmentos(r.svg) for (x, _y) in s]
    assert any(x < min(cs) - 0.1 for x in xs) and any(x > max(cs) + 0.1 for x in xs)
    assert len(segmentos(r.svg)) > len(segmentos(base.svg)), "recortar nas bordas parte traços"
    assert any(p[1] != q[1] and p[0] < c < q[0] for p, q in segmentos(base.svg) for c in cs), "um traço inclinado atravessa uma borda"


def test_moveis_como_caixa_e_cache_de_tipo_nao_perdem_nem_duplicam(monkeypatch, mod):
    F = faixas()
    f, _g, gid = mod
    base = planta_de(f, gid, moveis_como_caixa=True)
    esp = EspiaoFilho(monkeypatch, F)
    r = planta_de(f, gid, moveis_como_caixa=True, faixas=4)
    assert len(esp.chamadas) >= 3 and base.caixas
    exigir_igual(base.svg, r.svg, cortes_de(esp.chamadas))
    assert r.caixas == base.caixas
    # cache de tipo (padrão): quem é primário muda com as faixas e o clone arredonda a 1e-4; a projeção do clone não existe, então só os grupos (guid + caixa a 0,01 m) são comparados
    base2, r2 = Pl.gerar_planta(f, gid, executor=ExecutorEspiao()), Pl.gerar_planta(f, gid, executor=ExecutorEspiao(), faixas=4)
    assert partes(r2.svg, True)[1] == partes(base2.svg, True)[1] and len(set(r2.em_cache)) == len(r2.em_cache)


def test_n_um_ou_none_nao_gera_filhos(monkeypatch, mod):
    F = faixas()
    f, _g, gid = mod
    base, esp = planta_de(f, gid), EspiaoFilho(monkeypatch, F)
    for kw in ({}, {"faixas": None}, {"faixas": 1}):
        ex = ExecutorEspiao()
        r = planta_de(f, gid, ex, **kw)
        assert r.svg == base.svg and ex.pedidos_desenho[0].get("faixas", 1) == 1 and esp.chamadas == []


@pytest.mark.parametrize("n", [0, -1, True, 2.5, "4"])
def test_gerar_planta_rejeita_faixas_invalidas_antes_do_executor(mod, n):
    f, _g, gid = mod
    ex = ExecutorEspiao()
    with pytest.raises(ValueError):
        planta_de(f, gid, ex, faixas=n)
    assert ex.chamadas == []


@pytest.mark.parametrize("n", [0, -2, True, 2.5, "4", None])
def test_processar_faixas_invalidas_viram_erro_sem_filhos(monkeypatch, tmp_path, n):
    F = faixas()
    f, _g, gid = modelo()
    p = pedido_planta(f, gid, tmp_path / "p")
    esp = EspiaoFilho(monkeypatch, F)
    r = desenho_geo.processar({**copy.deepcopy(p), "faixas": n})
    assert r["ok"] is False and r["erro"]["tipo"] == "FaixasInvalidas" and "svg" not in r and esp.chamadas == []


def test_filho_recebe_so_a_sua_faixa_mais_o_halo(monkeypatch, tmp_path):
    F = faixas()
    f, g, gid = modelo()
    p = pedido_planta(f, gid, tmp_path / "p")
    assert "caixas_coords" not in p or not p["caixas_coords"], "a planta não traz caixas: o motor as calcula"
    itens = {i: (u0, u1) for i, _g, u0, u1 in itens_de(p)}
    assert len(itens) == len(p["elementos"])
    esp = EspiaoFilho(monkeypatch, F)
    _par(p, 4)
    guid_de = {i: gg for i, gg, *_ in itens_de(p)}
    vistos = []
    assert len(esp.chamadas) >= 3
    for ped, res in esp.ordenados():
        a, b = ped["faixa"]["u0"], ped["faixa"]["u1"]
        assert "faixas" not in ped and ped["arquivo"] == p["arquivo"] and ped["vista"] == p["vista"] and 1 <= ped["threads"] <= p["threads"]
        esperado = {i for i, (u0, u1) in itens.items() if (b is None or u0 <= b + 1e-6) and (a is None or u1 >= a - 1e-6)}
        assert {e[0] for e in ped["elementos"]} == esperado, "só quem encosta na faixa"
        donos = set(ped["faixa"]["donos"])
        assert donos == {i for i, (u0, u1) in itens.items() if (a is None or (u0 + u1) / 2 >= a) and (b is None or (u0 + u1) / 2 < b)} and donos <= esperado and not (donos & set(vistos))
        vistos += list(donos)
        xs = [x for s in segmentos(res["svg"]) for (x, _y) in s]
        assert all((a is None or x >= a - 1e-6) and (b is None or x <= b + 1e-6) for x in xs), "projeção recortada na faixa"
        assert {m[0] for m in partes(res["svg"])[1]} <= {guid_de[i] for i in donos}, "grupos de elemento só dos donos"
    assert sorted(vistos) == sorted(itens), "os donos particionam todos os elementos"


@pytest.mark.parametrize("t", [1, 2, 4])
def test_no_maximo_threads_filhos_juntos(monkeypatch, tmp_path, t):
    F = faixas()
    monkeypatch.setattr(N, "nucleos_fisicos", lambda: 8)
    f, _g, gid = modelo()
    p = pedido_planta(f, gid, tmp_path / "p")
    esp = EspiaoFilho(monkeypatch, F, atraso=0.15)
    r = _par(p, 4, threads=t)
    n = len(esp.chamadas)
    assert r["ok"] and n >= 3 and esp.max_ativos == min(n, t)
    assert all(1 <= c["threads"] and c["threads"] * esp.max_ativos <= t for c in esp.chamadas)


@pytest.mark.parametrize("modo", ["raise", "ok_false"])
def test_faixa_que_falha_recua_ao_caminho_sem_faixas(monkeypatch, tmp_path, modo):
    F = faixas()
    f, _g, gid = modelo()
    p = pedido_planta(f, gid, tmp_path / "p")
    base = desenho_geo.processar(copy.deepcopy(p))
    esp = EspiaoFilho(monkeypatch, F, falha=lambda c: modo if c["faixa"]["u1"] is None else None)
    r = _par(p, 4)  # não levanta
    assert len(esp.chamadas) >= 3 and r["ok"] and r["svg"] == base["svg"], "recuo tem de dar exatamente o desenho completo, nunca parcial"


def test_filhos_reais_com_lc_numeric_pt_br_e_filho_que_morre(monkeypatch, tmp_path):
    F = faixas()
    f, _g, gid = modelo(X.GEO)
    p = pedido_planta(f, gid, tmp_path / "p")
    base = desenho_geo.processar(copy.deepcopy(p))
    lims, real, n = F.limites(itens_de(p), 2), F.rodar_filho, []
    monkeypatch.setattr(F, "rodar_filho", lambda q: n.append(1) or real(q))  # conta os filhos spawn de verdade
    monkeypatch.setenv("LC_NUMERIC", "pt_BR.utf8")
    monkeypatch.setenv("LANG", "pt_BR.utf8")
    r = _par(p, 2)  # processos spawn de verdade
    assert r["ok"] and len(n) == 2, r.get("erro")
    exigir_igual(base["svg"], r["svg"], [b for _a, b in lims if b is not None])
    monkeypatch.setenv("OBIM_TESTE_AUX_SAIR", "3")  # `processo.entrada` sai antes de responder
    r2 = _par(p, 2)
    assert len(n) == 4 and r2["ok"] and r2["svg"] == base["svg"]
