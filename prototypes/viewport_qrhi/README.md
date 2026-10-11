<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
# Protótipo: viewport 3D com QRhiWidget (S03-T03)

Cubo colorido girando, desenhado em Python puro com `QRhiWidget` (PySide6 6.11.2).

- `viewport.py`: interface `Viewport` (`set_mesh`, `grab_image`).
- `cubo_rhi.py`: todo o desenho de baixo nível (único arquivo que fala com a QRhi).
- `shaders/`: GLSL (`.vert`, `.frag`) e os `.qsb` gerados.

Rodar (precisa de tela):

    cd prototypes && ~/miniforge3/envs/openbim/bin/python -m viewport_qrhi [--api opengl|vulkan]

Refazer os shaders (o `qsb` fica em `~/miniforge3/envs/openbim/lib/qt6/bin/qsb`):

    cd shaders && for s in cubo.vert cubo.frag; do qsb --glsl "100 es,120,150" --hlsl 50 --msl 12 -o $s.qsb $s; done

Teste: `QT_QPA_PLATFORM=xcb pytest tests/test_viewport_qrhi.py` (com tela). Sem tela (offscreen) o teste de desenho é pulado com mensagem.
