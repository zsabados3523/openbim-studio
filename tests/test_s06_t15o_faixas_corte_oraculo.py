# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo F0-S06-T15o (parte b): corte em faixas ponta a ponta. Ref: docs/state/cards/F0-S06/F0-S06-T15o-faixas.md; medições em reports/F0-S06-T15m-corte.md item 4.
CONTRATO (além do módulo `faixas`, ver a parte a):
1. `desenho.processar(pedido)` com `pedido["faixas"] = N` (inteiro >= 1; ausente ou 1 = comportamento atual, nenhum filho) num pedido de CORTE devolve o MESMO dict (ok, svg,
   n_paths, enviados, caixas, em_cache, falhas_geometria, tempos). Faixas inválidas -> {"ok": False, "erro": {"tipo": "FaixasInvalidas", ...}}, sem filhos.
   `app...corte.gerar_corte(..., faixas=1)` repassa `pedido["faixas"]` (inválido -> ValueError antes do executor).
2. Orquestração: `processar` calcula os itens (u0, u1) das caixas de `caixas_coords` com a câmera da vista, chama `faixas.limites/dividir` (móveis em caixa 2D = `so_primeira`) e,
   para cada faixa, chama `faixas.rodar_filho(pedido_filho) -> dict` (o módulo é consultado a cada chamada, para o teste trocar a função). O padrão de `rodar_filho` abre um
   processo spawn que roda `obim_geometria.processo.entrada` (cada filho abre o mesmo IFC reduzido do pedido) e NUNCA levanta nem trava: filho que morre = {"ok": False, "erro": ...}.
   No máximo `min(nº de faixas, threads)` filhos juntos (threads = `nucleos.limitar_threads(pedido.get("threads"))`); cada filho leva `threads = max(1, threads // simultâneos)`.
3. Pedido do filho = cópia do pedido sem `faixas`, com `elementos` = só a faixa (halo incluso) e `faixa = {"u0": a|None, "u1": b|None, "donos": [ids]}`. Donos = os de centro em
   [a, b) (o móvel em caixa 2D é da faixa 0): partição de todos os elementos. O filho devolve o SVG com a projeção recortada em [a+TX, b+TX] e só os grupos de corte dos donos.
4. Falha de uma faixa: erro claro (ok False, tipo e mensagem citando a faixa, SEM svg) OU recuo ao processo único (SVG idêntico ao sem faixas). Nunca SVG parcial.
COMPARAÇÃO (escolha): conjunto de segmentos com tolerância 1e-6, não ordem de caminhos. Motivo: recortar na borda muda nº e ordem dos caminhos (o protótipo deu 38428 -> ~38615), e a
projeção só tem traço sem preenchimento, então a ordem não aparece no desenho. O SVG de base é partido nas mesmas bordas; traço duplicado ou faltando reprova. Grupos de corte e caixas:
texto idêntico por guid (não se sobrepõem); cabeçalho/estilo idênticos."""
from __future__ import annotations

import copy
import locale
import re
import xml.etree.ElementTree as ET

import pytest
from s06_t15o_aux import (C, EspiaoFilho, ExecutorEspiao, TX, casar, cortes_de, corte, desenho_geo, exigir_dict_igual, exigir_igual, faixas, id_de, itens_do_pedido,
                          local, modelo_oclusao, modelo_varios, pedido_de, recortar, segmentos)
from s05_conteudo_aux import _limpa  # noqa: F401  (autouse)

import obim_geometria.nucleos as N
from openbim_app.desenho import estilo


def _par(p, n=4, **extra):
    return desenho_geo.processar({**copy.deepcopy(p), "faixas": n, **extra})


@pytest.fixture
def varios(tmp_path):
    f, g, gid = modelo_varios()
    p = pedido_de(f, gid, tmp_path / "v")
    return f, g, gid, p, desenho_geo.processar(copy.deepcopy(p))


def test_faixas_4_igual_ao_processo_unico_com_peca_cruzando_a_borda(monkeypatch, varios):
    F = faixas()
    f, g, _gid, p, base = varios
    assert base["ok"] and {"P", "L", "Pil1", "M"} <= {f.by_id(i).Name for i in base["enviados"]}
    esp = EspiaoFilho(monkeypatch, F)
    r = _par(p, 4)
    exigir_dict_igual(base, r)
    assert len(esp.chamadas) >= 3, "o modelo tem de gerar ao menos 3 faixas"
    exigir_igual(base["svg"], r["svg"], cortes_de(esp.chamadas))
    for nome in ("P", "Vig"):  # peças que cruzam fronteiras vieram a mais de um filho (halo) e têm projeção dos dois lados da borda
        assert sum(id_de(f, g, nome) in [e[0] for e in c["elementos"]] for c in esp.chamadas) >= 2
    xs = [x for s in segmentos(r["svg"]) for (x, _y) in s]
    assert any(x < min(cortes_de(esp.chamadas)) - 0.1 for x in xs) and any(x > max(cortes_de(esp.chamadas)) + 0.1 for x in xs)


def test_oclusao_entre_faixas_nao_muda_o_desenho(monkeypatch, tmp_path):
    F = faixas()
    f, g, gid = modelo_oclusao(True)
    p = pedido_de(f, gid, tmp_path / "com")
    base = desenho_geo.processar(copy.deepcopy(p))
    esp = EspiaoFilho(monkeypatch, F)
    r = _par(p, 4)
    exigir_dict_igual(base, r)
    exigir_igual(base["svg"], r["svg"], cortes_de(esp.chamadas))
    atras, tampa = id_de(f, g, "Atras2"), id_de(f, g, "Tampa")
    filho = next(c for c in esp.chamadas if atras in c["faixa"]["donos"])
    assert tampa in [e[0] for e in filho["elementos"]] and tampa not in filho["faixa"]["donos"], "quem cobre vem de outra faixa, como halo"
    f2, _g2, gid2 = modelo_oclusao(False)  # sem a tampa o pilar aparece inteiro: a oclusão existe e conta
    sem = desenho_geo.processar(pedido_de(f2, gid2, tmp_path / "sem"))
    so_sem, _ = casar(segmentos(sem["svg"]), segmentos(base["svg"]))
    assert len(so_sem) >= 2, "a tampa esconde traços do pilar; sem ela eles aparecem"
    assert casar(segmentos(sem["svg"]), segmentos(r["svg"]))[0], "o resultado em faixas também esconde esses traços"


def test_n_um_ou_ausente_nao_gera_filhos(monkeypatch, varios):
    F = faixas()
    _f, _g, _gid, p, base = varios
    esp = EspiaoFilho(monkeypatch, F)
    r1 = _par(p, 1)
    assert esp.chamadas == [] and r1["svg"] == base["svg"] and r1["enviados"] == base["enviados"] and r1["caixas"] == base["caixas"]
    exigir_dict_igual(base, r1)


def test_n_maior_que_elementos_e_zero_elementos(monkeypatch, varios):
    F = faixas()
    _f, _g, _gid, p, base = varios
    esp = EspiaoFilho(monkeypatch, F)
    r = _par(p, 50)
    exigir_dict_igual(base, r)
    exigir_igual(base["svg"], r["svg"], cortes_de(esp.chamadas))
    assert 1 <= len(esp.chamadas) <= len(p["elementos"]) and all(c["elementos"] and c["faixa"]["donos"] for c in esp.chamadas)
    vazio = {**copy.deepcopy(p), "elementos": [], "caixas_coords": {}}
    esp2 = EspiaoFilho(monkeypatch, F)
    b0, r0 = desenho_geo.processar(copy.deepcopy(vazio)), desenho_geo.processar({**vazio, "faixas": 4})
    assert esp2.chamadas == [] and r0["ok"] == b0["ok"] and r0.get("svg") == b0.get("svg")


@pytest.mark.parametrize("n", [0, -2, True, 2.5, "4", None])
def test_faixas_invalidas_viram_erro_sem_filhos(monkeypatch, varios, n):
    F = faixas()
    p = varios[3]
    esp = EspiaoFilho(monkeypatch, F)
    r = desenho_geo.processar({**copy.deepcopy(p), "faixas": n})
    assert r["ok"] is False and r["erro"]["tipo"] == "FaixasInvalidas" and "svg" not in r and esp.chamadas == []


def test_gerar_corte_repassa_faixas_e_o_svg_sai_igual(monkeypatch):
    F = faixas()
    f, _g, gid = modelo_varios()
    e0, e4 = ExecutorEspiao(), ExecutorEspiao()
    c1 = corte.gerar_corte(f, gid, executor=e0)
    assert e0.pedidos_desenho[0].get("faixas", 1) == 1
    esp = EspiaoFilho(monkeypatch, F)
    c4 = corte.gerar_corte(f, gid, executor=e4, faixas=4)
    assert e4.pedidos_desenho[0]["faixas"] == 4 and len(esp.chamadas) >= 3
    assert c4.n_paths == len(re.findall(r"<path\b", c4.svg)) and c4.caixas == c1.caixas
    exigir_igual(c1.svg, c4.svg, cortes_de(esp.chamadas))
    for n in (0, -1, True, 2.5, "4"):
        e = ExecutorEspiao()
        with pytest.raises(ValueError):
            corte.gerar_corte(f, gid, executor=e, faixas=n)
        assert e.chamadas == []


def test_filho_recebe_so_a_sua_faixa_mais_o_halo(monkeypatch, varios):
    F = faixas()
    f, g, _gid, p, _base = varios
    esp = EspiaoFilho(monkeypatch, F)
    _par(p, 4)
    itens = {i: (u0, u1) for i, _g, u0, u1 in itens_do_pedido(p)}
    movel = id_de(f, g, "M")
    todos, vistos = {i for i, _ in p["elementos"]}, []
    for k, (ped, res) in enumerate(esp.ordenados()):
        a, b = ped["faixa"]["u0"], ped["faixa"]["u1"]
        assert "faixas" not in ped or ped["faixas"] == 1
        assert ped["arquivo"] == p["arquivo"] and ped["vista"] == p["vista"] and ped["elementos"] and 1 <= ped["threads"] <= p["threads"]
        esperado = {i for i, (u0, u1) in itens.items() if i != movel and (b is None or u0 <= b + 1e-6) and (a is None or u1 >= a - 1e-6)} | ({movel} if k == 0 else set())
        assert {e[0] for e in ped["elementos"]} == esperado, f"faixa {k}: só quem encosta nela (e o móvel na faixa 0)"
        donos = set(ped["faixa"]["donos"])
        centro = lambda i: sum(itens[i]) / 2  # noqa: E731
        assert donos == {i for i in itens if i != movel and (a is None or centro(i) >= a) and (b is None or centro(i) < b)} | ({movel} if k == 0 else set())
        assert donos <= esperado and not (donos & set(vistos))
        vistos += list(donos)
        xs = [x for s in segmentos(res["svg"]) for (x, _y) in s]
        assert all((a is None or x >= a + TX - 1e-6) and (b is None or x <= b + TX + 1e-6) for x in xs), "projeção recortada na faixa"
        guids_cortados = {m for m in re.findall(r'<g id="product-[^"]*"[^>]*?ifc:guid="([^"]+)"', res["svg"])}
        assert guids_cortados <= {f.by_id(i).GlobalId for i in donos}, "grupos de corte só dos donos"
        assert ("IfcFurniture" in res["svg"]) == (k == 0), "caixa 2D do móvel só na faixa 0"
    assert sorted(vistos) == sorted(todos), "os donos particionam todos os elementos"


@pytest.mark.parametrize("t", [1, 2, 4])
def test_no_maximo_threads_filhos_juntos(monkeypatch, varios, t):
    F = faixas()
    monkeypatch.setattr(N, "nucleos_fisicos", lambda: 8)
    esp = EspiaoFilho(monkeypatch, F, atraso=0.15)
    r = _par(varios[3], 4, threads=t)
    n = len(esp.chamadas)
    assert r["ok"] and n >= 3
    assert esp.max_ativos == min(n, t), f"{n} faixas com threads={t}: {esp.max_ativos} filhos simultâneos"
    assert all(1 <= c["threads"] and c["threads"] * esp.max_ativos <= t for c in esp.chamadas), "filhos não passam das threads pedidas, somados"


@pytest.mark.parametrize("modo", ["raise", "ok_false"])
def test_faixa_que_falha_da_erro_claro_ou_recua_sem_svg_parcial(monkeypatch, varios, modo):
    F = faixas()
    base = varios[4]
    EspiaoFilho(monkeypatch, F, falha=lambda c: modo if c["faixa"]["u1"] is None else None)
    r = _par(varios[3], 4)  # não levanta
    if r["ok"]:
        assert r["svg"] == base["svg"], "recuo ao processo único tem de dar o desenho completo"
    else:
        assert not r.get("svg") and r["erro"]["tipo"] and "faixa" in r["erro"]["mensagem"].lower()


def test_filho_real_que_morre_nao_trava_nem_devolve_parcial(monkeypatch, varios):
    faixas()
    base = varios[4]
    monkeypatch.setenv("OBIM_TESTE_AUX_SAIR", "3")  # `processo.entrada` sai com código 3 antes de responder
    r = _par(varios[3], 2)
    assert (r["ok"] and r["svg"] == base["svg"]) or (not r["ok"] and not r.get("svg") and r["erro"]["mensagem"])


def test_estilo_funciona_no_svg_unido(monkeypatch, varios):
    F = faixas()
    base = varios[4]
    esp = EspiaoFilho(monkeypatch, F)
    r = _par(varios[3], 4)
    assert ET.fromstring(r["svg"]).tag.endswith("svg") and esp.chamadas
    sb, sp = estilo.aplicar_estilo(base["svg"], "1:100"), estilo.aplicar_estilo(r["svg"], "1:100")
    assert ET.fromstring(sp).tag.endswith("svg") and sp.count("<g ") == sb.count("<g ")
    cortes = cortes_de(esp.chamadas)
    so_b, so_p = casar(recortar(segmentos(sb), cortes), recortar(segmentos(sp), cortes))
    assert not so_b and not so_p, "estilo no SVG unido dá o mesmo desenho que no SVG único"


@pytest.mark.parametrize("real", [False, True])
def test_independe_de_lc_numeric(monkeypatch, varios, real):
    """Em processo: a localidade pt_BR já bagunça o cabeçalho do motor (vírgula decimal em ifc:plane/matrix3), então a base é calculada NA MESMA localidade e as faixas não podem
    depender de ler esses números (o TX sai do viewBox ou da câmera). Com filhos reais (spawn, env pt_BR): o resultado tem de ser o da base em C."""
    F = faixas()
    f, g, _gid, p, base = varios
    if real:
        monkeypatch.setenv("LC_NUMERIC", "pt_BR.utf8")
        monkeypatch.setenv("LANG", "pt_BR.utf8")
        lims = F.limites(itens_do_pedido(p), 2, so_primeira=[id_de(f, g, "M")])
        r = _par(p, 2)
        assert r["ok"], r.get("erro")
        exigir_igual(base["svg"], r["svg"], [b + TX for _a, b in lims if b is not None])
        return
    try:
        locale.setlocale(locale.LC_NUMERIC, "pt_BR.utf8")
    except locale.Error:
        pytest.skip("sem a localidade pt_BR.utf8 nesta máquina")
    try:
        base_loc = desenho_geo.processar(copy.deepcopy(p))
        esp = EspiaoFilho(monkeypatch, F)
        r = _par(p, 4)
        assert r["ok"], r.get("erro")
        exigir_igual(base_loc["svg"], r["svg"], cortes_de(esp.chamadas))
    finally:
        locale.setlocale(locale.LC_NUMERIC, "C")


def test_sem_caixas_coords_o_resultado_continua_igual(monkeypatch, varios):
    F = faixas()
    p = copy.deepcopy(varios[3])
    p.pop("caixas_coords")
    base = desenho_geo.processar(copy.deepcopy(p))
    esp = EspiaoFilho(monkeypatch, F)
    r = _par(p, 4)
    exigir_dict_igual(base, r)
    exigir_igual(base["svg"], r["svg"], cortes_de(esp.chamadas))
