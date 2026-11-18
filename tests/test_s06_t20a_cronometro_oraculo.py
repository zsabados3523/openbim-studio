# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oraculo leve F0-S06-T20a (T1): cronometro de RELOGIO da planta por componentes + sonda leve. Cartao: docs/state/cards/F0-S06/F0-S06-T20a-cronometro-e-sonda.md.
Contrato: `resp["tempos"]` ganha `pesados_s, formas_s, agrupar_s, max_lote_s, refaz_faixas_s` (float >= 0), `n_timeouts, n_grupos, maior_grupo` (int >= 0);
chaves antigas ficam. Cena: 4 caixas, A e B isoladas, C e C2 encostadas => 3 grupos, maior com 2 pecas. Lote morto com erro `Tempo` => n_timeouts >= 1 e refaz_faixas_s > 0.
Sonda: `python prototypes/s06/sonda_planta_leve.py ARQ.ifc PAV` (PAV = GlobalId do pavimento) imprime linhas com 'grupos', 'maior_grupo', 'inel_boxes', 'triangulos por classe'."""
from __future__ import annotations

import copy
import pathlib
import subprocess
import sys
import time

import pytest

import obim_geometria.desenho as D
from test_s06_t19i1_nunca_descartar_oraculo import Fake, _cena3

NOVAS_S = ("pesados_s", "formas_s", "agrupar_s", "max_lote_s", "refaz_faixas_s")
NOVAS_N = ("n_timeouts", "n_grupos", "maior_grupo")
ANTIGAS = ("geo_s", "write_s", "finalize_s", "abrir_s")
RAIZ = pathlib.Path(__file__).resolve().parents[1]


def _roda(ped):
    t0 = time.perf_counter()
    r = D.processar(copy.deepcopy(ped))
    return r, time.perf_counter() - t0


def test_a_tempos_de_relogio_presentes_e_coerentes(monkeypatch, tmp_path):
    ped, ids, ruins = _cena3(tmp_path)
    Fake(monkeypatch, ruins, None)
    r, total = _roda(ped)
    t = r["tempos"]
    assert r["ok"]
    for k in NOVAS_S:
        assert isinstance(t[k], float) and t[k] >= 0.0, k
    for k in NOVAS_N:
        assert isinstance(t[k], int) and not isinstance(t[k], bool) and t[k] >= 0, k
    assert t["n_grupos"] == 3 and t["maior_grupo"] == 2 and t["n_timeouts"] == 0 and t["refaz_faixas_s"] == 0.0
    assert t["max_lote_s"] > 0.0 and t["max_lote_s"] <= total + 1e-6
    assert sum(t[k] for k in NOVAS_S) <= total + 1e-6, "soma das fases de relogio passa do total (soma de filhos em vez de relogio?)"
    for k in ANTIGAS:
        assert isinstance(t[k], float) and t[k] >= 0.0, k


def test_b_lote_estourado_conta_timeout_e_tempo_de_refazer(monkeypatch, tmp_path):
    ped, ids, ruins = _cena3(tmp_path)
    fk = Fake(monkeypatch, ruins, "lote_morto")  # devolve erro de tipo "Tempo" no lote do grupo ruim; o refazer roda por faixas
    r, total = _roda(ped)
    t = r["tempos"]
    assert r["ok"] and fk.avulsos
    assert t["n_timeouts"] >= 1 and isinstance(t["n_timeouts"], int)
    assert t["refaz_faixas_s"] > 0.0
    assert sum(t[k] for k in NOVAS_S) <= total + 1e-6
    assert t["max_lote_s"] <= total + 1e-6


def test_c_sonda_leve_roda_no_ifc_sintetico(monkeypatch, tmp_path):
    ped, ids, ruins = _cena3(tmp_path)
    arq, pav = ped["arquivo"], ped["vista"]["pavimento"]
    if not pathlib.Path(arq).exists():
        pytest.skip("IFC sintetico nao gerado")
    script = RAIZ / "prototypes" / "s06" / "sonda_planta_leve.py"
    assert script.exists(), "prototypes/s06/sonda_planta_leve.py nao existe"
    p = subprocess.run([sys.executable, str(script), arq, pav], capture_output=True, text=True, timeout=110, cwd=str(RAIZ))
    assert p.returncode == 0, p.stderr[-600:]
    for chave in ("grupos", "maior_grupo", "inel_boxes", "triangulos por classe"):
        assert chave in p.stdout, f"saida sem '{chave}':\n{p.stdout[-600:]}"
