# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo do F0-S04-T30a1 (T30d1): o `sem` da cena (refaz um lote sem os objetos removidos) tem de dar o MESMO resultado de hoje
e parar de inflar `bytes_copia`. Quem implementa o T30a1 não edita este arquivo.
Sem marca: equivalência (passa com o `sem` de hoje e tem de continuar passando). `bytes_copia` sem sobra: passa desde o T30a1 (PR 200).
Forma canônica por peça: calculada em Python puro (`sem_mortos`) a partir do lote de entrada, pelo GUID; índices renumerados por soma parcial.
O Python não lê os vértices da cena de volta: a conferência em bits dos vértices é indireta, pela imagem (captura) da cena operada contra a
captura da mesma cena remontada do zero com a forma canônica (mesmo `enquadrar`, mesma ordem de lotes). Tabela, contagens e caixa: exatas.
Cada caso roda em subprocesso sob `xvfb-run` (nunca na tela real), com os auxiliares de `test_s04_viewport.py`."""
import importlib, sys  # noqa: E401
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from test_s04_viewport import CORES, RAIZ, caso as _caso, captura, esperar, lote, novo, rodar, viewport  # noqa: F401

ESTE = Path(__file__).resolve()
caso = lambda nome, *a, **k: _caso(nome, *a, alvo=ESTE, **k)  # noqa: E731
LARG = 200  # a grade de posições (1 m entre cubos) é uma só para todos os lotes: nenhum cubo encosta em outro
G = lambda j: f"{j:022d}"  # noqa: E731
TAMANHOS = {"A": 1, "D": 100, "B": 10_500, "C": 31_000}  # cubos: ~1 KB, ~80 KB, ~8,2 MiB, ~24,1 MiB (816 bytes de malha por cubo)

def lote_sint(n, ini):  # n cubos nos lugares ini..ini+n-1 da grade; GlobalId = posição (único na cena)
    pos = lambda k: ((k % LARG) - LARG / 2, (k // LARG) - 120.0, 0)  # noqa: E731
    l = lote(cubos=[(pos(ini + i), 0.3, CORES[(ini + i) % 3]) for i in range(n)])
    o = l.objetos.copy()
    o["guid"] = [G(ini + i).encode() for i in range(n)]
    return replace(l, objetos=o)

def sem_mortos(l, mortos):  # forma canônica do lote sem os objetos de `mortos`: vértices dos vivos em ordem, índices por soma parcial
    o = l.objetos
    vivo = np.array([g.decode() not in mortos for g in o["guid"]], bool)
    kv, ki = np.repeat(vivo, o["n_vertices"]), np.repeat(vivo, o["n_indices"])
    assert len(kv) == len(l.vertices) and len(ki) == len(l.indices), "lote sintético tem de ser todo coberto pela tabela"
    mortos_antes = np.cumsum(~kv) - (~kv)  # vértices removidos antes de cada vértice
    ind = l.indices[ki]
    novo_o = o[vivo].copy()
    novo_o["primeiro_vertice"] = np.cumsum(novo_o["n_vertices"]) - novo_o["n_vertices"]
    novo_o["primeiro_indice"] = np.cumsum(novo_o["n_indices"]) - novo_o["n_indices"]
    return replace(l, vertices=l.vertices[kv], indices=(ind - mortos_antes[ind]).astype(np.uint32), objetos=novo_o)

def tabela(c, faixa):  # a tabela de uma chamada = concatenação de objetos(q) para as sequências q da faixa (anterior + 1 até a devolvida)
    ds = [c.objetos(q) for q in range(faixa[0], faixa[1] + 1)]
    t = {k: np.concatenate([np.asarray(d[k]).ravel() for d in ds]) for k in ("id_step", "n_indices", "n_vertices")}
    return ds, t | {"caixa": np.concatenate([np.asarray(d["caixa"]).reshape(-1, 6) for d in ds]), "guid": [g for d in ds for g in d["guid"]]}

def confere(c, faixas, lotes, mortos, n_lotes, rotulo):  # compara a tabela de cada chamada, estatísticas e caixa da cena com a forma canônica; devolve falhas
    falhas, tri, ver, caixas = [], 0, 0, []
    for faixa, l in zip(faixas, lotes):
        e = sem_mortos(l, mortos)
        ds, t = tabela(c, faixa)
        o = e.objetos
        tri, ver = tri + len(e.indices) // 3, ver + len(e.vertices)
        caixas += [np.r_[o["caixa_min"].min(0), o["caixa_max"].max(0)]] if len(o) else []
        ok = t["guid"] == [x.decode() for x in o["guid"]]
        for k in ("id_step", "n_indices", "n_vertices"):
            ok = ok and t[k].tolist() == o[k].tolist()
        ok = ok and np.array_equal(t["caixa"], np.c_[o["caixa_min"], o["caixa_max"]].reshape(-1, 6))
        for d in ds:  # em cada sub-lote as faixas começam em 0 e são contíguas; sem partir (1 sub-lote) são exatamente as da forma canônica
            for p, n in (("primeiro_indice", "n_indices"), ("primeiro_vertice", "n_vertices")):
                ok = ok and d[p].tolist() == (np.cumsum(d[n]) - d[n]).tolist() and (len(ds) > 1 or d[p].tolist() == o[p].tolist())
        ok or falhas.append(f"{rotulo}: tabela da chamada (sequências {faixa[0]} a {faixa[1]}) diferente da forma canônica")
    s = c.estatisticas()
    s["triangulos"] == tri and s["vertices"] == ver or falhas.append(f"{rotulo}: triângulos/vértices {s['triangulos']}/{s['vertices']}, esperado {tri}/{ver}")
    s["lotes"] == n_lotes or falhas.append(f"{rotulo}: lotes {s['lotes']}, esperado {n_lotes}")
    return falhas, (np.minimum.reduce([x[:3] for x in caixas]) + np.maximum.reduce([x[3:] for x in caixas])) / 2

def c_equivalencia(res):
    c, w, _ = novo(0)
    ini, lotes = 0, {}
    for k, n in TAMANHOS.items():
        lotes[k], ini = lote_sint(n, ini), ini + n
    ordem = ["A", "D", "B", "C"]
    faixas, ult = [], 0
    for k in ordem:  # cada chamada devolve a sequência do ÚLTIMO sub-lote; os sub-lotes dela são os seguidos, de ult + 1 até a devolvida
        s = c.adicionar_lote(lotes[k])
        faixas.append((ult + 1, s))
        ult = s
    L = [lotes[k] for k in ordem]
    mortos, falhas = set(), []
    n_lotes = sum(b - a + 1 for a, b in faixas)  # lotes = sub-lotes dessas faixas + um por marcador
    guid = lambda k, j: lotes[k].objetos["guid"][j].decode()  # noqa: E731
    ops = [("1 objeto do lote de 24 MiB", [guid("C", 15_000)]),
           ("vários do mesmo lote (8 MiB)", [guid("B", j) for j in (0, 1, 5_000, 10_499)]),
           ("objetos de lotes diferentes", [guid("C", 0), guid("B", 7), guid("D", 50), guid("C", 30_999)]),
           ("nenhum (GUID inexistente)", ["Z" * 22]),
           ("todos os de um lote (1 KB)", [guid("A", 0)]),
           ("todos os de um lote (80 KB)", [guid("D", j) for j in range(TAMANHOS["D"])])]
    res["tempos"] = []
    for nome, rem in ops:
        antes = c.estatisticas()["lotes"]
        s = c.atualizar(None, rem)
        mortos |= set(rem)
        n_lotes += 1  # o `atualizar` sem lote novo põe 1 marcador (1 lote, 1 sequência)
        c.estatisticas()["lotes"] - antes == 1 or falhas.append(f"{nome}: lotes subiu {c.estatisticas()['lotes'] - antes}, o marcador é 1 lote")
        s == ult + 1 or falhas.append(f"{nome}: sequência {s}, esperado {ult + 1} (marcador = 1 lote)")
        ult = s
        f, centro = confere(c, faixas, L, mortos, n_lotes, nome)
        falhas += f
        c.enquadrar()
        ok = yield from esperar(lambda: np.allclose(c.camera()["alvo"], centro, atol=1e-3), 4000)
        ok or falhas.append(f"{nome}: centro da caixa da cena {list(c.camera()['alvo'])}, esperado {centro.tolist()}")
    ok = yield from esperar(lambda: c.estatisticas()["triangulos_na_placa"] == c.estatisticas()["triangulos"], 120000)
    yield 800
    a = captura(c).copy()
    c.limpar()  # a mesma cena, remontada do zero com a forma canônica (lotes que ficaram vazios não entram)
    for l in L:
        e = sem_mortos(l, mortos)
        len(e.objetos) and c.adicionar_lote(e)
    c.enquadrar()
    ok2 = yield from esperar(lambda: c.estatisticas()["triangulos_na_placa"] == c.estatisticas()["triangulos"], 120000)
    yield 800
    b = captura(c)
    res.update(falhas=falhas, na_placa=bool(ok and ok2), imagem_igual=bool(np.array_equal(a, b)), pixels_dif=int((a != b).any(-1).sum()),
               pixels_cena=int((np.abs(a[..., :3].astype(int) - np.array([30, 30, 40])).max(-1) > 25).sum()))
    c.parar()

def c_marcador(res):
    c, w, _ = novo(0)
    l = lote_sint(500, 0)
    s0, falhas = c.adicionar_lote(l), []
    def foto():
        d, st = c.objetos(s0), c.estatisticas()
        return [list(d["guid"]), d["primeiro_indice"].tolist(), d["primeiro_vertice"].tolist(), d["caixa"].tolist(), st["triangulos"], st["vertices"]]
    antes, seqs = foto(), [s0]
    vazio = replace(l, vertices=l.vertices[:0], indices=l.indices[:0], objetos=l.objetos[:0])
    for nome, args in {"atualizar(None, [])": (None, []), "lote só com marcador": (vazio, []), "atualizar(None, []) de novo": (None, [])}.items():
        seqs.append(c.atualizar(*args))
        foto() == antes or falhas.append(f"{nome}: mudou a tabela ou as contagens")
    all(b == a + 1 for a, b in zip(seqs, seqs[1:])) or falhas.append(f"cada marcador é 1 lote e as sequências são seguidas: {seqs}")
    res.update(falhas=falhas, seqs=seqs)
    c.parar()
    yield 0

def c_bytes_copia(res):
    c, w, _ = novo(0)
    b = lote_sint(TAMANHOS["B"], 0)
    c.adicionar_lote(lote_sint(1, TAMANHOS["B"]))
    c.adicionar_lote(b)
    novo_l = lote_sint(4, TAMANHOS["B"] + 1)  # poucos KB, GlobalIds novos
    antes = c.estatisticas()["bytes_copia"]
    c.atualizar(novo_l, [b.objetos["guid"][5_000].decode()])  # troca: parede nova + remoção de 1 parede num lote de ~8,2 MiB
    depois = c.estatisticas()["bytes_copia"]
    res.update(antes=antes, depois=depois, bytes_novo=int(novo_l.vertices.nbytes + novo_l.indices.nbytes + novo_l.objetos.nbytes),
               tam_lote=int(b.vertices.nbytes + b.indices.nbytes + b.objetos.nbytes))
    yield 0
    c.parar()

def test_sem_equivale_a_forma_canonica_por_peca_e_a_cena_remontada(viewport):  # critérios 1 e 4 (tabela de cada lote, contagens, caixa, imagem)
    r = caso("equivalencia", limite=900)
    assert not r["falhas"], "\n".join(r["falhas"])
    assert r["na_placa"] and r["pixels_cena"] >= 500, f"a cena não chegou à placa ou a imagem está vazia: {r}"
    assert r["imagem_igual"], f"a cena operada difere da remontada com a forma canônica em {r['pixels_dif']} pixels"

def test_marcador_vazio_e_lote_so_com_marcador_nao_mudam_nada(viewport):  # critério 3
    r = caso("marcador")
    assert not r["falhas"], "\n".join(r["falhas"])

def test_bytes_copia_sobe_so_o_lote_novo(viewport):  # critério 2; hoje a sobra de capacidade é de megabytes
    r = caso("bytes_copia")
    print(f"MEDIDO bytes_copia antes {r['antes']} depois {r['depois']} diferença {r['depois'] - r['antes']} (lote novo {r['bytes_novo']}, lote tocado {r['tam_lote']})")
    assert abs(r["depois"] - r["antes"]) <= r["bytes_novo"] + 64 * 1024, f"bytes_copia {r['antes']} -> {r['depois']}: diferença {r['depois'] - r['antes']}"

if __name__ == "__main__":
    sys.path.insert(0, str(RAIZ / "prototypes"))
    nome, *resto = sys.argv[1:]
    assert not {"obimcore", "PySide6.QtCore"} & sys.modules.keys(), "o oráculo importou Qt ou obimcore antes da ordem pedida"
    [importlib.import_module(m) for m in ("ifcopenshell", "obimcore")]
    rodar(lambda r: globals()["c_" + nome](r, *resto))
