# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo F0-S06-T18b-2 (`openbim_app.desenho.refino.refinar_pesados`): refino das peças pesadas uma a uma (ordem crescente de faces), cache por peça, falha isolada,
cancelamento, progresso/`ao_refinar`, entradas intactas e SVG final igual ao exato quando a peça não tem oclusão."""
from __future__ import annotations

import copy
import re
import threading

import pytest
import s06_t07_aux as X
from s05_conteudo_aux import _limpa  # noqa: F401  (autouse)
from s06_t18a_aux import densificar, modelo_denso, pedido_planta
from s06_t18a_malha import cilindro

import obim_geometria.local as L
import obim_geometria.pecas as P
from openbim_app.desenho.auxiliar import DesenhoCancelado
from openbim_app.desenho.cache import CacheDesenho
from openbim_app.desenho.refino import refinar_pesados

OP = dict(pesados="silhueta", limiar_pesado=50)


@pytest.fixture(scope="module")
def cena(tmp_path_factory):
    """Modelo com 3 pesadas separadas (24, 14 e 40 lados => 92, 52 e 156 faces (limiar 50)), pedido e resultado reais com silhuetas, e o SVG exato (sem a opção)."""
    pasta = tmp_path_factory.mktemp("t18b2")
    f, g, v, mov, _p = modelo_denso(24)
    pav = f.by_type("IfcBuildingStorey")[0]
    extras = [densificar(f, X.caixa(f, "IfcBuildingElementProxy", f"N{n}", 2.0 + 2 * i, 3.5, 0.0, 0.6, 0.6, 1.5), cilindro(0.3, n)) for i, n in enumerate((14, 40))]
    X.conter(f, pav, *extras)
    p = pedido_planta(f, v, pasta / "a")
    p.update(OP)
    r = L.executar(p)
    assert r.get("ok"), r
    base = L.executar({k: x for k, x in p.items() if k not in OP})
    assert base.get("ok"), base
    return f, p, r, base["svg"], {e.GlobalId: e.id() for e in [mov, *extras]}


def _exato(pedido):
    """Executor falso: devolve o grupo 'exato' da única peça do pedido (marca `data-fake`)."""
    assert len(pedido["elementos"]) == 1 and "pesados" not in pedido
    gid = pedido["elementos"][0][1]
    return {"ok": True, "tempos": {}, "svg": f'<svg xmlns:ifc="x"><g class="IfcFurniture" ifc:guid="{gid}" data-fake="1"><path d="M 0,0 L 1,0 L 1,1 Z"/></g></svg>'}


class Espiao:
    def __init__(self, falha=(), explode=(), depois=None):
        self.guids, self.falha, self.explode, self.depois = [], set(falha), set(explode), depois

    def __call__(self, pedido):
        gid = pedido["elementos"][0][1]
        self.guids.append(gid)
        if self.depois:
            self.depois(len(self.guids))
        if gid in self.falha:
            return {"ok": False, "erro": {"tipo": "X", "mensagem": "quebrou", "rastro": ""}}
        if gid in self.explode:
            raise RuntimeError("explodiu")
        return _exato(pedido)


def _ordem(r):
    return [d["guid"] for d in sorted(r["pesados"], key=lambda d: d["faces"])]


def _sil(svg):
    return re.findall(r'<g\b[^>]*data-silhueta="1"', svg)


def test_ordem_crescente_de_faces_mesmo_com_entrada_embaralhada(cena):
    f, p, r, _b, _ids = cena
    assert len(r["pesados"]) == 3 and len(_sil(r["svg"])) == 3
    r2 = copy.deepcopy(r)
    r2["pesados"].reverse()
    esp = Espiao()
    out = refinar_pesados(f, p, r2, executor=esp)
    assert esp.guids == _ordem(r)
    assert out["refinadas"] == _ordem(r) and out["falhas_refino"] == [] and out["em_cache"] == []
    assert not _sil(out["svg"]) and out["svg"].count('data-fake="1"') == 3


def test_nao_muta_entradas_e_devolve_copia(cena):
    f, p, r, _b, _ids = cena
    p0, r0 = copy.deepcopy(p), copy.deepcopy(r)
    out = refinar_pesados(f, p, r, executor=Espiao())
    assert p == p0 and r == r0 and out is not r and "refinadas" not in r
    assert {k: v for k, v in out.items() if k not in ("svg", "refinadas", "em_cache", "falhas_refino")} == {k: v for k, v in r.items() if k not in ("svg", "em_cache")}


def test_cache_miss_guarda_e_segunda_chamada_e_hit(cena, tmp_path):
    f, p, r, _b, ids = cena
    cache = CacheDesenho(tmp_path / "c")
    e1 = Espiao()
    o1 = refinar_pesados(f, p, r, executor=e1, cache=cache)
    assert len(e1.guids) == 3 and o1["em_cache"] == []
    for gid, i in ids.items():  # chave de UMA peça
        assert cache.obter(cache.chave(f, P.pedido_peca(p, i))) is not None
    e2 = Espiao()
    o2 = refinar_pesados(f, p, r, executor=e2, cache=cache)
    assert e2.guids == [] and sorted(o2["em_cache"]) == sorted(o1["refinadas"]) and o2["refinadas"] == o1["refinadas"]
    assert o2["svg"] == o1["svg"]


def test_falha_de_uma_peca_mantem_silhueta_e_as_outras_refinam(cena, tmp_path):
    f, p, r, _b, _ids = cena
    ordem = _ordem(r)
    for esp in (Espiao(falha=[ordem[1]]), Espiao(explode=[ordem[1]])):
        cache = CacheDesenho(tmp_path / f"c{len(esp.falha)}")
        out = refinar_pesados(f, p, r, executor=esp, cache=cache)
        assert esp.guids == ordem  # seguiu depois da falha
        assert out["refinadas"] == [ordem[0], ordem[2]]
        assert [d["guid"] for d in out["falhas_refino"]] == [ordem[1]] and out["falhas_refino"][0]["erro"]
        assert _sil(out["svg"]) and ordem[1] in _sil(out["svg"])[0] and len(_sil(out["svg"])) == 1
        assert out["svg"].count('data-fake="1"') == 2
        ok = Espiao()
        out2 = refinar_pesados(f, p, r, executor=ok, cache=cache)  # falha nao foi guardada
        assert ok.guids == [ordem[1]] and sorted(out2["em_cache"]) == sorted([ordem[0], ordem[2]]) and not _sil(out2["svg"])


def test_cancelar_antes_nao_executa_nada(cena):
    f, p, r, _b, _ids = cena
    ev, esp = threading.Event(), Espiao()
    ev.set()
    with pytest.raises(DesenhoCancelado):
        refinar_pesados(f, p, r, executor=esp, cancelar=ev)
    assert esp.guids == []


def test_cancelar_no_meio_para_sem_tocar_no_resto(cena):
    f, p, r, _b, _ids = cena
    ev = threading.Event()
    esp = Espiao(depois=lambda n: ev.set() if n == 2 else None)
    vistos = []
    with pytest.raises(DesenhoCancelado):
        refinar_pesados(f, p, r, executor=esp, cancelar=ev, ao_refinar=lambda s, g: vistos.append(g))
    assert esp.guids == _ordem(r)[:2]
    assert len(vistos) <= 2


def test_progresso_e_ao_refinar_na_ordem_com_svg_progressivo(cena):
    f, p, r, _b, _ids = cena
    msgs, vistos = [], []
    out = refinar_pesados(f, p, r, executor=Espiao(), progresso=msgs.append, ao_refinar=lambda s, g: vistos.append((g, len(_sil(s)), s.count('data-fake="1"'))))
    assert [g for g, _s, _e in vistos] == _ordem(r)
    assert [(s, e) for _g, s, e in vistos] == [(2, 1), (1, 2), (0, 3)]
    assert len(msgs) >= 3 and all(isinstance(m, str) and m for m in msgs)
    assert out["refinadas"] == _ordem(r)


def test_sem_pesados_devolve_igual_sem_executar(cena):
    f, p, r, _b, _ids = cena
    esp = Espiao()
    for res in ({**r, "pesados": [], "svg": r["svg"]}, {k: v for k, v in r.items() if k != "pesados"}):
        antes = copy.deepcopy(res)
        out = refinar_pesados(f, p, res, executor=esp)
        assert out["svg"] == antes["svg"] and res == antes and not out.get("refinadas") and not out.get("falhas_refino")
    assert esp.guids == []


def _d(grupo):
    return re.findall(r'\sd="([^"]*)"', grupo or "")


def test_integracao_motor_local_svg_igual_ao_exato_sem_oclusao(cena, tmp_path):
    f, p, r, base_svg, ids = cena
    cache = CacheDesenho(tmp_path / "c")
    out = refinar_pesados(f, p, r, executor=L.executar, cache=cache)
    assert out["falhas_refino"] == [] and sorted(out["refinadas"]) == sorted(ids) and not _sil(out["svg"])
    for gid in ids:
        assert _d(P.extrair_grupo(out["svg"], gid)) == _d(P.extrair_grupo(base_svg, gid)) != []
    assert sorted(re.findall(r'ifc:guid="([^"]+)"', out["svg"])) == sorted(re.findall(r'ifc:guid="([^"]+)"', base_svg))  # nenhum grupo perdido nem duplicado
    again = refinar_pesados(f, p, r, executor=lambda q: pytest.fail("hit nao chama executor"), cache=cache)
    assert sorted(again["em_cache"]) == sorted(ids) and again["svg"] == out["svg"]
