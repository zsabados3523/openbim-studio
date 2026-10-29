# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo do F0-S05-T09c5, base do diário refeita ao gravar sem editar (3ª rodada da revisão do T09c, lote Opus 84). Quem tira os
`@AINDA_NAO` é o autor.
CONTRATO (muda o do `Diario.zerar` do T09a2; soma-se ao de c1a, c1b, c2 e c4):
- `Diario.zerar(seq, *, ifc_caminho=None, obim_sha256=None)`: `seq` ABAIXO da base: nada muda. `seq` == seq da base: sem `ifc_caminho` e
  sem `obim_sha256`, nada muda; com algum deles, a base é REFEITA (mesmo seq, `ifc_caminho`/`ifc_sha256`/`ifc_tamanho`/`obim_sha256`
  novos, registros além do seq mantidos). `seq` acima da base: como antes. Motivo: gravar sem ter anotado nada desde o último zerar
  (Ctrl+S sem editar, autosave seguido de gravar, Sim e gravar) deixava a base no `Casa.ifc` antigo; a queda seguinte dizia "base não
  confere" e perdia o trabalho. AJUSTE no `test_13` do T09b: a linha `zerar(2, ifc_caminho=c.casa, obim_sha256="0"*64)` ("até a base:
  nada muda") passou a `zerar(1, ...)` ("abaixo da base: nada muda"); mesmo valor esperado, nada afrouxado, nenhum caso removido.
- `gravar_normal()`: o `ao_concluir` zera com o sha do lateral do retrato; se ele não foi calculado (o `gravar_par` resolveu antes uma
  pendência de gravação anterior, e o `seq()` ainda não rodou), calcula-o do `Casa.obim` já gravado.
- Sem marcador (passam hoje; matam mutantes que sobreviveram à 3ª rodada): `salvar()` com zerar falho na pendência não gira o `.bak`
  e leva a base ao autosave com o sha do `.obim` DELE; pendência de `autosave/` na abertura só zera o diário com `origem_ifc_sha256` =
  sha do `Casa.ifc` e `seq` <= último registro do diário; `Diario.continuar` corta o arquivo de verdade.
PENDÊNCIAS (sem caso aqui; notas baixas da 3ª rodada, a cobrar se o PO quiser): E9/E10 em `autosave/` move o `.bak` íntegro junto;
`zerar` falho no `ao_concluir` da abertura derruba `abrir_projeto` (o `gravacao.json` fica e tentar de novo resolve); `Diario.continuar`
deixa `_f` aberto se o `open` do descartado falhar."""
import re  # noqa: E401
import pytest, openbim_app.diario as D, openbim_app.gravacao_atomica as GA  # noqa: E401
from s05_conteudo_aux import _limpa, base_ifc  # noqa: F401
from s05_t05_aux import igual, sha
from test_s05_t05_diario_oraculo import local  # noqa: F401
from test_s05_t09b_autosave_oraculo import _base, fabrica  # noqa: F401
from test_s05_t09c_abrir_projeto_oraculo import _avisou, _cair, _foto, _morrer, _outro_casa, _tx, abre  # noqa: F401

HORA = r"Recuperar o trabalho de \d\d:\d\d\?"


def _reabre_e_confere(c, abre, esperado, onde):
    p, perg = abre(c, True)
    assert len(perg) == 1 and re.fullmatch(HORA, perg[0]) and p.recuperado is True, p.avisos
    igual(_foto(p), esperado, onde)


def test_p1a_abrir_gravar_sem_editar_transacao_e_queda(fabrica, abre):  # noqa: F811
    # M: zerar ignora seq == base.seq mesmo com ifc_caminho/obim_sha256: a base fica no Casa.ifc antigo
    c = fabrica()
    _morrer(c)
    p, perg = abre(c, True)
    assert perg == [] and p.autosave.gravar_normal()
    _tx(p, 2)
    esperado = _foto(p)
    _cair(p)
    _reabre_e_confere(c, abre, esperado, "p1a: abrir, gravar sem editar, tx, queda")


def test_p1b_gravar_duas_vezes_sem_editar_no_meio(fabrica, abre):  # noqa: F811
    # M: o mesmo da p1a, na 2ª gravação
    c = fabrica()
    c.tx(1), c.tx(2)
    c.auto.gravar_normal(), c.auto.gravar_normal()
    c.tx(3)
    esperado = c.foto()
    _morrer(c)
    _reabre_e_confere(c, abre, esperado, "p1b: gravar 2x, tx, queda")


def test_p1c_autosave_depois_gravar_sem_editar_transacao_e_queda(fabrica, abre):  # noqa: F811
    # M: o caso comum: o autosave dispara, o usuário grava, nada editado entre os dois
    c = fabrica()
    c.tx(1)
    assert c.auto.salvar() is True
    c.auto.gravar_normal()
    c.tx(2)
    esperado = c.foto()
    _morrer(c)
    _reabre_e_confere(c, abre, esperado, "p1c: tx, autosave, gravar, tx, queda")


def test_p1d_sim_a_partir_do_autosave_gravar_sem_editar_e_nova_queda(fabrica, abre):  # noqa: F811
    # M: base no autosave (Sim), gravar sem editar: a base não vai para o Casa.ifc novo
    c = fabrica()
    c.tx(1)
    assert c.auto.salvar() is True
    _morrer(c)
    p, perg = abre(c, True)
    assert len(perg) == 1 and p.recuperado is True
    p.autosave.gravar_normal()
    _tx(p, 2)
    esperado = _foto(p)
    _cair(p)
    _reabre_e_confere(c, abre, esperado, "p1d: Sim, gravar sem editar, tx, queda")


def test_zerar_no_seq_da_base_com_opcionais_refaz_a_base(fabrica, tmp_path):  # noqa: F811
    # M: retorno cedo com seq <= base.seq; refazer a base também sem os opcionais; refazer com seq abaixo da base
    c = fabrica(criar_auto=False)
    c.tx(1), c.tx(2)
    nova = tmp_path / "nova" / "Casa.ifc"
    nova.parent.mkdir()
    c.f.write(str(nova))
    c.diario.zerar(1, ifc_caminho=nova, obim_sha256="1" * 64)
    base, resto = _base(c)
    assert (base["seq"], base["obim_sha256"], [r["seq"] for r in resto]) == (1, "1" * 64, [2])
    c.diario.zerar(1)
    c.diario.zerar(0, ifc_caminho=c.casa, obim_sha256="2" * 64)
    assert _base(c)[0] == base
    c.diario.zerar(1, ifc_caminho=c.casa, obim_sha256="2" * 64)
    base2, resto2 = _base(c)
    assert (base2["seq"], base2["ifc_sha256"], base2["obim_sha256"], [r["seq"] for r in resto2]) == (1, sha(c.casa), "2" * 64, [2])
    assert c.diario.ultimo_seq == 2


def test_defeito2_gravar_normal_sha_do_lateral_apos_pre_resolver(fabrica, abre, monkeypatch):  # noqa: F811
    # M: ao_concluir do gravar_normal com sha_lat None (o pré-resolver roda antes do seq()): a base mantém o lateral velho
    c = fabrica()
    c.tx(1)
    with monkeypatch.context() as mp:
        mp.setattr(c.diario, "zerar", lambda *a, **k: (_ for _ in ()).throw(OSError(5, "zerar falho (antivírus)")))
        with pytest.raises(OSError):
            c.auto.gravar_normal()
    c.tx(2)
    with monkeypatch.context() as mp:  # a 2ª gravação resolve a pendência da 1ª e falha logo depois (disco cheio)
        mp.setattr(GA, "preparar", lambda *a, **k: (_ for _ in ()).throw(OSError(28, "disco cheio")))
        with pytest.raises(OSError):
            c.auto.gravar_normal()
    esperado = c.foto()
    _morrer(c)
    _reabre_e_confere(c, abre, esperado, "defeito 2: sha do lateral na base depois do pré-resolver")


def _zerar_falho(c, mp, erro=OSError(28, "falha simulada no zerar")):
    def f(*a, **k):
        raise erro
    mp.setattr(c.diario, "zerar", f)


def _sobras_de_zerar_falho(c, monkeypatch):  # tx1, autosave A; tx2 com zerar falho: autosave B, .bak A, base em A, pendência seq 2
    c.tx(1)
    assert c.auto.salvar() is True
    c.tx(2)
    with monkeypatch.context() as mp:
        _zerar_falho(c, mp)
        with pytest.raises(OSError):
            c.auto.salvar()


def test_salvar_com_zerar_falho_na_pendencia_nao_gira_o_bak(fabrica, monkeypatch):  # noqa: F811
    # M: ao_concluir=lambda s: None no resolver do salvar(); erro do zerar engolido (o salvar segue e gira o .bak)
    c = fabrica()
    _sobras_de_zerar_falho(c, monkeypatch)
    bak = c.auto_ifc.with_name(c.auto_ifc.name + ".bak")
    antes = (c.auto_ifc.read_bytes(), bak.read_bytes(), c.auto_obim.read_bytes(), _base(c)[0])
    c.tx(3)
    with monkeypatch.context() as mp:
        _zerar_falho(c, mp)
        with pytest.raises(OSError):
            c.auto.salvar()
    assert (c.auto_ifc.read_bytes(), bak.read_bytes(), c.auto_obim.read_bytes(), _base(c)[0]) == antes, "o salvar() girou o .bak"
    assert c.auto.salvar() is True  # o zerar voltou: a base vai ao autosave novo
    base, resto = _base(c)
    assert resto == [] and base["ifc_sha256"] == sha(c.auto_ifc) and base["obim_sha256"] == c.sha_lat()


def test_zerar_da_pendencia_usa_o_sha_do_obim_do_autosave(fabrica, monkeypatch):  # noqa: F811
    # M: sha do self._lateral (já com a tx3) em vez do .obim do autosave B
    c = fabrica()
    c.tx(1)
    assert c.auto.salvar() is True
    c.tx(2)
    sha2 = c.sha_lat()
    with monkeypatch.context() as mp:
        _zerar_falho(c, mp)
        with pytest.raises(OSError):
            c.auto.salvar()
    c.tx(3)
    assert c.sha_lat() != sha2
    with monkeypatch.context() as mp:  # o pré-resolver zera e a gravação falha logo depois (disco cheio)
        mp.setattr(GA, "preparar", lambda *a, **k: (_ for _ in ()).throw(OSError(28, "disco cheio")))
        with pytest.raises(OSError):
            c.auto.salvar()
    base = _base(c)[0]
    assert (base["seq"], base["ifc_sha256"], base["obim_sha256"]) == (2, sha(c.auto_ifc), sha2)


def test_pendencia_do_autosave_de_outro_casa_nao_zera_o_diario(fabrica, abre, monkeypatch):  # noqa: F811
    # M: ao_concluir do passo 2 sem conferir origem_ifc_sha256 = sha do Casa.ifc (reescreve o diário que vai ser descartado)
    c = fabrica()
    _sobras_de_zerar_falho(c, monkeypatch)
    _morrer(c)
    _outro_casa(c)
    morto = c.diario.caminho.read_bytes()
    p, perg = abre(c, True)
    assert perg == [] and p.recuperado is False
    _avisou(p)
    assert morto in [x.read_bytes() for x in c.diario.caminho.parent.glob("diario-descartado*.obimlog")]


def test_pendencia_orfa_do_autosave_nao_zera_diario_mais_curto(fabrica, abre, monkeypatch):  # noqa: F811
    # M: ao_concluir do passo 2 sem seq <= último registro do diário (T09b test_06, na abertura)
    c = fabrica()
    c.tx(1)
    apos_1 = c.foto()
    c.tx(2)
    with monkeypatch.context() as mp:  # autosave B (seq 2) com o zerar falho: fica a pendência seq 2
        _zerar_falho(c, mp)
        with pytest.raises(OSError):
            c.auto.salvar()
    _morrer(c)
    cam = c.diario.caminho
    cam.write_bytes(b"".join(cam.read_bytes().splitlines(keepends=True)[:2]))  # o diário só tem a base e a tx1: seq 2 não é dele
    p, perg = abre(c, True)
    assert len(perg) == 1 and p.recuperado is True and not (c.pasta_auto / "gravacao.json").exists()
    igual(_foto(p), apos_1, "pendência órfã do autosave não zera o diário")


def test_continuar_corta_a_cauda_rasgada_no_arquivo(fabrica, abre):  # noqa: F811
    # M: Diario.continuar sem truncate (a cauda rasgada fica no arquivo)
    c = fabrica()
    c.tx(1), c.tx(2)
    _morrer(c)
    cam = c.diario.caminho
    valido = cam.read_bytes()
    cam.write_bytes(valido + b'0badc0de {"v":1,"seq":99,"tipo":"transa')
    p, perg = abre(c, True)
    assert len(perg) == 1 and p.recuperado is True
    assert cam.read_bytes() == valido
