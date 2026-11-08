# SPDX-License-Identifier: AGPL-3.0-or-later
"""Auxiliar do oráculo F0-S06-T07d (estilo do desenho). Não é de `app/`; implementador não edita. SVGs sintéticos pequenos (caixa conhecida), SVGs reais crus da planta (T07b) e do corte (T07c)
e leitores independentes do SVG estilizado (viewBox, tamanho em mm, regras de CSS, classes dos grupos, pontos)."""
import re
import xml.etree.ElementTree as ET

NS_IFC = "{http://www.ifcopenshell.org/ns}"
NS_SVG = "{http://www.w3.org/2000/svg}"
CAB = '<svg xmlns="http://www.w3.org/2000/svg" xmlns:ifc="http://www.ifcopenshell.org/ns">'
# Caixa conhecida: parede cortada x 1..6, y 2..2.5 (m); projeção x -1..8, y 0..4. Envoltório exato: x -1..8, y 0..4.
PEQUENO = (CAB + '<g class="IfcWall" ifc:name="P" ifc:guid="G1"><path d="M1,2 L6,2 L6,2.5 L1,2.5 L1,2"/></g>'
           '<g class="projection"><path d="M-1,0 L8,0"/><path d="M8,0 L8,4"/></g></svg>')
CAIXA_PEQUENO = (-1.0, 0.0, 8.0, 4.0)
D = re.compile(r'<path d="([^"]*)"')
NUM = re.compile(r"(-?\d+\.?\d*(?:[eE][-+]?\d+)?),(-?\d+\.?\d*(?:[eE][-+]?\d+)?)")


def ds(svg):
    """Lista (em ordem) dos atributos `d` dos caminhos."""
    return D.findall(svg)


def vertices(svg):
    return [(float(a), float(b)) for d in ds(svg) for a, b in NUM.findall(d)]


def caixa(svg):
    """Envoltório (xmin, ymin, xmax, ymax) de todos os vértices dos caminhos."""
    v = vertices(svg)
    xs, ys = [p[0] for p in v], [p[1] for p in v]
    return min(xs), min(ys), max(xs), max(ys)


def viewbox(svg):
    return tuple(float(t) for t in ET.fromstring(svg).get("viewBox").split())


def mm(svg):
    r = ET.fromstring(svg)
    out = []
    for a in ("width", "height"):
        m = re.fullmatch(r"(\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)mm", r.get(a, ""))
        assert m, f"{a}={r.get(a)!r} não é número seguido de mm"
        out.append(float(m.group(1)))
    return tuple(out)


def estilos(svg):
    return [e for e in ET.fromstring(svg).iter() if e.tag in ("style", NS_SVG + "style")]


def regras(svg):
    """{seletor: {propriedade: valor}} do (único) `<style>`; seletores separados por vírgula viram entradas separadas."""
    css = re.sub(r"/\*.*?\*/", "", "".join(e.text or "" for e in estilos(svg)), flags=re.S).replace("<![CDATA[", "").replace("]]>", "")
    out = {}
    for sel, corpo in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
        decl = {}
        for item in corpo.split(";"):
            if ":" in item:
                k, v = item.split(":", 1)
                decl[k.strip()] = v.strip()
        for s in sel.split(","):
            out.setdefault(" ".join(s.split()), {}).update(decl)
    return out


def traco(svg, seletor):
    """Espessura de traço (unidades do viewBox = metros do modelo) da regra `seletor`."""
    v = regras(svg)[seletor]["stroke-width"]
    assert re.fullmatch(r"\d+(?:\.\d+)?(?:[eE][-+]?\d+)?", v), f"stroke-width {v!r} deve ser número sem unidade"
    return float(v)


def luminosidade(cor):
    m = re.fullmatch(r"#([0-9a-fA-F]{2})([0-9a-fA-F]{2})([0-9a-fA-F]{2})", cor)
    assert m, f"cor {cor!r} deve ser #rrggbb"
    return max(int(g, 16) for g in m.groups())


def classes(el):
    return (el.get("class") or "").split()


def grupos_folha(svg):
    """(cortados, projecao): `<g>` com ifc:guid e `<path>` filhos diretos; `<g class=projection>`."""
    r = ET.fromstring(svg)
    cortados = [g for g in r.iter(NS_SVG + "g") if g.get(NS_IFC + "guid") and g.findall(NS_SVG + "path")]
    proj = [g for g in r.iter(NS_SVG + "g") if "projection" in classes(g)]
    return cortados, proj


def ancestrais(svg):
    r = ET.fromstring(svg)
    pai = {c: p for p in r.iter() for c in p}
    return r, pai


def tela_mm(p, svg):
    """Ponto do desenho -> posição em mm no papel (origem no canto superior esquerdo do SVG, y para baixo), pelo viewBox e pelo tamanho em mm; sem transformação na raiz."""
    x0, y0, w, h = viewbox(svg)
    wm, hm = mm(svg)
    return (p[0] - x0) * wm / w, (p[1] - y0) * hm / h


def cru_planta():
    """(SVG cru da planta, GlobalIds) do modelo assimétrico: parede P0 em y_mundo 0..0,25 (x 0..5) e móvel M0_0 ao NORTE dela (y_mundo 2..2,5, x 0,5..1)."""
    import obim_geometria.local as L
    import openbim_app.desenho.planta as P
    import s06_t07b_aux as B
    f, pavs, g = B.modelo("IFC4")
    return P.gerar_planta(f, B.planta(f, pavs[0]), executor=L.executar).svg, g


def cru_corte():
    """(SVG cru do corte, GlobalIds) de uma parede com porta, laje abaixo e móvel atrás do plano."""
    import obim_geometria.local as L
    import openbim_app.desenho.corte as K
    import s06_t07c_aux as C
    f, g = C.modelo("IFC4", vaos=(C.PORTA,))
    return K.gerar_corte(f, C.corte(f), moveis_caixa2d=False, executor=L.executar).svg, g
