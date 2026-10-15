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

## Atualização 2026-10-11 (execuções 38148119510 e 38150116542, ramo `lote2-resultado`)
| Meta | Linux | Windows | Situação |
|---|---|---|---|
| Build limpo ≤ 60 min | AppImage: job `appimage` 170 a 182 s (inclui criar o ambiente e montar); testes: 81 s | 939 s a 1207 s (o 1207 s inclui gravar o cache pela 1ª vez) | **Atingida** nos dois |
| Build incremental ≤ 10 min | cache de pacotes ligado: `linux` 81 s (era 66 s sem cache) | 995 s com cache contra 939 s sem: **o cache de pacotes não ajudou** (restaurar leva 89 s; criar o ambiente continua ~186 s) | Medida; **não atingida no Windows** (~16 min por execução) |
| Instalador ≤ 600 MB | AppImage 389 MB (CI) | **309 MB** (CI; eram 482 MB antes de tirar o MKL por licença) | **Atingida** nos dois |
| Instalação ≤ 5 min / primeira abertura ≤ 10 s (ADR-005 teste 7) | | verificado pelo CI (falha se passar); teste todo leva 116 s com duas instalações | Atingida no runner do CI |

**Meta não atingida: build incremental do Windows (~16 min contra 10 min).** Regra da F0: parar e reportar ao PO com opções, sem contornar. O que consome o tempo no Windows não é compilar: é criar o ambiente conda do zero (~3 min), criar o segundo ambiente de runtime (~5 min) e montar o instalador (~1 min). O app esqueleto é só Python. Opções:
1. **Aceitar** nesta fatia e rever quando houver C++ do app (S04): hoje o "incremental" real é um teste de Python, que leva segundos no desenvolvimento local; o tempo do CI é o do ambiente. (Recomendado; **decidido pelo PO em 2026-10-11: opção 1**.)
2. Guardar o **ambiente já criado** em cache (não só os pacotes); economiza ~8 min, mas tem risco de ambiente velho e cache de vários GB.
3. Pular o instalador quando só mudar documentação (CI condicional); não reduz o tempo de uma mudança de código.

## Atualização 2026-10-14/15 (revisão da S02)
O instalador do Windows saiu do job `windows` e roda em job próprio, `instalador-windows`, e só quando o empacotamento muda (PR 91, ok do PO em 2026-10-14; depois PR 95). Efeito: o tempo do CI de um PR comum já não inclui o instalador; os números acima valem para mudanças de empacotamento. A meta original (incremental ≤ 10 min) segue registrada como **não atingida** (D8).

## Cota da S02 (3 linhas)
- Sessões 1 e 2 (preparação, S01, início da S02): janela de 5 h entre 22% e 34%; semana de 2% a 3%.
- Sessão 3 (S02 T07 a T14: CI, instalador, poda): a semana foi a 8%, sem parar por limite; o custo veio das muitas execuções de CI diagnosticadas à mão.
- Lição: instrumentar o CI para publicar o erro (feito) e testar localmente o que for possível antes de empurrar economiza cota.

Run 38653866732 (PR 93, 2026-10-14, lote Opus 30): `windows` 28 min 29 s e `linux` 17 min 27 s. O aumento vem dos passos da S04 (Windows ~15 min, Linux ~10 min). Build incremental (meta original ≤ 10 min) **não atingido também no Linux**. Falta o PO definir o que conta como "build incremental" (cartão `F0-S02-T25`).
