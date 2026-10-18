# SPDX-License-Identifier: AGPL-3.0-or-later
"""Confere o ci.yml: todo trabalho `windows-*` com passo que bloqueia o merge
precisa estar no `needs` do agregador `windows` (senão os testes dele não bloqueiam).

Uso: python3 scripts/conferir_ci_windows.py [.github/workflows/ci.yml]
Sai com código 1 e lista o que faltou. Só usa a biblioteca padrão.
"""
import re
import sys

BLOQUEIA = re.compile(r"(?<!não )bloqueia o merge")


def trabalhos(texto):
    """Devolve {nome: linhas} dos trabalhos (chaves com 2 espaços sob `jobs:`)."""
    achados, atual, dentro = {}, None, False
    for linha in texto.splitlines():
        if linha.startswith("jobs:"):
            dentro = True
            continue
        if dentro and linha.strip() and re.match(r"^\S", linha):
            dentro = False
        m = re.match(r"^  ([A-Za-z0-9_-]+):\s*$", linha) if dentro else None
        if m:
            atual = m.group(1)
            achados[atual] = []
        elif dentro and atual:
            achados[atual].append(linha)
    return achados


def conferir(texto):
    jobs = trabalhos(texto)
    if "windows" not in jobs:
        return ["falta o trabalho agregador `windows`"]
    corpo = "\n".join(jobs["windows"])
    m = re.search(r"^    needs:\s*\[([^\]]*)\]", corpo, re.M)
    if not m:
        return ["o `windows` precisa de `needs: [a, b, ...]` em uma linha"]
    needs = {n.strip() for n in m.group(1).split(",") if n.strip()}
    bloqueiam = {
        nome
        for nome, linhas in jobs.items()
        if nome.startswith("windows-") and BLOQUEIA.search("\n".join(linhas))
    }
    erros = [f"`{n}` bloqueia o merge mas não está no needs de `windows`" for n in sorted(bloqueiam - needs)]
    erros += [f"`{n}` está no needs de `windows` mas não existe" for n in sorted(needs - set(jobs))]
    return erros


def main(argv):
    caminho = argv[1] if len(argv) > 1 else ".github/workflows/ci.yml"
    with open(caminho, encoding="utf-8") as f:
        erros = conferir(f.read())
    for e in erros:
        print(f"::error title=needs do windows::{e}")
    if not erros:
        print("ok: todo trabalho do Windows que bloqueia está no needs de `windows`")
    return 1 if erros else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
