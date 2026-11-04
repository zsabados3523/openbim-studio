# SPDX-License-Identifier: AGPL-3.0-or-later
"""Pacote `.obimpack`: ZIP plano com o par IFC/OBIM e `manifesto.json`; valida tudo antes de gravar e usa só os dois nomes fixos."""
import hashlib
import json
import os
import stat
import tempfile
import zipfile
import zlib
from pathlib import Path

FORMATO = "obimpack"
VERSAO_PACOTE = "1.0.0"
NOME_IFC = "Casa.ifc"
NOME_OBIM = "Casa.obim"
NOME_MANIFESTO = "manifesto.json"
NOMES = (NOME_IFC, NOME_OBIM)
LIMITE_ENTRADAS = 1000
LIMITE_BYTES = 256 * 1024 * 1024
LIMITE_MANIFESTO = 1 << 20

_RESERVADOS = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{i}" for i in range(1, 10)}
    | {f"LPT{i}" for i in range(1, 10)}
)


class ObimpackInvalido(ValueError):
    """Pacote fora do formato ou inseguro; nada é extraído."""


class ArquivoJaExiste(FileExistsError):
    """Destino já tem arquivo e não houve autorização para trocar."""


def _proibido(nome):
    if not isinstance(nome, str) or not nome:
        return True
    if nome != nome.strip():
        return True
    if nome in (".", ".."):
        return True
    if nome.endswith(("/", "\\", ".", " ")):
        return True
    if "/" in nome or "\\" in nome:
        return True
    if ":" in nome:
        return True
    if any(ord(c) < 32 or ord(c) == 127 for c in nome):
        return True
    if nome.split(".")[0].upper() in _RESERVADOS:
        return True
    return False


def _ler(z, nome, teto):
    h, partes, total = hashlib.sha256(), [], 0
    with z.open(nome) as f:
        while True:
            restante = teto + 1 - total
            if restante <= 0:
                raise ObimpackInvalido(f"{nome} passa do limite de bytes do pacote")
            bloco = f.read(min(1 << 16, restante))
            if not bloco:
                break
            total += len(bloco)
            if total > teto:
                raise ObimpackInvalido(f"{nome} passa do limite de bytes do pacote")
            h.update(bloco)
            partes.append(bloco)
    return b"".join(partes), total, h.hexdigest()


def _manifesto(bruto):
    try:
        man = json.loads(bruto.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise ObimpackInvalido(f"manifesto.json ilegível: {e}") from e
    if not isinstance(man, dict) or man.get("formato") != FORMATO:
        raise ObimpackInvalido("manifesto.json fora do formato obimpack")
    if not isinstance(man.get("versao_pacote"), str) or not man["versao_pacote"]:
        raise ObimpackInvalido("manifesto.json sem versao_pacote texto não vazio")
    arquivos = man.get("arquivos")
    if not isinstance(arquivos, list) or len(arquivos) != 2:
        raise ObimpackInvalido("manifesto.json deve listar exatamente o arquivo IFC e o OBIM")
    vistos = set()
    for a in arquivos:
        if not isinstance(a, dict):
            raise ObimpackInvalido("manifesto.json com item de arquivo inválido")
        nome, tamanho, sha = a.get("nome"), a.get("tamanho"), a.get("sha256")
        if _proibido(nome):
            raise ObimpackInvalido(f"manifesto.json com nome de arquivo inválido: {nome!r}")
        if not isinstance(tamanho, int) or isinstance(tamanho, bool) or tamanho < 0:
            raise ObimpackInvalido(f"manifesto.json com tamanho inválido para {nome}")
        if not isinstance(sha, str) or len(sha) != 64 or any(c not in "0123456789abcdefABCDEF" for c in sha):
            raise ObimpackInvalido(f"manifesto.json com sha256 inválido para {nome}")
        if nome in vistos:
            raise ObimpackInvalido(f"manifesto.json repete o arquivo {nome}")
        vistos.add(nome)
    if vistos != set(NOMES):
        raise ObimpackInvalido("manifesto.json deve citar Casa.ifc e Casa.obim")
    return man


def _conferir_par(par):
    try:
        ifc, obim = par
    except (TypeError, ValueError) as e:
        raise ObimpackInvalido("o par deve ser (caminho_ifc, caminho_obim)") from e
    ifc, obim = Path(ifc), Path(obim)
    for caminho, sufixo in ((ifc, ".ifc"), (obim, ".obim")):
        if not caminho.is_file() or caminho.suffix.lower() != sufixo:
            raise ObimpackInvalido(f"arquivo do par inválido: {caminho}")
    if ifc.parent.resolve() != obim.parent.resolve() or ifc.stem != obim.stem:
        raise ObimpackInvalido("o par IFC/OBIM precisa estar na mesma pasta e ter o mesmo nome-base")
    if _proibido(ifc.stem):
        raise ObimpackInvalido(f"nome-base do par inválido: {ifc.stem!r}")
    return ifc, obim


def exportar(par, destino=None, *, sobrescrever=False, perguntar=None):
    """Gera o `.obimpack` a partir do par IFC/OBIM; grava por temporário e `os.replace`."""
    ifc, obim = _conferir_par(par)
    destino = Path(destino) if destino is not None else ifc.parent / f"{ifc.stem}.obimpack"
    if os.path.lexists(destino) and not sobrescrever:
        if perguntar is None or not perguntar(destino):
            raise ArquivoJaExiste(f"pacote já existe: {destino}")
    dados = {NOME_IFC: ifc.read_bytes(), NOME_OBIM: obim.read_bytes()}
    manifesto = {"formato": FORMATO, "versao_pacote": VERSAO_PACOTE, "arquivos": [
        {"nome": n, "tamanho": len(dados[n]), "sha256": hashlib.sha256(dados[n]).hexdigest()} for n in NOMES]}
    destino.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{destino.name}.", suffix=".tmp", dir=destino.parent)
    os.close(fd)
    try:
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
            for nome in NOMES:
                z.writestr(nome, dados[nome])
            z.writestr(NOME_MANIFESTO, json.dumps(manifesto, ensure_ascii=False, sort_keys=True).encode("utf-8"))
        with open(tmp, "rb+") as f:
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, destino)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return destino


def abrir(pacote, destino, *, sobrescrever=False, perguntar=None):
    """Valida o pacote inteiro antes de gravar e extrai os dois arquivos fixos em `destino`."""
    pacote, destino = Path(pacote), Path(destino)
    dados = {}
    try:
        with zipfile.ZipFile(pacote) as z:
            infos = z.infolist()
            if len(infos) > LIMITE_ENTRADAS:
                raise ObimpackInvalido(f"pacote com {len(infos)} entradas, acima do limite de {LIMITE_ENTRADAS}")
            nomes = [i.filename for i in infos]
            if len(set(nomes)) != len(nomes):
                raise ObimpackInvalido("pacote com entradas duplicadas")
            for info in infos:
                modo = info.external_attr >> 16
                tipo = stat.S_IFMT(modo)
                if (_proibido(info.filename) or info.flag_bits & 1
                        or info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)
                        or tipo not in (0, stat.S_IFREG)):
                    raise ObimpackInvalido(f"entrada insegura: {info.filename!r}")
            if NOME_MANIFESTO not in nomes:
                raise ObimpackInvalido("pacote sem manifesto.json")
            bruto, _, _ = _ler(z, NOME_MANIFESTO, LIMITE_MANIFESTO)
            manifest = _manifesto(bruto)
            declarados = {a["nome"]: a for a in manifest["arquivos"]}
            total = sum(a["tamanho"] for a in declarados.values())
            if total > LIMITE_BYTES:
                raise ObimpackInvalido(f"pacote declara {total} bytes, acima do limite de {LIMITE_BYTES}")
            permitidos = {NOME_MANIFESTO, *declarados}
            for nome in nomes:
                if nome not in permitidos:
                    raise ObimpackInvalido(f"entrada fora do manifesto: {nome}")
            faltando = [n for n in NOMES if n not in nomes]
            if faltando:
                raise ObimpackInvalido(f"pacote sem o arquivo {faltando[0]}")
            orcamento = LIMITE_BYTES
            for nome in NOMES:
                item = declarados[nome]
                teto = min(item["tamanho"] + 1, orcamento)
                conteudo, lido, sha = _ler(z, nome, teto)
                orcamento -= lido
                if lido != item["tamanho"]:
                    raise ObimpackInvalido(f"tamanho de {nome} diferente do manifesto: esperado {item['tamanho']}, lido {lido}")
                if sha.lower() != item["sha256"].lower():
                    raise ObimpackInvalido(f"sha256 de {nome} diferente do manifesto")
                dados[nome] = conteudo
    except ObimpackInvalido:
        raise
    except zipfile.BadZipFile as e:
        raise ObimpackInvalido(f"{pacote.name} não é um pacote ZIP válido") from e
    except (zlib.error, EOFError, OSError, RuntimeError, NotImplementedError) as e:
        raise ObimpackInvalido(f"{pacote.name} não pôde ser lido: {e}") from e
    alvos = {nome: destino / nome for nome in NOMES}
    existentes = [alvos[n] for n in NOMES if os.path.lexists(alvos[n])]
    if existentes and not sobrescrever:
        if perguntar is None:
            raise ArquivoJaExiste(f"arquivo já existe: {existentes[0]}")
        for caminho in existentes:
            if not perguntar(caminho):
                raise ArquivoJaExiste(f"arquivo já existe e não foi autorizado: {caminho}")
    destino.mkdir(parents=True, exist_ok=True)
    pendentes, backups, instalados = [], [], []
    try:
        for nome in NOMES:
            fd, tmp = tempfile.mkstemp(prefix=f".{nome}.", suffix=".tmp", dir=destino)
            os.close(fd)
            pendentes.append((tmp, alvos[nome]))
            with open(tmp, "wb") as f:
                f.write(dados[nome])
                f.flush()
                os.fsync(f.fileno())
        for tmp, alvo in pendentes:
            if os.path.lexists(alvo):
                fd, bak = tempfile.mkstemp(prefix=f".{alvo.name}.", suffix=".bak", dir=destino)
                os.close(fd)
                try:
                    os.replace(alvo, bak)
                except BaseException:
                    try:
                        os.unlink(bak)
                    except OSError:
                        pass
                    raise
                backups.append((bak, alvo))
        for tmp, alvo in pendentes:
            os.replace(tmp, alvo)
            instalados.append(alvo)
        for bak, _ in backups:
            try:
                os.unlink(bak)
            except OSError:
                pass
        pendentes, backups = [], []
    except BaseException:
        for alvo in instalados:
            try:
                os.unlink(alvo)
            except OSError:
                pass
        for bak, alvo in backups:
            try:
                os.replace(bak, alvo)
            except OSError:
                pass
        raise
    finally:
        for tmp, _ in pendentes:
            try:
                os.unlink(tmp)
            except OSError:
                pass
        for bak, _ in backups:
            try:
                os.unlink(bak)
            except OSError:
                pass
    return alvos[NOME_IFC], alvos[NOME_OBIM]
