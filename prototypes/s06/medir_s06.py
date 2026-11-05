# SPDX-License-Identifier: AGPL-3.0-or-later
"""Medicao F0-S06-T10: planta e corte (escalas 1:50 e 1:100) pelo processo auxiliar real.

Uso: medir_s06.py SAIDA_DIR [--ifc caminho.ifc] [--repeticoes 3]
Sem --ifc gera um IFC sintetico residencial (25 x 20 m = 500 m2). Com --ifc usa o pavimento mais baixo numa COPIA
temporaria (o arquivo original nao e alterado). Grava planta_1x50.svg/png, corte_1x50..., medicao.md e lado_a_lado.html.
"""
import argparse
import locale
import os
import platform
import shutil
import statistics
import sys
import tempfile
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "app"))
sys.path.insert(0, str(RAIZ / "geometria"))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import ifcopenshell  # noqa: E402
import ifcopenshell.api  # noqa: E402
import ifcopenshell.guid  # noqa: E402
import ifcopenshell.util.placement  # noqa: E402
import ifcopenshell.util.unit  # noqa: E402

from openbim_app import vistas_ifc  # noqa: E402
from openbim_app.desenho import auxiliar  # noqa: E402
from openbim_app.desenho import corte as C  # noqa: E402
from openbim_app.desenho import estilo, planta as P  # noqa: E402

META_S = 10.0
ESCALAS = ("1:50", "1:100")
PE_DIREITO = 2.8


def _api(nome, f, **kw):
    return ifcopenshell.api.run(nome, f, **kw)


def _novo():
    f = ifcopenshell.api.run("project.create_file", version="IFC4")
    proj = _api("root.create_entity", f, ifc_class="IfcProject", name="Sintetico 500 m2")
    _api("unit.assign_unit", f, length={"is_metric": True, "raw": "METERS"})  # metro (o padrao da API e milimetro)
    _api("context.add_context", f, context_type="Model")
    sitio = _api("root.create_entity", f, ifc_class="IfcSite", name="Terreno")
    pred = _api("root.create_entity", f, ifc_class="IfcBuilding", name="Casa")
    pav = _api("root.create_entity", f, ifc_class="IfcBuildingStorey", name="Terreo")
    pav.Elevation = 0.0
    _api("aggregate.assign_object", f, products=[sitio], relating_object=proj)
    _api("aggregate.assign_object", f, products=[pred], relating_object=sitio)
    _api("aggregate.assign_object", f, products=[pav], relating_object=pred)
    return f, pav


def _caixa(f, cls, nome, x, y, z, dx, dy, dz):
    """Elemento IFC4 com geometria de caixa (canto minimo em x, y, z do mundo)."""
    pt = lambda *c: f.create_entity("IfcCartesianPoint", Coordinates=tuple(float(v) for v in c))  # noqa: E731
    perfil = f.create_entity("IfcRectangleProfileDef", ProfileType="AREA", XDim=dx, YDim=dy,
                             Position=f.create_entity("IfcAxis2Placement2D", Location=f.create_entity("IfcCartesianPoint", Coordinates=(dx / 2, dy / 2))))
    solido = f.create_entity("IfcExtrudedAreaSolid", SweptArea=perfil, Position=f.create_entity("IfcAxis2Placement3D", Location=pt(0, 0, 0)),
                             Depth=dz, ExtrudedDirection=f.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0)))
    forma = f.create_entity("IfcShapeRepresentation", ContextOfItems=f.by_type("IfcGeometricRepresentationContext")[0],
                            RepresentationIdentifier="Body", RepresentationType="SweptSolid", Items=[solido])
    e = _api("root.create_entity", f, ifc_class=cls, name=nome)
    e.ObjectPlacement = f.create_entity("IfcLocalPlacement", RelativePlacement=f.create_entity("IfcAxis2Placement3D", Location=pt(x, y, z)))
    e.Representation = f.create_entity("IfcProductDefinitionShape", Representations=[forma])
    return e


def _vao(f, parede, cls, nome, x, y, z, dx, dy, dz):
    """Abertura que fura a parede + preenchimento (porta ou janela)."""
    o = _caixa(f, "IfcOpeningElement", "Abertura " + nome, x, y, z, dx, dy, dz)
    d = _caixa(f, cls, nome, x, y, z, dx, dy, dz)
    kw = dict(GlobalId=ifcopenshell.guid.new())
    f.create_entity("IfcRelVoidsElement", RelatingBuildingElement=parede, RelatedOpeningElement=o, **kw)
    f.create_entity("IfcRelFillsElement", GlobalId=ifcopenshell.guid.new(), RelatingOpeningElement=o, RelatedBuildingElement=d)


def sintetico():
    """Casa 25 x 20 m, pe-direito 2,8 m, 6 portas, 6 janelas, laje e 20 moveis. Devolve (arquivo, pavimento)."""
    f, pav = _novo()
    h = PE_DIREITO
    paredes = [  # nome, x, y, dx, dy
        ("Ext Sul", 0, 0, 25, 0.2), ("Ext Norte", 0, 19.8, 25, 0.2), ("Ext Oeste", 0, 0.2, 0.2, 19.6), ("Ext Leste", 24.8, 0.2, 0.2, 19.6),
        ("Int 1", 8, 0.2, 0.15, 19.6), ("Int 2", 16, 0.2, 0.15, 19.6), ("Int 3", 0.2, 14, 24.6, 0.15)]
    el = {n: _caixa(f, "IfcWall", n, x, y, 0, dx, dy, h) for n, x, y, dx, dy in paredes}
    cont = list(el.values()) + [_caixa(f, "IfcSlab", "Laje", 0, 0, -0.2, 25, 20, 0.2)]
    for n, x in enumerate((3, 12, 20)):
        _vao(f, el["Ext Sul"], "IfcDoor", f"Porta S{n}", x, 0, 0, 0.9, 0.2, 2.1)
    _vao(f, el["Int 1"], "IfcDoor", "Porta I1", 8, 9.55, 0, 0.15, 0.9, 2.1)
    _vao(f, el["Int 2"], "IfcDoor", "Porta I2", 16, 9.55, 0, 0.15, 0.9, 2.1)
    _vao(f, el["Int 3"], "IfcDoor", "Porta I3", 12, 14, 0, 0.9, 0.15, 2.1)
    for n, x in enumerate((3, 8, 13, 18, 22)):
        _vao(f, el["Ext Norte"], "IfcWindow", f"Janela N{n}", x, 19.8, 1.0, 1.2, 0.2, 1.2)
    _vao(f, el["Ext Leste"], "IfcWindow", "Janela L", 24.8, 9.4, 1.0, 0.2, 1.2, 1.2)
    k = 0
    for y in (3.0, 7.0, 9.8, 17.0):
        for x in (2.0, 5.0, 11.0, 13.5, 19.0, 22.0):
            if k < 20:
                cont.append(_caixa(f, "IfcFurniture", f"Movel {k}", x, y, 0, 0.6, 0.6, 0.9))
                k += 1
    _api("spatial.assign_container", f, products=cont, relating_structure=pav)
    return f, pav


def _contagem(pav):
    els = [e for r in pav.ContainsElements for e in r.RelatedElements]
    return sum(e.is_a("IfcWall") for e in els), sum(e.is_a("IfcFurnishingElement") for e in els)


def _escolher_pavimento(f, escolha):
    """Lista os pavimentos (paredes, moveis) e escolhe: --pavimento NOME/indice, senao o com MAIS paredes."""
    pavs = sorted(f.by_type("IfcBuildingStorey"), key=lambda p: (p.Elevation if p.Elevation is not None else 0.0))
    if not pavs:
        raise SystemExit("IFC sem IfcBuildingStorey")
    for p in pavs:  # so na copia: o desenho exige cota; sem Elevation usa a cota da colocacao
        if p.Elevation is None:
            p.Elevation = float(ifcopenshell.util.placement.get_local_placement(p.ObjectPlacement)[2, 3]) if p.ObjectPlacement else 0.0
    cont = [_contagem(p) for p in pavs]
    for k, (p, (w, m)) in enumerate(zip(pavs, cont)):
        print(f"pavimento {k}: {p.Name!r} Elevation={p.Elevation} paredes={w} moveis={m}")
    if escolha is None:
        k = max(range(len(pavs)), key=lambda i: cont[i][0])
    elif escolha.isdigit() and int(escolha) < len(pavs):
        k = int(escolha)
    else:
        k = next((i for i, p in enumerate(pavs) if p.Name == escolha), None)
        if k is None:
            raise SystemExit(f"pavimento {escolha!r} nao encontrado")
    return pavs[k], [(p.Name, p.Elevation, *c) for p, c in zip(pavs, cont)]


def _envoltorio(f, pav):
    """Envoltorio XY (m) das origens das paredes do pavimento (aproximacao pelas colocacoes) e pe-direito."""
    esc = float(ifcopenshell.util.unit.calculate_unit_scale(f))
    els = [e for r in pav.ContainsElements for e in r.RelatedElements if e.is_a("IfcWall") and e.ObjectPlacement is not None]
    if not els:
        raise SystemExit("pavimento sem paredes com colocacao")
    pts = [ifcopenshell.util.placement.get_local_placement(e.ObjectPlacement)[:3, 3] * esc for e in els]
    xs, ys, zs = [p[0] for p in pts], [p[1] for p in pts], [p[2] for p in pts]
    acima = sorted(p.Elevation for p in f.by_type("IfcBuildingStorey") if p.Elevation is not None and p.Elevation > pav.Elevation)
    pe = (acima[0] - pav.Elevation) * esc if acima else 3.0
    return (min(xs), min(ys), max(xs), max(ys)), min(zs), pe


def _vistas(f, pav, escala):
    """Cria a vista PLANTA e a vista CORTE (plano em Y no centro do envoltorio, olhando +Y). Devolve (gid_planta, gid_corte)."""
    esc = float(ifcopenshell.util.unit.calculate_unit_scale(f))
    u = 1.0 / esc
    (x0, y0, x1, y1), z0, pe = _envoltorio(f, pav)
    nome = escala.replace(":", "x")
    gp = vistas_ifc.criar_vista(f, f"Planta {nome}", "PLANTA", escala=escala, origem=(x0 * u, y0 * u, z0 * u), tamanho=((x1 - x0 + 2) * u, (y1 - y0 + 2) * u, pe * u))
    f.create_entity("IfcRelContainedInSpatialStructure", GlobalId=ifcopenshell.guid.new(), RelatingStructure=pav, RelatedElements=[f.by_guid(gp)],
                    **({"OwnerHistory": f.by_type("IfcOwnerHistory")[0]} if f.schema == "IFC2X3" else {}))
    larg, alt, prof = x1 - x0 + 1.0, pe + 0.5, (y1 - y0) / 2.0 + 1.0
    gc = vistas_ifc.criar_vista(f, f"Corte {nome}", "CORTE", escala=escala, origem=((x0 - 0.5) * u, ((y0 + y1) / 2.0) * u, (z0 - 0.5) * u),
                                tamanho=(larg * u, alt * u, prof * u))
    eixo = f.by_guid(gc).ObjectPlacement.RelativePlacement
    eixo.Axis = f.create_entity("IfcDirection", DirectionRatios=(0.0, -1.0, 0.0))
    eixo.RefDirection = f.create_entity("IfcDirection", DirectionRatios=(1.0, 0.0, 0.0))
    bloco = f.by_guid(gc).Representation.Representations[0].Items[0].TreeRootExpression
    bloco.Position.Location.Coordinates = (0.0, 0.0, -prof * u)  # volume de -profundidade a 0 em Z local (visao = -Z local)
    return gp, gc


def _mem_mb():
    try:
        import resource
        return resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss / 1024.0  # Linux: KB; maximo acumulado dos filhos
    except ImportError:
        return None


def _medir(f, caso, gid, escala, n, limite_s, cats):
    """Devolve (linhas, svg). Estouro ou falha viram linha com `erro` (nao interrompe as demais medicoes)."""
    gerar = P.gerar_planta if caso == "planta" else C.gerar_corte
    linhas, ultimo = [], None
    for i in range(n):
        t0 = time.perf_counter()
        try:
            r = gerar(f, gid, limite_s=limite_s, categorias_ocultas=cats)  # executor padrao: processo auxiliar real
            svg = estilo.aplicar_estilo(r.svg, escala)
        except auxiliar.AuxiliarEstourouTempo as e:
            linhas.append(dict(i=i + 1, t=time.perf_counter() - t0, mem=_mem_mb(), erro=f"ESTOUROU (limite {e.limite_s:g} s, fase {e.fase or '?'})"))
            break
        except Exception as e:  # noqa: BLE001
            linhas.append(dict(i=i + 1, t=time.perf_counter() - t0, mem=_mem_mb(), erro=f"FALHOU ({type(e).__name__}: {str(e)[:150]})"))
            break
        linhas.append(dict(i=i + 1, t=time.perf_counter() - t0, paths=r.n_paths, sel=len(r.selecao.ids), geo=r.tempos.get("geo_s", 0.0), mem=_mem_mb(),
                           tri=getattr(r.selecao, "triangulos", None)))
        ultimo = svg
    return linhas, ultimo


def _png(svg_path, png_path):
    try:
        from PySide6.QtCore import QByteArray, Qt
        from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter
        from PySide6.QtSvg import QSvgRenderer
    except ImportError:
        return False
    app = QGuiApplication.instance() or QGuiApplication(sys.argv[:1])  # noqa: F841
    locale.setlocale(locale.LC_NUMERIC, "C")  # o Qt troca para pt_BR e o IFC copiado ao auxiliar sai com virgula (desenho vazio)
    rend = QSvgRenderer(QByteArray(Path(svg_path).read_bytes()))
    if not rend.isValid():
        return False
    s = rend.defaultSize()
    if s.width() <= 0 or s.height() <= 0:
        return False
    w = 1600
    img = QImage(w, max(1, round(w * s.height() / s.width())), QImage.Format_ARGB32)
    img.fill(QColor("white"))
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    rend.render(p)
    p.end()
    return img.save(str(png_path))


def _tabela(resultados, n, origem, extra):
    L = ["# Medicao F0-S06-T10", "", f"- Modelo: {origem}", f"- Repeticoes por caso: {n}", f"- Sistema: {platform.system()} {platform.release()}, Python {platform.python_version()}",
         "- Tempo total = gerar_* pelo processo auxiliar real (executor padrao) + aplicar_estilo. Memoria = pico maximo acumulado dos processos filhos (getrusage).",
         "- Windows: nao medido"] + [f"- {k}: {v}" for k, v in extra.items()] + ["", "| caso | execucao | tempo total (s) | geo_s | n_paths | elementos selecionados | triangulos | memoria pico filhos (MB) |", "|---|---|---|---|---|---|---|---|"]
    for caso, linhas in resultados.items():
        for r in linhas:
            m = "n/d" if r["mem"] is None else f"{r['mem']:.0f}"
            if "erro" in r:
                L.append(f"| {caso} | {r['i']} | {r['t']:.1f} | - | - | - | - | {m} | {r['erro']}")
            else:
                L.append(f"| {caso} | {r['i']} | {r['t']:.2f} | {r['geo']:.2f} | {r['paths']} | {r['sel']} | {r['tri'] if r['tri'] is not None else 'n/d'} | {m} |")
    L += ["", "| caso | mediana (s) | maximo (s) | meta 10 s |", "|---|---|---|---|"]
    for caso, linhas in resultados.items():
        ok = [r for r in linhas if "erro" not in r]
        if len(ok) < len(linhas):
            L.append(f"| {caso} | - | - | {linhas[-1]['erro']} |")
            continue
        ts = [r["t"] for r in ok]
        L.append(f"| {caso} | {statistics.median(ts):.2f} | {max(ts):.2f} | {'meta 10 s: ATINGIDA' if max(ts) <= META_S else 'meta 10 s: NAO ATINGIDA'} |")
    return "\n".join(L) + "\n"


def _html(saida, origem):
    cel = lambda cam, rot: f'<figure><figcaption>{rot}</figcaption><img src="{cam}.svg" alt="{rot}"></figure>'  # noqa: E731
    corpo = "".join(cel(f"{c}_{e.replace(':', 'x')}", f"{c.capitalize()} {e}") for c in ("planta", "corte") for e in ESCALAS if (saida / f"{c}_{e.replace(':', 'x')}.svg").exists())
    (saida / "lado_a_lado.html").write_text(
        '<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><title>Planta e corte lado a lado</title><style>'
        "body{font-family:sans-serif;margin:16px}.g{display:grid;grid-template-columns:1fr 1fr;gap:16px}"
        "figure{margin:0;border:1px solid #bbb;padding:8px}img{width:100%;height:auto;background:#fff}</style></head><body>"
        f'<h1>Planta e corte, 1:50 e 1:100</h1><p>Modelo: {origem}. Medicao em medicao.md.</p><div class="g">{corpo}</div></body></html>', encoding="utf-8")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("saida")
    ap.add_argument("--ifc")
    ap.add_argument("--repeticoes", type=int, default=3)
    ap.add_argument("--pavimento", help="nome ou indice (ordem de cota); padrao: o com mais paredes")
    ap.add_argument("--limite-s", type=float, default=float(auxiliar.LIMITE_PADRAO_S), help="limite do processo auxiliar por desenho (padrao 180)")
    ap.add_argument("--sem-moveis", action="store_true", help="oculta IfcFurnishingElement (moveis) do desenho")
    a = ap.parse_args(argv)
    saida = Path(a.saida)
    saida.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="medir_s06_"))
    cats = ("IfcFurnishingElement",) if a.sem_moveis else ()
    extra = {"limite do auxiliar": f"{a.limite_s:g} s", "moveis ocultos": "sim" if a.sem_moveis else "nao"}
    try:
        if a.ifc:
            cop = tmp / "copia.ifc"
            shutil.copyfile(a.ifc, cop)  # nunca altera o original
            extra["tamanho do arquivo"] = f"{os.path.getsize(a.ifc) / 1e6:.1f} MB"
            t0 = time.perf_counter()
            f = ifcopenshell.open(str(cop))
            extra["abrir o IFC no processo pai"] = f"{time.perf_counter() - t0:.1f} s"
            pav, lista = _escolher_pavimento(f, a.pavimento)
            origem = f"{Path(a.ifc).name} (pavimento {pav.Name})"
            extra["pavimentos (nome, cota, paredes, moveis)"] = "; ".join(str(x) for x in lista)
        else:
            f, pav = sintetico()
            origem = "sintetico 25 x 20 m (500 m2), 6 portas, 6 janelas, 20 moveis, pe-direito 2,8 m"
        resultados = {}
        for esc in ESCALAS:
            sufixo = esc.replace(":", "x")
            try:
                gp, gc = _vistas(f, pav, esc)
            except (SystemExit, Exception) as e:  # noqa: BLE001
                for caso in ("planta", "corte"):
                    resultados[f"{caso} {esc}"] = [dict(i=1, t=0.0, mem=None, erro=f"FALHOU (vistas: {e})")]
                continue
            for caso, gid in (("planta", gp), ("corte", gc)):
                linhas, svg = _medir(f, caso, gid, esc, a.repeticoes, a.limite_s, cats)
                resultados[f"{caso} {esc}"] = linhas
                if svg is not None:
                    caminho = saida / f"{caso}_{sufixo}.svg"
                    caminho.write_text(svg, encoding="utf-8")
                    if not _png(caminho, saida / f"{caso}_{sufixo}.png"):
                        print(f"aviso: PNG de {caminho.name} nao gerado (so SVG)")
                (saida / "medicao.md").write_text(_tabela(resultados, a.repeticoes, origem, extra), encoding="utf-8")  # parcial a cada caso
        md = _tabela(resultados, a.repeticoes, origem, extra)
        (saida / "medicao.md").write_text(md, encoding="utf-8")
        _html(saida, origem)
        print(md)
        print(f"Saidas em {saida}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
