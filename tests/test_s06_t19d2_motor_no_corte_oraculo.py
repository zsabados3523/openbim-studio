# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo F0-S06-T19d2: `desenho._corte` desenha as peças elegíveis pelo motor lateral (T3). Cartão: docs/state/cards/F0-S06/F0-S06-T19d2-motor-no-corte.md. Não editar nesta tarefa.
CONTRATO (`desenho.processar`, vista CORTE, `pedido["motor_visivel"] = True`; ausente/False = comportamento de hoje, sem chamar o motor, sem `motor_pecas` e sem `motor_s`):
1. Peça ELEGÍVEL = mesma regra da planta: não é porta/janela, sem `HasOpenings`, com representação e geometria; `IfcOpeningElement` nunca. Elegíveis saem do iterator/serializer HLR e são desenhadas pelo motor:
   linhas por `visibilidade.linhas_visiveis_vista(pecas, quadro, *, profundidade)` (UMA chamada com todas as elegíveis, para haver oclusão entre elas; `quadro` = colocação da vista: origem, u, v, w, em metros do mundo;
   `profundidade` = `profundidade_corte` do pedido/vista, senão o `ZLength` do bloco da vista, em metros) e tampas por `visibilidade.secao_plana(verts, tris, quadro)` (uma chamada por peça). Chamar SEMPRE por
   `visibilidade.<nome>(...)` (atributo do módulo), não por nome importado: o teste troca o atributo do módulo para espionar e quebrar. Inelegíveis continuam no HLR e entram no mesmo SVG.
2. Resposta: `motor_pecas` (ids STEP entregues ao motor; contém ao menos as elegíveis que têm linha ou tampa no volume da vista e nenhuma inelegível), `tempos["motor_s"]` (float >= 0, também na queda para o HLR);
   `enviados` e `falhas_geometria` iguais aos do desenho sem a chave (conjuntos), `n_paths` = número de `<path` do SVG.
3. SVG com a estrutura do HLR: mesmo cabeçalho (viewBox, width, height, matrix3), tampa = `<g class="<IfcClasse>" ifc:guid="<guid>"><path d="..."/></g>` (UM grupo por peça, anéis e furos como sub-caminhos `M` do mesmo `d`, fill-rule evenodd),
   linhas = `<path>` dentro de UM `<g class="projection">` (sem `ifc:guid`: o `estilo.aplicar_estilo` põe a classe `cut` em todo grupo-folha com guid). `d` no formato `M x,y L x,y ...` com números decimais (o `aplicar_estilo` valida por regex).
   Coordenadas: x = u + L/2, y = A/2 - v, com (L, A) do viewBox, u e v relativos à origem do quadro.
4. Equivalência com o HLR (sem a chave) na cena sintética (mesa com 4 pernas e tampo, parede com abertura, porta, moldura com furo, oclusor, peças fora do volume): cobertura bilateral de linhas >= 0.99 a 5 mm
   (diagonais coplanares do HLR não contam), tampas por guid com a mesma área e o mesmo desenho (1%), mesmo conjunto de guids de corte. Limite aceito: peça elegível e peça inelegível não se ocultam entre si.
5. Queda para o HLR: exceção em `linhas_visiveis_vista` ou em `secao_plana` (em qualquer chamada) -> o corte sai INTEIRO pelo HLR (SVG idêntico ao sem a chave, `motor_pecas == []`), `ok` True.
6. `fase` (cancelamento/progresso) segue igual: "geometria" antes de "motor"; exceção levantada na `fase` volta como `ok False`, nunca é engolida pela queda para o HLR. `profundidade_corte` menor reduz o desenhado, como no HLR.
7. `corte.gerar_corte(..., motor_visivel=None)`: só repassa ao pedido quando True ou False (None: sem a chave); outro tipo -> TypeError ou ValueError; `Corte.tempos` carrega `motor_s`."""
from __future__ import annotations

import copy
import importlib
import inspect
import pathlib
import re
import xml.etree.ElementTree as ET
from functools import reduce
from types import SimpleNamespace

import numpy as np
import pytest
import s06_t07_aux as X
import s06_t18a_aux as Z
from s05_conteudo_aux import _limpa, exigir  # noqa: F401  (fixture autouse)
from test_s06_t15h_profundidade_corte_oraculo import ExecutorEspiao, _modelo_sintetico_corte
from test_s06_t19b1_visibilidade_oraculo import TOL, _amostra, _caixa, _cobertura, _dist, _junta, _segs
from test_s06_t19b2_visibilidade_hlr_oraculo import _coplanares
from test_s06_t19d1_motor_lateral_oraculo import _mesa, _no_quadro, _svg_hlr

import obim_geometria.desenho as D

PROF_BLOCO = 6.0  # y 0..6 no mundo (bloco da vista)
PROF_CURTA = 1.8  # deixa a MesaB (y >= 2.0) de fora e não corta ao meio nenhuma outra peça (Oclusor y 1,0..1,5)
NS = "{http://www.ifcopenshell.org/ns}"
ELEGIVEIS = ("K1", "MesaA", "MesaB", "Oclusor", "Moldura", "AtrasDaCamera", "AlemDoAlcance")
COM_LINHAS = ("K1", "MesaA", "MesaB", "Oclusor", "Moldura")  # as que o volume da vista enxerga
COM_TAMPA = ("K1", "MesaA", "Moldura")  # as que cruzam o plano de corte (y = 0)


def _moldura():
    """Tubo retangular (x 6,6..7,8, z 0..1,4, y -0,2..0,2) com vão 0,6 x 0,8: malha fechada, uma casca só. A tampa em y = 0 é um anel (área 1,2) com um furo."""
    x0, z0, x1, z1, a, c, b, d, y0, y1 = 6.6, 0.0, 7.8, 1.4, 6.9, 0.3, 7.5, 1.1, -0.2, 0.2
    anel = [(x0, z0), (x1, z0), (x1, z1), (x0, z1)] + [(a, c), (b, c), (b, d), (a, d)]
    v = np.array([(x, y, z) for y in (y0, y1) for x, z in anel], float)  # 0..3 fora, 4..7 vão (y0); 8..11 fora, 12..15 vão (y1)
    cx, cz = (x0 + x1) / 2, (z0 + z1) / 2
    faces = []
    for k in range(4):
        k2 = (k + 1) % 4
        faces += [([k, k2, 8 + k2, 8 + k], "fora"), ([4 + k, 4 + k2, 12 + k2, 12 + k], "vao"), ([k, k2, 4 + k2, 4 + k], (0, -1, 0)), ([8 + k, 8 + k2, 12 + k2, 12 + k], (0, 1, 0))]
    tris = []
    for q, tipo in faces:
        n = np.cross(v[q[1]] - v[q[0]], v[q[2]] - v[q[0]])
        c3 = v[q].mean(axis=0)
        sai = np.array([c3[0] - cx, 0.0, c3[2] - cz]) if tipo == "fora" else -np.array([c3[0] - cx, 0.0, c3[2] - cz]) if tipo == "vao" else np.array(tipo, float)
        q = q if n @ sai > 0 else q[::-1]
        tris += [(q[0], q[1], q[2]), (q[0], q[2], q[3])]
    return v, np.array(tris)


# ---------------------------------------------------------------- cena
def _cena(tmp_path, inelegiveis=True):
    """Corte para +Y a partir de y = 0 (a da T19d1: bloco x -2..8, z -1..3, y 0..6) com moldura e, se `inelegiveis`, parede com abertura e porta."""
    exigir()
    import ifcopenshell
    import ifcopenshell.geom
    import ifcopenshell.guid
    import ifcopenshell.util.placement as placement
    from openbim_app import vistas_ifc

    pecas = [
        ("K1", "IfcBuildingElementProxy", _caixa(0, -0.5, 0, 1, 0.5, 1)),
        ("MesaA", "IfcBuildingElementProxy", _mesa(2.0, 3.2, -0.1, 0.9, -0.05, 0.75)),
        ("MesaB", "IfcBuildingElementProxy", _mesa(5.0, 6.2, 2.0, 3.2, 2.05, 3.0)),
        ("Oclusor", "IfcBuildingElementProxy", _caixa(5.5, 1.0, 0.2, 6.5, 1.5, 0.6)),
        ("Moldura", "IfcBuildingElementProxy", _moldura()),
        ("AtrasDaCamera", "IfcBuildingElementProxy", _caixa(4.0, -2.0, 1.0, 4.5, -1.0, 1.8)),
        ("AlemDoAlcance", "IfcBuildingElementProxy", _caixa(0.0, 7.0, 1.2, 1.0, 8.0, 1.8)),
    ]
    if inelegiveis:
        pecas.append(("Porta", "IfcDoor", _caixa(1.4, -0.1, 0.0, 1.7, 0.1, 1.0)))
    f, pavs = X.estrutura("IFC4", n_pav=1)
    els = {}
    for nome, cls, m in pecas:
        e = X.caixa(f, cls, nome, 0, 0, 0, 1, 1, 1)
        X.conter(f, pavs[0], e)
        Z.densificar(f, e, ([tuple(map(float, p)) for p in m[0]], [tuple(map(int, q)) for q in m[1]]))
        els[nome] = e
    if inelegiveis:  # parede (x -1,8..-0,2, z 0..2,5) com vão 0,6 x 1,0: o plano a corta, tampa com furo (4,0 - 0,6 = 3,4)
        par = X.caixa(f, "IfcWall", "Parede", -1.8, -0.2, 0, 1.6, 0.4, 2.5)
        vao = X.caixa(f, "IfcOpeningElement", "Vao", -1.3, -0.2, 0.5, 0.6, 0.4, 1.0)
        X.conter(f, pavs[0], par)
        f.create_entity("IfcRelVoidsElement", GlobalId=ifcopenshell.guid.new(), RelatingBuildingElement=par, RelatedOpeningElement=vao, **X.kw(f))
        els["Parede"], els["Vao"] = par, vao
    x0, x1, y0, y1, z0, z1 = -2.0, 8.0, 0.0, 6.0, -1.0, 3.0
    gid = vistas_ifc.criar_vista(f, "C", "CORTE", escala="1:50", origem=(x0, y0, z0), tamanho=(x1 - x0, z1 - z0, y1 - y0))
    eixo = f.by_guid(gid).ObjectPlacement.RelativePlacement
    eixo.Axis = f.create_entity("IfcDirection", DirectionRatios=(0.0, -1.0, 0.0))
    eixo.RefDirection = f.create_entity("IfcDirection", DirectionRatios=(1.0, 0.0, 0.0))
    X.deslocar_bloco(f, gid, (0.0, 0.0, -(y1 - y0)))
    arq = str(pathlib.Path(tmp_path) / "corte.ifc")
    f.write(arq)
    ped = {"protocolo": 1, "op": "desenho", "arquivo": arq, "elementos": [[e.id(), e.GlobalId] for e in els.values()], "threads": 1,
           "vista": {"tipo": "CORTE", "guid": gid, "escala": 1.0}}
    m = placement.get_local_placement(f.by_guid(gid).ObjectPlacement)
    Q = SimpleNamespace(origem=np.array(m[:3, 3], float), u=np.array(m[:3, 0], float), v=np.array(m[:3, 1], float), w=np.array(m[:3, 2], float))
    st = ifcopenshell.geom.settings()
    st.set(st.USE_WORLD_COORDS, True)
    malhas = {}
    for nome, e in els.items():
        if nome in ELEGIVEIS:  # a malha como o motor de verdade a entrega (mundo)
            sh = ifcopenshell.geom.create_shape(st, e)
            malhas[nome] = (np.array(sh.geometry.verts, float).reshape(-1, 3), np.array(sh.geometry.faces, np.int64).reshape(-1, 3))
    return SimpleNamespace(ped=ped, Q=Q, malhas=malhas, ids={n: e.id() for n, e in els.items()}, guids={n: e.GlobalId for n, e in els.items()})


# ---------------------------------------------------------------- leitura do SVG e comparações
def _roda(c, fase=None, **extra):
    return D.processar({**copy.deepcopy(c.ped), **copy.deepcopy(extra)}, fase)


def _par(c, **extra):
    ref = _roda(c, **extra)
    r = _roda(c, motor_visivel=True, **extra)
    assert ref["ok"], ref.get("erro")
    assert r["ok"], r.get("erro")
    return ref, r


def _cortes(svg):
    """{guid: geometria da tampa} em (u, v) relativos à origem da vista: os grupos com `ifc:guid` fora do grupo `projection` (fill-rule evenodd por caminho)."""
    import shapely
    import shapely.geometry as sg

    vb = re.search(r'viewBox="0 0 ([-+0-9.eE]+) ([-+0-9.eE]+)"', svg)
    W, H = float(vb.group(1)), float(vb.group(2))
    corpo = re.sub(r'<g class="projection">.*?</g>', "", svg[svg.find("</style>"):], flags=re.S)
    out = {}
    for m in re.finditer(r'<g\b[^>]*\bifc:guid="([^"]+)"[^>]*>(.*?)</g>', corpo, re.S):
        geos = []
        for d in re.findall(r'<path\b[^>]*\bd="([^"]*)"', m.group(2)):
            subs = [[(float(a) - W / 2, H / 2 - float(b)) for a, b in re.findall(r"(-?[\d.]+(?:e[-+]?\d+)?),(-?[\d.]+(?:e[-+]?\d+)?)", s)] for s in d.split("M")[1:]]
            pols = [shapely.make_valid(sg.Polygon(p)) for p in subs if len(p) >= 3]
            if pols:
                geos.append(reduce(lambda a, b: a.symmetric_difference(b), pols))
        if geos:
            out[m.group(1)] = shapely.unary_union(geos)
    return out


def _raiz(svg):
    ET.fromstring(svg)  # bem formado, com os namespaces declarados
    return re.search(r"<svg\b[^>]*>", svg).group(0)  # xmlns, width, height, viewBox


def _confere_linhas(ref, r, malhas_motor, Q, minimo=0.99):
    """Motor x HLR. O HLR desenha diagonais coplanares da triangulação (sem traço no contrato do motor, T19b2): o trecho do HLR que só cai sobre elas não conta."""
    a, b = _segs(_svg_hlr(ref["svg"])[0]), _segs(_svg_hlr(r["svg"])[0])
    assert len(a) and len(b), "sem linhas"
    cop, resto = [], []
    for m in malhas_motor:
        c, rs = _coplanares(_no_quadro(Q, m))
        cop.append(c)
        resto.append(rs)
    cop, resto = np.concatenate(cop), np.concatenate(resto)
    p, w = _amostra(a)
    ficar = ~((_dist(p, cop) <= TOL) & (_dist(p, resto) > TOL))
    cob = float(w[ficar & (_dist(p, b) <= TOL)].sum() / w[ficar].sum())
    assert cob >= minimo, f"linha do HLR faltando no motor ({cob:.4f})"
    assert _cobertura(b, a) >= minimo, f"linha sobrando no motor ({_cobertura(b, a):.4f})"


def _confere_tampas(ref, r):
    cr, cm = _cortes(ref["svg"]), _cortes(r["svg"])
    assert cr, "o HLR de referência não devolveu corte"
    assert set(cm) == set(cr), f"grupos de corte diferentes: faltam {set(cr) - set(cm)}, sobram {set(cm) - set(cr)}"
    for g, ge in cr.items():
        assert ge.area > 0 and abs(cm[g].area - ge.area) <= 0.01 * ge.area, f"área da tampa {g}: {cm[g].area} x HLR {ge.area}"
        assert cm[g].symmetric_difference(ge).area <= 0.01 * ge.area, f"desenho da tampa {g} difere do HLR"


def _modulo():
    return importlib.import_module("obim_geometria.visibilidade")


def _espia(monkeypatch, nome, quebra_na=None):
    """Troca `visibilidade.<nome>` (e a cópia importada em `desenho`, se houver) por um espião que delega; `quebra_na=k` levanta RuntimeError da k-ésima chamada em diante."""
    V = _modulo()
    real = getattr(V, nome)
    chamadas = []

    def espiao(*a, **k):
        chamadas.append((a, k))
        if quebra_na is not None and len(chamadas) >= quebra_na:
            raise RuntimeError(f"falha injetada em {nome}")
        return real(*a, **k)

    monkeypatch.setattr(V, nome, espiao)
    if hasattr(D, nome):
        monkeypatch.setattr(D, nome, espiao)
    return chamadas


def _arg(chamada, i, nome):
    a, k = chamada
    return k[nome] if nome in k else a[i]


# ---------------------------------------------------------------- 1 a 4: resposta, estrutura e equivalência
@pytest.mark.parametrize("inelegiveis", [True, False])
def test_motor_no_corte_bate_com_o_hlr(tmp_path, inelegiveis):
    c = _cena(tmp_path, inelegiveis)
    ref, r = _par(c)
    mp = set(r["motor_pecas"])
    assert {c.ids[n] for n in COM_LINHAS} <= mp <= {c.ids[n] for n in ELEGIVEIS}, "motor_pecas deve ter as elegíveis e só elas"
    assert not mp & {c.ids.get(n) for n in ("Parede", "Vao", "Porta")}
    assert set(r["enviados"]) == set(ref["enviados"]) and set(c.ids.values()) - {c.ids.get("Vao")} <= set(r["enviados"])
    assert r["falhas_geometria"] == ref["falhas_geometria"] == []
    assert isinstance(r["tempos"].get("motor_s"), float) and r["tempos"]["motor_s"] >= 0 and "motor_s" not in ref["tempos"]
    assert r["n_paths"] == len(re.findall(r"<path\b", r["svg"]))
    assert _raiz(r["svg"]) == _raiz(ref["svg"])
    if inelegiveis:  # com peça no HLR o serializer abre o grupo `section` (matrix3); sem nenhuma, o HLR não escreve esse grupo e o motor não precisa recriá-lo
        assert re.search(r'ifc:matrix3="[^"]*"', r["svg"]).group(0) == re.search(r'ifc:matrix3="[^"]*"', ref["svg"]).group(0)
    assert r["svg"].count('<g class="projection">') == 1
    esperado = {c.guids[n] for n in COM_TAMPA} | ({c.guids["Parede"], c.guids["Porta"]} if inelegiveis else set())
    assert set(_cortes(r["svg"])) == set(_cortes(ref["svg"])) == esperado
    _confere_linhas(ref, r, [c.malhas[n] for n in ELEGIVEIS], c.Q)
    _confere_tampas(ref, r)
    cm = _cortes(r["svg"])
    assert abs(cm[c.guids["Moldura"]].area - (1.2 * 1.4 - 0.6 * 0.8)) <= 1e-6 and len(cm[c.guids["Moldura"]].interiors) == 1, "a moldura tem de ter o furo"
    if inelegiveis:
        assert abs(cm[c.guids["Parede"]].area - 3.4) <= 0.01 * 3.4, "a parede (HLR) perdeu o vão"


@pytest.mark.parametrize("inelegiveis", [True, False])
def test_svg_do_motor_e_consumido_pelo_estilo_sem_mudanca(tmp_path, inelegiveis):
    """O consumidor do SVG de corte no app (`estilo.aplicar_estilo`): valida cada `d`, acha o grupo `projection` e marca `cut` nos grupos-folha com guid. Igual ao do HLR."""
    from openbim_app.desenho import estilo

    c = _cena(tmp_path, inelegiveis)
    ref, r = _par(c)
    assert r["motor_pecas"], "o motor tem de ter desenhado algo"

    def le(svg):
        raiz = ET.fromstring(estilo.aplicar_estilo(svg, "1:50"))
        gs = [e for e in raiz.iter() if e.tag.endswith("}g")]
        proj = [e for e in gs if e.get("class") == "projection"]
        assert len(proj) == 1
        n_proj = sum(1 for p in proj[0].iter() if p.tag.endswith("}path"))
        com_guid = [e for e in proj[0].iter() if e.get(NS + "guid")]
        cut = {e.get(NS + "guid") for e in gs if "cut" in (e.get("class") or "").split()}
        return n_proj, com_guid, cut

    n_ref, _g, cut_ref = le(ref["svg"])
    n_r, com_guid, cut_r = le(r["svg"])
    assert not com_guid, "linha do motor dentro de `projection` não pode ter ifc:guid (viraria tampa)"
    assert cut_r == cut_ref and len(cut_r) == (5 if inelegiveis else 3) and n_r > 0 and n_ref > 0
    for g in cut_r:  # a classe IFC do grupo da tampa é a do HLR
        classe = lambda svg: re.search(r'<g\b(?=[^>]*ifc:guid="%s")[^>]*\bclass="([^"]*)"' % re.escape(g), svg).group(1)  # noqa: E731
        assert classe(r["svg"]) == classe(ref["svg"])


# ---------------------------------------------------------------- 4 e 6: o motor é chamado como no contrato
def test_chamadas_ao_motor_quadro_profundidade_e_pecas(monkeypatch, tmp_path):
    c = _cena(tmp_path)
    lin, sec = _espia(monkeypatch, "linhas_visiveis_vista"), _espia(monkeypatch, "secao_plana")
    r = _roda(c, motor_visivel=True)
    assert r["ok"] and len(lin) == 1, "uma chamada de linhas_visiveis_vista com todas as elegíveis (oclusão entre elas)"
    pecas, Q = _arg(lin[0], 0, "pecas"), _arg(lin[0], 1, "quadro")
    assert len(pecas) == len(ELEGIVEIS) and all(len(p[0]) and len(p[1]) for p in pecas), "entregar as elegíveis, e só elas"
    for eixo in ("origem", "u", "v", "w"):
        assert np.allclose(getattr(Q, eixo), getattr(c.Q, eixo), atol=1e-9), f"quadro.{eixo} não é o da colocação da vista"
    assert lin[0][1]["profundidade"] == pytest.approx(PROF_BLOCO), "profundidade = ZLength do bloco da vista (m)"
    assert len(sec) >= len(COM_TAMPA) and all(np.allclose(getattr(_arg(s, 2, "quadro"), "origem"), c.Q.origem) for s in sec)


@pytest.mark.parametrize("onde", ["pedido", "vista"])
def test_profundidade_corte_menor_reduz_o_desenhado(monkeypatch, tmp_path, onde):
    c = _cena(tmp_path)
    if onde == "pedido":
        extra = {"profundidade_corte": PROF_CURTA}
    else:
        extra = {"vista": {**c.ped["vista"], "profundidade_corte": PROF_CURTA}}
    lin = _espia(monkeypatch, "linhas_visiveis_vista")
    ref, r = _par(c, **extra)
    assert len(lin) == 1 and lin[0][1]["profundidade"] == pytest.approx(PROF_CURTA)
    assert c.guids["MesaB"] not in ref["svg"] + r["svg"]
    _confere_linhas(ref, r, [c.malhas[n] for n in ELEGIVEIS], c.Q)
    _confere_tampas(ref, r)
    ref_cheio, r_cheio = _par(c)
    cheio, curto = _segs(_svg_hlr(r_cheio["svg"])[0]), _segs(_svg_hlr(r["svg"])[0])
    pts, pesos = _amostra(cheio)
    assert float(pesos[_dist(pts, curto) > TOL].sum()) > 3.0, "com profundidade menor as linhas da MesaB (alem do alcance) somem"


# ---------------------------------------------------------------- 5: queda para o HLR
@pytest.mark.parametrize("nome, na_chamada", [("linhas_visiveis_vista", 1), ("secao_plana", 1), ("secao_plana", 2)])
def test_excecao_no_motor_cai_inteiro_para_o_hlr(monkeypatch, tmp_path, nome, na_chamada):
    c = _cena(tmp_path)
    ref = _roda(c)
    chamadas = _espia(monkeypatch, nome, quebra_na=na_chamada)
    r = _roda(c, motor_visivel=True)
    assert len(chamadas) >= na_chamada, "o motor não foi tentado (teste vazio): chamar por visibilidade.<nome>"
    assert r["ok"] and r["motor_pecas"] == []
    assert r["svg"] == ref["svg"], "a queda tem de ser inteira: o mesmo SVG do HLR sem a chave"
    assert set(r["enviados"]) == set(ref["enviados"]) and r["falhas_geometria"] == ref["falhas_geometria"]
    assert isinstance(r["tempos"].get("motor_s"), float)


# ---------------------------------------------------------------- 6: fase / cancelamento
def test_ordem_das_fases(tmp_path):
    c = _cena(tmp_path)
    for extra in ({}, {"motor_visivel": True}):
        nomes = []
        assert _roda(c, nomes.append, **extra)["ok"]
        assert "geometria" in nomes and "motor" in nomes and nomes.index("geometria") < nomes.index("motor"), nomes


@pytest.mark.parametrize("onde", ["geometria", "motor"])
def test_excecao_da_fase_nao_e_engolida(tmp_path, onde):
    class Cancelado(Exception):
        pass

    def fase(nome):
        if nome == onde:
            raise Cancelado("cancelado pelo teste")

    c = _cena(tmp_path)
    for extra in ({}, {"motor_visivel": True}):
        r = _roda(c, fase, **extra)
        assert r["ok"] is False and r["erro"]["tipo"] == "Cancelado", (extra, r)


# ---------------------------------------------------------------- 6: nada muda sem a chave
@pytest.mark.parametrize("extra", [{}, {"motor_visivel": False}])
def test_sem_a_chave_nao_toca_no_motor(monkeypatch, tmp_path, extra):
    c = _cena(tmp_path)
    ref = _roda(c)

    def proibido(*a, **k):
        raise AssertionError("o motor não pode ser chamado sem motor_visivel")

    V = _modulo()
    for nome in ("linhas_visiveis_vista", "secao_plana"):
        monkeypatch.setattr(V, nome, proibido)
        if hasattr(D, nome):
            monkeypatch.setattr(D, nome, proibido)
    r = _roda(c, **extra)
    assert r["ok"] and r["svg"] == ref["svg"]
    assert not r.get("motor_pecas") and "motor_s" not in r["tempos"]
    assert set(r["enviados"]) == set(ref["enviados"]) and r["falhas_geometria"] == ref["falhas_geometria"] == []
    assert set(_cortes(r["svg"])) == {c.guids[n] for n in ("K1", "MesaA", "Moldura", "Parede", "Porta")}  # o HLR de hoje, inteiro, com as tampas


# ---------------------------------------------------------------- 7: app (gerar_corte)
def test_gerar_corte_assinatura_e_repasse_da_chave():
    from openbim_app.desenho import corte

    p = inspect.signature(corte.gerar_corte).parameters
    assert "motor_visivel" in p and p["motor_visivel"].default is None and p["motor_visivel"].kind == inspect.Parameter.KEYWORD_ONLY
    f, gid, *_ = _modelo_sintetico_corte("IFC4")
    for valor, esperado in ((None, "ausente"), (True, True), (False, False)):
        esp = ExecutorEspiao()
        corte.gerar_corte(f, gid, motor_visivel=valor, executor=esp)
        assert len(esp.pedidos_desenho) == 1
        ped = esp.pedidos_desenho[0]
        if esperado == "ausente":
            assert "motor_visivel" not in ped
        else:
            assert ped["motor_visivel"] is esperado
    esp = ExecutorEspiao()
    corte.gerar_corte(f, gid, executor=esp)
    assert "motor_visivel" not in esp.pedidos_desenho[0], "padrão: sem a chave"


@pytest.mark.parametrize("invalido", [1, 0, "sim", "", 1.0, [], (True,)])
def test_gerar_corte_motor_visivel_invalido(invalido):
    from openbim_app.desenho import corte

    f, gid, *_ = _modelo_sintetico_corte("IFC4")
    assert "motor_visivel" in inspect.signature(corte.gerar_corte).parameters
    esp = ExecutorEspiao()
    with pytest.raises((TypeError, ValueError)):
        corte.gerar_corte(f, gid, motor_visivel=invalido, executor=esp)
    assert not esp.pedidos_desenho, "validar antes de pedir o desenho"


def test_gerar_corte_com_motor_traz_motor_s_e_o_mesmo_desenho():
    from openbim_app.desenho import corte

    f, gid, p1, _p2, _p3 = _modelo_sintetico_corte("IFC4", prof_original=20.0)
    c0 = corte.gerar_corte(f, gid, profundidade_corte=3.0, executor=ExecutorEspiao())
    c1 = corte.gerar_corte(f, gid, profundidade_corte=3.0, motor_visivel=True, executor=ExecutorEspiao())
    assert "motor_s" not in c0.tempos
    assert isinstance(c1.tempos.get("motor_s"), float) and c1.tempos["motor_s"] >= 0
    assert p1.GlobalId in c1.svg  # a Parede1 cruza o plano de corte: tampa
    assert set(_cortes(c1.svg)) == set(_cortes(c0.svg)) and c1.caixas == c0.caixas
