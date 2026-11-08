# SPDX-License-Identifier: AGPL-3.0-or-later
"""Reforço do oráculo F0-S06-T15c: processo de desenho, cota Z e modelo sem repetição."""
from __future__ import annotations

import sys
from pathlib import Path

import s06_t07_aux as X
from s05_conteudo_aux import _limpa, exigir  # noqa: F401 (fixture autouse e guarda)

RAIZ = Path(__file__).resolve().parent.parent
GEOMETRIA = RAIZ / "geometria"
if str(GEOMETRIA) not in sys.path:
    sys.path.insert(0, str(GEOMETRIA))

import obim_geometria.local as local
from openbim_app.desenho import auxiliar, planta


def _obter_em_cache(p) -> tuple[int, ...]:
    """Obtém a tupla de step IDs resolvidos via cache 2D de p.em_cache ou retorno correspondente."""
    em_cache = getattr(p, "em_cache", None)
    if em_cache is None and isinstance(p, dict):
        em_cache = p.get("em_cache")
    assert em_cache is not None, "Planta (ou retorno correspondente) deve expor em_cache"
    assert isinstance(em_cache, (tuple, list)), f"em_cache deve ser tupla ou lista, obtido: {type(em_cache)}"
    assert all(isinstance(x, int) for x in em_cache), f"IDs em em_cache devem ser inteiros: {em_cache}"
    return tuple(em_cache)


def _modelo_sintetico_t15c(schema: str = "IFC4", posicoes: list[tuple[float, float]] | None = None):
    """Modelo sintético com 1 parede e 5 pilares com mesma IfcShapeRepresentation."""
    exigir()
    if posicoes is None:
        posicoes = [(1.0, 1.0), (3.0, 1.0), (5.0, 1.0), (1.0, 3.0), (3.0, 3.0)]

    f, pavs = X.estrutura(schema)
    pav = pavs[0]
    parede = X.caixa(f, "IfcWall", "parede", 0.0, 0.0, 0.0, 5.0, 0.2, 3.0)
    pilar0 = X.caixa(f, "IfcColumn", "pilar_0", posicoes[0][0], posicoes[0][1], 0.0, 0.4, 0.4, 3.0)
    forma = pilar0.Representation.Representations[0]

    pilares = [pilar0]
    for i, (px, py) in enumerate(posicoes[1:], start=1):
        c = X.elemento(f, "IfcColumn", f"pilar_{i}")
        c.ObjectPlacement = f.create_entity(
            "IfcLocalPlacement", RelativePlacement=f.create_entity("IfcAxis2Placement3D", Location=X._pt(f, px, py, 0.0))
        )
        c.Representation = f.create_entity("IfcProductDefinitionShape", Representations=[forma])
        pilares.append(c)

    X.conter(f, pav, parede, *pilares)
    gid = X.vista(f, "PLANTA", pav, nome=f"V_T15c_{schema}")
    return f, gid, pav, parede, pilares, posicoes


def test_desenho_processar_respeita_cache_tipo(monkeypatch):
    """Contrato direto de obim_geometria.desenho.processar: réplicas em cache pulam motor 3D."""
    import ifcopenshell.geom
    f, _gid, pav, parede, pilares, _pos = _modelo_sintetico_t15c()

    vista = {"tipo": "PLANTA", "altura_corte_m": 1.2, "origem_pav": [0.0, 0.0, 0.0], "escala": 1.0, "pavimento": pav.GlobalId}
    elems = [[parede.id(), parede.GlobalId]] + [[c.id(), c.GlobalId] for c in pilares]

    includes_capturados = []
    real_iterator = ifcopenshell.geom.iterator

    def espia_iterator(*args, **kwargs):
        inc = kwargs.get("include") or (args[3] if len(args) > 3 else None)
        includes_capturados.append([e.id() for e in inc] if inc else [])
        return real_iterator(*args, **kwargs)

    monkeypatch.setattr(ifcopenshell.geom, "iterator", espia_iterator)

    # 1. Com cache_tipo=True: réplicas não vão ao iterator 3D
    with auxiliar.preparar(f, {"op": "desenho", "protocolo": 1, "elementos": elems, "vista": vista, "cache_tipo": True}) as p:
        res = local.executar(p.pedido)

    assert res["ok"] is True
    assert isinstance(res.get("em_cache"), list), f"res['em_cache'] deve ser lista, obtido: {type(res.get('em_cache'))}"
    assert len(res["em_cache"]) == 4
    assert pilares[0].id() not in res["em_cache"]
    assert set(res["em_cache"]) == {c.id() for c in pilares[1:]}
    assert set(res["enviados"]) == {e[0] for e in elems}
    assert res["falhas_geometria"] == []
    assert len(includes_capturados) == 1
    for replica in pilares[1:]:
        assert replica.id() not in includes_capturados[0], f"Réplica {replica.id()} não deve ir ao motor 3D"
    assert pilares[0].id() in includes_capturados[0], "Primeira instância deve ir ao motor 3D"
    assert parede.id() in includes_capturados[0], "Parede deve ir ao motor 3D"

    # 2. Com cache_tipo=False: caixas/em_cache vazios, todas as instâncias vão ao motor 3D
    includes_capturados.clear()
    with auxiliar.preparar(f, {"op": "desenho", "protocolo": 1, "elementos": elems, "vista": vista, "cache_tipo": False}) as p:
        res_falso = local.executar(p.pedido)

    assert res_falso["ok"] is True
    assert res_falso.get("em_cache") == []
    assert set(res_falso["enviados"]) == {e[0] for e in elems}
    assert len(includes_capturados) == 1
    for c in pilares:
        assert c.id() in includes_capturados[0], "Com cache desativado, todos os pilares vão ao motor 3D"


def test_cota_z_diferente_nao_compartilha_cache():
    """Elementos com mesma representação mas cotas Z relativas diferentes não podem compartilhar cache."""
    exigir()
    f, pavs = X.estrutura("IFC4")
    pav = pavs[0]

    pilar0 = X.caixa(f, "IfcColumn", "pilar_base", 1.0, 1.0, 0.0, 0.4, 0.4, 3.0)
    forma = pilar0.Representation.Representations[0]

    pilar1 = X.elemento(f, "IfcColumn", "pilar_z_dif")
    pilar1.ObjectPlacement = f.create_entity(
        "IfcLocalPlacement", RelativePlacement=f.create_entity("IfcAxis2Placement3D", Location=X._pt(f, 3.0, 1.0, 0.8))
    )
    pilar1.Representation = f.create_entity("IfcProductDefinitionShape", Representations=[forma])

    X.conter(f, pav, pilar0, pilar1)
    gid = X.vista(f, "PLANTA", pav, nome="V_CotasZ")

    p = planta.gerar_planta(f, gid, cache_tipo=True, executor=local.executar)
    em_cache = _obter_em_cache(p)
    assert pilar1.id() not in em_cache, f"Pilar com cota Z diferente não pode ser resolvido via cache: {em_cache}"


def test_sem_repeticao_cache_vazio():
    """Modelo com parede e apenas 1 pilar (sem repetição): em_cache deve ser vazio."""
    exigir()
    f, pavs = X.estrutura("IFC4")
    pav = pavs[0]
    parede = X.caixa(f, "IfcWall", "parede", 0.0, 0.0, 0.0, 5.0, 0.2, 3.0)
    col = X.caixa(f, "IfcColumn", "col", 1.0, 1.0, 0.0, 0.4, 0.4, 3.0)
    X.conter(f, pav, parede, col)
    gid = X.vista(f, "PLANTA", pav, nome="V_Unico")

    p = planta.gerar_planta(f, gid, cache_tipo=True, executor=local.executar)
    assert _obter_em_cache(p) == ()
    assert parede.id() in p.selecao.ids
    assert col.id() in p.selecao.ids


def test_rotacao_3d_inclinada_vai_para_include_elems(monkeypatch):
    """Pilar com eixo Z inclinado não satisfaz pure_z, não entra em cache e vai ao motor 3D."""
    import ifcopenshell.geom
    exigir()
    f, pavs = X.estrutura("IFC4")
    pav = pavs[0]

    pilar0 = X.caixa(f, "IfcColumn", "pilar_base", 1.0, 1.0, 0.0, 0.4, 0.4, 3.0)
    forma = pilar0.Representation.Representations[0]

    pilar_inclinado = X.elemento(f, "IfcColumn", "pilar_inclinado")
    dir_z = f.create_entity("IfcDirection", DirectionRatios=(0.0, 0.6, 0.8))
    dir_x = f.create_entity("IfcDirection", DirectionRatios=(1.0, 0.0, 0.0))
    axis = f.create_entity("IfcAxis2Placement3D", Location=X._pt(f, 3.0, 1.0, 0.0), Axis=dir_z, RefDirection=dir_x)
    pilar_inclinado.ObjectPlacement = f.create_entity("IfcLocalPlacement", RelativePlacement=axis)
    pilar_inclinado.Representation = f.create_entity("IfcProductDefinitionShape", Representations=[forma])

    X.conter(f, pav, pilar0, pilar_inclinado)
    gid = X.vista(f, "PLANTA", pav, nome="V_Inclinado")
    vista = {"tipo": "PLANTA", "altura_corte_m": 1.2, "origem_pav": [0.0, 0.0, 0.0], "escala": 1.0, "pavimento": pav.GlobalId}
    elems = [[pilar0.id(), pilar0.GlobalId], [pilar_inclinado.id(), pilar_inclinado.GlobalId]]

    includes_capturados = []
    real_iterator = ifcopenshell.geom.iterator

    def espia_iterator(*args, **kwargs):
        inc = kwargs.get("include") or (args[3] if len(args) > 3 else None)
        includes_capturados.append([e.id() for e in inc] if inc else [])
        return real_iterator(*args, **kwargs)

    monkeypatch.setattr(ifcopenshell.geom, "iterator", espia_iterator)

    with auxiliar.preparar(f, {"op": "desenho", "protocolo": 1, "elementos": elems, "vista": vista, "cache_tipo": True}) as p:
        res = local.executar(p.pedido)

    assert res["ok"] is True
    assert pilar_inclinado.id() not in res.get("em_cache", [])
    assert len(includes_capturados) == 1
    assert pilar_inclinado.id() in includes_capturados[0], "Pilar inclinado deve ir ao motor 3D (include_elems)"


def test_transladar_d_comando_arco_a():
    """_transladar_d em comando de arco A preserva raios e flags, transladando apenas o ponto final."""
    from obim_geometria.desenho import _transladar_d

    d = "M 10 20 A 5.5 3.2 45 0 1 30 40 Z"
    dx, dy = 5.0, 10.0
    res = _transladar_d(d, dx, dy)

    tokens = res.replace(",", " ").split()
    assert tokens[0] == "M"
    assert tokens[1] == "15.0000"
    assert tokens[2] == "10.0000"

    idx_a = tokens.index("A")
    assert tokens[idx_a + 1] == "5.5", "rx deve ser preservado intacto"
    assert tokens[idx_a + 2] == "3.2", "ry deve ser preservado intacto"
    assert tokens[idx_a + 3] == "45", "rotação do arco deve ser preservada intacta"
    assert tokens[idx_a + 4] == "0", "large-arc-flag deve ser preservado intacto"
    assert tokens[idx_a + 5] == "1", "sweep-flag deve ser preservado intacto"
    assert tokens[idx_a + 6] == "35.0000", "coordenada x final deve ser transladada (x + dx)"
    assert tokens[idx_a + 7] == "30.0000", "coordenada y final deve ser transladada (y - dy)"
    assert tokens[-1] == "Z", "comando Z final deve ser preservado"


def test_clonar_path_preserva_classes():
    """_clonar_path preserva classes (class='cut', class='boundary') e outros atributos da tag."""
    from obim_geometria.desenho import _clonar_path

    tag_cut = '<path class="cut" d="M1,-1 L2,-2" fill-rule="evenodd"/>'
    res_cut = _clonar_path(tag_cut, 1.0, 2.0)
    assert 'class="cut"' in res_cut
    assert 'fill-rule="evenodd"' in res_cut
    assert '2.0000,-3.0000' in res_cut
    assert '3.0000,-4.0000' in res_cut

    tag_boundary = '<path class="boundary" d="M 0 0 A 10 20 0 0 1 5 15 Z"/>'
    res_boundary = _clonar_path(tag_boundary, 2.0, 3.0)
    assert 'class="boundary"' in res_boundary
    assert "10" in res_boundary and "20" in res_boundary
    assert '7.0000,12.0000' in res_boundary

    # Suporte a espacos opcionais ao redor de =
    tag_espacos = '<path d = "M1,1 L2,2" class="boundary"/>'
    res_espacos = _clonar_path(tag_espacos, 1.0, 1.0)
    assert 'class="boundary"' in res_espacos
    assert '2.0000,0.0000' in res_espacos


def test_extrair_caminhos_grupo_autofechado_nao_rouba_caminho():
    """Grupo de elemento autofechado (<g ... />) não pode capturar caminhos de elementos subsequentes."""
    from obim_geometria.desenho import _extrair_caminhos

    svg = """<svg xmlns="http://www.w3.org/2000/svg">
  <g class="IfcColumn" ifc:guid="GUID_VAZIO" />
  <g class="IfcWall" ifc:guid="GUID_COM_CORTE">
     <path class="cut" d="M0,0 L10,0 L10,-10 L0,-10 Z"/>
  </g>
</svg>"""
    caminhos_vazio = _extrair_caminhos(svg, "GUID_VAZIO")
    assert caminhos_vazio == [], f"Grupo autofechado deve retornar [], obtido: {caminhos_vazio}"

    caminhos_parede = _extrair_caminhos(svg, "GUID_COM_CORTE")
    assert len(caminhos_parede) == 1
    assert 'class="cut"' in caminhos_parede[0]


def test_falha_primaria_replica_vai_para_falhas_geometria(monkeypatch):
    """Falha de geometria na primaria faz todas as replicas tambem falharem (em falhas_geometria, fora de enviados)."""
    import ifcopenshell.geom
    from obim_geometria import desenho

    f, _gid, pav, _parede, pilares, _pos = _modelo_sintetico_t15c()
    vista = {"tipo": "PLANTA", "altura_corte_m": 1.2, "origem_pav": [0.0, 0.0, 0.0], "escala": 1.0, "pavimento": pav.GlobalId}
    elems = [[c.id(), c.GlobalId] for c in pilares]

    real_iterator = ifcopenshell.geom.iterator

    class OmitirPrimariaIterator:
        def __init__(self, *args, **kwargs):
            self.it = real_iterator(*args, **kwargs)
            self._current = None

        def initialize(self):
            ok = self.it.initialize()
            if ok:
                self._advance()
            return self._current is not None

        def _advance(self):
            while True:
                sh = self.it.get()
                if sh.id != pilares[0].id():
                    self._current = sh
                    break
                if not self.it.next():
                    self._current = None
                    break

        def get(self):
            return self._current

        def next(self):
            if not self.it.next():
                self._current = None
                return False
            self._advance()
            return self._current is not None

    monkeypatch.setattr(ifcopenshell.geom, "iterator", OmitirPrimariaIterator)

    with auxiliar.preparar(f, {"op": "desenho", "protocolo": 1, "elementos": elems, "vista": vista, "cache_tipo": True}) as p:
        res = desenho.processar(p.pedido)

    assert res["ok"] is True
    assert res["enviados"] == []
    assert res["em_cache"] == []
    assert set(res["falhas_geometria"]) == {c.id() for c in pilares}


def test_primaria_sem_linhas_de_corte_processa_replica():
    """Primaria com geometria 3D mas sem corte nao entra em em_cache, mas replica entra em enviados via replicas_sem_linhas."""
    from obim_geometria import desenho

    f, _gid, pav, _parede, pilares, _pos = _modelo_sintetico_t15c(posicoes=[(1.0, 1.0), (3.0, 1.0)])
    # Desloca ambos os pilares para cota Z bem abaixo do corte
    for col in pilares:
        col.ObjectPlacement.RelativePlacement.Location.Coordinates = (
            float(col.ObjectPlacement.RelativePlacement.Location.Coordinates[0]),
            float(col.ObjectPlacement.RelativePlacement.Location.Coordinates[1]),
            -10.0,
        )

    vista = {"tipo": "PLANTA", "altura_corte_m": 1.2, "origem_pav": [0.0, 0.0, 0.0], "escala": 1.0, "pavimento": pav.GlobalId}
    elems = [[c.id(), c.GlobalId] for c in pilares]

    with auxiliar.preparar(f, {"op": "desenho", "protocolo": 1, "elementos": elems, "vista": vista, "cache_tipo": True}) as p:
        res = desenho.processar(p.pedido)

    assert res["ok"] is True
    assert res["em_cache"] == []
    assert set(res["enviados"]) == {c.id() for c in pilares}
    assert res["falhas_geometria"] == []


