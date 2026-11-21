# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oraculo F0-S06-T24l: abrir IFC com `lazy=True` somente no caminho da planta pelo cache.

Alvo (NAO editar este arquivo): `desenho.py` (e `persistente.py::_abrir_mantido` se precisar aceitar `lazy`).
Contrato:
1. Planta pelo cache (`pasta_cache_geometria` presente/nao vazia, nao `CORTE`, nao `faixa`): abre via
   `ifcopenshell.open(caminho, lazy=True)`; resposta (SVG byte a byte/SHA e campos fora `tempos`) identica
   ao nao-lazy; 1 abertura no acerto (tambem com `componentes`/`faixas`).
2. Fora do cache (`CORTE`, `faixa`, sem `pasta_cache_geometria`, `_processar_base`, `persistente.servir`):
   nunca chama `ifcopenshell.open(..., lazy=True)`; `persistente` mantem 1 abertura normal e atende cache.
3. Queda (`via_cache=False` com `queda`): motor antigo (`_processar_base`, `_planta_em_faixas`,
   `_planta_por_componentes` e filhos) recebe `f` NORMAL (`f.lazy_loading() is False`), resultado identico.
4. `processar_lote` (`_abrir_ifc`): chave inclui `lazy`; nunca mistura `lazy` com normal para o mesmo
   `(caminho, pavimento)`, reaproveita dentro do mesmo modo e zera `_ARQ_LOTE` ao fim.
5. Assinatura publica de `processar`/`processar_lote` inalterada; nao muta `pedido`; determinismo SHA 3x.
"""
from __future__ import annotations

import copy
import hashlib
import inspect
import json

import ifcopenshell
import numpy as np
import pytest

from obim_geometria import cache_geometria as C
from obim_geometria import desenho, persistente
from test_s06_t24b_despacho_cache_oraculo import _criar_cena, _pedido_corte, _sql
from test_s06_t24b_despacho_cache_oraculo2 import _criar_cena_3_componentes, _instalar_filho_inprocess

_dc = copy.deepcopy


def _suporta_lazy() -> bool:
    try:
        return "lazy" in inspect.signature(ifcopenshell.open).parameters
    except (TypeError, ValueError):
        return False


_SKIP_SEM_LAZY = pytest.mark.skipif(not _suporta_lazy(), reason="ifcopenshell.open nao suporta lazy=True (requer >= 0.9.0)")
_sha_svg = lambda resp: hashlib.sha256(resp["svg"].encode("utf-8")).hexdigest()
_sem_tempos = lambda resp: {k: v for k, v in resp.items() if k != "tempos"}
_is_lazy = lambda f: bool(fn()) if callable(fn := getattr(f, "lazy_loading", None)) else bool(fn)


def _espiar_open(monkeypatch) -> list[dict]:
    chamadas, orig = [], ifcopenshell.open
    def wrap(*args, **kwargs):
        f = orig(*args, **kwargs)
        chamadas.append({"args": args, "kwargs": dict(kwargs), "lazy": bool(kwargs.get("lazy", False)), "f": f, "f_lazy": _is_lazy(f)})
        return f
    monkeypatch.setattr(ifcopenshell, "open", wrap)
    return chamadas


def _rodar_sem_lazy(monkeypatch, fn, *args, **kwargs):
    orig = ifcopenshell.open
    with monkeypatch.context() as mp:
        mp.setattr(ifcopenshell, "open", lambda *a, **k: orig(*a, **{ck: cv for ck, cv in k.items() if ck != "lazy"}))
        return fn(*args, **kwargs)


def _espiar_f(monkeypatch, attr: str, chamadas: list[dict] | None = None):
    vistos, aberturas, orig = [], [], getattr(desenho, attr)
    def wrap(*a, **k):
        antes = len(chamadas) if chamadas is not None else 0
        vistos.append(k.get("f") if ("f" in k or attr != "_desenhar_planta_cache") else (a[0] if a else None))
        try:
            return orig(*a, **k)
        finally:
            if chamadas is not None:
                aberturas.extend(chamadas[antes:])
    monkeypatch.setattr(desenho, attr, wrap)
    return (vistos, aberturas) if chamadas is not None else vistos


# (1) Caminho do cache: lazy=True e igualdade byte a byte
@_SKIP_SEM_LAZY
def test_planta_cache_abre_com_lazy_e_resposta_identica_ao_nao_lazy(tmp_path, monkeypatch):
    cena = _criar_cena(tmp_path, com_sem_rep=True)
    r_ref = _rodar_sem_lazy(monkeypatch, desenho.processar, _dc(cena.pedido_cache))
    assert r_ref["ok"] is True and r_ref["via_cache"] is True and r_ref["queda"] is None
    for valor_pasta in (str(cena.pasta), cena.pasta):
        chamadas, fs_cache = _espiar_open(monkeypatch), _espiar_f(monkeypatch, "_desenhar_planta_cache")
        r = desenho.processar({**_dc(cena.pedido_base), "pasta_cache_geometria": valor_pasta})
        assert r["ok"] is True and r["via_cache"] is True and r["queda"] is None and r["n_faltantes"] == 0
        assert len(chamadas) == 1 and chamadas[0]["kwargs"].get("lazy") is True and chamadas[0]["f_lazy"] is True
        assert len(fs_cache) == 1 and _is_lazy(fs_cache[0]) is True
        assert r["svg"].encode("utf-8") == r_ref["svg"].encode("utf-8") and _sha_svg(r) == _sha_svg(r_ref)
        assert _sem_tempos(r) == _sem_tempos(r_ref) and set(r["tempos"]) == set(r_ref["tempos"])
        assert all(isinstance(v, float) and v >= 0.0 for v in r["tempos"].values())


@_SKIP_SEM_LAZY
@pytest.mark.parametrize("extra", [{"componentes": True}, {"faixas": 2}], ids=["componentes", "faixas"])
def test_planta_cache_com_componentes_ou_faixas_abre_com_lazy_no_acerto(tmp_path, monkeypatch, extra):
    cena = _criar_cena(tmp_path)
    ped = {**_dc(cena.pedido_cache), **extra}
    r_ref = _rodar_sem_lazy(monkeypatch, desenho.processar, _dc(ped))
    assert r_ref["ok"] is True and r_ref["via_cache"] is True
    chamadas = _espiar_open(monkeypatch)
    r = desenho.processar(_dc(ped))
    assert r["ok"] is True and r["via_cache"] is True and r["queda"] is None
    assert len(chamadas) == 1 and chamadas[0]["kwargs"].get("lazy") is True and chamadas[0]["f_lazy"] is True
    assert r["svg"].encode("utf-8") == r_ref["svg"].encode("utf-8") and _sem_tempos(r) == _sem_tempos(r_ref)


# (2) Fora do cache e queda -> arquivo normal
@_SKIP_SEM_LAZY
def test_corte_nao_usa_lazy_mesmo_com_pasta_cache(tmp_path, monkeypatch):
    cena = _criar_cena(tmp_path)
    ped_sem = {k: v for k, v in _pedido_corte(cena, cena.pasta).items() if k != "pasta_cache_geometria"}
    ref = desenho.processar(_dc(ped_sem))
    chamadas, fs_base = _espiar_open(monkeypatch), _espiar_f(monkeypatch, "_processar_base")
    r_com, r_inex = desenho.processar(_pedido_corte(cena, cena.pasta)), desenho.processar(_pedido_corte(cena, tmp_path / "sem"))
    assert all(r["ok"] is True and "via_cache" not in r and r["svg"] == ref["svg"] for r in (r_com, r_inex))
    assert len(chamadas) == 2 and all(not c["lazy"] and not c["f_lazy"] for c in chamadas)
    assert len(fs_base) == 2 and all(not _is_lazy(f) for f in fs_base)


@_SKIP_SEM_LAZY
def test_faixa_unica_nao_usa_lazy_mesmo_com_pasta_cache(tmp_path, monkeypatch):
    cena = _criar_cena(tmp_path)
    faixa = {"u0": -1.0, "u1": 10.0, "donos": [e.id() for e in cena.validos]}
    ref = desenho.processar({**_dc(cena.pedido_base), "faixa": faixa})
    chamadas, fs_rec = _espiar_open(monkeypatch), _espiar_f(monkeypatch, "_planta_recortada")
    r = desenho.processar({**_dc(cena.pedido_cache), "faixa": faixa})
    assert r["ok"] is True and "via_cache" not in r and r["svg"] == ref["svg"]
    assert len(chamadas) == 1 and not chamadas[0]["lazy"] and not chamadas[0]["f_lazy"]
    assert len(fs_rec) == 1 and not _is_lazy(fs_rec[0])


@_SKIP_SEM_LAZY
@pytest.mark.parametrize("valor_pasta", ["__AUSENTE__", None, ""], ids=["ausente", "none", "vazio"])
def test_planta_sem_pasta_cache_nao_usa_lazy(tmp_path, monkeypatch, valor_pasta):
    cena = _criar_cena(tmp_path)
    ped = _dc(cena.pedido_base) if valor_pasta == "__AUSENTE__" else {**_dc(cena.pedido_base), "pasta_cache_geometria": valor_pasta}
    chamadas, fs_base = _espiar_open(monkeypatch), _espiar_f(monkeypatch, "_processar_base")
    r = desenho.processar(ped)
    assert r["ok"] is True and "via_cache" not in r
    assert len(chamadas) == 1 and not chamadas[0]["lazy"] and not chamadas[0]["f_lazy"]
    assert len(fs_base) == 1 and not _is_lazy(fs_base[0])


@_SKIP_SEM_LAZY
def test_processar_base_direto_nao_usa_lazy(tmp_path, monkeypatch):
    cena = _criar_cena(tmp_path)
    chamadas = _espiar_open(monkeypatch)
    assert desenho._processar_base(_dc(cena.pedido_cache))["ok"] is True
    assert len(chamadas) == 1 and not chamadas[0]["lazy"] and not chamadas[0]["f_lazy"]


@_SKIP_SEM_LAZY
def test_persistente_abre_normal_e_atende_pedido_com_pasta_cache(tmp_path, monkeypatch):
    cena = _criar_cena(tmp_path)
    ref_cache = _rodar_sem_lazy(monkeypatch, desenho.processar, _dc(cena.pedido_cache))
    ref_base = _rodar_sem_lazy(monkeypatch, desenho.processar, _dc(cena.pedido_base))
    chamadas, resps = _espiar_open(monkeypatch), []
    fila = [json.dumps(x).encode("utf-8") for x in (
        {"op": "desenho", "numero": 1, **_dc(cena.pedido_cache)},
        {"op": "desenho", "numero": 2, **_dc(cena.pedido_base)},
        {"op": "encerrar"},
    )]
    tx = type("Tx", (), {"send_bytes": lambda _s, b: resps.append(m) if (m := json.loads(b)).get("tipo") == "resposta" else None, "close": lambda _s: None})()
    rx = type("Rx", (), {"recv_bytes": lambda _s: fila.pop(0) if fila else (_ for _ in ()).throw(EOFError)})()
    persistente.servir(tx, rx)
    assert len(chamadas) == 1 and not chamadas[0]["lazy"] and not chamadas[0]["f_lazy"] and len(resps) == 2
    r1, r2 = resps[0]["dados"], resps[1]["dados"]
    assert r1["ok"] is True and r1["via_cache"] is True and r1["svg"] == ref_cache["svg"]
    assert r2["ok"] is True and "via_cache" not in r2 and r2["svg"] == ref_base["svg"]


@_SKIP_SEM_LAZY
@pytest.mark.parametrize("caso,queda_esperada", [
    ("cache_ausente", "cache_ausente"),
    ("cache_invalido_lixo", "cache_invalido"),
    ("cache_invalido_cabecalho", "cache_invalido"),
    ("cache_incompleto", "cache_incompleto"),
    ("opcoes_incompativeis", "opcoes_incompativeis"),
    ("queda_gancho", "secao_aberta"),
    ("queda_excecao", "erro_motor"),
])
def test_queda_entrega_arquivo_normal_ao_motor_antigo_e_resultado_identico(tmp_path, monkeypatch, caso, queda_esperada):
    cena = _criar_cena(tmp_path)
    ped_base = {**_dc(cena.pedido_base), **({"moveis_como_caixa": True} if caso == "opcoes_incompativeis" else {})}
    base = _rodar_sem_lazy(monkeypatch, desenho.processar, _dc(ped_base))
    assert base["ok"] is True
    ped = _dc(cena.pedido_cache)
    if caso == "cache_ausente":
        ped["pasta_cache_geometria"] = str(tmp_path / "nao_existe")
    elif caso == "cache_invalido_lixo":
        pasta_lixo = tmp_path / "lixo"
        pasta_lixo.mkdir()
        (pasta_lixo / C.NOME_BANCO).write_bytes(b"lixo-nao-sqlite")
        ped["pasta_cache_geometria"] = str(pasta_lixo)
    elif caso == "cache_invalido_cabecalho":
        pasta_div = tmp_path / "cab_div"
        with C.abrir_cache(pasta_div, C.cabecalho_atual(tesselacao={})) as cb:
            cb.gravar_forma("s", np.zeros((3, 3), np.float64), np.array([[0, 1, 2]], np.int32))
        ped["pasta_cache_geometria"] = str(pasta_div)
    elif caso == "cache_incompleto":
        _sql(cena.pasta, "DELETE FROM ocorrencias WHERE global_id = ?", (cena.movel.GlobalId,))
    elif caso == "opcoes_incompativeis":
        ped["moveis_como_caixa"] = True
    elif caso == "queda_gancho":
        monkeypatch.setattr(desenho, "_desenhar_planta_cache", lambda *a: (None, "secao_aberta"))
    elif caso == "queda_excecao":
        monkeypatch.setattr(desenho, "_desenhar_planta_cache", lambda *a: (_ for _ in ()).throw(RuntimeError("boom")))
    chamadas = _espiar_open(monkeypatch)
    fs_base, aberturas_motor = _espiar_f(monkeypatch, "_processar_base", chamadas)
    resp = desenho.processar(ped)
    assert resp["ok"] is True and resp["via_cache"] is False and resp["queda"] == queda_esperada
    assert len(fs_base) == 1 and fs_base[0] is not None and not _is_lazy(fs_base[0])
    assert any(not c["lazy"] and not c["f_lazy"] for c in chamadas)
    assert all(not c["lazy"] and not c["f_lazy"] for c in aberturas_motor)
    assert resp["svg"] == base["svg"] and resp["n_paths"] == base["n_paths"]
    assert resp["enviados"] == base["enviados"] and resp["falhas_geometria"] == base["falhas_geometria"]


@_SKIP_SEM_LAZY
@pytest.mark.parametrize(
    "extra,attr_motor",
    [({"componentes": True}, "_planta_por_componentes"), ({"faixas": 2}, "_planta_em_faixas")],
    ids=["componentes", "faixas"],
)
def test_queda_em_componentes_e_faixas_entrega_normal_ao_motor_e_filhos(tmp_path, monkeypatch, extra, attr_motor):
    cena = _criar_cena_3_componentes(tmp_path)
    _instalar_filho_inprocess(monkeypatch)
    base = _rodar_sem_lazy(monkeypatch, desenho.processar, {**_dc(cena.pedido_base), **extra})
    assert base["ok"] is True
    monkeypatch.setattr(desenho, "_desenhar_planta_cache", lambda *a: (None, "secao_aberta"))
    chamadas = _espiar_open(monkeypatch)
    fs_motor, aberturas_motor = _espiar_f(monkeypatch, attr_motor, chamadas)
    resp = desenho.processar({**_dc(cena.pedido_base), **extra, "pasta_cache_geometria": str(cena.pasta)})
    assert resp["ok"] is True and resp["via_cache"] is False and resp["queda"] == "secao_aberta"
    assert len(fs_motor) == 1 and fs_motor[0] is not None and not _is_lazy(fs_motor[0])
    assert all(not c["lazy"] and not c["f_lazy"] for c in aberturas_motor) and resp["svg"] == base["svg"]


@_SKIP_SEM_LAZY
def test_conferir_elementos_divergente_com_pasta_cache_preserva_erro(tmp_path, monkeypatch):
    cena = _criar_cena(tmp_path)
    ped_ruim = {**_dc(cena.pedido_cache), "elementos": [(cena.parede.id(), "GUID-ERRADO-NAO-CONFERE")]}
    ref = _rodar_sem_lazy(monkeypatch, desenho.processar, _dc(ped_ruim))
    r = desenho.processar(_dc(ped_ruim))
    assert r["ok"] is False and ref["ok"] is False and r["erro"]["tipo"] == ref["erro"]["tipo"] == "ArquivoDivergente"


# (3) processar_lote: chave inclui lazy
@_SKIP_SEM_LAZY
def test_lote_nao_mistura_arquivo_lazy_com_normal_mesmo_pavimento(tmp_path, monkeypatch):
    cena = _criar_cena(tmp_path)
    ref_cache = _rodar_sem_lazy(monkeypatch, desenho.processar, _dc(cena.pedido_cache))
    ref_norm = _rodar_sem_lazy(monkeypatch, desenho.processar, _dc(cena.pedido_base))
    chamadas = _espiar_open(monkeypatch)
    fs_cache, fs_base = _espiar_f(monkeypatch, "_desenhar_planta_cache"), _espiar_f(monkeypatch, "_processar_base")
    r = desenho.processar_lote({"op": "desenho_lote", "pedidos": [_dc(cena.pedido_cache), _dc(cena.pedido_base)]})
    assert desenho._ARQ_LOTE is None and r["ok"] is True and len(r["resultados"]) == 2
    rc, rn = r["resultados"]
    assert rc["ok"] is True and rc["via_cache"] is True and rc["svg"] == ref_cache["svg"]
    assert rn["ok"] is True and "via_cache" not in rn and rn["svg"] == ref_norm["svg"]
    assert len(chamadas) == 2 and chamadas[0]["kwargs"].get("lazy") is True and chamadas[0]["f_lazy"] is True
    assert not chamadas[1]["lazy"] and not chamadas[1]["f_lazy"]
    assert len(fs_cache) == 1 and len(fs_base) == 1 and _is_lazy(fs_cache[0]) is True and not _is_lazy(fs_base[0])
    assert fs_cache[0] is not fs_base[0]


@_SKIP_SEM_LAZY
def test_lote_ordem_inversa_normal_depois_cache_nao_mistura_chaves(tmp_path, monkeypatch):
    cena = _criar_cena(tmp_path)
    chamadas = _espiar_open(monkeypatch)
    fs_cache, fs_base = _espiar_f(monkeypatch, "_desenhar_planta_cache"), _espiar_f(monkeypatch, "_processar_base")
    r = desenho.processar_lote({"op": "desenho_lote", "pedidos": [_dc(cena.pedido_base), _dc(cena.pedido_cache)]})
    assert desenho._ARQ_LOTE is None and r["ok"] is True and [x["ok"] for x in r["resultados"]] == [True, True]
    assert len(chamadas) == 2 and not chamadas[0]["lazy"] and not chamadas[0]["f_lazy"]
    assert chamadas[1]["kwargs"].get("lazy") is True and chamadas[1]["f_lazy"] is True
    assert not _is_lazy(fs_base[0]) and _is_lazy(fs_cache[0]) is True and fs_base[0] is not fs_cache[0]


@_SKIP_SEM_LAZY
def test_lote_reaproveita_lazy_e_normal_separadamente(tmp_path, monkeypatch):
    cena = _criar_cena(tmp_path)
    chamadas = _espiar_open(monkeypatch)
    fs_cache, fs_base = _espiar_f(monkeypatch, "_desenhar_planta_cache"), _espiar_f(monkeypatch, "_processar_base")
    pedidos = [_dc(p) for p in (cena.pedido_cache, cena.pedido_cache, cena.pedido_base, cena.pedido_base)]
    r = desenho.processar_lote({"op": "desenho_lote", "pedidos": pedidos})
    assert desenho._ARQ_LOTE is None and r["ok"] is True and [x["ok"] for x in r["resultados"]] == [True] * 4
    assert len(chamadas) == 2 and chamadas[0]["kwargs"].get("lazy") is True and not chamadas[1]["lazy"]
    assert len(fs_cache) == 2 and fs_cache[0] is fs_cache[1] and _is_lazy(fs_cache[0]) is True
    assert len(fs_base) == 2 and fs_base[0] is fs_base[1] and not _is_lazy(fs_base[0])


@_SKIP_SEM_LAZY
def test_lote_com_queda_abre_lazy_e_reaproveita_normal_sem_vazar_lazy(tmp_path, monkeypatch):
    cena = _criar_cena(tmp_path)
    monkeypatch.setattr(desenho, "_desenhar_planta_cache", lambda *a: (None, "secao_aberta"))
    chamadas, fs_base = _espiar_open(monkeypatch), _espiar_f(monkeypatch, "_processar_base")
    r = desenho.processar_lote({"op": "desenho_lote", "pedidos": [_dc(cena.pedido_cache), _dc(cena.pedido_base)]})
    assert desenho._ARQ_LOTE is None and r["ok"] is True and [x["ok"] for x in r["resultados"]] == [True, True]
    assert r["resultados"][0]["via_cache"] is False and r["resultados"][0]["queda"] == "secao_aberta"
    assert len(chamadas) == 2 and chamadas[0]["kwargs"].get("lazy") is True and not chamadas[1]["lazy"]
    assert len(fs_base) == 2 and fs_base[0] is fs_base[1] and not _is_lazy(fs_base[0])


# (4) Assinatura, imutabilidade, determinismo
def test_assinatura_publica_processar_e_processar_lote_inalterada():
    for fn in (desenho.processar, desenho.processar_lote):
        params = list(inspect.signature(fn).parameters.values())
        assert [p.name for p in params] == ["pedido", "fase"]
        assert params[0].kind is inspect.Parameter.POSITIONAL_OR_KEYWORD and params[0].default is inspect.Parameter.empty
        assert params[1].kind is inspect.Parameter.POSITIONAL_OR_KEYWORD and params[1].default is None


def test_nao_mutar_pedido_em_acerto_queda_e_sem_cache(tmp_path, monkeypatch):
    cena = _criar_cena(tmp_path)
    for ped_orig in (_dc(cena.pedido_cache), _dc(cena.pedido_base), {**_dc(cena.pedido_base), "pasta_cache_geometria": str(tmp_path / "aus")}):
        snap = _dc(ped_orig)
        assert desenho.processar(ped_orig)["ok"] is True and ped_orig == snap
    ped_queda, snap_q = _dc(cena.pedido_cache), _dc(cena.pedido_cache)
    monkeypatch.setattr(desenho, "_desenhar_planta_cache", lambda *a: (None, "secao_aberta"))
    rq = desenho.processar(ped_queda)
    assert rq["ok"] is True and rq["via_cache"] is False and ped_queda == snap_q


@_SKIP_SEM_LAZY
def test_determinismo_sha_3_rodadas_caminho_cache(tmp_path, monkeypatch):
    cena = _criar_cena(tmp_path, com_sem_rep=True)
    ref = _rodar_sem_lazy(monkeypatch, desenho.processar, _dc(cena.pedido_cache))
    sha_ref = _sha_svg(ref)
    rodadas = [desenho.processar(_dc(cena.pedido_cache)) for _ in range(3)]
    assert all(r["ok"] is True and r["via_cache"] is True for r in rodadas)
    assert [_sha_svg(r) for r in rodadas] == [sha_ref, sha_ref, sha_ref]
    assert all(_sem_tempos(r) == _sem_tempos(ref) for r in rodadas)


# (5) Mutantes plausiveis
@_SKIP_SEM_LAZY
def test_mutante_usar_lazy_fora_do_caminho_cache(tmp_path, monkeypatch):
    """Mata mutante que abre com lazy=True fora do caminho da planta pelo cache."""
    cena = _criar_cena(tmp_path)
    chamadas = _espiar_open(monkeypatch)
    faixa = {"u0": -1.0, "u1": 10.0, "donos": [e.id() for e in cena.validos]}
    assert desenho.processar(_dc(cena.pedido_base))["ok"] is True
    assert desenho.processar({**_dc(cena.pedido_base), "pasta_cache_geometria": ""})["ok"] is True
    assert desenho.processar(_pedido_corte(cena, cena.pasta))["ok"] is True
    assert desenho.processar({**_dc(cena.pedido_cache), "faixa": faixa})["ok"] is True
    assert desenho._processar_base(_dc(cena.pedido_cache))["ok"] is True
    assert len(chamadas) == 5 and all(not c["lazy"] and not c["f_lazy"] for c in chamadas)


@_SKIP_SEM_LAZY
def test_mutante_motor_antigo_recebe_arquivo_lazy_na_queda(tmp_path, monkeypatch):
    """Mata mutante que reaproveita o arquivo lazy na queda sem reabrir normal para o motor antigo."""
    cena = _criar_cena(tmp_path)
    base = _rodar_sem_lazy(monkeypatch, desenho.processar, _dc(cena.pedido_base))
    fs_base = _espiar_f(monkeypatch, "_processar_base")
    with monkeypatch.context() as mp:
        mp.setattr(desenho, "_desenhar_planta_cache", lambda *a: (None, "secao_aberta"))
        r1 = desenho.processar(_dc(cena.pedido_cache))
    assert r1["ok"] is True and r1["via_cache"] is False and r1["svg"] == base["svg"]
    _sql(cena.pasta, "DELETE FROM ocorrencias WHERE global_id = ?", (cena.movel.GlobalId,))
    r2 = desenho.processar(_dc(cena.pedido_cache))
    assert r2["ok"] is True and r2["via_cache"] is False and r2["svg"] == base["svg"]
    assert len(fs_base) == 2 and all(f is not None and not _is_lazy(f) for f in fs_base)


@_SKIP_SEM_LAZY
def test_mutante_lote_devolve_arquivo_lazy_para_chamada_normal(tmp_path, monkeypatch):
    """Mata mutante em que a chave de `_abrir_ifc` no lote omite `lazy` e entrega lazy ao normal."""
    cena = _criar_cena(tmp_path)
    fs_cache, fs_base = _espiar_f(monkeypatch, "_desenhar_planta_cache"), _espiar_f(monkeypatch, "_processar_base")
    r = desenho.processar_lote({"op": "desenho_lote", "pedidos": [_dc(cena.pedido_cache), _dc(cena.pedido_base)]})
    assert r["ok"] is True and all(x["ok"] for x in r["resultados"])
    assert len(fs_cache) == 1 and _is_lazy(fs_cache[0]) is True
    assert len(fs_base) == 1 and not _is_lazy(fs_base[0]) and fs_base[0] is not fs_cache[0]


@_SKIP_SEM_LAZY
def test_mutante_resposta_difere_do_nao_lazy(tmp_path, monkeypatch):
    """Mata mutante em que o caminho lazy produz SVG ou metadados diferentes da abertura normal."""
    cena = _criar_cena(tmp_path, com_sem_rep=True)
    ref = _rodar_sem_lazy(monkeypatch, desenho.processar, _dc(cena.pedido_cache))
    atual = desenho.processar(_dc(cena.pedido_cache))
    assert atual["ok"] is True and ref["ok"] is True
    assert atual["svg"].encode("utf-8") == ref["svg"].encode("utf-8") and _sha_svg(atual) == _sha_svg(ref)
    for campo in ("n_paths", "enviados", "caixas", "em_cache", "pesados", "falhas_geometria", "secoes_parciais", "via_cache", "queda", "n_faltantes"):
        assert atual[campo] == ref[campo], f"campo {campo} divergiu"
