<!--
SPDX-License-Identifier: AGPL-3.0-or-later
-->
# LOTE OPUS 16: revisão do PR 71 (ramo s04-t10)
Itens: F0-S04-T10 (seleção por triângulo e memória) e T10b (profundidade do desenho). Revisor opus, só leitura, 2026-10-13. Veredito: **T10 APROVADO com recomendações; T10b APROVADO (nota de processo); nenhum achado bloqueante.** Condição de merge: `linux` e `windows` verdes (o Windows roda o oráculo de profundidade no D3D11, única prova de que ele segue certo).

## Conferido
- Caixas por objeto primeiro, triângulos só dos candidatos, sobre a cópia compacta (selecao.cpp:62-89). 1 milhão de triângulos: mediana 8,1 ms no pior caso (meta 100 ms). Memória: `bytes_copia` (~26–27 B/triângulo) e RSS do oráculo (122–136 B/triângulo).
- Raio calculado direto da câmera (não da matriz), independente de `clipSpaceCorrMatrix`; vale para GL e D3D11. Pixel com y para baixo; ângulo 45°; aspecto do backbuffer real.
- Mutex: câmera (folha) e cena em separado; só `shared_ptr<Dados>` imutáveis sem o GIL; sem inversão.
- Möller–Trumbore com tolerâncias corretas; caixas com parada antecipada corretas (dependem de a caixa conter os triângulos; ver 3).
- ValueError para NaN, infinito, fora da janela e antes do primeiro quadro. Depois de atualizar/limpar/perda de contexto nunca devolve objeto removido.
- T10b: causa = janela GL sem buffer de profundidade; correção 24/8 bits em `Janela::Janela` (viewport.cpp:348-351), dentro de `if (gl)`; D3D11 intocado.
- Calibrações posteriores do oráculo (vão minimo=20, câmera do milhão, orbitar 240) não enfraquecem o critério.

## Achados (recomendações)
1. **Forte, antes da T11/T12.** Escala de tela (viewport.cpp:417, selecao.h:13): x e y são pixels do backbuffer, mas o mouse do Qt chega em pixels lógicos; com 125%/150% no Windows o clique erra. Aceitar coordenadas lógicas e converter por devicePixelRatio, ou documentar e cobrir no oráculo (caso da S03 `test_escala_de_tela_nao_muda_o_resultado` não foi trazido).
2. Câmera e tamanho fora de sincronia com o quadro apresentado (viewport.cpp:251-252, camera.cpp:13): gravar {câmera, w, h} juntos, sob um mutex, depois do `endFrame`.
3. A caixa de cada objeto vem da tabela do Python sem conferência (cena.cpp:106, selecao.cpp:72; `sem()` cena.cpp:42): calcular pelos triângulos do objeto como no selecao.py da S03.
4. Plano de recorte perto (viewport.cpp:262-266): geometria entre a câmera e `perto` some do desenho mas pode ser selecionada; começar o raio em t = perto.
5. A seleção acerta objetos que ainda não chegaram à placa durante a subida (aceito pela especificação): anotar no ADR-004.
6. `bytes_copia` não conta o texto dos GlobalId (~32 B por objeto; relevante com 100 mil objetos).
7. Lacunas do oráculo: (a) escala de tela diferente de 1; (b) deslocamento diferente de zero; (c) lote sem tabela de objetos e objeto sem geometria; (d) raio que cruza muitas caixas em <100 ms; (e) antes do primeiro quadro; (f) após redimensionar; (g) `selecionar` em outra thread durante `atualizar`/`limpar`; (h) caixa menor que a geometria.
8. Processo: T10b sem cartão próprio, registrar no LOG como T3 com a causa. Docstring de tests/test_s04_profundidade.py:3-4 ainda diz "FALHA ESPERADA HOJE" (agente de oráculo corrige). A sonda sonda_desenho.cpp:38 tem o mesmo formato sem profundidade (informativo).
9. Arquivos fora da lista do cartão (viewport.cpp, cena.*, CMake, ci.yml): inevitável, aceito.
10. Pendente para a T12: trocar uma peça reenvia a cena inteira (cena.cpp:150, viewport.cpp:191); medir M2b (<200 ms).

## Para o PO
Clique seleciona a peça certa, ignora vãos e peças escondidas; ~8 ms no modelo de 1 milhão (limite 100). O desenho mostrava peças de trás por cima das da frente: corrigido. Antes da próxima etapa, o clique precisa considerar a escala de tela do Windows.
