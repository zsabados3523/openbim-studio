<!--
SPDX-License-Identifier: AGPL-3.0-or-later
-->
# S03-T25: prova de desenho do cubo no CI

Estado (atualização 2026-10-15: o passo existe no `ci.yml` e roda nos dois sistemas, informativo; o texto abaixo é o de 2026-10-12): **passo escrito, ainda não executado no CI** (não pode haver commit/push nesta sessão). O resultado real sai da primeira execução do ramo.

## O que foi feito
- `tests/test_viewport_qrhi.py`: duas variáveis opcionais. `OBIM_EXIGIR_DESENHO=1` transforma "pulou por falta de GPU" em falha; `OBIM_PNG_SAIDA=<pasta>` grava o `cubo.png`; o teste imprime o backend usado. Sem as variáveis, nada muda (os jobs bloqueantes continuam iguais).
- `.github/workflows/ci.yml`: um passo por sistema, ambos `continue-on-error: true` e terminando em `exit 0`. O PNG e os logs vão para `out/desenho/` (artefato do job) e o veredito vira aviso (`::notice`) e linha no resumo.

## Como cada sistema tenta
- **Linux**: `xvfb-run` (tela virtual) + `QT_QPA_PLATFORM=xcb` + `LIBGL_ALWAYS_SOFTWARE=1` (Mesa llvmpipe, OpenGL por software). O runner `ubuntu-latest` costuma trazer Xvfb e Mesa; se faltar, o passo faz `apt-get install` só no runner (não é instalação na sua máquina). Não usei pacote Mesa do conda-forge: não consegui confirmar o nome sem rede.
- **Windows**: `QT_QPA_PLATFORM=windows`, `QSG_RHI_BACKEND=d3d11`; primeiro com `QSG_RHI_PREFER_SOFTWARE_RENDERER=1` (pede o WARP), depois sem. Nada é instalado.

## Evidência local (Linux, máquina do projeto)
`xvfb-run` + `LIBGL_ALWAYS_SOFTWARE=1` + `xcb`, ambiente `openbim`: 2 testes passaram, backend OpenGL, imagem com 3 cores (não uniforme). Isso prova a receita no Linux local, não no runner do GitHub.

## O que NÃO está provado (honesto)
- Linux no runner: depende de Xvfb/Mesa existirem lá e do Qt do conda achar o Mesa do sistema. Provável, não certo.
- Windows: não testado. Incerto se o QRhiWidget respeita `QSG_RHI_PREFER_SOFTWARE_RENDERER` (essa variável é do Qt Quick; para widgets não confirmei na documentação) e se o runner expõe um adaptador D3D11 (WARP costuma estar disponível, mas o Qt no `windows-latest` sem sessão de vídeo pode falhar ao criar a janela). Por isso há a segunda tentativa, sem a variável.
- "Desenha" = PNG com pelo menos 3 cores; não confere que é um cubo.

## Como será validado
Abrir o PR, ler os dois avisos "desenho do cubo no Linux/Windows" e baixar `desenho/cubo.png` dos artefatos. Se o Windows disser NÃO DESENHA, o motivo está no log do passo; então vale o roteiro manual em `docs/acceptance/F0-S03.md` (cubo na VM Windows).
