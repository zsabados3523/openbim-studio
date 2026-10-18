<!--
SPDX-License-Identifier: AGPL-3.0-or-later
-->
# Mapa do projeto (versão simples)

Para o Rafael. Escrito em 2026-10-15 e atualizado em 2026-10-18 a partir do que está no GitHub (`main`). Se este mapa e o resto divergirem, avise.

## 1. O que estamos construindo
Um programa aberto de modelagem BIM para arquitetos, no Windows e no Linux. O arquivo do modelo é um IFC limpo. Primeiro pacote regional: Brasil, com projeto legal e executivo residencial.

## 2. O caminho em 7 fases
Cada fase termina num **portão**: você testa e decide se passa.

| Fase | Resultado para você |
|---|---|
| **F0** | Provas de que a ideia funciona. **Ainda não existe programa.** |
| F1 | Abrir um IFC, navegar em 3D, ver propriedades e medir |
| F2 | Desenhar uma casa: paredes, portas, janelas, pisos |
| F3 | Plantas, cortes, cotas e pranchas (a "Planta Legal") |
| F4 | Telhado, escada, terreno, bibliotecas |
| F5 | Documentação executiva (fachadas, DXF, tabelas) |
| F6 | Polimento e versão 1.0 |

Prazo estimado de 21 a 42 meses. **Ainda não foi recalculado**. Isso só acontece depois da F0.

## 3. A Fase 0, etapa por etapa
Pense numa obra: antes de levantar a casa, provamos que o terreno e as fundações aguentam.

| Etapa | O que prova (em linguagem de obra) | Situação |
|---|---|---|
| S01 | Podemos usar as peças abertas sem problema de licença | **Feita**, você aceitou |
| S02 | A esteira de testes automáticos funciona no Windows e no Linux, e há um programa esqueleto | **Feita**, você aceitou |
| S03 | Dá para mostrar um modelo 3D na tela com velocidade boa | **Feita**, você aprovou |
| **S04** | **Python e C++ conversam bem?** Python é fácil de mexer. C++ é mais rápido. Testamos a mistura contra C++ sozinho. Essa prova decide a arquitetura | **Em andamento, esperando você.** Medição oficial feita; 3 metas não atingidas; decisões abaixo |
| S05 | Desfazer, refazer e gravar sem perder dados | Não começou |
| S06 | Gerar planta e corte automaticamente | Não começou |
| S07 | Criar uma porta ou janela por script | Não começou |
| S08 | Reunir modelos de teste | Contínua |
| S09 | Desenhos de tela, feitos com você | Entrevista feita e aceita por você (15/10, com um ajuste). Faltam os desenhos de tela: você manda as imagens |
| S10 | **Portão da F0:** juntar os números e decidir "seguimos" ou "mudamos o plano" | Não começou |

### Dentro da S04
**Pronto:** a ponte básica, a janela 3D, câmera, clique, comandos em Python (fluxo A), as paredes em C++ (fluxo B, agora com janela), a abertura de arquivos grandes e o estudo das threads. A ponte em C++ (`obimcore`) já vai dentro do AppImage (Linux) e do instalador do Windows (310,6 MB), com teste automático nos dois. Em 2026-10-17 a **medição oficial** rodou na sua placa de vídeo (RTX 3070). Resultado resumido: a base de teste e a abertura dos três arquivos reais passaram; **3 metas não foram atingidas**, e você mandou manter todas as metas, sem afrouxar nada:
- **Memória do arquivo pesado:** 6,84 GB contra a meta de 6,0 GB. Já medimos onde a memória vai (T21).
- **Trocar a forma de uma parede em IFC real (M2b):** 399 ms (arquivo de 25 MB) e 6.749 ms (arquivo detalhado) contra 200 ms. Já medimos o que pesa (T22): quase todo o tempo é espera do quadro novo.
- **Threads:** a forma 2 (fatias na janela) reprova a parede de 150 aberturas; a forma 1 (thread à parte) deixa a janela surda por mais de 1 s com o mouse no lote grande. A escolha é sua (T19).

**Agora:** o Opus está planejando as opções de redução para a memória e para o M2b (lote 57, em execução em 2026-10-18; ele só planeja, não implementa). **Depois:** você escolhe as opções; decidimos as threads e a arquitetura (ADR-001 e ADR-004, T19); só então escrevemos o roteiro de aceite da S04 para você conferir no AppImage e no instalador. Em paralelo: a conferência automática do Windows (o CI) leva cerca de 34 min e a meta é 10 min; você mandou manter a meta e abrir um cartão para encurtar (T23, da S04). O rascunho está pronto e **espera o seu ok** e 3 respostas suas. Ficou pausado: o registro local de mensagens (T04b) e a redução de memória em si (T20). O fim da S04 continua sendo uma decisão **sua**, com os números.

## 4. O plano de revisão (a proposta que você mandou ao Claude Projects)
**A ideia:** antes de continuar a parte mais difícil (S04), conferir se S01, S02 e S03 estão realmente certas, e organizar os riscos. As revisões das três fatias terminaram em 15/10 e a S04 voltou a andar.

**O que você decidiu (14 e 15/10):**
- Pausar a S04 até as revisões terminarem (D1). A pausa acabou com as revisões.
- Mover os 3 planos antigos para `docs/arquivo/` (D2). **Feito.**
- Detalhes 2D ficam na 1.0. DXF e fachadas são candidatos a adiar (D3).
- Exceções de portão sempre registram a meta original (D8).

**O que foi feito:**
- S01, S02 e S03 revisadas e **aceitas por você em 15/10**.
- 25 cartões de revisão geral (RG-01 a RG-25), quase todos mesclados. Uma revisão final independente do Opus concluiu que o CI não ficou mais frouxo e que nada se perdeu na reorganização.
- Relatórios e diário reorganizados em `docs/state/`.

**O que falta da revisão:**
- Texto do `CLAUDE.md` (cartão RG-28): o pedido 128 foi fechado sem mesclar; o texto exato volta a você para aprovar.
- Limpeza dos ramos antigos no GitHub: nada foi apagado; espera a sua palavra.
- Feitos desde então: pedido 127 (decisão do ADR-004 no plano) mesclado; seleção que devolvia objeto removido (RG-27) corrigida; pedido 124 (janela do fluxo B) fechado e refeito em partes, já no `main`.

## 5. Perguntas que são suas (nenhuma é urgente)
1. **Memória e atualização da forma da parede:** quando o Opus terminar o planejamento (lote 57), escolher entre as opções que ele apresentar. O resumo virá em 5 linhas.
2. **Threads e arquitetura (T19):** escolher a forma das threads (ADR-004) e decidir o híbrido contra o C++ puro (ADR-001), com os números oficiais.
3. **CI do Windows (T23):** dar o ok ao rascunho e responder 3 perguntas: como contar os 10 min; se o Linux ganha cartão irmão; o que fazer se o CI sozinho parar em 15 a 17 min.
4. **Roteiro de aceite da S04:** será escrito depois da decisão do T19; nada a responder agora.
5. **Texto do `CLAUDE.md` (RG-28)** e **ramos antigos do GitHub:** aprovar o texto e dizer se apagamos os ramos.
6. **Menores, sem prazo:** travar o ambiente do instalador pela mesma trava (A3) e aplicar ao AppImage o critério do instalador (A4); folga nos testes de tempo do Windows (A5); confirmar que as exceções de ausência acabaram (A9); convite de revisão externa, imagens dos desenhos de tela e os 8 testes no Revit (A6); nomes dos colegas de estágio para testar (A11); `/usage` para o registro de cota (A10); autorização da CAIXA para o SINAPI, necessária só na F5 (A15).
