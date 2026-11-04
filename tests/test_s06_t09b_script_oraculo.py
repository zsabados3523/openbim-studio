# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo do script gerar_casa_t09b.py: gera SÓ o IFC4 (pasta de saída com exatamente Casa-T09b.ifc), com paredes, 2 vistas e 1 prancha,
abre como D4 e recusa sobrescrever. O teste de CLI (sem argumento / destino que é arquivo) é do implementador: AINDA_NAO_T09B (xfail estrito).
GUARDA (pula, nunca afrouxa): sem ifcopenshell, pula; com OBIM_S05_OBRIGATORIO=1 vira falha."""
import os
import subprocess
import sys
from pathlib import Path

import pytest

if not os.environ.get("OBIM_S05_OBRIGATORIO"):
    pytest.importorskip("ifcopenshell")
import s05_conteudo_aux as R  # noqa: E402
from s05_conteudo_aux import _limpa  # noqa: E402,F401  (fixture autouse)

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "gerar_casa_t09b.py"


def _roda(*args):
    return subprocess.run([sys.executable, str(SCRIPT), *map(str, args)], cwd=ROOT, capture_output=True, text=True)


def test_script_gera_so_ifc_com_vistas_e_prancha_e_recusa_sobrescrever(tmp_path, monkeypatch):
    R.exigir()
    monkeypatch.setenv("OBIM_PASTA_LOCAL", str(tmp_path / "local"))
    saida = tmp_path / "saida"
    r = _roda(saida)
    assert r.returncode == 0, r.stderr
    ifc = Path(r.stdout.strip().splitlines()[-1])
    assert ifc == saida / "Casa-T09b.ifc" and ifc.is_file()
    assert [f.name for f in saida.iterdir()] == ["Casa-T09b.ifc"], "só o .ifc na pasta de saída (sem .obim, .tmp, gravacao.json, subpasta)"

    import openbim_app.autosave as S
    import openbim_app.vistas_ifc as V
    pr = S.abrir_projeto(ifc, lambda t: True, divergencia=True)
    try:
        g = pr.arquivo
        assert g.schema == "IFC4" and len(g.by_type("IfcWall")) >= 1
        assert pr.divergencia.caso == "D4" and pr.divergencia.vistas_preservadas == 2
        vistas = {v["nome"]: v for v in V.listar_vistas(g)}
        assert sorted(vistas) == ["Corte AA", "Planta Térreo"]
        assert vistas["Planta Térreo"]["tipo"] == "PLANTA" and vistas["Corte AA"]["tipo"] == "CORTE"
        p = V.ler_prancha(g, "A-01")
        assert p["titulo"] == "Plantas e cortes" and [V.ler_vista(g, x)["nome"] for x in p["vistas"]] == ["Corte AA", "Planta Térreo"]
    finally:
        pr.autosave.parar()
        pr.diario.fechar()
        pr.historico.encerrar()

    antes = ifc.read_bytes()
    r2 = _roda(saida)
    assert r2.returncode != 0 and ifc.read_bytes() == antes


def _uso_limpo(r):
    return r.returncode != 0 and "Traceback" not in r.stderr and "uso" in (r.stderr + r.stdout).lower()


@pytest.mark.xfail(strict=True, reason="AINDA_NAO_T09B: CLI sem argumento levanta IndexError cru")
def test_cli_sem_argumento_mostra_uso_em_portugues_sem_traceback():
    assert _uso_limpo(_roda())


@pytest.mark.xfail(strict=True, reason="AINDA_NAO_T09B: destino que é arquivo regular levanta FileExistsError cru")
def test_cli_destino_que_e_arquivo_mostra_erro_limpo_sem_traceback(tmp_path):
    arq = tmp_path / "arquivo.txt"
    arq.write_text("x")
    r = _roda(arq)
    assert r.returncode != 0 and "Traceback" not in r.stderr and r.stderr.strip() and arq.read_text() == "x"
