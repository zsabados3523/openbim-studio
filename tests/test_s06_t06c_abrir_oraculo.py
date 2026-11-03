# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo do F0-S06-T06c, abrir sem a flag não engole lateral recusado (achado 1 da revisão Opus da T06b). Marcadores AINDA_NAO_T06C já removidos.
CONTRATO (`openbim_app.autosave.abrir_projeto`, `divergencia.py`):
1. Lateral recusado (versão mais nova do formato = só leitura; manifesto sem campo obrigatório) levanta `LateralRecusado` COM ou SEM `divergencia=True`.
   Nada é regravado, criado ou vinculado: a pasta do projeto (IFC, `.obim`, rastro) fica byte a byte igual; vale também numa segunda abertura.
2. A recusa não deixa recurso aberto: nenhum `Diario` novo com arquivo aberto e nenhuma thread nova viva (Historico/Autosave não chegam a nascer, ou são encerrados).
3. `LateralAlheio` fala pt-BR simples: sem siglas técnicas, diz o que fazer, cita o nome do `.obim`.
Não coberto aqui: `.obim` ilegível (lixo) sem a flag segue como no oráculo da T06b (test_14); `classificar` extra na abertura (medir na S10).
GUARDA: sem ifcopenshell, pula (falha com OBIM_S05_OBRIGATORIO=1)."""
import gc
import re
import shutil
import threading
import zipfile
from pathlib import Path

import pytest
import s06_t06_aux as X
from s05_conteudo_aux import _limpa, exigir  # noqa: F401  (fixtures)

RECUSADOS = {
    "versao_nova": {"versao": "0.3.0"},
    "versao_futura": {"versao": "9.0.0"},
    "sem_revisao": {"man": {"Revisao": X.APAGAR}},
    "sem_sha": {"man": {"ifc_sha256": X.APAGAR}},
    "sem_globalid": {"man": {"ifc_projeto_globalid": X.APAGAR}},
    "sem_ifc_nome": {"man": {"ifc_nome": X.APAGAR}},
    "revisao_texto": {"man": {"Revisao": "2"}},
    "sem_ladoid_com_pset": {"man": {"LadoId": X.APAGAR}},
    "revisao_bool": {"man": {"Revisao": True}},
    "revisao_decimal": {"man": {"Revisao": 3.5}},
    "revisao_nula": {"man": {"Revisao": None}},
}


@pytest.fixture(autouse=True)
def _local(tmp_path, monkeypatch):
    exigir()
    monkeypatch.setenv("OBIM_PASTA_LOCAL", str(tmp_path / "local"))


@pytest.fixture
def p(tmp_path):
    return tmp_path / "proj"


AINDA_NAO_T06C = pytest.mark.xfail(strict=True, reason="T06c: ainda não implementado")
FLAGS = [False, True]


def _abrir(ifc, div):
    import openbim_app.autosave as S
    return S.abrir_projeto(ifc, lambda t: True, divergencia=div)


def _fecha(pr):
    for fn in (pr.autosave.parar, pr.diario.fechar, pr.historico.encerrar):
        try:
            fn()
        except Exception:  # noqa: BLE001
            pass


def _diarios_abertos():
    import openbim_app.diario as D
    return {id(o) for o in gc.get_objects() if isinstance(o, D.Diario) and getattr(o, "_f", None) is not None and not o._f.closed}


def _recursos():
    import ifcopenshell
    return (_diarios_abertos(), set(ifcopenshell.file.registry), {t.ident for t in threading.enumerate()})


# 1) recusa sem engolir
@pytest.mark.parametrize("div", FLAGS)
@pytest.mark.parametrize("nome", list(RECUSADOS))
def test_01_lateral_recusado_levanta_e_nao_toca_em_nada(p, nome, div):
    import openbim_app.divergencia as DV
    ifc, ob = X.fazer(p, **RECUSADOS[nome])
    antes = X.foto(p)
    for _ in range(2):  # a recusa é estável: repetir não "cura" nem grava
        try:
            pr = _abrir(ifc, div)
        except DV.LateralIncompativel:
            pr = None
        else:
            _fecha(pr)
        assert pr is None, "abrir devia recusar, não devolver Projeto"
        assert X.foto(p) == antes
    assert not list(p.glob("*.tmp")) and not list(p.glob("*.bak")) and ob.exists()


@pytest.mark.parametrize("div", FLAGS)
def test_02_recusado_nao_vincula_sozinho_o_manifesto_fica_como_estava(p, div):
    import openbim_app.divergencia as DV
    import openbim_app.obim_zip as Z
    ifc, ob = X.fazer(p, versao="0.3.0")
    dados, mt = ob.read_bytes(), ob.stat().st_mtime_ns
    with pytest.raises(DV.LateralRecusado):
        _abrir(ifc, div)
    leitura = Z.ler(ob)
    assert ob.read_bytes() == dados and ob.stat().st_mtime_ns == mt and leitura.somente_leitura and leitura.manifesto["versao_formato"] == "0.3.0"
    assert X.sha(ifc) == leitura.manifesto["ifc_sha256"]  # o IFC também intacto


# 2) sem vazamento
@pytest.mark.parametrize("div", [False, True])
@pytest.mark.parametrize("nome", ["versao_nova", "sem_revisao"])
def test_03_recusa_nao_deixa_diario_historico_nem_thread_abertos(p, nome, div, monkeypatch):
    import openbim_app.diario as D
    import openbim_app.divergencia as DV
    criados = []  # referência forte: pega Diario criado e esquecido, que o gc.get_objects não vê
    for nm in ("abrir", "continuar"):
        monkeypatch.setattr(D.Diario, nm, classmethod(lambda cls, *a, _o=getattr(D.Diario, nm), **k: criados.append(_o(*a, **k)) or criados[-1]))
    ifc, _ = X.fazer(p, **RECUSADOS[nome])
    gc.collect()
    antes = _recursos()
    with pytest.raises(DV.LateralRecusado):
        _abrir(ifc, div)
    gc.collect()
    d, _reg, th = _recursos()
    assert d <= antes[0] and all(x._f.closed for x in criados), "Diario ficou com arquivo aberto"
    assert th <= antes[2], "thread nova ficou viva"


def test_04_regua_do_vazamento_enxerga_um_projeto_aberto(p):
    ifc, _ = X.fazer(p)
    gc.collect()
    antes = _recursos()
    pr = _abrir(ifc, True)
    try:
        d, reg, _ = _recursos()
        assert d - antes[0] and reg - antes[1]
    finally:
        _fecha(pr)
    gc.collect()
    assert _recursos()[0] <= antes[0]


# 3) mensagem do LateralAlheio
JARGAO = re.compile(r"globalid|ladoid|hash|sha-?256|manifest|json|\bzip\b|ifcproject|traceback|exception|none\b|\bpath\b", re.I)


def test_05_mensagem_de_LateralAlheio_em_pt_BR_simples():
    import openbim_app.autosave as S
    for arg in (Path("/x/y/Casa.obim"), Path("Casa.obim")):
        msg = str(S.LateralAlheio(arg))
        assert "Casa.obim" in msg and "/x/y" not in msg
        assert not JARGAO.search(msg), msg
        assert re.search(r"outro projeto|de outro", msg, re.I), msg  # diz o que é
        assert re.search(r"escolh|criar|cancel|guard", msg, re.I), msg  # diz o que fazer
        assert "(" not in msg and msg[0].isupper() and len(msg) > 40


def test_06_mensagem_real_ao_gravar_com_alheio_e_a_mesma_simples(p):
    import openbim_app.autosave as S
    ifc, ob = X.fazer(p, o_gid="9zzzHZ1u8Ek9aBc3DeFgHi")
    pr = _abrir(ifc, False)
    try:
        with pytest.raises(S.LateralAlheio) as e:
            pr.autosave.gravar_normal()
    finally:
        _fecha(pr)
    msg = str(e.value)
    assert "Casa.obim" in msg and not JARGAO.search(msg) and re.search(r"outro projeto", msg, re.I) and re.search(r"escolh|criar|cancel|guard", msg, re.I), msg


# 4) casos novos (rodada 1 do Argon)
def _zip_trocando(ob, troca=None, extra=None):
    """Regrava o ZIP do `.obim` trocando o conteúdo de entradas (ZIP e manifesto continuam válidos)."""
    tmp = ob.with_name("tmp.zip")
    with zipfile.ZipFile(ob) as z, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as o:
        for i in z.infolist():
            o.writestr(i.filename, (troca or {}).get(i.filename, z.read(i.filename)))
        for n, b in (extra or {}).items():
            o.writestr(n, b)
    shutil.move(str(tmp), str(ob))


def _lixo(p):
    ifc, ob = X.fazer(p)
    ob.write_bytes(b"lixo")
    return ifc


def _vista_sem_guid(p):
    ifc, ob = X.fazer(p)
    _zip_trocando(ob, {"vistas/v1.json": b'{"estilo": "padrao"}'})
    return ifc


def _prancha_repetida(p):
    ifc, ob = X.fazer(p)
    with zipfile.ZipFile(ob) as z:
        _zip_trocando(ob, extra={"pranchas/p9.json": z.read("pranchas/p0.json")})
    return ifc


COLECAO_RUIM = {"vista_sem_guid": _vista_sem_guid, "prancha_repetida": _prancha_repetida}


@AINDA_NAO_T06C
def test_07_flag_com_obim_ilegivel_sobe_sem_vazar_diario_nem_thread(p, monkeypatch):
    import openbim_app.diario as D
    import openbim_app.divergencia as DV
    ifc = _lixo(p)
    criados = []
    for nm in ("abrir", "continuar"):
        monkeypatch.setattr(D.Diario, nm, classmethod(lambda cls, *a, _o=getattr(D.Diario, nm), **k: criados.append(_o(*a, **k)) or criados[-1]))
    gc.collect()
    antes = _recursos()
    with pytest.raises(DV.LateralRecusado):
        _abrir(ifc, True)
    gc.collect()
    d, _reg, th = _recursos()  # registro do ifcopenshell não entra: by_type() o enche e só Historico.encerrar o esvazia
    assert d <= antes[0] and all(x._f.closed for x in criados) and th <= antes[2]
    assert ifc.with_suffix(".obim").read_bytes() == b"lixo"


@pytest.mark.parametrize("div", [pytest.param(False, marks=AINDA_NAO_T06C), True])
@pytest.mark.parametrize("nome", list(COLECAO_RUIM))
def test_08_colecao_reservada_invalida_recusa_com_e_sem_a_flag_sem_carregar_nem_gravar(p, nome, div):
    import openbim_app.divergencia as DV
    ifc = COLECAO_RUIM[nome](p)
    ob = ifc.with_suffix(".obim")
    antes = X.foto(p)
    with pytest.raises(DV.LateralRecusado):
        _abrir(ifc, div)
    assert X.foto(p) == antes and ob.exists()


def test_09_LateralAlheio_sem_argumento_tem_mensagem_simples():
    import openbim_app.autosave as S
    msg = str(S.LateralAlheio())
    assert not JARGAO.search(msg) and re.search(r"outro projeto", msg, re.I) and re.search(r"escolh|criar|cancel|guard", msg, re.I), msg
    assert msg[0].isupper() and len(msg) > 40 and "(" not in msg
