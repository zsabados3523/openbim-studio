# SPDX-License-Identifier: AGPL-3.0-or-later
"""Aviso visível quando o desenho cai para software, sem placa de vídeo ."""
import os

from test_s04_viewport_b import _caso, guarda, viewport  # noqa: F401


def test_aviso_acompanha_o_desenho_por_software(viewport):  # noqa: F811
    r = _caso("imagem")  # o resultado do caso da imagem (cacheado) traz o estado do desenho
    if r.get("software") is None:
        guarda("OBIM_S04_VIEWPORT_OBRIGATORIO")("obimcore.Cena.aviso() ausente (módulo antigo)")
        return
    software, aviso = r["software"]
    assert isinstance(software, bool)
    assert bool(aviso) == software, f"aviso e estado do desenho discordam: {r['software']!r}"
    # CI: Windows com WARP (QSG_RHI_PREFER_SOFTWARE_RENDERER=1) e Linux com Mesa llvmpipe (LIBGL_ALWAYS_SOFTWARE=1)
    if os.environ.get("QSG_RHI_PREFER_SOFTWARE_RENDERER") == "1" or os.environ.get("LIBGL_ALWAYS_SOFTWARE") == "1":
        assert software is True and "software" in aviso, f"esperado desenho por software, veio {r['software']!r} ({r.get('info')!r})"
