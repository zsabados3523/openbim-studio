# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo do F0-S04-T30d2 (LOTE_OPUS_63 §3 ponto 4): a cena parte um lote grande em sub-lotes de até C = 8 MiB de vértices e índices (nv*28 + ni*4),
na fronteira de peça. Quem implementa o T30a2/T30b não edita este arquivo. Cada caso roda em subprocesso sob `xvfb-run`, como em `test_s04_viewport.py`.
Guardas (pulam, nunca afrouxam): `Cena.dados_lote` (T30a3, bits), `nao_partidos`/`pecas_maiores_que_c` em `estatisticas()` (T30b), Linux (/proc).
Uma chamada devolve a sequência do ÚLTIMO sub-lote; os sub-lotes dela são os seguidos (anterior + 1 até a devolvida); a tabela da chamada é a
concatenação de `objetos(q)` dessa faixa (função `tabela`, do oráculo do T30a1)."""
import gc, importlib, sys, time  # noqa: E401
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from test_s04_t30a1_sem_oraculo import G, sem_mortos, tabela
from test_s04_viewport import CORES, RAIZ, caso as _caso, captura, cubo, esperar, novo, quadros, rodar, viewport  # noqa: F401

ESTE = Path(__file__).resolve()
caso = lambda nome, *a, **k: _caso(nome, *a, alvo=ESTE, **k)  # noqa: E731
C = 8 << 20
PEQ, GIGANTE, METADE = (30, 90), (200_000, 900_000), (100_000, 348_576)  # (vértices, índices): 1,2 KB; 9,2 MB (> C); 4 MiB (duas = C exato)
tam = lambda p: p[0] * 28 + p[1] * 4  # noqa: E731

def cubos(n, ini=0):  # n cubos (816 bytes de malha cada) na grade de 1 m; GlobalId = posição na grade; vetorizado (lotes de dezenas de MiB)
    from viewport_qrhi.carregador import DTYPE_OBJETO, DTYPE_VERTICE, LoteMalha
    p0, n0, i0 = cubo((0, 0, 0), 0.3, 0)
    k = np.arange(ini, ini + n)
    pos = np.c_[(k % 200) - 100.0, (k // 200) - 120.0, 0 * k]
    v, o, j = np.empty(24 * n, DTYPE_VERTICE), np.empty(n, DTYPE_OBJETO), np.arange(n)
    v["pos"], v["normal"], v["cor"] = (p0[None] + pos[:, None]).reshape(-1, 3), np.tile(n0, (n, 1)), np.repeat(np.array(CORES)[k % 3], 24, axis=0)
    o["id_step"], o["guid"] = j, [G(x).encode() for x in k]
    o["primeiro_indice"], o["n_indices"], o["primeiro_vertice"], o["n_vertices"] = 36 * j, 36, 24 * j, 24
    o["caixa_min"], o["caixa_max"] = pos + p0.min(0), pos + p0.max(0)
    return LoteMalha(0, v, (np.array(i0, np.uint32)[None] + 24 * j.astype(np.uint32)[:, None]).ravel(), o, np.zeros(3), n, n)

def pecas(spec, ini=0):  # uma peça por (vértices, índices) de `spec`, com ni >= nv e ni múltiplo de 3 (todo vértice é usado: a caixa da peça é a dos vértices)
    from viewport_qrhi.carregador import DTYPE_OBJETO, DTYPE_VERTICE, LoteMalha
    nv, ni = np.array([s[0] for s in spec]), np.array([s[1] for s in spec])
    pv, pi = np.cumsum(nv) - nv, np.cumsum(ni) - ni
    v, o = np.zeros(nv.sum(), DTYPE_VERTICE), np.zeros(len(spec), DTYPE_OBJETO)
    v["pos"][:, 0] = np.concatenate([(np.arange(m) % 97) / 8 + 100 * j for j, m in enumerate(nv)])
    v["pos"][:, 1], v["normal"][:, 2], v["cor"] = (np.arange(len(v)) % 89) / 8, 1, CORES[0]
    ind = np.concatenate([np.arange(a) % m + b for a, m, b in zip(ni, nv, pv)]).astype(np.uint32)
    for j in range(len(spec)):
        p = v["pos"][pv[j]:pv[j] + nv[j]]
        o[j] = (j, G(ini + j).encode(), pi[j], ni[j], pv[j], nv[j], p.min(0), p.max(0))
    return LoteMalha(0, v, ind, o, np.zeros(3), len(spec), len(spec))

def compartilhado(l, j=5):  # a peça j usa um vértice da peça j+1 (não ladrilha): índice trocado e caixa da peça refeita pelos triângulos
    o, i = l.objetos.copy(), l.indices.copy()
    i[o["primeiro_indice"][j]] = o["primeiro_vertice"][j + 1]
    p = l.vertices["pos"][i[o["primeiro_indice"][j]:o["primeiro_indice"][j] + o["n_indices"][j]]]
    o["caixa_min"][j], o["caixa_max"][j] = p.min(0), p.max(0)
    return replace(l, indices=i, objetos=o)

def fora_de_ordem(l):  # tabela com as 2 primeiras linhas trocadas: as faixas não seguem a ordem do buffer
    o = l.objetos.copy()
    o[[0, 1]] = o[[1, 0]]
    return replace(l, objetos=o)

def cena():  # sem iniciar: nada de placa nem janela, só os dados
    import obimcore
    return obimcore.Cena(True)

def bytes_de(ds):
    return sum(int(d["n_vertices"].sum()) * 28 + int(d["n_indices"].sum()) * 4 for d in ds)

def minimo(bs):  # menor número de sub-lotes contíguos de até C (peça maior que C fica sozinha)
    n, acc = 1, 0
    for b in bs:
        n, acc = (n + 1, 0) if acc and acc + b > C else (n, acc)
        acc += b
    return n

def une(c, l, faixa, rot):  # (falhas da forma, falhas em bits): a união dos sub-lotes da faixa é a forma canônica da entrada, por GlobalId
    ds, t = tabela(c, faixa)
    o, f, b = l.objetos, [], []
    ok = t["guid"] == [g.decode() for g in o["guid"]] and np.array_equal(t["caixa"], np.c_[o["caixa_min"], o["caixa_max"]])
    ok = ok and all(t[k].tolist() == o[k].tolist() for k in ("id_step", "n_indices", "n_vertices"))
    for d in ds:  # as faixas começam em 0 em cada sub-lote e são contíguas; lote inteiro (1 sub-lote): são exatamente as da entrada
        for p, n in (("primeiro_indice", "n_indices"), ("primeiro_vertice", "n_vertices")):
            ok = ok and (d[p].tolist() == (np.cumsum(d[n]) - d[n]).tolist() if len(ds) > 1 else d[p].tolist() == o[p].tolist())
    ok or f.append(f"{rot}: a união das tabelas da faixa {faixa} difere da entrada")
    if hasattr(c, "dados_lote"):
        pos, tv, ti = {g: k for k, g in enumerate(o["guid"])}, 0, 0
        for q, d in zip(range(faixa[0], faixa[1] + 1), ds):
            V, I = c.dados_lote(q)
            tv, ti = tv + len(V), ti + len(I)
            if len(ds) == 1:
                ok = V.tobytes() == l.vertices.tobytes() and np.array_equal(I, l.indices)
            elif len(d["guid"]):
                a, z = pos[d["guid"][0].encode()], pos[d["guid"][-1].encode()]
                v0, v1 = int(o["primeiro_vertice"][a]), int(o["primeiro_vertice"][z] + o["n_vertices"][z])
                i0, i1 = int(o["primeiro_indice"][a]), int(o["primeiro_indice"][z] + o["n_indices"][z])
                ok = V.tobytes() == l.vertices[v0:v1].tobytes() and np.array_equal(I.astype(np.int64) + v0, l.indices[i0:i1])
            else:
                ok = len(V) == 0 and len(I) == 0
            ok or b.append(f"{rot}: bits do sub-lote {q} diferem da entrada (por GlobalId)")
        tv == len(l.vertices) and ti == len(l.indices) or b.append(f"{rot}: soma de vértices/índices dos sub-lotes {tv}/{ti}, entrada {len(l.vertices)}/{len(l.indices)}")
    return f, b

def c_teto(res):  # itens 3, 4 e 10
    c = cena()
    big, ult = cubos(10_281), 0
    casos = [("exatamente C (2 peças de 4 MiB)", pecas([METADE] * 2), minimo([tam(METADE)] * 2), (0, 0)),
             ("C mais 1 peça pequena", pecas([METADE] * 2 + [(3, 3)]), minimo([tam(METADE)] * 2 + [tam((3, 3))]), (0, 0)),
             ("10.280 cubos (≤ C)", cubos(10_280), 1, (0, 0)),
             ("10.281 cubos (C + 1 peça)", big, 2, (0, 0)),
             ("peça gigante sozinha", pecas([GIGANTE]), 1, (0, 1)),
             ("gigante no início", pecas([GIGANTE] + [PEQ] * 5), 2, (0, 1)),
             ("gigante no meio", pecas([PEQ] * 2 + [GIGANTE] + [PEQ] * 2), 3, (0, 1)),
             ("gigante no fim", pecas([PEQ] * 2 + [GIGANTE]), 2, (0, 1)),
             ("vértice compartilhado, ≤ C", compartilhado(cubos(50)), 1, (0, 0)),
             ("vértice compartilhado, > C", compartilhado(big), 1, (1, 0)),
             ("tabela fora de ordem, ≤ C", fora_de_ordem(cubos(50)), 1, (0, 0)),
             ("tabela fora de ordem, > C", fora_de_ordem(big), 1, (1, 0))]
    res.update(falhas_teto=[], falhas_forma=[], falhas_bits=[], falhas_contadores=[], acessor=hasattr(c, "dados_lote"), contadores="nao_partidos" in c.estatisticas())
    for nome, l, n_partes, (n_np, n_pm) in casos:
        antes = c.estatisticas()
        s = c.adicionar_lote(l)
        faixa, ult = (ult + 1, s), s
        ds, _ = tabela(c, faixa)
        depois = c.estatisticas()
        len(ds) == n_partes or res["falhas_teto"].append(f"{nome}: {len(ds)} sub-lotes, esperado {n_partes}")
        depois["lotes"] - antes["lotes"] == len(ds) or res["falhas_teto"].append(f"{nome}: a cena ganhou {depois['lotes'] - antes['lotes']} lotes, a faixa tem {len(ds)}")
        for d in ds:  # todo sub-lote ≤ C, salvo o de uma só peça (maior que C) e o lote que não ladrilha (1 sub-lote com a entrada inteira)
            if bytes_de([d]) > C and len(d["guid"]) > 1 and len(ds) > 1:
                res["falhas_teto"].append(f"{nome}: sub-lote de {bytes_de([d])} bytes (> C) com {len(d['guid'])} peças")
        f, b = une(c, l, faixa, nome)
        res["falhas_forma"] += f
        res["falhas_bits"] += b
        if res["contadores"]:
            dif = (depois["nao_partidos"] - antes["nao_partidos"], depois["pecas_maiores_que_c"] - antes["pecas_maiores_que_c"])
            dif == (n_np, n_pm) or res["falhas_contadores"].append(f"{nome}: (nao_partidos, pecas_maiores_que_c) subiu {dif}, esperado {(n_np, n_pm)}")
    c.parar()
    yield 0

def c_sequencias(res):  # item 2
    c, f = cena(), []
    ant = c.adicionar_lote(cubos(31_000))
    f += [] if ant > 1 else ["lote de 31.000 cubos devolveu a sequência de um lote só"]
    novo_l = cubos(12_000, 100_000)  # > C: o lote novo também parte
    marcas = [("lote pequeno", lambda: c.adicionar_lote(cubos(5, 200_000)), 1, None), ("marcador", lambda: c.atualizar(None, []), 1, None),
              ("atualizar com lote novo > C", lambda: c.atualizar(novo_l, [G(7)]), 2, novo_l)]
    for nome, op, minimo_partes, l in marcas:
        antes, s = c.estatisticas()["lotes"], op()
        faixa = (ant + 1, s)
        s > ant or f.append(f"{nome}: sequência {s} não cresceu ({ant})")
        c.estatisticas()["lotes"] - antes == s - ant or f.append(f"{nome}: lotes subiu {c.estatisticas()['lotes'] - antes}, a faixa tem {s - ant}")
        s - ant >= minimo_partes or f.append(f"{nome}: {s - ant} sub-lote(s), esperado ao menos {minimo_partes}")
        nome == "marcador" and s - ant != 1 and f.append(f"marcador devolveu {s - ant} lotes, deve ser 1")
        l is None or f.extend(une(c, l, faixa, nome)[0])
        ant = s
    G(7) in [g for q in range(1, ant + 1) for g in c.objetos(q)["guid"]] and f.append("GlobalId removido ainda está na cena")  # os lotes antigos seguem legíveis, com as mesmas sequências
    res["falhas"] = f
    c.parar()
    yield 0

def c_desenho(res):  # item 5
    c, w, _ = novo(0)
    n, f = 31_000, []
    c.adicionar_lote(cubos(n))
    c.enquadrar()
    cheia = lambda: c.estatisticas()["triangulos_na_placa"] == 12 * n  # noqa: E731
    ok = yield from esperar(cheia, 120000)
    yield 800
    a, cam = captura(c).copy(), np.r_[c.camera()["alvo"], c.camera()["distancia"]]
    n0 = c.estatisticas()["contextos"]
    c.perder_contexto()
    ok2 = yield from esperar(lambda: c.estatisticas()["contextos"] > n0 and cheia(), 120000)
    yield 800
    d = captura(c).copy()
    c.limpar()  # a mesma cena entregue já partida pelo Python: 4 lotes de 7.750 cubos (6,3 MB, abaixo de C)
    [c.adicionar_lote(cubos(7_750, k * 7_750)) for k in range(4)]
    c.enquadrar()
    ok3 = yield from esperar(cheia, 120000)
    yield 800
    b = captura(c).copy()
    np.allclose(np.r_[c.camera()["alvo"], c.camera()["distancia"]], cam) or f.append("a câmera enquadrada da cena partida pelo Python difere")
    res.update(falhas=f, na_placa=bool(ok and ok2 and ok3), dif_python=int((a != b).any(-1).sum()), dif_contexto=int((a != d).any(-1).sum()),
               pixels_cena=int((np.abs(a[..., :3].astype(int) - np.array([30, 30, 40])).max(-1) > 25).sum()))
    c.parar()

def c_honestidade(res):  # item 6
    c, w, _ = novo(0)
    n = 31_000
    s = c.adicionar_lote(cubos(n))
    viol, prim, t0 = [], None, time.perf_counter()
    while time.perf_counter() - t0 < 120:
        fr = [x for x in quadros(c) if x[1] >= s]  # relogio primeiro, placa depois: a placa lida é a do instante do quadro ou mais nova
        tri = c.estatisticas()["triangulos_na_placa"]
        if fr and tri < 12 * n:
            viol.append(tri)
        if fr and tri == 12 * n:
            prim = fr[0]
            break
        yield 5
    res.update(viol=viol, achou=prim is not None, sublotes=s)
    c.parar()

def c_erros(res):  # item 7
    c, f = cena(), []
    c.adicionar_lote(cubos(20))
    big = cubos(30_000, 100)
    o = big.objetos.copy()
    o["primeiro_indice"][-1] = len(big.indices)  # faixa do último objeto passa do fim
    ind = big.indices.copy()
    ind[-1] = len(big.vertices)  # o último índice (no último sub-lote) aponta para fora
    ruins = {"índice fora do lote": replace(big, indices=ind), "faixa de objeto fora do lote": replace(big, objetos=o),
             "deslocamento diferente": replace(big, deslocamento=np.array([5.0, 0, 0])), "índices fora de múltiplo de 3": replace(big, indices=big.indices[:-1])}
    estado = lambda: ({k: c.estatisticas()[k] for k in ("lotes", "triangulos", "vertices", "bytes_copia")}, [list(c.objetos(1)["guid"])])  # noqa: E731
    for nome, l in ruins.items():
        for via, op in (("adicionar_lote", lambda: c.adicionar_lote(l)), ("atualizar", lambda: c.atualizar(l, [G(0)]))):
            antes = estado()
            try:
                op()
                f.append(f"{nome} ({via}): aceitou o lote")
            except ValueError:
                pass
            except Exception as e:  # noqa: BLE001
                f.append(f"{nome} ({via}): {type(e).__name__} em vez de ValueError")
            estado() == antes or f.append(f"{nome} ({via}): a cena mudou ({antes} -> {estado()})")
    try:
        c.objetos(c.estatisticas()["lotes"] + 1)
        f.append("sequência de sub-lote publicado pela metade")
    except ValueError:
        pass
    res["falhas"] = f
    c.parar()
    yield 0

def c_desalinhado(res):  # item 8
    c, f = cena(), []
    def desalinha(a):
        m = np.frombuffer(bytearray(a.nbytes + 2), "<u4", count=a.size, offset=2)
        m[:] = a
        assert not m.flags.aligned
        return m
    for n, ini in ((12_000, 0), (50, 50_000)):
        ant = c.estatisticas()["lotes"]
        l = cubos(n, ini)
        s1 = c.adicionar_lote(l)
        s2 = c.adicionar_lote(replace(l, indices=desalinha(l.indices)))
        (s1 - ant) == (s2 - s1) or f.append(f"{n} cubos: {s1 - ant} sub-lotes alinhados, {s2 - s1} desalinhados")
        for fx in ((ant + 1, s1), (s1 + 1, s2)):
            fa, fb = une(c, l, fx, f"{n} cubos {fx}")
            f += fa + fb
    res["falhas"] = f
    c.parar()
    yield 0

def c_bytes(res):  # item 9
    c = cena()
    c.adicionar_lote(cubos(1_000))
    por_obj = (c.estatisticas()["bytes_copia"] - 1_000 * 816) / 1_000  # custo de tabela e texto do GlobalId por objeto, medido num lote que não parte
    b0, l = c.estatisticas()["bytes_copia"], cubos(30_000, 5_000)
    s = c.adicionar_lote(l)
    ds, _ = tabela(c, (2, s))
    res.update(delta=c.estatisticas()["bytes_copia"] - b0, esperado=bytes_de(ds) + 30_000 * por_obj, dados=bytes_de(ds), entrada=l.vertices.nbytes + l.indices.nbytes, sub=len(ds))
    c.parar()
    yield 0

def c_memoria(res):  # item 11 (Linux)
    hwm = lambda: int([x for x in open("/proc/self/status") if x.startswith("VmHWM")][0].split()[1]) * 1024  # noqa: E731
    try:
        open("/proc/self/clear_refs", "w").write("5")
    except OSError as e:
        res["pulou"] = f"sem /proc/self/clear_refs: {e}"
        return
    l, c = cubos(82_000), cena()  # ~64 MiB de malha
    gc.collect()
    open("/proc/self/clear_refs", "w").write("5")
    h0 = hwm()
    c.adicionar_lote(l)
    res.update(subiu=hwm() - h0, lote=l.vertices.nbytes + l.indices.nbytes + l.objetos.nbytes)
    c.parar()
    yield 0

def test_teto_de_cada_sublote_e_numero_minimo_de_sublotes(viewport):  # item 3
    r = caso("teto", limite=600)
    assert not r["falhas_teto"], "\n".join(r["falhas_teto"])

def test_uniao_dos_sublotes_e_a_forma_canonica_da_entrada(viewport):  # item 4 (tabelas; contra o `main` vale com 1 sub-lote)
    r = caso("teto", limite=600)
    assert not r["falhas_forma"], "\n".join(r["falhas_forma"])

def test_uniao_dos_sublotes_igual_em_bits_por_globalid(viewport):  # item 4, pelo acessor `dados_lote` (T30a3)
    r = caso("teto", limite=600)
    r["acessor"] or pytest.skip("sem Cena.dados_lote (T30a3)")
    assert not r["falhas_bits"], "\n".join(r["falhas_bits"])

def test_contadores_nao_partidos_e_pecas_maiores_que_c(viewport):  # item 10, com guarda até o T30b
    r = caso("teto", limite=600)
    r["contadores"] or pytest.skip("estatisticas() sem nao_partidos/pecas_maiores_que_c (T30b)")
    assert not r["falhas_contadores"], "\n".join(r["falhas_contadores"])

def test_sequencias_seguidas_crescentes_e_atualizar_devolve_a_do_ultimo(viewport):  # item 2
    r = caso("sequencias", limite=600)
    assert not r["falhas"], "\n".join(r["falhas"])

def test_desenho_igual_ao_partido_pelo_python_e_apos_perder_contexto(viewport):  # item 5
    r = caso("desenho", limite=900)
    assert not r["falhas"], "\n".join(r["falhas"])
    assert r["na_placa"] and r["pixels_cena"] >= 500, f"a cena não chegou à placa ou a imagem está vazia: {r}"
    assert r["dif_python"] == 0 and r["dif_contexto"] == 0, f"pixels diferentes: contra o partido pelo Python {r['dif_python']}, depois de perder o contexto {r['dif_contexto']}"

def test_primeiro_quadro_com_a_sequencia_da_chamada_ja_tem_todos_os_sublotes_na_placa(viewport):  # item 6
    r = caso("honestidade", limite=600)
    assert r["achou"], "nenhum quadro com a sequência da chamada chegou a ser apresentado com a placa cheia"
    assert not r["viol"], f"quadro com a sequência {r['sublotes']} apresentado com a placa incompleta (triângulos na placa: {r['viol'][:3]})"

def test_erros_recusam_o_lote_inteiro_e_a_cena_fica_intacta(viewport):  # item 7
    r = caso("erros", limite=600)
    assert not r["falhas"], "\n".join(r["falhas"])

def test_indices_desalinhados_dao_o_mesmo_resultado_dos_alinhados(viewport):  # item 8
    r = caso("desalinhado", limite=600)
    assert not r["falhas"], "\n".join(r["falhas"])

def test_bytes_copia_e_a_soma_exata_dos_sublotes(viewport):  # item 9
    r = caso("bytes", limite=600)
    print(f"MEDIDO sub-lotes {r['sub']} delta {r['delta']} esperado {r['esperado']}")
    assert r["dados"] == r["entrada"], f"os sub-lotes somam {r['dados']} bytes de malha, a entrada tem {r['entrada']}"
    assert abs(r["delta"] - r["esperado"]) <= 64 * 1024, f"bytes_copia subiu {r['delta']}, soma dos sub-lotes {r['esperado']}"

def test_memoria_do_pico_ao_adicionar_lote_de_64_mib(viewport):  # item 11 (só Linux)
    sys.platform.startswith("linux") or pytest.skip("VmHWM só no Linux")
    r = caso("memoria", limite=600)
    "pulou" in r and pytest.skip(r["pulou"])
    print(f"MEDIDO pico subiu {r['subiu']} (lote {r['lote']})")
    assert r["subiu"] <= r["lote"] + C + (16 << 20), f"o pico subiu {r['subiu']} bytes; limite lote + C + 16 MiB = {r['lote'] + C + (16 << 20)}"

if __name__ == "__main__":
    sys.path.insert(0, str(RAIZ / "prototypes"))
    nome, *resto = sys.argv[1:]
    assert not {"obimcore", "PySide6.QtCore"} & sys.modules.keys(), "o oráculo importou Qt ou obimcore antes da ordem pedida"
    [importlib.import_module(m) for m in ("ifcopenshell", "obimcore")]
    rodar(lambda r: globals()["c_" + nome](r, *resto))
