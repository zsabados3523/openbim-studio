# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo do F0-S06-T06, os 6 casos de divergência ao abrir. Fontes: ADR-003 §6 (textos e opções fixados) e §11 (T06 a a e), v2/02 §6.4 e Revisão 4,
cartão T06. Só o autor do oráculo tira os `@AINDA_NAO` (xfail estrito). Auxiliares: `s06_t06_aux.py`. Mutantes para o revisor: `s06_t06_mutantes.md`.
CONTRATO (API PROPOSTA NESTE TESTE; o ADR fixa os textos, não os nomes). `openbim_app/divergencia.py`:
- `classificar(caminho, obim=None) -> Resultado`. `caminho` = `.ifc` ou `.obim`. `obim` = lateral escolhido pelo usuário ("localizar arquivo"); sem ele, o lateral é
  `<mesmo nome>.obim` ao lado do IFC. Só LÊ: nunca cria, apaga ou regrava arquivo (nem do usuário nem na pasta do programa).
- `Resultado` (dataclass congelada, == por valor): `caso` ("D0".."D6"), `aviso` (texto exato ou None), `opcoes` (tupla de textos exatos, na ordem do ADR),
  `referencias_quebradas` (int N), `ambiguas` (tupla ordenada de `Identification` repetidas no IFC), `vistas_preservadas` (int: IfcAnnotation DRAWING do IFC
  que seguem abertas), `estilo_padrao` (bool: abre com estilo e posição padrão), `vinculado` (bool: o lateral foi vinculado), `via_obim` (bool: a entrada foi
  um `.obim`), `versao_lateral` (texto ou None), `ifc` e `obim` (Path dados/achados ou None).
- `class LateralRecusado(ValueError)`: lateral ilegível (ZIP inválido, manifesto ilegível ou sem `formato`, caminho perigoso) ou de versão que o programa só
  abre para leitura (0.3+, 1.x). A mensagem cita o nome do arquivo. Nada em disco muda. Lateral 0.1.0 (legado da S05) NÃO é recusado: migra em memória.
- `abrir_projeto(ifc, perguntar, divergencia=False)`: com True, `Projeto.divergencia == classificar(ifc)` e o `aviso` (se houver) entra em `Projeto.avisos`.
  Sem o parâmetro nada muda (`Projeto.divergencia is None`).
REGRAS DE DECISÃO (decisão do autor do oráculo onde o ADR não fixa): (1) IFC sem pset `OBIM_Projeto` e sem `.obim` = "D0", sem aviso, vistas abertas.
(2) Com `.obim`: projeto diferente = `ifc_projeto_globalid` OU `LadoId` do manifesto diferente do IFC -> D5 (vem antes de tudo). (3) `Revisao` do lateral >
`Revisao` do pset -> D3 (vem antes do hash: IFC antigo restaurado também tem hash diferente). (4) hash igual (`ifc_sha256` x sha256 real do arquivo) -> D1;
senão D2. (5) N de D2 = viewports + objetos de `vistas` do lateral cujo `vista_guid` não está no IFC + documentos SHEET de `Identification` repetida (um por
documento). (6) D6: a entrada é `.obim`; acha o IFC só pelo nome base de `ifc_nome` na mesma pasta (`..` ou `/` em `ifc_nome` = não achou). Achou e o par casa
= caso "D6", sem aviso, `via_obim` True; achou e diverge = o caso da divergência (D2, D3, D5) com `via_obim` True. Não achou = "D6" com o aviso e a opção abaixo.
(7) `Revisao` é número inteiro nos dois lados. (8) D4 só quando há pset e não há `.obim`; `obim=` dado e casando vale como D1/D2/D3/D5 normal.
GUARDA: sem ifcopenshell, pula (falha com OBIM_S05_OBRIGATORIO=1). Os casos `fixture_*` e `abrir_sem_parametro` não usam o módulo novo."""
import pytest
import s06_t06_aux as X
from s05_conteudo_aux import _limpa, exigir  # noqa: F401  (fixtures)

AINDA_NAO = pytest.mark.xfail(strict=True, reason="F0-S06-T06: openbim_app.divergencia ainda não existe")
D2 = "O modelo foi alterado em outro programa depois da última gravação. A documentação foi verificada: {} referências quebradas."
D2_OP = ("abrir painel de referências", "continuar")
D3, D3_OP = "A documentação é mais nova que o modelo.", ("abrir assim", "procurar outro IFC")
D4 = "Documentação não encontrada. As vistas e pranchas do modelo foram abertas com estilo e posição padrão."
D4_OP = ("localizar arquivo", "abrir só o modelo")
D5, D5_OP = "Esta documentação é de outro projeto e não foi vinculada.", ("escolher outro arquivo", "abrir só o modelo")
D6, D6_OP = "O modelo de {} não foi encontrado.", ("localizar o IFC",)


@pytest.fixture(autouse=True)
def _local(tmp_path, monkeypatch):
    exigir()
    monkeypatch.setenv("OBIM_PASTA_LOCAL", str(tmp_path / "local"))  # diário e autosave do programa fora da pasta do usuário


@pytest.fixture
def p(tmp_path):
    return tmp_path / "proj"


def dv():
    import openbim_app.divergencia as m  # primeira linha de cada caso @AINDA_NAO: hoje é ela que dá o xfail
    return m


def _r(res, caso, aviso=None, opcoes=(), n=0, vistas=2, padrao=False, vinc=True):
    assert (res.caso, res.aviso, tuple(res.opcoes)) == (caso, aviso, opcoes)
    assert (res.referencias_quebradas, res.vistas_preservadas, res.estilo_padrao, res.vinculado) == (n, vistas, padrao, vinc)


def fixture_par_valido(p):  # a régua do auxiliar: o par que os casos usam é um par real
    import openbim_app.obim_zip as Z
    ifc, ob = X.fazer(p)
    assert X.contar_vistas(ifc) == 2 and Z.ler(ob).manifesto["ifc_sha256"] == X.sha(ifc)
    assert (Z.ler(ob).versao_original, Z.ler(ob).somente_leitura) == ("0.2.0", False)
    X.mudar_um_byte(ifc)
    assert Z.ler(ob).manifesto["ifc_sha256"] != X.sha(ifc) and X.contar_vistas(ifc) == 2


test_fixture_par_valido = fixture_par_valido


def test_abrir_sem_parametro_nao_muda(p):
    import openbim_app.autosave as S
    ifc, _ = X.fazer(p)
    pr = S.abrir_projeto(ifc, lambda t: True)
    assert pr.avisos == [] and getattr(pr, "divergencia", None) is None


@AINDA_NAO
def test_d1_casando_nada_a_avisar(p):
    ifc, ob = X.fazer(p)
    r = dv().classificar(ifc)
    _r(r, "D1")
    assert (r.ifc, r.obim, r.via_obim, r.versao_lateral, r.ambiguas) == (ifc, ob, False, "0.2.0", ())


@AINDA_NAO
def test_d1_lateral_legado_0_1_0_migra_sem_recusar(p):
    ifc, _ = X.fazer(p, versao="0.1.0")
    r = dv().classificar(ifc)
    _r(r, "D1")
    assert r.versao_lateral == "0.1.0"


@AINDA_NAO
def test_d2_ifc_alterado_fora_conta_referencias_quebradas(p):
    ifc, ob = X.fazer(p)  # o .obim cita as vistas 1 e 2
    ifc2, _ = X.fazer(p / "novo", vistas=("1", "3"), obim=False)  # outro programa tirou a vista 2 e pôs a 3 (mesmo projeto, mesmo LadoId)
    ifc.write_bytes(ifc2.read_bytes())
    r = dv().classificar(ifc)
    _r(r, "D2", D2.format(2), D2_OP, n=2)  # 1 viewport + 1 objeto de `vistas` citam a vista 2
    assert r.vistas_preservadas == 2 and r.obim == ob


@AINDA_NAO
def test_d2_um_unico_byte_diferente_basta(p):
    ifc, _ = X.fazer(p)
    X.mudar_um_byte(ifc)
    _r(dv().classificar(ifc), "D2", D2.format(0), D2_OP, n=0)


@AINDA_NAO
def test_d2_identification_repetida_marca_ambigua_e_entra_na_contagem(p):
    ifc, _ = X.fazer(p, pranchas=("A-01",))
    ifc2, _ = X.fazer(p / "novo", pranchas=("A-01", "A-01", "B-02"), obim=False)
    ifc.write_bytes(ifc2.read_bytes())
    r = dv().classificar(ifc)
    _r(r, "D2", D2.format(2), D2_OP, n=2)
    assert r.ambiguas == ("A-01",)


@AINDA_NAO
def test_d3_lateral_mais_novo_vem_antes_do_hash(p):
    ifc, _ = X.fazer(p, rev=2, o_rev=3)
    X.mudar_um_byte(ifc)  # IFC antigo restaurado: hash também difere, mas D3 manda
    _r(dv().classificar(ifc), "D3", D3, D3_OP)


@AINDA_NAO
def test_d3_borda_revisao_igual_nao_e_mais_nova(p):
    ifc, _ = X.fazer(p, rev=3, o_rev=3)
    X.mudar_um_byte(ifc)
    _r(dv().classificar(ifc), "D2", D2.format(0), D2_OP)


@AINDA_NAO
def test_d4_lateral_ausente_mantem_as_vistas_do_ifc_com_estilo_padrao(p):
    ifc, _ = X.fazer(p, obim=False)
    r = dv().classificar(ifc)
    _r(r, "D4", D4, D4_OP, padrao=True, vinc=False)
    assert r.vistas_preservadas == X.contar_vistas(ifc) == 2 and r.obim is None


@AINDA_NAO
def test_d4_localizar_arquivo_vincula_o_lateral_escolhido(p, tmp_path):
    ifc, ob = X.fazer(p)
    guardado = tmp_path / "outro" / "achei.obim"
    guardado.parent.mkdir()
    ob.rename(guardado)
    assert dv().classificar(ifc).caso == "D4"
    r = dv().classificar(ifc, obim=guardado)
    _r(r, "D1")
    assert r.obim == guardado


@AINDA_NAO
@pytest.mark.parametrize("troca", [{"o_gid": "9zzzzzzzzzzzzzzzzzzzzz"}, {"o_lado": "00000000-0000-4000-8000-000000000001"}], ids=["projeto", "LadoId"])
def test_d5_lateral_de_outro_projeto_nao_vincula_sozinho(p, troca):
    ifc, _ = X.fazer(p, **troca)
    r = dv().classificar(ifc)
    _r(r, "D5", D5, D5_OP, padrao=True, vinc=False)
    assert r.referencias_quebradas == 0


@AINDA_NAO
def test_d5_vem_antes_de_d3(p):
    ifc, _ = X.fazer(p, rev=1, o_rev=9, o_gid="9zzzzzzzzzzzzzzzzzzzzz")
    assert dv().classificar(ifc).caso == "D5"


@AINDA_NAO
def test_d6_obim_direto_acha_o_ifc_ao_lado_por_ifc_nome(p):
    ifc, ob = X.fazer(p)
    r = dv().classificar(ob)
    _r(r, "D6")
    assert (r.ifc, r.obim, r.via_obim) == (ifc, ob, True)


@AINDA_NAO
def test_d6_achou_o_ifc_mas_o_par_diverge_mostra_a_divergencia(p):
    ifc, ob = X.fazer(p)
    X.mudar_um_byte(ifc)
    r = dv().classificar(ob)
    _r(r, "D2", D2.format(0), D2_OP)
    assert r.via_obim and r.ifc == ifc


@AINDA_NAO
def test_d6_nao_achou_pede_para_localizar(p):
    ifc, ob = X.fazer(p)
    ifc.unlink()
    r = dv().classificar(ob)
    _r(r, "D6", D6.format("Casa.ifc"), D6_OP, vistas=0, vinc=False)
    assert r.ifc is None and r.via_obim


@AINDA_NAO
@pytest.mark.parametrize("nome", ["../Casa.ifc", "sub/Casa.ifc", "/etc/Casa.ifc"])
def test_d6_ifc_nome_com_caminho_so_vale_ao_lado(p, nome):
    import json
    import zipfile
    ifc, ob = X.fazer(p / "x")
    (p / "Casa.ifc").write_bytes(ifc.read_bytes())  # existe fora da pasta do .obim: não pode ser achado por `..`
    with zipfile.ZipFile(ob) as z:
        dados = {n: z.read(n) for n in z.namelist()}
    man = json.loads(dados["manifest.json"])
    man["ifc_nome"] = nome
    dados["manifest.json"] = json.dumps(man).encode()
    with zipfile.ZipFile(ob, "w") as z:
        for n, b in dados.items():
            z.writestr(n, b)
    (ob.parent / "sub").mkdir()
    (ob.parent / "sub" / "Casa.ifc").write_bytes(ifc.read_bytes())
    ifc.rename(ifc.with_name("Outra.ifc"))
    r = dv().classificar(ob)
    assert r.caso == "D6" and r.aviso and r.ifc is None


@AINDA_NAO
def test_ifc_de_outro_programa_sem_pset_e_sem_obim_nao_avisa(p):
    ifc, _ = X.fazer(p, pset=False, obim=False)
    r = dv().classificar(ifc)
    _r(r, "D0", vinc=False)
    assert r.vistas_preservadas == 2


RUINS = {"zip_invalido": lambda ob: ob.write_bytes(b"isto nao e um zip"),
         "manifesto_ilegivel": lambda ob: _regravar(ob, b"{nao json"),
         "sem_formato": lambda ob: _regravar(ob, b'{"versao_formato": "0.2.0"}'),
         "versao_futura_1_0_0": lambda ob: _versao(ob, "1.0.0"), "versao_futura_0_3_0": lambda ob: _versao(ob, "0.3.0")}


def _regravar(ob, manifesto):
    import zipfile
    with zipfile.ZipFile(ob, "w") as z:
        z.writestr("manifest.json", manifesto)


def _versao(ob, v):
    X.fazer(ob.parent, obim=True, versao=v)


@AINDA_NAO
@pytest.mark.parametrize("como", list(RUINS))
@pytest.mark.parametrize("entrada", ["ifc", "obim"])
def test_lateral_corrompido_ou_futuro_e_recusado_sem_tocar_no_disco(p, como, entrada):
    ifc, ob = X.fazer(p)
    RUINS[como](ob)
    antes = X.foto(p)
    with pytest.raises(dv().LateralRecusado, match="Casa.obim"):
        dv().classificar(ifc if entrada == "ifc" else ob)
    assert X.foto(p) == antes


CASOS = {"D1": {}, "D2": {"muda": True}, "D3": {"o_rev": 5}, "D4": {"obim": False}, "D5": {"o_gid": "9zzzzzzzzzzzzzzzzzzzzz"}}


@AINDA_NAO
@pytest.mark.parametrize("caso", list(CASOS))
def test_nenhum_caso_apaga_cria_ou_sobrescreve_arquivo_do_usuario(p, caso):
    import openbim_app.autosave as S
    args = dict(CASOS[caso])
    muda = args.pop("muda", False)
    ifc, ob = X.fazer(p, **args)
    if muda:
        X.mudar_um_byte(ifc)
    antes = X.foto(p)
    r1 = dv().classificar(ifc)
    assert X.foto(p) == antes, "classificar mexeu em arquivo do usuário"
    pr = S.abrir_projeto(ifc, lambda t: True, divergencia=True)
    assert X.foto(p) == antes, "abrir_projeto mexeu em arquivo do usuário"
    assert pr.divergencia == r1 == dv().classificar(ifc), "reabrir com a mesma entrada tem de dar o mesmo resultado"
    assert r1.caso == caso and ((r1.aviso in pr.avisos) if r1.aviso else True)


@AINDA_NAO
def test_abrir_projeto_com_d1_nao_acrescenta_aviso_e_sem_parametro_fica_none(p):
    import openbim_app.autosave as S
    ifc, _ = X.fazer(p)
    dv()
    com = S.abrir_projeto(ifc, lambda t: True, divergencia=True)
    assert com.divergencia.caso == "D1" and com.avisos == []
    sem = S.abrir_projeto(ifc, lambda t: True)
    assert sem.divergencia is None and sem.avisos == []
