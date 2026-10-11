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


def test_licenca_fora_da_lista_reprova(tmp_path):
    meta = tmp_path / "conda-meta"
    meta.mkdir()
    _pkg(meta, "bom", "MIT", FORGE + "bom-1.0-0.conda")
    _pkg(meta, "ruim", "LicenseRef-NVIDIA-End-User-License-Agreement", FORGE + "ruim-1.0-0.conda")
    _pkg(meta, "so-gpl2", "GPL-2.0-only", FORGE + "so-gpl2-1.0-0.conda")
    r = _run(tmp_path, tmp_path / "o.md")
    assert r.returncode == 1
    txt = (tmp_path / "o.md").read_text(encoding="utf-8")
    assert "## Licença fora da lista de permitidas (2)" in txt and "ruim 1.0" in txt and "so-gpl2 1.0" in txt


def test_expressoes_or_and_with(tmp_path):
    meta = tmp_path / "conda-meta"
    meta.mkdir()
    _pkg(meta, "ou", "GPL-2.0-only OR FTL", FORGE + "ou-1.0-0.conda")
    _pkg(meta, "e", "MIT AND BSD-3-Clause", FORGE + "e-1.0-0.conda")
    _pkg(meta, "com", "GPL-3.0-only WITH GCC-exception-3.1", FORGE + "com-1.0-0.conda")
    _pkg(meta, "minus", "LGPL-2.1-only or MPL-1.1", FORGE + "minus-1.0-0.conda")
    r = _run(tmp_path, tmp_path / "o.md")
    # "or MPL-1.1": MPL-1.1 não está na lista e LGPL-2.1-only está, então passa por uma alternativa
    assert r.returncode == 0, (r.stdout, r.stderr)


def test_e_com_item_proibido_reprova(tmp_path):
    meta = tmp_path / "conda-meta"
    meta.mkdir()
    _pkg(meta, "misto", "MIT AND GPL-2.0-only", FORGE + "misto-1.0-0.conda")
    assert _run(tmp_path, tmp_path / "o.md").returncode == 1


def test_removido_nao_conta_e_informativo(tmp_path):
    meta = tmp_path / "conda-meta"
    meta.mkdir()
    _pkg(meta, "ruim", "LicenseRef-NVIDIA-End-User-License-Agreement", FORGE + "ruim-1.0-0.conda")
    lista = tmp_path / "removidos.txt"
    lista.write_text("ruim 1.0 LicenseRef-NVIDIA\n", encoding="utf-8")
    env = dict(os.environ, CONDA_PREFIX=str(tmp_path))
    r = subprocess.run([sys.executable, str(SCRIPT), str(tmp_path / "o.md"), f"--removidos={lista}"], env=env, capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0
    assert "não (removido na montagem)" in (tmp_path / "o.md").read_text(encoding="utf-8")
    r2 = subprocess.run([sys.executable, str(SCRIPT), str(tmp_path / "o2.md"), "--informativo"], env=env, capture_output=True, text=True, encoding="utf-8")
    assert r2.returncode == 0


def test_excecao_amarrada_a_versao(tmp_path):
    meta = tmp_path / "conda-meta"
    meta.mkdir()
    (meta / "tbb-devel-2023.1.0-0.json").write_text(json.dumps(
        {"name": "tbb-devel", "version": "2023.1.0", "license": "", "channel": FORGE, "url": FORGE + "tbb-devel-2023.1.0-0.conda"}))
    assert _run(tmp_path, tmp_path / "o.md").returncode == 0
    (meta / "tbb-devel-2023.1.0-0.json").write_text(json.dumps(
        {"name": "tbb-devel", "version": "2024.0.0", "license": "", "channel": FORGE, "url": FORGE + "tbb-devel-2024.0.0-0.conda"}))
    assert _run(tmp_path, tmp_path / "o.md").returncode == 1
