# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo F0-S06-T19c2b: `openbim_app.desenho.refino.refinar_pesados` refina cada peça por `pecas.refinar_peca` (motor novo `peca_visivel`, queda para `desenho`).
Interface (cartão, seção API): `out["motores"]` {guid: "visibilidade"|"hlr"} (também para peça vinda do cache), `out["motivos_hlr"]` {guid: motivo} só para queda,
mensagem de `progresso` da peça cita o motor; chave de cache muda com o motor/versão (grupo HLR antigo, guardado na chave de antes, não é reaproveitado)."""
from __future__ import annotations

import json
import re
import threading

import pytest
from s05_conteudo_aux import _limpa  # noqa: F401  (autouse)
from test_s06_t18b2_refino_oraculo import _ordem, _sil, cena  # noqa: F401  (fixture)

import obim_geometria.pecas as P
from openbim_app.desenho import auxiliar
from openbim_app.desenho.auxiliar import DesenhoCancelado
from openbim_app.desenho.cache import CacheDesenho
from openbim_app.desenho.refino import refinar_pesados


def _g(gid, marca):
    return f'<g class="IfcFurniture" xmlns:ifc="x" ifc:guid="{gid}" data-fake="{marca}"><path d="M 0,0 L 1,0 L 1,1 Z"/></g>'


class Fake:
    """Executor falso que distingue as duas ops. `inel`: peca_visivel diz inelegível (cai no desenho); `falha`: desenho falha; `depois(n)`: após a n-ésima chamada."""

    def __init__(self, inel=(), falha=(), depois=None):
        self.chamadas, self.inel, self.falha, self.depois = [], set(inel), set(falha), depois

    def __call__(self, q):
        op, gid = q.get("op", "desenho"), q["elementos"][0][1]
        self.chamadas.append((op, gid))
        if self.depois:
            self.depois(len(self.chamadas))
        if op == "peca_visivel":
            if gid in self.inel:
                return {"ok": False, "elegivel": False, "motivo": "porta"}  # como peca_visivel._inelegivel
            return {"ok": True, "grupo": _g(gid, "mv"), "tempos": {}}
        if gid in self.falha:
            return {"ok": False, "erro": {"tipo": "X", "mensagem": "quebrou", "rastro": ""}}
        return {"ok": True, "svg": f'<svg xmlns:ifc="x">{_g(gid, "hlr")}</svg>', "tempos": {}}

    def ops(self, gid=None):
        return [o for o, g in self.chamadas if gid is None or g == gid]


def test_elegivel_usa_motor_novo_e_nao_chama_desenho(cena):
    f, p, r, _b, _ids = cena
    ex, msgs = Fake(), []
    out = refinar_pesados(f, p, r, executor=ex, progresso=msgs.append)
    assert ex.ops() == ["peca_visivel"] * 3 and out["refinadas"] == _ordem(r) and out["falhas_refino"] == []
    assert out["motores"] == {g: "visibilidade" for g in _ordem(r)} and not out.get("motivos_hlr")
    assert out["svg"].count('data-fake="mv"') == 3 and not _sil(out["svg"])
    assert all("visibilidade" in m for m in msgs if "refinada" in m)


def test_inelegivel_cai_no_desenho_e_registra_motivo(cena):
    f, p, r, _b, _ids = cena
    ordem = _ordem(r)
    ex, msgs = Fake(inel=[ordem[1]]), []
    out = refinar_pesados(f, p, r, executor=ex, progresso=msgs.append)
    assert ex.ops(ordem[1]) == ["peca_visivel", "desenho"] and ex.ops(ordem[0]) == ["peca_visivel"]
    assert out["motores"] == {ordem[0]: "visibilidade", ordem[1]: "hlr", ordem[2]: "visibilidade"}
    assert "porta" in out["motivos_hlr"][ordem[1]] and set(out["motivos_hlr"]) == {ordem[1]}
    assert out["svg"].count('data-fake="hlr"') == 1 and out["svg"].count('data-fake="mv"') == 2 and not _sil(out["svg"])
    assert any(ordem[1] in m and "hlr" in m for m in msgs)  # mensagem cita o motor


def test_cache_hit_nao_chama_executor_e_grupo_hlr_antigo_nao_e_reaproveitado(cena, tmp_path):
    f, p, r, _b, ids = cena
    ordem = _ordem(r)
    cache = CacheDesenho(tmp_path / "c")
    antigo = _g(ordem[0], "ANTIGO")  # o que o refino de antes (só `desenho`) guardava, na chave de antes
    assert cache.guardar(cache.chave(f, P.pedido_peca(p, ids[ordem[0]])), {"svg": antigo, "grupo": antigo})
    e1 = Fake(inel=[ordem[1]])
    o1 = refinar_pesados(f, p, r, executor=e1, cache=cache)
    assert o1["em_cache"] == [] and e1.ops(ordem[0]) == ["peca_visivel"] and "ANTIGO" not in o1["svg"]
    guardados = [json.loads(a.read_text()) for a in cache.pasta.glob("*.json")]
    assert any(d.get("svg") == d.get("grupo") and 'data-fake="mv"' in d["grupo"] for d in guardados)  # formato de hoje
    e2 = Fake()
    o2 = refinar_pesados(f, p, r, executor=e2, cache=cache)
    assert e2.chamadas == [] and sorted(o2["em_cache"]) == sorted(ordem) and o2["svg"] == o1["svg"]
    assert o2["motores"] == o1["motores"] == {ordem[0]: "visibilidade", ordem[1]: "hlr", ordem[2]: "visibilidade"}
    assert o2["motivos_hlr"] == o1["motivos_hlr"] and "porta" in o2["motivos_hlr"][ordem[1]]


def test_falha_de_uma_peca_continua_isolada_e_nao_e_guardada(cena, tmp_path):
    f, p, r, _b, _ids = cena
    ordem = _ordem(r)
    cache = CacheDesenho(tmp_path / "c")
    ex = Fake(inel=[ordem[1]], falha=[ordem[1]])
    out = refinar_pesados(f, p, r, executor=ex, cache=cache)
    assert out["refinadas"] == [ordem[0], ordem[2]] and [d["guid"] for d in out["falhas_refino"]] == [ordem[1]]
    assert out["falhas_refino"][0]["erro"] and ordem[1] not in out["motores"]
    assert len(_sil(out["svg"])) == 1 and ordem[1] in _sil(out["svg"])[0] and out["svg"].count('data-fake="mv"') == 2
    ok = Fake(inel=[ordem[1]])
    o2 = refinar_pesados(f, p, r, executor=ok, cache=cache)
    assert ok.ops(ordem[1]) == ["peca_visivel", "desenho"] and ok.ops(ordem[0]) == [] and not _sil(o2["svg"])


def test_cancelar_antes_e_no_meio(cena):
    f, p, r, _b, _ids = cena
    ev, ex = threading.Event(), Fake()
    ev.set()
    with pytest.raises(DesenhoCancelado):
        refinar_pesados(f, p, r, executor=ex, cancelar=ev)
    assert ex.chamadas == []
    ev2 = threading.Event()
    ex2 = Fake(depois=lambda n: ev2.set() if n == 2 else None)
    with pytest.raises(DesenhoCancelado):
        refinar_pesados(f, p, r, executor=ex2, cancelar=ev2)
    assert [g for _o, g in ex2.chamadas] == _ordem(r)[:2]


def test_tratar_resposta_preserva_inelegivel_e_ainda_levanta_nas_outras_falhas():
    r = {"ok": False, "elegivel": False, "motivo": "porta"}
    assert auxiliar._tratar_resposta(r) == r  # contrato novo: sem levantar, motivo intacto
    for raw in ({"ok": False, "erro": {"tipo": "X", "mensagem": "m", "rastro": ""}}, {"ok": False, "elegivel": True, "erro": {"tipo": "X", "mensagem": "m"}}):
        with pytest.raises(auxiliar.FalhaNoAuxiliar):
            auxiliar._tratar_resposta(raw)


def test_estouro_de_tempo_no_motor_novo_nao_cai_no_hlr(cena, tmp_path):
    f, p, r, _b, _ids = cena
    ordem = _ordem(r)
    cache = CacheDesenho(tmp_path / "c")
    ex = Fake()
    base = ex.__call__

    def estoura(q):
        if q.get("op") == "peca_visivel" and q["elementos"][0][1] == ordem[1]:
            ex.chamadas.append(("peca_visivel", ordem[1]))
            raise auxiliar.AuxiliarEstourouTempo(1.0, "peca_visivel")
        return base(q)

    out = refinar_pesados(f, p, r, executor=estoura, cache=cache)
    assert ex.ops(ordem[1]) == ["peca_visivel"]  # desenho nao chamado
    assert [d["guid"] for d in out["falhas_refino"]] == [ordem[1]] and out["falhas_refino"][0]["erro"]
    assert out["refinadas"] == [ordem[0], ordem[2]] and ordem[1] not in out["motores"] and ordem[1] not in out.get("motivos_hlr", {})
    assert len(_sil(out["svg"])) == 1 and ordem[1] in _sil(out["svg"])[0]
    assert not any(ordem[1] in a.read_text() for a in cache.pasta.glob("*.json"))  # nao guardada
