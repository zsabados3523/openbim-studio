# SPDX-License-Identifier: AGPL-3.0-or-later
"""Testa scripts/license_inventory.py com um conda-meta falso."""
import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "license_inventory.py"
FORGE = "https://conda.anaconda.org/conda-forge/linux-64/"


def _pkg(meta, name, lic, url):
    (meta / f"{name}-1.0-0.json").write_text(json.dumps(
        {"name": name, "version": "1.0", "license": lic, "channel": url.rsplit("/", 1)[0], "url": url}))


def _run(prefix, out):
    env = dict(os.environ, CONDA_PREFIX=str(prefix))
    return subprocess.run([sys.executable, str(SCRIPT), str(out)], env=env, capture_output=True, text=True, encoding="utf-8")


def test_bom_passa(tmp_path):
    meta = tmp_path / "conda-meta"
    meta.mkdir()
    _pkg(meta, "bom", "MIT", FORGE + "bom-1.0-0.conda")
    r = _run(tmp_path, tmp_path / "o.md")
    assert r.returncode == 0
    assert "| bom | 1.0 | MIT | conda-forge |" in (tmp_path / "o.md").read_text(encoding="utf-8")


def test_falha_sem_licenca_e_outro_canal(tmp_path):
    meta = tmp_path / "conda-meta"
    meta.mkdir()
    _pkg(meta, "bom", "MIT", FORGE + "bom-1.0-0.conda")
    _pkg(meta, "semlic", "", FORGE + "semlic-1.0-0.conda")
    _pkg(meta, "defaults", "MIT", "https://repo.anaconda.com/pkgs/main/linux-64/defaults-1.0-0.conda")
    r = _run(tmp_path, tmp_path / "o.md")
    assert r.returncode == 1
    txt = (tmp_path / "o.md").read_text(encoding="utf-8")
    assert "## Não conda-forge (1)" in txt and "defaults 1.0" in txt
    assert "## Sem licença (1)" in txt and "semlic 1.0" in txt
