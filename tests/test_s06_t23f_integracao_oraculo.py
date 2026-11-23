# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oraculo F0-S06-T23f (cartao T23f; especificacao T23 §3, §7, §8): filho REAL (`FilhoPersistente` + `persistente.servir`) com construtor REAL.
Sintetico de 2.000 pecas (cubos de 40 tamanhos, gerado em tmp_path) e casa-simples.ifc. Sem IFC do PO. Sem mocks do construtor.
Criterios cobertos: A2 (kill -9), A5 (pedido passa a frente), A6 (1 x 4 threads); mais universo, estado e saida por memoria."""
from __future__ import annotations

import random
import sqlite3
import time
from pathlib import Path

import ifcopenshell
import pytest
from obim_geometria import construtor, persistente
from obim_geometria.cache_geometria import NOME_BANCO
from s05_conteudo_aux import _limpa, exigir  # noqa: F401  (fixture autouse e guarda)
from test_s06_t23c_construtor_oraculo import _cena

from openbim_app.desenho import filho as F
from openbim_app.desenho.filho import FilhoPersistente

CASA = Path(__file__).parent / "amostras" / "casa-simples.ifc"
N, LOTE = 2000, 32


def esperar(cond, t=120.0):
    fim = time.monotonic() + t
    while time.monotonic() < fim:
        if cond():
            return True
        time.sleep(0.02)
    return False


def estado(fi):
    return fi.executar({"op": "estado_construcao", "arquivo": fi.arquivo}, limite_s=120)


def terminar(fi, t=180.0):
    assert esperar(lambda: estado(fi)["pendentes"] == 0, t), "construcao nao terminou"
    return estado(fi)


def banco(pasta):
    """(formas, ocorrencias, memo) lidos direto do SQLite, sem `gravado_em`; vazio se o banco ainda nao existe."""
    p = Path(pasta) / NOME_BANCO
    if not p.exists():
        return [], [], []
    con = sqlite3.connect(str(p))
    try:
        return (
            con.execute("SELECT chave, dtype_v, vertices, triangulos, checksum FROM formas ORDER BY chave").fetchall(),
            con.execute("SELECT * FROM ocorrencias ORDER BY documento, global_id").fetchall(),
            con.execute("SELECT * FROM memo ORDER BY documento, id_step").fetchall(),
        )
    finally:
        con.close()


def gids_da_fila(arq):
    f = ifcopenshell.open(str(arq))
    return [f.by_id(i).GlobalId for i in construtor.fila_inicial(f)]


def construir(arq, pasta, **kw):
    fi = FilhoPersistente(arq, ocioso_s=3600.0)
    kw.setdefault("lote_max", LOTE)
    kw.setdefault("threads", 1)
    r = fi.construir(pasta, limite_s=120, **kw)
    assert r["aceito"] is True, r
    return fi, r


@pytest.fixture(scope="module")
def sint(tmp_path_factory):
    exigir()
    pos = [((i % 50) * 3.0, (i // 50) * 3.0, 0.0) for i in range(N)]
    f, els = _cena(pos, escalas=[0.5 + 0.02 * (i % 40) for i in range(N)])
    arq = tmp_path_factory.mktemp("t23f") / "sint.ifc"
    f.write(str(arq))
    plano = {
        "op": "desenho", "protocolo": 1, "arquivo": str(arq), "threads": 1,
        "elementos": [[e.id(), e.GlobalId] for e in els[:30]],
        "vista": {"tipo": "PLANTA", "altura_corte_m": 0.3, "origem_pav": [0.0, 0.0, 0.0], "escala": 1.0, "pavimento": f.andar.GlobalId},
    }
    return arq, plano


@pytest.fixture(scope="module")
def base(sint, tmp_path_factory):
    """Construcao completa de referencia (1 thread): banco, fila, estado final e tempo."""
    arq = sint[0]
    pasta = tmp_path_factory.mktemp("base")
    fi, _ = construir(arq, pasta)
    t0 = time.monotonic()
    est = terminar(fi)
    dt = time.monotonic() - t0
    fi.fechar()
    return {"pasta": pasta, "banco": banco(pasta), "gids": gids_da_fila(arq), "est": est, "tempo": dt}


def test_codigo_de_saida_igual_nos_dois_lados():
    assert F.SAIDA_MEMORIA == persistente.SAIDA_MEMORIA == 86


def test_construcao_termina_com_o_universo_e_estado_bate(sint, base):  # caso 4
    formas, ocs, memo = base["banco"]
    gids = base["gids"]
    assert len(gids) == N
    assert [o[1] for o in ocs] == sorted(gids) and len({o[1] for o in ocs}) == N
    est = base["est"]
    assert est["pendentes"] == 0 and est["feitos"] == N and est["falhas"] == 0 and est["parado"] is None and est["erro"] is None
    assert est["tesseladas"] == len(formas) == 40  # 40 tamanhos = 40 formas; o resto reaproveita
    assert est["lotes"] == -(-N // LOTE) and len(memo) == N
    assert {m[3] for m in memo} == {r[0] for r in formas} and {o[2] for o in ocs} == {r[0] for r in formas}
    print(f"\nT23f construcao completa: {base['tempo']:.2f}s, lote_max_s={est['lote_max_s']:.3f}, lotes={est['lotes']}")


def test_casa_simples_termina_e_bate(tmp_path):  # caso 4, arquivo do repo
    fi, _ = construir(CASA, tmp_path)
    try:
        est = terminar(fi, 60)
    finally:
        fi.fechar()
    gids = gids_da_fila(CASA)
    assert gids and est["feitos"] == len(gids) and est["falhas"] == 0 and est["parado"] is None
    formas, ocs, _ = banco(tmp_path)
    assert sorted(o[1] for o in ocs) == sorted(gids) and est["tesseladas"] == len(formas)


def test_determinismo_1_e_4_threads(sint, base, tmp_path):  # A6
    fi, _ = construir(sint[0], tmp_path, threads=4)
    try:
        est = terminar(fi)
    finally:
        fi.fechar()
    assert est["falhas"] == 0
    assert banco(tmp_path) == base["banco"]


def test_kill9_em_instantes_sorteados_perde_no_maximo_um_lote(sint, base, tmp_path):  # A2
    arq, gids, (formas0, ocs0, _m) = sint[0], base["gids"], base["banco"]
    rng = random.Random(2023)
    atrasos = [rng.uniform(0.0, 0.95 * base["tempo"]) for _ in range(10)]
    vistos = set()
    for k, atraso in enumerate(atrasos):
        pasta = tmp_path / f"k{k}"
        fi, _ = construir(arq, pasta)
        time.sleep(atraso)
        fi._proc.kill()  # equivale a kill -9 (SIGKILL no Linux, TerminateProcess no Windows)
        fi._proc.join(10)
        fi.fechar()
        formas, ocs, memo = banco(pasta)
        n = len(ocs)
        vistos.add(n)
        assert n % LOTE == 0 or n == N, f"lote parcial gravado: {n}"
        assert sorted(o[1] for o in ocs) == sorted(gids[:n]), "gravados nao sao um prefixo da fila"
        assert len(memo) == n
        assert {o[2] for o in ocs} <= {r[0] for r in formas}
        c = construtor.abrir_banco(pasta)  # reabre sem recriar: cabecalho igual e banco integro
        try:
            assert c._con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        finally:
            c.fechar()
        assert len(banco(pasta)[1]) == n, "banco recriado ao reabrir"
        fi2, _ = construir(arq, pasta)
        try:
            est = terminar(fi2)
        finally:
            fi2.fechar()
        assert est["tesseladas"] == len(formas0) - len(formas), "retomada tesselou forma que ja estava no banco"
        assert banco(pasta) == base["banco"]
    print(f"\nT23f kill -9: atrasos {[round(a, 2) for a in atrasos]}; gravados no kill: {sorted(vistos)}")


def test_pedido_de_desenho_no_meio_da_construcao_passa_a_frente(sint, tmp_path):  # A5
    arq, plano = sint
    ref = FilhoPersistente(arq, ocioso_s=3600.0)
    try:
        for _ in range(2):
            assert ref.executar(plano, limite_s=120).get("svg")
        t0 = time.monotonic()
        assert ref.executar(plano, limite_s=120).get("svg")
        base_s = time.monotonic() - t0
    finally:
        ref.fechar()
    fi, _ = construir(arq, tmp_path, lote_max=8)
    try:
        assert esperar(lambda: estado(fi)["lotes"] >= 1)
        assert estado(fi)["pendentes"] > 0
        t0 = time.monotonic()
        r = fi.executar(plano, limite_s=120)
        extra = time.monotonic() - t0 - base_s
        assert r.get("ok") and r.get("svg")
        est = estado(fi)
        assert est["pendentes"] > 0, "construcao ja tinha acabado: o teste nao mediu o meio dela"
        lote_s = est["lote_max_s"]
        assert extra <= 3 * (lote_s + 0.2), f"atraso extra {extra:.2f}s; maior lote {lote_s:.3f}s"
        print(f"\nT23f A5: base {base_s:.3f}s, atraso extra {extra:.3f}s, maior lote {lote_s:.3f}s")
        terminar(fi)
    finally:
        fi.fechar()


def test_saida_por_memoria_o_app_segue_desenhando_sem_queda(sint, tmp_path):  # caso 5
    arq, plano = sint
    fi, _ = construir(arq, tmp_path, limite_mb=1.0)  # RSS real do filho passa de 1 MB no primeiro lote
    try:
        assert esperar(lambda: not fi._proc.is_alive(), 120)
        assert fi._proc.exitcode == persistente.SAIDA_MEMORIA
        sig = fi._disco()
        r = fi.executar(plano, limite_s=120)  # caminho de hoje: filho novo, sem construcao
        assert r.get("ok") and r.get("svg")
        assert fi._quedas_seguidas == 0 and fi._sig_bloqueada_construir == sig and not fi._construcao_ativa
        assert estado(fi)["ativo"] is False
        assert fi.construir(tmp_path) == {"aceito": False, "motivo": "memoria"}
    finally:
        fi.fechar()
    assert 0 < len(banco(tmp_path)[1]) < N  # o lote que estourou ficou gravado inteiro
