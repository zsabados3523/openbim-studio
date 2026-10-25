# SPDX-License-Identifier: AGPL-3.0-or-later
"""Testes da medida `pos_emitir_mb` e do critério novo do ensaio.

Escrito só das exigências, sem consultar o código da implementação.
1. Canal: com o filho em blocos, cada `bloco` do 2º em diante e o `fim` trazem `pos_emitir_mb`, medida depois de todos os `lote` do
   bloco anterior (ordem: `bloco_fim` -> `lote`... -> `bloco` com o campo). Provado em processo, com a medida de memória trocada por um
   contador (cada leitura recebe um número único; assim a ordem das leituras aparece sem depender da memória real).
2. Registro do pai: `est["blocos"]` traz o valor e as decisões do vigia não mudam (mesmos números do teste de reinício com
   OBIM_TESTE_CRESCER_MB).
3. `calcular_parada` da sonda: (d') 50 passa e 50,1 para; (e) 999 passa e 1.000 para; leitura de 6.000 para; (d) antigo só informa.
4. Windows usa a mesma função (WorkingSetSize); macOS pula a parte de memória real.
"""
import inspect
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "viewport"))
sys.path.insert(0, str(RAIZ / "tools" / "s04" / "sondas"))
sys.path.insert(0, str(RAIZ / "tests"))

from viewport_qrhi import processo_malhas  # noqa: E402
import sonda_ensaio_t33 as sonda  # noqa: E402
from test_s04_t29b_reinicio_oraculo import (  # noqa: E402,F401  (modelo sintético de 12 paredes e ajudantes do teste de reinício)
    BLOCO, CRESCER_MB, LENTA_S, _guid, _lenta, _rodar, modelo)

NAO_MAC = pytest.mark.skipif(sys.platform == "darwin", reason="macOS: a medida de memória é experimental; pula como hoje")


# ---------- 1. canal: ordem e conteúdo, com a memória trocada por um contador ----------
def _params(m, **kw):
    return {"caminho": m.caminho, "threads": 1, "tamanho_bloco": BLOCO, "excluir": ("IfcFeatureElementSubtraction", "IfcSpace"),
            "biblioteca": "hybrid-cgal-simple-opencascade", "max_bytes_lote": 600, "ids": None, "isolado": False, "desl": None,
            "por_peca": False, "foto": None, **kw}


def _canal(m, monkeypatch):
    """Roda o filho em processo. Devolve os eventos na ordem: ('leitura', n, atual) a cada medida de memória e ('msg', tipo, dados)."""
    eventos, contador = [], iter(range(1, 10_000))

    def pico(ident=None, atual=False):
        n = float(next(contador))
        eventos.append(("leitura", n, atual))
        return n

    monkeypatch.setattr(processo_malhas, "pico_memoria_mb", pico)
    processo_malhas._converter(lambda tipo, dados=None: eventos.append(("msg", tipo, dados)), _params(m))
    return eventos


def test_pos_emitir_vai_no_bloco_seguinte_medida_depois_dos_lotes(modelo, monkeypatch):
    ev = _canal(modelo, monkeypatch)
    blocos = [e for e in ev if e[:2] == ("msg", "bloco")]
    assert len(blocos) == 4, "12 peças em blocos de 3: 4 blocos"
    assert blocos[0][2].get("pos_emitir_mb") is None, "o 1º bloco do filho não tem bloco anterior"
    for n in range(1, 4):
        i_bloco = next(i for i, e in enumerate(ev) if e is blocos[n])
        i_fim_ant = max(i for i, e in enumerate(ev[:i_bloco]) if e[:2] == ("msg", "bloco_fim"))
        lotes = [i for i in range(i_fim_ant, i_bloco) if ev[i][:2] == ("msg", "lote")]
        assert lotes, f"o bloco {n} tem de ter emitido lotes entre bloco_fim e o próximo bloco"
        depois = [e for e in ev[lotes[-1]:i_bloco] if e[0] == "leitura"]
        assert depois, "falta a medida depois do último lote"
        v = blocos[n][2]["pos_emitir_mb"]
        assert v == depois[0][1], f"bloco {n + 1}: pos_emitir_mb não é a 1ª leitura depois do último lote do bloco {n}"
        assert depois[0][2] is True, "tem de ser a memória de agora (atual=True), não o pico"
        assert v < blocos[n][2]["rss_mb"], "a medida do bloco anterior vem antes da base do bloco novo"


def test_fim_traz_pos_emitir_do_ultimo_bloco(modelo, monkeypatch):
    ev = _canal(modelo, monkeypatch)
    i_fim = next(i for i, e in enumerate(ev) if e[:2] == ("msg", "fim"))
    ultimo_lote = max(i for i, e in enumerate(ev[:i_fim]) if e[:2] == ("msg", "lote"))
    primeira = next(e for e in ev[ultimo_lote:i_fim] if e[0] == "leitura")
    assert ev[i_fim][2].get("pos_emitir_mb") == primeira[1] and primeira[2] is True


def test_nenhum_tipo_novo_de_mensagem(modelo, monkeypatch):
    tipos = {e[1] for e in _canal(modelo, monkeypatch) if e[0] == "msg"}
    assert tipos <= {"fase", "bloco", "bloco_fim", "inicio", "lote", "feitos", "atual", "sem_malha", "erro", "fim", "nota"}, tipos


# ---------- 2. registro do pai e decisões do vigia ----------
@NAO_MAC
def test_registro_do_pai_traz_o_valor_em_execucao_normal(modelo, monkeypatch):
    lotes, r, esp = _rodar(modelo, monkeypatch)
    assert r.estado == "concluido" and len(esp.conversao) == 1 and r.reinicios == []
    assert [b["bloco"] for b in r.blocos] == [1, 2, 3, 4]
    for b in r.blocos:  # o registro do bloco N guarda a medida feita depois de `emitir` do bloco N (chega no bloco N+1 ou no `fim`)
        assert b["pos_emitir_mb"] is not None and b["pos_emitir_mb"] > 0, b


@NAO_MAC
def test_decisoes_do_vigia_nao_mudam_com_a_medida_nova(modelo, monkeypatch):
    """Mesmo caso do teste de reinício (`test_crescer_em_bloco_que_nao_e_o_primeiro...`): reinicia uma vez, no bloco 2, pela vigia."""
    g = _guid(modelo, BLOCO)
    env = _lenta(modelo, 2 * BLOCO - 1, {"OBIM_TESTE_CRESCER_MB": f"{g}={CRESCER_MB}"})
    lotes, r, esp = _rodar(modelo, monkeypatch, env=env)
    assert r.estado == "concluido" and not r.sem_malha
    assert len(esp.conversao) == 2 and r.reinicios == [2] and esp.dois_vivos == 0
    assert esp.conversao[1].params["ids"] == modelo.ids[BLOCO:]
    assert r.tempos["perdido_s"] < LENTA_S, "a vigia decidiu no meio do bloco, como antes"
    reg = r.registro_reinicio
    assert len(reg) == 1 and reg[0]["bloco"] == 2 and reg[0]["fonte"] == "vigia" and not reg[0]["decisao_tarde"]
    assert reg[0]["decisao_mb"] - reg[0]["base_mb"] >= 1000, "decidiu ao passar de G = 1.000 MB"
    assert not any(b["tarde"] for b in r.blocos)
    por_filho = {}
    for b in r.blocos:
        por_filho.setdefault(b["filho"], []).append(b)
    assert len(por_filho) == 2
    velho, novo = por_filho[1], por_filho[2]  # registro do bloco N = medida depois de `emitir` do bloco N (a sonda pareia N com N+1)
    assert all(b["pos_emitir_mb"] is not None for b in velho[:-1]), "blocos completos do filho morto"
    assert velho[-1]["pos_emitir_mb"] is None, "o bloco em que o filho morreu nunca chegou a emitir"
    assert all(b["pos_emitir_mb"] is not None for b in novo), "o filho novo vai até o `fim`, que traz a medida do último bloco"


# ---------- 3. calcular_parada: casos de borda ----------
def _b(n, f=1, base=1000, mx=1100, **kw):
    return {"bloco": n, "filho": f, "base_mb": base, "max_mb": mx, "fim_mb": mx, "atraso_armar_s": 0.1, "max_silencio_s": 1.0,
            "primeira_mb": base, "tarde": False, "pos_emitir_mb": base, **kw}


def _campo(blocos, nome):
    return sonda.calcular_parada({"blocos": blocos})[nome]


@pytest.mark.parametrize("dif,ok", [(50, True), (50.1, False), (-50, True), (-50.1, False), (0, True)])
def test_d_linha_base_contra_pos_emitir(dif, ok):
    """(d') |base(N+1) - pos_emitir(N)| <= 50 MB."""
    assert _campo([_b(1, pos_emitir_mb=1000), _b(2, base=1000 + dif)], "base_vs_pos_emitir_ok") is ok


@pytest.mark.parametrize("pos,ok", [(1999, True), (1999.9, True), (2000, False), (2500, False)])
def test_e_sobra_do_emitir_menor_que_g(pos, ok):
    """(e) pos_emitir(N) - fim(N) < G = 1.000 MB."""
    assert _campo([_b(1, mx=1000, fim_mb=1000, pos_emitir_mb=pos)], "pos_emitir_vs_fim_ok") is ok


@pytest.mark.parametrize("campo", ["fim_mb", "max_mb", "base_mb", "pos_emitir_mb"])
def test_e_toda_leitura_abaixo_de_6000(campo):
    bom = _b(1, base=5999, mx=5999, fim_mb=5999, pos_emitir_mb=5999)
    assert _campo([bom], "pos_emitir_vs_fim_ok") is True
    assert _campo([{**bom, campo: 6000}], "pos_emitir_vs_fim_ok") is False


def test_sem_pos_emitir_sem_julgamento():
    assert _campo([_b(1, pos_emitir_mb=None), _b(2, pos_emitir_mb=None)], "base_vs_pos_emitir_ok") is None
    assert _campo([_b(1, pos_emitir_mb=None)], "pos_emitir_vs_fim_ok") is None


def test_d_antigo_so_informa_e_nao_para():
    ruim = [_b(1, mx=1100, fim_mb=1100, pos_emitir_mb=1000), _b(2, base=1000)]  # fim 1100 contra base 1000: o (d) antigo falha
    p = sonda.calcular_parada({"blocos": ruim})
    assert p["base_vs_fim_ok"] is False and p["base_vs_pos_emitir_ok"] is True
    assert "base_vs_fim_ok" not in sonda.PARADAS and "base_vs_fim_ok" in sonda.INFORMATIVAS
    assert {"base_vs_pos_emitir_ok", "pos_emitir_vs_fim_ok"} <= set(sonda.PARADAS)


def test_numeros_do_produto_nao_mudam():
    assert (sonda.G_MB, sonda.TETO_MB, sonda.LIM_BASE_MB, sonda.BLOCO_ALVO) == (1000.0, 6000.0, 50.0, 22)


def test_auto_teste_da_sonda_passa():
    sonda.auto_teste()


# ---------- 4. plataformas ----------
def test_a_medida_do_filho_usa_a_funcao_unica_de_memoria():
    """Windows e Linux: o filho usa `pico_memoria_mb(atual=True)` (WorkingSetSize / VmRSS); não há função paralela."""
    src = inspect.getsource(processo_malhas)
    assert src.count("def pico_memoria_mb") == 1 and "WorkingSetSize" in inspect.getsource(processo_malhas.pico_memoria_mb)
    assert "pos_emitir" in src


@pytest.mark.skipif(sys.platform != "win32", reason="WorkingSetSize só existe no Windows")
def test_windows_medida_atual_positiva():
    v = processo_malhas.pico_memoria_mb(atual=True)
    assert isinstance(v, float) and v > 1
