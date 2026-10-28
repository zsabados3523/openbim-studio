# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo do F0-S05-T09c1a, `abrir_projeto` (ordem ao abrir; ADR-002 §4.4, §4.5, §4.7). Quem tira os `@AINDA_NAO` é o autor.
CONTRATO: `openbim_app.autosave.abrir_projeto(ifc_caminho, perguntar) -> Projeto`. Sem Qt: `perguntar(texto) -> bool` é do chamador.
- `Projeto`: `caminho` (Path do Casa.ifc), `lado_id`, `arquivo` (ifcopenshell), `lateral` (Lateral do Casa.obim; vazio sem ele), `sessao`
  (SessaoModelo do `arquivo`), `historico` (Historico vazio que anota no diário pelo `autosave.anotar`), `diario` (Diario aberto),
  `autosave` (Autosave parado, `ifc_origem` = Casa.ifc), `recuperado` (bool: "recuperado, não gravado"), `avisos` (list[str], frases
  não vazias), `pendencia` (resultado de `resolver_gravacao_pendente` do par do usuário: "sem_pendencia", "concluido", "desfeito", ...).
- Ordem: 1) `gravacao.json` do par do usuário em `pasta_projeto(lado_id)`; 2) pendência e par do autosave em `<pasta>/autosave/`;
  3) o diário. Pendência de sessão morta se resolve AQUI, antes do diário; se ela conclui (`ao_concluir(seq)`), os registros até `seq`
  já estão no par novo e só os seguintes contam, sobre o par novo. Pendência do par que não se resolve (E9, E10, ilegível): avisa, não
  mexe no par nem no `gravacao.json`, segue abrindo o `Casa.ifc` como está.
- Pendência que não se resolve em `autosave/` (a pasta é nossa): avisa e tira o autosave do caminho, movendo o conteúdo para
  `<pasta>/autosave-descartado/` (uma geração); o próximo `autosave.salvar()` grava.
- Base do diário: casa com o `Casa.ifc` (+ lateral do `Casa.obim`), com o autosave (`autosave/Casa.ifc` e `.obim`, manifesto com
  `origem_ifc_sha256` = sha256 do `Casa.ifc`) ou com o `.bak` desse autosave (`Casa.ifc.bak` e `Casa.obim.bak`), comparando sha256 do
  IFC e `obim_sha256` do lateral. Base que não casa: não aplica, avisa, não pergunta; o diário vira descartado.
- Pergunta (uma vez) quando há trabalho fora do `Casa.ifc`: registros além da base que casa, ou base que é o autosave (ou seu `.bak`).
  Texto exato "Recuperar o trabalho de HH:MM?", hora local do último registro inteiro. Sim: estado = base + registros, `recuperado`
  True, histórico vazio, e uma nova queda logo depois pergunta de novo e devolve o mesmo estado. Não: estado = `Casa.ifc`, o diário vira
  `diario-descartado*.obimlog` e a reabertura não pergunta mais.
- Os itens do autosave (2, base no autosave ou no `.bak`, pergunta só com o autosave) são cobrados em
  `test_s05_t09c1b_autosave_na_abertura_oraculo.py` (T09c1b); aqui só a ordem, o par do usuário e o diário.
- Nunca grava por cima do `Casa.ifc`/`Casa.obim` sozinho (a pasta do usuário só muda ao concluir ou desfazer a pendência do item 1)."""
import datetime, hashlib, json, re, zipfile  # noqa: E401
from contextlib import suppress
import pytest, openbim_app.diario as D, openbim_app.gravacao_atomica as GA, openbim_app.gravacao_par as GP  # noqa: E401
from openbim_app.lateral import Lateral
import s05_conteudo_aux as R, s05_t07_aux as X7  # noqa: E401
from s05_conteudo_aux import _limpa, base_ifc  # noqa: F401
from s05_t05_aux import igual, sha
from test_s05_t05_diario_oraculo import local  # noqa: F401
from test_s05_t09b_autosave_oraculo import fabrica  # noqa: F401

AINDA_NAO = pytest.mark.xfail(strict=True, reason="T09c1a: abrir_projeto ainda não existe")


def _cair(p):  # a sessão morre sem gravar: solta os arquivos e não descarta nada
    with suppress(Exception):
        p.autosave.parar()
    p.diario.fechar(), p.historico.encerrar()


@pytest.fixture
def abre(fabrica):  # noqa: F811
    abertos = []

    def f(c, resposta=True):
        import openbim_app.autosave as A
        perg = []
        p = A.abrir_projeto(c.casa, lambda texto: (perg.append(texto), resposta)[1])
        abertos.append(p)
        return p, perg
    yield f
    for p in abertos:
        with suppress(Exception):
            _cair(p)


def _morrer(c):  # a sessão da cena morre: o diário fica no disco como está
    with suppress(Exception):
        c.auto.parar()
    c.diario.fechar()
    regs, av = D.ler_diario(str(c.diario.caminho))
    assert av == [] and regs, av
    return regs


def _texto(regs):
    hora = datetime.datetime.fromisoformat(regs[-1]["hora"]).astimezone().strftime("%H:%M")
    return f"Recuperar o trabalho de {hora}?"


_pasta = lambda c: {x.name: x.read_bytes() for x in c.casa.parent.iterdir()}  # noqa: E731
_disco = lambda c: R.foto(R.ifcopenshell.open(str(c.casa)), Lateral(X7.ler_obim(c.obim)[1]) if c.obim.exists() else Lateral())  # noqa: E731
_foto = lambda p: R.foto(p.arquivo, p.lateral)  # noqa: E731
_sha_lat = lambda lat: hashlib.sha256(lat.canonico()).hexdigest()  # noqa: E731


def _avisou(p):
    assert p.avisos and all(isinstance(a, str) and a.strip() for a in p.avisos), p.avisos


def _vazio(p):  # histórico começa vazio
    assert not list(p.arquivo.history) and not p.historico.pode_desfazer and not p.historico.pode_refazer


def _tx(p, tag):
    with p.sessao.escrever() as esc, p.historico.transacao(esc) as t:
        X7.mudar(t.ifc, t.lado.criar, tag)


@AINDA_NAO
@pytest.mark.parametrize("com_obim", [True, False])
def test_01_abertura_limpa_nao_pergunta_e_liga_o_diario(fabrica, abre, com_obim):  # noqa: F811
    # M: pergunta sem trabalho; lateral não lido do Casa.obim; histórico sem anotar no diário; aviso à toa
    c = fabrica(com_obim=com_obim)
    _morrer(c)
    antes = _pasta(c)
    p, perg = abre(c)
    assert perg == [] and p.avisos == [] and p.recuperado is False and p.pendencia == "sem_pendencia" and p.lado_id == c.lado_id
    igual(_foto(p), _disco(c), "abertura limpa")
    assert _sha_lat(p.lateral) == c.sha_lat() and _pasta(c) == antes
    _vazio(p)
    _tx(p, 5)
    assert p.diario.ultimo_seq == 1 and p.autosave.salvar() is True and _pasta(c) == antes
    assert p.diario.caminho == D.pasta_projeto(c.lado_id) / "diario" / "diario.obimlog"


@AINDA_NAO
def test_02_sim_recupera_do_diario_sem_gravar_no_casa_e_sobrevive_a_nova_queda(fabrica, abre):  # noqa: F811
    # M: texto/hora errados; perguntar 2x; gravar por cima do Casa.ifc; histórico com passos; nova queda perde o recuperado
    c = fabrica()
    c.tx(1), c.tx(2), c.passo()
    esperado = c.foto()
    regs = _morrer(c)
    antes = _pasta(c)
    p, perg = abre(c, True)
    assert perg == [_texto(regs)] and p.recuperado is True and _pasta(c) == antes
    igual(_foto(p), esperado, "recuperar do diário")
    _vazio(p)
    _cair(p)
    p2, perg2 = abre(c, True)
    assert len(perg2) == 1 and re.fullmatch(r"Recuperar o trabalho de \d\d:\d\d\?", perg2[0]) and p2.recuperado is True
    igual(_foto(p2), esperado, "nova queda logo depois de recuperar")
    assert _pasta(c) == antes


@AINDA_NAO
def test_03_nao_descarta_o_diario_e_nao_pergunta_de_novo(fabrica, abre):  # noqa: F811
    # M: aplicar mesmo com Não; apagar o diário sem descartado; perguntar de novo na reabertura
    c = fabrica()
    c.tx(1)
    _morrer(c)
    morto, antes = c.diario.caminho.read_bytes(), _pasta(c)
    p, perg = abre(c, False)
    assert len(perg) == 1 and p.recuperado is False and _pasta(c) == antes
    igual(_foto(p), _disco(c), "recusar a recuperação")
    assert morto in [x.read_bytes() for x in c.diario.caminho.parent.glob("diario-descartado*.obimlog")]
    _cair(p)
    p2, perg2 = abre(c, True)
    assert perg2 == [] and p2.recuperado is False


def _outro_casa(c):  # outro programa grava o Casa.ifc (mesmo LadoId, sha256 novo)
    f = R.ifcopenshell.open(str(c.casa))
    f.by_type("IfcProject")[0].Name = "mudado por outro programa"
    f.write(str(c.casa))


def _outro_obim(c):  # outro lateral no Casa.obim, mesmo manifesto
    man, objs = X7.ler_obim(c.obim)
    objs.setdefault("notas", {})["n0"] = {"texto": "mudado por outro programa"}
    with zipfile.ZipFile(c.obim, "w") as z:
        z.writestr("manifest.json", json.dumps(man))
        [z.writestr(f"{k}/{i}.json", json.dumps(o)) for k, d in objs.items() for i, o in d.items()]


@AINDA_NAO
@pytest.mark.parametrize("mexe,auto", [(_outro_casa, False), (_outro_obim, False)], ids=["ifc", "obim"])
def test_04_base_que_nao_casa_avisa_e_nao_aplica(fabrica, abre, mexe, auto):  # noqa: F811
    # M: aplicar sobre outro arquivo; aceitar autosave cuja origem_ifc_sha256 não é o Casa.ifc; perguntar; não avisar; manter o diário vivo
    c = fabrica()
    c.tx(1)
    assert not auto or c.auto.salvar() is True
    _morrer(c)
    mexe(c)
    morto, antes = c.diario.caminho.read_bytes(), _pasta(c)
    p, perg = abre(c, True)
    assert perg == [] and p.recuperado is False and _pasta(c) == antes
    _avisou(p)
    igual(_foto(p), _disco(c), "base que não casa")
    assert morto in [x.read_bytes() for x in c.diario.caminho.parent.glob("diario-descartado*.obimlog")]
    _cair(p)
    assert abre(c, True)[1] == []


class _Morte(BaseException):
    pass


def _morrer_gravando(c, monkeypatch, estado):  # gravação normal da cena morre em E7 (troca feita) ou E6 (só o IFC trocado, sem o tmp)
    seq = lambda: c.diario.ultimo_seq  # noqa: E731
    kw = dict(sessao=c.sessao, historico=c.h, lateral=c.lat, destino=c.casa, pasta_projeto=c.pasta_proj, lado_id=c.lado_id, seq=seq)
    if estado == "E7":
        def morre(s):
            raise _Morte()
        with pytest.raises(_Morte):
            GP.gravar_par(**kw, ao_concluir=morre)
        return
    conf, res, n = GA.confirmar, GP.resolver_gravacao_pendente, {"c": 0, "r": 0}

    def conf_falha(prep):
        n["c"] += 1
        if n["c"] == 2:
            raise OSError(5, "falha simulada na troca do .obim")
        return conf(prep)

    def res_morre(*a, **k):
        n["r"] += 1
        if n["r"] == 2:
            raise _Morte()
        return res(*a, **k)
    with monkeypatch.context() as mp:
        mp.setattr(GA, "confirmar", conf_falha), mp.setattr(GP, "resolver_gravacao_pendente", res_morre)
        with pytest.raises(_Morte):
            GP.gravar_par(**kw, ao_concluir=lambda s: None)
    c.obim.with_name(c.obim.name + ".tmp").unlink()


@AINDA_NAO
@pytest.mark.parametrize("estado", ["E7", "E6"])
def test_05_ordem_gravacao_json_antes_do_diario(fabrica, abre, monkeypatch, estado):  # noqa: F811
    # M: ler o diário antes do gravacao.json; concluir com o ao_concluir de outra sessão; reaplicar registros já gravados
    c = fabrica()
    sha_antigo = sha(c.casa)
    ponto = lambda: c.f.createIfcCartesianPoint((1.0, 2.0, 3.0))  # noqa: E731  (criar não é idempotente: reaplicar o gravado duplica)
    c.tx(1, ponto), c.tx(2, ponto)
    antes_de_gravar = c.foto()
    _morrer_gravando(c, monkeypatch, estado)
    gj = c.pasta_proj / "gravacao.json"
    assert gj.exists()
    if estado == "E7":
        c.tx(3)
    esperado = c.foto() if estado == "E7" else antes_de_gravar
    regs = _morrer(c)
    p, perg = abre(c, True)
    assert not gj.exists() and p.pendencia == ("concluido" if estado == "E7" else "desfeito")
    assert (sha(c.casa) != sha_antigo) is (estado == "E7")
    assert perg == [_texto(regs)] and p.recuperado is True
    igual(_foto(p), esperado, f"{estado}: gravacao.json resolvido antes do diário")


@AINDA_NAO
def test_06_pendencia_do_par_que_nao_se_resolve_avisa_e_nao_mexe(fabrica, abre, monkeypatch):  # noqa: F811
    # M: apagar o gravacao.json; mexer no Casa.ifc; aplicar o diário sobre arquivo de outro programa
    c = fabrica()
    c.tx(1)
    _morrer_gravando(c, monkeypatch, "E7")
    _morrer(c)
    _outro_casa(c)
    gj = c.pasta_proj / "gravacao.json"
    antes, dados = _pasta(c), gj.read_bytes()
    p, perg = abre(c, True)
    assert p.pendencia == "destino_alterado" and gj.read_bytes() == dados and _pasta(c) == antes
    assert perg == [] and p.recuperado is False
    _avisou(p)
