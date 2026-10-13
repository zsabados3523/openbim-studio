<!--
SPDX-License-Identifier: AGPL-3.0-or-later
-->
# Roteiro da entrevista da S09: como você trabalha hoje

Para você, Rafael. Uma conversa de 1 hora, sem computador do nosso lado e sem preparo técnico. Não há resposta certa: queremos saber como você trabalha de verdade.

## 1. Objetivo
Entender, com as suas palavras, como um arquiteto faz um projeto residencial do começo ao fim, para desenharmos as telas do programa (desenhos de papel, sem código) e você aprovar. Esta entrevista é o primeiro passo; depois vêm duas rodadas de revisão (seção 8). Também confirma a decisão D: uma interface híbrida (painéis de navegação e propriedades ao estilo do Revit; caixa de ferramentas e "favoritos" ao estilo do ArchiCAD).

## 2. Preparação (uns 20 minutos, antes do dia)
Traga o que for fácil. Nada é obrigatório.
- 1 ou 2 projetos residenciais seus, abertos no programa que você usa, para você mostrar enquanto conta. Podem ser casas reais, sem problema.
- Prints ou fotos de tela **só para uso interno**: servem para você se lembrar do que quer dizer. Ficam na sua máquina, **fora do repositório**, e **nada vai a serviço online**. Não vamos copiar telas, ícones nem textos de ajuda.
- Uma lista rápida (papel serve) de: 5 coisas que você faz todo dia; 3 que mais irritam; 3 que você jamais quer perder.
- Um lugar sem interrupções e, se quiser, permissão para o líder gravar o **áudio só para fazer o resumo**. Se não quiser gravar, tudo bem: o líder anota. O áudio, se existir, fica fora do repositório e é apagado depois do resumo aprovado.

## 3. Minuto a minuto (60 min)
| Tempo | Bloco | O que conversamos |
|---|---|---|
| 0–5 | Abertura | Objetivo, regras da seção 6, como será o resultado. Você diz qual programa usa mais no dia a dia. |
| 5–12 | Como começa um projeto | O que você tem em mãos no início (terreno, levantamento, briefing do cliente)? O que cria primeiro? Usa modelo-base ou começa do zero? Em que ordem define níveis, eixos, paredes? |
| 12–20 | Fluxo diário de uma casa | Conte uma casa residencial do primeiro traço até a entrega. Onde gasta mais tempo? Onde refaz mais coisas? Que etapas são legais (prefeitura) e quais são executivas? |
| 20–27 | Ver e navegar | Como alterna entre planta, corte, fachada e 3D? Quantas vistas ficam abertas? O que você precisa ver sempre na tela? Como anda no 3D (mouse, teclas)? |
| 27–37 | Desenhar e editar | Parede, porta, janela, laje: como você as coloca (clicando, digitando medida, escolhendo tipo antes)? Como corrige: mover, copiar, alinhar, aparar? Com que frequência digita números em vez de usar o mouse? |
| 37–43 | Pranchas | Como monta uma prancha? O que muda de uma folha para outra? Quanto você ajusta à mão (cotas, textos, carimbo)? |
| 43–49 | Atalhos e hábitos | Quais atalhos de teclado usa sem pensar? Mão no mouse o tempo todo ou alterna? Botão do meio, roda, clique duplo: o que espera de cada um? |
| 49–55 | Dores e o que NÃO perder | As 3 maiores dores e os 3 hábitos que o programa novo não pode quebrar. O que você abandonaria sem dó? |
| 55–60 | Híbrido e fechamento | Revisamos juntos as perguntas da seção 4 que sobraram e combinamos as datas das duas revisões. |

### Perguntas extras sobre anotação (para os blocos Pranchas e Dores)
Respostas curtas bastam. Servem ao catálogo `docs/design/catalogo-ferramentas-f3-anotacao.md`.
1. **Cotas:** quais você usa mais (linear, alinhada, de nível, de ponto, angular)? Precisa que a cota **siga o desenho** quando a parede muda? Já digitou um valor na cota para mover a parede (cota "que comanda"), e quer isso?
2. **Tags:** o que você etiqueta (portas, janelas, ambientes, outros)? A numeração das esquadrias é automática ou à mão?
3. **Textos:** que tipos usa (nota, título de vista, especificação)? Algum modelo de nota que você reutiliza?
4. **Detalhes 2D:** no executivo, o que você desenha em 2D por cima do modelo (linhas, hachuras, textos, peças)? Quantos detalhes tem uma casa típica? Aceitaria que na 1.0 só houvesse linhas, hachuras e texto, sem biblioteca de peças e sem chamada?
5. **Quadros:** quais quadros você coloca na prancha (áreas, esquadrias, materiais, legenda)? Quais colunas são indispensáveis? Você edita pelo quadro ou só lê?
6. **Carimbo:** quais campos ele tem? Quantos modelos de carimbo você usa? Revisão: nuvem no desenho ou só uma letra e data no carimbo?
7. **Prefeitura contra executivo:** o que a prefeitura exige a mais que você não faria no executivo (cotas, quadro, carimbo, textos)? E o contrário?
8. **Dor:** qual anotação consome mais tempo hoje (rótulos, tags, textos, chamadas, legendas, tabelas, carimbo)? O que você quer que o programa novo faça sozinho?

Dica de ritmo: se um bloco estourar, o líder anota o ponto e volta nele na revisão, em vez de tirar tempo do bloco seguinte.

## 4. Perguntas objetivas
Cada pergunta tem duas opções e a recomendação do líder. Você pode responder "A", "B" ou "nenhuma, é assim: ...". As recomendações são palpites para destravar a conversa, não decisões tomadas.

| # | Pergunta | A | B | Recomendação do líder |
|---|---|---|---|---|
| 1 | Onde ficam as vistas do projeto (plantas, cortes, fachadas, pranchas)? | Numa lista em árvore à esquerda, sempre visível | Numa janela que abre e fecha quando precisa | A, a lista fixa: dá visão geral e você troca de vista com um clique. |
| 2 | Onde edita as propriedades do que está selecionado (altura, material, tipo)? | Painel fixo ao lado, que mostra tudo do que você clicou | Janela que abre ao clicar duas vezes | A, painel fixo: menos cliques e muda na hora. |
| 3 | Como escolhe a ferramenta (parede, porta, janela)? | Caixa de ferramentas com botões grandes e favoritos que você monta | Faixa de abas no topo com grupos (ao estilo de menu de fita) | A, caixa com favoritos: é o centro do híbrido e mantém o desenho limpo. |
| 4 | Ao desenhar parede, você prefere... | Escolher o tipo (espessura, camadas) antes de desenhar | Desenhar primeiro e trocar o tipo depois | A, escolher antes, mas poder trocar depois. |
| 5 | Ao colocar porta ou janela... | Clicar na parede e o vão abre sozinho | Marcar o ponto e digitar a distância do canto | A com B opcional: clica e, se quiser, digita a medida. |
| 6 | Medidas na hora de desenhar | Digitar o número logo depois do primeiro clique | Usar só o mouse e ajustar depois | A, digitar número: é como se projeta a 60 m² sem medir com o mouse. |
| 7 | Prancha | Montar na hora, arrastando vistas para a folha | Preparar tudo nas vistas e a prancha só reúne | A, arrastar para a folha, com a vista continuando editável. |
| 8 | Atalhos de teclado | Seguir o padrão de um dos programas que você usa | Atalhos próprios, que você pode trocar | A como ponto de partida, B sempre possível (configuração). Dizer qual programa seguir. |
| 9 | Navegar no 3D | Botão do meio para girar e roda para zoom | Atalho de teclado com mouse | A, e perguntar qual dos dois programas é a referência. |
| 10 | Vistas abertas ao mesmo tempo | Várias lado a lado | Uma de cada vez, com abas | B, abas: mais simples para a 1.0; lado a lado entra depois se pesar. |

## 5. O que o líder grava como saída
Em até 2 dias após a entrevista, o líder entrega ao PO:
1. **Resumo de 1 página**, em pt-BR simples, com a história do fluxo e as frases mais fortes que você disse.
2. **Lista dos fluxos** (da ideia ao desenho, da vista à prancha etc.), cada um em 3 a 6 passos.
3. **Decisões tomadas** (cada pergunta da seção 4 com a resposta A, B ou outra) e **dúvidas que ficaram**.
4. **Ferramentas prioritárias**: as 5 a 8 que você mais usa, na ordem de importância, com 1 linha sobre como cada uma deve se comportar.
5. **Lista do "não pode perder"** e **lista das dores**.
Onde ficam: o resumo e as listas vão em `docs/research/` como ficha de pesquisa (regra da seção 6); as decisões entram também em `docs/state/PO.md`. O áudio, se houve, e seus prints ficam fora do repositório.

## 6. Regras de propriedade intelectual (valem durante a entrevista e depois)
- Tudo o que o líder escreve é **comportamento descrito com as suas palavras** ("quando clico na parede, o vão abre"). Não copiamos telas, ícones, nomes de comandos de marca, textos de ajuda ou layouts idênticos.
- Prints e fotos de tela que você trouxer ficam só com você, fora do repositório. Não entram em documento, teste nem wireframe.
- Não abrimos arquivos proprietários nem inspecionamos programas. Seus testes de comportamento com modelos próprios (você faz algo no seu programa e conta o resultado) **são permitidos** e podem virar ficha de pesquisa.
- Conceitos e fluxos (níveis, vistas, tipos, pranchas, propriedades) podem ser imitados; a aparência específica não.
- Seus projetos não vão a nenhum serviço online sem autorização escrita sua no chat.
- Normas ABNT: se você citar uma, anotamos só o número, nunca o texto.

## 7. Aceite desta entrevista
Você confirma, no chat, que (1) o resumo reflete o que disse; (2) as respostas da seção 4 estão certas; (3) a decisão D (híbrido) fica confirmada ou ajustada. Só então os wireframes começam.

## 8. Como a entrevista vira wireframes (2 rodadas)
Wireframe é um desenho de caixas e rótulos, sem cores nem ícones de marca, mostrando onde fica cada coisa.
1. **Rascunho 1:** o líder desenha, a partir das suas respostas, a janela principal, o navegador de vistas, o painel de propriedades, a ferramenta de parede, o editor de vista e a prancha. Você recebe imagens e uma nota de 5 linhas explicando.
2. **Revisão 1 (cerca de 30 min):** você marca o que está errado, o que falta e o que sobra, no chat ou no desenho.
3. **Rascunho 2:** o líder corrige e devolve com lista do que mudou.
4. **Revisão 2 (cerca de 20 min):** última rodada. Você aprova ou diz o que falta.
5. **Aceite (F0-S09):** você aprova no chat. Se ainda houver pendência grande, o líder leva as opções e a recomendação, em vez de fazer uma terceira rodada em silêncio.
Os wireframes aprovados viram base das telas das fases seguintes.
