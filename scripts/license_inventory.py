# SPDX-License-Identifier: AGPL-3.0-or-later
"""Inventário de licenças do ambiente conda ativo (ADR-009 §7, itens 2 e 3).

Uso: python scripts/license_inventory.py SAIDA.md
Lê $CONDA_PREFIX/conda-meta/*.json. Sai com 1 se algum pacote não vier do
conda-forge ou não tiver licença declarada.
"""
import json
import os
import sys
from pathlib import Path

UNKNOWN = {"", "unknown", "none", "null"}

# Exceções registradas (ADR-009: licença vazia bloqueia, salvo decisão registrada).
# nome -> (licença SPDX, justificativa). Registrar também em docs/state/LOG.md.
EXCEPTIONS = {
    "tbb-devel": ("Apache-2.0", "metadado do pacote vazio; o pacote irmão tbb e a página do conda-forge declaram Apache-2.0 (2026-10-10)"),
}


def collect(prefix):
    rows = []
    for f in sorted((Path(prefix) / "conda-meta").glob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        origin = d.get("url") or d.get("channel") or ""
        name = d.get("name", f.stem)
        lic = (d.get("license") or "").strip()
        if lic.lower() in UNKNOWN and name in EXCEPTIONS:
            lic = EXCEPTIONS[name][0] + " (exceção registrada)"
        rows.append((name, d.get("version", ""), lic, origin))
    return rows


def is_forge(origin):
    return "/conda-forge/" in origin or origin.rstrip("/").endswith("/conda-forge") or origin == "conda-forge"


def build_report(rows):
    out = ["| nome | versão | licença | canal |", "|---|---|---|---|"]
    bad_chan, no_lic = [], []
    for name, ver, lic, origin in rows:
        chan = "conda-forge" if is_forge(origin) else (origin or "(vazio)")
        out.append(f"| {name} | {ver} | {lic or '(vazio)'} | {chan} |")
        if not is_forge(origin):
            bad_chan.append(f"{name} {ver} ({chan})")
        if lic.lower() in UNKNOWN:
            no_lic.append(f"{name} {ver}")
    out += ["", f"Total: {len(rows)} pacotes", "", f"## Não conda-forge ({len(bad_chan)})"]
    out += [f"- {x}" for x in bad_chan] or ["- nenhum"]
    out += ["", f"## Sem licença ({len(no_lic)})"]
    out += [f"- {x}" for x in no_lic] or ["- nenhum"]
    return "\n".join(out) + "\n", bad_chan, no_lic


def main(argv):
    if len(argv) != 2:
        print("uso: license_inventory.py SAIDA.md", file=sys.stderr)
        return 2
    prefix = os.environ.get("CONDA_PREFIX")
    if not prefix:
        print("CONDA_PREFIX não definido", file=sys.stderr)
        return 2
    text, bad_chan, no_lic = build_report(collect(prefix))
    Path(argv[1]).write_text(text, encoding="utf-8")
    print(text)
    return 1 if (bad_chan or no_lic) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
