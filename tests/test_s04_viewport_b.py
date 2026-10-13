# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo da viewport, casos novos (S04-T06b; LOTE_OPUS_12 §4 f e achado 9.e; LOTE_OPUS_13). Reaproveita os auxiliares de
`test_s04_viewport.py` (importados) e roda os casos em subprocesso sob `xvfb-run`, como ele. Os casos (g) tamanho da captura e (h) escala
1,25 estão em `test_s04_viewport.py` (caso `trocar`). Aqui:
 * `info()` -> str "<desenho> | <placa>" (ex. "OpenGL | llvmpipe", "D3D11 | ..."); começa por "ERRO" se a QRhi não subiu. Existe desde a T07.
 * T07b (guarda: pula enquanto `estatisticas()` não trouxer as chaves; FALHA com OBIM_S04_T07B_OBRIGATORIO=1, que entra junto com a T07b):
   estatisticas()["superficies_soltas"] (int, quantas superfícies a thread de desenho soltou; >= 1 no caso `recriar_superficie`, que destrói a janela nativa) e
   estatisticas()["solturas_atrasadas"] (int, soltas que estouraram os 3 s; == 0 em todos os casos).
 * T08 (guarda: pula enquanto `estatisticas()` não trouxer a chave marcadora "fatias_enviadas" (int, fatias de envio à placa); FALHA com
   OBIM_S04_T08_OBRIGATORIO=1, que entra junto com a T08): orçamento por quadro (lote de ~1 milhão de triângulos em UM adicionar_lote: nenhum
   intervalo entre quadros apresentados > 50 ms até tudo estar na placa); sequência: o relogio() mostra, depois de perder_contexto() e depois
   de limpar()+novo lote, quadros cuja sequência volta a alcançar a devolvida por adicionar_lote (maior prefixo contínuo na placa);
   adicionar_lote com dtype/índices errados (vértices com itemsize != 28, índices não-uint32 ou não contíguos, índice >= nº de vértices,
   objeto que não é LoteMalha) levanta TypeError ou ValueError do Python (nunca derruba o processo) e não altera estatisticas()."""
import os
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from test_s04_viewport import (RAIZ, agora, caso as _caso, captura, esperar, lote, novo, quadros, rodar, soltas,  # noqa: F401
                               um, viewport)

ESTE = Path(__file__).resolve()
caso = lambda nome, *a, **k: _caso(nome, *a, alvo=ESTE, **k)  # noqa: E731
ESC = lambda x: [("QT_SCALE_FACTOR", x)]  # noqa: E731  (as mesmas chaves do teste de `trocar` no outro arquivo: o resultado é reaproveitado)
CASOS_T07B = [("imagem", (), (), 400), ("relogio", (), (), 400), ("intervalo", (), (), 900), ("trocar", (), ESC("1"), 400),
              ("trocar", (), ESC("1.25"), 400), ("recriar_superficie", (), (), 400), ("contexto", (), (), 600), ("destruir", ("janela",), (), 400),
              ("destruir", ("conteiner",), (), 400), ("destruir", ("sair",), (), 400)]

def guarda(var):  # pula; com OBIM_S04_OBRIGATORIO=1 e a variável da etapa = 1, falha
    obrigatorio = os.environ.get("OBIM_S04_OBRIGATORIO") == "1" and os.environ.get(var) == "1"
    return pytest.fail if obrigatorio else pytest.skip

def test_info_diz_qual_desenho_foi_usado(viewport):
    r = _caso("imagem")  # o resultado do caso da imagem (cacheado) traz info()
    if r.get("info") is None:
        pytest.skip("obimcore.Cena.info() ausente")
    desenho, _, placa = r["info"].partition("|")
    quer = ("d3d11", "direct3d 11") if os.environ.get("RHI", "d3d11" if sys.platform == "win32" else "gl") != "gl" else ("opengl",)
    assert not r["info"].startswith("ERRO") and placa.strip(), f"QRhi sem placa: {r['info']!r}"
    assert desenho.strip().lower() in quer, f"desenho usado {desenho!r}, esperado um de {quer}"

@pytest.mark.parametrize("nome,args,extra,limite", CASOS_T07B, ids=[f"{n}{'-' + a[0] if a else ''}{'-' + e[0][1] if e else ''}" for n, a, e, _ in CASOS_T07B])
def test_contadores_de_soltura_t07b(viewport, nome, args, extra, limite):  # a confirmação vem depois dos casos (resultado em cache)
    s = _caso(nome, *args, limite=limite, extra=extra).get("solt") or {}
    if s.get("superficies_soltas") is None or s.get("solturas_atrasadas") is None:
        guarda("OBIM_S04_T07B_OBRIGATORIO")("\n!!! aguarda S04-T07b: estatisticas() sem superficies_soltas/solturas_atrasadas !!!\n")
    assert s["solturas_atrasadas"] == 0, f"{nome}: soltura passou dos 3 s ({s})"
    # `trocar` NÃO exige superficies_soltas >= 1: o Qt reparenta o contêiner sem destruir a janela nativa (no CI o contador ficou em 0).
    assert nome != "recriar_superficie" or s["superficies_soltas"] >= 1, f"recriar_superficie: nenhuma superfície solta ({s})"

# ---- T08 (guardados) ----
def grade(n):  # ~2*n*n triângulos num só lote, na frente da câmera (plano z=0, cor verde)
    from viewport_qrhi.carregador import DTYPE_OBJETO, DTYPE_VERTICE, LoteMalha
    ij = np.stack(np.meshgrid(np.arange(n + 1), np.arange(n + 1)), -1).reshape(-1, 2).astype(np.float32)
    v = np.zeros((n + 1) ** 2, DTYPE_VERTICE)
    v["pos"][:, :2], v["normal"][:, 2], v["cor"] = (ij - n / 2) * (8.0 / n), 1, (30, 220, 30, 255)
    a = (np.arange(n)[:, None] * (n + 1) + np.arange(n)[None, :]).ravel().astype(np.uint32)
    ind = np.stack([a, a + 1, a + n + 2, a, a + n + 2, a + n + 1], -1).ravel().astype(np.uint32)
    o = np.zeros(1, DTYPE_OBJETO)
    o[0] = (1, b"G" * 22, 0, len(ind), 0, len(v), v["pos"].min(0), v["pos"].max(0))
    return LoteMalha(0, v, ind, o, np.zeros(3), 1, 1)

def t08_presente(c):
    return "fatias_enviadas" in c.estatisticas()

def c_orcamento(res):
    c, w, _ = novo(0)
    res["t08"] = t08_presente(c)
    if not res["t08"]:
        return c.parar()
    yield 1000
    g, t0 = grade(707), agora()  # 2*707² = 999 698 triângulos
    res["tri"] = len(g.indices) // 3
    c.adicionar_lote(g)
    res["ok"] = yield from esperar(lambda: c.estatisticas()["triangulos_na_placa"] == res["tri"], 90000)
    yield 500
    ts = [t for t, _ in quadros(c, t0)]
    res["maior_ms"], res["quadros"] = max([b - a for a, b in zip(ts, ts[1:])] or [1e9]), len(ts)
    c.parar()

def c_sequencia(res):
    c, w, _ = novo(0)
    res["t08"] = t08_presente(c)
    if not res["t08"]:
        return c.parar()
    s1 = c.adicionar_lote(lote())
    yield from esperar(lambda: c.estatisticas()["triangulos_na_placa"] == 7200)
    yield 500
    res["antes"] = max(s for _, s in quadros(c))
    t0, n0 = agora(), c.estatisticas()["contextos"]
    c.perder_contexto()
    yield from esperar(lambda: c.estatisticas()["contextos"] > n0 and c.estatisticas()["triangulos_na_placa"] == 7200, 12000)
    yield 800
    res.update(s1=s1, depois_perda=max([s for _, s in quadros(c, t0)] or [-1]))
    c.limpar()
    yield from esperar(lambda: c.estatisticas()["triangulos"] == 0)
    t1, s2 = agora(), c.adicionar_lote(um(0))
    res["ok2"] = yield from esperar(lambda: c.estatisticas()["triangulos_na_placa"] == 12)
    yield 500
    res.update(s2=s2, depois_limpar=max([s for _, s in quadros(c, t1)] or [-1]), viva=c.viva())
    c.parar()

def c_tipos_errados(res):
    c, w, _ = novo(0)
    res["t08"] = t08_presente(c)
    if not res["t08"]:
        return c.parar()
    c.adicionar_lote(um(0))
    yield from esperar(lambda: c.estatisticas()["triangulos_na_placa"] == 12)
    b, e0 = um(1), c.estatisticas()
    ruins = {"vertices float32": replace(b, vertices=np.zeros((24, 7), np.float32)), "vertices itemsize": replace(b, vertices=b.vertices.view(np.uint8)),
             "indices int64": replace(b, indices=b.indices.astype(np.int64)), "indices int16": replace(b, indices=b.indices.astype(np.int16)),
             "indices nao contiguos": replace(b, indices=np.repeat(b.indices, 2)[::2]),
             "indice fora": replace(b, indices=np.where(np.arange(len(b.indices)) == 3, np.uint32(10 ** 6), b.indices).astype(np.uint32)),
             "None": None, "dict": {"vertices": b.vertices}, "lista": [1, 2, 3]}
    res["erros"], res["silencio"] = {}, []
    for k, x in ruins.items():
        try:
            c.adicionar_lote(x)
            res["silencio"].append(k)
        except (TypeError, ValueError) as ex:
            res["erros"][k] = type(ex).__name__
        except BaseException as ex:  # noqa: BLE001  (RuntimeError, SystemError... não são "erro limpo")
            res["erros"][k] = "SUJO " + type(ex).__name__
    yield 500
    res.update(viva=c.viva(), igual=c.estatisticas()["triangulos"] == e0["triangulos"] and c.estatisticas()["lotes"] == e0["lotes"])
    c.adicionar_lote(um(2))  # e um lote bom continua entrando
    res["bom"] = yield from esperar(lambda: c.estatisticas()["triangulos_na_placa"] == 24)
    c.parar()

def exige_t08(r):
    r["t08"] or guarda("OBIM_S04_T08_OBRIGATORIO")(
        "\n!!! aguarda S04-T08: estatisticas() sem 'fatias_enviadas' (orçamento/sequência/tipos NÃO FORAM EXECUTADOS) !!!\n")

def test_orcamento_por_quadro_lote_de_um_milhao_de_triangulos(viewport):
    r = caso("orcamento", limite=300)
    exige_t08(r)
    assert r["ok"] and r["quadros"] >= 20, r
    assert r["maior_ms"] <= 50, f"maior intervalo entre quadros {r['maior_ms']:.0f} ms > 50 com o lote de {r['tri']} triângulos"

def test_sequencia_volta_depois_da_perda_e_depois_de_limpar(viewport):
    r = caso("sequencia", limite=300)
    exige_t08(r)
    assert r["antes"] >= r["s1"] and r["depois_perda"] >= r["s1"], f"sequência não voltou depois da perda: {r}"
    assert r["s2"] > r["s1"] and r["ok2"] and r["depois_limpar"] >= r["s2"] and r["viva"], f"sequência não voltou depois de limpar: {r}"

def test_tipos_de_dado_errados_dao_erro_python_limpo(viewport):
    r = caso("tipos_errados", limite=300)
    exige_t08(r)
    assert not r["silencio"], f"aceitou dado errado: {r['silencio']}"
    assert all(not v.startswith("SUJO") for v in r["erros"].values()), f"erro que não é TypeError/ValueError: {r['erros']}"
    assert r["viva"] and r["igual"] and r["bom"], r

if __name__ == "__main__":
    sys.path.insert(0, str(RAIZ / "prototypes"))
    import importlib
    nome, *resto = sys.argv[1:]
    assert not {"obimcore", "PySide6.QtCore"} & sys.modules.keys(), "o oráculo importou Qt ou obimcore antes da ordem pedida"
    [importlib.import_module(m) for m in ("ifcopenshell", "obimcore")]
    rodar(lambda r: globals()["c_" + nome](r, *resto))
