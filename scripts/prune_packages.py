# SPDX-License-Identifier: AGPL-3.0-or-later
"""Remove de um ambiente conda os pacotes de raiz informados e os que só existem por causa deles.

Uso: prune_packages.py PREFIXO RELATORIO.txt [--esperado=PKG,PKG] RAIZ [RAIZ ...]
Um pacote dependente só é removido se TODOS os pacotes que dependem dele também forem removidos
(então nada que o resto do ambiente declare precisar é apagado). Apaga os arquivos listados em
conda-meta/<pacote>.json; os próprios .json ficam (o inventário de licenças continua listando tudo).
Com --esperado, falha (código 2) se os pacotes MANTIDOS que declaram depender de algo removido
não forem exatamente os esperados (hoje: occt, que depende do vtk).
RELATORIO.txt recebe um pacote por linha (nome versão licença), para o REMOVIDOS.md e o FONTES.md.
"""
import json
import sys
from pathlib import Path


def main(argv):
    for fluxo in (sys.stdout, sys.stderr):  # console do Windows usa cp1252 por padrão
        fluxo.reconfigure(encoding="utf-8", errors="replace")
    esperado = None
    args = []
    for a in argv[3:]:
        if a.startswith("--esperado="):
            esperado = set(a.split("=", 1)[1].split(","))
        else:
            args.append(a)
    prefix, relatorio, raizes = Path(argv[1]), Path(argv[2]), set(args)
    pk = {}
    for f in (prefix / "conda-meta").glob("*.json"):
        d = json.loads(f.read_text(encoding="utf-8"))
        pk[d["name"]] = d
    faltam = raizes - pk.keys()
    if faltam:
        print("pacotes raiz ausentes do ambiente:", ", ".join(sorted(faltam)), file=sys.stderr)
    rev = {}
    for n, d in pk.items():
        for dep in d.get("depends", []):
            rev.setdefault(dep.split()[0], set()).add(n)
    removidos = set(raizes) & pk.keys()
    mudou = True
    while mudou:
        mudou = False
        for n in list(removidos):
            for dep in pk[n].get("depends", []):
                m = dep.split()[0]
                if m in pk and m not in removidos and rev.get(m, set()) <= removidos:
                    removidos.add(m)
                    mudou = True
    orfaos = {
        n for n, d in pk.items()
        if n not in removidos and any(dep.split()[0] in removidos for dep in d.get("depends", []))
    }
    print("mantidos que declaram depender de pacote removido:", ", ".join(sorted(orfaos)) or "(nenhum)")
    if esperado is not None and orfaos != esperado:
        print("ERRO: esperado", ", ".join(sorted(esperado)), file=sys.stderr)
        return 2
    apagados = 0
    for n in sorted(removidos):
        for rel in pk[n].get("files", []):
            alvo = prefix / rel
            if alvo.is_file() or alvo.is_symlink():
                alvo.unlink()
                apagados += 1
    relatorio.write_text(
        "".join(f"{n} {pk[n]['version']} {pk[n].get('license') or '?'}\n" for n in sorted(removidos)),
        encoding="utf-8",
    )
    print(f"{len(removidos)} pacotes removidos ({apagados} arquivos)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
