# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo do script gerar_casa_t09b.py: gera só o IFC, com 2 vistas e 1 prancha, e recusa sobrescrever."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "gerar_casa_t09b.py"


def _roda(pasta):
    return subprocess.run([sys.executable, str(SCRIPT), str(pasta)], cwd=ROOT, capture_output=True, text=True)


def test_script_gera_so_ifc_com_vistas_e_prancha_e_recusa_sobrescrever(tmp_path, monkeypatch):
    monkeypatch.setenv("OBIM_PASTA_LOCAL", str(tmp_path / "local"))
    r = _roda(tmp_path)
    assert r.returncode == 0, r.stderr
    ifc = Path(r.stdout.strip().splitlines()[-1])
    assert ifc == tmp_path / "Casa-T09b.ifc" and ifc.is_file()
    assert not ifc.with_suffix(".obim").exists()

    import openbim_app.autosave as S
    import openbim_app.vistas_ifc as V
    pr = S.abrir_projeto(ifc, lambda t: True, divergencia=True)
    try:
        g = pr.arquivo
        vistas = {v["nome"]: v for v in V.listar_vistas(g)}
        assert sorted(vistas) == ["Corte AA", "Planta Térreo"]
        assert vistas["Planta Térreo"]["tipo"] == "PLANTA" and vistas["Corte AA"]["tipo"] == "CORTE"
        p = V.ler_prancha(g, "A-01")
        assert [V.ler_vista(g, x)["nome"] for x in p["vistas"]] == ["Corte AA", "Planta Térreo"]
    finally:
        pr.autosave.parar()
        pr.diario.fechar()
        pr.historico.encerrar()

    antes = ifc.read_bytes()
    r2 = _roda(tmp_path)
    assert r2.returncode != 0 and ifc.read_bytes() == antes
