# SPDX-License-Identifier: AGPL-3.0-or-later
"""Inventário de licenças do ambiente conda ativo (ADR-009 §7, itens 2 e 3).

Uso: python scripts/license_inventory.py SAIDA.md [--removidos=ARQUIVO] [--informativo]
Lê $CONDA_PREFIX/conda-meta/*.json. Sai com 1 se algum pacote que VAI NO PACOTE não vier do
conda-forge, não tiver licença declarada ou tiver licença fora da lista de permitidas.
--removidos=ARQUIVO (um pacote por linha, nome primeiro; saída de prune_packages.py): esses pacotes
saem da checagem e aparecem como "vai no pacote: não".
--informativo: licença fora da lista só é listada, não reprova (para o ambiente de desenvolvimento, que não é distribuído).
"""
import json
import os
import re
import sys
from pathlib import Path

UNKNOWN = {"", "unknown", "none", "null"}

# Licenças permitidas (ADR-009 §4). Identificadores SPDX; comparação sem diferenciar maiúsculas.
# Não entram: GPL-2.0-only e LGPL-2.0-only sozinhas, licenças proprietárias, "sem licença".
# LGPL-2.1-only (OCCT, geos, libiconv...) é permitida só como biblioteca dinâmica sem modificação (ADR-009 §5.1).
ALLOWED = {x.lower() for x in """
MIT MIT-open-group X11 NCSA ISC 0BSD HPND HPND-sell-variant PostgreSQL TCL blessing curl Zlib zlib-acknowledgement libpng-2.0
BSD-2-Clause BSD-3-Clause BSD-3-Clause-Attribution BSD-3-Clause-Clear BSL-1.0 Apache-2.0 PSF-2.0 Python-2.0 MPL-2.0 OFL-1.1 FTL
IJG JasPer-2.0 SGI-B-2.0 bzip2-1.0.6 OLDAP-2.8
LGPL-2.1-only LGPL-2.1-or-later LGPL-2.0-or-later LGPL-3.0-only LGPL-3.0-or-later
GPL-2.0-or-later GPL-3.0-only GPL-3.0-or-later
LicenseRef-libglvnd LicenseRef-Qhull LicenseRef-Public-Domain LicenseRef-Ubuntu-Font-Licence-Version-1.0
""".split()}
# Licenças aceitas SÓ por exceção nomeada (nunca por metadado de outro pacote).
EXCEPTION_ONLY = {"licenseref-microsoft-redistributable"}
ALLOWED_EXCEPTIONS = {x.lower() for x in "GCC-exception-3.1 LLVM-exception OCCT-exception-1.0 Qt-GPL-exception-1.0".split()}

# Exceções registradas, uma a uma, amarradas à versão (reconferir quando a versão mudar).
# (nome, versão) -> (licença SPDX equivalente, justificativa). Registrar também em docs/state/LOG.md.
EXCEPTIONS = {
    ("tbb-devel", "2023.1.0"): ("Apache-2.0", "metadado vazio; o próprio pacote traz o arquivo de licença Apache-2.0 e sai da mesma receita do tbb (conferido no lote opus 2)"),
    # Runtimes redistribuíveis da Microsoft (decisão do PO, 2026-10-11): a Microsoft permite redistribuir estas DLLs
    # junto de programas; todo programa C++ no Windows as leva. Condições no THIRD_PARTY.md.
    ("ucrt", "10.0.26100.0"): ("LicenseRef-Microsoft-Redistributable", "Universal CRT do Windows SDK 10, redistribuível pelos termos da Microsoft"),
    ("vc14_runtime", "14.51.36247"): ("LicenseRef-Microsoft-Redistributable", "runtime do Visual C++ 2015-2022, redistribuível pelos termos da Microsoft"),
    ("vcomp14", "14.51.36247"): ("LicenseRef-Microsoft-Redistributable", "runtime OpenMP do Visual C++ 2015-2022, redistribuível pelos termos da Microsoft"),
    ("cgal-cpp", "6.2.1"): ("GPL-3.0-or-later AND LGPL-3.0-or-later", "metadado 'GPL3/LGPL3' (não é SPDX); cabeçalhos do CGAL em GPL-3 e LGPL-3 (partes diferentes), compilados dentro do IfcOpenShell; combinação pela seção 13 da AGPL (lote opus 2)"),
}


def expr_ok(expr):
    """True se a expressão SPDX é aceita: alguma alternativa de OR tem todos os itens de AND permitidos."""
    expr = re.sub(r"\s+", " ", expr.strip())
    # Só um par de parênteses externo é lido; parênteses internos reprovam (o pacote vira exceção nomeada).
    if expr.startswith("(") and expr.endswith(")"):
        expr = expr[1:-1].strip()
    if "(" in expr or ")" in expr:
        return False
    for alt in re.split(r"\s+or\s+", expr, flags=re.I):
        atoms = re.split(r"\s+and\s+", alt, flags=re.I)
        if all(_atom_ok(a) for a in atoms):
            return True
    return False


def _atom_ok(atom):
    parts = re.split(r"\s+with\s+", atom.strip(), maxsplit=1, flags=re.I)
    if parts[0].lower() not in ALLOWED:
        return False
    return len(parts) == 1 or parts[1].lower() in ALLOWED_EXCEPTIONS


def collect(prefix):
    rows = []
    for f in sorted((Path(prefix) / "conda-meta").glob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        origin = d.get("url") or d.get("channel") or ""
        name, ver = d.get("name", f.stem), d.get("version", "")
        lic = (d.get("license") or "").strip()
        exc = EXCEPTIONS.get((name, ver))
        rows.append((name, ver, lic, origin, exc))
    return rows


def is_forge(origin):
    return "/conda-forge/" in origin or origin.rstrip("/").endswith("/conda-forge") or origin == "conda-forge"


def build_report(rows, removidos=frozenset()):
    out = ["| nome | versão | licença | canal | vai no pacote |", "|---|---|---|---|---|"]
    bad_chan, no_lic, not_allowed = [], [], []
    for name, ver, lic, origin, exc in rows:
        chan = "conda-forge" if is_forge(origin) else (origin or "(vazio)")
        vai = name not in removidos
        shown = lic or "(vazio)"
        if exc:
            shown += f" → {exc[0]} (exceção registrada)"
        out.append(f"| {name} | {ver} | {shown} | {chan} | {'sim' if vai else 'não (removido na montagem)'} |")
        if not vai:
            continue
        if not is_forge(origin):
            bad_chan.append(f"{name} {ver} ({chan})")
        if lic.lower() in UNKNOWN and not exc:
            no_lic.append(f"{name} {ver}")
        elif not exc and lic.lower() not in UNKNOWN and not expr_ok(lic):
            not_allowed.append(f"{name} {ver}: {lic}")
        elif exc and not (expr_ok(exc[0]) or exc[0].lower() in EXCEPTION_ONLY):
            not_allowed.append(f"{name} {ver}: exceção com licença não permitida ({exc[0]})")
    out += ["", f"Total: {len(rows)} pacotes ({len(removidos & {r[0] for r in rows})} removidos na montagem)", "", f"## Não conda-forge ({len(bad_chan)})"]
    out += [f"- {x}" for x in bad_chan] or ["- nenhum"]
    out += ["", f"## Sem licença ({len(no_lic)})"]
    out += [f"- {x}" for x in no_lic] or ["- nenhum"]
    out += ["", f"## Licença fora da lista de permitidas ({len(not_allowed)})"]
    out += [f"- {x}" for x in not_allowed] or ["- nenhum"]
    out += ["", "## Exceções registradas"] + [f"- {n} {v}: {e[0]}. {e[1]}" for (n, v), e in sorted(EXCEPTIONS.items())]
    return "\n".join(out) + "\n", bad_chan, no_lic, not_allowed


def main(argv):
    for fluxo in (sys.stdout, sys.stderr):  # console do Windows usa cp1252 por padrão
        fluxo.reconfigure(encoding="utf-8", errors="replace")
    args = [a for a in argv[1:] if not a.startswith("--")]
    opts = [a for a in argv[1:] if a.startswith("--")]
    if len(args) != 1:
        print("uso: license_inventory.py SAIDA.md [--removidos=ARQUIVO]", file=sys.stderr)
        return 2
    prefix = os.environ.get("CONDA_PREFIX")
    if not prefix:
        print("CONDA_PREFIX não definido", file=sys.stderr)
        return 2
    removidos = set()
    for o in opts:
        if o.startswith("--removidos="):
            arq = Path(o.split("=", 1)[1])
            removidos = {l.split()[0] for l in arq.read_text(encoding="utf-8").splitlines() if l.strip()}
    text, bad_chan, no_lic, not_allowed = build_report(collect(prefix), removidos)
    Path(args[0]).write_text(text, encoding="utf-8")
    print(text)
    return 1 if (bad_chan or no_lic or (not_allowed and "--informativo" not in opts)) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
