# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo F0-S06-T07e3b, rodada 2 (reprovação do Argon, itens 1 a 3). Não editar na implementação (marcadores `@AINDA_NAO_T07E3B` já retirados).
CONTRATO (decisões do líder):
1. Pavimento da vista com `Elevation` ausente (None; atributo opcional no IFC4): `planta.gerar_planta` levanta `selecao.SelecaoInvalida` com mensagem em pt-BR simples que cita o pavimento sem cota
   (contém "pavimento" e "cota", sem caixa). Nada de planta vazia; vale antes de `preparar` e do executor.
2. `obim_geometria.desenho._somente_pavimento(svg, guid) -> str`: devolve SEMPRE XML bem formado terminando em `</svg>`; mantém só o grupo `IfcBuildingStorey` de `ifc:guid == guid` (com tudo o que está dentro);
   todo outro grupo `IfcBuildingStorey` sai, inclusive aninhado dentro de outro que também sai; tags `<g .../>` auto-fechadas não desalinham a conta dos fechamentos.
3. Pedido `desenho` SEM `vista["pavimento"]`: `desenho.processar` devolve `{"ok": false, "erro": {"tipo": "ProtocoloInvalido", ...}}` (pelo cliente: `auxiliar.ProtocoloInvalido`); não adivinha o container."""
import xml.etree.ElementTree as ET

import pytest
import s06_t07e_aux as T
from test_s06_t07e_auxiliar_oraculo import _loc, _x, tmp_aux  # noqa: F401  (a fixture `tmp_aux` vem junto)

NS = 'xmlns="http://www.w3.org/2000/svg" xmlns:ifc="http://www.ifcopenshell.org/ns"'


def _filtrar(svg, guid):
    from obim_geometria import desenho as D
    try:
        out = D._somente_pavimento(svg, guid)
    except Exception as e:  # noqa: BLE001  (qualquer quebra é falha do contrato, não outro motivo de xfail)
        raise AssertionError(f"_somente_pavimento quebrou: {e!r}")
    try:
        ET.fromstring(out)
    except ET.ParseError as e:
        raise AssertionError(f"saída não é XML bem formado: {e}")
    assert out.rstrip().endswith("</svg>")
    return out


def _g(guid, miolo="", cls="IfcBuildingStorey"):
    return f'<g class="{cls}" ifc:guid="{guid}">{miolo}</g>'


def test_elevation_ausente_e_recusada_no_pai(tmp_aux):
    import ifcopenshell.guid  # noqa: F401
    from openbim_app.desenho import planta, selecao
    f, d = T.modelo()
    pav0 = f.by_guid(d["vp"]).ContainedInStructure[0].RelatingStructure
    pav0.Elevation = None

    def nao(pedido):
        raise AssertionError("executor chamado: cota ausente devia parar no pai")
    try:
        planta.gerar_planta(f, d["vp"], executor=nao)
    except selecao.SelecaoInvalida as e:
        msg = str(e).lower()
        assert "pavimento" in msg and "cota" in msg, msg
    else:
        raise AssertionError("não levantou SelecaoInvalida")
    assert not list(tmp_aux.glob("obim-desenho-*"))


def test_filtro_grupos_aninhados_remove_pai_e_filho():
    svg = f'<svg {NS}>' + _g("A", '<path d="M0,0 L1,1"/>' + _g("B", '<path d="M2,2 L3,3"/>')) + _g("K", _g("E1", '<path d="M5,5 L6,6"/>', "IfcWall")) + '</svg>'
    out = _filtrar(svg, "K")
    assert 'ifc:guid="K"' in out and 'ifc:guid="E1"' in out and "M5,5 L6,6" in out
    assert 'ifc:guid="A"' not in out and 'ifc:guid="B"' not in out and "M0,0" not in out and "M2,2" not in out


def test_filtro_grupos_aninhados_em_tres_niveis_e_mantido_no_meio():
    svg = f'<svg {NS}>' + _g("A", _g("B", _g("C", '<path d="M7,7 L8,8"/>'))) + _g("K", '<path d="M1,1 L2,2"/>') + _g("Z", _g("Y")) + '</svg>'
    out = _filtrar(svg, "K")
    assert 'ifc:guid="K"' in out and "M1,1 L2,2" in out and not any(f'ifc:guid="{g}"' in out for g in "ABCZY") and "M7,7" not in out


def test_filtro_tag_auto_fechada_nao_desalinha():
    svg = (f'<svg {NS}>' + _g("A", '<g class="projection"/><path d="M9,9 L9,9"/>') + '<g class="IfcBuildingStorey" ifc:guid="Z"/>'
           + _g("K", '<g class="projection"/><path d="M1,1 L2,2"/>' + _g("E1", "", "IfcWall")) + '</svg>')
    out = _filtrar(svg, "K")
    assert 'ifc:guid="K"' in out and "M1,1 L2,2" in out and 'ifc:guid="E1"' in out and out.count('class="projection"') == 1
    assert 'ifc:guid="A"' not in out and 'ifc:guid="Z"' not in out and "M9,9" not in out


def test_filtro_sem_o_guid_pedido_deixa_svg_valido_sem_pavimentos():
    out = _filtrar(f'<svg {NS}>' + _g("A", _g("B")) + '<g class="IfcBuildingStorey" ifc:guid="Z"/>' + '</svg>', "K")
    assert "IfcBuildingStorey" not in out


def test_pedido_sem_pavimento_e_protocolo_invalido(tmp_aux):
    import obim_geometria.desenho as D
    X, L = _x(), _loc()
    f, d = T.modelo()
    vista = {"tipo": "PLANTA", "altura_corte_m": 1.2, "origem_pav": [0.0, 0.0, 0.0], "escala": 1.0}  # sem "pavimento"
    with X.preparar(f, {"op": "desenho", "elementos": T.elementos(f, "P", "M"), "vista": vista}) as p:
        r = D.processar(dict(p.pedido))
        assert r["ok"] is False and r["erro"]["tipo"] == "ProtocoloInvalido", r
        try:
            X.executar(p, executor=L.executar)
        except X.ProtocoloInvalido:
            pass
        else:
            raise AssertionError("cliente não levantou ProtocoloInvalido")
