# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo F0-S06-T19h: planta desenhada por componentes de pegada (T3). Cartão: docs/state/cards/F0-S06/F0-S06-T19h-componentes-pegada.md (seção API). Não editar nesta tarefa.
CONTRATO (resumo; o cartão manda):
1. `obim_geometria.componentes.pegada_xy(verts, tris)` -> shapely Polygon/MultiPolygon: união dos triângulos projetados em XY (sem folga); None se vazia. `agrupar(pegadas, folga=0.002)`
   -> list[list[int]]: componentes conexos (união-busca; duas pegadas se ligam quando a distância é <= folga); índices crescentes em cada grupo, grupos por menor índice; None = grupo sozinho.
2. `desenho.processar` de PLANTA com `pedido["componentes"] = True` (sem `faixa`, `faixas` ausente ou 1): `dividir_elementos` agrupa por pegada (sem pesadas de silhueta, que o pai desenha); 1 grupo = caminho
   normal, sem filho. N>1: um `faixas.rodar_filho(q)` por grupo (q = pedido sem `componentes`/`pesados`/`limiar_pesado`, `elementos` = grupo na ordem original, `threads` = max(1, threads // simultâneos)),
   SVGs unidos por `faixas.unir_planta`; os grupos de elemento (`ifc:guid`) ficam na ordem de `elementos` do pedido (a réplica do cache de tipo NÃO vai para o fim). Resposta ganha `grupos` (int) e `grupos_ids` (lista de listas de id STEP, na ordem original). Sem `componentes`: sem essas chaves.
3. Filho que levanta, devolve ok False ou morre: só os elementos dele entram em `falhas_geometria`; os demais grupos e as silhuetas do pai ficam (ok True)."""
from __future__ import annotations

import copy
import pathlib
import re
import threading
import time

import numpy as np
import pytest
import s06_t07_aux as X
import s06_t18a_aux as Z
from test_s06_t19b1_visibilidade_oraculo import TOL, _amostra, _caixa, _cobertura, _dist, _junta
from test_s06_t19b2_visibilidade_hlr_oraculo import _prisma

import obim_geometria.desenho as D
import obim_geometria.faixas as F


def _comp():
    import importlib
    try:
        return importlib.import_module("obim_geometria.componentes")
    except ImportError as e:
        pytest.fail(f"módulo obim_geometria.componentes inexistente (a implementar na T19h): {e}")


def _prisma_ou(n, r, h, x, y):
    v, t = _prisma(n, r, h)
    return v + [x, y, 0.0], t


def _laje(x0, y0, x1, y1):
    return _caixa(x0, y0, 0, x1, y1, 0.1)


L_MALHA = _junta(_caixa(10, 0, 0, 13, 1, 1), _caixa(10, 1, 0, 11, 3, 1))  # em L: caixa 2D (10..13 x 0..3) contém o nicho
G_MALHA = _caixa(12, 2, 0, 12.8, 2.8, 1)  # dentro do nicho do L: 20 cm de vão, caixas 2D se sobrepõem, pegadas não


# ---------------------------------------------------------------- puros (casos 3 e 4)
def test_pegada_e_agrupar_puros():
    C = _comp()
    peg = C.pegada_xy(*L_MALHA)
    assert abs(peg.area - 5.0) < 1e-9 and C.pegada_xy(np.zeros((0, 3)), np.zeros((0, 3), int)) is None
    pg = C.pegada_xy(*G_MALHA)
    assert peg.envelope.intersects(pg.envelope) and not peg.buffer(0.002).intersects(pg)  # caso 4
    assert C.agrupar([peg, pg]) == [[0], [1]]
    base = C.pegada_xy(*_caixa(0, 0, 0, 1, 1, 1))
    vizinho = lambda d: C.pegada_xy(*_caixa(1 + d, 0, 0, 2 + d, 1, 1))  # noqa: E731
    assert C.agrupar([base, vizinho(0.0)]) == [[0, 1]] and C.agrupar([base, vizinho(0.0015)]) == [[0, 1]]
    assert C.agrupar([base, vizinho(0.005)]) == [[0], [1]] and C.agrupar([base, vizinho(0.005)], folga=0.01) == [[0, 1]]
    assert C.agrupar([pg, None, base, peg]) == [[0], [1], [2], [3]]
    far = [C.pegada_xy(*_caixa(10 * k, 0, 0, 10 * k + 1, 1, 1)) for k in range(4)]
    assert C.agrupar(far + [C.pegada_xy(*_laje(-1, -1, 40, 2))]) == [[0, 1, 2, 3, 4]]  # caso 3: a laje une tudo
    assert C.agrupar([far[3], far[0], base]) == [[0], [1, 2]]  # ordem estável: menor índice; índices crescentes
    assert C.agrupar([]) == []


# ---------------------------------------------------------------- cena com IFC
def _cena(tmp, malhas, comp_rep=None, corte=50.0):
    """IFC de 1 pavimento; cada peça é um proxy com a malha (mundo) como corpo. `comp_rep=(i, j, dx)`: a peça j reaproveita a representação da i, deslocada de dx."""
    f, pavs = X.estrutura("IFC4", n_pav=1)
    els = []
    for k, m in enumerate(malhas):
        e = X.caixa(f, "IfcBuildingElementProxy", f"P{k}", 0, 0, 0, 1, 1, 1)
        X.conter(f, pavs[0], e)
        Z.densificar(f, e, ([tuple(map(float, p)) for p in m[0]], [tuple(map(int, q)) for q in m[1]]))
        els.append(e)
    if comp_rep:
        i, j, dx = comp_rep
        els[j].Representation = els[i].Representation
        els[j].ObjectPlacement.RelativePlacement.Location.Coordinates = (dx, 0.0, 0.0)
    arq = str(pathlib.Path(tmp) / "m.ifc")
    f.write(arq)
    ped = {"arquivo": arq, "elementos": [[e.id(), e.GlobalId] for e in els], "threads": 1,
           "vista": {"tipo": "PLANTA", "escala": 1.0, "altura_corte_m": corte, "pavimento": pavs[0].GlobalId}}
    return ped, [e.id() for e in els]


def _segs(svg):
    out = []
    for d in re.findall(r'<path\b[^>]*\bd="([^"]*)"', svg[svg.find("</style>"):]):
        pts = [(float(a), -float(b)) for a, b in re.findall(r"(-?[\d.]+(?:e[-+]?\d+)?),(-?[\d.]+(?:e[-+]?\d+)?)", d)]
        out += list(zip(pts, pts[1:]))
    return np.array(out, float).reshape(-1, 2, 2)


def _guids(svg):
    return re.findall(r'<g\b(?![^>]*IfcBuildingStorey)[^>]*\bifc:guid="([^"]+)"', svg)


def _extra(seg, alvo, caixa, margem=0.05):
    """Comprimento de `seg` dentro da caixa (encolhida) que NÃO tem par em `alvo`."""
    p, w = _amostra(seg)
    x0, y0, x1, y1 = caixa
    d = (p[:, 0] > x0 + margem) & (p[:, 0] < x1 - margem) & (p[:, 1] > y0 + margem) & (p[:, 1] < y1 - margem)
    return float(w[d & (_dist(p, alvo) > TOL)].sum())


class Espiao:
    """Substitui `faixas.rodar_filho`: grava o pedido e delega ao `desenho.processar` no mesmo processo (serializado). `falha(pedido) -> None | "raise" | "ok_false"`."""

    def __init__(self, monkeypatch, falha=None):
        self.chamadas, self.falha, self._tr = [], falha, threading.Lock()
        monkeypatch.setattr(F, "rodar_filho", self)

    def __call__(self, pedido, *a, **k):
        ped = copy.deepcopy(pedido)
        with self._tr:
            self.chamadas.append(ped)
            modo = self.falha(ped) if self.falha else None
            if modo == "raise":
                raise RuntimeError("filho morreu (simulado)")
            if modo == "ok_false":
                return {"ok": False, "erro": {"tipo": "Simulado", "mensagem": "falha do filho", "rastro": ""}}
            return D.processar(ped)


def _caixas_xy(ms):
    return [(m[0][:, 0].min(), m[0][:, 1].min(), m[0][:, 0].max(), m[0][:, 1].max()) for m in ms]


# ---------------------------------------------------------------- casos 1, 2 e 5
@pytest.mark.parametrize("corte", [50.0, 0.5], ids=["so_projecao", "com_corte"])
def test_componentes_cobre_o_conjunto_com_oclusao_e_ordem(monkeypatch, tmp_path, corte):
    A, B, C, C2 = (_caixa(0, 0, 0, 1, 1, 1), _caixa(3, 0, 0, 4, 1, 1), _caixa(6, 0, 0, 7, 1, 1), _caixa(0, 0, 0, 1, 1, 1))  # C2 será cópia de A (mesma representação) 3 m à esquerda
    DD, E = _caixa(20, 0, 0, 22, 2, 1), _caixa(21, 1, 0, 23, 3, 2)  # E mais alto cobre o canto de D
    malhas = [A, B, C, C2, DD, E, L_MALHA, G_MALHA]
    ped, ids = _cena(tmp_path, malhas, comp_rep=(0, 3, -3.0), corte=corte)  # cache de tipo ligado: A é o primário e C2 a réplica, em grupos diferentes
    ref = D.processar(copy.deepcopy(ped))
    assert ref["ok"] and "grupos" not in ref and "grupos_ids" not in ref
    esp = Espiao(monkeypatch)
    r = D.processar({**copy.deepcopy(ped), "componentes": True})
    assert r["ok"] and not r["falhas_geometria"]
    assert len(esp.chamadas) == r["grupos"] == len(r["grupos_ids"])
    g = sorted(sorted(x) for x in r["grupos_ids"])
    assert g == sorted(sorted(x) for x in [[ids[0]], [ids[1]], [ids[2]], [ids[3]], [ids[4], ids[5]], [ids[6]], [ids[7]]])  # L e G separados: o nicho do L
    assert [e for gr in r["grupos_ids"] for e in gr if e in (ids[4], ids[5])] == [ids[4], ids[5]]  # ordem original dentro do grupo
    assert all(c["elementos"] and "componentes" not in c and "pesados" not in c for c in esp.chamadas)
    assert sorted(i for c in esp.chamadas for i, _ in c["elementos"]) == sorted(ids)
    a, b = _segs(ref["svg"]), _segs(r["svg"])
    assert len(a) and _cobertura(a, b) >= 0.999, "linha do conjunto faltando"
    assert _cobertura(b, a) >= 0.999, "linha sobrando em relação ao conjunto"
    if corte > 10:  # caso 2: o canto de D debaixo de E segue escondido (D sozinha mostraria linha ali, que o conjunto e os grupos não têm)
        cx = _caixas_xy([E])[0]
        so_d = _segs(D.processar({**copy.deepcopy(ped), "elementos": [ped["elementos"][4]]})["svg"])
        assert _extra(so_d, a, cx) > 1.0, "o caso não discrimina: D sozinha deveria ter linha extra sob E"
        assert _extra(so_d, b, cx) > 1.0, "oclusão de E sobre D perdida"
    else:  # caso 5: grupos de elemento (cortes) na ordem de `elementos`, inclusive a réplica do cache de tipo
        assert [[e[1] for e in ped["elementos"]].index(x) for x in _guids(r["svg"])] == list(range(8))
    r2 = D.processar({**copy.deepcopy(ped), "componentes": True})
    assert r2["svg"] == r["svg"] and r2["grupos_ids"] == r["grupos_ids"]


def test_laje_que_sobrepoe_tudo_vira_um_grupo_sem_filho(monkeypatch, tmp_path):
    ped, ids = _cena(tmp_path, [_caixa(0, 0, 0, 1, 1, 1), _caixa(8, 0, 0, 9, 1, 1), _laje(-1, -1, 10, 2)])
    ref = D.processar(copy.deepcopy(ped))
    esp = Espiao(monkeypatch)
    r = D.processar({**copy.deepcopy(ped), "componentes": True})
    assert r["ok"] and r["grupos"] == 1 and r["grupos_ids"] == [ids] and not esp.chamadas
    assert r["svg"] == ref["svg"]


# ---------------------------------------------------------------- caso 6
def test_falha_de_um_grupo_nao_derruba_os_demais(monkeypatch, tmp_path):
    malhas = [_caixa(0, 0, 0, 1, 1, 1), _caixa(3, 0, 0, 4, 1, 1), _caixa(6, 0, 0, 7, 1, 1), _prisma_ou(40, 0.5, 1.0, 20, 0)]
    ped, ids = _cena(tmp_path, malhas, corte=0.5)
    ped.update({"pesados": "silhueta", "limiar_pesado": 100})  # o prisma de 40 lados (~156 triângulos) é pesado: silhueta desenhada pelo pai
    ref = D.processar(copy.deepcopy(ped))
    assert ref["ok"] and ref["pesados"]
    for modo in ("raise", "ok_false"):
        esp = Espiao(monkeypatch, falha=lambda p: modo if ids[1] in [i for i, _ in p["elementos"]] else None)
        r = D.processar({**copy.deepcopy(ped), "componentes": True})
        assert r["ok"] and r["grupos"] == 3 and len(esp.chamadas) == 3, "o pesado não entra nos grupos dos filhos"
        assert r["falhas_geometria"] == [ids[1]] and [p["id"] for p in r["pesados"]] == [ids[3]]
        gs = set(_guids(r["svg"]))
        guid = {e[0]: e[1] for e in ped["elementos"]}
        assert {guid[ids[0]], guid[ids[2]], guid[ids[3]]} <= gs and guid[ids[1]] not in gs


# ---------------------------------------------------------------- tempo (sintético)
def test_tempo_dos_grupos_nao_cresce_com_o_conjunto(monkeypatch, tmp_path):
    """36 peças pesadas (~1,2 mil triângulos cada) em grade 6x6, todas separadas (vão de 20 cm): o HLR do conjunto é superlinear nos triângulos do mesmo pedido; por componentes custa ~a soma das peças.
    Medido na máquina de referência: grupos/conjunto = 0,72. Margem larga (0,85) e uma execução de cada; a parte estrutural (um filho por peça) não depende de relógio."""
    n = 36
    malhas = [_prisma_ou(300, 0.5, 1.0, 1.2 * (k % 6), 1.2 * (k // 6)) for k in range(n)]
    ped, ids = _cena(tmp_path, malhas)
    esp = Espiao(monkeypatch)
    t = time.perf_counter()
    rc = D.processar(copy.deepcopy(ped))
    t_conj = time.perf_counter() - t
    t = time.perf_counter()
    rg = D.processar({**copy.deepcopy(ped), "componentes": True})
    t_comp = time.perf_counter() - t
    assert rc["ok"] and rg["ok"] and rg["grupos"] == n and [len(c["elementos"]) for c in esp.chamadas] == [1] * n
    assert _cobertura(_segs(rc["svg"]), _segs(rg["svg"])) >= 0.999 and _cobertura(_segs(rg["svg"]), _segs(rc["svg"])) >= 0.999
    assert t_comp < 0.85 * t_conj, f"conjunto {t_conj:.2f}s, grupos {t_comp:.2f}s"
