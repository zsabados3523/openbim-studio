# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oraculo F0-S06-T24h (ADR-010, P3): aneis fechados nao agrupaveis em `planta_cache.py`.

Alvo (implementador NAO edita este arquivo; somente `geometria/obim_geometria/planta_cache.py`):
- Se `oclusores._agrupar_aneis(fechados)` devolver `None` ou `[]`: aneis fechados da peca NAO entram
  na tampa (`grupos_secao`), viram linhas M/L sem Z na secao, a peca conta 1x em `secoes_parciais`
  (mesmo se ja tiver `abertos`) e segue em `enviados`/SVG.
- Limite `secoes_parciais <= math.ceil(0.25 * n_cortadas)` (T24f + T24h; denominador = cortadas).
- Pecas boas nao mudam (byte a byte); determinismo (SHA-256) e imutabilidade de `malhas_mundo`.
"""
from __future__ import annotations

import math
import xml.etree.ElementTree as ET
import numpy as np
import pytest

from obim_geometria import aneis, corte_plano, oclusores, planta_cache, recorte, visibilidade
from openbim_app.desenho import estilo
from test_s06_t24c_planta_cache_oraculo import _tubo_np
from test_s06_t24f_secao_tolerante_oraculo import (
    _caixa_100_aberta_np, _caixa_np, _caixas_fundidas_em_t_np, _dist_pontos_a_segs,
    _extrair_polilinhas_d, _malha_sem_segmentos_corte_np, _montar_cena_numpy, _parse_svg,
    _polilinhas_mundo, _polilinhas_para_segs, _pontos_de_segs, _sha256, _transladar_malha,
)


def _extrudir_prisma_fechado(pts2d, caps_tris, z0: float = 0.0, z1: float = 2.8):
    n = len(pts2d)
    verts = np.array([(x, y, z) for z in (z0, z1) for (x, y) in pts2d], dtype=np.float64)
    tris = []
    for i in range(n):
        j = (i + 1) % n
        tris.extend([[i, j, j + n], [i, j + n, i + n]])
    for a, b, c in caps_tris:
        tris.extend([[a, c, b], [a + n, b + n, c + n]])
    return verts, np.asarray(tris, dtype=np.int32)


def _malha_anel_area_quase_zero_np(dx: float = 0.0, dy: float = 0.0, z0: float = 0.0, z1: float = 2.8):
    """1 fechado com |area|=5e-14 <= 1e-12 -> `_agrupar_aneis` None."""
    return _extrudir_prisma_fechado([(dx, dy), (dx + 0.5, dy + 1e-13), (dx + 1.0, dy)], [(0, 1, 2)], z0, z1)


def _malha_anel_bowtie_area_zero_np(dx: float = 0.0, dy: float = 0.0, z0: float = 0.0, z1: float = 2.8):
    """1 fechado auto-intersectante com area=0.0 -> `_agrupar_aneis` None."""
    return _extrudir_prisma_fechado([(dx, dy), (dx + 1.0, dy + 1.0), (dx + 1.0, dy), (dx, dy + 1.0)], [], z0, z1)


def _malha_furo_sem_pai_np(dx: float = 0.0, dy: float = 0.0, z0: float = 0.0, z1: float = 2.8):
    """L + triangulo na concavidade: 2 fechados (11.2 e -0.5), furo sem pai -> None."""
    ext_l = [(dx, dy), (dx + 4.0, dy), (dx + 4.0, dy + 2.0), (dx + 1.6, dy + 2.0), (dx + 1.6, dy + 4.0), (dx, dy + 4.0)]
    tri_b = [(dx + 1.5, dy + 2.0), (dx + 2.5, dy + 1.5), (dx + 2.5, dy + 2.5)]
    v_a, t_a = _extrudir_prisma_fechado(ext_l, [(0, 1, 2), (0, 2, 3), (0, 3, 4), (0, 4, 5)], z0, z1)
    v_b, t_b = _extrudir_prisma_fechado(tri_b, [(0, 1, 2)], z0, z1)
    return np.vstack([v_a, v_b]), np.vstack([t_a, t_b + len(v_a)]).astype(np.int32)


def _malha_mista_nao_agrupavel_e_aberta_np(dx: float = 0.0, dy: float = 0.0, z0: float = 0.0, z1: float = 2.8):
    """Mesma peca com 1 fechado nao agrupavel + 1 aberto -> conta 1 em `secoes_parciais`."""
    v0, t0 = _malha_anel_area_quase_zero_np(dx, dy, z0, z1)
    v1, t1 = _caixa_100_aberta_np(dx, dy + 1.0, z0, dx + 1.0, dy + 1.4, z1)
    return np.vstack([v0, v1]), np.vstack([t0, t1 + len(v0)]).astype(np.int32)


def _boas(n: int, *, id0: int = 10, x0: float = 0.0, passo: float = 4.0, prefixo: str = "G_BOA"):
    return [(id0 + i, f"{prefixo}_{i}", "IfcWall", _caixa_np(x0 + i * passo, 0.0, 0.0, x0 + i * passo + 2.0, 0.3, 2.8)) for i in range(n)]


def _xml_grupos(parsed, gid: str) -> list[str]:
    return [ET.tostring(g, encoding="unicode") for g in parsed.cut_by_guid[gid]]


def _verificar_linhas_peca_ruim(parsed, gid: str, malha, z_corte: float) -> None:
    """Confere peca ruim no SVG como linhas M/L sem Z coerentes com o corte real."""
    assert gid in parsed.cut_by_guid, f"{gid} ausente no SVG"
    grupos_el = parsed.cut_by_guid[gid]
    for g in grupos_el:
        for p in g.iter():
            if p.tag.rsplit("}", 1)[-1] == "path":
                cmds, _ = _extrair_polilinhas_d(p.get("d") or "")
                assert cmds and set(cmds).issubset({"M", "L"}) and "Z" not in cmds and "z" not in cmds
    pls = _polilinhas_mundo(grupos_el)
    segs_des = _polilinhas_para_segs(pls)
    assert len(segs_des) >= 1, f"{gid} sem segmentos desenhados no SVG"
    _, _, segs_corte = corte_plano.cortar_malha_no_plano(*malha, z_corte)
    fechados, abertos = aneis.aneis_de_segmentos(segs_corte)
    assert len(pls) >= len(fechados) + len(abertos)
    segs_esp = np.asarray(segs_corte, dtype=np.float64).reshape(-1, 4)
    assert float(_dist_pontos_a_segs(_pontos_de_segs(segs_des), segs_esp).max()) <= 1e-4
    assert float(_dist_pontos_a_segs(np.vstack([*fechados, *abertos]), segs_des).max()) <= 1e-4


def _congelar_snapshot(malhas: dict, pedido: dict):
    chaves = list(malhas.keys())
    copia_m = {g: (v.copy(), t.copy()) for g, (v, t) in malhas.items()}
    copia_p = {k: (dict(v) if isinstance(v, dict) else list(v) if isinstance(v, list) else v) for k, v in pedido.items()}
    for v, t in malhas.values():
        v.setflags(write=False)
        t.setflags(write=False)
    return chaves, copia_m, copia_p


def _checar_imutavel(malhas: dict, pedido: dict, chaves, copia_m, copia_p) -> None:
    assert list(malhas.keys()) == chaves
    for g, (v0, t0) in copia_m.items():
        np.testing.assert_array_equal(malhas[g][0], v0)
        np.testing.assert_array_equal(malhas[g][1], t0)
    assert pedido == copia_p


def _svg_referencia_boas(f, pedido: dict, malhas_mundo: dict, elementos_validos):
    """Monta SVG esperado byte a byte para cena so com pecas boas sem deslocamento."""
    vista, z = pedido["vista"], float(pedido["vista"]["altura_corte_m"])
    eps = max(1e-9, 1e-12 * max(1.0, abs(z)))
    enviados, pecas_secao, grupos_secao, malhas_proj = [], [], [], []
    for id_step, gid in sorted(elementos_validos, key=lambda item: (str(item[1]), int(item[0]))):
        v, t = np.asarray(malhas_mundo[gid][0], dtype=np.float64), np.asarray(malhas_mundo[gid][1], dtype=np.int64)
        classe = str(f.by_id(int(id_step)).is_a() or "IfcProduct")
        if float(v[:, 2].min()) > z + eps:
            continue
        enviados.append(int(id_step))
        if float(v[:, 2].max()) <= z + eps:
            malhas_proj.append((v, t))
            continue
        v_ab, t_ab, segs = corte_plano.cortar_malha_no_plano(v, t, z)
        fechados, abertos = aneis.aneis_de_segmentos(segs)
        grupos = oclusores._agrupar_aneis(fechados)
        assert fechados and not abertos and grupos
        pecas_secao.append((str(gid), classe, fechados, abertos, 0.0, 0.0))
        grupos_secao.extend(rings for rings, _ in grupos)
        if len(t_ab) > 0:
            malhas_proj.append((v_ab, t_ab))
    pols_proj = [p for ps in visibilidade.linhas_visiveis_multi(malhas_proj, angulo_graus=0.001, trabalhadores=1) for p in ps]
    if pols_proj and grupos_secao:
        pols_proj = recorte.recortar_fora_dos_aneis(pols_proj, grupos_secao, encolher=5e-4)
    svg, n_paths = planta_cache._montar_svg(str(vista["pavimento"]), pecas_secao, pols_proj)
    return svg, n_paths, enviados


# ---------- SANIDADE (PASSA HOJE) ----------
def test_sanidade_malhas_sinteticas_disparam_agrupar_aneis_none():
    """Cada malha sintetica produz aneis fechados reais recusados por `_agrupar_aneis`."""
    for nome, malha, n_fech, n_ab in (
        ("area_quase_zero", _malha_anel_area_quase_zero_np(), 1, 0),
        ("bowtie", _malha_anel_bowtie_area_zero_np(), 1, 0),
        ("furo_sem_pai", _malha_furo_sem_pai_np(), 2, 0),
        ("mista", _malha_mista_nao_agrupavel_e_aberta_np(), 1, 1),
    ):
        _, _, segs = corte_plano.cortar_malha_no_plano(*malha, 1.2)
        fechados, abertos = aneis.aneis_de_segmentos(segs)
        assert (len(fechados), len(abertos)) == (n_fech, n_ab), nome
        assert oclusores._agrupar_aneis(fechados) is None, nome


# ---------- REQ 1: ACEITACAO DE ANEIS FECHADOS NAO AGRUPAVEIS ----------
@pytest.mark.parametrize(
    ("classe_ruim", "fabrica_ruim"),
    [
        pytest.param("IfcFurnishingElement", lambda: _malha_anel_area_quase_zero_np(20.0, 0.0), id="area_quase_zero"),
        pytest.param("IfcDoor", lambda: _malha_anel_bowtie_area_zero_np(20.0, 0.0), id="bowtie_area_zero"),
        pytest.param("IfcWindow", lambda: _malha_furo_sem_pai_np(20.0, 0.0), id="furo_sem_pai"),
    ],
)
def test_req1_pavimento_com_1_peca_nao_agrupavel_aceito_e_boas_inalteradas(classe_ruim, fabrica_ruim):
    """4 boas + laje + 1 nao agrupavel: aceita, desenha ruim como linhas, boas identicas, parciais=1."""
    boas = [*_boas(4), (14, "G_LAJE", "IfcSlab", _caixa_np(0.0, -0.5, -0.2, 14.5, 2.0, 0.0))]
    r_base, mot_base = planta_cache.desenhar_planta_cache(*_montar_cena_numpy(boas, altura_corte_m=1.2, pav_guid="PAV_T24H"))
    assert mot_base is None and r_base is not None and r_base["secoes_parciais"] == 0
    parsed_base = _parse_svg(r_base["svg"])

    malha_ruim = fabrica_ruim()
    resp, motivo = planta_cache.desenhar_planta_cache(
        *_montar_cena_numpy([*boas, (20, "G_RUIM", classe_ruim, malha_ruim)], altura_corte_m=1.2, pav_guid="PAV_T24H")
    )
    assert motivo is None and resp is not None and resp["ok"] is True
    assert type(resp["secoes_parciais"]) is int and resp["secoes_parciais"] == 1
    assert set(resp["enviados"]) == {10, 11, 12, 13, 14, 20} and "-0.000000" not in resp["svg"]

    parsed = _parse_svg(resp["svg"])
    assert set(parsed.cut_by_guid.keys()) == {"G_BOA_0", "G_BOA_1", "G_BOA_2", "G_BOA_3", "G_RUIM"}
    _verificar_linhas_peca_ruim(parsed, "G_RUIM", malha_ruim, 1.2)
    for gid in ("G_BOA_0", "G_BOA_1", "G_BOA_2", "G_BOA_3"):
        assert _xml_grupos(parsed, gid) == _xml_grupos(parsed_base, gid), f"peca boa {gid} alterada"

    segs_base = _polilinhas_para_segs(_polilinhas_mundo(parsed_base.proj_groups))
    segs_novo = _polilinhas_para_segs(_polilinhas_mundo(parsed.proj_groups))
    assert float(_dist_pontos_a_segs(_pontos_de_segs(segs_base), segs_novo).max()) <= 1e-5
    assert "cut" in (_parse_svg(estilo.aplicar_estilo(resp["svg"], "1:50")).cut_by_guid["G_RUIM"][0].get("class") or "").split()


def test_req1_agrupar_aneis_retorna_lista_vazia_mesma_politica(monkeypatch):
    """`_agrupar_aneis` devolvendo `[]` para 1 peca em 4 cortadas segue a mesma politica."""
    real_agrupar, chamadas = oclusores._agrupar_aneis, {"n": 0}

    def agrupar_vazio_na_quarta(fechados):
        chamadas["n"] += 1
        return [] if chamadas["n"] == 4 else real_agrupar(fechados)

    monkeypatch.setattr(oclusores, "_agrupar_aneis", agrupar_vazio_na_quarta)
    malha_alvo = _caixa_np(12.0, 0.0, 0.0, 14.0, 0.4, 2.8)
    pecas = [
        *_boas(3, prefixo="G_01_BOA"), (13, "G_04_VAZIO", "IfcDoor", malha_alvo),
        (14, "G_05_BARRA", "IfcSlab", _caixa_np(12.9, -0.5, 0.0, 13.1, 1.0, 0.2)),
    ]
    resp, motivo = planta_cache.desenhar_planta_cache(*_montar_cena_numpy(pecas, altura_corte_m=1.2))
    assert motivo is None and resp is not None and resp["ok"] is True and resp["secoes_parciais"] == 1
    parsed = _parse_svg(resp["svg"])
    _verificar_linhas_peca_ruim(parsed, "G_04_VAZIO", malha_alvo, 1.2)
    segs_proj = _polilinhas_para_segs(_polilinhas_mundo(parsed.proj_groups))
    assert float(_dist_pontos_a_segs(np.array([[12.9, 0.2], [13.1, 0.2]]), segs_proj).max()) <= 1e-3


# ---------- REQ 2: LIMITE ceil(0.25 * n_cortadas) ----------
def test_req2_limite_25_porcento_4_cortadas_1_passa_2_cai():
    """4 cortadas: 1 ruim (25%) passa; 2 ruins (>25%) voltam (None, 'secao_aberta')."""
    base_4 = [*_boas(3, passo=6.0), (13, "G_3", "IfcFurnishingElement", _malha_furo_sem_pai_np(18.0, 0.0))]
    r1, mot1 = planta_cache.desenhar_planta_cache(*_montar_cena_numpy(base_4, altura_corte_m=1.2))
    assert mot1 is None and r1 is not None and r1["ok"] is True and r1["secoes_parciais"] == 1
    assert len(_parse_svg(r1["svg"]).cut_by_guid) == 4
    duas_ruins = [*base_4[:2], (12, "G_2", "IfcDoor", _malha_anel_area_quase_zero_np(12.0, 0.0)), base_4[3]]
    assert planta_cache.desenhar_planta_cache(*_montar_cena_numpy(duas_ruins, altura_corte_m=1.2)) == (None, "secao_aberta")


@pytest.mark.parametrize(
    ("n_cortadas", "n_ruins", "deve_aceitar"),
    [(1, 1, True), (2, 1, True), (2, 2, False), (4, 1, True), (4, 2, False), (5, 2, True), (5, 3, False), (8, 2, True), (8, 3, False)],
)
def test_req2_limite_25_porcento_fronteira_parametrizado(n_cortadas: int, n_ruins: int, deve_aceitar: bool):
    """Fronteira exata ceil(0.25 * n_cortadas) alternando area quase zero e furo sem pai."""
    assert (n_ruins <= math.ceil(0.25 * n_cortadas)) is deve_aceitar
    pecas = [
        (10 + i, f"G_RUIM_{i:02d}", "IfcFurnishingElement",
         _malha_anel_area_quase_zero_np(i * 6.0, 0.0) if (i % 2 == 0) else _malha_furo_sem_pai_np(i * 6.0, 0.0))
        if i < n_ruins else (10 + i, f"G_BOA_{i:02d}", "IfcWall", _caixa_np(i * 6.0, 0.0, 0.0, i * 6.0 + 2.0, 0.3, 2.8))
        for i in range(n_cortadas)
    ]
    resp, motivo = planta_cache.desenhar_planta_cache(*_montar_cena_numpy(pecas, altura_corte_m=1.2))
    if deve_aceitar:
        assert motivo is None and resp is not None and resp["ok"] is True
        assert type(resp["secoes_parciais"]) is int and resp["secoes_parciais"] == n_ruins
        assert len(_parse_svg(resp["svg"]).cut_by_guid) == n_cortadas
    else:
        assert resp is None and motivo == "secao_aberta"


def test_req2_limite_combina_t24f_abertos_e_t24h_nao_agrupaveis():
    """Parciais T24f (cadeia aberta) e T24h (aneis nao agrupaveis) somam no mesmo limite."""
    base = [
        (10, "G_T24F", "IfcWall", _caixas_fundidas_em_t_np(0.0, 0.0)),
        (11, "G_T24H", "IfcWindow", _malha_furo_sem_pai_np(6.0, 0.0)),
        *_boas(2, id0=12, x0=14.0),
    ]
    assert planta_cache.desenhar_planta_cache(*_montar_cena_numpy(base, altura_corte_m=1.2)) == (None, "secao_aberta")
    r5, mot5 = planta_cache.desenhar_planta_cache(
        *_montar_cena_numpy([*base, (14, "G_BOA_3", "IfcWall", _caixa_np(22.0, 0.0, 0.0, 24.0, 0.3, 2.8))], altura_corte_m=1.2)
    )
    assert mot5 is None and r5 is not None and r5["ok"] is True and r5["secoes_parciais"] == 2
    assert len(_parse_svg(r5["svg"]).cut_by_guid) == 5


def test_req2_denominador_conta_apenas_cortadas():
    """Pecas abaixo/acima do plano nao inflam o denominador do limite de 25%."""
    pecas = [
        (10, "G_RUIM_1", "IfcDoor", _malha_anel_area_quase_zero_np(0.0, 0.0)),
        (11, "G_RUIM_2", "IfcWindow", _malha_furo_sem_pai_np(4.0, 0.0)),
        *[(20 + i, f"G_ABAIXO_{i:02d}", "IfcSlab", _caixa_np(i * 2.0, 6.0, -0.2, i * 2.0 + 1.0, 7.0, 0.0)) for i in range(10)],
        *[(40 + i, f"G_ACIMA_{i:02d}", "IfcBeam", _caixa_np(i * 2.0, 9.0, 2.2, i * 2.0 + 1.0, 9.4, 2.8)) for i in range(4)],
    ]
    assert planta_cache.desenhar_planta_cache(*_montar_cena_numpy(pecas, altura_corte_m=1.2)) == (None, "secao_aberta")


# ---------- REQ 3: NAO-REGRESSAO PECAS BOAS BYTE A BYTE (PASSA HOJE) ----------
def test_req3_pecas_totalmente_boas_svg_identico_byte_a_byte():
    """Cena so com pecas boas (caixas + moldura com furo + bloco no furo + laje + viga): SVG byte a byte igual."""
    ext = [(10.0, 0.0), (12.0, 0.0), (12.0, 2.0), (10.0, 2.0)]
    furo = [(10.5, 0.5), (11.5, 0.5), (11.5, 1.5), (10.5, 1.5)]
    pecas = [
        *_boas(2), (12, "G_MOLDURA", "IfcWall", _tubo_np(ext, furo, 0.0, 2.8)),
        (13, "G_BLOCO_FURO", "IfcFurnishingElement", _caixa_np(10.8, 0.8, 0.0, 11.2, 1.2, 0.6)),
        (14, "G_LAJE", "IfcSlab", _caixa_np(0.0, -0.5, -0.2, 13.0, 2.5, 0.0)),
        (15, "G_VIGA_ACIMA", "IfcBeam", _caixa_np(0.0, 0.0, 2.2, 3.0, 0.3, 2.8)),
    ]
    f, pedido, malhas, ev = _montar_cena_numpy(pecas, altura_corte_m=1.2, pav_guid="PAV_BOAS")
    svg_ref, n_paths_ref, enviados_ref = _svg_referencia_boas(f, pedido, malhas, ev)
    resp, motivo = planta_cache.desenhar_planta_cache(f, pedido, malhas, ev)
    assert motivo is None and resp is not None and resp["ok"] is True
    assert type(resp["secoes_parciais"]) is int and resp["secoes_parciais"] == 0
    assert resp["svg"] == svg_ref and resp["n_paths"] == n_paths_ref and resp["enviados"] == enviados_ref


# ---------- REQ 4: DETERMINISMO E IMUTABILIDADE ----------
def test_req4_determinismo_sha256_3_rodadas_ordem_reversa_e_threads():
    """SHA-256 identico em 3 rodadas, entrada reversa e threads=4 com pecas nao agrupaveis."""
    pecas = [
        *_boas(6, id0=10, x0=18.0),
        (20, "G_01_RUIM_A0", "IfcDoor", _malha_anel_area_quase_zero_np(0.0, 0.0)),
        (21, "G_02_RUIM_FSP", "IfcWindow", _malha_furo_sem_pai_np(6.0, 0.0)),
        (22, "G_09_LAJE", "IfcSlab", _caixa_np(0.0, -0.5, -0.2, 42.0, 4.5, 0.0)),
    ]
    f1, p1, m1, e1 = _montar_cena_numpy(pecas, altura_corte_m=1.2, threads=1)
    shas = []
    for _ in range(3):
        r, mot = planta_cache.desenhar_planta_cache(f1, p1, m1, e1)
        assert mot is None and r is not None and r["secoes_parciais"] == 2
        shas.append(_sha256(r["svg"]))
    assert shas[0] == shas[1] == shas[2]
    r_rev, mot_rev = planta_cache.desenhar_planta_cache(*_montar_cena_numpy(list(reversed(pecas)), altura_corte_m=1.2, threads=1))
    assert mot_rev is None and _sha256(r_rev["svg"]) == shas[0]
    r_t4, mot_t4 = planta_cache.desenhar_planta_cache(*_montar_cena_numpy(pecas, altura_corte_m=1.2, threads=4))
    assert mot_t4 is None and _sha256(r_t4["svg"]) == shas[0]


def test_req4_nao_muta_malhas_mundo_nem_pedido_aceito_e_utm():
    """`malhas_mundo` (read-only) e `pedido` nao sao mutados no caminho T24h, inclusive em UTM."""
    ox, oy = 500_000.123456, 7_500_000.654321
    base = [*_boas(3), (13, "G_RUIM_FSP", "IfcWindow", _malha_furo_sem_pai_np(14.0, 0.0)),
            (14, "G_LAJE", "IfcSlab", _caixa_np(0.0, -0.5, -0.2, 20.0, 4.5, 0.0))]
    f, pedido, malhas, ev = _montar_cena_numpy([(i, g, c, _transladar_malha(m, ox, oy)) for i, g, c, m in base], altura_corte_m=1.2)
    snap = _congelar_snapshot(malhas, pedido)
    resp, motivo = planta_cache.desenhar_planta_cache(f, pedido, malhas, ev)
    assert motivo is None and resp is not None and resp["ok"] is True and resp["secoes_parciais"] == 1
    _checar_imutavel(malhas, pedido, *snap)


def test_req4_nao_muta_malhas_mundo_na_queda_acima_limite():
    """Na queda `secao_aberta` (>25%), `malhas_mundo` read-only e `pedido` ficam intactos."""
    pecas = [*_boas(2), (12, "G_RUIM_0", "IfcDoor", _malha_anel_area_quase_zero_np(8.0, 0.0)),
             (13, "G_RUIM_1", "IfcWindow", _malha_furo_sem_pai_np(12.0, 0.0))]
    f, pedido, malhas, ev = _montar_cena_numpy(pecas, altura_corte_m=1.2)
    snap = _congelar_snapshot(malhas, pedido)
    assert planta_cache.desenhar_planta_cache(f, pedido, malhas, ev) == (None, "secao_aberta")
    _checar_imutavel(malhas, pedido, *snap)


# ---------- REQ 5: MUTANTES ----------
def test_mutante_01_peca_ruim_some_do_svg():
    """Mutante 1: pular ou omitir a peca nao agrupavel do SVG ou de `enviados` deve falhar."""
    malha_ruim = _malha_furo_sem_pai_np(14.0, 0.0)
    resp, motivo = planta_cache.desenhar_planta_cache(
        *_montar_cena_numpy([*_boas(3), (19, "G_JANELA_RUIM", "IfcWindow", malha_ruim)], altura_corte_m=1.2)
    )
    assert motivo is None and resp is not None and resp["ok"] is True
    assert 19 in resp["enviados"], "peca nao agrupavel omitida de enviados"
    parsed = _parse_svg(resp["svg"])
    assert "G_JANELA_RUIM" in parsed.cut_by_guid, "peca nao agrupavel sumiu do SVG"
    _verificar_linhas_peca_ruim(parsed, "G_JANELA_RUIM", malha_ruim, 1.2)


def test_mutante_02_peca_ruim_entra_na_tampa(monkeypatch):
    """Mutante 2: colocar aneis nao agrupaveis em `grupos_secao` apagaria piso sob a peca ruim."""
    grupos_passados: list[list] = []
    real_recorte = recorte.recortar_fora_dos_aneis
    monkeypatch.setattr(
        recorte, "recortar_fora_dos_aneis",
        lambda pols, grupos, *a, **k: (grupos_passados.append(list(grupos)), real_recorte(pols, grupos, *a, **k))[1],
    )
    pecas = [
        (10, "G_RUIM_FSP", "IfcFurnishingElement", _malha_furo_sem_pai_np(0.0, 0.0)),
        (11, "G_BOA_ALVO", "IfcWall", _caixa_np(10.0, 0.0, 0.0, 12.0, 1.0, 2.8)),
        *_boas(2, id0=12, x0=15.0, passo=5.0),
        (14, "G_BARRA_SOB_RUIM", "IfcSlab", _caixa_np(0.6, -0.5, 0.0, 0.9, 4.5, 0.2)),
        (15, "G_BARRA_SOB_BOA", "IfcSlab", _caixa_np(10.9, -0.5, 0.0, 11.1, 1.5, 0.2)),
    ]
    resp, motivo = planta_cache.desenhar_planta_cache(*_montar_cena_numpy(pecas, altura_corte_m=1.2))
    assert motivo is None and resp is not None and resp["ok"] is True
    assert len(grupos_passados) == 1 and len(grupos_passados[0]) == 3
    segs_proj = _polilinhas_para_segs(_polilinhas_mundo(_parse_svg(resp["svg"]).proj_groups))
    assert float(_dist_pontos_a_segs(np.array([[0.6, 1.0], [0.9, 1.0]]), segs_proj).max()) <= 1e-3, "peca ruim tampou piso"
    assert float(_dist_pontos_a_segs(np.array([[10.9, 0.5], [11.1, 0.5]]), segs_proj).min()) > 0.05, "peca boa nao tampou"


def test_mutante_03_contagem_secoes_parciais_errada():
    """Mutante 3: nao contar (0) ou contar em dobro (2) quando a peca tem fechado nao agrupavel + aberto."""
    boas3 = _boas(3)
    r1, mot1 = planta_cache.desenhar_planta_cache(
        *_montar_cena_numpy([*boas3, (13, "G_SO_FECH_RUIM", "IfcDoor", _malha_anel_area_quase_zero_np(12.0, 0.0))], altura_corte_m=1.2)
    )
    assert mot1 is None and r1 is not None and type(r1["secoes_parciais"]) is int and r1["secoes_parciais"] == 1
    r2, mot2 = planta_cache.desenhar_planta_cache(
        *_montar_cena_numpy([*boas3, (13, "G_MISTA_RUIM", "IfcFurnishingElement", _malha_mista_nao_agrupavel_e_aberta_np(12.0, 0.0))], altura_corte_m=1.2)
    )
    assert mot2 is None and r2 is not None and type(r2["secoes_parciais"]) is int and r2["secoes_parciais"] == 1


def test_mutante_04_limite_25_ignorado():
    """Mutante 4: ignorar o limite de 25% para pecas nao agrupaveis ou aceitar peca sem segmentos."""
    assert planta_cache.desenhar_planta_cache(
        *_montar_cena_numpy([*_boas(2), (12, "G_R0", "IfcWindow", _malha_furo_sem_pai_np(10.0, 0.0)),
                             (13, "G_R1", "IfcWindow", _malha_furo_sem_pai_np(16.0, 0.0))], altura_corte_m=1.2)
    ) == (None, "secao_aberta")
    assert planta_cache.desenhar_planta_cache(
        *_montar_cena_numpy([*_boas(1), (11, "G_R0", "IfcDoor", _malha_anel_area_quase_zero_np(4.0, 0.0)),
                             (12, "G_R1", "IfcDoor", _malha_anel_area_quase_zero_np(8.0, 0.0)),
                             (13, "G_R2", "IfcDoor", _malha_anel_area_quase_zero_np(12.0, 0.0))], altura_corte_m=1.2)
    ) == (None, "secao_aberta")
    assert planta_cache.desenhar_planta_cache(
        *_montar_cena_numpy([*_boas(4), (99, "G_SEM_SEGS", "IfcWall", _malha_sem_segmentos_corte_np(24.0, 0.0, 0.0, 26.0, 0.5, 2.8))], altura_corte_m=1.2)
    ) == (None, "secao_aberta")
