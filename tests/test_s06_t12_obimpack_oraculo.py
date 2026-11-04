# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oraculo da F0-S06-T12: pacote `.obimpack` (modulo `app/openbim_app/obimpack.py`, ainda nao existe).

API exata esperada:
  exportar(par, destino=None, *, sobrescrever=False, perguntar=None) -> Path
      par = (caminho_ifc, caminho_obim), mesma pasta e mesmo nome-base (Casa.ifc, Casa.obim).
      Gera ZIP com Casa.ifc, Casa.obim e "manifesto.json"; destino padrao = pasta do par, Casa.obimpack.
  abrir(pacote, destino, *, sobrescrever=False, perguntar=None) -> (Path ifc, Path obim)
      Valida TUDO antes de gravar; extrai em `destino` (criado se faltar) e devolve os caminhos extraidos.
  ObimpackInvalido(ValueError): pacote ruim, mensagem pt-BR clara. Nada e extraido.
  ArquivoJaExiste(FileExistsError): destino ja tem arquivo; padrao recusa sem tocar em nada.
      sobrescrever=True permite; perguntar(caminho)->bool e consultado por arquivo existente (False recusa tudo).
  Constantes LIMITE_ENTRADAS (int) e LIMITE_BYTES (int, soma dos tamanhos declarados): acima => ObimpackInvalido.
Manifesto (JSON em "manifesto.json"): {"formato": "obimpack", "versao_pacote": "<texto>",
  "arquivos": [{"nome": str, "tamanho": int, "sha256": hex}, ...]} com exatamente o .ifc e o .obim.
Pacote valido: exatamente 3 entradas (Casa.ifc, Casa.obim, manifesto.json). Entrada fora do manifesto => recusa."""
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


def test_exportar_gera_zip_com_tres_entradas_e_manifesto_certo(tmp_path):
    m = _m()
    pacote = m.exportar(_par(tmp_path))
    assert pacote.name == "Casa.obimpack" and pacote.parent == tmp_path / "origem"
    with zipfile.ZipFile(pacote) as z:
        assert sorted(z.namelist()) == ["Casa.ifc", "Casa.obim", "manifesto.json"]
        man = json.loads(z.read("manifesto.json"))
        assert z.read("Casa.ifc") == IFC and z.read("Casa.obim") == OBIM
    assert man["formato"] == "obimpack" and isinstance(man["versao_pacote"], str) and man["versao_pacote"]
    por_nome = {a["nome"]: a for a in man["arquivos"]}
    assert set(por_nome) == {"Casa.ifc", "Casa.obim"}
    assert por_nome["Casa.ifc"] == {"nome": "Casa.ifc", "tamanho": len(IFC), "sha256": _sha(IFC)}
    assert por_nome["Casa.obim"] == {"nome": "Casa.obim", "tamanho": len(OBIM), "sha256": _sha(OBIM)}
def test_ida_e_volta_devolve_par_igual_por_bytes(tmp_path):
    m = _m()
    ifc, obim = _par(tmp_path)
    pacote = m.exportar((ifc, obim), tmp_path / "saida.obimpack")
    novo_ifc, novo_obim = m.abrir(pacote, tmp_path / "novo")
    assert (novo_ifc.name, novo_obim.name) == ("Casa.ifc", "Casa.obim")
    assert novo_ifc.parent == novo_obim.parent == tmp_path / "novo"
    assert novo_ifc.read_bytes() == ifc.read_bytes() and novo_obim.read_bytes() == obim.read_bytes()
    assert sorted(p.name for p in (tmp_path / "novo").iterdir()) == ["Casa.ifc", "Casa.obim"]
def test_exportar_nao_altera_originais(tmp_path):
    m = _m()
    ifc, obim = _par(tmp_path)
    m.exportar((ifc, obim))
    assert ifc.read_bytes() == IFC and obim.read_bytes() == OBIM
    assert sorted(p.name for p in ifc.parent.iterdir()) == ["Casa.ifc", "Casa.obim", "Casa.obimpack"]
def test_ifc_sozinho_continua_valido_sem_o_pacote(tmp_path):
    m = _m()
    ifc, obim = _par(tmp_path)
    pacote = m.exportar((ifc, obim))
    pacote.unlink()
    obim.unlink()
    assert ifc.read_bytes() == IFC  # o IFC nao depende de pacote nem de .obim
def test_exportar_recusa_sobrescrever_pacote_existente(tmp_path):
    m = _m()
    par = _par(tmp_path)
    alvo = tmp_path / "origem" / "Casa.obimpack"
    alvo.write_bytes(b"antigo")
    with pytest.raises(m.ArquivoJaExiste):
        m.exportar(par)
    assert alvo.read_bytes() == b"antigo"
    m.exportar(par, sobrescrever=True)
    assert zipfile.is_zipfile(alvo)
def test_abrir_recusa_sobrescrever_e_nao_toca_em_nada(tmp_path):
    m = _m()
    pacote = _zip(tmp_path / "p.obimpack")
    dest = tmp_path / "dest"
    dest.mkdir()
    (dest / "Casa.obim").write_bytes(b"MEU")
    with pytest.raises(m.ArquivoJaExiste):
        m.abrir(pacote, dest)
    assert (dest / "Casa.obim").read_bytes() == b"MEU"
    assert not (dest / "Casa.ifc").exists(), "recusa deve ser tudo ou nada"
    assert sorted(p.name for p in dest.iterdir()) == ["Casa.obim"]
def test_abrir_com_sobrescrever_true_troca_os_dois(tmp_path):
    m = _m()
    pacote = _zip(tmp_path / "p.obimpack")
    dest = tmp_path / "dest"
    dest.mkdir()
    (dest / "Casa.ifc").write_bytes(b"A")
    (dest / "Casa.obim").write_bytes(b"B")
    ifc, obim = m.abrir(pacote, dest, sobrescrever=True)
    assert ifc.read_bytes() == IFC and obim.read_bytes() == OBIM
def test_perguntar_callback_decide_por_arquivo_existente(tmp_path):
    m = _m()
    pacote = _zip(tmp_path / "p.obimpack")
    dest = tmp_path / "dest"
    dest.mkdir()
    (dest / "Casa.ifc").write_bytes(b"A")
    vistos = []

    def nao(caminho):
        vistos.append(Path(caminho))
        return False
    with pytest.raises(m.ArquivoJaExiste):
        m.abrir(pacote, dest, perguntar=nao)
    assert vistos == [dest / "Casa.ifc"] and (dest / "Casa.ifc").read_bytes() == b"A"
    assert not (dest / "Casa.obim").exists()
    ifc, obim = m.abrir(pacote, dest, perguntar=lambda c: True)
    assert ifc.read_bytes() == IFC and obim.read_bytes() == OBIM
def test_nao_zip_recusa(tmp_path):
    p = tmp_path / "p.obimpack"
    p.write_bytes(b"isto nao e zip")
    _recusa(tmp_path, p)
def test_sem_ifc_recusa(tmp_path):
    p = _zip(tmp_path / "p.obimpack", {"Casa.obim": OBIM}, _manifesto())
    _recusa(tmp_path, p, "Casa.ifc")
def test_sem_obim_recusa(tmp_path):
    p = _zip(tmp_path / "p.obimpack", {"Casa.ifc": IFC}, _manifesto())
    _recusa(tmp_path, p, "Casa.obim")
def test_sem_manifesto_recusa(tmp_path):
    _recusa(tmp_path, _zip(tmp_path / "p.obimpack", manifesto=False), "manifesto")
@pytest.mark.parametrize("texto", [b"nao e json", b"[]", b'{"formato": "outro", "versao_pacote": "1", "arquivos": []}',
                                   b'{"formato": "obimpack"}'])
def test_manifesto_ilegivel_ou_fora_do_formato_recusa(tmp_path, texto):
    p = tmp_path / "p.obimpack"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("Casa.ifc", IFC)
        z.writestr("Casa.obim", OBIM)
        z.writestr("manifesto.json", texto)
    _recusa(tmp_path, p)
@pytest.mark.parametrize("alvo", ["Casa.ifc", "Casa.obim"])
def test_sha256_diferente_recusa_citando_o_arquivo(tmp_path, alvo):
    ent = {"Casa.ifc": IFC, "Casa.obim": OBIM}
    ent[alvo] = ent[alvo][:-1] + b"X"  # mesmo tamanho, conteudo trocado
    p = _zip(tmp_path / "p.obimpack", ent, _manifesto())
    _recusa(tmp_path, p, alvo)
@pytest.mark.parametrize("alvo", ["Casa.ifc", "Casa.obim"])
def test_tamanho_declarado_diferente_recusa(tmp_path, alvo):
    man = _manifesto()
    for a in man["arquivos"]:
        if a["nome"] == alvo:
            a["tamanho"] += 1
    _recusa(tmp_path, _zip(tmp_path / "p.obimpack", manifesto=man), alvo)
@pytest.mark.parametrize("nome", ["../fora.ifc", "a/../../fora.ifc", "/etc/fora.ifc", "\\fora.ifc", "C:/fora.ifc", "sub/Casa.ifc"])
def test_zip_slip_e_caminho_com_pasta_recusa_sem_extrair_nada(tmp_path, nome):
    p = _zip(tmp_path / "p.obimpack", extra=[(nome, b"mal")])
    _recusa(tmp_path, p)
    assert not (tmp_path / "fora.ifc").exists() and not (tmp_path.parent / "fora.ifc").exists()
def test_nome_perigoso_citado_no_manifesto_recusa(tmp_path):
    man = _manifesto()
    man["arquivos"][0]["nome"] = "../Casa.ifc"
    _recusa(tmp_path, _zip(tmp_path / "p.obimpack", {"../Casa.ifc": IFC, "Casa.obim": OBIM}, man))
    assert not (tmp_path / "Casa.ifc").exists()


def test_link_simbolico_recusa(tmp_path):
    p = tmp_path / "p.obimpack"
    _zip(p)
    info = zipfile.ZipInfo("Casa.ifc")
    info.create_system = 3
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(p, "w") as z:
        z.writestr(info, "/etc/passwd")
        z.writestr("Casa.obim", OBIM)
        man = _manifesto(ifc=b"/etc/passwd")
        z.writestr("manifesto.json", json.dumps(man))
    _recusa(tmp_path, p)
@pytest.mark.parametrize("repetida", ["Casa.ifc", "Casa.obim", "manifesto.json"])
def test_entrada_duplicada_recusa(tmp_path, repetida):
    igual = {"Casa.ifc": IFC, "Casa.obim": OBIM, "manifesto.json": json.dumps(_manifesto()).encode()}[repetida]
    p = _zip(tmp_path / "p.obimpack", extra=[(repetida, igual)])  # copia identica: so a duplicidade denuncia
    _recusa(tmp_path, p)
def test_entrada_fora_do_manifesto_recusa(tmp_path):
    p = _zip(tmp_path / "p.obimpack", extra=[("extra.txt", b"surpresa")])
    _recusa(tmp_path, p, "extra.txt")
def test_teto_de_bytes_contra_zip_bomb(tmp_path, monkeypatch):
    m = _m()
    grande = b"\x00" * 200_000  # comprime a quase nada
    p = _zip(tmp_path / "p.obimpack", {"Casa.ifc": grande, "Casa.obim": OBIM}, _manifesto(ifc=grande))
    monkeypatch.setattr(m, "LIMITE_BYTES", 100_000)
    _recusa(tmp_path, p)
    monkeypatch.setattr(m, "LIMITE_BYTES", 10_000_000)
    ifc, _ = m.abrir(p, tmp_path / "ok")
    assert ifc.read_bytes() == grande
def test_teto_de_entradas_contra_zip_bomb(tmp_path, monkeypatch):
    m = _m()
    p = _zip(tmp_path / "p.obimpack")  # pacote valido, 3 entradas
    monkeypatch.setattr(m, "LIMITE_ENTRADAS", 2)
    _recusa(tmp_path, p)
    monkeypatch.setattr(m, "LIMITE_ENTRADAS", 3)
    m.abrir(p, tmp_path / "ok")
def test_limites_padrao_sao_inteiros_positivos_e_pacote_normal_passa(tmp_path):
    m = _m()
    assert isinstance(m.LIMITE_ENTRADAS, int) and 3 <= m.LIMITE_ENTRADAS <= 10_000
    assert isinstance(m.LIMITE_BYTES, int) and m.LIMITE_BYTES >= 1 << 20
    m.abrir(_zip(tmp_path / "p.obimpack"), tmp_path / "dest")
    assert issubclass(m.ObimpackInvalido, ValueError) and issubclass(m.ArquivoJaExiste, FileExistsError)
def test_falha_nao_deixa_temporarios_nem_pacote_parcial_no_destino(tmp_path):
    m = _m()
    p = _zip(tmp_path / "p.obimpack", {"Casa.ifc": IFC[:-1] + b"X", "Casa.obim": OBIM}, _manifesto())
    dest = tmp_path / "dest"
    dest.mkdir()
    with pytest.raises(m.ObimpackInvalido):
        m.abrir(p, dest)
    assert list(dest.iterdir()) == []


@pytest.mark.parametrize("campo,valor", [("formato", "outro"), ("versao_pacote", ""), ("versao_pacote", 3), ("versao_pacote", None)])
def test_manifesto_com_arquivos_certos_mas_cabecalho_ruim_recusa(tmp_path, campo, valor):
    _recusa(tmp_path, _zip(tmp_path / "p.obimpack", manifesto=_manifesto(**{campo: valor})))


def test_perguntar_e_consultado_para_todos_os_existentes(tmp_path):
    m = _m()
    pacote = _zip(tmp_path / "p.obimpack")
    dest = tmp_path / "dest"
    dest.mkdir()
    (dest / "Casa.ifc").write_bytes(b"A")
    (dest / "Casa.obim").write_bytes(b"B")
    with pytest.raises(m.ArquivoJaExiste):
        m.abrir(pacote, dest, perguntar=lambda c: Path(c).name == "Casa.ifc")  # nega so o segundo
    assert (dest / "Casa.ifc").read_bytes() == b"A" and (dest / "Casa.obim").read_bytes() == b"B"


def test_falha_na_troca_final_nao_deixa_temporarios(tmp_path, monkeypatch):
    m = _m()
    pacote = _zip(tmp_path / "p.obimpack")
    dest = tmp_path / "dest"

    def quebra(*a, **k):
        raise OSError("disco falhou")
    monkeypatch.setattr("os.replace", quebra)
    with pytest.raises(OSError):
        m.abrir(pacote, dest)
    assert list(dest.iterdir()) == []


# 1. abrir: troca final tudo ou nada
@pytest.mark.parametrize("antes", [("A", "B"), ("A", None), (None, "B"), (None, None)])
def test_abrir_falha_no_segundo_replace_desfaz_tudo(tmp_path, monkeypatch, antes):
    m = _m()
    pacote = _zip(tmp_path / "p.obimpack")
    dest = tmp_path / "dest"
    dest.mkdir()
    esperado = {}
    for nome, cont in zip(("Casa.ifc", "Casa.obim"), antes):
        if cont:
            (dest / nome).write_bytes(cont.encode())
            esperado[nome] = cont.encode()
    real, chamadas = os.replace, []

    def falha(src, dst, *a, **k):
        chamadas.append(1)
        if len(chamadas) == 2:
            raise OSError("disco falhou")
        return real(src, dst, *a, **k)
    monkeypatch.setattr(os, "replace", falha)
    with pytest.raises(OSError):
        m.abrir(pacote, dest, sobrescrever=True)
    monkeypatch.setattr(os, "replace", real)
    assert {p.name: p.read_bytes() for p in dest.iterdir()} == esperado, "sem troca parcial, .tmp ou .bak"


# 2. abrir: manifesto mente no tamanho; nao pode descomprimir tudo
def test_manifesto_com_tamanho_pequeno_nao_descomprime_a_entrada_toda(tmp_path, monkeypatch):
    m = _m()
    ifc, obim = b"\x00" * 5_000_000, b"o" * 100
    man = _manifesto(ifc=ifc, obim=obim)
    man["arquivos"][0]["tamanho"] = 10
    p = _zip(tmp_path / "p.obimpack", {"Casa.ifc": ifc, "Casa.obim": obim}, man)
    monkeypatch.setattr(m, "LIMITE_BYTES", 200_000)
    lido = _espiar_leitura(monkeypatch)
    _recusa(tmp_path, p)
    assert lido[0] < 70_000, f"descomprimiu {lido[0]} bytes de uma entrada que passa do limite"


def test_orcamento_de_bytes_diminui_a_cada_arquivo_lido(tmp_path, monkeypatch):
    m = _m()
    ifc, obim = b"\x00" * 150_000, b"\x00" * 300_000
    man = _manifesto(ifc=ifc, obim=obim)
    man["arquivos"][1]["tamanho"] = 10  # mente: soma declarada cabe no limite, a real nao
    p = _zip(tmp_path / "p.obimpack", {"Casa.ifc": ifc, "Casa.obim": obim}, man)
    monkeypatch.setattr(m, "LIMITE_BYTES", 200_000)
    lido = _espiar_leitura(monkeypatch)
    _recusa(tmp_path, p)
    assert lido[0] < 160_000, f"leu {lido[0]} bytes: o 2o arquivo deveria estourar o saldo restante"


# 3. abrir: ZIP quebrado, com senha, metodo invalido, inexistente, pasta
def test_zip_vazio_e_truncado_recusa(tmp_path):
    p = tmp_path / "v.obimpack"
    p.write_bytes(b"")
    _recusa(tmp_path, p)
    bom = _zip(tmp_path / "b.obimpack").read_bytes()
    t = tmp_path / "t.obimpack"
    t.write_bytes(bom[:len(bom) // 2])
    _recusa(tmp_path, t)


@pytest.mark.parametrize("fill", [0xFF, 0x00, 0x55])
def test_deflate_corrompido_no_meio_recusa(tmp_path, fill):
    texto = "".join(f"#{i}=IFCWALL('g{i * 7919 % 10007}',$,'p{i}');\n" for i in range(3000)).encode()
    p = _zip(tmp_path / "p.obimpack", {"Casa.ifc": texto, "Casa.obim": OBIM}, _manifesto(ifc=texto))
    with zipfile.ZipFile(p) as z:
        info = z.getinfo("Casa.ifc")
    b = bytearray(p.read_bytes())
    nlen, elen = struct.unpack("<HH", b[info.header_offset + 26:info.header_offset + 30])
    ini = info.header_offset + 30 + nlen + elen + info.compress_size // 3
    b[ini:ini + 40] = bytes([fill]) * 40
    p.write_bytes(bytes(b))
    _recusa(tmp_path, p)


@pytest.mark.parametrize("erro", [zlib.error("x"), EOFError("x"), OSError("x"), RuntimeError("x"), NotImplementedError("x")])
def test_erro_de_leitura_do_zip_vira_obimpack_invalido(tmp_path, monkeypatch, erro):
    p = _zip(tmp_path / "p.obimpack")

    def quebra(self, n=-1):
        raise erro
    monkeypatch.setattr(zipfile.ZipExtFile, "read", quebra)
    _recusa(tmp_path, p)


@pytest.mark.parametrize("flags", [0x1, 0x1 | 0x8, 0x41])
def test_zip_com_senha_recusa(tmp_path, flags):
    p = _remendar(_zip_stored(tmp_path / "p.obimpack"), flags=flags)
    _recusa(tmp_path, p)


@pytest.mark.parametrize("metodo", [99, 7, 255])
def test_metodo_de_compressao_invalido_recusa(tmp_path, metodo):
    p = _remendar(_zip_stored(tmp_path / "p.obimpack"), metodo=metodo)
    _recusa(tmp_path, p)


def test_pacote_inexistente_recusa(tmp_path):
    m = _m()
    with pytest.raises(m.ObimpackInvalido):
        m.abrir(tmp_path / "nao_existe.obimpack", tmp_path / "dest")
    assert _vazio(tmp_path / "dest")


def test_pacote_que_e_pasta_recusa(tmp_path):
    m = _m()
    pasta = tmp_path / "pasta.obimpack"
    pasta.mkdir()
    with pytest.raises(m.ObimpackInvalido):
        m.abrir(pasta, tmp_path / "dest")
    assert _vazio(tmp_path / "dest")
