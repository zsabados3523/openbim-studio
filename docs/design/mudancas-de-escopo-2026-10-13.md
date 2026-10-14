<!--
SPDX-License-Identifier: AGPL-3.0-or-later
-->
# Mudanças de escopo pedidas em 13/10/2026

- Para: Rafael (PO). Aqui estão **todas** as mudanças de escopo pedidas hoje (decisões e entrevista S09) e o que cada uma pede para mudar no plano `v2/02`. **Estado (13/10): o PO aprovou as 14 mudanças e o plano `v2/02` foi atualizado numa única revisão (Revisão 3). Os prazos não foram recalculados; a faixa de 21 a 42 meses será refeita depois da medição da F0 (S10).** Texto original abaixo, mantido como registro.
- "1.0" = o marco F6 do plano (faixa publicada de 21 a 42 meses). Impacto no prazo é só uma **estimativa qualitativa**; números novos só depois que a Fase 0 medir a velocidade real.
- Siglas de fatia: F1-S02 = fatia 2 da Fase 1, e assim por diante.

## Mudanças

| # | Mudança | O que muda no `v2/02` | Impacto provável no prazo |
|---|---|---|---|
| 1 | Detalhes 2D na 1.0: linha de detalhe (D1), região preenchida (D2), itens de detalhe 2D (D3, biblioteca pequena própria). Chamada e vista de detalhe (D4) ficam para depois | Hoje "detalhes 2D" está em "Should" (§8) e na F5. Passar para "Must" e criar fatia nova de desenho 2D **antes da F3** (a definir) | Médio a grande: ferramenta nova de desenho, mais a biblioteca |
| 2 | Texto simples (T1) | Do F5 para a **F3**, junto da tag de ambiente (F3-S04) | Pequeno |
| 3 | Nuvem de revisão na 1.0 (revisões completas depois) | Em "revisões" (Should) só a nuvem vira "Must"; carimbo ganha campo livre "revisão" | Pequeno |
| 4 | Importar padrões de outro projeto, escolhendo o que importar (modelos de vista, estilos de linha e de texto, carimbo) | Acrescentar à F3, depois da primeira prancha (F3-S05) | Pequeno a médio |
| 5 | Referências quebradas: versão mínima (lista e contagem) | Da F5 para a **F3**; religar continua na F5 | Pequeno |
| 6 | **Voar** no 3D (botão direito mais W, A, S, D) | Acrescentar ao aceite de **F1-S02**, no roteiro de navegação | Pequeno |
| 7 | **Piso unificado** (laje e acabamento numa ferramenta, tipo com camadas) | F2-S05 passa a "Piso" com tipo de camadas; reduz a parte de "revestimentos por ambiente" da F4 (só o que não for piso) | Neutro ou pequeno: uma ferramenta em vez de duas, mas as camadas pedem mais testes |
| 8 | **Forro e rodapé na F2** | Forro sai da lista da F4 ("forros"); rodapé é novo. Criar **fatia nova na F2**, depois da F2-S07 (rodapé depende de paredes e portas). Modos "por ambiente" ficam para depois da F3-S01 | Pequeno a médio na F2; alivia a F4 só em parte |
| 9 | **Fundações** (sapata, bloco, estaca) candidatas da F4 | Citar na F4 como candidata (não fechada). Confirmar que é só o elemento, sem cálculo, porque o §8 deixa "estrutura/MEP" em "Won't" | Médio se entrar (desenho e ligação com pilares) |
| 10 | **Atalhos de duas letras** como padrão de fábrica (TR, AL, MM, MI, RR, CC, TG, WA), configuráveis | Acrescentar ao aceite de F1-S02 e F2-S09 (o conjunto de teclas) e criar uma tela de atalhos em Preferências; falta decidir a convivência com as teclas de uma letra | Pequeno |
| 11 | **Tags por atributo**, sem criar uma família nova para cada atributo | F3-S04 (tag de ambiente) e a tag por categoria (F4) mudam de forma: a tag mostra os campos escolhidos do tipo | Pequeno a médio |
| 12 | **"Por que não vejo isto?"** (botão que explica a regra que esconde um elemento) | Acrescentar a **F1-S05** em versão mínima (visibilidade); versão completa com as vistas da F3 | Pequeno |
| 13 | **Folha criada a partir de um modelo de folha** (tamanho, carimbo, campos) | F3-S05 (pranchas e carimbo): o aceite "prancha em ≤ 15 min" parte do modelo de folha | Neutro (já faz parte do carimbo configurável) |
| 14 | **Análises fora do núcleo** (solar, iluminação, energia, estrutural: plugins opcionais) | Registrar no §8 como "Won't" do núcleo, possíveis como plugin | Reduz risco; nenhum trabalho na 1.0 |

## Outras coisas que o PO disse e já mexem no plano
- Navegador do projeto **organizável pelo usuário** (pastas livres, com agrupamentos prontos): pesa em F1-S03 e F2-S10 (recomendação na entrevista).
- Cota que acompanha o desenho (F3-S04) fica como **indispensável**; "cota que comanda" (cadeado) fica para versão futura.

## Para o PO decidir
1. Aprovar esta lista como escopo (todas, ou riscar as que não quer).
2. Sim ou não para forro e rodapé **na F2, depois da F2-S07**, em vez de só na F3 (pergunta 7 do catálogo).
3. Se fundações são só o elemento (sem cálculo): recomendação sim.

## Arquivos de catálogo ainda por atualizar
`docs/design/catalogo-ferramentas-f3-anotacao.md` (tabela e seção 4) ainda mostra as recomendações **anteriores** às suas decisões de hoje (por exemplo "detalhes 2D fora da 1.0", texto na F4, nuvem "talvez"). Deve ser acertado depois da sua aprovação.

## Quando atualizar o `v2/02`
**Recomendação:** esperar o seu "de acordo" nesta lista; então fazer **uma única revisão do plano** (Revisão 3) com as 14 mudanças, antes de planejar a F1 e **sem** mexer nos números de prazo. Só recalcular a faixa de 21 a 42 meses **depois da medição da Fase 0** (portão S10), porque a velocidade real ainda não é conhecida. Regra do plano: **cortar escopo antes de aceitar atraso acima de 30%**; se a faixa recalibrada subir, os candidatos naturais a sair são fundações (9), importar padrões (4) e D3 (1).
