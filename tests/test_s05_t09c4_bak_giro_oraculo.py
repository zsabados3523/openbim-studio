# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo do F0-S05-T09c4, giro do `.bak` do autosave e corte do diário (2ª rodada da revisão do T09c, lote Opus 84). Quem tira os
`@AINDA_NAO` é o autor.
CONTRATO (soma-se ao de `test_s05_t09c_abrir_projeto_oraculo.py` e `test_s05_t09b_autosave_oraculo.py`):
- `Autosave.salvar()` zera o diário para o `autosave/Casa.ifc` atual ANTES de girar o `.bak`: se a base do diário ainda depende de um
  `zerar` que falhou, ele é refeito primeiro. Se esse zerar falhar, `salvar()` levanta sem gravar e não gira o `.bak` (a base do diário
  nunca fica apontando um arquivo que já saiu do autosave e do `.bak`). Só vale para pendência de seq deste diário (seq <= `ultimo_seq`);
  pendência órfã de sessão morta (seq além do último do diário novo) segue sem zerar, como cobra o test_06 do T09b.
- Passo 2 do `abrir_projeto`: a pendência de `autosave/` é resolvida com um `ao_concluir(seq)` que zera o diário para o autosave
  (`ifc_caminho` = `autosave/Casa.ifc`, `obim_sha256` = o do lateral dele), como o passo 1 já faz com o par do usuário.
- `Diario.continuar` com linha ruim no meio: os bytes cortados (registros inteiros que vinham depois) são copiados para
  `diario-descartado*.obimlog` antes do corte."""
import re  # noqa: E401
import pytest, openbim_app.diario as D  # noqa: E401
from s05_conteudo_aux import _limpa, base_ifc  # noqa: F401
from s05_t05_aux import igual
from test_s05_t05_diario_oraculo import local  # noqa: F401
from test_s05_t09b_autosave_oraculo import fabrica  # noqa: F401
from test_s05_t09c_abrir_projeto_oraculo import _Morte, _avisou, _cair, _foto, _morrer, _texto, _tx, abre  # noqa: F401

HORA = r"Recuperar o trabalho de \d\d:\d\d\?"


def _zerar_falha(obj, monkeypatch, erro):  # o zerar do diário falha antes da troca (no Windows, antivírus segurando o diario.obimlog)
    def falha(*a, **k):
        raise erro
    monkeypatch.setattr(obj, "zerar", falha)


def test_r3_dois_zerar_falhos_seguidos_e_queda_ainda_recupera(fabrica, abre, monkeypatch):  # noqa: F811
    # M: o 2º salvar() resolve a pendência sem zerar e gira o .bak: base no autosave A, autosave/ com C e .bak com B
    c = fabrica()
    c.tx(1)
    assert c.auto.salvar() is True  # autosave A, base do diário em A
    with monkeypatch.context() as mp:
        _zerar_falha(c.diario, mp, OSError(28, "falha simulada no zerar"))
        for tag in (2, 3):
            c.tx(tag)
            with pytest.raises(OSError):
                c.auto.salvar()
    c.tx(4)
    esperado = c.foto()
    regs = _morrer(c)
    p, perg = abre(c, True)
    assert perg == [_texto(regs)] and p.recuperado is True, p.avisos
    igual(_foto(p), esperado, "dois zerar falhos + queda")


def test_r4_zerar_falho_queda_sim_transacao_e_queda_entre_troca_e_zerar(fabrica, abre, monkeypatch):  # noqa: F811
    # M: passo 2 do abrir_projeto resolve a pendência do autosave sem levar a base do diário para o par novo
    c = fabrica()
    c.tx(1)
    assert c.auto.salvar() is True
    c.tx(2)
    with monkeypatch.context() as mp:
        _zerar_falha(c.diario, mp, OSError(28, "falha simulada no zerar"))
        with pytest.raises(OSError):
            c.auto.salvar()
    _morrer(c)
    p, perg = abre(c, True)
    assert len(perg) == 1 and re.fullmatch(HORA, perg[0]) and p.recuperado is True, p.avisos
    _tx(p, 3)
    esperado = _foto(p)
    with monkeypatch.context() as mp:
        _zerar_falha(p.diario, mp, _Morte())  # a sessão cai entre a troca do autosave e o zerar
        with pytest.raises(_Morte):
            p.autosave.salvar()
    _cair(p)
    p2, perg2 = abre(c, True)
    assert len(perg2) == 1 and re.fullmatch(HORA, perg2[0]) and p2.recuperado is True, p2.avisos
    igual(_foto(p2), esperado, "Sim + transação + queda entre a troca e o zerar")


def test_nota_linha_ruim_no_meio_guarda_os_bytes_cortados_no_descartado(fabrica, abre):  # noqa: F811
    # M: continuar() corta o arquivo sem copiar o que vinha depois da linha ruim
    c = fabrica()
    c.tx(1)
    apos_1 = c.foto()
    c.tx(2), c.tx(3)
    _morrer(c)
    cam = c.diario.caminho
    linhas = cam.read_bytes().splitlines(keepends=True)  # base, tx1, tx2, tx3
    assert len(linhas) == 4
    linhas[2] = (b"0" if linhas[2][:1] != b"0" else b"1") + linhas[2][1:]  # CRC errado no meio
    cam.write_bytes(b"".join(linhas))
    regs, av = D.ler_diario(str(cam))
    assert av and [r["seq"] for r in regs] == [0, 1]
    cortados = b"".join(linhas[2:])
    p, perg = abre(c, True)
    assert perg == [_texto(regs)] and p.recuperado is True
    _avisou(p)
    igual(_foto(p), apos_1, "linha ruim no meio: valem os registros inteiros antes dela")
    guardados = [x.read_bytes() for x in cam.parent.glob("diario-descartado*.obimlog")]
    assert any(cortados in g for g in guardados), "os registros cortados sumiram sem ir para o descartado"
