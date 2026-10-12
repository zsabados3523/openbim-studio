<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
# Protótipo: viewport 3D com QRhiWidget (S03-T03)

Cubo colorido com câmera orbital (S03-T04), desenhado em Python puro com `QRhiWidget` (PySide6 6.11.2).

- `viewport.py`: interface `Viewport` (`set_mesh`, `grab_image`).
- `cubo_rhi.py`: todo o desenho de baixo nível (único arquivo que fala com a QRhi).
- `camera.py`: classe `Camera` pura (sem Qt), Z para cima, elevação limitada a ±89°.
- `shaders/`: GLSL (`.vert`, `.frag`) e os `.qsb` gerados.

Rodar (precisa de tela):

    cd prototypes && ~/miniforge3/envs/openbim/bin/python -m viewport_qrhi [--api opengl|vulkan]

Refazer os shaders (o `qsb` fica em `~/miniforge3/envs/openbim/lib/qt6/bin/qsb`):

    cd shaders && for s in cubo.vert cubo.frag malha.vert malha.frag; do qsb --glsl "100 es,120,150" --hlsl 50 --msl 12 -o $s.qsb $s; done

Teste: `QT_QPA_PLATFORM=xcb pytest tests/test_viewport_qrhi.py` (com tela). Sem tela (offscreen) o teste de desenho é pulado com mensagem.

Controles do mouse: arrasto com botão esquerdo = orbitar; arrasto com botão do meio ou Shift+esquerdo = mover; roda = aproximar/afastar (distância limitada entre 0,1 e 10000).
Teste da câmera sem tela: `pytest tests/test_viewport_camera.py`.

## Seleção por clique (S03-T06)

`selecao.py` (sem Qt, CPU, numpy): `Malha` (lista de objetos com id), `malha_de_ifc(caminho)`, `raio_da_tela`, `pick_raio`, `pick`. Caixa delimitadora por objeto, ordem pela entrada do raio e parada antecipada; Möller-Trumbore nos triângulos candidatos. No widget: `set_objetos(malha)`, `pick(x, y)` (pixels lógicos; só a razão com o tamanho do widget importa, então vale em tela com escala) e o sinal `clicado(id | None)` (clique esquerdo sem arrasto). Sem `set_objetos`, o cubo padrão é o objeto de id 1.

Medida (modelo de 1 milhão de triângulos, 83 334 objetos, `corpus/modelo-grande-1m.ifc`, uma máquina de desenvolvimento): `pick` mediana 5,6 ms, máximo 14,9 ms (meta: < 100 ms). Carregar a malha do IFC leva cerca de 52 s (feito uma vez; threads são da T05). Teste pesado:

    OBIM_MODELO_GRANDE=corpus/modelo-grande-1m.ifc QT_QPA_PLATFORM=offscreen pytest tests/test_viewport_selecao.py -s
