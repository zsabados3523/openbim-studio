# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo do F0-S05-T09c1b, o autosave na abertura (`abrir_projeto`; ADR-002 §4.7; nota 5 da revisão do T09a2). Quem tira os
`@AINDA_NAO` é o autor. CONTRATO: o de `test_s05_t09c_abrir_projeto_oraculo.py` (T09c1a), itens do autosave: base no autosave ou no
seu `.bak` (só com `origem_ifc_sha256` = sha256 do `Casa.ifc`), pergunta mesmo sem registros além dessa base, e pendência que não se
resolve em `autosave/` movida para `autosave-descartado/`, com aviso, sem travar o próximo `salvar()`."""
import json, re  # noqa: E401
import pytest, openbim_app.gravacao_atomica as GA, openbim_app.gravacao_par as GP  # noqa: E401
from s05_conteudo_aux import _limpa, base_ifc  # noqa: F401
from s05_t05_aux import igual, sha
from test_s05_t05_diario_oraculo import local  # noqa: F401
from test_s05_t09b_autosave_oraculo import fabrica  # noqa: F401
from test_s05_t09c_abrir_projeto_oraculo import _Morte, _avisou, _disco, _foto, _morrer, _outro_casa, _pasta, _texto, _tx, abre  # noqa: F401



def test_06b_autosave_de_outro_casa_nao_se_aplica(fabrica, abre):  # noqa: F811
    # M: aceitar autosave cuja origem_ifc_sha256 não é o Casa.ifc atual
    c = fabrica()
    c.tx(1)
    assert c.auto.salvar() is True
    _morrer(c)
    _outro_casa(c)
    antes = _pasta(c)
    p, perg = abre(c, True)
    assert perg == [] and p.recuperado is False and _pasta(c) == antes
    _avisou(p)
    igual(_foto(p), _disco(c), "autosave de outro Casa.ifc")


def test_07_autosave_sem_registro_alem_da_base_e_recuperado(fabrica, abre):  # noqa: F811
    # M: só perguntar com registros além da base; aplicar sobre o Casa.ifc; exigir origem errada
    c = fabrica()
    c.tx(1)
    assert c.auto.salvar() is True
    esperado = c.foto()
    regs = _morrer(c)
    assert len(regs) == 1 and regs[0]["ifc_sha256"] == sha(c.auto_ifc)
    antes = _pasta(c)
    p, perg = abre(c, True)
    assert len(perg) == 1 and re.fullmatch(r"Recuperar o trabalho de \d\d:\d\d\?", perg[0]) and p.recuperado is True
    igual(_foto(p), esperado, "base no autosave, sem registros depois")
    assert _pasta(c) == antes


def test_08_base_no_bak_do_autosave_e_aceita(fabrica, abre, monkeypatch):  # noqa: F811
    # nota 5 da revisão do T09a2: o zerar falhou antes da troca e a base aponta o autosave anterior, hoje o .bak
    # M: aceitar só o autosave atual; ler o lateral do .obim errado
    c = fabrica()
    c.tx(1)
    assert c.auto.salvar() is True
    c.tx(2)
    zerar = c.diario.zerar
    with monkeypatch.context() as mp:
        mp.setattr(c.diario, "zerar", lambda *a, **k: (_ for _ in ()).throw(OSError(28, "falha simulada no zerar")))
        with pytest.raises(OSError):
            c.auto.salvar()
    assert c.diario.zerar == zerar
    c.tx(3)
    assert GP.resolver_gravacao_pendente(c.pasta_auto, c.auto_ifc, None) == "concluido"  # como o salvar() seguinte faz
    esperado = c.foto()
    regs = _morrer(c)
    bak = c.auto_ifc.with_name(c.auto_ifc.name + ".bak")
    assert regs[0]["ifc_sha256"] == sha(bak) != sha(c.auto_ifc) and [r["seq"] for r in regs[1:]] == [2, 3]
    p, perg = abre(c, True)
    assert perg == [_texto(regs)] and p.recuperado is True
    igual(_foto(p), esperado, "base no .bak do autosave")


def test_08b_pendencia_do_autosave_resolvida_na_abertura(fabrica, abre, monkeypatch):  # noqa: F811
    # nota 1 da revisão do oráculo: o salvar() do autosave morre em E6 (Casa.ifc do autosave trocado, .obim não; o .obim.tmp fica)
    # M: não resolver a pendência de autosave/ no passo 2 (aí nem o autosave nem o .bak casam com a base)
    c = fabrica()
    c.tx(1)
    assert c.auto.salvar() is True
    c.tx(2)
    conf, res, n = GA.confirmar, GP.resolver_gravacao_pendente, {"c": 0, "r": 0}

    def conf_falha(prep):
        n["c"] += 1
        if n["c"] == 2:
            raise OSError(5, "falha simulada na troca do .obim do autosave")
        return conf(prep)

    def res_morre(*a, **k):
        n["r"] += 1
        if n["r"] == 2:
            raise _Morte()
        return res(*a, **k)
    with monkeypatch.context() as mp:
        mp.setattr(GA, "confirmar", conf_falha), mp.setattr(GP, "resolver_gravacao_pendente", res_morre)
        with pytest.raises(_Morte):
            c.auto.salvar()
    c.tx(3)
    esperado = c.foto()
    regs = _morrer(c)
    assert (c.pasta_auto / "gravacao.json").exists() and c.auto_obim.with_name(c.auto_obim.name + ".tmp").exists()
    assert [r["seq"] for r in regs[1:]] == [2, 3]
    p, perg = abre(c, True)
    assert perg == [_texto(regs)] and p.recuperado is True and not (c.pasta_auto / "gravacao.json").exists()
    igual(_foto(p), esperado, "pendência E6 do autosave resolvida na abertura")


def _ilegivel(c):
    return b"{nao e json"


def _destino_alterado(c):  # gravacao.json legível, mas o autosave/Casa.ifc não é nem o antigo nem o novo dele
    c.auto_ifc.write_bytes(b"outro conteudo")
    lado = lambda cam: {"caminho": str(cam.absolute()), "temporario": str(cam.absolute()) + ".tmp", "antigo_sha256": "0" * 64,  # noqa: E731
                        "antigo_tamanho": 1, "novo_sha256": "1" * 64, "novo_tamanho": 1}
    return json.dumps({"versao": 1, "lado_id": c.lado_id, "Revisao": 1, "seq": 1,
                       "ifc": lado(c.auto_ifc), "obim": lado(c.auto_obim)}).encode("utf-8")


@pytest.mark.parametrize("gerar,estado", [(_ilegivel, "gravacao_ilegivel"), (_destino_alterado, "destino_alterado")],
                         ids=["ilegivel", "destino_alterado"])
def test_09_pendencia_irresoluvel_em_autosave_tem_saida(fabrica, abre, gerar, estado):  # noqa: F811
    # M: autosave travado para sempre (RuntimeError a cada salvar); apagar a pendência sem guardar; não avisar; mover só o ilegível
    c = fabrica()
    _morrer(c)
    c.pasta_auto.mkdir(parents=True, exist_ok=True)
    lixo = gerar(c)
    (c.pasta_auto / "gravacao.json").write_bytes(lixo)
    assert GP.resolver_gravacao_pendente(c.pasta_auto, c.auto_ifc) == estado
    antes = _pasta(c)
    p, perg = abre(c, True)
    assert perg == [] and _pasta(c) == antes
    _avisou(p)
    assert (c.pasta_proj / "autosave-descartado" / "gravacao.json").read_bytes() == lixo
    _tx(p, 5)
    assert p.autosave.salvar() is True and c.auto_ifc.exists()
