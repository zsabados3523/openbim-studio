# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oraculo da F0-S06-T12 (parte 2): destino com link, nomes perigosos e `exportar`. Ajudantes em `_obimpack_ajudantes.py`."""
import hashlib
import json
import os
import stat
import struct
import warnings
import zipfile
import zlib
from pathlib import Path

import pytest
from _obimpack_ajudantes import (  # noqa: F401
    IFC,
    OBIM,
    _m,
    _par,
    _sha,
    _manifesto,
    _zip,
    _vazio,
    _recusa,
    _ls,
    _espiar_leitura,
    _zip_stored,
    _remendar,
    _precisa_symlink,
)


# 4. abrir: tipo da entrada pelo external_attr (qualquer create_system) e destino link quebrado
def _zip_attr(caminho, create_system, modo):
    info = zipfile.ZipInfo("Casa.ifc")
    info.create_system = create_system
    info.external_attr = modo << 16
    with zipfile.ZipFile(caminho, "w") as z:
        z.writestr(info, IFC)
        z.writestr("Casa.obim", OBIM)
        z.writestr("manifesto.json", json.dumps(_manifesto()))
    return caminho


@pytest.mark.parametrize("cs", [0, 3, 19])
def test_entrada_arquivo_comum_com_qualquer_create_system_passa(tmp_path, cs):
    m = _m()
    ifc, _ = m.abrir(_zip_attr(tmp_path / "p.obimpack", cs, stat.S_IFREG | 0o644), tmp_path / "dest")
    assert ifc.read_bytes() == IFC


def _casos_especiais():
    for cs in (0, 3, 19):
        for tipo in (stat.S_IFLNK, stat.S_IFIFO, stat.S_IFCHR, stat.S_IFBLK, stat.S_IFSOCK, stat.S_IFDIR):
            ja_passa = cs == 3 and tipo == stat.S_IFLNK  # unico caso que o codigo atual ja recusa
            yield pytest.param(cs, tipo, id=f"cs{cs}-{oct(tipo)}")


@pytest.mark.parametrize("cs,tipo", list(_casos_especiais()))
def test_entrada_especial_recusa_em_qualquer_create_system(tmp_path, cs, tipo):
    p = _zip_attr(tmp_path / "p.obimpack", cs, tipo | 0o777)
    _recusa(tmp_path, p)


@pytest.mark.parametrize("nome", ["Casa.ifc", "Casa.obim"])
def test_destino_symlink_quebrado_conta_como_existente(tmp_path, nome):
    _precisa_symlink(tmp_path)
    m = _m()
    dest = tmp_path / "dest"
    dest.mkdir()
    os.symlink(tmp_path / "nada", dest / nome)
    with pytest.raises(m.ArquivoJaExiste):
        m.abrir(_zip(tmp_path / "p.obimpack"), dest)
    assert os.path.islink(dest / nome) and os.readlink(dest / nome) == str(tmp_path / "nada")
    assert _ls(dest) == [nome]


def test_sobrescrever_nunca_escreve_atraves_de_symlink_do_destino(tmp_path):
    _precisa_symlink(tmp_path)
    m = _m()
    fora = tmp_path / "fora.txt"
    fora.write_bytes(b"INTACTO")
    dest = tmp_path / "dest"
    dest.mkdir()
    os.symlink(fora, dest / "Casa.ifc")
    ifc, _ = m.abrir(_zip(tmp_path / "p.obimpack"), dest, sobrescrever=True)
    assert fora.read_bytes() == b"INTACTO" and not os.path.islink(ifc) and ifc.read_bytes() == IFC


def test_exportar_destino_symlink_quebrado_conta_como_existente(tmp_path):
    _precisa_symlink(tmp_path)
    m = _m()
    par = _par(tmp_path)
    alvo = tmp_path / "origem" / "Casa.obimpack"
    os.symlink(tmp_path / "nada", alvo)
    with pytest.raises(m.ArquivoJaExiste):
        m.exportar(par)
    assert os.path.islink(alvo) and not (tmp_path / "nada").exists()


# 5. nomes perigosos (Windows)
PERIGOSOS = ["Casa.ifc:$DATA", "Casa.ifc::$DATA", "Casa.ifc:", "Casa.ifc.", "a\x00b",
             "CON", "con", "NUL", "COM1", "LPT1", "COM9", "LPT9", "AUX", "PRN", "CON.txt", "nul.ifc"]


@pytest.mark.parametrize("nome", PERIGOSOS)
def test_proibido_recusa_nomes_perigosos(nome):
    assert _m()._proibido(nome) is True


@pytest.mark.parametrize("nome", ["", " x", "x ", ".", "..", "a/b", "x/", "/x", "a\\b", "\\x", "C:", "C:x", "c:/x", None, 3])
def test_proibido_recusa_nomes_basicos(nome):
    assert _m()._proibido(nome) is True


def test_manifesto_tamanho_bool_nao_vale_como_inteiro(tmp_path):
    ifc = b"x"  # len 1 == True: so a checagem de tipo denuncia
    man = _manifesto(ifc=ifc)
    man["arquivos"][0]["tamanho"] = True
    _recusa(tmp_path, _zip(tmp_path / "p.obimpack", {"Casa.ifc": ifc, "Casa.obim": OBIM}, man))


@pytest.mark.parametrize("nome", ["Casa.ifc", "Casa.obim", "manifesto.json", "CONSOLE.ifc", "Comarca.ifc", "COM10.ifc"])
def test_proibido_aceita_nomes_normais(nome):
    assert _m()._proibido(nome) is False


@pytest.mark.parametrize("nome", [n for n in PERIGOSOS if "\x00" not in n])
def test_entrada_extra_com_nome_perigoso_recusa(tmp_path, nome):
    _recusa(tmp_path, _zip(tmp_path / "p.obimpack", extra=[(nome, b"x")]))


@pytest.mark.parametrize("nome", ["Casa.ifc:$DATA", "Casa.ifc.", "CON", "Casa.obim."])
def test_manifesto_citando_nome_perigoso_no_lugar_do_certo_recusa(tmp_path, nome):
    man = _manifesto()
    man["arquivos"][0]["nome"] = nome
    _recusa(tmp_path, _zip(tmp_path / "p.obimpack", {nome: IFC, "Casa.obim": OBIM}, man))


@pytest.mark.parametrize("stem", ["CON", "nul", "COM1", "LPT1", "Casa.", "Casa:x"])
def test_exportar_recusa_nome_base_perigoso(tmp_path, stem):
    m = _m()
    par = _par(tmp_path, nome=stem)
    with pytest.raises(m.ObimpackInvalido):
        m.exportar(par)
    assert _ls(tmp_path / "origem") == sorted([f"{stem}.ifc", f"{stem}.obim"])


# 6. exportar: par invalido, perguntar, limites, manifesto, limpeza
def test_exportar_par_invalido_recusa(tmp_path):
    m = _m()
    ifc, obim = _par(tmp_path)
    outra = tmp_path / "outra"
    outra.mkdir()
    (outra / "Casa.obim").write_bytes(OBIM)
    (ifc.parent / "Outra.obim").write_bytes(OBIM)
    (ifc.parent / "Casa.txt").write_bytes(b"t")
    casos = [(ifc, outra / "Casa.obim"),            # pastas diferentes
             (ifc, ifc.parent / "Outra.obim"),      # stems diferentes
             (obim, ifc),                           # sufixos trocados
             (ifc, ifc.parent / "Casa.txt"),        # sufixo errado
             (ifc, ifc.parent / "nao_existe.obim"),  # inexistente
             (ifc.parent / "nao_existe.ifc", obim),
             (ifc, ifc.parent),                     # pasta no lugar do arquivo
             (ifc,), "Casa.ifc", None, (ifc, obim, obim)]
    for par in casos:
        with pytest.raises(m.ObimpackInvalido):
            m.exportar(par, tmp_path / "saida.obimpack")
        assert not (tmp_path / "saida.obimpack").exists()
    assert _ls(tmp_path) == ["origem", "outra"]


def test_exportar_perguntar_decide(tmp_path):
    m = _m()
    par = _par(tmp_path)
    alvo = tmp_path / "origem" / "Casa.obimpack"
    alvo.write_bytes(b"antigo")
    vistos = []

    def nao(c):
        vistos.append(Path(c))
        return False
    with pytest.raises(m.ArquivoJaExiste):
        m.exportar(par, perguntar=nao)
    assert vistos == [alvo] and alvo.read_bytes() == b"antigo"
    m.exportar(par, perguntar=lambda c: True)
    assert zipfile.is_zipfile(alvo)


def test_exportar_sem_arquivo_existente_nao_pergunta(tmp_path):
    m = _m()
    vistos = []
    m.exportar(_par(tmp_path), perguntar=lambda c: vistos.append(c) or False)
    assert vistos == []


def test_borda_exata_do_limite_de_bytes(tmp_path, monkeypatch):
    m = _m()
    ifc, obim = b"a" * 300, b"b" * 300
    ent = {"Casa.ifc": ifc, "Casa.obim": obim}
    p = _zip(tmp_path / "p.obimpack", ent, _manifesto(ifc=ifc, obim=obim))
    monkeypatch.setattr(m, "LIMITE_BYTES", 600)
    novo_ifc, novo_obim = m.abrir(p, tmp_path / "ok")
    assert novo_ifc.read_bytes() == ifc and novo_obim.read_bytes() == obim
    monkeypatch.setattr(m, "LIMITE_BYTES", 599)
    _recusa(tmp_path, p)


def _man_com(**campos_do_primeiro):
    man = _manifesto()
    man["arquivos"][0].update(campos_do_primeiro)
    return man


def _man_dup():
    man = _manifesto()
    man["arquivos"][1] = dict(man["arquivos"][0])
    return man


MANIFESTOS_RUINS = {
    "duplicado": _man_dup(),
    "tamanho_bool": _man_com(tamanho=True),
    "tamanho_negativo": _man_com(tamanho=-1),
    "tamanho_float": _man_com(tamanho=float(len(IFC))),
    "tamanho_texto": _man_com(tamanho=str(len(IFC))),
    "tamanho_nulo": _man_com(tamanho=None),
    "sha_curto": _man_com(sha256="abc"),
    "sha_nao_hex": _man_com(sha256="g" * 64),
    "sha_longo": _man_com(sha256="a" * 65),
    "sha_numero": _man_com(sha256=12345),
    "sha_ausente": {"formato": "obimpack", "versao_pacote": "1", "arquivos": [
        {"nome": "Casa.ifc", "tamanho": len(IFC)}, {"nome": "Casa.obim", "tamanho": len(OBIM), "sha256": _sha(OBIM)}]},
    "item_nao_dict": {"formato": "obimpack", "versao_pacote": "1", "arquivos": ["Casa.ifc", "Casa.obim"]},
    "tres_arquivos": dict(_manifesto(), arquivos=_manifesto()["arquivos"] + [{"nome": "x", "tamanho": 1, "sha256": "0" * 64}]),
    "arquivos_nao_lista": dict(_manifesto(), arquivos={"Casa.ifc": 1}),
}


@pytest.mark.parametrize("chave", sorted(MANIFESTOS_RUINS))
def test_manifesto_malformado_recusa(tmp_path, chave):
    _recusa(tmp_path, _zip(tmp_path / "p.obimpack", manifesto=MANIFESTOS_RUINS[chave]))


@pytest.mark.parametrize("onde", ["os.replace", "os.fsync", "zipfile.ZipFile.writestr"])
@pytest.mark.parametrize("existia", [False, True])
def test_exportar_falha_no_meio_limpa_temporario_e_preserva_destino(tmp_path, monkeypatch, onde, existia):
    m = _m()
    par = _par(tmp_path)
    pasta = tmp_path / "origem"
    alvo = pasta / "Casa.obimpack"
    if existia:
        alvo.write_bytes(b"antigo")
    antes = _ls(pasta)
    modulo, _, attr = onde.rpartition(".")
    alvo_obj = zipfile.ZipFile if onde.endswith("writestr") else os
    chamadas = []
    real = getattr(alvo_obj, attr)

    def falha(*a, **k):
        chamadas.append(1)
        if onde.endswith("writestr") and len(chamadas) == 1:
            return real(*a, **k)  # falha so na 2a entrada: meio da escrita
        raise OSError("falhou no meio")
    monkeypatch.setattr(alvo_obj, attr, falha)
    with pytest.raises(OSError):
        m.exportar(par, sobrescrever=True)
    monkeypatch.setattr(alvo_obj, attr, real)
    assert _ls(pasta) == antes, "sem .tmp sobrando"
    if existia:
        assert alvo.read_bytes() == b"antigo"
