# SPDX-License-Identifier: AGPL-3.0-or-later
"""Prova T07e4 (ADR-004 2C, R3): o processo auxiliar de geometria funciona DENTRO do pacote (AppImage ou pasta instalada no Windows).
Roda com o Python do PACOTE em modo isolado (`-I`; no Windows tambem com `pythonw.exe`), chamado por test_appimage_auxiliar.sh e test_instalador_auxiliar.sh.
Uso: geometria_no_pacote.py RAIZ [--pythonw] [--saida ARQ]
  RAIZ = pasta do pacote (squashfs-root; ou a pasta instalada). Confere: app/obim_geometria/ (processo, caixas, desenho, __init__), LGPL-COMO-TROCAR.md na raiz,
  um filho `spawn` sonda (isolado, Python do pacote, obim_geometria do pacote e nao do PYTHONPATH sujo) e o filho REAL (`obim_geometria.processo.entrada`) faz `caixas` num IFC pequeno.
  --pythonw: exige que o executavel do pai e do filho se chame pythonw (Windows sem janela de texto); sem stdout, por isso --saida grava o resultado (JSON).
Codigo de saida: 0 = tudo certo; 1 = alguma prova reprovou. So biblioteca padrao no topo: o filho `spawn` reimporta este modulo."""
import json
import multiprocessing
import os
import sys
import tempfile

MODULOS = ("__init__.py", "processo.py", "caixas.py", "desenho.py")


def norm(caminho):
    c = os.path.realpath(caminho)  # expande nomes curtos (RUNNER~1) e links
    return os.path.normcase(c[4:] if c.startswith("\\\\?\\") else c)


def dentro(caminho, raiz):
    c, r = norm(caminho), norm(raiz)
    return c == r or c.startswith(r + os.sep)


def e_pythonw(exe):  # OBIM_TESTE_SIMULADO=1 (ensaio em Linux, proibido no Windows pelo .sh) aceita qualquer nome, para exercitar --pythonw
    return os.environ.get("OBIM_TESTE_SIMULADO") == "1" or os.path.basename(exe).lower() == "pythonw.exe"


def sonda(fila):  # alvo do filho 1 (importavel: o filho reimporta este modulo)
    import obim_geometria
    fila.put({"isolado": sys.flags.isolated, "exe": sys.executable, "modulo": obim_geometria.__file__})


def ifc_pequeno(pasta):
    import ifcopenshell
    import ifcopenshell.guid
    f = ifcopenshell.file(schema="IFC4")
    pt = lambda *c: f.create_entity("IfcCartesianPoint", Coordinates=tuple(float(v) for v in c))  # noqa: E731
    ax = f.create_entity("IfcAxis2Placement3D", Location=pt(0, 0, 0))
    ctx = f.create_entity("IfcGeometricRepresentationContext", ContextType="Model", CoordinateSpaceDimension=3, Precision=1e-5, WorldCoordinateSystem=ax)
    perfil = f.create_entity("IfcRectangleProfileDef", ProfileType="AREA", XDim=4.0, YDim=0.25, Position=f.create_entity(
        "IfcAxis2Placement2D", Location=f.create_entity("IfcCartesianPoint", Coordinates=(2.0, 0.125))))
    solido = f.create_entity("IfcExtrudedAreaSolid", SweptArea=perfil, Position=ax, Depth=3.0,
                             ExtrudedDirection=f.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0)))
    forma = f.create_entity("IfcShapeRepresentation", ContextOfItems=ctx, RepresentationIdentifier="Body", RepresentationType="SweptSolid", Items=[solido])
    w = f.create_entity("IfcWall", GlobalId=ifcopenshell.guid.new(), Name="P", Representation=f.create_entity("IfcProductDefinitionShape", Representations=[forma]),
                        ObjectPlacement=f.create_entity("IfcLocalPlacement", RelativePlacement=f.create_entity("IfcAxis2Placement3D", Location=pt(10, 20, 0))))
    caminho = os.path.join(pasta, "pequeno.ifc")
    f.write(caminho)
    return caminho, [[w.id(), w.GlobalId]]


def provar(raiz, pythonw):
    erros, info = [], {}
    geo = os.path.join(raiz, "app", "obim_geometria")
    for m in MODULOS:
        if not os.path.isfile(os.path.join(geo, m)):
            erros.append(f"faltou app/obim_geometria/{m} dentro do pacote")
    if not os.path.isfile(os.path.join(raiz, "LGPL-COMO-TROCAR.md")):
        erros.append("faltou LGPL-COMO-TROCAR.md na raiz do pacote")
    if erros:
        return erros, info
    if not sys.flags.isolated:
        erros.append("o pai nao esta em modo isolado (-I)")
    if pythonw and not e_pythonw(sys.executable):
        erros.append(f"o pai devia ser pythonw.exe e e {sys.executable}")
    if os.name == "nt":  # como o OpenBIM-Studio.pyw: DLLs do pacote no PATH e no carregador
        for sub in ("Library\\bin", "Library\\mingw-w64\\bin", "Library\\usr\\bin", "bin", "Scripts"):
            pasta = os.path.join(raiz, "env", sub)
            if os.path.isdir(pasta):
                os.environ["PATH"] = pasta + os.pathsep + os.environ.get("PATH", "")
                os.add_dll_directory(pasta)
    sys.path.insert(0, os.path.join(raiz, "app"))  # como o AppRun e o OpenBIM-Studio.pyw: o filho spawn herda este sys.path; PYTHONPATH nao conta em -I
    ctx = multiprocessing.get_context("spawn")
    fila = ctx.Queue()
    p = ctx.Process(target=sonda, args=(fila,))
    p.start()
    p.join(90)
    if p.is_alive():
        p.kill()
        erros.append("o filho sonda nao terminou em 90 s")
    elif p.exitcode != 0:
        erros.append(f"o filho sonda caiu com codigo {p.exitcode} (nao achou obim_geometria sob -I?)")
    else:
        try:
            r = fila.get(timeout=10)
        except Exception as e:  # noqa: BLE001 - queue.Empty etc.: vira erro da prova, nao excecao solta
            return erros + [f"o filho sonda saiu bem mas nao devolveu resposta: {e!r}"], info
        info["sonda"] = r
        erros += ["o filho nao esta em modo isolado (-I)"] * (r["isolado"] != 1)
        erros += [f"o filho nao e o Python do pacote: {r['exe']}"] * (not dentro(r["exe"], raiz))
        erros += [f"o filho nao e pythonw: {r['exe']}"] * (pythonw and not e_pythonw(r["exe"]))
        erros += [f"o filho achou obim_geometria fora do pacote: {r['modulo']}"] * (not dentro(r["modulo"], raiz))
    if erros:
        return erros, info
    from obim_geometria import processo
    with tempfile.TemporaryDirectory(prefix="obim-prova-") as pasta:
        arq, elems = ifc_pequeno(pasta)
        rx, tx = ctx.Pipe(duplex=False)
        f = ctx.Process(target=processo.entrada, args=(tx, json.dumps({"protocolo": 1, "op": "caixas", "arquivo": arq, "elementos": elems, "threads": 1})))
        f.start()
        tx.close()
        resposta = None
        while rx.poll(90):
            try:
                msg = json.loads(rx.recv_bytes().decode("utf-8"))
            except (EOFError, OSError):  # pipe fechado ou quebrado (Windows)
                break
            if msg.get("tipo") == "resposta":
                resposta = msg["dados"]
                break
        f.join(10)
        if f.is_alive():
            f.kill()
        if resposta is None:
            erros.append(f"o filho real nao respondeu (codigo de saida {f.exitcode})")
        elif not resposta.get("ok"):
            erros.append(f"o filho real devolveu erro: {resposta.get('erro')}")
        else:
            cx = resposta["caixas_envolventes"].get(str(elems[0][0]))
            info["caixa"] = cx
            esperado = [10.0, 20.0, 0.0, 14.0, 20.25, 3.0]
            if not cx or any(abs(a - b) > 1e-6 for a, b in zip(cx, esperado)):
                erros.append(f"caixa errada: {cx}, esperada {esperado}")
            if resposta.get("falhas_geometria"):
                erros.append(f"falhas_geometria nao vazia: {resposta['falhas_geometria']}")
    return erros, info


def main(argv):
    if not argv or argv[0].startswith("-"):
        print(__doc__)
        return 2
    raiz, pythonw = os.path.abspath(argv[0]), "--pythonw" in argv
    saida = argv[argv.index("--saida") + 1] if "--saida" in argv else None
    try:
        erros, info = provar(raiz, pythonw)
    except Exception:  # noqa: BLE001 - nada de excecao solta: o rastro vai para o resultado e para o log
        import traceback
        erros, info = ["excecao nao tratada na prova:\n" + traceback.format_exc()], {}
    texto = json.dumps({"erros": erros, "info": info}, ensure_ascii=False)
    if saida:
        with open(saida, "w", encoding="utf-8") as fh:
            fh.write(texto)
    if sys.stdout is not None:
        print(texto)
    return 1 if erros else 0


if __name__ == "__main__":
    multiprocessing.freeze_support()
    sys.exit(main(sys.argv[1:]))
