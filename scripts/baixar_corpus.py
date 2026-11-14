# SPDX-License-Identifier: AGPL-3.0-or-later
"""Baixa modelos do corpus a partir de `corpus/lista.json` e gera manifestos."""
import argparse
from datetime import date
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import zipfile

BLOCO = 65536


def _sha256_arquivo(caminho: Path) -> str:
    h = hashlib.sha256()
    with caminho.open("rb") as f:
        for bloco in iter(lambda: f.read(BLOCO), b""):
            h.update(bloco)
    return h.hexdigest()


def _ler_secao_header(caminho: Path) -> str:
    """Lê apenas até ENDSEC; para evitar carregar arquivos grandes na memória."""
    buf = bytearray()
    with caminho.open("rb") as f:
        while bloco := f.read(BLOCO):
            buf.extend(bloco)
            if b"ENDSEC;" in buf:
                break
    if buf.startswith(b"\xef\xbb\xbf"):
        del buf[:3]
    texto = bytes(buf).decode("utf-8", errors="replace")
    fim = texto.find("ENDSEC;")
    return texto[:fim] if fim != -1 else texto


def _achar_inicio_args(texto: str, nome_cmd: str) -> int | None:
    alvo, upper, idx = nome_cmd.upper(), texto.upper(), 0
    while (pos := upper.find(alvo, idx)) != -1:
        idx = pos + len(alvo)
        if pos > 0 and (upper[pos - 1].isalnum() or upper[pos - 1] == "_"):
            continue
        j = idx
        while j < len(texto) and texto[j].isspace():
            j += 1
        if j < len(texto) and texto[j] == "(":
            return j
    return None


def _parse_tupla_step(texto: str, pos: int) -> tuple[list, int]:
    """Analisa uma lista entre parênteses do cabeçalho STEP respeitando strings '...'."""
    itens: list = []
    i, n = pos + 1, len(texto)
    token: list[str] = []

    def _flush() -> None:
        bruto = "".join(token).strip()
        token.clear()
        if bruto:
            itens.append(bruto)

    while i < n:
        ch = texto[i]
        if ch == "'":
            i += 1
            chars: list[str] = []
            while i < n:
                if texto[i] == "'" and i + 1 < n and texto[i + 1] == "'":
                    chars.append("'")
                    i += 2
                elif texto[i] == "'":
                    i += 1
                    break
                else:
                    chars.append(texto[i])
                    i += 1
            itens.append("".join(chars))
            token.clear()
        elif ch == "/" and i + 1 < n and texto[i + 1] == "*":
            fim = texto.find("*/", i + 2)
            i = n if fim == -1 else fim + 2
        elif ch == "(":
            sub, i = _parse_tupla_step(texto, i)
            itens.append(sub)
            token.clear()
        elif ch == ",":
            _flush()
            i += 1
        elif ch == ")":
            _flush()
            return itens, i + 1
        else:
            token.append(ch)
            i += 1
    _flush()
    return itens, i


def cabecalho_step(caminho) -> dict[str, str]:
    """Extrai esquema (1o item de FILE_SCHEMA) e programa (6o campo de FILE_NAME)."""
    texto = _ler_secao_header(Path(caminho))
    esquema, programa = "", ""
    if (pos := _achar_inicio_args(texto, "FILE_SCHEMA")) is not None:
        args, _ = _parse_tupla_step(texto, pos)
        if args:
            esquema = str(args[0][0]) if isinstance(args[0], list) and args[0] else str(args[0])
    if (pos := _achar_inicio_args(texto, "FILE_NAME")) is not None:
        args, _ = _parse_tupla_step(texto, pos)
        if len(args) >= 6:
            programa = str(args[5])
    return {"esquema": esquema, "programa": programa}


def _resolver_url(url: str, base_url_override: str | None) -> str:
    if not base_url_override:
        return url
    partes = urllib.parse.urlsplit(url)
    caminho = f"{partes.path}?{partes.query}" if partes.query else partes.path
    return base_url_override.rstrip("/") + caminho


def _ja_valido(destino_ifc: Path, destino_manif: Path) -> bool:
    if not destino_ifc.is_file() or not destino_manif.is_file():
        return False
    try:
        dados = json.loads(destino_manif.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return isinstance(dados, dict) and dados.get("sha256") == _sha256_arquivo(destino_ifc)


def _baixar_para_temp(url: str, tmp_path: Path) -> tuple[int, str]:
    req = urllib.request.Request(url, headers={"User-Agent": "OpenBIM-Studio/0.1"})
    h, tamanho = hashlib.sha256(), 0
    with urllib.request.urlopen(req, timeout=60) as resp, tmp_path.open("wb") as out:
        while bloco := resp.read(BLOCO):
            out.write(bloco)
            h.update(bloco)
            tamanho += len(bloco)
    return tamanho, h.hexdigest()


def _extrair_ifc_do_zip(zip_path: Path, destino_ifc: Path, arquivo_no_zip: str | None) -> None:
    with zipfile.ZipFile(zip_path, "r") as zf:
        if arquivo_no_zip:
            if arquivo_no_zip not in zf.namelist():
                raise ValueError(f"arquivo '{arquivo_no_zip}' não encontrado no zip.")
            alvo = arquivo_no_zip
        else:
            candidatos = [
                i for i in zf.infolist()
                if not i.is_dir() and not i.filename.startswith("__MACOSX/") and i.filename.lower().endswith(".ifc")
            ]
            if not candidatos:
                raise ValueError("nenhum arquivo .ifc encontrado no zip.")
            alvo = max(candidatos, key=lambda i: i.file_size).filename
        with zf.open(alvo, "r") as src, destino_ifc.open("wb") as dst:
            shutil.copyfileobj(src, dst, length=BLOCO)


def _processar_entrada(
    entrada: dict, dir_corpus: Path, dir_manifestos: Path, base_url_override: str | None
) -> str | None:
    nome = entrada["nome"]
    destino_ifc, destino_manif = dir_corpus / f"{nome}.ifc", dir_manifestos / f"{nome}.json"
    if _ja_valido(destino_ifc, destino_manif):
        return None

    url = _resolver_url(entrada["url"], base_url_override)
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir) / "download.bin"
        try:
            tam_baixado, sha_baixado = _baixar_para_temp(url, tmp_path)
        except urllib.error.HTTPError as exc:
            return f"Falha ao baixar '{nome}': erro HTTP {exc.code} ({exc.reason})."
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            return f"Falha de rede ao baixar '{nome}': {exc}."

        tam_esp = entrada.get("tamanho_esperado")
        if tam_esp is not None and tam_baixado != tam_esp:
            return f"Falha ao validar '{nome}': tamanho {tam_baixado} difere do esperado ({tam_esp})."

        sha_esp = entrada.get("sha256_esperado")
        if sha_esp and sha_baixado != str(sha_esp).lower():
            return f"Falha ao validar '{nome}': sha256 divergente (esperado {sha_esp}, obtido {sha_baixado})."

        eh_zip = bool(entrada.get("arquivo_no_zip")) or urllib.parse.urlsplit(url).path.lower().endswith(".zip")
        if eh_zip or zipfile.is_zipfile(tmp_path):
            try:
                _extrair_ifc_do_zip(tmp_path, destino_ifc, entrada.get("arquivo_no_zip"))
            except (zipfile.BadZipFile, ValueError, OSError) as exc:
                destino_ifc.unlink(missing_ok=True)
                return f"Falha ao extrair '{nome}': {exc}"
            sha_ifc, tam_ifc = _sha256_arquivo(destino_ifc), destino_ifc.stat().st_size
        else:
            shutil.copyfile(tmp_path, destino_ifc)
            sha_ifc, tam_ifc = sha_baixado, tam_baixado

    cab = cabecalho_step(destino_ifc)
    manifesto = {
        "nome": nome, "origem": entrada["origem"], "versao_ou_commit": entrada["versao_ou_commit"],
        "data_acesso": entrada.get("data_acesso") or date.today().isoformat(),
        "sha256": sha_ifc, "tamanho_bytes": tam_ifc, "licenca": entrada["licenca"],
        "atribuicao": entrada["atribuicao"], "pode_ir_no_git": entrada["pode_ir_no_git"],
        "esquema": cab["esquema"], "programa_de_origem": cab["programa"],
        "contagens": {}, "valores_conhecidos": {}, "cobre": entrada["cobre"],
        "observacoes": entrada.get("observacoes", ""),
    }
    destino_manif.write_text(json.dumps(manifesto, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return None


def baixar(lista_path, pasta_corpus, pasta_manifestos, base_url_override=None) -> list[str]:
    """Baixa os modelos listados em `lista_path`, grava manifestos e retorna erros em pt-BR."""
    dir_corpus, dir_manifestos = Path(pasta_corpus), Path(pasta_manifestos)
    dir_corpus.mkdir(parents=True, exist_ok=True)
    dir_manifestos.mkdir(parents=True, exist_ok=True)
    entradas = json.loads(Path(lista_path).read_text(encoding="utf-8"))
    erros: list[str] = []
    for entrada in entradas:
        if erro := _processar_entrada(entrada, dir_corpus, dir_manifestos, base_url_override):
            erros.append(erro)
    return erros


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Baixa modelos do corpus e gera manifestos.")
    parser.add_argument("--base-url", default=None, help="Substitui esquema e host das URLs (uso em testes).")
    parser.add_argument("lista", nargs="?", default="corpus/lista.json")
    parser.add_argument("pasta_corpus", nargs="?", default="corpus")
    parser.add_argument("pasta_manifestos", nargs="?", default="corpus/manifestos")
    args = parser.parse_args(argv)
    erros = baixar(args.lista, args.pasta_corpus, args.pasta_manifestos, base_url_override=args.base_url)
    for erro in erros:
        print(f"ERRO: {erro}", file=sys.stderr)
    return 1 if erros else 0


if __name__ == "__main__":
    raise SystemExit(main())
