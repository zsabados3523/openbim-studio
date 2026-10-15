<!--
SPDX-License-Identifier: AGPL-3.0-or-later
-->
# Mapa do projeto (versão simples)

Para o Rafael. Escrito em 2026-10-15 a partir do que está no GitHub (`main`). Se este mapa e o resto divergirem, avise.

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
| **S04** | **Python e C++ conversam bem?** Python é fácil de mexer. C++ é mais rápido. Testamos a mistura contra C++ sozinho. Essa prova decide a arquitetura | **Pausada** por decisão sua |
| S05 | Desfazer, refazer e gravar sem perder dados | Não começou |
| S06 | Gerar planta e corte automaticamente | Não começou |
| S07 | Criar uma porta ou janela por script | Não começou |
| S08 | Reunir modelos de teste | Contínua |
| S09 | Desenhos de tela, feitos com você | Entrevista feita. Falta você aceitar o resumo |
| S10 | **Portão da F0:** juntar os números e decidir "seguimos" ou "mudamos o plano" | Não começou |

### Dentro da S04
Já fizemos a ponte básica, a janela 3D, câmera, clique, comandos em Python, as paredes em C++ e a abertura de arquivos grandes. A ferramenta que mede os resultados também está pronta, mas a medição oficial ainda não rodou. Está parado: o fluxo em C++ com janela (T14c), threads e memória do viewport. O fim da S04 é uma decisão **sua**: as duas decisões de arquitetura (ADR-001 e ADR-004), com números.

## 4. O plano de revisão (a proposta que você mandou ao Claude Projects)
**A ideia:** antes de continuar a parte mais difícil (S04), conferir se S01, S02 e S03 estão realmente certas, e organizar os riscos.

**O que você decidiu (14 e 15/10):**
- Pausar a S04 até as revisões terminarem (D1).
- Mover os 3 planos antigos para `docs/arquivo/` (D2). **Feito.**
- Detalhes 2D ficam na 1.0. DXF e fachadas são candidatos a adiar (D3).
- Exceções de portão sempre registram a meta original (D8).

**O que foi feito:**
- S01, S02 e S03 revisadas e **aceitas por você em 15/10**.
- 25 cartões de revisão geral (RG-01 a RG-25), quase todos mesclados. Uma revisão final independente do Opus concluiu que o CI não ficou mais frouxo e que nada se perdeu na reorganização.
- Relatórios e diário reorganizados em `docs/state/`.

**O que falta:**
- RG-28 (texto do `CLAUDE.md`) e os pedidos 127 e 128 esperam você.
- Falta fechar a segunda falha de teste da noite (seleção devolveu objeto removido). Cartão RG-27.
- Aceitar o resumo da entrevista (S09).
- Decidir o que fazer com o pedido 124 (T14c), que foi reaberto durante a pausa.
- Depois disso, retomar a S04 (cartão RG-02).

## 5. Perguntas que são suas (nenhuma é urgente)
1. Os pedidos 127 e 128 estão aprovados?
2. A S04 continua pausada ou você libera?
3. Pode apagar os 25 ramos antigos do GitHub?
