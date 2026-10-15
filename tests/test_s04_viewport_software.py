# SPDX-License-Identifier: AGPL-3.0-or-later
"""Aviso visível quando o desenho cai para software, sem placa de vídeo (F0-RG-13, achado B25)."""
import os

import pytest

from test_s04_viewport_b import _caso, viewport  # noqa: F401


def test_aviso_acompanha_o_desenho_por_software(viewport):  # noqa: F811
    r = _caso("imagem")  # o resultado do caso da imagem (cacheado) traz o estado do desenho
    if r.get("software") is None:
        pytest.skip("obimcore.Cena.aviso() ausente (módulo antigo)")
    software, aviso = r["software"]
    assert isinstance(software, bool)
    assert bool(aviso) == software, f"aviso e estado do desenho discordam: {r['software']!r}"
    if os.environ.get("QSG_RHI_PREFER_SOFTWARE_RENDERER") == "1":  # o CI do Windows liga o WARP
        assert software and "software" in aviso
