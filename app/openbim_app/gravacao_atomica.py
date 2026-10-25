# SPDX-License-Identifier: AGPL-3.0-or-later
"""Gravação atômica de um arquivo: temporário na mesma pasta, fsync, conferência, .bak de uma geração e troca (ADR-002 §4.5 e §4.8)."""
import errno
import hashlib
import os
import shutil
import sys
import time
from dataclasses import dataclass
from pathlib import Path

ETAPAS = ("escrever", "fsync", "conferir", "bak", "trocar", "fsync_pasta")
TENTATIVAS_TROCA = 6
ESPERA_TROCA = 0.05  # dobra a cada nova tentativa


class FalhaGravacao(Exception):
    """Falha ao gravar; `str(e)` já está em pt-BR. `gravado` é verdadeiro só se a troca já aconteceu."""

    def __init__(self, etapa, motivo, caminho, gravado, mensagem):
        super().__init__(mensagem)
        self.etapa, self.motivo, self.caminho, self.gravado = etapa, motivo, caminho, gravado


@dataclass(frozen=True)
class Preparado:
    destino: Path
    temporario: Path
    sha256: str
    tamanho: int


@dataclass(frozen=True)
class Gravado:
    caminho: Path
    sha256: str
    tamanho: int
    bak: Path | None


def _etapa(nome, caminho):
    """Ponto de falha e de morte dos testes: lê o ambiente na hora."""
    if os.environ.get("OBIM_S05_FALHA_EM") == nome:
        raise OSError(errno.EIO, f"falha simulada em {nome}", str(caminho))
    if os.environ.get("OBIM_S05_MORRER_EM") == nome:
        os._exit(86)


def _motivo(erro, etapa):
    if isinstance(erro, ValueError) and etapa == "conferir":
        return "conferencia"
    if isinstance(erro, OSError) and erro.errno == errno.ENOSPC:
        return "disco_cheio"
    if isinstance(erro, PermissionError):
        return "arquivo_em_uso" if etapa == "trocar" else "sem_permissao"
    return "outro"


_TEXTO = {
    "sem_permissao": "sem permissão para gravar na pasta",
    "disco_cheio": "o disco está cheio",
    "arquivo_em_uso": "o arquivo está em uso por outro programa",
    "conferencia": "o arquivo gravado não passou na conferência",
    "outro": "erro inesperado",
}


def _falha(erro, etapa, destino, gravado=False, extra=""):
    motivo = _motivo(erro, etapa)
    msg = f"Não foi possível gravar {destino.name} ({etapa}): {_TEXTO[motivo]}. {erro}{extra}"
    return FalhaGravacao(etapa, motivo, destino, gravado, msg)


def _apagar(*caminhos):
    for c in caminhos:
        try:
            Path(c).unlink(missing_ok=True)
        except OSError:
            pass


def _nomes(destino):
    destino = Path(destino)
    return destino, destino.with_name(destino.name + ".tmp"), destino.with_name(destino.name + ".bak"), destino.with_name(destino.name + ".bak.tmp")


def _resumo(caminho):
    h, tamanho = hashlib.sha256(), 0
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
            tamanho += len(bloco)
    return h.hexdigest(), tamanho


def conferir_ifc(caminho):
    """G5: recusa (ValueError) o IFC que não começa com ISO-10303-21; ou não termina com END-ISO-10303-21;."""
    with open(caminho, "rb") as f:
        inicio = f.read(13)
        f.seek(0, os.SEEK_END)
        f.seek(max(0, f.tell() - 64))
        fim = f.read().rstrip()
    if inicio != b"ISO-10303-21;" or not fim.endswith(b"END-ISO-10303-21;"):
        raise ValueError(f"{Path(caminho).name} parece incompleto (cabeçalho ou final do IFC ausente)")


def limpar_temporarios(destino):
    """Apaga `.tmp` e `.bak.tmp` que sobraram; devolve os caminhos apagados."""
    _, tmp, _, btmp = _nomes(destino)
    apagados = []
    for c in (tmp, btmp):
        if c.exists():
            _apagar(c)
            if not c.exists():
                apagados.append(c)
    return apagados


def preparar(destino, escrever, conferir=None):
    """Escreve o temporário, grava no disco (fsync) e confere; não toca no destino."""
    destino, tmp, _, btmp = _nomes(destino)
    etapa = "escrever"
    try:
        _apagar(tmp)
        _etapa("escrever", tmp)
        escrever(tmp)
        etapa = "fsync"
        _etapa("fsync", tmp)
        with open(tmp, "rb+") as f:
            f.flush()
            os.fsync(f.fileno())
        digest, tamanho = _resumo(tmp)
        etapa = "conferir"
        _etapa("conferir", tmp)
        if conferir:
            conferir(tmp)
    except Exception as e:  # noqa: BLE001
        _apagar(tmp, btmp)
        raise _falha(e, etapa, destino) from e
    return Preparado(destino, tmp, digest, tamanho)


def _fazer_bak(destino, bak, btmp):
    _apagar(btmp)
    try:
        os.link(destino, btmp)
    except OSError:
        shutil.copy2(destino, btmp)
        with open(btmp, "rb+") as f:
            os.fsync(f.fileno())
    os.replace(btmp, bak)


def _trocar(origem, destino):
    espera = ESPERA_TROCA
    for tentativa in range(TENTATIVAS_TROCA):
        try:
            os.replace(origem, destino)
            return
        except PermissionError:
            if tentativa == TENTATIVAS_TROCA - 1:
                raise
            time.sleep(espera)
            espera *= 2


def confirmar(preparado):
    """Faz o .bak de uma geração, troca o temporário pelo destino e grava a pasta (fsync)."""
    destino, tmp, bak, btmp = _nomes(preparado.destino)
    etapa, gravado = "bak", False
    try:
        _etapa("bak", destino)
        com_bak = destino.exists()
        if com_bak:
            _fazer_bak(destino, bak, btmp)
        etapa = "trocar"
        _etapa("trocar", destino)
        _trocar(tmp, destino)
        gravado, etapa = True, "fsync_pasta"
        _etapa("fsync_pasta", destino.parent)
        if sys.platform != "win32":
            fd = os.open(destino.parent, os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
    except Exception as e:  # noqa: BLE001
        if etapa == "trocar":
            if tmp.exists():
                extra = f" O arquivo novo ficou salvo em {tmp}."
            else:
                extra = f" O arquivo temporário {tmp} não foi encontrado no disco."
            raise _falha(e, etapa, destino, extra=extra) from e
        if not gravado:
            _apagar(tmp, btmp)
        raise _falha(e, etapa, destino, gravado) from e
    return Gravado(destino, preparado.sha256, preparado.tamanho, bak if com_bak else None)


def gravar_atomico(destino, escrever, conferir=None):
    return confirmar(preparar(destino, escrever, conferir))
