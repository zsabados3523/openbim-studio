<!--
SPDX-License-Identifier: AGPL-3.0-or-later
-->
# Mapa do projeto (versão simples)

Para o Rafael. Escrito em 2026-10-15 e atualizado em 2026-10-23 a partir do que está no GitHub (`main`) e em `docs/state/BOARD.md`. Se este mapa e o resto divergirem, avise.

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
| S04 | **Python e C++ conversam bem?** Testamos a mistura contra C++ sozinho. Essa prova decidia a arquitetura | **Pronta, esperando o seu aceite** pelo roteiro `docs/acceptance/S04.md`. Você já aceitou o híbrido (ADR-001) e a forma mista das threads (ADR-004) |
| **S05** | **Desfazer, refazer e gravar sem perder dados** | **Em andamento.** Plano e 12 cartões prontos; você aprovou as respostas P1 a P5; falta a P6 (esta organização de documentos) |
| S06 | Gerar planta e corte automaticamente | Não começou |
| S07 | Criar uma porta ou janela por script | Não começou |
| S08 | Reunir modelos de teste | Contínua |
| S09 | Desenhos de tela, feitos com você | Entrevista feita e aceita por você (15/10, com um ajuste). Faltam os desenhos de tela: você manda as imagens |
| S10 | **Portão da F0:** juntar os números e decidir "seguimos" ou "mudamos o plano" | Não começou |

### Como a S04 terminou (23/10)
- **Decisões suas:** arquitetura híbrida (Python mais núcleo em C++) e threads em forma mista, ambas aceitas em 23/10.
- **Metas na sua placa (RTX 3070):** todas atingidas. Troca de parede em arquivo real: cerca de 49 ms (antes 399 e 6.749 ms). Arquivo pesado: 52 s e 5.858 MB contra a meta de 6.000 MB (folga de só 42 MB no pior caso).
- **Aceitos por você como estão:** o teste automático do Windows leva cerca de 12 min (meta 10, mantida para a F1); 0,3% de oscilação num dos testes de lote foi aceito como ruído. O teste automático do Linux caiu de 39 para cerca de 9 min.
- **Abertos, com cartão e dono:** trava rara do Windows sem placa compatível (F1), Windows com placa real (T28, seu), quatro números do ADR-004 sem medida. Relatório: `docs/state/reports/F0-S04-fechamento.md`.

### Dentro da S05 (começou em 23/10)
Cartões T01 a T12 em `docs/state/cards/F0-S05/README.md`. Metas: 10.000 operações aleatórias e desfazer tudo voltam ao modelo igual; matar o programa no meio de uma sequência e reabrir recupera até a última edição confirmada; matar durante a gravação do par `.ifc` + `.obim` ainda deixa um par coerente; aplicar uma edição em menos de 5 ms num modelo de 50 MB; protótipo de merge (não é portão). Respostas suas já aprovadas: comparação do IFC por conteúdo sem instalar nada, `.obim` mínimo provisório, "Recuperar o trabalho de HH:MM?" sem nunca gravar por cima do seu `Casa.ifc`, salvamento automático a cada 5 min.

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
- Texto do `CLAUDE.md` (cartão RG-28): o texto exato volta a você para aprovar.
- Limpeza dos ramos antigos no GitHub: nada foi apagado; espera a sua palavra.

## 5. Perguntas que são suas (nenhuma é urgente)
1. **Aceite da S04:** conferir pelo roteiro `docs/acceptance/S04.md` no AppImage e no instalador; depois a S04 vira "Fechada".
2. **P6 (esta organização):** manter 1, 2 ou 3 dos documentos de estado (quadro, mapa, painel). Recomendação no relatório `docs/state/reports/F0-S05-T01-organizacao.md`.
3. **Texto do `CLAUDE.md` (RG-28)** e **ramos antigos do GitHub:** aprovar o texto e dizer se apagamos os ramos.
4. **Menores, sem prazo:** travar o ambiente do instalador pela mesma trava (A3) e aplicar ao AppImage o critério do instalador (A4); folga nos testes de tempo do Windows (A5); confirmar que as exceções de ausência acabaram (A9); convite de revisão externa, imagens dos desenhos de tela e os 8 testes no Revit (A6); nomes dos colegas de estágio para testar (A11); `/usage` para o registro de cota (A10); autorização da CAIXA para o SINAPI, necessária só na F5 (A15); T28, medir o viewport num Windows com placa real.
