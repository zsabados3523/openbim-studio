# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo do F0-S06-T05, `.obim` real (ZIP 0.2.0). Fontes: ADR-003 §4 a §8 e §11 (T05 a a h); cartão T05; decisão do PO de 29/10 (vista por
GlobalId, prancha por `Identification`, viewport guarda o GlobalId da vista). Só o autor do oráculo tira os `@AINDA_NAO` (xfail estrito).
CONTRATO. Os nomes de `obim_zip` abaixo são PROPOSTOS NESTE TESTE (o ADR só fixa o formato); o ADR-003 e o cartão não nomeiam a API.
`openbim_app/obim_zip.py` (sem Qt, sem ifcopenshell, só stdlib e `lateral`):
- `VERSAO_FORMATO == "0.2.0"`; `class ObimInvalido(ValueError)`.
- `escrever(caminho, lateral, manifesto, extras=None)`: ZIP deflate. `manifest.json` = o `manifesto` dado, campo a campo (inclui os desconhecidos). Uma entrada
  `<coleção>/<id>.json` por objeto do `Lateral` (JSON canônico). `extras` = {nome da entrada: bytes} para entrada que não é JSON do lateral
  (`titleblocks/<id>.svg`, `assets/...`), gravada como veio. Valida antes de abrir o arquivo; falha = `ObimInvalido` e NADA gravado em `caminho`.
- `ler(caminho)` devolve objeto com: `.manifesto` (dict), `.lateral` (`Lateral`), `.extras` ({nome: bytes}, tudo que não é `manifest.json` nem
  `<coleção>/<id>.json`), `.versao_original` (texto), `.somente_leitura` (bool). Migra em memória: 0.1.0 devolve `.manifesto["versao_formato"] == "0.2.0"`
  sem `provisorio`; `.versao_original` guarda "0.1.0". Versão fora de 0.1 e 0.2 (ex. 0.3.0, 1.0.0) abre com `.somente_leitura` True e não perde nada.
  Entrada de caminho perigoso (`..`, absoluto, `\\`) ou sem `manifest.json` ou manifesto sem `formato == "obim-lateral"` = `ObimInvalido`.
- Validação (em `escrever` e, por ela, em `gravar_par`): coleção `vistas`: `vista_guid` texto não vazio, único; `pranchas`: `identification` texto não vazio,
  sem espaço nas pontas, único (comparação exata); `viewports`: `prancha` e `vista_guid` texto não vazio, `x` e `y` números, `escala` número > 0,
  par (`prancha`, `vista_guid`) único. Chave vive no CAMPO do JSON; o nome do arquivo é o id do `Lateral` (UUID), nunca a chave.
- `orfaos(lateral, vista_guids, identifications)` -> {"vistas": [ids], "pranchas": [ids], "viewports": [ids]} (ids do lateral, ordenados): o que o `.obim`
  cita e o IFC (os dois conjuntos dados) não tem. Só calcula; nunca apaga.
- `apagar_vista(lado, vista_guid)`: `lado` = `t.lado` de uma transação; apaga o objeto de `vistas` dessa chave e TODOS os `viewports` dela (ADR §6, "vista
  apagada por nós"); só mexe nessa vista; tudo na mesma transação (um `desfazer` volta tudo).
`gravar_par` (mudança mínima): manifesto sai `versao_formato` "0.2.0", SEM `provisorio`; campos desconhecidos do manifesto e entradas fora do lateral do
`Casa.obim` que já está ao lado do destino são repassados; `Casa.obim` com versão fora de 0.1/0.2 (`.somente_leitura`) = recusa gravar. `_conferir_obim` aceita
`titleblocks/*.svg`, `assets/*` e entrada desconhecida, e continua a recusar caminho perigoso.
DECISOES DO LIDER: ao tirar os marcadores o autor atualiza, em commit separado, a regua da S05 (`s05_t07_aux`, `test_s05_t09b` l.344, `test_s05_t07_regua`) para
0.2.0 sem `provisorio` (só a versão; nada afrouxado; o implementador não toca). Esquema CC0 fica para a T13. Casos novos: `..._b_oraculo.py`.
GUARDA: sem ifcopenshell, pula (falha com OBIM_S05_OBRIGATORIO=1). O caso 17 e o 20 não usam o módulo novo."""
import json
import zipfile
from pathlib import Path

import pytest
import s05_t07_aux as X
from s05_conteudo_aux import _limpa, base_ifc, exigir  # noqa: F401  (fixtures)
from s05_t07_aux import LADO
from test_s05_t07_par_oraculo import Proj

G1, G2 = "0$Fq3Zk1D5Pv2wX4yAbC_E", "3cUz$7rQ0aLm9XyN2bP_Hd"  # GlobalId tem `$` (alfabeto 0-9A-Za-z_$), 22 caracteres
IDENT = "A-01.2 / rev B"  # Identification pode ter espaço, ponto e barra
U = {n: f"{i:08x}-0000-4000-8000-00000000000{i}" for i, n in enumerate(("est", "v1", "v2", "p1", "p2", "vp1", "vp2", "vp3", "tb"), 1)}
SVG = '<svg xmlns="http://www.w3.org/2000/svg"><text>Carimbo ação</text></svg>'.encode()
MAN = {"formato": "obim-lateral", "versao_formato": "0.2.0", "LadoId": LADO, "Revisao": 1, "ifc_nome": "Casa.ifc", "ifc_sha256": "0" * 64,
       "ifc_tamanho": 1, "ifc_projeto_globalid": "p", "programa_versao": "0.1.0", "data": "2026-10-30T00:00:00Z", "x_futuro": {"k": [1, 2]}}


def ob():
    import openbim_app.obim_zip as m  # primeira linha de cada caso @AINDA_NAO que usa o módulo: hoje é ela que dá o xfail
    return m


def objetos(**sobre):
    o = {"styles": {U["est"]: {"nome": "padrao", "espessuras": {"corte": 0.5, "vista": 0.25}, "campo_futuro": {"a": [1, 2]}}},
         "vistas": {U["v1"]: {"vista_guid": G1, "estilo": U["est"], "visibilidade": {"IfcFurniture": False}, "extra": [1]},
                    U["v2"]: {"vista_guid": G2, "estilo": U["est"]}},
         "pranchas": {U["p1"]: {"identification": IDENT, "formato": "A1", "carimbo": {"titulo": "Planta térreo"}, "titleblock": U["tb"]}},
         "viewports": {U["vp1"]: {"prancha": IDENT, "vista_guid": G1, "x": 10.0, "y": 20.5, "escala": 100.0},
                       U["vp2"]: {"prancha": IDENT, "vista_guid": G2, "x": 400, "y": 20.5, "escala": 50}},
         "notas": {"nx": {"texto": "nota"}}}
    o.update(sobre)
    return o


def lat(**sobre):
    from openbim_app.lateral import Lateral
    return Lateral(objetos(**sobre))


def canon(l):
    return bytes(l.canonico())


def entradas(caminho):
    with zipfile.ZipFile(caminho) as z:
        return z.namelist()

def test_01_zip_comum_estrutura_e_manifesto(tmp_path):
    m, p = ob(), tmp_path / "Casa.obim"
    m.escrever(p, lat(), MAN, {f"titleblocks/{U['tb']}.svg": SVG})
    with zipfile.ZipFile(p) as z:  # descompactador comum: testzip + extrair
        assert z.testzip() is None
        assert all(i.compress_type == zipfile.ZIP_DEFLATED for i in z.infolist() if i.file_size > 0), "ZIP não está em deflate"
        z.extractall(tmp_path / "x")
    nomes = set(entradas(p))
    for pasta in ("styles", "vistas", "pranchas", "viewports", "titleblocks"):
        assert any(n.startswith(pasta + "/") for n in nomes), f"sem a pasta {pasta}/: {sorted(nomes)}"
    assert (tmp_path / "x" / "titleblocks" / f"{U['tb']}.svg").read_bytes() == SVG
    assert not [n for n in nomes if "$" in n], "GlobalId no NOME do arquivo (a chave vive no campo, o nome é UUID)"
    man = json.loads(zipfile.ZipFile(p).read("manifest.json"))
    assert man["versao_formato"] == "0.2.0" and "provisorio" not in man and man["formato"] == "obim-lateral"
    assert man["x_futuro"] == {"k": [1, 2]}

def test_02_gravar_e_ler_identico(tmp_path):
    m, p = ob(), tmp_path / "Casa.obim"
    origem = lat()
    m.escrever(p, origem, MAN, {f"titleblocks/{U['tb']}.svg": SVG})
    r = m.ler(p)
    assert canon(r.lateral) == canon(origem) and r.manifesto == MAN
    assert r.extras == {f"titleblocks/{U['tb']}.svg": SVG}
    assert (r.versao_original, r.somente_leitura) == ("0.2.0", False)
    q = tmp_path / "outra.obim"
    m.escrever(q, r.lateral, r.manifesto, r.extras)
    assert canon(m.ler(q).lateral) == canon(origem) and m.ler(q).extras == r.extras, "ler -> escrever -> ler muda algo"

def test_03_chave_com_dolar_e_identification_estranha(tmp_path):
    m, p = ob(), tmp_path / "Casa.obim"
    m.escrever(p, lat(), MAN)
    r = m.ler(p).lateral
    guids = sorted(r.obter("vistas", i)["vista_guid"] for i in r.ids("vistas"))
    assert guids == sorted((G1, G2)) and "$" in G1
    assert r.obter("pranchas", U["p1"])["identification"] == IDENT
    vp = r.obter("viewports", U["vp1"])
    assert (vp["prancha"], vp["vista_guid"]) == (IDENT, G1), "viewport tem de guardar a Identification da prancha e o GlobalId da vista"


def _rep_vista():
    return {"vistas": {**objetos()["vistas"], "outra": {"vista_guid": G1}}}


def _rep_prancha():
    return {"pranchas": {**objetos()["pranchas"], "outra": {"identification": IDENT, "formato": "A3"}}}


def _rep_viewport():
    return {"viewports": {**objetos()["viewports"], "outro": {"prancha": IDENT, "vista_guid": G1, "x": 0, "y": 0, "escala": 100}}}


def _com(col, i, **campos):
    o = objetos()
    o[col] = {**o[col], i: campos}
    return {col: o[col]}


RUINS = [("vista_guid repetido", _rep_vista), ("identification repetida", _rep_prancha), ("par prancha+vista repetido", _rep_viewport),
         ("vista sem vista_guid", lambda: _com("vistas", "x", estilo="a")),
         ("vista_guid vazio", lambda: _com("vistas", "x", vista_guid="")),
         ("vista_guid que não é texto", lambda: _com("vistas", "x", vista_guid=7)),
         ("identification vazia", lambda: _com("pranchas", "x", identification="")),
         ("identification com espaço nas pontas", lambda: _com("pranchas", "x", identification=" A-02")),
         ("identification sem campo", lambda: _com("pranchas", "x", formato="A1")),
         ("viewport sem prancha", lambda: _com("viewports", "x", vista_guid=G1, x=0, y=0, escala=100)),
         ("viewport sem vista_guid", lambda: _com("viewports", "x", prancha="B", x=0, y=0, escala=100)),
         ("viewport com x texto", lambda: _com("viewports", "x", prancha="B", vista_guid=G1, x="1", y=0, escala=100)),
         ("viewport com escala zero", lambda: _com("viewports", "x", prancha="B", vista_guid=G1, x=0, y=0, escala=0)),
         ("viewport com escala negativa", lambda: _com("viewports", "x", prancha="B", vista_guid=G1, x=0, y=0, escala=-5))]

@pytest.mark.parametrize("sobre", [f for _, f in RUINS], ids=[n for n, _ in RUINS])
def test_04_validacao_recusa_e_nao_grava(tmp_path, sobre):
    m, p = ob(), tmp_path / "Casa.obim"
    with pytest.raises(m.ObimInvalido):
        m.escrever(p, lat(**sobre()), MAN)
    assert not p.exists() and not list(tmp_path.iterdir()), f"sobrou arquivo depois da recusa: {list(tmp_path.iterdir())}"

def test_05_desconhecidos_sobrevivem_a_regravar(tmp_path):
    m, p, q = ob(), tmp_path / "a.obim", tmp_path / "b.obim"
    o = objetos(zzz_futuro={"u1": {"qualquer": [1, {"b": None}], "texto": "ç"}})
    from openbim_app.lateral import Lateral
    extras = {"assets/logo.png": b"\x89PNG\r\n\x1a\n\x00\xff", f"titleblocks/{U['tb']}.svg": SVG, "futuro/lixo.bin": b"\x00\x01"}
    m.escrever(p, Lateral(o), MAN, extras)
    r = m.ler(p)
    m.escrever(q, r.lateral, r.manifesto, r.extras)
    r2 = m.ler(q)
    assert r2.manifesto["x_futuro"] == {"k": [1, 2]} and r2.extras == extras
    assert r2.lateral.obter("zzz_futuro", "u1") == o["zzz_futuro"]["u1"]
    assert r2.lateral.obter("vistas", U["v1"])["extra"] == [1], "campo desconhecido dentro de objeto conhecido perdido"
    assert r2.lateral.obter("styles", U["est"])["campo_futuro"] == {"a": [1, 2]}


PERIGOSAS = ["../fora.json", "/abs/x.json", "vistas/../../fora.json", "vistas\\x.json", "styles/../x.json"]

@pytest.mark.parametrize("nome", PERIGOSAS)
def test_06_caminho_perigoso_recusado(tmp_path, nome):
    m, p = ob(), tmp_path / "ruim.obim"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("manifest.json", json.dumps(MAN))
        z.writestr(zipfile.ZipInfo(nome), b"{}")
    with pytest.raises(m.ObimInvalido):
        m.ler(p)
    import openbim_app.gravacao_par as GP
    with pytest.raises(ValueError):
        GP._conferir_obim(p)

def test_07_ler_recusa_sem_manifesto_ou_outro_formato(tmp_path):
    m = ob()
    a, b, c = tmp_path / "a.obim", tmp_path / "b.obim", tmp_path / "c.obim"
    with zipfile.ZipFile(a, "w") as z:
        z.writestr("vistas/x.json", "{}")
    with zipfile.ZipFile(b, "w") as z:
        z.writestr("manifest.json", json.dumps({**MAN, "formato": "outra-coisa"}))
    c.write_bytes(b"isto nao e zip")
    for p in (a, b, c):
        with pytest.raises(m.ObimInvalido):
            m.ler(p)


def _par_0_1_0(tmp_path, base_ifc, notas=None):  # noqa: F811  (arquivo provisório da S05, feito pela régua que reproduz o formato dela)
    d = tmp_path / "antigo" / "Casa.ifc"
    d.parent.mkdir()
    X.escrever_par_falso(d, base_ifc, {"notas": notas or {"n1": {"texto": "da S05", "ifc_guids": ["abc"]}}, "outra": {"o_1": {"v": 1.5}}}, 3, legado=True)
    return d, d.with_suffix(".obim")

def test_08_migra_0_1_0_em_memoria(tmp_path, base_ifc):  # noqa: F811
    exigir()
    m = ob()
    _, o = _par_0_1_0(tmp_path, base_ifc)
    bytes_antes = o.read_bytes()
    r = m.ler(o)
    assert (r.versao_original, r.somente_leitura) == ("0.1.0", False)
    assert r.manifesto["versao_formato"] == "0.2.0" and "provisorio" not in r.manifesto
    assert r.manifesto["Revisao"] == 3 and r.manifesto["LadoId"] == LADO, "migração perdeu campo do manifesto"
    assert r.lateral.obter("notas", "n1") == {"texto": "da S05", "ifc_guids": ["abc"]} and r.lateral.obter("outra", "o_1") == {"v": 1.5}
    assert o.read_bytes() == bytes_antes, "ler mudou o arquivo (migra só em memória; regrava só ao gravar o par)"

@pytest.mark.parametrize("versao", ["0.3.0", "1.0.0", "2.4.1"])
def test_09_versao_maior_abre_so_leitura_e_nada_se_perde(tmp_path, versao):
    m, p = ob(), tmp_path / "f.obim"
    m.escrever(p, lat(), {**MAN, "versao_formato": versao, "novo_campo_v": 1})
    r = m.ler(p)
    assert r.somente_leitura is True and r.versao_original == versao and r.manifesto["novo_campo_v"] == 1
    assert canon(r.lateral) == canon(lat())

def test_10_versao_menor_nova_grava_e_preserva(tmp_path):
    m, p = ob(), tmp_path / "f.obim"
    m.escrever(p, lat(), {**MAN, "versao_formato": "0.2.1", "campo_021": [1]})
    r = m.ler(p)
    assert r.somente_leitura is False and r.manifesto["campo_021"] == [1]

def test_11_orfaos_sao_calculados_e_nunca_apagados(tmp_path):
    m, p = ob(), tmp_path / "f.obim"
    l = lat()
    assert m.orfaos(l, {G1, G2}, {IDENT}) == {"vistas": [], "pranchas": [], "viewports": []}
    sem_g2 = m.orfaos(l, {G1}, {IDENT})  # a vista G2 sumiu do IFC por fora do programa
    assert sem_g2 == {"vistas": [U["v2"]], "pranchas": [], "viewports": [U["vp2"]]}
    assert m.orfaos(l, {G1, G2}, set())["pranchas"] == [U["p1"]] and sorted(m.orfaos(l, {G1, G2}, set())["viewports"]) == sorted((U["vp1"], U["vp2"]))  # ADR §6: prancha inexistente no IFC = viewport órfão
    assert sorted(m.orfaos(l, set(), set())["viewports"]) == sorted((U["vp1"], U["vp2"]))
    assert l.obter("viewports", U["vp2"]) is not None, "orfaos() apagou"
    m.escrever(p, l, MAN)  # gravar com órfãos não os apaga
    assert canon(m.ler(p).lateral) == canon(l)


def _fabrica(proj):
    with proj.s.escrever() as esc, proj.h.transacao(esc) as t:
        for c, objs in objetos().items():
            for i, o in objs.items():
                t.lado.criar(c, i, o)

def test_12_apagar_vista_apaga_so_os_viewports_dela_numa_transacao(proj):
    m = ob()
    _fabrica(proj)
    cheio = canon(proj.lat)
    with proj.s.escrever() as esc, proj.h.transacao(esc) as t:
        m.apagar_vista(t.lado, G1)
    assert proj.lat.obter("vistas", U["v1"]) is None and proj.lat.obter("viewports", U["vp1"]) is None
    assert proj.lat.obter("vistas", U["v2"]) is not None and proj.lat.obter("viewports", U["vp2"]) is not None, "apagou além da vista pedida"
    assert proj.lat.obter("pranchas", U["p1"]) is not None and proj.lat.obter("styles", U["est"]) is not None
    with proj.s.escrever() as esc:
        proj.h.desfazer(esc)  # UM desfazer volta a vista e o viewport
    assert canon(proj.lat) == cheio
    with proj.s.escrever() as esc:
        proj.h.refazer(esc)
    assert proj.lat.obter("viewports", U["vp1"]) is None and proj.lat.obter("vistas", U["v1"]) is None

@pytest.fixture
def proj(tmp_path, base_ifc, monkeypatch):  # noqa: F811
    exigir()
    for v in ("OBIM_S05_FALHA_EM", "OBIM_S05_MORRER_EM"):
        monkeypatch.delenv(v, raising=False)
    p = Proj(tmp_path, base_ifc)
    yield p
    p.h.encerrar()

def test_14_gravar_par_sai_0_2_0_com_estrutura_real(proj):
    m = ob()
    _fabrica(proj)
    proj.gravar()
    o = proj.destino.with_suffix(".obim")
    assert zipfile.ZipFile(o).testzip() is None
    r = m.ler(o)
    assert r.manifesto["versao_formato"] == "0.2.0" and "provisorio" not in r.manifesto and r.versao_original == "0.2.0"
    assert r.manifesto["ifc_nome"] == "Casa.ifc" and r.manifesto["Revisao"] == 1 and r.manifesto["LadoId"] == LADO
    assert canon(r.lateral) == canon(proj.lat)
    assert not [n for n in entradas(o) if "$" in n] and not any(proj.pasta.glob("gravacao*"))

def test_15_gravar_par_repassa_manifesto_e_entradas_desconhecidas(proj):
    m = ob()
    _fabrica(proj)
    o = proj.destino.with_suffix(".obim")
    proj.gravar()
    r = m.ler(o)
    m.escrever(o, r.lateral, {**r.manifesto, "x_futuro": {"k": [9]}, "campo_novo": "z"}, {"assets/logo.png": b"\x89PNG\x00", f"titleblocks/{U['tb']}.svg": SVG})
    proj.tx(2)
    proj.gravar()
    r2 = m.ler(o)
    assert r2.manifesto["x_futuro"] == {"k": [9]} and r2.manifesto["campo_novo"] == "z", "gravar_par montou o manifesto do zero"
    assert r2.manifesto["Revisao"] == 2 and r2.manifesto["ifc_sha256"] == X.sha(proj.destino.read_bytes()), "campos do programa não foram atualizados"
    assert r2.extras == {"assets/logo.png": b"\x89PNG\x00", f"titleblocks/{U['tb']}.svg": SVG}, "entrada desconhecida perdida"
    assert r2.lateral.obter("notas", "n2") is not None

def test_16_gravar_par_migra_0_1_0_e_guarda_o_bak(proj, base_ifc, tmp_path):  # noqa: F811
    m = ob()
    X.escrever_par_falso(proj.destino, base_ifc, {"notas": {"n0": {"texto": "primeira"}}}, 5, legado=True)
    antigo = X.Antigo(proj.destino.read_bytes(), proj.destino.with_suffix(".obim").read_bytes())
    proj.gravar()
    assert proj.destino.with_name("Casa.obim.bak").read_bytes() == antigo.obim and proj.destino.with_name("Casa.ifc.bak").read_bytes() == antigo.ifc
    r = m.ler(proj.destino.with_suffix(".obim"))
    assert r.versao_original == "0.2.0" and r.manifesto["versao_formato"] == "0.2.0" and "provisorio" not in r.manifesto
    assert canon(r.lateral) == canon(proj.lat)
    assert m.ler(proj.destino.with_name("Casa.obim.bak")).versao_original == "0.1.0", "o .bak do provisório tem de continuar legível"


def _estado_intacto(proj, antigo):
    assert X.estado_par(proj.destino, antigo, None, proj.pasta) == ("antigo", []), "o par de antes mudou ou sobrou arquivo"


def _antes(proj, base_ifc, versao="0.1.0", **man):  # noqa: F811
    X.escrever_par_falso(proj.destino, base_ifc, {"notas": {"n0": {"texto": "primeira"}}}, 5, manifesto={"versao_formato": versao, **man}, legado=True)
    return X.Antigo(proj.destino.read_bytes(), proj.destino.with_suffix(".obim").read_bytes())


def test_17_falha_antes_do_diario_deixa_o_par_de_antes(proj, base_ifc, monkeypatch):  # noqa: F811
    import openbim_app.gravacao_atomica as GA
    _fabrica(proj)
    antigo = _antes(proj, base_ifc)
    real = GA._etapa

    def quebra(n, c):
        if n == "conferir" and Path(str(c)).name == "Casa.obim.tmp":
            raise OSError("falha injetada no lateral 0.2.0")
        return real(n, c)
    monkeypatch.setattr(GA, "_etapa", quebra)
    with pytest.raises(Exception) as e:  # FalhaGravacao de GA, em português, citando o arquivo
        proj.gravar()
    assert "Casa.obim" in str(e.value)
    _estado_intacto(proj, antigo)
    assert proj.chamadas == [] and proj.pset() is None, "ao_concluir chamado ou carimbo não voltou"

@pytest.mark.parametrize("sobre", [_rep_vista, _rep_prancha], ids=["vista_guid repetido", "identification repetida"])
def test_18_gravar_par_com_lateral_invalido_nao_toca_no_par(proj, base_ifc, sobre):  # noqa: F811
    from openbim_app.lateral import Lateral
    proj.lat = Lateral(objetos(**sobre()))
    proj.h.encerrar()
    from openbim_app.transacao import Historico
    proj.h = Historico(proj.s, proj.lat, anotar=lambda *a, **k: None)
    antigo = _antes(proj, base_ifc)
    with pytest.raises(ValueError):
        proj.gravar()
    _estado_intacto(proj, antigo)

def test_19_gravar_par_recusa_obim_de_versao_maior(proj, base_ifc):  # noqa: F811
    _fabrica(proj)
    antigo = _antes(proj, base_ifc, versao="0.3.0", campo_novo=1)
    with pytest.raises(Exception) as e:
        proj.gravar()
    assert "Casa.obim" in str(e.value), "a mensagem tem de citar o arquivo (em português)"
    _estado_intacto(proj, antigo)

def test_20_conferir_obim_aceita_svg_e_entrada_desconhecida(tmp_path):
    import openbim_app.gravacao_par as GP
    p = tmp_path / "ok.obim"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("manifest.json", json.dumps({**MAN, "versao_formato": GP.VERSAO_FORMATO}))
        z.writestr("vistas/a.json", "{}")
        z.writestr(f"titleblocks/{U['tb']}.svg", SVG)
        z.writestr("assets/logo.png", b"\x00")
    assert GP.VERSAO_FORMATO == "0.2.0"
    GP._conferir_obim(p)  # não levanta
