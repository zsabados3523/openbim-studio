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

import time

import numpy as np
import pytest

from test_s06_t20d1_previa_oraculo import QUAD, L_CAPS, L_POLI, Z, caixa, grupos, moldura, peca, prisma, repete
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


def test_7c_guid_duplicado_nao_quebra_e_nao_perde_guid():
    ps = [laje("L", 0, 0, 10, 10), viga("X", 2, 2, 3, 3), viga("X", 15, 2, 16, 3)]
    r, a = rodar(ps)
    assert set().union(*a.values()) == {"L", "X"} and a["vista"] >= {"L"}


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
