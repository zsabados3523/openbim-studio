# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo F0-S06-T05c, lacunas e bugs do lote Opus 75 (parte T05). Contrato base em `test_s06_t05_obim_zip_oraculo.py`; só o autor do oráculo mexe nos marcadores.
Bug 1: `.obim` existente com `NaN`/`Infinity` no manifesto (ou em entrada) não pode travar a gravação: `ler` levanta `ObimInvalido`; `gravar_par` cai no caminho de
`.obim` ilegível (sobrescreve; o antigo vai para `Casa.obim.bak`). Bug 3: destino `gravar_par` com final `.obim` (qualquer caixa) é recusado logo no começo,
com mensagem que cita o nome e o IFC; nada é escrito, `ao_concluir` não roda, carimbo e histórico não mudam.
Mutantes: N2 (`a//b.json`, `a/` e `vistas//x.json` recusados em `ler` e em `escrever`), N8 (`gravar_par(autosave=True, origem_ifc_sha256=)` grava `autosave` e a
origem no manifesto; gravação normal tira os dois), N9 (`apagar_vista` com a vista em 2 pranchas apaga os 2 viewports, um desfazer volta tudo).
Marcadores `@AINDA_NAO` retirados depois da correção (T05c). Bug 2 (troca do `.obim` falha, resolvedor conclui) fica de fora: aguarda decisão do líder."""
import json
import zipfile

import pytest
import s05_t07_aux as X
from s05_conteudo_aux import _limpa, base_ifc, exigir  # noqa: F401
from test_s06_t05_obim_zip_oraculo import G1, G2, IDENT, MAN, U, _fabrica, canon, lat, ob, objetos, proj  # noqa: F401


def _cru(o, manifesto_texto, entradas=None):
    with zipfile.ZipFile(o, "w") as z:
        z.writestr("manifest.json", manifesto_texto)
        for nome, dados in (entradas or {}).items():
            z.writestr(nome, dados)


def _man_texto(valor):
    return json.dumps(MAN)[:-1] + ', "x_outro": ' + valor + "}"


VALORES = ["NaN", "Infinity", "-Infinity"]


# ---------- bug 1 ----------
@pytest.mark.parametrize("valor", VALORES)
def test_01_ler_recusa_nao_finito_no_manifesto(tmp_path, valor):
    m, p = ob(), tmp_path / "f.obim"
    _cru(p, _man_texto(valor))
    with pytest.raises(m.ObimInvalido):
        m.ler(p)


@pytest.mark.parametrize("valor", VALORES)
def test_02_ler_recusa_nao_finito_em_entrada(tmp_path, valor):
    m, p = ob(), tmp_path / "f.obim"
    _cru(p, json.dumps(MAN), {"notas/n1.json": '{"v": ' + valor + "}"})
    with pytest.raises(m.ObimInvalido):
        m.ler(p)


@pytest.mark.parametrize("valor", VALORES)
def test_03_gravar_par_sobrescreve_obim_com_nao_finito_e_guarda_o_antigo(proj, base_ifc, valor):  # noqa: F811
    m = ob()
    _fabrica(proj)
    X.escrever_par_falso(proj.destino, base_ifc, {"notas": {"n0": {"texto": "primeira"}}}, 5)
    o = proj.destino.with_suffix(".obim")
    _cru(o, _man_texto(valor), {"notas/n0.json": '{"texto": "primeira"}'})
    ruim = o.read_bytes()
    proj.gravar()  # a 1a gravação já não pode falhar
    assert proj.destino.with_name("Casa.obim.bak").read_bytes() == ruim, "o .obim ilegível não foi guardado no .bak"
    r = m.ler(o)
    assert canon(r.lateral) == canon(proj.lat) and "x_outro" not in r.manifesto
    proj.tx(2)
    proj.gravar()  # e a seguinte também (antes: falhava para sempre)
    assert m.ler(o).manifesto["Revisao"] == r.manifesto["Revisao"] + 1


# ---------- bug 3 ----------
@pytest.mark.parametrize("nome", ["Casa.obim", "Casa.OBIM"])
def test_04_destino_com_final_obim_recusado_no_comeco(proj, nome):
    antes = sorted(p.name for p in proj.destino.parent.rglob("*")) + sorted(p.name for p in proj.pasta.rglob("*"))
    rev, n_anot, rev_h = proj.pset(), len(proj.anot), proj.h.pode_desfazer
    alvo = proj.destino.with_name(nome)
    with pytest.raises(Exception) as e:
        proj.gravar(destino=alvo)
    msg = str(e.value)
    assert nome in msg and "ifc" in msg.lower(), f"mensagem não cita o destino e o IFC: {msg!r}"
    assert "temporário" not in msg, "recusa por acaso (temporário mudou), não por checar o final do destino"
    depois = sorted(p.name for p in proj.destino.parent.rglob("*")) + sorted(p.name for p in proj.pasta.rglob("*"))
    assert depois == antes, f"a recusa escreveu algo: {set(depois) ^ set(antes)}"
    assert (proj.pset(), len(proj.anot), proj.h.pode_desfazer) == (rev, n_anot, rev_h), "carimbo ou histórico mudou"
    assert proj.chamadas == [], "ao_concluir rodou"


# ---------- N2 ----------
VAZIAS = ["vistas//a.json", "vistas/", "/vistas/a.json", "a//b.json", "//"]


@pytest.mark.parametrize("nome", ["vistas//a.json", "a//b.json", "notas//x.txt"])
def test_05_n2_ler_recusa_parte_vazia(tmp_path, nome):
    m, p = ob(), tmp_path / "f.obim"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("manifest.json", json.dumps(MAN))
        z.writestr(zipfile.ZipInfo(nome), b"{}")
    with pytest.raises(m.ObimInvalido):
        m.ler(p)
    import openbim_app.gravacao_par as GP
    with pytest.raises(ValueError):
        GP._conferir_obim(p)


@pytest.mark.parametrize("nome", ["vistas//a.json", "a//b.json", "assets//logo.png", "//x"])
def test_06_n2_escrever_recusa_extra_com_parte_vazia(tmp_path, nome):
    m, p = ob(), tmp_path / "f.obim"
    with pytest.raises(m.ObimInvalido):
        m.escrever(p, lat(), MAN, {nome: b"x"})
    assert not p.exists()


# ---------- N8 ----------
def test_07_n8_autosave_grava_marca_e_origem_no_manifesto(proj, tmp_path):
    m = ob()
    auto = proj.pasta / "autosave" / "Casa.ifc"
    auto.parent.mkdir()
    origem = "ab" * 32
    proj.gravar(historico=None, carimbo=False, destino=auto, pasta_projeto=auto.parent, autosave=True, origem_ifc_sha256=origem, ao_concluir=None)
    man = m.ler(auto.with_suffix(".obim")).manifesto
    assert man["autosave"] is True and man["origem_ifc_sha256"] == origem, f"manifesto do autosave: {man}"
    proj.gravar()  # gravação normal do par do usuário: sem as duas marcas
    man2 = m.ler(proj.destino.with_suffix(".obim")).manifesto
    assert "autosave" not in man2 and "origem_ifc_sha256" not in man2
    # a normal por cima de um .obim que já tinha as marcas também as tira
    proj.gravar(historico=None, carimbo=False, destino=auto, pasta_projeto=auto.parent, autosave=True, origem_ifc_sha256="cd" * 32, ao_concluir=None)
    assert m.ler(auto.with_suffix(".obim")).manifesto["origem_ifc_sha256"] == "cd" * 32, "origem não foi atualizada"
    proj.gravar(historico=None, carimbo=False, destino=auto, pasta_projeto=auto.parent, ao_concluir=None)
    man3 = m.ler(auto.with_suffix(".obim")).manifesto
    assert "autosave" not in man3 and "origem_ifc_sha256" not in man3, "gravação normal deixou as marcas do autosave"


# ---------- N9 ----------
def _dois_viewports_da_mesma_vista():
    o = objetos()
    o["pranchas"] = {**o["pranchas"], U["p2"]: {"identification": "B-02", "formato": "A3"}}
    o["viewports"] = {**o["viewports"], U["vp3"]: {"prancha": "B-02", "vista_guid": G1, "x": 5, "y": 5, "escala": 100}}
    return o


def test_08_n9_apagar_vista_em_duas_pranchas_apaga_todos_os_viewports(proj):
    from openbim_app.lateral import Lateral
    m = ob()
    with proj.s.escrever() as esc, proj.h.transacao(esc) as t:
        for c, objs in _dois_viewports_da_mesma_vista().items():
            for i, o in objs.items():
                t.lado.criar(c, i, o)
    assert {proj.lat.obter("viewports", U[k])["prancha"] for k in ("vp1", "vp3")} == {IDENT, "B-02"}
    cheio = canon(proj.lat)
    with proj.s.escrever() as esc, proj.h.transacao(esc) as t:
        m.apagar_vista(t.lado, G1)
    sobra = [i for i in proj.lat.ids("viewports") if proj.lat.obter("viewports", i)["vista_guid"] == G1]
    assert sobra == [] and proj.lat.obter("vistas", U["v1"]) is None, f"viewports da vista apagada que sobraram: {sobra}"
    assert proj.lat.obter("viewports", U["vp2"]) is not None and proj.lat.obter("vistas", U["v2"]) is not None, "apagou além da vista pedida"
    assert {proj.lat.obter("pranchas", U[k]) is not None for k in ("p1", "p2")} == {True}
    with proj.s.escrever() as esc:
        proj.h.desfazer(esc)  # UM desfazer volta a vista e os 2 viewports
    assert canon(proj.lat) == cheio and isinstance(proj.lat, Lateral)
    with proj.s.escrever() as esc:
        proj.h.refazer(esc)
    assert [i for i in proj.lat.ids("viewports") if proj.lat.obter("viewports", i)["vista_guid"] == G1] == []
