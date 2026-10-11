<!--
SPDX-License-Identifier: AGPL-3.0-or-later
-->
# Relatório T13: metas da S02 contra o que o CI mediu

Fonte: execução do CI [38110728020](https://github.com/zsabados3523/openbim-studio/actions/runs/38110728020) (verde nos três sistemas; a anterior sem cache também). Ambiente criado do zero a cada execução (o CI não usa cache).

| Meta | Linux | Windows | Situação |
|---|---|---|---|
| Build limpo ≤ 60 min | 66 s (testes, inventário, REUSE; **sem** AppImage no CI) | 939 s ≈ 15,7 min (ambiente 188 s; ambiente de runtime + instalador 655 s; teste do instalador 67 s) | Windows atingida. Linux: ver pendência 1 |
| Build incremental ≤ 10 min | **não medido** | **não medido** | Pendência 2 |
| Instalador ≤ 600 MB | AppImage 390 MB (montado na máquina do líder, não no CI) | 482 MB (pacote do CI) | Atingida nos dois, com a ressalva da pendência 1 |

macOS (melhor esforço, não bloqueia): 93 s, verde.

## Pendências que impedem declarar a T13 completa
1. **O AppImage ainda não é gerado no CI** (critério 1 da T10 pede "a cada merge"). Hoje ele foi montado e testado só na máquina do líder. Para gerar no CI é preciso baixar o `appimagetool` (MIT, versão fixa 1.9.1, conferida por sha256) dentro do CI. Pede ok do PO.
2. **Build incremental não medido:** o CI não guarda cache, então toda execução é "limpa". O app esqueleto é só Python (não há compilação); o único trecho compilado é a sonda C++, que levou 2,4 s limpa e 0,9 s incremental no Linux (relatório F0-S02-sonda). Sem cache de pacotes o Windows leva ~16 min por execução, acima dos 10 min da meta incremental. Opções: (a) ligar cache de pacotes e medir (recomendado); (b) aceitar a medição da sonda C++ como a de "incremental" nesta fatia e medir de verdade na S04, quando houver código C++ do app.

## Cota da S02 (3 linhas)
- Sessões 1 e 2 (preparação, S01, início da S02): janela de 5 h entre 22% e 34%; semana de 2% a 3%.
- Sessão 3 (S02 T07 a T14: CI, instalador, poda): a semana foi a 8%, sem parar por limite; o custo veio das muitas execuções de CI diagnosticadas à mão.
- Lição: instrumentar o CI para publicar o erro (feito) e testar localmente o que for possível antes de empurrar economiza cota.
