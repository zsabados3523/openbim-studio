# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo da F0-S04-T15d: elemento pesado durante a edição (LOTE_OPUS_9 §5.2, decisão do PO depois do lote 4) e o relatório da T15 (cartão F0-S04-T15d).
`lote.py <saida.json> --base N --pesada 150 --rodadas R` mede SÓ a parede pesada: a base do gerador mais 1 parede de 60 m com 150 aberturas (o MAB do lote 4);
`malha_ms` = uma chamada de `obimcore.malhas` só dela (com a trava do modelo); depois `mover` dela (dx 0,01 m, alternando o sinal) nas formas 1 e 2 do T15b,
com M5 e M5b iguais aos do T15b (mouse agendado a cada 20 ms desde t0, conferido como no T15b). O `mover` medido refez a malha DA PAREDE PESADA (lote 48):
em cada rodada das duas formas t1 - t0 >= 0,5 x `malha_ms`; na forma 2, mediana da maior fatia entre 0,75 e 2 x `malha_ms`, com a maior operação `obimcore.malhas`.
Portão = regra de parada (b), APROVADA PELO PO em 2026-10-16: a parede com 150 aberturas não pode parar a janela mais da metade do tempo do cálculo do desenho;
com a malha feita FORA do bloqueio (forma 1), mediana (das rodadas) do maior atraso de M5b na forma 1 < metade de `malha_ms`. Reprovado = parar e levar ao PO.
O relatório `docs/state/reports/F0-S04-threads.md` existe e responde cada item do lote 9 §2.3 e §5.2 (cada título conferido como LINHA INTEIRA).
GUARDA: SUBPROCESSO sob `xvfb-run` (nunca na tela real; Windows só no CI ou com OBIM_S04_TELA_VIRTUAL=1); pula sem lote.py com `base_pesada` ou sem obimcore;
com OBIM_S04_T15_OBRIGATORIO=1 todo pulo vira falha."""
import importlib.util
import json
import os
import shutil
import statistics
import sys
import tempfile
import traceback
from pathlib import Path

import pytest
import s04_fluxo_aux as aux
from test_s04_t15b_formas import MOUSE_MS, igual, resumo

ESTE = Path(__file__).resolve()
OBRIGATORIO = os.environ.get("OBIM_S04_T15_OBRIGATORIO") == "1"
BASE, ABERTURAS, RODADAS = int(os.environ.get("OBIM_S04_BASE", "300")), 150, 3
RELATORIO = aux.RAIZ / "docs" / "state" / "reports" / "F0-S04-threads.md"
TITULOS = ("## Resumo para o PO", "## Forma 1", "## Forma 2", "## Forma 3", "## M5b", "## Conferência (i)", "## Conferência (ii)", "## Conferência (iii)",
           "## Parede com 150 aberturas", "## Recomendação para o ADR-004", "## Como reproduzir")


def pular(msg):
    (pytest.fail if OBRIGATORIO else pytest.skip)(f"\n!!! S04-T15d: {msg} (oráculo da parede pesada NÃO FOI EXECUTADO) !!!\n")


def c_pesada(res, base, aberturas, rodadas):
    import lote
    saida = Path(tempfile.mkdtemp()) / "pesada.json"
    res["ret"] = lote.main([str(saida), "--base", str(base), "--pesada", str(aberturas), "--rodadas", str(rodadas)])
    res["arquivo"] = json.loads(saida.read_text(encoding="utf-8"))
    return res


@pytest.fixture(scope="module")
def pes():
    if not (aux.PASTA / "lote.py").is_file() or "def base_pesada" not in (aux.PASTA / "lote.py").read_text(encoding="utf-8"):
        pular("prototypes/s04/fluxo_a/lote.py sem base_pesada")
    if importlib.util.find_spec("obimcore") is None:
        pular("módulo obimcore ausente")
    if not (os.environ.get("CI") or os.environ.get("OBIM_S04_TELA_VIRTUAL") == "1") if sys.platform == "win32" else not shutil.which("xvfb-run"):
        pular("sem tela virtual (xvfb-run; no Windows só no CI ou com OBIM_S04_TELA_VIRTUAL=1): nunca na tela real")
    from test_s04_viewport import caso
    r = caso("pesada", BASE, ABERTURAS, RODADAS, alvo=ESTE, limite=600)
    assert r["ret"] == r["arquivo"]
    a = r["arquivo"]
    assert a["versao"] == 1 and a["base"] == BASE and a["aberturas"] == ABERTURAS and a["rodadas"] == RODADAS and "formas" not in a, sorted(a)
    return a["pesada"]


def test_t15d_a_parede_e_pesada_de_verdade(pes):
    assert len(pes["guid"]) == 22 and pes["triangulos"] >= 600, f"a parede com {ABERTURAS} aberturas tem de vir furada ({pes['triangulos']} triângulos)"
    assert pes["malha_ms"] >= 100, (f"a malha da parede pesada levou {pes['malha_ms']:.0f} ms: abaixo de 100 ms o caso não mede nada "
                                    "(NÃO aumentar as aberturas, 150 é o número do PO: voltar ao líder)")


def test_t15d_rodadas_e_conta_iguais_as_do_t15b_e_o_mover_refez_a_malha_pesada(pes):
    assert set(pes["formas"]) == {"1", "2"}
    for forma in (1, 2):
        rs = pes["formas"][str(forma)]
        assert len(rs) == RODADAS
        for i, r in enumerate(rs):
            assert r["forma"] == forma and r["criados"] == 0 and (r["thread_lote"] != r["thread_janela"]) == (forma == 1), r["forma"]
            m, t0, t1 = r["mouse"], r["t0_ms"], r["t1_ms"]
            assert all(t0 <= t <= t1 for t in r["quadros"]), f"forma {forma} rodada {i}: quadro fora de [t0, t1]"
            assert len(m) == int((t1 - t0) // MOUSE_MS) + 1, f"forma {forma} rodada {i}: {len(m)} eventos de mouse para {t1 - t0:.0f} ms (um a cada 20 ms até t1)"
            for k, (ag, post, trat) in enumerate(m):  # a mesma conferência do T15b: o atraso conta do AGENDADO
                assert abs(ag - (t0 + k * MOUSE_MS)) <= 1e-6 and trat is not None and post >= ag - 1e-6 and trat >= post, f"forma {forma} rodada {i}: evento {k} {m[k]}"
            igual(resumo(r), r["resumo"], f"pesada forma {forma} rodada {i}")
            # o `mover` medido refez a malha da parede pesada (lote 48; referência Linux: t1 - t0 = 1,04 a 1,18 x `malha_ms`; parede leve: 0,03 a 0,10)
            assert t1 - t0 >= 0.5 * pes["malha_ms"], (f"forma {forma} rodada {i}: a edição levou {t1 - t0:.0f} ms, menos da metade da malha da parede pesada "
                                                      f"({pes['malha_ms']:.0f} ms): o `mover` medido não refez a malha dela")
    # forma 2: a maior fatia é a malha da parede pesada, medida por outro caminho (referência Linux: 0,91 a 1,03 x `malha_ms`). O piso de 0,75 impede inflar
    # `malha_ms` (o portão é 0,5 x `malha_ms`, inflar afrouxa); o teto de 2 só barra `malha_ms` medido baixo demais (o que só endurece o portão).
    assert all("fatias" in r for r in pes["formas"]["2"]), "forma 2 sem `fatias`"
    fz = [resumo(r)["fatias"] for r in pes["formas"]["2"]]
    med = statistics.median(x["maior_ms"] for x in fz)
    assert all(x["maior_op"] == "obimcore.malhas" for x in fz) and 0.75 * pes["malha_ms"] <= med <= 2 * pes["malha_ms"], (
        f"forma 2: maior fatia (mediana) {med:.0f} ms com {[x['maior_op'] for x in fz]}, contra `malha_ms` {pes['malha_ms']:.0f} ms (exige `obimcore.malhas` "
        "e 0,75 a 2 vezes `malha_ms`): o `mover` medido não refez a malha da parede pesada, ou `malha_ms` não mede essa malha")


def test_t15d_com_a_malha_fora_do_bloqueio_a_janela_nao_para_pela_peca(pes):
    mx = statistics.median(resumo(r)["M5b"]["max_ms"] for r in pes["formas"]["1"])
    assert mx < 0.5 * pes["malha_ms"], (f"forma 1: a janela ficou {mx:.0f} ms sem tratar o mouse numa malha de {pes['malha_ms']:.0f} ms feita fora do bloqueio: "
                                        "PARAR e levar ao PO (regra de parada (b), aprovada pelo PO em 2026-10-16)")


def test_t15d_relatorio_responde_cada_item():
    if not RELATORIO.is_file():
        pular("docs/state/reports/F0-S04-threads.md ausente")
    t = RELATORIO.read_text(encoding="utf-8")
    linhas = {x.rstrip() for x in t.splitlines()}
    faltam = [x for x in TITULOS if x not in linhas]
    assert not faltam, f"o relatório não tem as seções {faltam}"
    assert "SPDX-License-Identifier" in t.splitlines()[0] and len(t.splitlines()) <= 150, "cabeçalho SPDX e no máximo 150 linhas"
    assert t.count("ms") >= 10, "os números em ms"


if __name__ == "__main__":
    import faulthandler
    faulthandler.dump_traceback_later(int(os.environ.get("OBIM_LIMITE", 600)) - 20, exit=True)
    import ifcopenshell  # noqa: F401  (antes do obimcore)
    try:
        saida = globals()["c_" + sys.argv[1]]({}, *sys.argv[2:])
    except BaseException:
        saida = {"erro": traceback.format_exc()}
    print("RESULTADO " + json.dumps(saida, ensure_ascii=False), flush=True)
    os._exit(0)
