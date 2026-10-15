# Pedido do lote Opus 5: revisão obrigatória da T05 (partes 0, A e B) e amostra de T06 e T25

> Para colar numa sessão **Opus** aberta na pasta do projeto. Preparado em 2026-10-11 pelo líder (sonnet). Antes de abrir: cota semanal restante > 25% (informado em 2026-10-11: ~14% usados). Lote anterior: `docs/state/arquivo/lotes-1-a-28/LOTE_OPUS_4/resultado.md`.

## Cole isto na sessão Opus
Você é o papel Arquiteto/Revisor crítico do OpenBIM Studio (BIM aberto, AGPL v3 ou posterior, Windows e Linux). O PO, Rafael, é arquiteto e não programa: resumos em pt-BR claro, com recomendação. **Regra de execução:** testes gráficos só dentro de `xvfb-run -a -s "-screen 0 1280x1024x24"` com `LIBGL_ALWAYS_SOFTWARE=1`; nunca abra janela na tela real do PO.

**Contexto fechado.** O trabalho está em três PRs empilhados, ainda sem merge. Leia o diff de cada um com `git fetch` e:
- Parte 0 (testes do oráculo): `git diff origin/main...origin/s03-t05-p0` (PR 16)
- Parte A (carregador): `git diff origin/s03-t05-p0...origin/s03-t05-a` (PR 18)
- Parte B (viewport e medição): `git diff origin/s03-t05-a...origin/s03-t05-b` (PR 19)
- Correção de localidade nos testes (já proposta ao `main`): `git show origin/fix-locale` (PR 17)
Leia também: `docs/state/arquivo/lotes-1-a-28/LOTE_OPUS_4/resultado.md` (sua especificação, seção 1 e as perguntas), o cartão `docs/state/arquivo/F0-S03/cartoes/F0-S03-T05.md`, o relatório `docs/state/arquivo/F0-S03/F0-S03-T05.md` (na ramo da Parte B), `docs/state/arquivo/F0-S03/cartoes/F0-S03-T06.md` e T25, `prototypes/viewport_qrhi/selecao.py` (já no `main`). Não use rede. Só crie os arquivos listados.

### Item 1 (obrigatório, T3): revisar as três partes da T05
1. **Parte 0:** os testes transcrevem fielmente o §1.5? Nenhum número afrouxado? Avaliar as escolhas que o implementador fez onde o §1.5 não define (V3 "zeradas", V4 acessa `camera.perto/longe`, O7 "só o resumo sai", R2 medido em iterador separado, parametrizações extras). Dizer o que mudar.
2. **Parte A:** `carregador.py` cumpre §1.2 e §1.3 (posse do arquivo, cancelamento, erros, fila limitada, deslocamento, cor, normais, `sem_malha`, vida dos dados)? Há corrida de threads, vazamento de objeto do IfcOpenShell na fila, ou caso que o oráculo não pega? O R2 às vezes dá `xpass` (≤ 200 ms por pouco): o `xfail` não estrito está certo?
3. **Parte B:** `adicionar_lote` custo proporcional ao lote; sem descarte de faces; perto/longe; envio 1 lote por quadro; reenvio após perda de contexto; adaptador com QTimer. O relatório mede o que o §1.6 pediu? As metas do portão da S03 estão atingidas (abrir 13,5 s; 833 MB; atraso 118 ms; 60 FPS com placa real, medidos na máquina do PO)? Duas dúvidas de política: (a) 1 thread leva 66 s (acima de 60 s; a meta vale com threads padrão): manter assim? (b) bloco 0 reprova de propósito; bloco 1000 tem p95 72,7 ms: registrar só?
4. **Decisão:** para cada parte, aprovado ou reprovado com lista numerada. **Nada entra no `main` sem o seu aprovado e o ok do PO.**

### Item 2: amostra de revisão de T06 (seleção por clique) e T25 (desenho no CI)
T06: o `pick` em CPU com caixas por objeto escala? Há risco com a malha em lotes da T05 (a T06 hoje usa `Malha` própria)? T25: o critério "≥ 3 cores" prova mesmo o desenho? O passo do Windows usou WARP e do Linux Mesa por software: conclusão sustentada? Aprovado ou reprovado.

## Arquivos que você pode criar ou editar
`docs/state/arquivo/lotes-1-a-28/LOTE_OPUS_5/resultado.md` (novo)

## Formato da resposta final no chat
STATUS: SUCESSO | FALHA | PRECISA_PO
TAREFA: Lote Opus 5
RESUMO: ≤ 8 linhas em pt-BR simples
EVIDENCIAS: item 1: parte 0, A, B (aprovado/reprovado e defeitos); item 2: T06 e T25
PERGUNTA_PO: se houver, com recomendação

Depois, o PO volta ao líder com "Leia docs/state e continue".
