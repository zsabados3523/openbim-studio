# SPDX-License-Identifier: AGPL-3.0-or-later
"""Auxiliar do oráculo F0-S06-T15o (corte em faixas). Não é de `app/`; o implementador não edita.
Modelos sintéticos, espiões de `faixas.rodar_filho` e a régua de comparação de SVG (ver o topo de test_s06_t15o_faixas_corte_oraculo.py)."""
from __future__ import annotations

import copy
import importlib
import math
import re
import threading
import time

import pytest
from s06_t15i_aux import ExecutorEspiao, X, corte, desenho_geo, local  # noqa: F401
import s06_t07c_aux as C

NUM = r"-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?"
U0 = -C.XMIN  # u (m, a partir da câmera) = x do mundo + 0,5 (vista +Y, modelo na origem)
TX = C.DX / 2.0  # o SVG soma TX ao u (largura/2 do viewBox)


def faixas():
    try:
        return importlib.import_module("obim_geometria.faixas")
    except ImportError as e:
        pytest.fail(f"módulo obim_geometria.faixas inexistente: {e}")


def modelo_varios():
    """Corte +Y: parede P e laje L (cortadas), pilar Pil1 (cortado), pilar Pil2 e caixa Cx atrás do plano, viga Vig (cruza todas as bordas) e o móvel M (caixa 2D)."""
    f, g = C.modelo("IFC4")
    pav = f.by_type("IfcBuildingStorey")[0]
    novos = [("Pil3", "IfcColumn", 0.1, 1.5, 0.0, 0.3, 0.3, 2.0), ("Cx2", "IfcBuildingElementProxy", 5.8, 2.5, 0.0, 0.4, 0.4, 1.0), ("Pil1", "IfcColumn", 1.0, -0.3, 0.0, 0.4, 0.6, 3.0), ("Pil2", "IfcColumn", 3.2, 1.0, 0.0, 0.4, 0.4, 3.0),
             ("Vig", "IfcBeam", 0.0, 0.8, 2.6, 5.0, 0.3, 0.4), ("Cx", "IfcBuildingElementProxy", 4.2, 2.0, 0.0, 0.5, 0.5, 1.0)]
    for nome, cls, *dim in novos:
        e = X.caixa(f, cls, nome, *dim)
        X.conter(f, pav, e)
        g[nome] = e.GlobalId
    return f, g, C.corte(f)


def modelo_oclusao(tampa: bool):
    """Tudo atrás do plano. `Tampa` (x 1..3, y 1..1,2, z 0..2,5) esconde a parte baixa do pilar `Atras2` (x 2,5..2,9, y 3, z 0..3,5), que está noutra faixa que o centro dela;
    Pa e Pb espalham os centros. Sem `tampa` o pilar aparece inteiro (prova de que a oclusão existe)."""
    f, pavs = X.estrutura("IFC4")
    pecas = [("Pa", 0.6, 2.0, 0.0, 0.4, 0.4, 2.0), ("Pb", 4.5, 2.0, 0.0, 0.4, 0.4, 2.0), ("Atras2", 2.5, 3.0, 0.0, 0.4, 0.4, 3.5)]
    if tampa:
        pecas.append(("Tampa", 1.0, 1.0, 0.0, 2.0, 0.2, 2.5))
    g = {}
    for nome, *dim in pecas:
        e = X.caixa(f, "IfcColumn" if nome != "Tampa" else "IfcBuildingElementProxy", nome, *dim)
        X.conter(f, pavs[0], e)
        g[nome] = e.GlobalId
    return f, g, C.corte(f)


def pedido_de(f, gid, pasta, **kw):
    """Pedido de `desenho` exatamente como `gerar_corte` o monta, apontando para o IFC completo gravado em `pasta` (a pasta do pedido real some ao sair do `with`)."""
    esp = ExecutorEspiao()
    corte.gerar_corte(f, gid, executor=esp, **kw)
    p = copy.deepcopy(esp.pedidos_desenho[0])
    pasta.mkdir(exist_ok=True)
    f.write(str(pasta / "m.ifc"))
    p["arquivo"] = str(pasta / "m.ifc")
    p["threads"] = p.get("threads", 4)
    return p


def itens_do_pedido(p):
    """(id, guid, u0, u1) de cada elemento com caixa (vista +Y, modelo na origem)."""
    cx = {int(k): v for k, v in p["caixas_coords"].items()}
    return [(i, g, cx[i][0] + U0, cx[i][3] + U0) for i, g in p["elementos"] if i in cx]


class EspiaoFilho:
    """Substitui `faixas.rodar_filho`: grava o pedido, conta filhos simultâneos e delega ao `desenho.processar` no mesmo processo (serializado por trava).
    `falha(pedido) -> None | "raise" | "ok_false"` simula erro; `atraso` mantém o filho 'vivo' para medir a concorrência."""

    def __init__(self, monkeypatch, F, atraso=0.0, falha=None):
        self.chamadas, self.resultados, self.max_ativos, self._ativos = [], [], 0, 0
        self.atraso, self.falha = atraso, falha
        self._tr, self._real = threading.Lock(), threading.Lock()
        monkeypatch.setattr(F, "rodar_filho", self)

    def __call__(self, pedido):
        ped = copy.deepcopy(pedido)
        with self._tr:
            self.chamadas.append(ped)
            self._ativos += 1
            self.max_ativos = max(self.max_ativos, self._ativos)
        try:
            time.sleep(self.atraso)
            modo = self.falha(ped) if self.falha else None
            if modo == "raise":
                raise RuntimeError("filho morreu (simulado)")
            if modo == "ok_false":
                return {"ok": False, "erro": {"tipo": "Simulado", "mensagem": "falha do filho", "rastro": ""}}
            with self._real:
                r = desenho_geo.processar(ped)
            with self._tr:
                self.resultados.append((ped, r))
            return r
        finally:
            with self._tr:
                self._ativos -= 1

    def ordenados(self):
        """[(pedido, resultado)] por faixa, da esquerda para a direita."""
        return sorted(self.resultados, key=lambda t: -math.inf if t[0]["faixa"]["u0"] is None else t[0]["faixa"]["u0"])


def cortes_de(chamadas):
    """Bordas internas das faixas, já no sistema do SVG (u + TX)."""
    return sorted({b + TX for c in chamadas for b in (c["faixa"]["u0"], c["faixa"]["u1"]) if b is not None})


# ---- régua de comparação ----
def _ws(t):
    return re.sub(r">\s+<", "><", re.sub(r"\s+", " ", t)).strip()


_PROJ = re.compile(r'<g class="projection">.*?</g>', re.S)
_PROD = re.compile(r'<g id="product-[^"]*"[^>]*?ifc:guid="([^"]+)"[^>]*>.*?</g>', re.S)
_CAIXA = re.compile(r'<g class="Ifc(?:Furniture|FurnishingElement|SystemFurnitureElement)" ifc:guid="[^"]+">.*?</g>', re.S)


def partes(svg):
    """(esqueleto sem projeção/grupos de corte/caixas, {guid: grupo de corte}, caixas)."""
    grupos = {m.group(1): _ws(m.group(0)) for m in _PROD.finditer(svg)}
    caixas = sorted(_ws(m.group(0)) for m in _CAIXA.finditer(svg))
    return _ws(_CAIXA.sub("", _PROD.sub("", _PROJ.sub("<PROJ/>", svg)))), grupos, caixas


def segmentos(svg):
    m = _PROJ.search(svg)
    out = []
    for d in re.findall(r'<path d="([^"]*)"', m.group(0) if m else ""):
        pts = [(float(a), float(b)) for a, b in re.findall(rf"({NUM}),({NUM})", d)]
        for p, q in zip(pts, pts[1:]):
            if math.dist(p, q) > 1e-9:
                out.append(tuple(sorted((p, q), key=lambda v: (round(v[0], 4), round(v[1], 4)))))
    return out


def recortar(segs, cortes):
    """Parte cada segmento nas bordas (x = c) que o atravessam por dentro; o que só encosta na borda fica inteiro."""
    out = []
    for p, q in segs:
        if p[0] > q[0]:
            p, q = q, p
        pts = [p]
        for c in cortes:
            lo, hi = sorted((p[0], q[0]))
            if lo + 1e-9 < c < hi - 1e-9:
                t = (c - p[0]) / (q[0] - p[0])
                pts.append((c, p[1] + t * (q[1] - p[1])))
        pts.append(q)
        out += [tuple(sorted(s, key=lambda v: (round(v[0], 4), round(v[1], 4)))) for s in zip(pts, pts[1:])]
    return out


def casar(a, b, tol=1e-6):
    """Multiconjuntos de segmentos iguais a menos de `tol`; devolve (só em a, só em b)."""
    grade = {}
    for s in b:
        grade.setdefault((round(s[0][0] * 1e3), round(s[0][1] * 1e3)), []).append(s)
    so_a = []
    for s in a:
        kx, ky = round(s[0][0] * 1e3), round(s[0][1] * 1e3)
        achou = None
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for t in grade.get((kx + dx, ky + dy), []):
                    if all(abs(u - v) <= tol for pa, pb in zip(s, t) for u, v in zip(pa, pb)):
                        achou = (kx + dx, ky + dy, t)
                        break
                if achou:
                    break
            if achou:
                break
        if achou:
            grade[achou[:2]].remove(achou[2])
        else:
            so_a.append(s)
    return so_a, [t for lst in grade.values() for t in lst]


def exigir_igual(base_svg, svg, cortes):
    """Mesmo desenho: esqueleto, grupos de corte (por guid, texto idêntico) e caixas idênticos; projeção = mesmo multiconjunto de segmentos (tolerância 1e-6), com o SVG de base
    partido nas mesmas bordas (a emenda é a única diferença permitida; traço duplicado ou faltando reprova)."""
    (e0, g0, c0), (e1, g1, c1) = partes(base_svg), partes(svg)
    assert e1 == e0, "cabeçalho/estilo/seção do SVG mudou"
    assert g1 == g0, f"grupos de corte diferem: só base {sorted(set(g0) - set(g1))}, só faixas {sorted(set(g1) - set(g0))}"
    assert c1 == c0, "caixas 2D de móveis diferem"
    so_base, so_par = casar(recortar(segmentos(base_svg), cortes), recortar(segmentos(svg), cortes))
    assert not so_base and not so_par, f"projeção difere: faltam {len(so_base)} (ex. {so_base[:2]}), sobram {len(so_par)} (ex. {so_par[:2]})"


def exigir_dict_igual(base, r):
    """Mesmo dict de `processar`: mesmas chaves (podem sobrar), enviados/falhas/caixas iguais sem repetição, n_paths do SVG final, tempos numéricos."""
    assert r.get("ok") is True, r.get("erro")
    assert base.keys() <= r.keys()
    assert sorted(r["enviados"]) == sorted(base["enviados"]) and list(r["caixas"]) == list(base["caixas"])
    assert sorted(r["falhas_geometria"]) == sorted(base["falhas_geometria"]) and list(r["em_cache"]) == list(base["em_cache"])
    assert r["n_paths"] == len(re.findall(r"<path\b", r["svg"]))
    assert set(base["tempos"]) <= set(r["tempos"]) and all(isinstance(v, float) and v >= 0 for v in r["tempos"].values())


def id_de(f, g, nome):
    return f.by_guid(g[nome]).id()
