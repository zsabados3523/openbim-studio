# SPDX-License-Identifier: AGPL-3.0-or-later
"""Ajudantes comuns dos oraculos da F0-S06-T12 (pacote `.obimpack`)."""
import hashlib
import json
import os
import struct
import warnings
import zipfile

import pytest


IFC = b"ISO-10303-21;\nDATA;\n#1=IFCPROJECT('x');\nENDSEC;\nEND-ISO-10303-21;\n" * 20
OBIM = b"PK-obim-simulado-\x00\x01\x02" * 50

def _m():
    from openbim_app import obimpack
    return obimpack

def _par(tmp_path, nome="Casa"):
    pasta = tmp_path / "origem"
    pasta.mkdir()
    ifc, obim = pasta / f"{nome}.ifc", pasta / f"{nome}.obim"
    ifc.write_bytes(IFC)
    obim.write_bytes(OBIM)
    return ifc, obim

def _sha(b):
    return hashlib.sha256(b).hexdigest()

def _manifesto(ifc=IFC, obim=OBIM, **mudar):
    m = {"formato": "obimpack", "versao_pacote": "1.0.0", "arquivos": [
        {"nome": "Casa.ifc", "tamanho": len(ifc), "sha256": _sha(ifc)},
        {"nome": "Casa.obim", "tamanho": len(obim), "sha256": _sha(obim)}]}
    m.update(mudar)
    return m

def _zip(caminho, entradas=None, manifesto=None, extra=()):
    """Monta pacote cru. entradas: dict nome->bytes (padrao valido); extra: lista (ZipInfo|nome, bytes) adicionais."""
    entradas = {"Casa.ifc": IFC, "Casa.obim": OBIM} if entradas is None else dict(entradas)
    if manifesto is not False:
        entradas["manifesto.json"] = json.dumps(manifesto or _manifesto()).encode()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        with zipfile.ZipFile(caminho, "w", zipfile.ZIP_DEFLATED) as z:
            for n, b in list(entradas.items()) + list(extra):
                z.writestr(n, b)
    return caminho

def _vazio(pasta):
    return not pasta.exists() or not any(pasta.rglob("*"))

def _recusa(tmp_path, pacote, trecho=None):
    m = _m()
    dest = tmp_path / "dest"
    with pytest.raises(m.ObimpackInvalido) as e:
        m.abrir(pacote, dest)
    assert _vazio(dest), "pacote recusado nao pode extrair nada (nem temporario)"
    assert len(str(e.value)) >= 15
    if trecho:
        assert trecho in str(e.value)
    return e.value


def _ls(pasta):
    return sorted(p.name for p in pasta.iterdir())


def _espiar_leitura(monkeypatch):
    lido, orig = [0], zipfile.ZipExtFile.read

    def read(self, n=-1):
        d = orig(self, n)
        lido[0] += len(d)
        return d
    monkeypatch.setattr(zipfile.ZipExtFile, "read", read)
    return lido


def _zip_stored(caminho, ifc=IFC, obim=OBIM, man=None):
    man = man or _manifesto(ifc=ifc, obim=obim)
    with zipfile.ZipFile(caminho, "w", zipfile.ZIP_STORED) as z:
        z.writestr("Casa.ifc", ifc)
        z.writestr("Casa.obim", obim)
        z.writestr("manifesto.json", json.dumps(man))
    return caminho


def _remendar(caminho, flags=None, metodo=None):
    """Troca flags/metodo em todos os cabecalhos (locais e do diretorio central) de um ZIP STORED."""
    b = bytearray(caminho.read_bytes())
    for sig, o_flags, o_met in ((b"PK\x03\x04", 6, 8), (b"PK\x01\x02", 8, 10)):
        pos = b.find(sig)
        while pos != -1:
            if flags is not None:
                b[pos + o_flags:pos + o_flags + 2] = struct.pack("<H", flags)
            if metodo is not None:
                b[pos + o_met:pos + o_met + 2] = struct.pack("<H", metodo)
            pos = b.find(sig, pos + 4)
    caminho.write_bytes(bytes(b))
    return caminho


def _precisa_symlink(tmp_path):
    try:
        os.symlink(tmp_path / "x_alvo", tmp_path / "x_teste")
        (tmp_path / "x_teste").unlink()
    except (OSError, NotImplementedError, AttributeError):
        pytest.skip("sistema sem link simbolico")
