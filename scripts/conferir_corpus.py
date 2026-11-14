# SPDX-License-Identifier: AGPL-3.0-or-later
"""Confere manifestos do corpus (`corpus/manifestos/<nome>.json`) contra os modelos."""
import argparse
import hashlib
import json
import sys
from pathlib import Path

CAMPOS_OBRIGATORIOS = (
    "nome",
    "origem",
    "versao_ou_commit",
    "data_acesso",
    "sha256",
    "tamanho_bytes",
    "licenca",
    "atribuicao",
    "pode_ir_no_git",
    "esquema",
    "programa_de_origem",
    "contagens",
    "valores_conhecidos",
    "cobre",
    "observacoes",
)

LICENCAS_ACEITAS = frozenset({"CC-BY-4.0", "MIT", "Apache-2.0", "dominio-publico", "propria"})
LICENCAS_FORA_DO_GIT = frozenset({"CC-BY-ND-4.0", "KIT"})
VALORES_GIT = frozenset({"sim", "nao"})


def carregar_manifesto(caminho) -> dict:
    """Lê um manifesto JSON em UTF-8 e garante que é um objeto JSON."""
    p = Path(caminho)
    try:
        texto = p.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ValueError(f"Não foi possível ler o manifesto '{p.name}' em UTF-8: {exc}") from exc
    try:
        dados = json.loads(texto)
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON inválido no manifesto '{p.name}': {exc}") from exc
    if not isinstance(dados, dict):
        raise ValueError(f"Manifesto '{p.name}' deve conter um objeto JSON.")
    return dados


def _sha256_arquivo(caminho: Path) -> str:
    """Calcula o SHA-256 em hexadecimal minúsculo lendo o arquivo em blocos."""
    h = hashlib.sha256()
    with caminho.open("rb") as f:
        for bloco in iter(lambda: f.read(1024 * 1024), b""):
            h.update(bloco)
    return h.hexdigest()


def _validar_manifesto(stem: str, dados: dict, arquivo: Path | None) -> list[str]:
    """Valida campos obrigatórios, licença, política de git e integridade do arquivo."""
    erros: list[str] = []
    for campo in CAMPOS_OBRIGATORIOS:
        if campo not in dados or dados[campo] is None:
            erros.append(f"Manifesto '{stem}': campo obrigatório '{campo}' ausente.")

    if dados.get("nome") is not None and dados["nome"] != stem:
        erros.append(f"Manifesto '{stem}': campo 'nome' ('{dados['nome']}') difere do arquivo.")

    pode_git = dados.get("pode_ir_no_git")
    if pode_git is not None and pode_git not in VALORES_GIT:
        erros.append(f"Manifesto '{stem}': campo 'pode_ir_no_git' inválido ('{pode_git}'); use 'sim' ou 'nao'.")

    licenca = dados.get("licenca")
    if licenca is not None:
        if licenca in LICENCAS_FORA_DO_GIT:
            if pode_git != "nao":
                erros.append(
                    f"Manifesto '{stem}': licença '{licenca}' exige 'pode_ir_no_git' = 'nao'."
                )
        elif licenca not in LICENCAS_ACEITAS:
            erros.append(f"Manifesto '{stem}': campo 'licenca' não aceito ('{licenca}').")

    if arquivo is None:
        if pode_git == "sim":
            erros.append(
                f"Manifesto '{stem}': modelo ausente em corpus com 'pode_ir_no_git' = 'sim'."
            )
        return erros

    tam = dados.get("tamanho_bytes")
    if tam is not None:
        tamanho_real = arquivo.stat().st_size
        if isinstance(tam, bool) or not isinstance(tam, int) or tam != tamanho_real:
            erros.append(
                f"Manifesto '{stem}': campo 'tamanho_bytes' ({tam}) não confere com '{arquivo.name}' ({tamanho_real})."
            )

    sha_decl = dados.get("sha256")
    if sha_decl is not None:
        sha_real = _sha256_arquivo(arquivo)
        if not isinstance(sha_decl, str) or sha_decl.lower() != sha_real:
            erros.append(
                f"Manifesto '{stem}': campo 'sha256' não confere com '{arquivo.name}'."
            )

    return erros


def conferir(pasta_corpus, pasta_manifestos) -> list[str]:
    """Confere modelos em `pasta_corpus` e manifestos em `pasta_manifestos`, devolvendo lista de erros em pt-BR."""
    dir_corpus = Path(pasta_corpus)
    dir_manifestos = Path(pasta_manifestos)
    erros: list[str] = []
    modelos_por_stem: dict[str, Path] = {}

    if dir_corpus.is_dir():
        for arq in sorted(dir_corpus.iterdir()):
            if not arq.is_file() or arq.name.startswith("README"):
                continue
            if arq.stem in modelos_por_stem:
                erros.append(
                    f"Modelo '{arq.name}': conflito de nome-base com '{modelos_por_stem[arq.stem].name}'."
                )
            else:
                modelos_por_stem[arq.stem] = arq
            if not (dir_manifestos / f"{arq.stem}.json").is_file():
                erros.append(f"Modelo '{arq.name}' sem manifesto ({arq.stem}.json).")

    if dir_manifestos.is_dir():
        for m_path in sorted(dir_manifestos.glob("*.json")):
            if not m_path.is_file():
                continue
            try:
                dados = carregar_manifesto(m_path)
            except ValueError as exc:
                erros.append(f"Manifesto '{m_path.stem}': {exc}")
                continue
            erros.extend(_validar_manifesto(m_path.stem, dados, modelos_por_stem.get(m_path.stem)))

    return erros


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Confere manifestos e modelos do corpus.")
    parser.add_argument("pasta_corpus", nargs="?", default="corpus")
    parser.add_argument("pasta_manifestos", nargs="?", default="corpus/manifestos")
    args = parser.parse_args(argv)
    erros = conferir(args.pasta_corpus, args.pasta_manifestos)
    if erros:
        for e in erros:
            print(f"ERRO: {e}", file=sys.stderr)
        return 1
    print("Corpus conferido sem erros.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
