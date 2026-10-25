# SPDX-License-Identifier: AGPL-3.0-or-later
"""Testes do reenvio por posição, instantâneo e contadores. Reenvio
não edita este arquivo. Cada caso roda em subprocesso sob `xvfb-run` (helpers de `test_s04_viewport.py` e de `test_s04_t30d2_sublotes_oraculo.py`).
Guardas (pulam, nunca afrouxam): `nao_partidos`/`pecas_maiores_que_c` em `estatisticas()` chave `geracao` em `estatisticas()` (não a
expõe hoje: o item "ger_" fica pulado até alguém expô-la; o "instantâneo coerente" não tem API no Python: o revisor lê o diff e o item 6 o cobre pelo piso
de triângulos na placa), `Cena.dados_lote`.
Os marcadores `@AINDA_NAO` (xfail estrito) foram retirados depois da correção de reenvio por posição (antes, o código principal reenviava a cena inteira a cada troca e `sem` subia `ger_`): `test_quadros_por_troca...`, `test_placa_nunca_...`,
`test_so_o_sublote_trocado_e_reenviado`, `test_troca_repetida...` e `test_apagar...`. Cena grande reduzida aos 4 lotes tocados (8,97, 24,24, 68,27 e 285,36 MiB, 387 MiB) mais o de 1 KB: com os 13 lotes (805,7 MiB) o `main`
leva ~500 s só nas trocas (reenvia tudo), e a conta de quadros do reenvio por posição é por lote tocado. O enchimento é de peças de ~1 MiB, para o sub-lote tocado
ser cheio (~8 MiB), como no detalhado. Trocas: 2 nos lotes de 8,97 e 285,36 (a mediana do item 4) e 1 nos demais."""
import importlib, statistics, sys, time  # noqa: E401
from pathlib import Path

import numpy as np
import pytest

from test_s04_t30a1_sem_oraculo import G
from test_s04_t30d2_sublotes_oraculo import C, GIGANTE, PEQ, compartilhado, cena, cubos, pecas
from test_s04_viewport import RAIZ, agora, caso as _caso, captura, esperar, novo, quadros, rodar, viewport  # noqa: F401

ESTE = Path(__file__).resolve()
caso = lambda nome, *a, **k: _caso(nome, *a, alvo=ESTE, **k)  # noqa: E731
MIB = (8.97, 24.24, 68.27, 285.36)  # lotes tocados (os outros 9 só atrasam: leva ~500 s com os 13; ver cabeçalho)
TOCADOS, ORC, AMARELO = {"8MiB": 0, "24MiB": 1, "68MiB": 2, "285MiB": 3}, 2 << 20, (240, 240, 30, 255)
NOMES = ("1KB", "8MiB", "24MiB", "68MiB", "285MiB")
CAM = dict(alvo=(-98.0, -45.0, 0.0), distancia=4.0, azimute=-90.0, elevacao=20.0)  # olha para os cubos 15.000 a 15.004 da grade de `cubos`

def lote_t27(mib, tag, paredes=()):  # paredes (36 vértices, 12 triângulos) primeiro; depois peças de enchimento de 36.000 vértices (1 MiB), vértice = índice
    from viewport_qrhi.carregador import DTYPE_OBJETO, DTYPE_VERTICE, LoteMalha
    nv = np.r_[[36] * len(paredes), [36_000] * (max(1, round(mib * (1 << 20) / 32 / 36_000)) if mib else 0)].astype(int)
    pv = np.cumsum(nv) - nv
    v, o = np.zeros(nv.sum(), DTYPE_VERTICE), np.zeros(len(nv), DTYPE_OBJETO)
    for j in range(len(paredes)):
        i = np.arange(36)
        v["pos"][pv[j]:pv[j] + 36, 0], v["pos"][pv[j]:pv[j] + 36, 1], v["cor"][pv[j]:pv[j] + 36] = (i % 6) * 0.2, (i // 6) * 0.2, (200, 200, 200, 255)
    o["guid"] = [(paredes[j] if j < len(paredes) else f"E{tag}{j:07d}").encode() for j in range(len(nv))]
    o["primeiro_indice"], o["n_indices"], o["primeiro_vertice"], o["n_vertices"], o["id_step"] = pv, nv, pv, nv, np.arange(len(nv))
    o["caixa_max"][:len(paredes)] = (1.0, 1.0, 0.0)
    return LoteMalha(0, v, np.arange(len(v), dtype=np.uint32), o, np.zeros(3), len(nv), len(nv))

def troca(c, op, total):  # gerador: roda `op` (devolve a sequência S), conta quadros até o primeiro com sequência >= S, mede `atualizar` e o piso da placa
    t0 = time.perf_counter()
    s = op()
    ms, t_cmd, tri_min, fim = (time.perf_counter() - t0) * 1000, agora(), 1 << 60, time.perf_counter() + 900
    while time.perf_counter() < fim:
        fr = quadros(c, t_cmd)
        tri_min = min(tri_min, c.estatisticas()["triangulos_na_placa"])
        k = [i for i, x in enumerate(fr) if x[1] >= s]
        if k:
            return dict(ms=ms, quadros=k[0] + 1, tri_min=int(tri_min), piso=total - 12, seq=s)
        yield 2
    raise TimeoutError(f"sem quadro com a sequência {s}")

def c_contadores(res):  # item 1: nao_partidos e pecas_maiores_que_c antes e depois de `sem`
    c = cena()
    est = lambda: tuple(c.estatisticas().get(k) for k in ("nao_partidos", "pecas_maiores_que_c"))  # noqa: E731
    c.adicionar_lote(pecas([GIGANTE, PEQ, GIGANTE, PEQ]))  # G(0..3): duas peças maiores que C
    c.adicionar_lote(compartilhado(cubos(10_281, 100)))  # não ladrilha e passa de C
    res["guarda"], f = est() != (None, None), []
    passos = [("duas gigantes e um lote que não parte", None, (1, 2)), ("sem a gigante G(0)", [G(0)], (1, 1)),
              ("sem a peça 5 do lote que não parte: cai para C, sai da conta", [G(105)], (0, 1)), ("sem a última gigante", [G(2)], (0, 0))]
    for nome, mortos, esperado in passos:
        mortos and c.atualizar(None, mortos)
        est() == esperado or f.append(f"{nome}: {est()}, esperado {esperado}")
    c.adicionar_lote(pecas([GIGANTE], 10))
    est() == (0, 1) or f.append(f"nova gigante: {est()}")
    c.limpar()
    est() == (0, 0) or f.append(f"depois de limpar(): {est()}")
    res["falhas"] = f
    c.parar()
    yield 0

def c_geracao(res):  # item 1: troca e remoção não sobem `ger_`; limpar() sobe
    c, f = cena(), []
    g = lambda: c.estatisticas().get("geracao")  # noqa: E731
    c.adicionar_lote(cubos(40))
    res["guarda"], g0 = g() is not None, g()
    if g0 is None:
        c.parar()
        return
    c.atualizar(cubos(1, 900), [G(3)])
    c.atualizar(None, [G(4)])
    g() == g0 or f.append(f"ger_ subiu em atualizar/remover: {g0} -> {g()}")
    c.limpar()
    g() > g0 or f.append(f"limpar() não subiu ger_: {g0} -> {g()}")
    res["falhas"] = f
    c.parar()
    yield 0

def c_trocas(res):  # itens 3 e 4 (e o piso de triângulos): cena grande na placa, trocas de uma parede por lote
    c, w, _ = novo(0)
    total = 0
    for i, m in enumerate(MIB):
        l = lote_t27(m, i, [f"W{i}{k}" for k in range(3)])
        c.adicionar_lote(l)
        total += len(l.vertices) // 3
    ok = yield from esperar(lambda: c.estatisticas()["triangulos_na_placa"] >= total, 900000)
    yield 500
    casos = res["casos"] = {n: [] for n in NOMES}
    res["na_placa"] = bool(ok)
    yield from troca(c, lambda: c.atualizar(lote_t27(0, "c", ["C0"]), []), total + 12)  # criar a parede de 1 KB (piso)
    total += 12
    yield 300
    for nome, i, n in zip(NOMES, (None, *TOCADOS.values()), (1, 2, 1, 1, 2)):
        for k in range(n):
            velho, novo_g = (f"C{k}", f"C{k + 1}") if i is None else (f"W{i}{k}", f"N{i}{k}")
            casos[nome].append((yield from troca(c, lambda: c.atualizar(lote_t27(0, "n", [novo_g]), [velho]), total)))
            yield 300
    c.parar()

def c_reenvio(res):  # item 2: trocar uma peça de lote grande refaz só o sub-lote dela (bits pelo `dados_lote`, mesma sequência)
    c, w, _ = novo(0)
    n = 31_000
    s = c.adicionar_lote(cubos(n))
    sub = [q for q in range(1, s + 1)]
    guids = {q: list(c.objetos(q)["guid"]) for q in sub}
    bits = {q: tuple(a.tobytes() for a in c.dados_lote(q)) for q in sub} if hasattr(c, "dados_lote") else None
    ok = yield from esperar(lambda: c.estatisticas()["triangulos_na_placa"] == 12 * n, 120000)
    yield 300
    alvo = G(n // 2)
    q_alvo = [q for q in sub if alvo in guids[q]][0]
    novo_l = cubos(1, 900_000)
    r = yield from troca(c, lambda: c.atualizar(novo_l, [G(n // 2)]), 12 * n)
    f = []
    for q in sub:
        mudou = list(c.objetos(q)["guid"]) != guids[q] or (bits and tuple(a.tobytes() for a in c.dados_lote(q)) != bits[q])
        if q != q_alvo and mudou:
            f.append(f"o sub-lote {q} (não tocado) mudou de guids ou de bits")
    alvo in [g for q in range(1, r["seq"] + 1) for g in c.objetos(q)["guid"]] and f.append("o GlobalId trocado ainda está na cena")
    # bytes por troca = lote novo + sub-lote trocado: o teto de quadros usa o que a cena guarda desse sub-lote e do lote novo
    b = (sum(len(x) for x in bits[q_alvo]) + novo_l.vertices.nbytes + novo_l.indices.nbytes) if bits else 0
    res.update(falhas=f, na_placa=bool(ok), sublotes=len(sub), quadros=r["quadros"], bytes_esperados=b, teto=-(-b // ORC) + 3, tem_acessor=bits is not None, tri_min=r["tri_min"])
    c.parar()

def conta(a, cor):  # pixels perto da cor (o sombreado escurece as faces)
    return int((np.abs(a[..., :3].astype(int) - np.array(cor[:3])).max(-1) < 70).sum())

def c_repetida(res):  # itens 5 e 6: captura no quadro de S; trocas repetidas durante o reenvio; apagar em <= 2 quadros; bytes_copia sem sobra
    c, w, _ = novo(0)
    n, f = 31_000, []
    c.definir_camera(**CAM)
    c.adicionar_lote(cubos(n))
    c.adicionar_lote(cubos(100, 500_000))  # lote pequeno (82 KB) para o apagar
    total = 12 * (n + 100)
    ok = yield from esperar(lambda: c.estatisticas()["triangulos_na_placa"] == total, 120000)
    yield 800
    cor_velha = ((240, 30, 30, 255), (30, 220, 30, 255), (30, 50, 240, 255))[15_000 % 3]
    a0, b0 = captura(c).copy(), c.estatisticas()["bytes_copia"]
    s1 = c.atualizar(cubos_em(15_000, 900_000), [G(15_000)])
    viol, t0 = [], time.perf_counter()
    while not [x for x in quadros(c) if x[1] >= s1] and time.perf_counter() - t0 < 120:
        viol += [t] if (t := c.estatisticas()["triangulos_na_placa"]) < total - 12 else []
        yield 5
    aS = captura(c).copy()  # o quadro da sequência S: sem a parede antiga e com a nova
    res.update(velha_antes=conta(a0, cor_velha), velha_depois=conta(aS, cor_velha), amarela_antes=conta(a0, AMARELO), amarela_depois=conta(aS, AMARELO))
    for j in range(1, 5):  # 4 trocas seguidas no mesmo lote, cada uma depois de ao menos um quadro novo da anterior (reenvio em curso)
        t_cmd = agora()
        s = c.atualizar(cubos_em(15_000 + j, 900_000 + j, AMARELO), [G(15_000 + j)])
        fim = time.perf_counter() + 120
        while j < 4 and not quadros(c, t_cmd) and time.perf_counter() < fim:
            viol += [t] if (t := c.estatisticas()["triangulos_na_placa"]) < total - 12 else []
            yield 2
    while not [x for x in quadros(c) if x[1] >= s] and time.perf_counter() - t0 < 240:
        viol += [t] if (t := c.estatisticas()["triangulos_na_placa"]) < total - 12 else []
        yield 5
    ok2 = yield from esperar(lambda: c.estatisticas()["triangulos_na_placa"] == total, 120000)
    yield 800
    antes = [g for q in range(1, s + 1) for g in c.objetos(q)["guid"]]
    f += [f"GlobalId {k} ainda na cena" for k in range(15_000, 15_005) if G(k) in antes]
    f += [f"GlobalId novo {k} ausente ou repetido" for k in range(900_000, 900_005) if antes.count(G(k)) != 1]
    res.update(falhas=f, viol=viol[:3], na_placa=bool(ok and ok2), delta_copia=c.estatisticas()["bytes_copia"] - b0)
    a, n0 = captura(c).copy(), c.estatisticas()["contextos"]
    c.perder_contexto()
    ok3 = yield from esperar(lambda: c.estatisticas()["contextos"] > n0 and c.estatisticas()["triangulos_na_placa"] == total, 120000)
    yield 800
    res.update(dif_contexto=int((a != captura(c)).any(-1).sum()), recuperou=bool(ok3), amarelas=conta(a, AMARELO))
    r = yield from troca(c, lambda: c.atualizar(None, [G(500_003)]), total)  # apagar um cubo do lote pequeno
    res.update(apagar_quadros=r["quadros"], apagar_tri_min=r["tri_min"], apagar_piso=r["piso"])
    c.parar()

def cubos_em(k, g, cor=AMARELO):  # um cubo no lugar do cubo k da grade, de outra cor, com o GlobalId G(g)
    l = cubos(1, k)
    l.vertices["cor"], l.objetos["guid"][0] = cor, G(g).encode()
    return l

def c_limpar(res):  # item 7: depois de limpar() e de reenviar a cena, a espera é pelo quadro com a sequência da última chamada, só depois pela placa cheia
    c, w, _ = novo(0)
    n = 31_000
    c.adicionar_lote(cubos(n))
    c.enquadrar()
    cheia = lambda: c.estatisticas()["triangulos_na_placa"] == 12 * n  # noqa: E731
    ok = yield from esperar(cheia, 120000)
    yield 800
    a = captura(c).copy()
    c.limpar()
    s = [c.adicionar_lote(cubos(7_750, k * 7_750)) for k in range(4)][-1]
    c.enquadrar()
    ok2 = yield from esperar(lambda: any(x[1] >= s for x in quadros(c)), 120000)
    ok3 = yield from esperar(cheia, 120000)
    yield 800
    res.update(na_placa=bool(ok and ok2 and ok3), dif=int((a != captura(c)).any(-1).sum()), pixels=int((np.abs(a[..., :3].astype(int) - np.array([30, 30, 40])).max(-1) > 25).sum()))
    c.parar()

def c_acessor(res):  # item 7: ValueError do `dados_lote` em sequência desconhecida e depois de limpar()
    c, f = cena(), []
    if not hasattr(c, "dados_lote"):
        res["guarda"] = False
        return
    s = c.adicionar_lote(cubos(20))
    for q in (0, -1, s + 1, 10**6):
        try:
            c.dados_lote(q)
            f.append(f"sequência {q}: aceitou")
        except ValueError:
            pass
    c.limpar()
    try:
        c.dados_lote(s)
        f.append("depois de limpar(): aceitou a sequência antiga")
    except ValueError:
        pass
    res.update(guarda=True, falhas=f)
    c.parar()
    yield 0

def test_contadores_nao_partidos_e_pecas_maiores_que_c_antes_e_depois_de_sem(viewport):  # item 1
    r = caso("contadores", limite=600)
    r["guarda"] or pytest.skip("estatisticas() sem nao_partidos/pecas_maiores_que_c")
    assert not r["falhas"], "\n".join(r["falhas"])

def test_troca_nao_sobe_a_geracao_e_limpar_sobe(viewport):  # item 1
    r = caso("geracao", limite=600)
    r["guarda"] or pytest.skip("estatisticas() sem a chave geracao")
    assert not r["falhas"], "\n".join(r["falhas"])

def test_quadros_por_troca_ate_teto_de_c_por_2_mib_mais_3_em_toda_faixa_de_lote(viewport):  # item 3
    r = caso("trocas", limite=1500)
    assert r["na_placa"], "a cena grande não chegou à placa"
    teto = C // ORC + 3
    ruins = [f"{n}: {x['quadros']} quadros" for n, xs in r["casos"].items() for x in xs if x["quadros"] > teto]
    print("MEDIDO quadros", {n: [x["quadros"] for x in xs] for n, xs in r["casos"].items()})
    assert not ruins, f"teto {teto} (= C ÷ 2 MiB + 3): " + "; ".join(ruins)

def test_atualizar_do_lote_de_285_mib_custa_no_maximo_3_vezes_o_de_8_97_mib(viewport):  # relativo, mesma rodada
    r = caso("trocas", limite=1500)
    ms = {n: statistics.median(x["ms"] for x in r["casos"][n]) for n in ("8MiB", "285MiB")}
    print("MEDIDO atualizar_ms mediana", ms)
    assert ms["285MiB"] <= 3 * ms["8MiB"], f"atualizar no lote de 285 MiB {ms['285MiB']:.2f} ms > 3 × {ms['8MiB']:.2f} ms (8,97 MiB)"

def test_placa_nunca_abaixo_da_cena_menos_a_peca_antiga_em_toda_troca(viewport):  # lote 62 §6.2 critério 2
    r = caso("trocas", limite=1500)
    ruins = [f"{n}: placa {x['tri_min']} < {x['piso']}" for n, xs in r["casos"].items() for x in xs if x["tri_min"] < x["piso"]]
    assert not ruins, "; ".join(ruins)

def test_sublotes_nao_tocados_ficam_com_os_mesmos_bits_e_a_mesma_sequencia(viewport):  # item 2
    r = caso("reenvio", limite=900)
    r["tem_acessor"] or pytest.skip("sem Cena.dados_lote")
    assert r["sublotes"] >= 3 and not r["falhas"], f"{r['sublotes']} sub-lotes; " + "\n".join(r["falhas"])

def test_so_o_sublote_trocado_e_reenviado_bytes_por_troca(viewport):  # bytes por troca = lote novo + sub-lote trocado
    r = caso("reenvio", limite=900)
    r["tem_acessor"] or pytest.skip("sem Cena.dados_lote")
    assert r["na_placa"] and 0 < r["bytes_esperados"] <= C + (1 << 20), r
    assert r["quadros"] <= r["teto"], f"{r['quadros']} quadros; teto(bytes {r['bytes_esperados']} ÷ 2 MiB) + 3 = {r['teto']}"

def test_captura_no_quadro_de_s_sem_a_parede_antiga_e_com_a_nova(viewport):  # item 5
    r = caso("repetida", limite=1500)
    assert r["na_placa"] and r["velha_antes"] >= 200 and r["amarela_antes"] == 0, f"cena de partida sem o cubo à vista: {r}"
    assert r["velha_depois"] <= r["velha_antes"] - 200 and r["amarela_depois"] >= 200, f"no quadro de S: cor velha {r['velha_antes']} -> {r['velha_depois']}, nova {r['amarela_antes']} -> {r['amarela_depois']}"

def test_captura_depois_das_trocas_igual_pixel_a_pixel_a_de_depois_de_perder_contexto(viewport):  # item 5
    r = caso("repetida", limite=1500)
    assert r["recuperou"] and r["amarelas"] >= 800, f"a placa não voltou ou os 5 cubos novos não aparecem: {r}"
    assert r["dif_contexto"] == 0, f"{r['dif_contexto']} pixels diferentes depois de perder o contexto"

def test_troca_repetida_no_mesmo_lote_durante_o_reenvio_mantem_piso_e_estado_final(viewport):
    r = caso("repetida", limite=1500)
    assert r["na_placa"] and not r["falhas"], "\n".join(r["falhas"])
    assert not r["viol"], f"a placa ficou abaixo da cena menos a peça antiga: {r['viol']}"

def test_bytes_copia_das_trocas_repetidas_sem_sobra(viewport):  # item 6 (lote 62 §6.4 ponto 7)
    r = caso("repetida", limite=1500)
    assert abs(r["delta_copia"]) <= 5 * 816 + 64 * 1024, f"bytes_copia mudou {r['delta_copia']} em 5 trocas de cubo por cubo"

def test_apagar_em_lote_de_ate_2_mib_leva_no_maximo_2_quadros(viewport):
    r = caso("repetida", limite=1500)
    assert r["apagar_quadros"] <= 2 and r["apagar_tri_min"] >= r["apagar_piso"], f"apagar: {r['apagar_quadros']} quadros, placa mínima {r['apagar_tri_min']} (piso {r['apagar_piso']})"

def test_limpar_e_reenviar_espera_o_quadro_da_sequencia_antes_da_placa_cheia(viewport):  # item 7 (sugestão 1 do lote 64)
    r = caso("limpar", limite=900)
    assert r["na_placa"] and r["pixels"] >= 500, r
    assert r["dif"] == 0, f"{r['dif']} pixels diferentes depois de limpar() e reenviar a mesma cena"

def test_dados_lote_recusa_sequencia_desconhecida_e_limpa_com_value_error(viewport):
    r = caso("acessor", limite=600)
    r["guarda"] or pytest.skip("sem Cena.dados_lote")
    assert not r["falhas"], "\n".join(r["falhas"])

if __name__ == "__main__":
    sys.path.insert(0, str(RAIZ / "prototypes"))
    nome, *resto = sys.argv[1:]
    assert not {"obimcore", "PySide6.QtCore"} & sys.modules.keys(), "o teste importou Qt ou obimcore antes da ordem pedida"
    [importlib.import_module(m) for m in ("ifcopenshell", "obimcore")]
    rodar(lambda r: globals()["c_" + nome](r, *resto))
