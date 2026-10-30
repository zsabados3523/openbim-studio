# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo do F0-S06-T06b, abrir e gravar não religam sozinhos um lateral de outro projeto (ADR-003 §6 D5: "recusa vincular sozinho";
achado 1 da revisão Opus da T06). Só o autor tira os `@AINDA_NAO` (xfail estrito). Auxiliar: `s06_t06_aux.py`. Mutantes: `s06_t06b_mutantes.md`.
CONTRATO (API PROPOSTA NESTE TESTE; o ADR fixa a regra, não os nomes). `openbim_app/autosave.py`:
- `class LateralAlheio(ValueError)`: gravar o par do usuário com lateral alheio ainda sem escolha. A mensagem cita o nome do `.obim`.
- Lateral alheio = `Casa.obim` ao lado do IFC cujo manifesto tem `ifc_projeto_globalid` OU `LadoId` diferente do IFC (o D5 de `divergencia.classificar`).
  Detectado SEMPRE em `abrir_projeto`, com ou sem `divergencia=True` (a proteção não depende da flag). `.obim` ilegível ou recusado continua como hoje.
- `Projeto.lateral_alheio`: `Path` do `.obim` alheio enquanto não houver escolha; `None` caso contrário (D1 a D4, ou depois de "criar_novo_lateral").
- Com lateral alheio: `Projeto.lateral` é VAZIO (nada de vistas, estilos ou pranchas dele na memória) e nada em disco é tocado ao abrir.
- `Projeto.escolher_lateral(opcao)`: `"cancelar"` não grava nem move nada (a pendência segue; pode escolher de novo depois).
  `"criar_novo_lateral"` GUARDA o alheio com `os.replace` (mesmo volume, atômico, mtime preservado) em `Casa.obim.alheio-<8 primeiros hex do sha256 do
  conteúdo>` na mesma pasta; `lateral_alheio` vira `None`; o `Casa.obim` novo só nasce na próxima `gravar_normal`. Escolha inválida ou sem pendência = `ValueError`,
  sem mexer em nada. Falha ao guardar (OSError) sobe, deixa o alheio onde estava e a pendência continua.
- `Autosave.gravar_normal()` com pendência: levanta `LateralAlheio` ANTES de qualquer escrita (nem IFC, nem `.obim`, nem carimbo de Revisao na memória).
- `Autosave.salvar()` (autosave) não toca a pasta do usuário e nunca grava conteúdo do alheio (só `Projeto.lateral`, vazio).
- Depois de "criar_novo_lateral" + gravar: `Casa.obim` novo com `ifc_projeto_globalid` e `LadoId` DESTE projeto, sem objetos do alheio; reabrir dá D1, sem pendência.
GUARDA: sem ifcopenshell, pula (falha com OBIM_S05_OBRIGATORIO=1)."""
import hashlib
import os
import shutil
from pathlib import Path

import pytest
import s06_t06_aux as X
from s05_conteudo_aux import _limpa, exigir  # noqa: F401  (fixtures)

OUTRO_GID = "9zzzHZ1u8Ek9aBc3DeFgHi"
OUTRO_LADO = "0a0a0a0a-1b1b-4c4c-9d9d-2e2e2e2e2e2e"
TIPOS = ("globalid", "ladoid")
RASTRO = ("Casa.obim.tmp", "Casa.ifc.tmp", "gravacao.json")


@pytest.fixture(autouse=True)
def _local(tmp_path, monkeypatch):
    exigir()
    monkeypatch.setenv("OBIM_PASTA_LOCAL", str(tmp_path / "local"))


@pytest.fixture
def abre():
    import openbim_app.autosave as S
    abertos = []

    def f(ifc, div=False):
        pr = S.abrir_projeto(ifc, lambda t: True, divergencia=div)
        abertos.append(pr)
        return pr
    yield f
    for pr in abertos:
        for fn in (pr.autosave.parar, pr.diario.fechar, pr.historico.encerrar):
            try:
                fn()
            except Exception:  # noqa: BLE001
                pass


@pytest.fixture
def p(tmp_path):
    return tmp_path / "proj"


def alheio(p, tipo="globalid", **kw):
    """Par cujo `.obim` é de outro projeto. Devolve (ifc, obim, bytes do obim, mtime_ns do obim)."""
    ifc, ob = X.fazer(p, **({"o_gid": OUTRO_GID} if tipo == "globalid" else {"o_lado": OUTRO_LADO}), **kw)
    return ifc, ob, ob.read_bytes(), ob.stat().st_mtime_ns


def achados(pasta, dados):
    return [f for f in Path(pasta).iterdir() if f.is_file() and f.read_bytes() == dados]


def guardado(pasta, dados):
    return Path(pasta) / f"Casa.obim.alheio-{hashlib.sha256(dados).hexdigest()[:8]}"


def revisao(pr):
    import ifcopenshell.util.element as UE
    return UE.get_psets(pr.arquivo.by_type("IfcProject")[0])["OBIM_Projeto"]["Revisao"]


def sujar(pr, tag="x"):
    with pr.sessao.escrever() as esc, pr.historico.transacao(esc) as t:
        t.ifc.by_type("IfcProject")[0].Description = f"alterado {tag}"


def gravado(ob):
    import openbim_app.obim_zip as Z
    return Z.ler(ob)


def obter_vazio(lat):
    return lat.canonico() == b"{}"


def obter(pr, c="vistas"):
    return list(pr.lateral.ids(c))


# 1) abrir
@pytest.mark.parametrize("div", [False, True])
@pytest.mark.parametrize("tipo", TIPOS)
def test_01_abrir_nao_carrega_nem_toca_o_alheio(p, abre, tipo, div):
    ifc, ob, dados, mt = alheio(p, tipo)
    antes = X.foto(p)
    pr = abre(ifc, div)
    assert pr.lateral_alheio is not None and os.path.samefile(pr.lateral_alheio, ob)
    assert [obter(pr, c) for c in ("vistas", "pranchas", "viewports")] == [[], [], []] and pr.lateral.canonico() == b"{}"
    assert X.foto(p) == antes and ob.read_bytes() == dados and ob.stat().st_mtime_ns == mt
    if div:
        assert pr.divergencia.caso == "D5" and pr.divergencia.aviso in pr.avisos


# 2) gravar sem escolha
@pytest.mark.parametrize("tipo", TIPOS)
def test_02_gravar_sem_escolha_levanta_e_nao_escreve_nada(p, abre, tipo):
    import openbim_app.autosave as S
    ifc, ob, dados, mt = alheio(p, tipo)
    pr = abre(ifc)
    antes, rev = X.foto(p), revisao(pr)
    for _ in range(2):
        with pytest.raises(S.LateralAlheio, match="Casa.obim"):
            pr.autosave.gravar_normal()
    assert issubclass(S.LateralAlheio, ValueError) and X.foto(p) == antes and ob.stat().st_mtime_ns == mt
    assert revisao(pr) == rev and not (Path(pr.caminho).parent / "Casa.ifc.bak").exists()


def test_03_autosave_nao_regrava_o_alheio_nem_grava_conteudo_dele(p, abre):
    import openbim_app.diario as D
    ifc, ob, dados, mt = alheio(p)
    pr = abre(ifc)
    antes = X.foto(p)
    sujar(pr)
    assert pr.autosave.salvar() is True
    assert X.foto(p) == antes and ob.stat().st_mtime_ns == mt
    auto = D.pasta_projeto(pr.lado_id) / "autosave" / "Casa.obim"
    assert auto.exists() and obter_vazio(gravado(auto).lateral)


# 3) escolha
def test_04_cancelar_nao_grava_nem_move_e_a_pendencia_segue(p, abre):
    import openbim_app.autosave as S
    ifc, ob, dados, mt = alheio(p)
    pr = abre(ifc)
    antes = X.foto(p)
    pr.escolher_lateral("cancelar")
    assert X.foto(p) == antes and ob.stat().st_mtime_ns == mt and pr.lateral_alheio is not None
    with pytest.raises(S.LateralAlheio):
        pr.autosave.gravar_normal()
    assert X.foto(p) == antes


def test_05_criar_novo_lateral_guarda_o_alheio_e_so_depois_grava_o_novo(p, abre):
    ifc, ob, dados, mt = alheio(p)
    pr = abre(ifc)
    pr.escolher_lateral("criar_novo_lateral")
    g = guardado(p, dados)
    assert pr.lateral_alheio is None and g.read_bytes() == dados and g.stat().st_mtime_ns == mt
    assert not ob.exists() or ob.read_bytes() != dados  # o alheio não segue como Casa.obim
    pr.autosave.gravar_normal()
    novo = gravado(ob)
    assert novo.manifesto["ifc_projeto_globalid"] == X.GID and novo.manifesto["LadoId"] == X.LADO
    assert novo.manifesto["ifc_sha256"] == X.sha(ifc) and obter_vazio(novo.lateral)
    assert g.read_bytes() == dados and g.stat().st_mtime_ns == mt and len(achados(p, dados)) == 1
    assert not [n for n in RASTRO if (p / n).exists()]


def test_06_gravar_depois_da_escolha_e_reabrir_da_d1_sem_pendencia(p, abre):
    ifc, ob, dados, mt = alheio(p)
    pr = abre(ifc)
    pr.escolher_lateral("criar_novo_lateral")
    pr.autosave.gravar_normal()
    pr.autosave.parar(), pr.diario.fechar(), pr.historico.encerrar()
    pr2 = abre(ifc, True)
    assert pr2.lateral_alheio is None and pr2.divergencia.caso == "D1" and obter(pr2) == []
    assert guardado(p, dados).read_bytes() == dados


def test_07_reabrir_sem_escolher_segue_pendente_e_intacto(p, abre):
    ifc, ob, dados, mt = alheio(p)
    pr = abre(ifc)
    pr.autosave.parar(), pr.diario.fechar(), pr.historico.encerrar()
    pr2 = abre(ifc)
    assert pr2.lateral_alheio is not None and obter(pr2) == [] and ob.read_bytes() == dados and ob.stat().st_mtime_ns == mt


@pytest.mark.parametrize("opcao", ["", "apagar", "CANCELAR", None])
def test_08_escolha_invalida_e_ValueError_sem_mexer(p, abre, opcao):
    ifc, ob, dados, mt = alheio(p)
    pr = abre(ifc)
    antes = X.foto(p)
    with pytest.raises(ValueError):
        pr.escolher_lateral(opcao)
    assert X.foto(p) == antes and pr.lateral_alheio is not None


@pytest.mark.parametrize("opcao", ["cancelar", "criar_novo_lateral"])
def test_09_escolher_sem_pendencia_e_ValueError(p, abre, opcao):
    ifc, _ = X.fazer(p)
    pr = abre(ifc)
    antes = X.foto(p)
    with pytest.raises(ValueError):
        pr.escolher_lateral(opcao)
    assert X.foto(p) == antes


# 4) queda
def test_10_falha_na_gravacao_depois_da_escolha_nao_perde_o_alheio(p, abre, monkeypatch):
    import openbim_app.autosave as S
    ifc, ob, dados, mt = alheio(p)
    pr = abre(ifc)
    pr.escolher_lateral("criar_novo_lateral")
    real = S.gravar_par

    def cai(*a, **k):
        raise OSError("queda simulada")
    monkeypatch.setattr(S, "gravar_par", cai)
    with pytest.raises(OSError, match="queda"):
        pr.autosave.gravar_normal()
    assert len(achados(p, dados)) == 1
    monkeypatch.setattr(S, "gravar_par", real)
    pr.autosave.gravar_normal()  # a nova tentativa funciona
    assert guardado(p, dados).read_bytes() == dados and gravado(ob).manifesto["ifc_projeto_globalid"] == X.GID


def test_11_falha_ao_guardar_deixa_o_alheio_onde_estava_e_a_pendencia(p, abre, monkeypatch):
    import openbim_app.autosave as S
    ifc, ob, dados, mt = alheio(p)
    pr = abre(ifc)

    def cai(*a, **k):
        raise OSError("queda simulada")
    with monkeypatch.context() as m:
        for obj, nome in ((os, "replace"), (os, "rename"), (os, "link"), (shutil, "move"), (shutil, "copyfile"), (shutil, "copy2"), (shutil, "copy")):
            m.setattr(obj, nome, cai)
        with pytest.raises(OSError, match="queda"):
            pr.escolher_lateral("criar_novo_lateral")
    assert ob.read_bytes() == dados and ob.stat().st_mtime_ns == mt and pr.lateral_alheio is not None
    with pytest.raises(S.LateralAlheio):
        pr.autosave.gravar_normal()
    assert ob.read_bytes() == dados


# 5) regressão: sem lateral alheio tudo como hoje
def _d1(p):
    return X.fazer(p)[0]


def _d2(p):
    ifc = X.fazer(p)[0]
    X.mudar_um_byte(ifc)
    return ifc


def _d3(p):
    return X.fazer(p, rev=2, o_rev=3)[0]


def _d4(p):
    return X.fazer(p, obim=False)[0]


@pytest.mark.parametrize("div", [False, True])
@pytest.mark.parametrize("fab,vistas", [(_d1, ["v1", "v2"]), (_d2, ["v1", "v2"]), (_d3, ["v1", "v2"]), (_d4, [])])
def test_12_casos_sem_alheio_abrem_e_gravam_como_hoje(p, abre, fab, vistas, div):
    ifc = fab(p)
    pr = abre(ifc, div)
    assert obter(pr) == vistas
    pr.autosave.gravar_normal()
    ob = ifc.with_suffix(".obim")
    assert gravado(ob).manifesto["ifc_projeto_globalid"] == X.GID and sorted(gravado(ob).lateral.ids("vistas")) == vistas
    assert not list(p.glob("Casa.obim.alheio-*"))


@pytest.mark.parametrize("fab", [_d1, _d2, _d3, _d4])
def test_12b_sem_alheio_nao_ha_pendencia(p, abre, fab):
    pr = abre(fab(p))
    assert pr.lateral_alheio is None
    with pytest.raises(ValueError):
        pr.escolher_lateral("criar_novo_lateral")


def test_13_regua_o_alheio_da_fixture_e_de_fato_alheio(p):
    ifc, ob, dados, _ = alheio(p)
    m = gravado(ob).manifesto
    assert m["ifc_projeto_globalid"] != X.GID and len(OUTRO_GID) == 22
    ifc2, ob2, _, _ = alheio(p / "b", "ladoid")
    assert gravado(ob2).manifesto["LadoId"] != X.LADO and gravado(ob2).manifesto["ifc_projeto_globalid"] == X.GID
    assert guardado(p, dados).name.startswith("Casa.obim.alheio-") and len(guardado(p, dados).name) == len("Casa.obim.alheio-") + 8


# 6) lateral ilegível não é "alheio": segue como hoje (sem a flag abre; com a flag a recusa sobe, não é engolida)
def test_14_lateral_ilegivel_sem_flag_abre_como_hoje_e_nao_vira_alheio(p, abre):
    ifc, ob = X.fazer(p)
    ob.write_bytes(b"lixo")
    pr = abre(ifc)
    assert obter(pr) == [] and ob.read_bytes() == b"lixo"
    assert getattr(pr, "lateral_alheio", None) is None


def test_15_lateral_ilegivel_com_flag_continua_levantando_LateralRecusado(p, abre):
    import openbim_app.divergencia as DV
    ifc, ob = X.fazer(p)
    ob.write_bytes(b"lixo")
    with pytest.raises(DV.LateralRecusado):
        abre(ifc, True)
    assert ob.read_bytes() == b"lixo"
