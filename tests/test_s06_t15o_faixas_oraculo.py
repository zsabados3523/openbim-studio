# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo F0-S06-T15o (parte a): módulo puro `geometria/obim_geometria/faixas.py`. Ref: docs/state/cards/F0-S06/F0-S06-T15o-faixas.md.
Contrato do módulo (sem ifcopenshell, sem processo, sem Qt; a parte b testa o corte inteiro):
- `FaixasInvalidas(ValueError)`.
- Item = `(id:int, guid:str, u0:float, u1:float)`: intervalo do elemento na horizontal da tela (u, em metros a partir da câmera, antes de somar TX do SVG).
- `limites(itens, n, *, so_primeira=()) -> list[(a|None, b|None)]`: faixas contíguas e crescentes da esquerda para a direita, 1 <= len <= min(n, nº de centros distintos);
  a primeira começa em None e a última termina em None (abertas); as bordas são escolhidas pelos CENTROS dos itens (quantis), então nenhuma faixa nasce sem dono.
  Os ids em `so_primeira` (móveis desenhados como caixa 2D, fora do HLR) não contam nos quantis. Sem nenhum centro: [(None, None)].
- Dono de um item = a faixa com a <= centro < b (None = infinito). Dono único, sempre.
- `dividir(itens, n, *, so_primeira=()) -> list[list[[id, guid]]]`, uma lista por faixa de `limites`: o item entra em TODA faixa que o intervalo [u0, u1] encosta
  (conjunto fechado, tolerância 1e-6): é o que mantém a oclusão certa, quem cobre outro numa faixa vizinha vem junto. `so_primeira` entra só na faixa 0.
  Ordem de entrada preservada; itens vazios -> [].
- `unir(svgs) -> str`: SVGs dos filhos (já recortados e só com os grupos de corte dos donos), da esquerda para a direita. Mantém o cabeçalho do primeiro, UM
  `<g class="projection">` com os caminhos de todos (na ordem), todos os grupos `product-` e as caixas 2D. [] ou `<svg ...>` de raiz diferente (viewBox) -> FaixasInvalidas; um só = ele mesmo."""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET

import pytest
from s06_t15o_aux import faixas

ITENS8 = [(10 + k, f"G{k}", k + 0.1, k + 0.9) for k in range(8)]  # centros 0,5 .. 7,5, sem encostar


def _dono(lims, c):
    return [k for k, (a, b) in enumerate(lims) if (a is None or c >= a) and (b is None or c < b)]


def test_limites_contiguos_abertos_e_balanceados():
    F = faixas()
    lims = F.limites(ITENS8, 4)
    assert len(lims) == 4 and lims[0][0] is None and lims[-1][1] is None
    assert all(lims[k][1] == lims[k + 1][0] and lims[k][1] is not None for k in range(3))
    assert all(lims[k][0] < lims[k][1] for k in range(1, 3))
    donos = [_dono(lims, (u0 + u1) / 2) for _, _, u0, u1 in ITENS8]
    assert all(len(d) == 1 for d in donos)
    assert [sum(1 for d in donos if d[0] == k) for k in range(4)] == [2, 2, 2, 2]


def test_dividir_particao_com_halo_para_quem_cruza():
    F = faixas()
    itens = ITENS8 + [(99, "LONGO", -1.0, 9.0), (98, "CRUZA", 1.5, 5.5)]
    lims, fx = F.limites(itens, 4), F.dividir(itens, 4)
    assert len(fx) == len(lims) and all(fx) and all(isinstance(e, (list, tuple)) and len(e) == 2 for f_ in fx for e in f_)
    for k, (a, b) in enumerate(lims):
        esperado = [(i, g) for i, g, u0, u1 in itens if (b is None or u0 <= b + 1e-6) and (a is None or u1 >= a - 1e-6)]
        assert [tuple(e) for e in fx[k]] == esperado, f"faixa {k}: elementos que encostam nela, na ordem de entrada"
    assert all((99, "LONGO") in [tuple(e) for e in f_] for f_ in fx)  # atravessa todas
    assert sum((98, "CRUZA") in [tuple(e) for e in f_] for f_ in fx) >= 2  # cruza ao menos uma borda
    assert {tuple(e) for f_ in fx for e in f_} == {(i, g) for i, g, *_ in itens}  # nada se perde


def test_casos_de_borda_n_um_n_grande_vazio_e_centros_iguais():
    F = faixas()
    assert [[tuple(e) for e in f_] for f_ in F.dividir(ITENS8, 1)] == [[(i, g) for i, g, *_ in ITENS8]]
    assert F.limites(ITENS8, 1) == [(None, None)]
    fx = F.dividir(ITENS8[:3], 50)  # n maior que os elementos: no máximo 3 faixas, nenhuma vazia
    assert 1 <= len(fx) <= 3 and all(fx) and {tuple(e) for f_ in fx for e in f_} == {(i, g) for i, g, *_ in ITENS8[:3]}
    assert F.dividir([], 4) == []
    iguais = [(1, "A", 2.0, 3.0), (2, "B", 2.0, 3.0), (3, "C", 2.2, 2.8)]  # mesmo centro: uma faixa só
    assert len(F.dividir(iguais, 4)) == 1 and len(F.dividir(iguais, 4)[0]) == 3


def test_so_primeira_vai_so_na_faixa_zero_e_nao_cria_faixa():
    F = faixas()
    itens = ITENS8 + [(77, "MOVEL", 6.0, 7.0)]
    fx = F.dividir(itens, 4, so_primeira=[77])
    assert len(fx) == len(F.limites(itens, 4, so_primeira=[77])) == 4
    assert [k for k, f_ in enumerate(fx) if (77, "MOVEL") in [tuple(e) for e in f_]] == [0]
    assert F.limites(itens, 4, so_primeira=[77]) == F.limites(ITENS8, 4)  # o móvel não mexe nas bordas
    so_movel = [(1, "M", 0.0, 1.0), (2, "N", 5.0, 6.0)]
    fx2 = F.dividir(so_movel, 4, so_primeira=[1, 2])
    assert len(fx2) == 1 and len(fx2[0]) == 2


@pytest.mark.parametrize("n", [0, -1, True, 2.0, "4", None])
def test_n_invalido_e_recusado(n):
    F = faixas()
    assert issubclass(F.FaixasInvalidas, ValueError)
    with pytest.raises(F.FaixasInvalidas):
        F.dividir(ITENS8, n)
    with pytest.raises(F.FaixasInvalidas):
        F.limites(ITENS8, n)


def _svg(paths, grupos, vb="0 0 7 4.5", extra=""):
    gs = "".join(f'<g id="product-{g}-body" class="IfcWall" ifc:name="{g}" ifc:guid="{g}" ><path d="M0,0 L1,1"/></g>\n' for g in grupos)
    ps = "\n".join(f'<path d="{d}"/>' for d in paths)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:ifc="http://www.ifcopenshell.org/ns" width="7mm" viewBox="{vb}">\n<style>.cut path {{ fill: #444; }}</style>\n'
            f'<g ifc:name="C" class="section" ifc:matrix3="[[1,0,3.5],[0,1,2.25],[0,0,1]]">\n{gs}<g class="projection">\n{ps}\n</g>\n</g>\n{extra}</svg>')


def test_unir_junta_projecao_e_grupos_sem_duplicar_cabecalho():
    F = faixas()
    a = _svg(["M1,1 L2,1", "M2,1 L2,2"], ["AAA"])
    b = _svg(["M2,2 L3,2"], ["BBB", "CCC"], extra='<g class="IfcFurniture" ifc:guid="MOV"><path d="M 1,1 L 2,2"/></g>\n')
    u = F.unir([a, b])
    raiz = ET.fromstring(u)
    assert raiz.tag.endswith("svg") and u.count("<style") == 1 and u.count('class="projection"') == 1
    assert re.findall(r'<path d="([^"]*)"/>', u.split('class="projection"')[1].split("</g>")[0]) == ["M1,1 L2,1", "M2,1 L2,2", "M2,2 L3,2"]
    assert [g for g in ("AAA", "BBB", "CCC") if f'ifc:guid="{g}"' in u] == ["AAA", "BBB", "CCC"] and u.count('ifc:guid="MOV"') == 1
    assert F.unir([a]) == a
    with pytest.raises(F.FaixasInvalidas):
        F.unir([])
    with pytest.raises(F.FaixasInvalidas):
        F.unir([a, _svg(["M0,0 L1,1"], [], vb="0 0 9 4.5")])  # outra raiz: não mistura desenhos incompatíveis
