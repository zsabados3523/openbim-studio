# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo do F0-S06-T09b: abrir SÓ o `.ifc` (sem `.obim`) mostra as vistas e pranchas com estilo padrão (cartão T09b; README da S06, regra 1).
Fluxo real: base em disco, `Sessao`, 2 vistas + 1 prancha numa transação, `gravar_par`, APAGA o `.obim`, `abrir_projeto(ifc, ..., divergencia=True)`.
CONTRATO (comportamento atual, sem API nova):
1. A lista de vistas e de pranchas lida do modelo aberto é a que foi criada (nomes, tipos, escalas, ordem da prancha), em IFC2X3, IFC4 e IFC4X3.
2. Abrir não dá erro, não avisa nada, classifica como D4 (lateral ausente) com `estilo_padrao` e `vistas_preservadas` = 2; `Projeto.lateral` é vazio
   (sem estilos, viewports ou pranchas do `.obim`) e `lateral_alheio` é None.
3. Abrir não cria `Casa.obim` (nem `.tmp`) e não altera o `.ifc` (bytes iguais), também depois de parar o autosave e o diário.
GUARDA (pula, nunca afrouxa): sem ifcopenshell, pula; com OBIM_S05_OBRIGATORIO=1 vira falha."""
import hashlib

import ifcopenshell
import pytest
import s05_conteudo_aux as R
import s06_t04_aux as A
from s05_conteudo_aux import _limpa  # noqa: F401  (fixture autouse)
from s06_t04_sessao_aux import Sessao
from test_s06_t09_antes_depois_oraculo import criar, gravar, montar_base


@pytest.fixture(autouse=True)
def _local(tmp_path, monkeypatch):
    R.exigir()
    monkeypatch.setenv("OBIM_PASTA_LOCAL", str(tmp_path / "local"))


@pytest.fixture(params=A.ESQUEMAS)
def par_sem_obim(request, tmp_path):
    base = montar_base(request.param, tmp_path / "Base.ifc")
    destino, pasta = tmp_path / "proj" / "Casa.ifc", tmp_path / "pasta"
    destino.parent.mkdir()
    pasta.mkdir()
    s = Sessao(ifcopenshell.open(str(base)))
    criar(s)
    gravar(s, destino, pasta)
    s.encerrar()
    obim = destino.with_suffix(".obim")
    assert obim.exists(), "premissa: gravar_par grava o par"
    obim.unlink()
    return request.param, destino, obim


@pytest.fixture
def abre():
    import openbim_app.autosave as S
    abertos = []

    def f(ifc):
        pr = S.abrir_projeto(ifc, lambda t: True, divergencia=True)
        abertos.append(pr)
        return pr
    yield f
    for pr in abertos:
        for fn in (pr.autosave.parar, pr.diario.fechar, pr.historico.encerrar):
            try:
                fn()
            except Exception:  # noqa: BLE001
                pass


def _sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def test_vistas_e_pranchas_aparecem_so_com_o_ifc(par_sem_obim, abre):
    import openbim_app.vistas_ifc as V
    _, ifc, _ = par_sem_obim
    g = abre(ifc).arquivo
    vistas = {v["nome"]: v for v in V.listar_vistas(g)}
    assert sorted(vistas) == ["Corte AA", "Planta Térreo"]
    assert vistas["Planta Térreo"]["tipo"] == "PLANTA" and vistas["Planta Térreo"]["escala"] == "1:50"
    assert vistas["Corte AA"]["tipo"] == "CORTE"
    p = V.ler_prancha(g, "A-01")
    assert p["titulo"] == "Plantas e cortes"
    assert [V.ler_vista(g, x)["nome"] for x in p["vistas"]] == ["Corte AA", "Planta Térreo"]
    assert len(V.listar_pranchas(g)) == 2, "A-01 e a folha externa X-1"
    assert V.ler_prancha(g, "X-1")["vistas"] == []


def test_abrir_sem_obim_e_caso_d4_com_estilo_padrao_e_sem_lateral(par_sem_obim, abre):
    from openbim_app.lateral import Lateral
    _, ifc, _ = par_sem_obim
    pr = abre(ifc)
    d = pr.divergencia
    assert d.caso == "D4" and d.estilo_padrao is True and d.vistas_preservadas == 2 and d.obim is None
    assert d.aviso and "estilo e posição padrão" in d.aviso
    assert pr.avisos == [d.aviso], "nenhum outro aviso nem erro"
    assert pr.lateral.canonico() == Lateral().canonico(), "sem .obim o lateral é vazio (estilo padrão)"
    assert pr.lateral_alheio is None and pr.recuperado is False


def test_abrir_nao_cria_obim_nem_altera_o_ifc(par_sem_obim, abre):
    _, ifc, obim = par_sem_obim
    antes = ifc.read_bytes()
    pr = abre(ifc)
    pr.autosave.parar()
    pr.diario.fechar()
    assert not obim.exists() and not list(ifc.parent.glob("*.obim*")) and not list(ifc.parent.glob("*.tmp"))
    assert ifc.read_bytes() == antes and _sha(ifc) == hashlib.sha256(antes).hexdigest()
    assert sorted(f.name for f in ifc.parent.iterdir()) == ["Casa.ifc"]
