# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oraculo F0-S06-T20d3a: previa sem as pecas escondidas (oclusao 2,5D) (T3). Alvo: `previa_planta.gerar_previa_planta`. Nao editar nesta tarefa.
CONTRATO (z = z_corte; helpers de malha reaproveitados de test_s06_t20d1_previa_oraculo):
 1. Auditoria passa a ter 5 chaves: cortada | vista | oculta | acima | falha; particao exata por GUID (cada GUID em um so conjunto; uniao == GUIDs pedidos).
 2. Peca classificada "vista" (zmax <= z) vira OCULTA se area(pegada da peca) - area(pegada ∩ UNIAO das pegadas dos oclusores) <= 1e-4 m2.
    Oclusor = outra peca com zmax_outra > zmax_peca + 1e-3 E pegada EXATA: secao da cortada (aneis evenodd da secao, nao a pegada inteira) ou silhueta_xy (tris <= limiar_tris).
    Casco convexo (tris > limiar_tris), caixa (movel com moveis_como_caixa), peca em "falha" e peca "acima" NUNCA ocluem. A pegada usa evenodd: furo de laje nao cobre.
 3. Oculta nao e desenhada (sem <g> no SVG). Cortada nunca e ocultada; acima segue acima; falha segue falha. Peca parcialmente coberta, ou no mesmo z (zmax dentro de 1e-3), fica vista.
 4. A peca com casco/caixa pode ser ocultada por oclusor exato.
MUTANTES que os testes matam: casco como oclusor; caixa como oclusor; so contorno externo (ignora furos); ignora z relativo; tolerancia de area errada (0, 1e-5, 1e-3, 1e-2);
ocultar cortada; auditoria sem `oculta`; oclusor por pegada inteira da cortada (em vez da secao); ocluir por oclusor unico (sem uniao); falha/acima como oclusores."""
from __future__ import annotations

import re
import time

from shapely.errors import GEOSException

import numpy as np
import pytest
import shapely

from test_s06_t20d1_previa_oraculo import QUAD, L_CAPS, L_POLI, Z, area_pintada, caixa, grupos, moldura, peca, prisma, repete
import obim_geometria.previa_planta as PP
from obim_geometria.previa_planta import gerar_previa_planta

CHAVES = {"cortada", "vista", "oculta", "acima", "falha"}


def rodar(pecas, **kw):
    r = gerar_previa_planta(pecas, Z, **kw)
    return r, {k: set(v) for k, v in r["auditoria"].items()}


def desenhados(r):
    return [g[1] for g in grupos(r["svg"])]


def laje(guid, x0, y0, x1, y1, z0=0.5, z1=0.7, **kw):
    return peca(guid, "IfcSlab", caixa(x0, y0, z0, x1, y1, z1), **kw)


def viga(guid, x0, y0, x1, y1, z0=0.0, z1=0.3, **kw):
    return peca(guid, "IfcBeam", caixa(x0, y0, z0, x1, y1, z1), **kw)


def junta(*vts):
    v, t, n = [], [], 0
    for vv, tt in vts:
        v.append(vv)
        t.append(tt + n)
        n += len(vv)
    return np.vstack(v), np.vstack(t)


def confere(r, aud, guids):
    assert set(aud) == CHAVES, set(aud)
    todos = [g for v in aud.values() for g in v]
    assert len(todos) == len(set(todos)) and set(todos) == set(guids), "particao exata: GUID duplicado ou omitido"


# ---------------------------------------------------------------- 1. casos basicos
def test_1_viga_sob_laje_inteira_e_oculta_e_some_do_svg():
    r, a = rodar([laje("L", 0, 0, 10, 10), viga("V", 2, 2, 3, 8)])
    assert a == {"cortada": set(), "vista": {"L"}, "oculta": {"V"}, "acima": set(), "falha": set()}
    assert desenhados(r) == ["L"] and 'ifc:guid="V"' not in r["svg"]
    confere(r, a, ["L", "V"])


def test_1b_viga_com_ponta_fora_da_laje_fica_vista():
    r, a = rodar([laje("L", 0, 0, 10, 10), viga("V", 8, 4, 12, 5)])
    assert a["vista"] == {"L", "V"} and not a["oculta"] and desenhados(r) == ["L", "V"]


def test_1c_viga_sob_o_furo_da_laje_fica_vista_e_viga_atras_do_aro_oculta():
    furada = peca("L", "IfcSlab", moldura(0, 0, 10, 10, 3.5, 0.5, 0.7))  # furo 3,5..6,5
    r, a = rodar([furada, viga("NO_FURO", 4.2, 4.2, 5.8, 5.8), viga("NO_ARO", 0.5, 0.5, 3.0, 9.5), viga("CRUZA", 2.0, 4.5, 4.5, 5.5)])
    assert a["vista"] == {"L", "NO_FURO", "CRUZA"} and a["oculta"] == {"NO_ARO"}
    confere(r, a, ["L", "NO_FURO", "NO_ARO", "CRUZA"])


def test_1d_peca_parcialmente_coberta_fica_vista_inteira():
    r, a = rodar([laje("L", 0, 0, 10, 10), viga("V", 9.5, 4, 10.5, 5)])
    assert "V" in a["vista"] and not a["oculta"]
    assert desenhados(r) == ["L", "V"]


def test_1e_viga_coberta_pela_uniao_de_duas_lajes_vizinhas():
    r, a = rodar([laje("A", 0, 0, 5, 10), laje("B", 5, 0, 10, 10), viga("V", 4, 2, 6, 8)])
    assert a["oculta"] == {"V"} and a["vista"] == {"A", "B"}, "a uniao cobre; um oclusor so nao"


# ---------------------------------------------------------------- 2. casco e caixa nunca ocluem
def test_2_laje_grande_com_casco_nao_oclui():
    grande = peca("G", "IfcSlab", repete(caixa(0, 0, 0.5, 10, 10, 0.7), 2400))  # > limiar_tris: casco
    r, a = rodar([grande, viga("V", 2, 2, 3, 8)])
    assert a["vista"] == {"G", "V"} and not a["oculta"]


def test_2b_limiar_tris_baixo_faz_a_laje_virar_casco_e_a_viga_reaparece():
    lj = laje("L", 0, 0, 10, 10)
    assert rodar([lj, viga("V", 2, 2, 3, 8)])[1]["oculta"] == {"V"}
    assert rodar([lj, viga("V", 2, 2, 3, 8)], limiar_tris=5)[1]["oculta"] == set(), "12 tris > limiar 5: casco, nao oclui"


def test_2c_laje_em_L_de_casco_nao_oclui_nem_no_corpo_nem_no_vazio():
    g = peca("G", "IfcSlab", repete(prisma(L_POLI, 0.5, 0.7, L_CAPS), 2400))
    r, a = rodar([g, viga("CORPO", 0.2, 0.2, 0.8, 0.8), viga("VAZIO", 1.3, 1.3, 1.8, 1.8)])
    assert a["vista"] == {"G", "CORPO", "VAZIO"} and not a["oculta"]


def test_2d_movel_em_caixa_nao_oclui_mas_movel_exato_oclui():
    m = peca("M", "IfcFurniture", caixa(0, 0, 0.0, 4, 4, 0.8), movel=True)
    ra, aa = rodar([m, viga("V", 1, 1, 2, 2)], moveis_como_caixa=True)
    assert aa["vista"] == {"M", "V"} and not aa["oculta"], "caixa nunca oclui"
    rb, ab = rodar([m, viga("V", 1, 1, 2, 2)])
    assert ab["oculta"] == {"V"} and ab["vista"] == {"M"}, "sem caixa o movel tem silhueta exata e oclui"


def test_2e_peca_com_casco_ou_caixa_pode_ser_ocultada_por_oclusor_exato():
    grande = peca("G", "IfcSlab", repete(caixa(2, 2, 0.0, 3, 3, 0.2), 2400))
    movel = peca("M", "IfcFurniture", caixa(5, 5, 0.0, 6, 6, 0.2), movel=True)
    r, a = rodar([laje("L", 0, 0, 10, 10), grande, movel], moveis_como_caixa=True)
    assert a["oculta"] == {"G", "M"} and a["vista"] == {"L"}


# ---------------------------------------------------------------- 3. secao da cortada oclui
def test_3_secao_de_parede_cortada_oculta_peca_baixa_e_a_cortada_segue_cortada():
    parede = peca("P", "IfcWall", caixa(0, 0, 0.0, 5, 0.2, 3.0))
    r, a = rodar([parede, viga("V", 1, 0.02, 2, 0.18)])
    assert a == {"cortada": {"P"}, "vista": set(), "oculta": {"V"}, "acima": set(), "falha": set()}


def test_3b_oclusor_e_a_secao_e_nao_a_pegada_inteira_da_peca_alta():
    base = caixa(0, 0, 0.0, 6, 6, 0.5)  # alarga so abaixo do corte
    topo = caixa(0, 0, 0.5, 2, 2, 2.0)
    degrau = peca("D", "IfcWall", junta(base, topo))
    r, a = rodar([degrau, viga("SOB_SECAO", 0.5, 0.5, 1.5, 1.5), viga("FORA_SECAO", 4, 4, 5, 5)])
    assert a["cortada"] == {"D"} and a["oculta"] == {"SOB_SECAO"} and a["vista"] == {"FORA_SECAO"}


def test_3c_secao_com_furo_nao_oclui_dentro_do_furo():
    r, a = rodar([peca("P", "IfcWall", moldura(0, 0, 4, 4, 1.5, 0.0, 3.0)), viga("NO_FURO", 1.8, 1.8, 2.2, 2.2), viga("SOB_PAREDE", 0.3, 0.3, 1.2, 1.2)])
    assert a["vista"] == {"NO_FURO"} and a["oculta"] == {"SOB_PAREDE"}


def test_3d_cortada_nunca_e_ocultada():
    alta = peca("ALTA", "IfcWall", caixa(0, 0, 0.0, 6, 6, 3.0))
    baixa = peca("BAIXA", "IfcWall", caixa(1, 1, 0.0, 2, 2, 2.0))  # cortada, zmax menor e pegada dentro da alta
    r, a = rodar([alta, baixa])
    assert a["cortada"] == {"ALTA", "BAIXA"} and not a["oculta"] and desenhados(r) == ["ALTA", "BAIXA"]


# ---------------------------------------------------------------- 4. z relativo e tolerancia de 1e-3
def test_4_so_oclui_quem_esta_mais_alto():
    r, a = rodar([laje("BAIXA", 0, 0, 10, 10, 0.0, 0.3), viga("ALTA", 2, 2, 3, 8, 0.4, 0.9)])
    assert a["vista"] == {"BAIXA", "ALTA"} and not a["oculta"], "viga acima da laje nao some sob ela"


def test_4b_mesma_pegada_so_a_mais_baixa_some():
    r, a = rodar([laje("A", 0, 0, 4, 4, 0.0, 0.3), laje("B", 0, 0, 4, 4, 0.0, 0.6)])
    assert a["oculta"] == {"A"} and a["vista"] == {"B"}


def test_4c_mesmo_z_nao_oculta():
    r, a = rodar([laje("A", 0, 0, 4, 4, 0.0, 0.5), laje("B", 1, 1, 2, 2, 0.1, 0.5)])
    assert a["vista"] == {"A", "B"} and not a["oculta"]


@pytest.mark.parametrize("dz, oculta", [(5e-4, False), (9e-4, False), (2e-3, True), (5e-3, True)])
def test_4d_tolerancia_de_zmax_1e3(dz, oculta):
    r, a = rodar([laje("TOPO", 0, 0, 10, 10, 0.1, 0.3 + dz), viga("V", 2, 2, 3, 8, 0.0, 0.3)])
    assert a["oculta"] == ({"V"} if oculta else set())
    assert a["vista"] == ({"TOPO"} if oculta else {"TOPO", "V"})


# ---------------------------------------------------------------- 5. tolerancia de area 1e-4 m2
@pytest.mark.parametrize("largura, oculta", [(5e-5, True), (3e-4, False)])
def test_5_area_descoberta_ate_1e4_m2(largura, oculta):
    r, a = rodar([laje("L", 0, 0, 10, 10), viga("V", 4, 4, 10 + largura, 5)])  # descoberta = largura x 1 m
    assert a["oculta"] == ({"V"} if oculta else set()), f"area descoberta {largura * 1.0:.1e}"


# ---------------------------------------------------------------- 6. falha e acima nao ocluem; falha nao some
def test_6_falha_e_acima_nao_ocluem_e_falha_nao_e_ocultada():
    falha_grande = peca("F", "IfcSlab", None, caixa=(0, 0, 10, 10))
    acima = peca("A", "IfcSlab", caixa(0, 0, 2.0, 10, 10, 2.5))
    sob_falha = peca("FS", "IfcWall", None, caixa=(2, 2, 3, 3))
    r, a = rodar([falha_grande, acima, viga("V", 2, 2, 3, 8), laje("L", 20, 20, 21, 21), sob_falha, laje("MAIOR", 1, 1, 4, 4)])
    assert a["falha"] == {"F", "FS"} and a["acima"] == {"A"}
    assert "V" in a["vista"] and "FS" not in a["oculta"] and "F" not in a["oculta"]
    confere(r, a, ["F", "A", "V", "L", "FS", "MAIOR"])


def test_6b_malha_degenerada_nao_oclui():
    degen = peca("D", "IfcSlab", (np.array([(0, 0, 0.5), (10, 0, 0.5), (20, 0, 0.5)]), np.array([[0, 1, 2]])), caixa=(0, 0, 20, 10))
    r, a = rodar([degen, viga("V", 2, 2, 3, 8)])
    assert a["falha"] == {"D"} and a["vista"] == {"V"}


# ---------------------------------------------------------------- 7. particao, GUID duplicado, ordem
def cena_mista():
    return [
        peca("PAREDE", "IfcWall", caixa(0, 0, 0.0, 6, 0.2, 3.0)),
        laje("LAJE", 10, 0, 20, 10),
        viga("OCULTA1", 11, 1, 12, 5),
        viga("OCULTA2", 0.5, 0.02, 1.5, 0.18),
        viga("VISTA", 19, 4, 21, 5),
        peca("ACIMA", "IfcBeam", caixa(0, 5, 2.0, 1, 6, 3.0)),
        peca("FALHA", "IfcWall", None, caixa=(30, 0, 31, 1)),
        peca("GRANDE", "IfcSlab", repete(caixa(40, 0, 0.0, 41, 1, 0.2), 2400)),
    ]


def test_7_particao_exata_por_guid_e_ordem_do_svg():
    ps = cena_mista()
    r, a = rodar(ps)
    assert a == {"cortada": {"PAREDE"}, "vista": {"LAJE", "VISTA", "GRANDE"}, "oculta": {"OCULTA1", "OCULTA2"}, "acima": {"ACIMA"}, "falha": {"FALHA"}}
    confere(r, a, [p["guid"] for p in ps])
    assert desenhados(r) == ["PAREDE", "LAJE", "VISTA", "FALHA", "GRANDE"], "ordem de `pecas`, sem ocultas nem acima"


def test_7b_resultado_estavel_entre_chamadas_e_independente_da_ordem_de_entrada():
    ps = cena_mista()
    r1, a1 = rodar(ps)
    r2, a2 = rodar(ps)
    assert r1["svg"] == r2["svg"] and a1 == a2
    _r3, a3 = rodar(list(reversed(ps)))
    assert a3 == a1, "a classificacao nao depende da ordem"


def test_7c_guid_duplicado_particao_completa_e_um_grupo_por_guid():
    ps = [laje("L", 0, 0, 10, 10), viga("X", 12, 2, 13, 3), viga("X", 15, 2, 16, 3)]
    r, a = rodar(ps)
    confere(r, a, ["L", "X"])
    assert a["vista"] == {"L", "X"}
    gs = [g for g in grupos(r["svg"]) if g[1] == "X"]
    assert len(gs) == 1, "um <g> por GUID"
    assert sum(len(sub) for path in gs[0][2] for sub in [path]) >= 2 and sum(1 for path in gs[0][2] for _ in path) == 2, "aneis das duas partes unidos no mesmo grupo"


@pytest.mark.parametrize("partes, esperado", [
    (("cortada", "vista"), "cortada"), (("vista", "oculta"), "vista"), (("oculta", "falha"), "oculta"), (("falha", "acima"), "falha"),
    (("cortada", "oculta"), "cortada"), (("vista", "falha"), "vista"), (("oculta", "acima"), "oculta"),
])
def test_7d_prioridade_cortada_vista_oculta_falha_acima_para_guid_repetido(partes, esperado):
    pos = {"cortada": peca("X", "IfcWall", caixa(30, 0, 0.0, 31, 1, 3.0)), "vista": viga("X", 20, 0, 21, 1),
           "oculta": viga("X", 2, 2, 3, 3), "falha": peca("X", "IfcWall", None, caixa=(40, 0, 41, 1)), "acima": peca("X", "IfcBeam", caixa(50, 0, 2.0, 51, 1, 3.0))}
    ps = [laje("L", 0, 0, 10, 10)] + [pos[k] for k in partes]
    r, a = rodar(ps)
    confere(r, a, ["L", "X"])
    assert "X" in a[esperado], (partes, a)
    assert ('ifc:guid="X"' in r["svg"]) == (esperado not in ("oculta", "acima"))
    assert r["svg"].count('ifc:guid="X"') <= 1


def test_7e_partes_do_mesmo_guid_nao_se_ocluem():
    ps = [peca("X", "IfcSlab", caixa(0, 0, 0.5, 10, 10, 0.7)), peca("X", "IfcBeam", caixa(2, 2, 0.0, 3, 8, 0.3))]
    r, a = rodar(ps)
    confere(r, a, ["X"])
    assert a["vista"] == {"X"}
    (g,) = [g for g in grupos(r["svg"]) if g[1] == "X"]
    assert sum(len(sub) for sub in g[2]) == 2, "as duas partes ficam desenhadas (o mesmo GUID nao se oculta)"
    rr, aa = rodar([peca("X", "IfcSlab", caixa(0, 0, 0.5, 10, 10, 0.7)), peca("Y", "IfcBeam", caixa(2, 2, 0.0, 3, 8, 0.3))])
    assert aa["oculta"] == {"Y"}, "contraste: GUID diferente oculta"


# ---------------------------------------------------------------- 8. destino, fase e desempenho
def test_8_ao_fase_destino_e_chaves_continuam(tmp_path):
    fases, d = [], tmp_path / "p.svg"
    r, a = rodar([laje("L", 0, 0, 10, 10), viga("V", 2, 2, 3, 8)], destino=str(d), ao_fase=fases.append)
    assert fases == ["previa"] and d.read_text(encoding="utf-8") == r["svg"] and 'ifc:guid="V"' not in d.read_text(encoding="utf-8")


def test_9_desempenho_400_pecas_sob_1_5_s():
    ps = []
    for i in range(200):
        x, y = (i % 20) * 2.0, (i // 20) * 2.0
        ps.append(laje(f"L{i}", x, y, x + 1.9, y + 1.9))
        ps.append(viga(f"V{i}", x + 0.2, y + 0.2, x + 1.7, y + 0.5))
    t0 = time.perf_counter()
    r, a = rodar(ps)
    dt = time.perf_counter() - t0
    assert a["oculta"] == {f"V{i}" for i in range(200)} and len(a["vista"]) == 200
    assert dt < 1.5, f"400 pecas levaram {dt:.2f} s"


# ================================================================ T20d3a rodada 2 (revisao Argon)
# Contrato acrescentado:
#  A. Pegada = evenodd de TODOS os aneis (ilhas disjuntas, furo e ilha dentro do furo): cada anel alterna dentro/fora.
#  B. Oculta SO se area_coberta >= 0,5 * area da pegada E area_descoberta <= 1e-4 m2. Peca pequena (<= 1e-4) fora do oclusor, so tocando borda/vertice, e vista.
#  C. GUID repetido: particao por prioridade cortada > vista > oculta > falha > acima (o GUID vai ao conjunto de maior prioridade entre as partes); UM <g ifc:guid> por GUID,
#     com os aneis das partes NAO ocultas/acima unidos; partes do mesmo GUID nunca se ocluem.
#  D. GEOSException em symmetric_difference / union_all / difference: a previa nao cai; a peca afetada fica vista (nunca oculta); particao intacta.
#     Area liquida evenodd <= 1e-12 (casca dupla): categoria "falha" com aneis de falha (mesma regra de _aneis_validos).
#  E. Oclusor oculto continua ocluindo. viewBox so inclui o que e desenhado (nem oculta, nem acima). Fronteiras: zmax_outra == zmax + 1e-3 NAO conta (`>` estrito).


def _caixa_area(g):
    xs = [p for path in g[2] for sub in path for p in sub]
    return xs


# ---- (1) ilhas e aneis aninhados
def test_10_peca_de_2_ilhas_so_com_a_primeira_coberta_fica_vista():
    duas = peca("D", "IfcBeam", junta(caixa(0, 0, 0.0, 2, 2, 0.3), caixa(6, 0, 0.0, 8, 2, 0.3)))
    r, a = rodar([duas, laje("A", -1, -1, 3, 3)])
    assert a["vista"] == {"D", "A"} and not a["oculta"], "2a ilha descoberta: peca visivel"
    r, a = rodar([duas, laje("A", -1, -1, 3, 3), laje("B", 5, -1, 9, 3)])
    assert a["oculta"] == {"D"} and a["vista"] == {"A", "B"}, "as duas ilhas cobertas"


def test_10b_viga_sob_a_ilha_interna_oculta_e_no_furo_fica_vista():
    anel_com_ilha = peca("S", "IfcSlab", junta(moldura(0, 0, 10, 10, 2, 0.5, 0.7), caixa(4, 4, 0.5, 6, 6, 0.7)))  # externo + furo (2..8) + ilha (4..6)
    r, a = rodar([anel_com_ilha, viga("ILHA", 4.5, 4.5, 5.5, 5.5), viga("FURO", 2.5, 2.5, 3.5, 3.5), viga("ARO", 0.5, 0.5, 1.5, 1.5)])
    assert a["oculta"] == {"ILHA", "ARO"} and a["vista"] == {"S", "FURO"}
    confere(r, a, ["S", "ILHA", "FURO", "ARO"])


# ---- (2) cobertura real minima de 50%
@pytest.mark.parametrize("nome, rect", [("toca_borda", (10.0, 0.0, 10.01, 0.008)), ("toca_vertice", (10.0, 10.0, 10.01, 10.008)), ("toca_borda_do_furo_fora", (10.0, 5.0, 10.01, 5.008))])
def test_11_peca_minuscula_fora_do_oclusor_so_tocando_fica_vista(nome, rect):
    r, a = rodar([laje("L", 0, 0, 10, 10), viga("P", *rect)])  # area 8e-5 <= 1e-4, cobertura real 0
    assert a["vista"] == {"L", "P"} and not a["oculta"], nome


@pytest.mark.parametrize("dentro, oculta", [(0.01, True), (0.006, True), (0.004, False), (0.0, False)])
def test_11b_peca_minuscula_precisa_de_pelo_menos_metade_coberta(dentro, oculta):
    r, a = rodar([laje("L", 0, 0, 10, 10), viga("P", 10.0 - dentro, 4.0, 10.01 - dentro, 4.008)])  # area 8e-5; fracao dentro = dentro / 0,01
    assert a["oculta"] == ({"P"} if oculta else set()), f"fracao coberta {dentro / 0.01:.0%}"


# ---- (3) GUID duplicado: ver 7c, 7d, 7e acima

# ---- (4) desempenho com 3000 pecas
def laje_com_furos(guid, x0, y0, z, nx=31, ny=21):
    """Laje de celulas 1 x 1 em grade nx x ny com 150 furos (celulas impares isoladas): so a face superior (flat, z constante), ~1000 tris (<= limiar)."""
    v, t = [], []
    for i in range(nx):
        for j in range(ny):
            if i % 2 == 1 and j % 2 == 1:
                continue
            k = len(v)
            v += [(x0 + i, y0 + j, z), (x0 + i + 1, y0 + j, z), (x0 + i + 1, y0 + j + 1, z), (x0 + i, y0 + j + 1, z)]
            t += [(k, k + 1, k + 2), (k, k + 2, k + 3)]
    return peca(guid, "IfcSlab", (np.array(v, float), np.array(t, int)))


def pilar(guid, cx, cy):
    ang = np.linspace(0, 2 * np.pi, 32, endpoint=False)
    v = [(cx + 0.3 * np.cos(a), cy + 0.3 * np.sin(a), z) for z in (0.0, 1.0) for a in ang] + [(cx, cy, 0.0), (cx, cy, 1.0)]
    t = []
    for k in range(32):
        a, b = k, (k + 1) % 32
        t += [(64, b, a), (65, 32 + a, 32 + b), (a, b, 32 + b), (a, 32 + b, 32 + a)]  # 128 tris
    return peca(guid, "IfcColumn", (np.array(v, float), np.array(t, int)))


def test_12_desempenho_3000_pecas_sob_5_s():
    ps, esp_ocultas = [], set()
    for s in range(5):  # 5 lajes 31 x 21, 150 furos cada
        ps.append(laje_com_furos(f"S{s}", 0.0, s * 30.0, 0.8))
    for s in range(5):  # vigas sob as lajes, em celulas cheias (i, j pares): 2000 -> ocultas
        for k in range(400):
            i, j = (k % 15) * 2, (k // 15) * 2 % 20
            ps.append(viga(f"V{s}_{k}", i + 0.2, s * 30.0 + j + 0.2, i + 0.7, s * 30.0 + j + 0.7))
            esp_ocultas.add(f"V{s}_{k}")
    for k in range(995):  # pilares vistos (128 tris) longe das lajes
        ps.append(pilar(f"P{k}", 100.0 + (k % 40) * 2, (k // 40) * 2.0))
    assert len(ps) == 3000
    t0 = time.perf_counter()
    r, a = rodar(ps)
    dt = time.perf_counter() - t0
    assert dt < 5.0, f"3000 pecas levaram {dt:.2f} s"
    assert a["oculta"] == esp_ocultas and len(a["vista"]) == 5 + 995
    confere(r, a, [p["guid"] for p in ps])


def test_12b_previa_nao_abre_um_pool_de_threads_por_peca(monkeypatch):
    """Pilares de 128 tris passavam do limite (64 tris) que abre ThreadPoolExecutor dentro de `uniao_triangulos_xy`: 1 pool por peca custa ~3 s por 1000 pecas.
    A previa roda peca a peca (ja e a fase barata): deve pedir `threads=1` (zero pools)."""
    from obim_geometria import silhueta as SIL
    criados = []

    class Pool(SIL.ThreadPoolExecutor):
        def __init__(self, *a, **k):
            criados.append(1)
            super().__init__(*a, **k)

    monkeypatch.setattr(SIL, "ThreadPoolExecutor", Pool)
    ps = [pilar(f"P{k}", (k % 20) * 2.0, (k // 20) * 2.0) for k in range(200)]
    r, a = rodar(ps)
    assert len(a["vista"]) == 200 and not criados, f"{len(criados)} pools de threads criados"


# ---- (5) GEOSException e casca dupla
def _estoura(monkeypatch, nome):
    def f(*a, **k):
        raise GEOSException("simulado")
    monkeypatch.setattr(shapely, nome, f)


@pytest.mark.parametrize("op, afetada", [("difference", "SLIVER"), ("union_all", "SOB_AB"), ("symmetric_difference", "SOB_F")])
def test_13_geos_exception_nao_derruba_e_a_peca_fica_vista(monkeypatch, op, afetada):
    furada = peca("F", "IfcSlab", moldura(0, 0, 10, 10, 3.5, 0.5, 0.7))
    ps = [furada, laje("A", 20, 0, 25, 10), laje("B", 25, 0, 30, 10), viga("SOB_AB", 24, 2, 26, 8), viga("SOB_F", 0.5, 0.5, 3.0, 9.5),
          viga("SLIVER", 21, 2, 25.00005, 3)]  # SLIVER: so a diferenca (5e-5 m2 fora de A) decide
    r0, a0 = rodar(ps)
    assert a0["oculta"] == {"SOB_AB", "SOB_F", "SLIVER"}, a0
    _estoura(monkeypatch, op)
    r, a = rodar(ps)
    confere(r, a, [p["guid"] for p in ps])
    assert afetada in a["vista"] and afetada not in a["oculta"], f"{op}: {afetada} deve ficar vista (nunca oculta por erro)"
    assert f'ifc:guid="{afetada}"' in r["svg"]


def test_13b_casca_dupla_area_liquida_zero_vira_falha_com_aneis_de_falha(monkeypatch):
    anel = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
    real = PP.silhueta_xy
    monkeypatch.setattr(PP, "silhueta_xy", lambda v, t, *a, **k: [anel, anel] if float(np.min(v[:, 0])) == 0.0 and float(np.max(v[:, 0])) == 1.0 else real(v, t, *a, **k))
    ps = [peca("D", "IfcSlab", caixa(0, 0, 0.0, 1, 1, 0.2), caixa=(0, 0, 1, 1)), viga("V", 5, 5, 6, 6)]
    r, a = rodar(ps)
    confere(r, a, ["D", "V"])
    assert a["falha"] == {"D"} and a["vista"] == {"V"}
    (g,) = [g for g in grupos(r["svg"]) if g[1] == "D"]
    assert g[0] == ["IfcSlab", "projection"] and abs(area_pintada(g) - 1.0) <= 0.02, "desenhada como caixa de falha (1 x 1), nao como casca dupla (area 0 evenodd)"


# ---- (6) cadeia, viewBox e fronteiras
def _rect(guid, x1, z1, y1=10.0):
    return peca(guid, "IfcSlab", caixa(0, 0, z1 - 0.1, x1, y1, z1))


def test_14_oclusor_oculto_continua_ocluindo():
    topo, meio, baixa = _rect("TOPO", 10.0, 0.9), _rect("MEIO", 10.000008, 0.5), _rect("BAIXA", 10.000015, 0.2)  # sobras 8e-5 / (7e-5 sob MEIO, 1,5e-4 sob TOPO)
    r, a = rodar([topo, meio, baixa])
    assert a["oculta"] == {"MEIO", "BAIXA"} and a["vista"] == {"TOPO"}, "BAIXA so e coberta por MEIO, que esta oculta"
    r2, a2 = rodar([topo, baixa])
    assert a2["vista"] == {"TOPO", "BAIXA"}, "sem o MEIO, a sobra de 1,5e-4 deixa BAIXA vista"


def test_14b_viewbox_nao_inclui_oculta_nem_acima():
    topo, meio, baixa = _rect("TOPO", 10.0, 0.9), _rect("MEIO", 10.000008, 0.5), _rect("BAIXA", 10.000015, 0.2)
    longe = peca("ACIMA", "IfcBeam", caixa(100, 0, 2.0, 101, 1, 3.0))
    r, a = rodar([topo, meio, baixa, longe])
    assert a["oculta"] == {"MEIO", "BAIXA"} and a["acima"] == {"ACIMA"}
    x, y, w, h = map(float, re.search(r'viewBox="([^"]+)"', r["svg"]).group(1).split())
    assert abs(w - 10.0) < 1e-6 and abs(h - 10.0) < 1e-6, f"viewBox {w} x {h}: so a TOPO (10 x 10) esta desenhada"


def test_15_fronteira_de_zmax_exatamente_1e3_nao_conta_e_1_0001e3_conta():
    base = viga("V", 2, 2, 3, 8, 0.0, 0.5)
    r, a = rodar([base, laje("T", 0, 0, 10, 10, 0.1, 0.5 + 1e-3)])
    assert a["vista"] == {"V", "T"}, "zmax_outra == zmax + 1e-3: `>` estrito, nao conta"
    r, a = rodar([base, laje("T", 0, 0, 10, 10, 0.1, 0.5 + 1.0001e-3)])
    assert a["oculta"] == {"V"}


@pytest.mark.parametrize("sobra, oculta", [(9.9e-5, True), (1.01e-4, False)])
def test_15b_fronteira_de_area_descoberta_1e4(sobra, oculta):
    r, a = rodar([laje("L", 0, 0, 1, 1), viga("V", 0.2, 0.0, 1.0 + sobra, 1.0)])  # descoberta = sobra x 1 m
    assert a["oculta"] == ({"V"} if oculta else set())


# ================================================================ T20d3a rodada 3 (Argon: clip_by_rect em oclusor concavo / furo diagonal)
# Contrato: a classificacao oculta/vista e a da DIFERENCA DIRETA de poligonos (sem recorte por retangulo):
#   oculta <=> desc <= 1e-4 e (area - desc) >= 0,5 * area, com desc = area(pegada - uniao(pegadas dos oclusores)). Nenhuma geometria invalida pode decidir o resultado.
V_POLI = [(0, 0), (10, 0), (10, 10), (5, 2), (0, 10)]  # laje em V: entalhe triangular vazio (0,10)-(5,2)-(10,10)
V_CAPS = [(0, 3, 4), (0, 1, 3), (1, 2, 3)]


def V(z0=0.5, z1=0.7, guid="OCL_V"):
    return peca(guid, "IfcSlab", prisma(V_POLI, z0, z1, V_CAPS))


def malha_de_poligono(poli, z0, z1):
    """Malha (tampa inferior e superior) de um Polygon shapely com furos, por triangulacao de Delaunay restrita."""
    tri = shapely.constrained_delaunay_triangles(poli)
    v, ix, t = [], {}, []
    for g in tri.geoms:
        cs = list(g.exterior.coords)[:3]
        ids = []
        for c in cs:
            if c not in ix:
                ix[c] = len(v)
                v.append(c)
            ids.append(ix[c])
        t.append(ids)
    n = len(v)
    t = np.array(t, int)
    verts = np.array([(x, y, z0) for x, y in v] + [(x, y, z1) for x, y in v], float)
    return verts, np.vstack([t, t + n])


def esperado_oculta(pegada, oclusores):
    """Regra do contrato, por diferenca direta (sem clip_by_rect)."""
    if not oclusores:
        return False
    desc = pegada.difference(shapely.union_all(oclusores)).area
    return desc <= 1e-4 and pegada.area - desc >= 0.5 * pegada.area


def test_16_a_peca_triangular_no_entalhe_do_V_tem_cobertura_zero_e_fica_vista():
    no_vazio = peca("NO_VAZIO", "IfcBeam", prisma([(0, 10), (5, 2), (10, 10)], 0.0, 0.3, [(0, 1, 2)]))  # area 40, so encosta nas arestas diagonais
    r, a = rodar([V(), no_vazio])
    assert a["vista"] == {"OCL_V", "NO_VAZIO"} and not a["oculta"]
    assert 'ifc:guid="NO_VAZIO"' in r["svg"]


def test_16b_peca_triangular_dentro_do_furo_em_losango_fica_vista():
    laje_losango = shapely.Polygon([(0, 0), (10, 0), (10, 10), (0, 10)], [[(5, 2), (8, 5), (5, 8), (2, 5)]])
    furada = peca("L", "IfcSlab", malha_de_poligono(laje_losango, 0.5, 0.7))
    dentro = peca("T", "IfcBeam", prisma([(2, 5), (5, 2), (8, 5)], 0.0, 0.3, [(0, 1, 2)]))  # bounds (2,2,8,5) tangenciam vertices do furo
    r, a = rodar([furada, dentro])
    assert a["vista"] == {"L", "T"} and not a["oculta"]
    sob_aro = peca("A", "IfcBeam", caixa(0.5, 0.5, 0.0, 1.5, 1.5, 0.3))
    assert rodar([furada, sob_aro])[1]["oculta"] == {"A"}, "contraste: sob o aro continua oculta"


def test_16c_duas_ilhas_nas_abas_cheias_do_V_com_sobra_1e5_ficam_ocultas():
    ilhas = peca("I", "IfcBeam", junta(caixa(0, 2, 0.0, 1, 3, 0.3), caixa(9, 2, 0.0, 10 + 1.25e-5, 3, 0.3)))  # sobra = 1,25e-5 x 0,8 = 1e-5; bounds (0,2,...) tangenciam (5,2)
    r, a = rodar([V(), ilhas])
    assert a["oculta"] == {"I"} and a["vista"] == {"OCL_V"}
    mais_sobra = peca("J", "IfcBeam", junta(caixa(0, 2, 0.0, 1, 3, 0.3), caixa(9, 2, 0.0, 10 + 1.4e-4, 3, 0.3)))  # sobra 1,1e-4 > 1e-4
    assert rodar([V(), mais_sobra])[1]["vista"] == {"OCL_V", "J"}


BOXES_V = [(1, 2, 9, 4), (0, 2, 10, 3), (2, 2, 8, 10), (4, 2, 6, 6), (0, 0, 10, 2), (0.2, 2, 1.0, 5), (4.9, 2, 5.1, 2.5), (3, 5, 7, 9), (0, 0, 10, 10)]


@pytest.mark.parametrize("box", BOXES_V)
def test_16d_bounds_tangentes_ao_vertice_do_V_batem_com_a_diferenca_direta(monkeypatch, box):
    invalidas = []
    real = shapely.clip_by_rect
    monkeypatch.setattr(shapely, "clip_by_rect", lambda g, *a, **k: (lambda o: (invalidas.append(o) if not o.is_valid else None, o)[1])(real(g, *a, **k)))
    x0, y0, x1, y1 = box
    r, a = rodar([V(), viga("P", x0, y0, x1, y1)])
    esp = esperado_oculta(shapely.box(x0, y0, x1, y1), [shapely.Polygon(V_POLI)])
    assert ("P" in a["oculta"]) == esp, f"{box}: esperado oculta={esp} (diferenca direta)"
    assert ("P" in a["vista"]) == (not esp) and not invalidas, "geometria invalida usada na decisao"


def _poligono_aleatorio(rng, cx, cy, r, tipo):
    if tipo == "convexo":
        pts = np.c_[cx + rng.uniform(-r, r, 9), cy + rng.uniform(-r, r, 9)]
        return shapely.convex_hull(shapely.multipoints(pts))
    n = int(rng.integers(5, 10))
    ang = np.sort(rng.uniform(0, 2 * np.pi, n))
    rad = rng.uniform(0.35 * r, r, n)
    p = shapely.Polygon(np.c_[cx + rad * np.cos(ang), cy + rad * np.sin(ang)])
    if not p.is_valid or p.area < 1e-3:
        return None
    if tipo == "furo":
        furo = shapely.Polygon(np.c_[cx + 0.3 * r * np.cos(np.linspace(0, 2 * np.pi, 6, endpoint=False)), cy + 0.3 * r * np.sin(np.linspace(0, 2 * np.pi, 6, endpoint=False))])
        if p.contains(furo):
            p = shapely.Polygon(p.exterior.coords, [furo.exterior.coords])
    return p


def test_17_propriedade_200_pecas_poligonais_aleatorias_batem_com_a_diferenca_direta():
    rng = np.random.default_rng(20241119)
    polis, zs = [], []
    while len(polis) < 200:
        grande = len(polis) < 40
        tipo = ["convexo", "concavo", "furo"][len(polis) % 3] if grande else ["convexo", "concavo"][len(polis) % 2]
        p = _poligono_aleatorio(rng, rng.uniform(0, 40), rng.uniform(0, 40), rng.uniform(6, 12) if grande else rng.uniform(0.8, 3.0), tipo)
        if p is None or p.geom_type != "Polygon" or p.area < 0.05:
            continue
        polis.append(p)
        zs.append(float(rng.choice([0.6, 0.9, 1.1]) if grande else rng.choice([0.2, 0.3, 0.5])))
    ps = [peca(f"G{i}", "IfcSlab", malha_de_poligono(p, z - 0.1, z)) for i, (p, z) in enumerate(zip(polis, zs))]
    r, a = rodar(ps)
    confere(r, a, [p["guid"] for p in ps])
    esp = set()
    for i, p in enumerate(polis):
        ocl = [q for j, q in enumerate(polis) if j != i and zs[j] > zs[i] + 1e-3]
        if esperado_oculta(p, ocl):
            esp.add(f"G{i}")
    assert 15 <= len(esp) <= 185, f"cena sem variedade ({len(esp)} ocultas)"
    assert a["oculta"] == esp, f"diferem: so previa {sorted(a['oculta'] - esp)}; so direta {sorted(esp - a['oculta'])}"
    assert a["vista"] == {f"G{i}" for i in range(200)} - esp


def test_17b_propriedade_pecas_triangulares_com_vertices_nos_vertices_do_oclusor():
    """Pecas cujos bounds tangenciam vertices concavos e de furos dos oclusores (caso que enganava o recorte por retangulo)."""
    rng = np.random.default_rng(7)
    ocl, k = [], 0
    while len(ocl) < 12:
        p = _poligono_aleatorio(rng, 15.0, 15.0, rng.uniform(6, 12), ["concavo", "furo"][k % 2])
        k += 1
        if p is not None and p.geom_type == "Polygon":
            ocl.append(p)
    ocl.append(shapely.Polygon(V_POLI))
    ocl.append(shapely.Polygon([(0, 0), (10, 0), (10, 10), (0, 10)], [[(5, 2), (8, 5), (5, 8), (2, 5)]]))
    pecas_, tris, esp_pol = [], [], []
    for i, p in enumerate(ocl):
        pecas_.append(peca(f"O{i}", "IfcSlab", malha_de_poligono(p, 0.7, 0.9)))
        pts = [c for anel in [p.exterior, *p.interiors] for c in list(anel.coords)[:-1]]
        for j in range(6):
            a, b, c = (pts[int(x)] for x in rng.choice(len(pts), 3, replace=False))
            t = shapely.Polygon([a, b, c])
            if t.is_valid and t.area > 1e-3:
                tris.append(t)
                pecas_.append(peca(f"T{len(tris) - 1}", "IfcBeam", malha_de_poligono(t, 0.0, 0.2)))
    r, a = rodar(pecas_)
    confere(r, a, [p["guid"] for p in pecas_])
    esp = {f"T{i}" for i, t in enumerate(tris) if esperado_oculta(t, ocl)}
    obtido = {g for g in a["oculta"] if g.startswith("T")}
    assert 5 <= len(esp) < len(tris) - 5, f"cena sem variedade: {len(esp)} de {len(tris)}"
    assert obtido == esp, f"so previa {sorted(obtido - esp)}; so direta {sorted(esp - obtido)}"
