# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oraculo F0-S06-T25b (rodada 2, parte b): item 6 da REVISAO.md.
- (6) GerenteDesenho.pedir passa caminho ja resolvido em opcoes["caminho_ifc"], imune a mudanca de CWD.
Os apoios (cena sintetica, espiao de cache) vem do arquivo da parte a."""
from __future__ import annotations

import os
from pathlib import Path

from test_s06_t25b_chave_arquivo_oraculo2 import _CacheEspiao, _criar_ifc_sintetico, _espiar_grafo, _pedir_gerente, app  # noqa: F401
from openbim_app.desenho import gerente as G


def test_item6_gerente_passa_caminho_ja_resolvido_imune_a_chdir(app, tmp_path, monkeypatch):
    """(6) GerenteDesenho.pedir grava caminho ja resolvido em opcoes['caminho_ifc'], imune a mudanca de CWD."""
    dir_a, dir_b = tmp_path / "dir_a", tmp_path / "dir_b"
    dir_a.mkdir()
    dir_b.mkdir()
    arq = dir_a / "modelo.ifc"
    f, _ped, meta = _criar_ifc_sintetico(arq, n_paredes=2, props=1, com_vistas=True)
    link = dir_a / "atalho.ifc"
    link.symlink_to(arq)

    monkeypatch.chdir(dir_a)
    cont, esp = _espiar_grafo(monkeypatch), _CacheEspiao(tmp_path / "cg")
    opcoes_vistas, chamadas = {}, []

    def chave_estado(_tipo, _ifc, _guid, opcoes):
        opcoes_vistas.update(opcoes)
        os.chdir(dir_b)  # CWD muda antes da thread de fundo chamar gerar_planta
        return "chave-item6"

    exec_p = lambda q: (chamadas.append(dict(q)), {"ok": True, "svg": "<svg/>", "n_paths": 1, "tempos": {}, "caixas": [], "em_cache": [], "pesados": []})[1]
    g = G.GerenteDesenho(cache=esp, chave_estado=chave_estado, filho_persistente=False)
    try:
        _pedir_gerente(app, g, "planta", f, meta["gid_planta"], caminho_ifc=Path("atalho.ifc"), revisao=1, revisao_salva=1, executor=exec_p)
    finally:
        g.fechar()

    esperado = arq.resolve()
    assert "caminho_ifc" in opcoes_vistas
    assert Path(opcoes_vistas["caminho_ifc"]).is_absolute() and Path(opcoes_vistas["caminho_ifc"]) == esperado
    assert esp.arquivos == [esperado] and cont["ser"] == 0 and cont["elem"] == 0
    assert len(chamadas) == 1 and Path(chamadas[0]["arquivo"]) == esperado
