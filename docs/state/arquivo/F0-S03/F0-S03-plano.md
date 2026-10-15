<!--
SPDX-License-Identifier: AGPL-3.0-or-later
-->
# Plano proposto da F0-S03 (protótipo de viewport), para aprovação do PO

Fonte: `v2/03` S03. Nada foi iniciado. Em 5 linhas:
1. **O que provar:** desenhar um modelo IFC grande em 3D, girar/mover/aproximar e selecionar por clique, nos dois sistemas, dentro das metas (abrir ~100 MB < 60 s; ≥ 30 quadros/s com ~1 milhão de triângulos; clique < 100 ms; memória < 6 GB; funciona também em vídeo integrado Intel).
2. **Cuidado técnico:** a parte do Qt que desenha (QRhi) é semi-pública: ficará atrás de uma interface nossa, com a versão do Qt fixa.
3. **Tarefa crítica (T3, com Opus):** a geração das malhas com várias linhas de execução (threads) do IfcOpenShell. Precisa de especificação do Opus; o resto é T2.
4. **Depende de você:** (a) autorizar o download de um IFC público grande para o corpus (S08); (b) a máquina Windows é VM, então vídeo integrado Intel só se testa depois, em hardware real.
5. **Custo estimado:** média, com um lote Opus (especificação e revisão da malha). Semana atual em 14%: cabe.

## Cartões propostos
| Cartão | Título | Classe | Modelo |
|---|---|---|---|
| S03-T01 | Ficha de pesquisa: viewports abertos e QRhi (só fontes públicas) | T0/T1 | haiku + sonnet |
| S03-T02 | Corpus: um IFC público grande (precisa do seu ok para baixar) | T1 | sonnet |
| S03-T03 | Janela 3D mínima com QRhi (cubo na tela) e interface própria | T2 | sonnet |
| S03-T04 | Câmera: orbitar, mover, aproximar | T2 | sonnet |
| S03-T05 | Malhas do IFC em threads (IfcOpenShell C++) | **T3** | sonnet, especificação e revisão **opus** |
| S03-T06 | Seleção por clique | T2 | sonnet |
| S03-T07 | Benchmark reproduzível e relatório por sistema | T1 | sonnet |

## Perguntas ao PO
1. Aprova esta divisão? **Recomendo sim.**
2. Autoriza baixar um IFC público de ~100 MB (fonte e licença serão listadas antes)? **Recomendo sim**, na T02, depois da ficha.
3. Primeiro lote Opus da S03 (especificação da T05) só quando as T01 a T04 estiverem prontas.
