# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo T19j4b: opção `motor_janelas` (bool, padrão False) do pedido de `desenho` de planta, com `motor_visivel`.
Contrato (cartão F0-S06-T19j4b): com True, janelas/portas (IfcWindow/IfcDoor) de `hlr_cands` com malha válida saem pelo motor
(`linhas_peca_cortada` + `oclusores_da_peca`) e entram em `motor_pecas`; `None`/oclusor impossível (móvel sobre a caixa, peça baixa
alta, seção aberta, plano) => HLR (fora de `motor_pecas`, grupo SVG igual ao do HLR). Com False/ausente o SVG é IDÊNTICO.
Oráculo por amostragem: as linhas do HLR (batente) são cobertas (>= 99,9%, 1 mm); o motor não passa do HLR; nenhuma linha a mais de 2 mm
dentro do anel das paredes (esperado calculado à mão a partir da geometria do modelo). Modelo: parede P0 5 x 0,25 x 3, porta x 1..2 e janela
x 3..4 (z 0,9..1,9), corte z 1,2. Nunca compara com a implementação."""
from __future__ import annotations

import copy

import numpy as np
import pytest
import s06_t07_aux as X
import s06_t07b_aux as B
from s05_conteudo_aux import _limpa, exigir  # noqa: F401  (autouse)
from s06_t17_aux import pedido_planta

import obim_geometria.desenho as D

VAOS = (("porta", "IfcDoor", 1.0, 0.0, 1.0, 2.0), ("jan", "IfcWindow", 3.0, 0.9, 1.0, 1.0))
PORTA = VAOS[:1]
PAREDE = [(0, 0, 1, .25), (2, 0, 3, .25), (4, 0, 5, .25)]  # seção da parede no corte (vãos x 1..2 e 3..4), a mão
PAREDE_PORTA = [(0, 0, 1, .25), (2, 0, 5, .25)]  # só com o vão da porta
TOL = 1e-3


# ---------- montagem e execução ----------
def cena(extra=None, vaos=VAOS):
    exigir()
    f, pavs, g = B.modelo("IFC4", n_pav=1, vaos=vaos)
    if extra:
        extra(f, pavs[0], g)
    return f, g, B.planta(f, pavs[0], "V")


def pedido(f, gid, pasta):
    return pedido_planta(f, gid, pasta)


def roda(p, **opc):
    r = D.processar({**copy.deepcopy(p), "motor_visivel": True, **opc})
    assert r["ok"] is True
    return r


def linhas(r, guid):
    """Polilinhas (n,2) do elemento no SVG, em coordenadas do mundo (o SVG inverte y)."""
    txt = B.grupo(r["svg"], guid)
    return [np.array([(x, -y) for x, y in pl], float) for pl in B.subcaminhos(txt)] if txt else []


def segs(pls):
    return np.vstack([np.c_[l[:-1], l[1:]] for l in pls if len(l) > 1] or [np.zeros((0, 4))])


def amostras(pls, passo=0.005):
    out = []
    for a, b, c, d in segs(pls):
        n = max(1, int(np.ceil(np.hypot(c - a, d - b) / passo)))
        u = (np.arange(n) + 0.5) / n
        out.append(np.c_[a + u * (c - a), b + u * (d - b)])
    return np.vstack(out) if out else np.zeros((0, 2))


def dist(P, S):
    if len(S) == 0 or len(P) == 0:
        return np.full(len(P), np.inf)
    a, d = S[:, :2], S[:, 2:] - S[:, :2]
    w = P[:, None, :] - a[None]
    u = np.clip((w * d[None]).sum(2) / np.maximum((d ** 2).sum(1)[None], 1e-30), 0, 1)
    return np.sqrt(((w - u[..., None] * d[None]) ** 2).sum(2)).min(1)


def fundo(P, ret, e=2e-3):
    """Quais pontos estão a mais de `e` DENTRO de algum retângulo (x0, y0, x1, y1)."""
    m = np.zeros(len(P), bool)
    for x0, y0, x1, y1 in ret:
        m |= (P[:, 0] > x0 + e) & (P[:, 0] < x1 - e) & (P[:, 1] > y0 + e) & (P[:, 1] < y1 - e)
    return m


def pelo_motor(f, g, r, nome):
    return f.by_guid(g[nome]).id() in (r.get("motor_pecas") or [])


# ---------- janela e porta ----------
@pytest.mark.parametrize("nome,vaos,parede", [("jan0", VAOS, PAREDE), ("porta0", PORTA, PAREDE_PORTA)])
def test_janela_e_porta_pelo_motor_cobrem_o_hlr_e_nada_dentro_da_parede(tmp_path, nome, vaos, parede):
    f, g, gid = cena(vaos=vaos)
    p = pedido(f, gid, tmp_path / "p")
    base, com = roda(p), roda(p, motor_janelas=True)
    assert not pelo_motor(f, g, base, nome) and pelo_motor(f, g, com, nome)
    hlr, mot = linhas(base, g[nome]), linhas(com, g[nome])
    assert hlr and mot
    assert (dist(amostras(hlr), segs(mot)) <= TOL).mean() >= 0.999  # cobre o contorno do batente
    assert (dist(amostras(mot), segs(hlr)) <= TOL).all()  # e não passa dele
    assert not fundo(amostras(mot), parede).any()


def test_janela_e_porta_na_mesma_parede_ambas_pelo_motor(tmp_path):
    # o trecho de parede sob a janela (topo z 0,9) fica fora da seção, mas longe da caixa da porta: não oculta a porta (regra do degrau só dentro da caixa)
    f, g, gid = cena()
    p = pedido(f, gid, tmp_path / "p")
    base, com = roda(p), roda(p, motor_janelas=True)
    for nome in ("jan0", "porta0"):
        assert not pelo_motor(f, g, base, nome) and pelo_motor(f, g, com, nome)
        hlr, mot = linhas(base, g[nome]), linhas(com, g[nome])
        assert (dist(amostras(hlr), segs(mot)) <= TOL).mean() >= 0.999
        assert (dist(amostras(mot), segs(hlr)) <= TOL).all()
        assert not fundo(amostras(mot), PAREDE).any()


def test_flag_false_ou_ausente_svg_identico(tmp_path):
    f, g, gid = cena()
    p = pedido(f, gid, tmp_path / "p")
    a, b = roda(p), roda(p, motor_janelas=False)
    assert a["svg"] == b["svg"] and a.get("motor_pecas") == b.get("motor_pecas")
    assert roda(p, motor_janelas=True)["svg"] is not None  # a opção existe e roda


def test_janela_embutida_na_parede_so_fica_a_borda_colinear(tmp_path):
    def extra(f, pav, g):
        j = X.caixa(f, "IfcWindow", "emb", 4.2, 0.0, 0.9, 0.6, 0.25, 1.0)  # dentro da parede cheia, x 4,2..4,8
        g["emb"] = j.GlobalId
        X.conter(f, pav, j)
    f, g, gid = cena(extra)
    r = roda(pedido(f, gid, tmp_path / "p"), motor_janelas=True)
    assert pelo_motor(f, g, r, "emb")
    mot = linhas(r, g["emb"])
    assert not fundo(amostras(mot), PAREDE + [(4, 0, 5, .25)]).any()  # nada além da borda: x 4,2 e 4,8 ficam ocultos
    S = segs(mot)
    esperado = np.vstack([np.c_[np.linspace(4.205, 4.795, 119), np.full(119, y)] for y in (0.0, 0.25)])
    assert (dist(esperado, S) <= TOL).all()  # as bordas y=0 e y=0,25 colineares com a parede continuam


@pytest.mark.parametrize("como_caixa", [False, True])
def test_movel_sobre_a_caixa_da_janela_vai_ao_hlr(tmp_path, como_caixa):
    def extra(f, pav, g):
        X.conter(f, pav, X.caixa(f, X.MOVEL["IFC4"], "Mv", 3.3, 0.05, 0.0, 0.3, 0.15, 1.0))
    f, g, gid = cena(extra)
    p = pedido(f, gid, tmp_path / "p")
    base, com = roda(p, moveis_como_caixa=como_caixa), roda(p, moveis_como_caixa=como_caixa, motor_janelas=True)
    assert not pelo_motor(f, g, com, "jan0") and pelo_motor(f, g, com, "porta0")  # só a janela cai; a porta segue pelo motor
    assert B.grupo(com["svg"], g["jan0"]) == B.grupo(base["svg"], g["jan0"])  # saída do HLR, igual à de antes


def test_parede_dupla_oculta_o_que_esta_dentro_da_uniao(tmp_path):
    def extra(f, pav, g):
        X.conter(f, pav, X.caixa(f, "IfcWall", "PB", 0.0, 0.1, 0.0, 5.0, 0.25, 3.0))  # segunda parede y 0,1..0,35 sobre a janela
    f, g, gid = cena(extra)
    p = pedido(f, gid, tmp_path / "p")
    com = roda(p, motor_janelas=True)
    assert pelo_motor(f, g, com, "jan0")
    S = segs(linhas(com, g["jan0"]))
    visivel = np.vstack([np.c_[np.linspace(3.005, 3.995, 199), np.zeros(199)],  # aresta y=0 (fora da parede nova)
                         np.c_[np.full(19, 3.0), np.linspace(0.005, 0.095, 19)], np.c_[np.full(19, 4.0), np.linspace(0.005, 0.095, 19)]])
    oculto = np.vstack([np.c_[np.linspace(3.01, 3.99, 99), np.full(99, 0.25)],  # aresta y=0,25: dentro da parede nova
                        np.c_[np.full(25, 3.0), np.linspace(0.115, 0.245, 25)], np.c_[np.full(25, 4.0), np.linspace(0.115, 0.245, 25)]])
    assert (dist(visivel, S) <= TOL).all()
    assert (dist(oculto, S) > TOL).all()


# ---------- lacunas leves da j4a (oclusores_da_peca) ----------
def _prisma(poly, z0, z1, tris):
    n = len(poly)
    t = list(tris) + [tuple(n + i for i in c[::-1]) for c in tris]
    for i in range(n):
        j = (i + 1) % n
        t += [(i, j, n + j), (i, n + j, n + i)]
    return np.array([(x, y, z) for z in (z0, z1) for x, y in poly], float), np.array(t, int)


def _quad(x0, y0, x1, y1, z0, z1):
    return _prisma([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], z0, z1, [(0, 1, 2), (0, 2, 3)])


def _juntar(*ms):
    o = np.cumsum([0] + [len(v) for v, _ in ms])
    return np.vstack([v for v, _ in ms]), np.vstack([t + k for (_, t), k in zip(ms, o)])


def test_face_horizontal_exatamente_em_zmin_mais_tol_e_none():
    from obim_geometria.oclusores import oclusores_da_peca
    peca = _juntar(_quad(0, 0, 1, 0.2, 0.0, 3.0), _quad(1.2, 0.05, 1.6, 0.15, 0.2, 0.75))  # topo do calço em 0,5 + 0,25 (exato em binário)
    assert oclusores_da_peca((0.9, 0.05, 2.0, 0.15, 0.5), [peca], 1.5, tol_z=0.25) is None


def test_anel_concavo_em_U_com_pontos_no_miolo_dos_dois_bracos_nao_e_none():
    from obim_geometria.oclusores import oclusores_da_peca
    u = [(0, 0), (3, 0), (3, 2), (2, 2), (2, 1), (1, 1), (1, 2), (0, 2)]  # U: base y 0..1, braços x 0..1 e 2..3 até y 2
    corpo = _prisma(u, 0.0, 3.0, [(0, 1, 4), (0, 4, 5), (0, 5, 6), (0, 6, 7), (1, 2, 3), (1, 3, 4)])
    # um bloco no miolo de cada braço, acima do zmin da janela: tudo cabe na seção; o vão entre os braços não pode ser testado
    r = oclusores_da_peca((0.9, 1.2, 2.1, 1.8, 0.85), [_juntar(corpo, _quad(.4, 1.3, .6, 1.7, .2, 1.2), _quad(2.4, 1.3, 2.6, 1.7, .2, 1.2))], 1.5)
    assert r is not None and len(r) == 1


# ---------- rodada 2 (Opus): plano na borda, soleira baixa, comprimento zero, pré-filtro, falha isolada ----------
@pytest.mark.parametrize("corte", [0.9, 1.9])
def test_none_da_j4a_corte_em_z0_ou_z1_da_janela_vai_ao_hlr(tmp_path, corte):
    f, g, gid = cena()
    p = pedido(f, gid, tmp_path / "p")
    p["vista"]["altura_corte_m"] = corte  # janela z 0,9..1,9: o plano passa pela face dela (None do j3, nunca [])
    base, com = roda(p), roda(p, motor_janelas=True)
    assert not pelo_motor(f, g, com, "jan0")
    assert B.grupo(com["svg"], g["jan0"]) == B.grupo(base["svg"], g["jan0"])


def test_none_da_j3_so_da_janela_vai_ao_hlr(tmp_path, monkeypatch):
    from obim_geometria import peca_cortada
    orig = peca_cortada.linhas_peca_cortada

    def none_na_janela(verts, tris, z, grupos=(), **k):
        return None if abs(np.asarray(verts)[:, 0].min() - 3.0) < 1e-3 else orig(verts, tris, z, grupos, **k)  # janela x 3..4
    monkeypatch.setattr(peca_cortada, "linhas_peca_cortada", none_na_janela)
    f, g, gid = cena()
    p = pedido(f, gid, tmp_path / "p")
    base, com = roda(p), roda(p, motor_janelas=True)
    assert not pelo_motor(f, g, com, "jan0") and pelo_motor(f, g, com, "porta0")  # None vira HLR, nunca []
    assert B.grupo(com["svg"], g["jan0"]) == B.grupo(base["svg"], g["jan0"])


def test_soleira_comum_na_caixa_de_janela_saliente_nao_entra_no_motor(tmp_path):
    def extra(f, pav, g):
        j = X.caixa(f, "IfcWindow", "sal", 2.2, -0.1, 0.9, 0.6, 0.35, 1.0)  # janela saliente: y -0,1..0,25 (a parede é y 0..0,25)
        s = X.caixa(f, "IfcBuildingElementProxy", "sol", 2.3, -0.1, 0.0, 0.4, 0.08, 0.3)  # z 0..0,3, y -0,1..-0,02: na caixa da janela, fora da parede
        g["sal"], g["sol"] = j.GlobalId, s.GlobalId
        X.conter(f, pav, j, s)
    f, g, gid = cena(extra)
    p = pedido(f, gid, tmp_path / "p")
    base, com = roda(p), roda(p, motor_janelas=True)
    assert not pelo_motor(f, g, base, "sol") and not pelo_motor(f, g, com, "sol")  # a caixa da janela segue em inel_boxes
    assert B.grupo(com["svg"], g["sol"]) == B.grupo(base["svg"], g["sol"])


def test_polilinha_de_comprimento_zero_nao_vai_ao_svg(tmp_path, monkeypatch):
    from obim_geometria import peca_cortada
    orig, chamadas = peca_cortada.linhas_peca_cortada, []

    def com_ponto(*a, **k):
        r = orig(*a, **k)
        chamadas.append(r)
        return r if not r else r + [np.array([r[0][0], r[0][0]])]  # [[x,y],[x,y]]
    monkeypatch.setattr(peca_cortada, "linhas_peca_cortada", com_ponto)
    f, g, gid = cena()
    r = roda(pedido(f, gid, tmp_path / "p"), motor_janelas=True)
    assert chamadas and pelo_motor(f, g, r, "jan0")
    for nome in ("jan0", "porta0"):
        for pl in linhas(r, g[nome]):
            assert len(pl) >= 2 and not np.all(pl == pl[0]), "polilinha de comprimento zero no SVG"


def test_parede_longe_da_janela_nao_entra_em_outras(tmp_path, monkeypatch):
    from obim_geometria import oclusores
    orig, vistas = oclusores.oclusores_da_peca, []

    def espia(caixa, outras, z, **k):
        outras = list(outras)
        vistas.append((tuple(caixa), [(v[:, :2].min(0), v[:, :2].max(0)) for v, _t in outras]))
        return orig(caixa, outras, z, **k)
    monkeypatch.setattr(oclusores, "oclusores_da_peca", espia)

    def extra(f, pav, g):
        X.conter(f, pav, X.caixa(f, "IfcWall", "PL", 0.0, 2.0, 0.0, 5.0, 0.25, 3.0))  # y 2..2,25: >1 mm de folga da janela (y 0..0,25)
    f, g, gid = cena(extra)
    r = roda(pedido(f, gid, tmp_path / "p"), motor_janelas=True)
    assert pelo_motor(f, g, r, "jan0")
    cx = [v for v in vistas if abs(v[0][0] - 3.0) < 1e-3 and abs(v[0][2] - 4.0) < 1e-3]
    assert cx, "oclusores_da_peca não foi chamado para a janela"
    for caixa, caixas_outras in cx:
        assert caixas_outras, "a parede da própria janela tem de entrar"
        for lo, hi in caixas_outras:  # toda peça de `outras` cruza a caixa XY da janela + 1 mm
            assert hi[0] >= caixa[0] - 1e-3 and lo[0] <= caixa[2] + 1e-3 and hi[1] >= caixa[1] - 1e-3 and lo[1] <= caixa[3] + 1e-3


def test_falha_em_uma_janela_so_leva_essa_janela_ao_hlr(tmp_path, monkeypatch):
    from obim_geometria import peca_cortada
    orig = peca_cortada.linhas_peca_cortada

    def falha_na_janela(verts, tris, z, grupos=(), **k):
        if abs(np.asarray(verts)[:, 0].min() - 3.0) < 1e-3:  # a janela (x 3..4)
            raise RuntimeError("falha simulada")
        return orig(verts, tris, z, grupos, **k)
    monkeypatch.setattr(peca_cortada, "linhas_peca_cortada", falha_na_janela)
    f, g, gid = cena()
    p = pedido(f, gid, tmp_path / "p")
    base, com = roda(p), roda(p, motor_janelas=True)
    assert not pelo_motor(f, g, com, "jan0")  # só ela cai no HLR
    assert pelo_motor(f, g, com, "porta0")  # a porta segue pelo motor (a parede P0, z1 > corte, nunca é elegível ao motor)
    assert com["motor_janelas_diag"]["erro"] == 1
    assert B.grupo(com["svg"], g["jan0"]) == B.grupo(base["svg"], g["jan0"])
