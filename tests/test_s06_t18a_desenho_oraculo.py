# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo F0-S06-T18a (integração `desenho.processar` com IFC sintético). Pedido com `pesados="silhueta"` + `limiar_pesado`: `pesados` = [{guid, id, faces}] (sem duplicata, agregado nas faixas);
a peça sai em `<g ifc:guid data-silhueta="1">` com `<path ... Z fill-rule="evenodd">`; porta/janela/peça com vão, móvel em caixa, silhueta vazia e peça acima do corte ficam fora (HLR normal ou nada);
`contar_faces(el_ou_forma)` conta triângulos; corte ignora a opção; as pesadas nunca passam pelo serializador HLR; com faixas o pai tira as pesadas dos filhos."""
from __future__ import annotations

import re

import ifcopenshell.geom
import ifcopenshell.geom as G
import pytest
import s06_t07_aux as X
import s06_t07c_aux as C
import s06_t15o_aux as T15
from s05_conteudo_aux import _limpa  # noqa: F401  (autouse)
from s06_t17_aux import partes
from s06_t18a_aux import com_pesadas_longe, densificar, modelo_denso, pedido_planta
from s06_t18a_malha import anel_de_blocos, area_aneis, cilindro

import obim_geometria.desenho as D
import obim_geometria.faixas as F
import obim_geometria.local as L
import obim_geometria.silhueta as S


def test_contar_faces_elemento_e_forma():
    f, g, _v, mov, parede = modelo_denso(24)
    assert S.contar_faces(parede) == 12
    n_mov = S.contar_faces(mov)
    assert n_mov == len(mov.Representation.Representations[0].Items[0].Faces) == 4 * 24 - 4
    cfg = ifcopenshell.geom.settings()
    forma = ifcopenshell.geom.create_shape(cfg, mov)
    assert S.contar_faces(forma) == n_mov
    sem = f.by_type("IfcBuildingStorey")[0]
    assert S.contar_faces(sem) == 0


def _rodar(f, g, vista, tmp_path, **extra):
    p = pedido_planta(f, vista, tmp_path)
    p.update(extra)
    r = L.executar(p)
    assert r.get("ok"), r
    return p, r


def _grupo(svg, guid):
    m = re.search(r'<g\b[^>]*\bifc:guid="%s"[^>]*>.*?</g>' % re.escape(guid), svg, re.S)
    return m.group(0) if m else None


def test_sem_opcao_ou_com_limiar_alto_svg_identico(tmp_path):
    f, g, v, mov, _p = modelo_denso(24)
    _p0, base = _rodar(f, g, v, tmp_path / "a")
    _p1, alto = _rodar(f, g, v, tmp_path / "b", pesados="silhueta", limiar_pesado=100000)
    assert not base.get("pesados") and alto["pesados"] == []
    assert alto["svg"] == base["svg"] and "data-silhueta" not in base["svg"]


def test_pesados_silhueta_so_o_movel_denso(tmp_path):
    f, g, v, mov, parede = modelo_denso(24)
    p0, base = _rodar(f, g, v, tmp_path / "a")
    p1, r = _rodar(f, g, v, tmp_path / "b", pesados="silhueta", limiar_pesado=50)
    assert r["pesados"] == [{"guid": mov.GlobalId, "id": mov.id(), "faces": 4 * 24 - 4}]
    gm = _grupo(r["svg"], mov.GlobalId)
    assert gm and 'data-silhueta="1"' in gm and re.search(r'<path\b[^>]*\bd="M[^"]*[Zz]', gm), gm
    assert _grupo(base["svg"], mov.GlobalId) and 'data-silhueta' not in _grupo(base["svg"], mov.GlobalId)
    # mesma pegada do desenho exato (0,6 x 0,6) e o resto do desenho intacto
    _e0, g0 = partes(base["svg"], aprox=True)
    _e1, g1 = partes(r["svg"], aprox=True)
    assert dict(g1)[mov.GlobalId] == pytest.approx(dict(g0)[mov.GlobalId], abs=0.02)
    assert {k: v for k, v in g1 if k != mov.GlobalId} == {k: v for k, v in g0 if k != mov.GlobalId}
    assert [k for k, _ in g1] == [k for k, _ in g0]  # nenhum grupo perdido nem duplicado
    assert parede.GlobalId not in [d["guid"] for d in r["pesados"]]
    assert mov.id() in r["enviados"] and r["falhas_geometria"] == []


@pytest.mark.parametrize("off,k", [(X.GEO, 1.0), ((0.0, 0.0), 1000.0), (X.GEO, 1000.0)])
def test_georref_e_milimetros_mesma_pegada_do_hlr(tmp_path, off, k):
    f, g, v, mov, _p = modelo_denso(24, off, k)
    _p, base = _rodar(f, g, v, tmp_path / "a")
    _p, r = _rodar(f, g, v, tmp_path / "b", **OP)
    assert [d["guid"] for d in r["pesados"]] == [mov.GlobalId] and r["falhas_geometria"] == []
    assert dict(partes(r["svg"], aprox=True)[1])[mov.GlobalId] == pytest.approx(dict(partes(base["svg"], aprox=True)[1])[mov.GlobalId], abs=0.02)


OP = dict(pesados="silhueta", limiar_pesado=50)


def _silh(svg):
    return re.findall(r'<g\b[^>]*\bifc:guid="([^"]+)"[^>]*\bdata-silhueta="1"|<g\b[^>]*\bdata-silhueta="1"[^>]*\bifc:guid="([^"]+)"', svg)


def test_porta_janela_e_parede_com_vao_seguem_no_hlr(tmp_path):
    f, g, v, mov, par = modelo_denso(24, vaos=(("porta", "IfcDoor", 1.0, 0.0, 1.0, 2.0), ("jan", "IfcWindow", 3.0, 0.9, 1.0, 1.0)))
    for nome in ("porta0", "jan0"):
        densificar(f, f.by_guid(g[nome]), cilindro(0.3, 24))
    assert par.HasOpenings
    densificar(f, par, cilindro(0.3, 24))
    _p, r = _rodar(f, g, v, tmp_path, **OP)
    assert [d["guid"] for d in r["pesados"]] == [mov.GlobalId]
    for gid in (g["porta0"], g["jan0"], par.GlobalId):
        assert 'data-silhueta' not in (_grupo(r["svg"], gid) or "")


def test_moveis_como_caixa_nao_vira_silhueta(tmp_path):
    f, g, v, mov, _p = modelo_denso(24)
    _p, r = _rodar(f, g, v, tmp_path, moveis_como_caixa=True, **OP)
    assert not r.get("pesados") and 'data-silhueta' not in r["svg"]


def test_silhueta_vazia_cai_no_hlr_normal(tmp_path, monkeypatch):
    f, g, v, mov, _p = modelo_denso(24)
    _p, base = _rodar(f, g, v, tmp_path / "a")
    monkeypatch.setattr(S, "silhueta_xy", lambda *a, **k: [])
    _p, r = _rodar(f, g, v, tmp_path / "b", **OP)
    assert r["pesados"] == [] and r["svg"] == base["svg"] and mov.id() not in (r.get("falhas_geometria") or [])
    assert _grupo(r["svg"], mov.GlobalId)


def test_peca_pesada_acima_do_corte_nao_desenha_nem_falha(tmp_path):
    f, g, v, mov, _p = modelo_denso(24)
    mov.ObjectPlacement.RelativePlacement.Location.Coordinates = (0.5, 2.0, 5.0)
    _p, r = _rodar(f, g, v, tmp_path, **OP)
    assert not _grupo(r["svg"], mov.GlobalId) and mov.id() not in (r.get("falhas_geometria") or []) and 'data-silhueta' not in r["svg"]


def test_pesada_nao_passa_pelo_serializador_hlr(tmp_path, monkeypatch):
    f, g, v, mov, par = modelo_denso(24)
    p = pedido_planta(f, v, tmp_path)  # o run preliminar (sem a opção) fica fora do espião
    escritos, original = [], G.serializers.svg

    class Espiao:
        def __init__(self, *a, **k):
            self._r = original(*a, **k)

        def write(self, shape):
            escritos.append(shape.id)
            return self._r.write(shape)

        def __getattr__(self, nome):
            return getattr(self._r, nome)
    monkeypatch.setattr(G.serializers, "svg", Espiao)
    r = L.executar({**p, **OP})
    assert r["ok"] and r["pesados"] and par.id() in escritos and mov.id() not in escritos


def test_faixas_pai_tira_as_pesadas_dos_filhos_e_agrega(tmp_path, monkeypatch):
    f, g, v, mov, _p = modelo_denso(24)
    pesadas = [mov] + com_pesadas_longe(f, g)
    chamadas = []

    def filho(q):
        chamadas.append(q)
        return D.processar(q)
    monkeypatch.setattr(F, "rodar_filho", filho)
    _p, sem = _rodar(f, g, v, tmp_path / "a", **OP)
    _p, com = _rodar(f, g, v, tmp_path / "b", faixas=2, **OP)
    ids = {e.id() for e in pesadas}
    assert len(chamadas) > 1
    for q in chamadas:  # o pai calcula as pesadas e as tira da lista; nenhum filho recebe id de pesada nem a opção
        assert not ({i for i, _g in q["elementos"]} & ids) and not q.get("pesados")
    guids = [d["guid"] for d in com["pesados"]]
    assert len(guids) == len(set(guids)) == len(pesadas) and {d["id"] for d in com["pesados"]} == ids
    assert com["svg"].count('data-silhueta="1"') == len(pesadas) == sem["svg"].count('data-silhueta="1"')
    assert ids <= set(com["enviados"]) and com["falhas_geometria"] == [] and partes(com["svg"], aprox=True) == partes(sem["svg"], aprox=True)
    assert sorted(a or b for a, b in _silh(com["svg"])) == sorted(a or b for a, b in _silh(sem["svg"]))


def test_corte_ignora_pesados(tmp_path):
    f, g = C.modelo("IFC4")
    densificar(f, f.by_guid(g["M"]), cilindro(0.3, 24))
    p = T15.pedido_de(f, C.corte(f), tmp_path)
    base = L.executar(dict(p))
    r = L.executar({**p, **OP})
    assert base["ok"] and r["ok"] and r["svg"] == base["svg"] and not r.get("pesados")


def test_path_evenodd_com_furo_e_area_real(tmp_path):
    f, g, v, mov, _p = modelo_denso(24)
    densificar(f, mov, anel_de_blocos(1.5))
    _p, r = _rodar(f, g, v, tmp_path, **OP)
    gm = _grupo(r["svg"], mov.GlobalId)
    assert r["pesados"] and 'fill-rule="evenodd"' in gm
    d = re.search(r'<path\b[^>]*\bd="([^"]*)"', gm).group(1)
    aneis = [[(float(a), float(b)) for a, b in re.findall(r"(-?[\d.]+(?:e-?\d+)?)[ ,](-?[\d.]+(?:e-?\d+)?)", s)] for s in d.split("M")[1:]]
    assert len(aneis) == 2 and area_aneis(aneis) == pytest.approx(8.0, abs=0.05)
