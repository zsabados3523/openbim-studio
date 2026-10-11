# SPDX-License-Identifier: AGPL-3.0-or-later
"""Teste 2 do ADR-005: o pacote do IfcOpenShell traz cabeçalhos e bibliotecas compartilhadas, e o módulo
Python liga nelas (em vez de embutir uma cópia própria, o risco R1)? Funciona no Linux e no Windows.

Uso: python scripts/sonda_ifcopenshell.py [SAIDA.txt]   (no ambiente que tem o ifcopenshell instalado)
Lê só arquivos locais. No Windows lê a tabela de importação do .pyd (PE) em Python puro; no Linux usa `readelf -d`.
"""
import struct
import subprocess
import sys
from pathlib import Path


def pe_imports(path):
    """Nomes das DLLs que o arquivo PE importa (tabela de importação normal)."""
    d = Path(path).read_bytes()
    pe = struct.unpack_from("<I", d, 0x3C)[0]
    if d[pe:pe + 4] != b"PE\0\0":
        return []
    nsec, = struct.unpack_from("<H", d, pe + 6)
    optsz, = struct.unpack_from("<H", d, pe + 20)
    opt = pe + 24
    magic, = struct.unpack_from("<H", d, opt)
    ddir = opt + (112 if magic == 0x20B else 96)
    rva, _ = struct.unpack_from("<II", d, ddir + 8)  # entrada 1 = importação
    secs = [struct.unpack_from("<IIII", d, opt + optsz + 40 * i + 8) for i in range(nsec)]

    def off(r):
        for vsize, va, rawsize, rawptr in secs:
            if va <= r < va + max(vsize, rawsize):
                return r - va + rawptr
        return None

    out, o = [], off(rva) if rva else None
    while o is not None:
        name_rva = struct.unpack_from("<I", d, o + 12)[0]
        if name_rva == 0:
            break
        n = off(name_rva)
        out.append(d[n:d.index(b"\0", n)].decode("ascii", "replace"))
        o += 20
    return out


def needed(path):
    p = str(path)
    if p.lower().endswith((".pyd", ".dll")):
        return pe_imports(p)
    r = subprocess.run(["readelf", "-d", p], capture_output=True, text=True)
    return [l.split("[")[1].rstrip("]") for l in r.stdout.splitlines() if "(NEEDED)" in l]


def main(argv):
    for fluxo in (sys.stdout, sys.stderr):  # console do Windows usa cp1252 por padrão
        fluxo.reconfigure(encoding="utf-8", errors="replace")
    import ifcopenshell
    pkg = Path(ifcopenshell.__file__).parent
    prefix = Path(sys.prefix)
    linhas = [f"ifcopenshell {ifcopenshell.version} em {pkg}", f"prefixo do ambiente: {prefix}"]
    heads = sorted({p.parent for p in prefix.rglob("file.h") if p.parent.name == "ifcparse"})
    linhas.append("cabeçalhos ifcparse: " + (", ".join(str(h) for h in heads) or "NÃO ACHADOS"))
    exts = {".so", ".dll", ".lib", ".a", ".dylib"}
    libs = sorted(p for d in (prefix / "lib", prefix / "Library" / "lib", prefix / "Library" / "bin")
                  if d.is_dir() for p in d.iterdir()
                  if "ifcopenshell" in p.name.lower() or "ifcparse" in p.name.lower() or "ifcgeom" in p.name.lower())
    libs = [p for p in libs if any(s in exts for s in p.suffixes)]
    principais = [p for p in libs if p.name.lower().startswith(("libifcopenshell", "ifcopenshell.", "ifcparse", "ifcgeom"))
                  and "_ifc" not in p.name.lower()]
    linhas.append(f"bibliotecas do IfcOpenShell no ambiente: {len(libs)} arquivos; as principais:")
    linhas += [f"  {p.relative_to(prefix)}  ({p.stat().st_size // 1024} KB)" for p in principais] or ["  (nenhuma principal)"]
    estaticas = [p for p in libs if p.suffix in {".a"} or (p.suffix == ".lib" and not any(q.stem == p.stem and q.suffix == ".dll" for q in libs))]
    linhas.append("só estáticas (.a, ou .lib sem .dll de mesmo nome): " + (", ".join(p.name for p in estaticas) or "nenhuma"))
    mods = sorted(list(pkg.glob("_ifcopenshell_wrapper*.so")) + list(pkg.glob("_ifcopenshell_wrapper*.pyd")))
    ligam = False
    for m in mods:
        n = needed(m)
        usa = [x for x in n if "ifc" in x.lower()]
        ligam = ligam or bool(usa)
        linhas.append(f"módulo {m.name} ({m.stat().st_size // 1024} KB) importa: {', '.join(n) or '(nada)'}")
        linhas.append(f"  liga em bibliotecas ifc* separadas: {'SIM ' + ', '.join(usa) if usa else 'NÃO (provável cópia embutida)'}")
    linhas.append(f"VEREDITO: cabeçalhos={'sim' if heads else 'NÃO'}; bibliotecas compartilhadas={'sim' if any(p.suffix in {'.so', '.dll'} for p in libs) else 'NÃO'}; módulo liga nelas={'sim' if ligam else 'NÃO'}")
    texto = "\n".join(linhas) + "\n"
    print(texto)
    if len(argv) > 1:
        Path(argv[1]).write_text(texto, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
