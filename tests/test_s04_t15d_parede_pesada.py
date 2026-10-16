# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo da F0-S04-T15d: elemento pesado durante a edição (LOTE_OPUS_9 §5.2, decisão do PO depois do lote 4) e o relatório da T15 (cartão F0-S04-T15d).
`lote.py <saida.json> --base N --pesada 150 --rodadas R` mede SÓ a parede pesada: a base do gerador mais 1 parede de 60 m com 150 aberturas (o MAB do lote 4);
`malha_ms` = uma chamada de `obimcore.malhas` só dela (com a trava do modelo); depois `mover` dela (dx 0,01 m, alternando o sinal) nas formas 1 e 2 do T15b,
com M5 e M5b iguais aos do T15b. Portão (PROPOSTA DO OPUS, aguarda o PO; o lote 9 §5.2 diz só registrar; o PO pediu depois do lote 4 que a janela não pare
pela peça): com a malha feita FORA do bloqueio (forma 1), mediana (das rodadas) do maior atraso de M5b na forma 1 < metade de `malha_ms`. Reprovado = parar e levar ao PO.
O relatório `docs/state/reports/F0-S04-threads.md` existe e responde cada item do lote 9 §2.3 e §5.2 (títulos conferidos abaixo).
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
from test_s04_t15b_formas import igual, resumo

ESTE = Path(__file__).resolve()
OBRIGATORIO = os.environ.get("OBIM_S04_T15_OBRIGATORIO") == "1"
BASE, ABERTURAS, RODADAS = int(os.environ.get("OBIM_S04_BASE", "300")), 150, 3
RELATORIO = aux.RAIZ / "docs" / "state" / "reports" / "F0-S04-threads.md"
TITULOS = ("## Forma 1", "## Forma 2", "## Forma 3", "## M5b", "## Conferência (i)", "## Conferência (ii)", "## Conferência (iii)",
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
    assert pes["malha_ms"] >= 100, f"a malha da parede pesada levou {pes['malha_ms']:.0f} ms: abaixo de 100 ms o caso não mede nada (aumentar as aberturas e avisar no relatório)"


def test_t15d_rodadas_e_conta_iguais_as_do_t15b(pes):
    assert set(pes["formas"]) == {"1", "2"}
    for forma in (1, 2):
        rs = pes["formas"][str(forma)]
        assert len(rs) == RODADAS
        for i, r in enumerate(rs):
            assert r["forma"] == forma and r["criados"] == 0 and (r["thread_lote"] != r["thread_janela"]) == (forma == 1), r["forma"]
            assert all(r["t0_ms"] <= t <= r["t1_ms"] for t in r["quadros"]) and len(r["mouse"]) >= 1 and all(m[2] is not None and m[2] >= m[0] for m in r["mouse"])
            igual(resumo(r), r["resumo"], f"pesada forma {forma} rodada {i}")


def test_t15d_com_a_malha_fora_do_bloqueio_a_janela_nao_para_pela_peca(pes):
    mx = statistics.median(resumo(r)["M5b"]["max_ms"] for r in pes["formas"]["1"])
    assert mx < 0.5 * pes["malha_ms"], (f"forma 1: a janela ficou {mx:.0f} ms sem tratar o mouse numa malha de {pes['malha_ms']:.0f} ms feita fora do bloqueio: "
                                        "PARAR e levar ao PO (lote 9 §5.2)")


def test_t15d_relatorio_responde_cada_item():
    if not RELATORIO.is_file():
        pular("docs/state/reports/F0-S04-threads.md ausente")
    t = RELATORIO.read_text(encoding="utf-8")
    faltam = [x for x in TITULOS if x not in t]
    assert not faltam, f"o relatório não tem as seções {faltam}"
    assert "SPDX-License-Identifier" in t.splitlines()[0] and len(t.splitlines()) <= 150, "cabeçalho SPDX e no máximo 150 linhas"
    assert "Resumo para o PO" in t and t.count("ms") >= 10, "resumo para o PO e os números em ms"


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
