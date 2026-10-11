# SPDX-License-Identifier: AGPL-3.0-or-later
"""Copia os arquivos de licença que cada pacote conda traz (info/licenses/) para uma pasta.

Uso: collect_package_licenses.py PREFIXO_DO_AMBIENTE PASTA_SAIDA
Cria PASTA_SAIDA/<pacote>/... e imprime quantos pacotes tinham arquivos de licença.
Pacotes sem a pasta (ou sem cache extraído) são listados no fim, para constar no relatório.
"""
import json
import shutil
import sys
from pathlib import Path


def main(argv):
    for fluxo in (sys.stdout, sys.stderr):  # console do Windows usa cp1252 por padrão
        fluxo.reconfigure(encoding="utf-8", errors="replace")
    prefix, out = Path(argv[1]), Path(argv[2])
    com, sem = 0, []
    for f in sorted((prefix / "conda-meta").glob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        src = Path(d.get("extracted_package_dir") or "") / "info" / "licenses"
        if src.is_dir() and any(src.iterdir()):
            shutil.copytree(src, out / d["name"], dirs_exist_ok=True)
            com += 1
        else:
            sem.append(d["name"])
    print(f"{com} pacotes com arquivos de licença; {len(sem)} sem: {', '.join(sem)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
