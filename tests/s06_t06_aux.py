# SPDX-License-Identifier: AGPL-3.0-or-later
"""Auxiliar do oráculo F0-S06-T06 (6 casos de divergência). Código de teste; o implementador não edita.
`fazer(pasta, ...)` grava `Casa.ifc` (IFC4 mínimo, vistas = IfcAnnotation DRAWING com GlobalId dado, pranchas = IfcDocumentInformation SHEET,
pset OBIM_Projeto com LadoId e Revisao) e, se pedido, `Casa.obim` real 0.2.0 via `obim_zip` (manifesto com o sha256 do IFC gravado).
`foto(pasta)` = {caminho relativo: sha256} + pastas, para provar que nada foi apagado, criado ou regravado."""
import hashlib
from pathlib import Path

import ifcopenshell
import ifcopenshell.api
import s06_t04_aux as A

LADO = "5b1f6a40-7d0e-4c52-9a43-1c0de5a7f066"
GID = "2xQ0hZ1u8Ek9aBc3DeFgHi"  # GlobalId do IfcProject (22 caracteres)
V = {n: f"{n}0Fq3Zk1D5Pv2wX4yAbC_E"[:22] for n in "123"}  # GlobalIds de vista: V["1"], V["2"], V["3"]
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()  # noqa: E731


def fazer(pasta, *, vistas=("1", "2"), pranchas=("A-01",), pset=True, lado=LADO, rev=2, gid=GID, obim=True, o_lado=None, o_rev=None, o_gid=None,
          o_vistas=None, versao="0.2.0", nome="Casa"):
    """Devolve (ifc, obim). `o_*` = valor do manifesto do `.obim` quando difere do IFC; `o_vistas` = vistas que o `.obim` cita (padrão: as do IFC)."""
    import openbim_app.obim_zip as Z
    from openbim_app.lateral import Lateral
    pasta = Path(pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    f = A.novo_arquivo("IFC4")
    proj = f.by_type("IfcProject")[0]
    proj.GlobalId = gid
    for n in vistas:
        A.annotation(f, f"Planta {n}").GlobalId = V[n]
    for numero in pranchas:
        A.folha(f, numero, f"Prancha {numero}")
    if pset:
        ps = ifcopenshell.api.run("pset.add_pset", f, product=proj, name="OBIM_Projeto")
        ifcopenshell.api.run("pset.edit_pset", f, pset=ps, properties={"LadoId": lado, "Revisao": rev})
    ifc = pasta / f"{nome}.ifc"
    f.write(str(ifc))
    ob = ifc.with_suffix(".obim")
    if obim:
        citadas = vistas if o_vistas is None else o_vistas
        objs = {"vistas": {f"v{n}": {"vista_guid": V[n], "estilo": "padrao"} for n in citadas},
                "pranchas": {f"p{i}": {"identification": x, "formato": "A1"} for i, x in enumerate(pranchas)},
                "viewports": {f"vp{n}": {"prancha": pranchas[0], "vista_guid": V[n], "x": 10.0, "y": 20.0, "escala": 100.0} for n in citadas} if pranchas else {}}
        man = {"formato": "obim-lateral", "versao_formato": versao, "LadoId": o_lado or lado, "Revisao": o_rev or rev, "ifc_nome": ifc.name,
               "ifc_sha256": sha(ifc), "ifc_tamanho": ifc.stat().st_size, "ifc_projeto_globalid": o_gid or gid, "programa_versao": "0.1.0",
               "data": "2026-10-30T00:00:00Z"}
        Z.escrever(ob, Lateral(objs), man)
    return ifc, ob


def mudar_um_byte(ifc):
    """Troca 1 byte do IFC ('Casa' -> 'Caso' no nome do projeto): continua IFC válido e o hash muda."""
    b = Path(ifc).read_bytes()
    assert b.count(b"'Casa'") == 1
    Path(ifc).write_bytes(b.replace(b"'Casa'", b"'Caso'"))


def contar_vistas(ifc):
    return len(A.anotacoes_vista(ifcopenshell.open(str(ifc))))


def foto(pasta):
    pasta = Path(pasta)
    return {str(p.relative_to(pasta)): (sha(p) if p.is_file() else "<pasta>") for p in sorted(pasta.rglob("*"))}
