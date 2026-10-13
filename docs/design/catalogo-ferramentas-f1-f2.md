# Catálogo de ferramentas das Fases 1 e 2

- Autor: agente sonnet (líder técnico) · Data: 2026-10-12
- Para: Rafael (PO), que vai desenhar o visual à mão a partir deste documento.
- Base: a ficha de pesquisa `docs/research/2026-10-12-ferramentas-revit-archicad-f1-f2.md`, o plano `v2/02` (Fases 1 e 2) e o padrão híbrido da `v2/03` (F0-S09).
- Estado: **proposta**. Nada aqui vira especificação sem a sua aprovação.
- Palavras e nomes são nossos. Não há cópia de telas, ícones, textos de ajuda ou marcas. Onde a ficha não confirmou um comportamento, está escrito **"a confirmar com teste do PO"**.

## Como ler cada ficha de ferramenta

Cada ferramenta tem sempre os mesmos itens, na mesma ordem:
1. **O que faz** (uma frase).
2. **Como se usa** (passo a passo, mouse e teclado).
3. **Na tela** (o que aparece quando ela está ativa).
4. **Altera o modelo?** (o que muda e o que NÃO muda).
5. **Entra em** (fatia do plano).
6. **Outros programas e nossa proposta** (uma linha de comparação e a recomendação).

Palavras que usamos:
- **Modelo** = o desenho em si, guardado no arquivo `.ifc`.
- **Vista salva** = configuração de como você enxerga o modelo (o que está oculto, cortes, cores). Fica no arquivo `.obim`, ao lado do `.ifc`. Não muda o modelo.
- **Estado de tela** = coisa temporária, só para você olhar. Some ao fechar o projeto. Não é gravada em lugar nenhum.
- **Elemento** = uma parede, laje, porta etc.

---

## 1. Mapa da tela (padrão híbrido)

O padrão assumido na F0-S09: **navegador do projeto e propriedades ao jeito do Revit** (listas à esquerda e à direita, sempre abertas); **caixa de ferramentas e ajustes salvos ao jeito do ArchiCAD** (faixa de botões das ferramentas, com ajustes prontos de cada ferramenta). Só o conceito é imitado; o desenho dos botões e dos painéis será nosso.

### Desenho em texto (janela principal)

```
+----------------------------------------------------------------------------------+
| [1] BARRA DE MENU      Arquivo  Editar  Vista  Modelo  Ajuda     [desfazer][refazer] |
+----------------------------------------------------------------------------------+
| [2] BARRA DE OPÇÕES  (muda conforme a ferramenta ativa)                            |
|     Ex.: Parede ->  Tipo [ v ]  Linha de localização [ v ]  Altura [ v ]  [x] Encadear |
+--------------+-------------------------------------------------+-----------------+
| [3] CAIXA DE | [5] ÁREA DE TRABALHO (desenho)                  | [4] PAINEL DE   |
|  FERRAMENTAS |                                                 |  PROPRIEDADES   |
| -Selecionar- |        +---------+   [cubo de vistas]           |                 |
| [Selecionar] |        |  3D ou  | [mini-barra:                 |  Elemento: Parede|
|  -Modelar-   |        |         |                              |                  |
| [Parede]     |        | planta  |  Mover Copiar Girar ...]     |  Tipo: [ v ] [Editar tipo]|
| [Laje]       |        |         |        campo junto ao cursor |  Comprimento ... |
| [Pilar]      |        +---------+        +---------------+     |  Altura ...      |
| [Viga]       |                           | 3,25 m | 90°  |     |  Material ...    |
| [Porta]      |                           +---------------+     |  (lista longa    |
| [Janela]     |   (clique direito no elemento abre a mesma      |   com rolagem)   |
|   -Editar-   |    mini-barra)                                  |                 |
| [Mover]      |                                                 |                 |
| [Copiar]     |                                                 |                 |
| [Girar]      |                                                 |                 |
| [Espelhar]   |                                                 |                 |
| [Alinhar]    |                                                 |                 |
| [Aparar/est.]|                                                 |                 |
|-Referências- |                                                 |                 |
| [Nível/Eixo] +-------------------------------------------------+-----------------+
|   -Medir-    |                                                                    |
| [Medir]      | [6] NAVEGADOR DO PROJETO (árvore)                                  |
|              |   Casa                                                             |
|  -Ajustes-   |    +- Pavimentos: Térreo, Cobertura                                |
|   -salvos-   |    +- Vistas: Planta Térreo, 3D, Corte A                           |
| Parede 15cm  |    +- Tipos: Paredes, Portas, Janelas ...                          |
| Parede 20cm  |    +- Modelo por classe: Paredes (12), Portas (4) ...              |
+--------------+--------------------------------------------------------------------+
| [7] BARRA DE ESTADO: dica da ferramenta | X 4,20  Y 7,10  Z 0,00 | Distância 3,25 | FPS 60 | Unidade: m |
+----------------------------------------------------------------------------------+
```

Observação: o navegador do projeto (6) pode ficar à esquerda, em cima da caixa de ferramentas, em abas. Quem decide a posição final é o seu desenho; aqui só dizemos **o que existe** e **o que cada parte faz**.

### O que é cada parte

1. **Barra de menu.** Arquivo, Editar, Vista, Modelo, Ajuda. Os botões de desfazer e refazer ficam sempre à vista.
2. **Barra de opções.** Faixa fina logo abaixo do menu. **Muda sozinha** conforme a ferramenta ativa: ao escolher Parede, mostra tipo, linha de localização, altura, "encadear". Sem ferramenta, fica vazia ou mostra opções da vista. É onde ficam as escolhas "antes de desenhar" e as escolhas **durante o uso** das ferramentas de Editar (copiar várias vezes, restringir a direção). A distância ou o ângulo se digitam no **campo junto ao cursor**. Desfazer e refazer continuam no topo.
3. **Caixa de ferramentas** (esquerda). Botões das ferramentas, em grupos, cada um com título no desenho: **Selecionar**; **Modelar** (parede, laje, pilar, viga, porta, janela); **Editar** (mover, copiar, girar, espelhar, alinhar, aparar e estender), logo abaixo de Modelar; **Referências** (nível, eixo); **Medir**. Os seis botões de Editar ficam **apagados quando nada está selecionado** e **acesos quando há seleção**. Abaixo, o grupo **Ajustes salvos**: ajustes prontos de uma ferramenta (por exemplo "Parede 15 cm, bloco, reboco duplo"). Clicar num ajuste ativa a ferramenta já configurada.
   - **Mini-barra de edição.** Uma faixa pequena com os mesmos seis botões de Editar aparece **junto ao elemento selecionado** e também ao **clicar com o botão direito** sobre ele. É um atalho: faz o mesmo que os botões da caixa de ferramentas.
4. **Painel de propriedades** (direita). Sempre aberto. Mostra os dados do que está selecionado; sem seleção, mostra os da vista ativa. Tem o botão "Editar tipo". Mudar a **instância** altera só o elemento; mudar o **tipo** altera todos daquele tipo.
5. **Área de trabalho.** O desenho: planta, corte ou 3D. Mostra o **cubo de vistas** (canto), os **campos junto ao cursor** (número digitável ao lado do ponteiro) e as **cotas temporárias** (medidas que aparecem sobre o elemento enquanto você desenha ou seleciona).
6. **Navegador do projeto.** Árvore com: pavimentos, vistas salvas, tipos e o modelo por classe (a "árvore espacial": projeto, terreno, edifício, pavimento, elementos). Duplo clique abre a vista. Clicar num item seleciona no desenho, e vice-versa.
7. **Barra de estado** (rodapé). Frase de dica da ferramenta ("Clique no ponto inicial da parede"), coordenadas do cursor, distância em andamento, FPS (quadros por segundo, pedido no F1-S02) e unidade.

### Onde ficam as medidas (resumo)

| Medida | Onde aparece |
|---|---|
| Posição do cursor (X, Y, Z) | Barra de estado |
| Distância e ângulo durante o desenho | Campos junto ao cursor + barra de estado |
| Valor digitável durante o desenho | Campos junto ao cursor (Tab troca de campo) |
| Cotas temporárias de um elemento selecionado | Sobre o desenho, ao lado do elemento; clique no número para editar |
| Resultado da ferramenta Medir | Cartão pequeno junto à linha medida + barra de estado |
| Dados fixos (comprimento, altura, área) | Painel de propriedades |

### Regras gerais de tela (valem para todas as ferramentas)
- **Esc** cancela o que está em andamento; um segundo Esc volta para Selecionar.
- **Enter** ou clique duplo conclui (quando a ferramenta tem vários cliques).
- A dica da barra de estado **sempre diz o próximo passo**.
- Nada some sem aviso: se uma ferramenta não puder agir, a barra de estado explica por quê.
- O arquivo mostra um ponto no título quando há mudança não salva.

---

## 2. Fichas das ferramentas

Índice (em ordem de uso):

**Fase 1: visualizador**
V1 Orbitar, deslocar e aproximar · V2 Cubo de vistas · V3 Enquadrar tudo e enquadrar seleção · V4 Selecionar · V5 Filtro da seleção · V6 Navegador do projeto e árvore espacial · V7 Filtro por classe · V8 Painel de propriedades (leitura) · V9 Ocultar e isolar (temporário) · V10 Ocultar na vista (salvo) · V11 Transparência · V12 Cor por propriedade · V13 Caixa de corte 3D · V14 Plano de corte · V15 Medir entre dois pontos · V16 Medir somando trechos · V17 Salvar sem perdas

**Fase 2: modelagem básica**
M1 Desfazer, refazer e recuperação automática · M2 Novo projeto a partir do modelo brasileiro · M3 Níveis · M4 Eixos · M5 Parede · M6 Camadas e linha de localização da parede · M7 Junções de parede (L e T) · M8 Laje · M9 Pilar · M10 Viga · M11 Porta · M12 Janela · M13 Snaps (pontos de captura) · M14 Entrada numérica junto ao cursor · M15 Cotas temporárias · M16 Mover · M17 Copiar · M18 Girar · M19 Espelhar · M20 Alinhar · M21 Aparar e estender · M22 Tipos e edição de propriedades · M23 Ajustes salvos (favoritos)

**Depois (só resumo):** T1 Telhado · T2 Escada

Siglas de comparação: **Rv** = como o Revit faz; **Ac** = como o ArchiCAD faz. São só para você reconhecer o fluxo; não copiamos nada.

---

### Fase 1: visualizador

#### V1. Orbitar, deslocar e aproximar (F1-S02)
- **Nome nosso:** Navegação 3D.
- **O que faz:** muda de onde você olha o modelo, sem mexer no modelo.
- **Como se usa:**
  1. **Modo A (roda e botão do meio):** roda do mouse aproxima e afasta, em direção ao ponteiro. Botão do meio arrastando desloca. Shift + botão do meio arrastando gira (orbita).
  2. **Modo B (botão esquerdo com teclas):** Shift + botão esquerdo arrastando gira. Ctrl + botão esquerdo arrastando (ou a roda) aproxima. Botão direito arrastando desloca. Duplo clique num elemento vai até ele; duplo clique no fundo enquadra tudo.
  3. O centro da rotação é o centro do modelo; **com algo selecionado, é o elemento selecionado**.
  4. O modo (A ou B) se escolhe em Arquivo > Preferências, e fica lembrado.
- **Na tela:** o cursor muda de forma (mão, círculo de giro, lupa). A barra de estado mostra os FPS. Nenhuma barra de opções.
- **Altera o modelo:** NÃO altera nada. Só a câmera.
- **Entra em:** F1-S02.
- **Comparação e proposta:** Rv resolve com 3 gestos fixos; Ac usa modos e teclas. **Proposta:** oferecer os dois como "Modo A" e "Modo B" (nomes neutros, sem marca). **Recomendação:** modo A como padrão, por ser mais simples. Teclas do modo B no pan: não usamos a barra de espaço (ela fica livre para virar porta). **A confirmar com teste do PO:** orbitar com e sem seleção, para conferir a sensação.

#### V2. Cubo de vistas (F1-S02)
- **Nome nosso:** Cubo de vistas (a ficha sugere "cubo de orientação"; o nome final fica para o PO).
- **O que faz:** mostra para onde o modelo aponta e salta para vistas prontas (frente, topo, canto).
- **Como se usa:**
  1. Clicar numa face leva a câmera àquela direção (frente, trás, esquerda, direita, topo, base).
  2. Clicar numa quina ou num canto leva a uma vista diagonal.
  3. Arrastar o cubo gira livremente.
  4. Botão "vista inicial" (uma casinha) volta à vista salva como inicial; menu do botão direito permite redefinir a vista inicial.
- **Na tela:** cubo pequeno no canto superior direito da área de trabalho, com os nomes das faces em português. Visual **próprio** (não copiamos a aparência de nenhum cubo existente).
- **Altera o modelo:** NÃO. Só a câmera.
- **Entra em:** F1-S02.
- **Comparação e proposta:** Rv tem um cubo; Ac troca vistas por menu e atalhos. **Proposta:** cubo próprio, com desenho nosso, mais a lista de vistas no menu Vista. **Recomendação:** manter o cubo (ajuda quem vem do Revit) e garantir o menu como alternativa.

#### V3. Enquadrar tudo e enquadrar seleção (F1-S02)
- **Nome nosso:** Enquadrar.
- **O que faz:** ajusta a câmera para caber o modelo todo, ou só o que está selecionado.
- **Como se usa:** tecla **Z** enquadra tudo; **Shift+Z** enquadra a seleção (sem seleção, avisa na barra de estado). Também há botões na barra do cubo.
- **Na tela:** a câmera desliza até o enquadramento. Se algum elemento estiver muito longe do resto (erro comum em arquivos recebidos), aparece o aviso "Há elementos distantes. Enquadrar sem eles?" com os botões Sim e Não.
- **Altera o modelo:** NÃO.
- **Entra em:** F1-S02.
- **Comparação e proposta:** Rv e Ac sofrem quando há um elemento perdido longe do modelo. **Proposta:** ignorar elementos remotos suspeitos, com aviso. **Recomendação:** adotar.

#### V4. Selecionar (F1-S03)
- **Nome nosso:** Selecionar.
- **O que faz:** escolhe um ou mais elementos para ver os dados ou agir sobre eles.
- **Como se usa:**
  1. Clique no elemento seleciona.
  2. **Tab** com o cursor parado troca para o próximo elemento sob o cursor (a barra de estado diz qual). Shift+Tab volta. Tab sobre paredes ligadas pegando a corrente inteira: **a confirmar com teste do PO**.
  3. **Janela da esquerda para a direita** (borda cheia): pega só o que está inteiro dentro da janela.
  4. **Janela da direita para a esquerda** (borda tracejada): pega também o que a janela toca.
  5. **Ctrl** + clique soma ao conjunto. **Shift** + clique tira.
  6. Clicar no vazio limpa a seleção.
- **Na tela:** elemento selecionado fica com contorno destacado; os dados aparecem no painel de propriedades; a barra de estado conta quantos há ("3 elementos: 2 paredes, 1 porta").
- **Altera o modelo:** NÃO. Só o conjunto selecionado, que é estado de tela.
- **Entra em:** F1-S03.
- **Comparação e proposta:** Rv: Tab, janela esquerda-direita contra direita-esquerda, Ctrl e Shift. Ac: usa uma "área de seleção" separada e a busca por critérios. **Proposta:** adotar o fluxo do Rv (é o que o arquiteto já tem na mão) e deixar a busca por critérios para depois. **Recomendação:** adotar.

#### V5. Filtro da seleção (F1-S03)
- **Nome nosso:** Filtro da seleção.
- **O que faz:** quando há várias categorias selecionadas, deixa tirar categorias do conjunto.
- **Como se usa:**
  1. Selecionar vários elementos de tipos diferentes.
  2. Clicar em "Filtrar" na barra de estado (ou no painel).
  3. Desmarcar as categorias que não quer (ex.: tirar "Portas").
  4. OK.
- **Na tela:** janelinha com a lista de categorias e a contagem de cada uma.
- **Altera o modelo:** NÃO.
- **Entra em:** F1-S03.
- **Comparação e proposta:** Rv tem um "Filtro" parecido; Ac usa "Localizar e selecionar". **Proposta:** só o filtro simples. **Recomendação:** adotar; busca avançada fica para outra fase.

#### V6. Navegador do projeto e árvore espacial (F1-S03; F2-S10)
- **Nome nosso:** Navegador do projeto.
- **O que faz:** lista tudo do projeto em árvore e liga a lista ao desenho.
- **Como se usa:**
  1. Abrir o grupo "Modelo por classe" ou "Estrutura do projeto" (projeto > edifício > pavimento > elementos).
  2. Clicar num item seleciona o elemento no 3D. Clicar no desenho seleciona o item na árvore.
  3. Duplo clique numa vista salva ou num pavimento abre aquela vista.
  4. Botão direito: renomear, duplicar vista, apagar vista.
- **Na tela:** painel em árvore, com grupos fechados por padrão: Pavimentos, Vistas, Tipos, Modelo por classe. Cada item mostra um número ("Paredes (12)").
- **Altera o modelo:** abrir e selecionar NÃO altera. Renomear ou criar vista altera só o `.obim`. Renomear um pavimento altera o modelo (`.ifc`).
- **Entra em:** F1-S03 (árvore e seleção ligada), F2-S10 (aba de tipos).
- **Comparação e proposta:** Rv junta tudo em "Vistas". Ac separa "pontos de vista" (planta de pavimento, corte) de "vistas salvas" (ponto de vista mais configurações). **Proposta:** separar como o Ac: "pontos de vista" e "vistas salvas". **Recomendação:** adotar.

#### V7. Filtro por classe (F1-S03)
- **Nome nosso:** Filtro por classe.
- **O que faz:** mostra na árvore e no desenho só um tipo de coisa (só paredes, só portas).
- **Como se usa:** na caixa de busca do navegador, digitar parte do nome ou escolher a classe numa lista; a árvore se reduz e o desenho destaca esses elementos.
- **Na tela:** caixa de texto e lista de classes no topo do navegador; os elementos que não batem ficam esmaecidos no desenho.
- **Altera o modelo:** NÃO. É estado de tela.
- **Entra em:** F1-S03.
- **Comparação e proposta:** os dois fazem algo parecido com critérios. **Proposta:** filtro simples por classe e por nome. **Recomendação:** adotar.

#### V8. Painel de propriedades, leitura (F1-S04)
- **Nome nosso:** Painel de propriedades.
- **O que faz:** mostra todos os dados do elemento selecionado: atributos, conjuntos de propriedades, quantidades, material e tipo.
- **Como se usa:** selecionar um elemento; o painel preenche sozinho. Seções recolhíveis. Sem seleção, mostra os dados da vista ativa. Na F1 é **só leitura**; a edição vem na F2.
- **Na tela:** lista com seções (Identificação, Posição, Dimensões, Material, Conjuntos de propriedades, Quantidades, Tipo). Botão de copiar valor.
- **Altera o modelo:** NÃO (F1). Na F2 a edição vira a ferramenta M22.
- **Entra em:** F1-S04.
- **Comparação e proposta:** Rv tem paleta fixa. Ac tem janela de configurações por ferramenta mais o painel de informação. **Proposta:** paleta fixa à direita, como o Rv. **Recomendação:** adotar.

#### V9. Ocultar e isolar (temporário) (F1-S05)
- **Nome nosso:** Ocultar e isolar.
- **O que faz:** esconde (ou deixa só) o selecionado, apenas para você olhar.
- **Como se usa:**
  1. Selecionar um elemento (ou uma categoria).
  2. **H** oculta. **I** isola (tudo o mais some).
  3. **Shift+H** mostra tudo de novo.
  4. No menu, "Aplicar à vista" transforma o estado temporário em estado salvo (ver V10).
- **Na tela:** uma moldura colorida fina em volta da área de trabalho e a frase "Visibilidade temporária" com botão "Mostrar tudo".
- **Altera o modelo:** NÃO. É estado de tela: não é gravado e some ao fechar o projeto.
- **Entra em:** F1-S05.
- **Comparação e proposta:** Rv tem ocultar e isolar temporários; Ac usa camadas. **Proposta:** separar bem **temporário** e **salvo**, como os dois fazem. **Recomendação:** adotar.

#### V10. Ocultar na vista (salvo) (F1-S05)
- **Nome nosso:** Ocultar na vista.
- **O que faz:** esconde elementos ou categorias de forma permanente numa vista salva.
- **Como se usa:** selecionar > menu "Ocultar na vista" > escolher "Elemento" ou "Categoria". Para voltar: "Mostrar ocultos" (revela temporariamente o que está oculto, em outra cor) e restaurar.
- **Na tela:** os elementos desaparecem; no modo "Mostrar ocultos" aparecem em cor de aviso.
- **Altera o modelo:** NÃO. Altera só a vista salva (no `.obim`).
- **Entra em:** F1-S05 (a gravação da vista no `.obim` depende do estado do projeto; a confirmar na especificação).
- **Comparação e proposta:** Rv: "ocultar na vista"; Ac: combinação de camadas. **Proposta:** por vista, não por camada. **Recomendação:** adotar.

#### V11. Transparência (F1-S05)
- **Nome nosso:** Transparência.
- **O que faz:** deixa elementos translúcidos para ver o que há atrás.
- **Como se usa:** selecionar > controle deslizante "Transparência" no painel ou menu Vista. Pode ser por elemento, por categoria (ex.: todas as lajes) ou geral.
- **Na tela:** controle deslizante de 0 a 100% e botão "Aplicar à vista".
- **Altera o modelo:** NÃO. Fica no estado de tela ou na vista salva.
- **Entra em:** F1-S05.
- **Comparação e proposta:** Rv: pelas regras de gráficos por categoria; Ac: pelas sobreposições gráficas. **Proposta:** controle direto, mais simples. **Recomendação:** adotar.

#### V12. Cor por propriedade (F1-S05)
- **Nome nosso:** Cor por propriedade.
- **O que faz:** pinta os elementos conforme um dado deles (material, tipo, pavimento, resistência ao fogo...).
- **Como se usa:**
  1. Menu Vista > Cor por propriedade.
  2. Criar uma regra: escolher a propriedade, o valor e a cor.
  3. Adicionar quantas regras quiser; arrastar para mudar a ordem. **A primeira regra que combina vence.**
  4. Marcar "Salvar na vista" para gravar.
- **Na tela:** janela com a lista de regras (critério, cor, ordem) e legenda das cores no canto da área de trabalho.
- **Altera o modelo:** NÃO. As regras ficam na vista salva (`.obim`).
- **Entra em:** F1-S05.
- **Comparação e proposta:** Rv: filtros de vista com regras; Ac: regras ordenadas em combinações. **Proposta:** regras com critério, estilo e prioridade, como os dois. **Recomendação:** adotar; primeira versão só com cor (hachura fica para a F3).

#### V13. Caixa de corte 3D (F1-S06)
- **Nome nosso:** Caixa de corte.
- **O que faz:** recorta o 3D por uma caixa ajustável, para ver o interior.
- **Como se usa:**
  1. Tecla **B** liga a caixa em volta do modelo (ou do selecionado).
  2. Arrastar uma face da caixa para dentro corta aquele lado.
  3. Duplo clique numa face leva a face até um limite exato (valor digitável).
  4. **B** de novo desliga. "Salvar na vista" guarda a caixa.
- **Na tela:** caixa translúcida com alças nas faces; a parte fora da caixa some; barra de opções com "Mostrar caixa", "Redefinir" e "Salvar na vista".
- **Altera o modelo:** NÃO. Só a vista.
- **Entra em:** F1-S06.
- **Comparação e proposta:** Rv: "caixa de seção"; Ac: "corte 3D". É o mesmo conceito. **Proposta:** um só recurso, com caixa e plano personalizado (V14). **Recomendação:** adotar.

#### V14. Plano de corte (F1-S06)
- **Nome nosso:** Plano de corte.
- **O que faz:** corta o 3D por um plano que você define com dois cliques.
- **Como se usa:**
  1. Tecla **Q**.
  2. Clicar o primeiro ponto, clicar o segundo ponto: a linha entre os dois define o plano vertical.
  3. A seta mostra qual lado fica. Clicar na seta inverte.
  4. **Esc** cancela. Para sair, **Q** de novo.
- **Na tela:** linha do plano com a seta; o lado removido some; barra de opções com "Inverter lado" e "Salvar na vista".
- **Altera o modelo:** NÃO. Só a vista.
- **Entra em:** F1-S06. (O **alcance da vista** da planta, que decide o que aparece cortado na planta, só entra na Fase 2/3, junto das vistas de planta.)
- **Comparação e proposta:** os dois têm algo equivalente. **Proposta:** plano de dois cliques. **Recomendação:** adotar.

#### V15. Medir entre dois pontos (F1-S07)
- **Nome nosso:** Medir.
- **O que faz:** mostra a distância entre dois pontos do modelo, com captura (snap) em cantos, pontas e centros.
- **Como se usa:**
  1. Tecla **R** (de régua).
  2. Passar o cursor perto de um canto ou de uma ponta: aparece o marcador de captura (ver M13).
  3. Clicar o ponto 1, clicar o ponto 2.
  4. Ler o resultado: distância total, e também o deslocamento em X, Y e Z.
  5. **Esc** limpa. Clique novo começa outra medida.
- **Na tela:** linha, números junto à linha (cartão pequeno) e repetição na barra de estado. A tolerância esperada é de ±1 mm para o corpus de teste (F1-S07).
- **Altera o modelo:** NÃO. É leitura temporária. Não cria cota (a cota permanente vem na F3).
- **Entra em:** F1-S07.
- **Comparação e proposta:** Rv tem "Medir" com dois modos. Ac não tem um comando de distância único no desktop; usa a régua e as cotas. **Proposta:** o modo dois pontos, com captura. **Recomendação:** adotar.

#### V16. Medir somando trechos (F1-S07)
- **Nome nosso:** Medir caminho.
- **O que faz:** soma vários trechos seguidos, útil para contornos e perímetros.
- **Como se usa:** dentro de Medir (R), marcar a opção "Somar trechos"; clicar vários pontos; o total acumulado aparece e é atualizado a cada ponto; Enter encerra.
- **Na tela:** linha quebrada, medida de cada trecho e o total.
- **Altera o modelo:** NÃO.
- **Entra em:** F1-S07.
- **Comparação e proposta:** o Ac descreve total acumulado (no visualizador dele); o Rv mede ao longo de um elemento. **Proposta:** só soma de pontos clicados. **Recomendação:** adotar; medir ao longo de um elemento fica para depois.

#### V17. Salvar sem perdas (F1-S08)
- **Nome nosso:** Salvar.
- **O que faz:** grava o `.ifc` sem alterar nada que você não mexeu.
- **Como se usa:** **Ctrl+S**. Na F1 (só visualizador), o arquivo não muda; o que é gravado são as vistas salvas (no `.obim`).
- **Na tela:** barra de progresso no rodapé; no título, o ponto de mudança não salva some.
- **Altera o modelo:** NÃO deve mudar o sentido de nada; o critério de aceite é "diferença semântica zero" no corpus de teste.
- **Entra em:** F1-S08.
- **Comparação e proposta:** os dois gravam em formato próprio; nosso IFC é o formato principal. **Proposta:** o que a ficha não cobre; esta ficha só registra o comportamento esperado. **Recomendação:** especificar na própria fatia, sem depender da pesquisa.

---

### Fase 2: modelagem básica

#### M1. Desfazer, refazer e recuperação automática (F2-S01)
- **Nome nosso:** Desfazer, refazer e recuperação.
- **O que faz:** volta e avança as ações do modelo; e guarda cópias de segurança para recuperar depois de um travamento.
- **Como se usa:**
  1. **Ctrl+Z** desfaz; **Ctrl+Y** (ou Ctrl+Shift+Z) refaz.
  2. A seta ao lado do botão abre a **lista de ações**: escolher uma desfaz ela e todas as seguintes.
  3. Se você fizer uma ação nova, o "refazer" é descartado.
  4. A gravação automática acontece sozinha, em segundo plano.
  5. Ao reabrir depois de uma falha, aparece "Recuperar o trabalho de há X segundos?" com Sim e Não.
- **Na tela:** botões na barra de menu, com o nome da última ação ("Desfazer: Mover parede"). Na reabertura, janela de recuperação com data e hora.
- **Altera o modelo:** desfazer e refazer revertem ou reaplicam as mudanças do modelo.
- **Entra em:** F2-S01.
- **Comparação e proposta:** nem Rv nem Ac prometem "recuperar até 30 segundos antes". O Rv só tem lembrete de salvar e cópias numeradas; o Ac tem salvamento automático configurável, mas ele pode falhar junto com a falha. **Proposta:** manter o nosso aceite (30 s), **avisar com honestidade** que a recuperação pode falhar, e **nunca zerar** a lista de desfazer em operações de pavimento (decisão nossa, melhor que o Ac). **Recomendação:** adotar.

#### M2. Novo projeto a partir do modelo brasileiro (F2-S02)
- **Nome nosso:** Novo projeto.
- **O que faz:** cria o par `Casa.ifc` + `Casa.obim` já com pavimentos, materiais e vistas padrão.
- **Como se usa:**
  1. **Ctrl+N**.
  2. Escolher o modelo (por ora, "Residencial BR").
  3. Preencher: nome do projeto, nome do arquivo, pasta. A ficha lembra: **pedir o nome** na criação, porque os dados do projeto vêm vazios.
  4. Criar.
- **Na tela:** janela de três passos (modelo, dados, pasta). O projeto abre com os pavimentos já na árvore e uma planta e um 3D prontos.
- **Altera o modelo:** cria os dois arquivos, válidos desde o primeiro segundo.
- **Entra em:** F2-S02.
- **Comparação e proposta:** Rv e Ac trazem unidades, níveis e vistas padrão. **Proposta:** igual, com unidades em metros e milímetros. **Recomendação:** adotar.

#### M3. Níveis (F2-S03)
- **Nome nosso:** Nível (pavimento).
- **O que faz:** cria e move planos de referência de altura (pavimentos); o que está preso a um nível se move junto.
- **Como se usa:**
  1. Tecla **N**.
  2. Numa vista de corte ou elevação, clicar onde o nível começa e onde termina (ou digitar a cota).
  3. Para mudar a cota: selecionar o nível > editar o valor no painel de propriedades (ou na cota temporária).
  4. Os elementos presos àquele nível (paredes, portas, pilares) **acompanham**.
- **Na tela:** linha horizontal com nome e cota; ao mudar a cota, aviso: "12 elementos serão movidos". Se algum elemento ficar com topo abaixo da base, **aviso de elemento invertido**.
- **Altera o modelo:** muda a cota do pavimento e a posição de quem depende dele. NÃO mexe nos elementos que não dependem dele.
- **Entra em:** F2-S03.
- **Comparação e proposta:** Rv: mudar a cota move o nível e os dependentes. Ac tem **duas ações diferentes**: mudar a **cota** (altera as alturas dos vizinhos) e mudar a **altura** (desloca todos os de cima). **Proposta:** uma única ação clara, "mudar a cota do nível" (como o Rv). Ver "Decisões para o PO", pergunta 2. **Recomendação:** adotar só a do Rv na F2.

#### M4. Eixos (F2-S03)
- **Nome nosso:** Eixos.
- **O que faz:** desenha linhas de referência (eixos de pilares e paredes) que fazem parte do modelo.
- **Como se usa:**
  1. Tecla **E**.
  2. Clicar o ponto inicial, clicar o ponto final; ou digitar o comprimento.
  3. O nome (A, B, 1, 2...) sobe sozinho; clique duplo para renomear.
  4. Eixos aparecem numa planta só se cruzarem o nível daquela planta.
- **Na tela:** linha tracejada longa com uma bolha com o nome na ponta.
- **Altera o modelo:** cria eixos (parte do modelo). Atenção: **a grade de captura é outra coisa**: é só ajuda de tela, não faz parte do modelo (ver M13).
- **Entra em:** F2-S03.
- **Comparação e proposta:** Rv e Ac têm eixos como elemento. **Proposta:** separar sempre "eixo do modelo" de "grade de captura", como o Ac. **Recomendação:** adotar.

#### M5. Parede (F2-S04)
- **Nome nosso:** Parede.
- **O que faz:** desenha paredes retas, uma ou várias em sequência, com tipo e altura.
- **Como se usa:**
  1. Tecla **P**. Na barra de opções escolher: tipo, altura (ou "até o nível de cima"), linha de localização (ver M6), "Encadear" (liga ou desliga).
  2. Clicar o ponto inicial.
  3. Mover o cursor; digitar o comprimento (ver M14) e **Enter**, ou clicar o ponto final.
  4. Com "Encadear", a ponta final já é o início da próxima parede. Duplo clique ou **Esc** termina.
  5. **Espaço** ou clique no ícone troca o lado da linha de localização antes de colocar.
- **Na tela:** parede fantasma seguindo o cursor, cota temporária com o comprimento, campos junto ao cursor (comprimento e ângulo), dica na barra de estado.
- **Altera o modelo:** cria paredes (cada uma com camadas e eixo). As junções entre paredes são resolvidas pela regra de M7. Não cria portas nem vãos.
- **Entra em:** F2-S04.
- **Comparação e proposta:** Rv: clique-clique, tipo e linha de localização; Ac: método geométrico e linha de referência. **Proposta:** só paredes retas na F2 (curvas ficam fora do escopo). **Recomendação:** adotar.

#### M6. Camadas e linha de localização da parede (F2-S04)
- **Nome nosso:** Camadas da parede e linha de localização.
- **O que faz:** define de que é feita a parede (camadas) e qual linha da parede segue o seu clique.
- **Como se usa:**
  1. Tipo de parede: botão "Editar tipo" no painel (M22).
  2. Lista de camadas: função (estrutura, acabamento, isolamento), material, espessura. Arrastar para reordenar.
  3. **Núcleo**: duas marcas dizem onde começa e termina a camada estrutural.
  4. Linha de localização: 6 opções: eixo da parede, eixo do núcleo, face externa de acabamento, face interna de acabamento, face externa do núcleo, face interna do núcleo.
  5. Mudar a linha de localização depois NÃO move a parede; "inverter" gira a parede em torno da linha.
- **Na tela:** janela de edição com a lista de camadas e um desenho em corte (planta) da parede; a linha de localização aparece como traço colorido no desenho.
- **Altera o modelo:** altera o tipo (e portanto todas as paredes daquele tipo). Os materiais das camadas ficam no modelo.
- **Entra em:** F2-S04.
- **Comparação e proposta:** os dois têm camadas e núcleo; o Ac chama de "linha de referência", com 3 opções simples e 6 compostas. **Proposta:** as 6 opções sempre. **Recomendação:** adotar.

#### M7. Junções de parede (L e T) (F2-S04)
- **Nome nosso:** Junção de paredes.
- **O que faz:** resolve como duas ou mais paredes se encontram (L, T) e como suas camadas se unem.
- **Como se usa:**
  1. Sozinha: ao desenhar, a junção é criada automaticamente.
  2. Para mudar: ferramenta "Junção de paredes" (sem tecla própria; fica no menu Modelo e na caixa de ferramentas), clicar na junção.
  3. Na barra de opções: tipo (**topo** ou **esquadria**), botões "Próxima" e "Anterior" para percorrer as ordens possíveis.
  4. "Impedir junção" numa ponta; "Permitir" para restaurar.
  5. Camadas: a camada de função mais forte avança sobre a mais fraca.
- **Na tela:** as paredes mudam de forma à vista; a barra de opções mostra o tipo atual e um contador ("opção 2 de 3").
- **Altera o modelo:** muda só a **forma** mostrada das paredes. Não cria nem apaga paredes; guarda o tipo de junção e as exceções.
- **Entra em:** F2-S04.
- **Comparação e proposta:** Rv: tipos topo, esquadria e esquadrejar; Ac: ordem de junção por prioridade. Meia-esquadria entre parede e o meio de outra não existe nos dois. **Proposta:** vocabulário comum e regra de prioridade explícita: função da camada, depois ordem. **As regras exatas saem do caderno de joins do PO** (20 casos). **A confirmar com teste do PO** (caderno de joins). **Recomendação:** adotar; o caderno é o oráculo.

#### M8. Laje (F2-S05)
- **Nome nosso:** Laje.
- **O que faz:** cria uma laje a partir de um contorno fechado, com ou sem furos.
- **Como se usa:**
  1. Tecla **L**. Escolher tipo e nível na barra de opções.
  2. Clicar os cantos do contorno, um a um; fechar no primeiro ponto (ou Enter).
  3. **Furo:** selecionar a laje, ativar "Adicionar furo" e desenhar outro contorno fechado **dentro** da laje.
  4. Editar o contorno depois: duplo clique na laje, ajustar pontos, Enter.
- **Na tela:** contorno em linha tracejada, área da laje em tempo real na barra de estado, furos com borda diferente.
- **Altera o modelo:** cria a laje com o contorno; furos viram vazios dentro dela.
- **Entra em:** F2-S05.
- **Comparação e proposta:** Rv: contorno fechado, abertura dentro do contorno; Ac: contorno e furo desenhado dentro. **Proposta:** o mesmo fluxo; poço que atravessa vários níveis fica para depois. **Recomendação:** adotar.

#### M9. Pilar (F2-S06)
- **Nome nosso:** Pilar.
- **O que faz:** coloca um pilar de seção escolhida num ponto, entre dois níveis.
- **Como se usa:**
  1. Tecla **K**. Escolher o perfil (retangular, circular...), nível de base e de topo (ou altura livre).
  2. Clicar o ponto. Se estiver sobre o cruzamento de eixos, a captura ajuda.
  3. **Espaço** gira 90° antes de colocar.
- **Na tela:** pilar fantasma no cursor, medidas da seção na barra de opções.
- **Altera o modelo:** cria um pilar com perfil e extrusão. Não mexe nas paredes à volta.
- **Entra em:** F2-S06.
- **Comparação e proposta:** Rv: base e topo por níveis, deslocamentos, espaço gira; Ac: configuração semelhante (os detalhes do pilar no Ac: **a confirmar com teste do PO**). **Proposta:** perfil e níveis. **Recomendação:** adotar.

#### M10. Viga (F2-S06)
- **Nome nosso:** Viga.
- **O que faz:** coloca uma viga entre dois pontos, com perfil e altura de assentamento.
- **Como se usa:**
  1. Tecla **V**. Escolher perfil e deslocamento em relação ao nível.
  2. Clicar o início, clicar o fim (a ordem importa).
  3. Opção "Encadear" para várias vigas seguidas.
  4. Dica: colocar eixos e pilares antes ajuda a capturar.
- **Na tela:** viga fantasma, comprimento no campo junto ao cursor.
- **Altera o modelo:** cria uma viga (perfil e extrusão). Não cria "sistema de vigas".
- **Entra em:** F2-S06.
- **Comparação e proposta:** Rv: dois cliques; Ac: viga única, encadeada ou retângulo (inclinada só na única). **Proposta:** única e encadeada; inclinada fica fora. **Recomendação:** adotar.

#### M11. Porta (F2-S07)
- **Nome nosso:** Porta.
- **O que faz:** coloca uma porta numa parede. A porta fica **presa à parede** e leva o vão com ela.
- **Como se usa:**
  1. Tecla **D**. Escolher o tipo (tipos fixos).
  2. Passar o cursor sobre uma parede: a porta aparece como fantasma, grudada.
  3. **Espaço** vira o sentido da abertura (lado) e a mão (esquerda ou direita) antes de colocar.
  4. Chegar perto da face interna ou externa define o lado do batente.
  5. Clicar coloca. A parede é furada **automaticamente**.
  6. Depois de colocada, selecionar e arrastar: **o vão acompanha**. Dois botões pequenos giram o sentido e a mão.
- **Na tela:** porta fantasma, cotas temporárias até as pontas da parede (editáveis), campos de altura da verga e peitoril na barra de opções.
- **Altera o modelo:** cria a porta, o vão na parede e a ligação entre eles. NÃO cria vão sozinho sem porta.
- **Entra em:** F2-S07.
- **Comparação e proposta:** Rv: peça hospedada, espaço vira o lado; Ac: dois cliques (posição e abertura), mas um elemento "abertura" separado **não acompanha** a porta se ela for movida. **Proposta:** porta sempre hospedada na parede; abertura solta não existe na F2. **A confirmar com teste do PO:** o furo automático da parede no Rv e o mover porta. **Recomendação:** adotar.

#### M12. Janela (F2-S07)
- **Nome nosso:** Janela.
- **O que faz:** coloca uma janela numa parede, igual à porta, mas com peitoril.
- **Como se usa:** tecla **J**. Mesmo fluxo da porta (M11). Além disso: altura do peitoril (referência: nível, base da parede ou topo da parede) escolhida na barra de opções, com valor digitável.
- **Na tela:** janela fantasma, cotas temporárias, campos de peitoril e altura.
- **Altera o modelo:** cria a janela, o vão e a ligação. Mover a janela move o vão.
- **Entra em:** F2-S07.
- **Comparação e proposta:** igual à porta. **Proposta:** igual à porta. **Recomendação:** adotar.

#### M13. Snaps, os pontos de captura (F2-S08)
- **Nome nosso:** Captura de pontos.
- **O que faz:** grudar o cursor em cantos, pontas, meios, centros e cruzamentos.
- **Como se usa:**
  1. Ligada sempre. Passar perto de um ponto faz aparecer um marcador (quadrado, triângulo, círculo, cruz) e uma etiqueta ("Ponta", "Meio").
  2. **Tab** muda entre os pontos disponíveis no mesmo lugar.
  3. **Shift** trava o movimento na horizontal ou vertical.
  4. Menu Vista > Captura: ligar ou desligar cada tipo; intervalo da grade de captura.
  5. As **guias de alinhamento** (linhas finas que aparecem quando o cursor se alinha com outro ponto) ajudam a desenhar sem digitar.
- **Na tela:** marcador, etiqueta e guias tracejadas.
- **Altera o modelo:** NÃO. A grade de captura é ajuda de tela.
- **Entra em:** F2-S08 (V15 e V16, medir com captura, usam a mesma captura já na F1-S07).
- **Comparação e proposta:** Rv tem diálogo de captura e atalhos de duas letras; Ac tem guias de alinhamento e linhas permanentes. **Proposta:** captura sempre ligada, mais guias de alinhamento. **Recomendação:** adotar; atalhos de duas letras ficam para depois.

#### M14. Entrada numérica junto ao cursor (F2-S08)
- **Nome nosso:** Campos junto ao cursor (a ficha lembra que o nome original é marca; este é nosso).
- **O que faz:** deixa digitar medidas diretamente enquanto desenha, sem usar o mouse para medir.
- **Como se usa:**
  1. Com uma ferramenta ativa e o primeiro ponto clicado, simplesmente **digitar um número**. Ele entra no campo destacado (por exemplo, o comprimento).
  2. **Tab** passa para o próximo campo (ângulo, altura).
  3. **Enter** confirma e coloca o elemento.
  4. Sinais de + e - acumulam e subtraem ("3,20+0,15").
  5. Unidade padrão do projeto; aceita vírgula ou ponto decimal.
- **Na tela:** quadro pequeno ao lado do cursor com os campos (comprimento, ângulo, e quando couber altura); o campo ativo fica em destaque.
- **Altera o modelo:** NÃO sozinha; só define a medida do elemento que está sendo criado.
- **Entra em:** F2-S08 (aceite: desenhar uma casa de 60 m² sem medir com o mouse).
- **Comparação e proposta:** Ac tem o fluxo completo (digitar já preenche o campo, Tab troca); no Rv, digitar durante o desenho: **a confirmar com teste do PO**. **Proposta:** adotar o fluxo do Ac como padrão. **Recomendação:** adotar; é o que garante o aceite do F2-S08. **Atenção às teclas:** enquanto o quadro está ativo, só números, Tab, Enter e Esc valem; letras de ferramenta ficam desligadas.

#### M15. Cotas temporárias (F2-S08)
- **Nome nosso:** Cotas temporárias.
- **O que faz:** mostra medidas ao lado do elemento selecionado ou em colocação; clicar no número muda a medida e move o elemento.
- **Como se usa:**
  1. Selecionar uma parede, porta etc.: aparecem as cotas até os elementos vizinhos.
  2. Clicar num número, digitar o valor novo, Enter: o elemento se move.
  3. Um botão pequeno ao lado transforma a cota temporária em cota permanente (a cota permanente completa vem na F3).
- **Na tela:** linhas finas com números em azul, só enquanto o elemento está selecionado.
- **Altera o modelo:** editar o número move o elemento (muda posição). Ver a cota NÃO altera nada.
- **Entra em:** F2-S08.
- **Comparação e proposta:** Rv tem exatamente esse recurso; no Ac o equivalente é digitar no Tracker (M14). **Proposta:** os dois: campos ao desenhar, cotas temporárias ao editar. **Recomendação:** adotar.

#### M16. Mover (F2-S09)
- **Nome nosso:** Mover.
- **O que faz:** desloca elementos selecionados.
- **Como se usa:**
  1. Selecionar. Tecla **M**.
  2. Clicar um ponto de partida (com captura), clicar o destino. Ou digitar distância e Enter (M14).
  3. Opção **"Restringir"** (barra de opções): só na direção perpendicular ou ao longo do elemento.
  4. Opção **"Desconectar"**: quebra as relações antes de mover (a porta pode trocar de parede, por exemplo).
  5. Os valores das opções ficam lembrados.
- **Na tela:** **Onde fica e como ativar:** botão no grupo "Editar" da caixa de ferramentas (aceso só com seleção), botão igual na mini-barra junto à seleção, item no clique com o botão direito, ou tecla **M**. Durante o uso: linha do deslocamento com distância ao vivo; a sombra do elemento no destino. "Restringir" e "Desconectar" ficam na barra de opções; a distância se digita no campo junto ao cursor.
- **Altera o modelo:** muda a posição dos elementos. Elementos presos (porta numa parede) vão junto, a menos que "Desconectar" esteja marcado.
- **Entra em:** F2-S09.
- **Comparação e proposta:** os dois fazem de forma parecida; o Ac tem um menu "Editar > Mover". **Proposta:** adotar as opções do Rv. **Recomendação:** adotar.

#### M17. Copiar (F2-S09)
- **Nome nosso:** Copiar.
- **O que faz:** faz uma cópia de elementos num novo lugar.
- **Como se usa:** como Mover, com tecla **C**. Opção **"Múltiplo"** mantém a ferramenta ativa para várias cópias seguidas.
- **Na tela:** **Onde fica e como ativar:** botão no grupo "Editar" da caixa de ferramentas (aceso só com seleção), botão igual na mini-barra junto à seleção, item no clique com o botão direito, ou tecla **C**. Durante o uso: igual a Mover; a cópia aparece como fantasma. "Múltiplo" fica na barra de opções.
- **Altera o modelo:** cria novos elementos, **cada um com identificação própria nova**. Não altera o original.
- **Entra em:** F2-S09.
- **Comparação e proposta:** Rv: restringir, desconectar, múltiplo; Ac: cópia por arrastar com Ctrl+Alt, "Multiplicar" (matriz). **Proposta:** só cópia simples e múltipla. **Matriz** (copiar em grade ou círculo) **fica para depois**. **Recomendação:** adotar.

#### M18. Girar (F2-S09)
- **Nome nosso:** Girar.
- **O que faz:** gira elementos em torno de um ponto.
- **Como se usa:**
  1. Selecionar. Tecla **G**.
  2. Clicar o centro de rotação.
  3. Clicar o ângulo inicial, clicar o ângulo final; ou digitar o ângulo (M14).
  4. Opção "Copiar" gira uma cópia e deixa o original.
- **Na tela:** **Onde fica e como ativar:** botão no grupo "Editar" da caixa de ferramentas (aceso só com seleção), botão igual na mini-barra junto à seleção, item no clique com o botão direito, ou tecla **G**. Durante o uso: transferidor leve ao redor do centro e valor do ângulo ao vivo; o ângulo se digita no campo junto ao cursor e "Copiar" fica na barra de opções.
- **Altera o modelo:** muda a posição e a orientação. Não altera o tipo.
- **Entra em:** F2-S09.
- **Comparação e proposta:** os dois têm. **Proposta:** com o campo de ângulo. **Recomendação:** adotar.

#### M19. Espelhar (F2-S09)
- **Nome nosso:** Espelhar.
- **O que faz:** inverte elementos em relação a um eixo, com ou sem deixar o original.
- **Como se usa:**
  1. Selecionar. Tecla **F** ("flip").
  2. Escolher "Usar um eixo existente" (clicar numa linha) ou "Desenhar o eixo" (dois cliques).
  3. Opção "Copiar": ligada, deixa o original; desligada, só espelha.
- **Na tela:** **Onde fica e como ativar:** botão no grupo "Editar" da caixa de ferramentas (aceso só com seleção), botão igual na mini-barra junto à seleção, item no clique com o botão direito, ou tecla **F**. Durante o uso: a linha do eixo e a imagem fantasma espelhada; "Copiar" e a escolha do eixo ficam na barra de opções.
- **Altera o modelo:** espelha os elementos (ou cria cópias espelhadas, com identificação nova).
- **Entra em:** F2-S09.
- **Comparação e proposta:** os dois têm. **Proposta:** igual ao Rv, com opção "Copiar" explícita. **Recomendação:** adotar.

#### M20. Alinhar (F2-S09)
- **Nome nosso:** Alinhar.
- **O que faz:** leva um elemento a ficar alinhado com outro.
- **Como se usa:**
  1. Tecla **A**. Na barra de opções, escolher a preferência: faces, eixos, face do núcleo, centro do núcleo.
  2. Clicar a referência (o que **fica parado**).
  3. Clicar o elemento a alinhar (o que **se move**).
  4. Alinhamento múltiplo: segurar **Ctrl** e clicar vários.
- **Na tela:** **Onde fica e como ativar:** botão no grupo "Editar" da caixa de ferramentas (aceso só com seleção), botão igual na mini-barra junto à seleção, item no clique com o botão direito, ou tecla **A**. Durante o uso: linha tracejada de referência e a mudança de posição ao vivo; a preferência (faces, eixos...) fica na barra de opções.
- **Altera o modelo:** muda a posição do elemento movido. **NÃO** guarda uma "trava": o alinhamento acontece uma vez só.
- **Entra em:** F2-S09.
- **Comparação e proposta:** Rv oferece um cadeado que mantém o alinhamento se um dos dois mover. Isso exige **restrições guardadas no `.obim`** (o IFC não guarda). **Proposta:** adiar o cadeado. **Recomendação:** adiar (ver pergunta 5).

#### M21. Aparar e estender (F2-S09)
- **Nome nosso:** Aparar e estender.
- **O que faz:** corta ou prolonga paredes e vigas até uma linha limite.
- **Como se usa:**
  1. Tecla **T**. Escolher o modo: "Até o canto" (duas paredes, clicando em cada uma na parte que fica), "Um elemento" (contra um limite) ou "Vários".
  2. Clicar o limite e depois o que será aparado ou estendido.
- **Na tela:** **Onde fica e como ativar:** botão no grupo "Editar" da caixa de ferramentas (aceso só com seleção), botão igual na mini-barra junto à seleção, item no clique com o botão direito, ou tecla **T**. Durante o uso: a parte que será removida fica esmaecida antes do clique; o modo (até o canto, um elemento, vários) fica na barra de opções.
- **Altera o modelo:** muda o comprimento do elemento. Não altera o tipo.
- **Entra em:** F2-S09.
- **Comparação e proposta:** Rv tem três modos. O Ac tem "ajustar" e "tesoura" (a documentação lida do Ac não detalha: **a confirmar com teste do PO**). **Proposta:** os três modos do Rv. **Recomendação:** adotar.

#### M22. Tipos e edição de propriedades (F2-S10)
- **Nome nosso:** Tipos e propriedades.
- **O que faz:** edita dados de um elemento (instância) ou de todos os elementos de um tipo.
- **Como se usa:**
  1. Selecionar o elemento: o painel mostra os dados da **instância**. Mudar um valor altera só ele.
  2. Botão "Editar tipo": abre os dados do **tipo**. Mudar um valor altera todos os elementos daquele tipo.
  3. Selecionar um tipo no navegador (aba Tipos) mostra os dados dele só para leitura; o botão "Editar tipo" abre a edição.
  4. Trocar o tipo de um elemento: lista de tipos no topo do painel.
- **Na tela:** painel de propriedades com dois blocos (instância e tipo), um aviso "afeta N elementos" no botão de tipo.
- **Altera o modelo:** valor de instância altera aquele elemento; valor de tipo altera o tipo e todas as instâncias.
- **Entra em:** F2-S10.
- **Comparação e proposta:** Rv trabalha assim; o Ac não tem tipo compartilhado (só atributos como compostos e materiais). O formato IFC já tem tipo e instância. **Proposta:** adotar o modelo do Rv. **Recomendação:** adotar.

#### M23. Ajustes salvos, os favoritos (depois da F2-S10; a decidir)
- **Nome nosso:** Ajustes salvos. (A palavra "favoritos" aparece no plano da F0-S09; é conceito comum, mas é nome de produto do Ac, por isso propomos "ajustes salvos".)
- **O que faz:** guarda uma ferramenta já configurada (tipo, altura, linha de localização) para reuso em um clique.
- **Como se usa:**
  1. Configurar a ferramenta; botão "Salvar como ajuste" na barra de opções; dar um nome.
  2. O ajuste aparece na caixa de ferramentas, abaixo dos botões.
  3. Clicar nele ativa a ferramenta com aqueles valores.
  4. Botão direito: renomear, apagar, atualizar com a configuração atual.
- **Na tela:** lista curta de ajustes salvos na caixa de ferramentas.
- **Altera o modelo:** NÃO. Fica na configuração do programa (e, se você quiser, no `.obim`).
- **Entra em:** não tem fatia no plano. **Proposta:** entra como extra na F2-S10 ou logo depois. O PO decide.
- **Comparação e proposta:** é o recurso do Ac que o padrão híbrido quer. **Recomendação:** adiar para depois da F2-S10; o plano não pediu na F2.

---

### Depois (resumo)

> Atenção: o seu pedido dizia "F3", mas o plano `v2/02` coloca telhado e escada em **F4** ("Modelagem residencial completa"). Onde há conflito, o `v2/` prevalece. Ver "Decisões para o PO", pergunta 1.

#### T1. Telhado (F4)
- **O que faz:** cria a cobertura da casa (águas, beiral).
- **Resumo do que os outros programas fazem:** Rv desenha por contorno (linhas marcadas "define inclinação") ou por perfil em elevação; Ac faz um plano por vez, com linha de pivô, lado que sobe e inclinação, beiral global ou por plano.
- **Altera o modelo:** criaria cobertura e recortaria paredes.
- **Nossa proposta:** detalhar na F4. Nesta fase, nada.

#### T2. Escada (F4)
- **O que faz:** cria escadas retas, em L ou em U entre dois níveis.
- **Resumo do que os outros programas fazem:** Rv calcula degraus até o nível seguinte e tem patamar opcional; Ac desenha por polilinha e propõe soluções se não fechar. Os limites de altura de degrau e largura do piso nos programas: **a confirmar com teste do PO**.
- **Altera o modelo:** criaria lances de escada e patamares.
- **Nossa proposta:** detalhar na F4.

---

## 3. Tabela resumo

"Altera o modelo?" = muda o arquivo `.ifc`. "Só a vista" = muda só o `.obim`. "Não" = estado de tela, nada gravado.

| # | Ferramenta | Tecla | Fatia | Altera o modelo? |
|---|---|---|---|---|
| V1 | Navegação 3D (orbitar, deslocar, aproximar) | mouse | F1-S02 | Não |
| V2 | Cubo de vistas | mouse | F1-S02 | Não |
| V3 | Enquadrar tudo / seleção | Z / Shift+Z | F1-S02 | Não |
| V4 | Selecionar | S (ou Esc) | F1-S03 | Não |
| V5 | Filtro da seleção | menu | F1-S03 | Não |
| V6 | Navegador do projeto (árvore) | Ctrl+2 | F1-S03 | Não (renomear pavimento muda o modelo) |
| V7 | Filtro por classe | busca | F1-S03 | Não |
| V8 | Painel de propriedades (leitura) | Ctrl+1 | F1-S04 | Não |
| V9 | Ocultar e isolar (temporário) | H / I / Shift+H | F1-S05 | Não |
| V10 | Ocultar na vista | menu | F1-S05 | Só a vista |
| V11 | Transparência | menu | F1-S05 | Não ou só a vista |
| V12 | Cor por propriedade | menu | F1-S05 | Só a vista |
| V13 | Caixa de corte | B | F1-S06 | Não ou só a vista |
| V14 | Plano de corte | Q | F1-S06 | Não ou só a vista |
| V15 | Medir (dois pontos) | R | F1-S07 | Não |
| V16 | Medir caminho (soma) | R + opção | F1-S07 | Não |
| V17 | Salvar sem perdas | Ctrl+S | F1-S08 | Não (sentido igual) |
| M1 | Desfazer, refazer, recuperação | Ctrl+Z / Ctrl+Y | F2-S01 | Sim (reverte) |
| M2 | Novo projeto (modelo BR) | Ctrl+N | F2-S02 | Cria |
| M3 | Nível | N | F2-S03 | Sim |
| M4 | Eixos | E | F2-S03 | Sim |
| M5 | Parede | P | F2-S04 | Sim |
| M6 | Camadas e linha de localização | via tipo | F2-S04 | Sim (no tipo) |
| M7 | Junção de paredes | menu | F2-S04 | Sim (forma) |
| M8 | Laje | L | F2-S05 | Sim |
| M9 | Pilar | K | F2-S06 | Sim |
| M10 | Viga | V | F2-S06 | Sim |
| M11 | Porta | D | F2-S07 | Sim (porta e vão) |
| M12 | Janela | J | F2-S07 | Sim (janela e vão) |
| M13 | Captura de pontos | automático | F2-S08 | Não |
| M14 | Campos junto ao cursor | digitar | F2-S08 | Não (só define medida) |
| M15 | Cotas temporárias | clicar no número | F2-S08 | Sim, ao editar |
| M16 | Mover | botão Editar, mini-barra, clique direito ou M | F2-S09 | Sim |
| M17 | Copiar | botão Editar, mini-barra, clique direito ou C | F2-S09 | Sim (cria) |
| M18 | Girar | botão Editar, mini-barra, clique direito ou G | F2-S09 | Sim |
| M19 | Espelhar | botão Editar, mini-barra, clique direito ou F | F2-S09 | Sim |
| M20 | Alinhar | botão Editar, mini-barra, clique direito ou A | F2-S09 | Sim |
| M21 | Aparar e estender | botão Editar, mini-barra, clique direito ou T | F2-S09 | Sim |
| M22 | Tipos e propriedades | Ctrl+E (editar tipo) | F2-S10 | Sim |
| M23 | Ajustes salvos | Ctrl+3 (caixa) | a decidir | Não |
| T1 | Telhado | (depois) | F4 | Sim |
| T2 | Escada | (depois) | F4 | Sim |

Total: 40 fichas na Fase 1 e 2 (17 de visualizador, 23 de modelagem) mais 2 resumos (telhado e escada).

### Atalhos de teclado propostos (sem repetição)

Teclas de uma letra funcionam quando nenhum campo de texto tem o foco e quando **não** há um número sendo digitado (ver M14).

| Tecla | Faz | Observação |
|---|---|---|
| Esc | Cancela / volta a Selecionar | Sempre |
| Enter | Conclui | Sempre |
| Tab | Troca candidato (Selecionar), troca ponto de captura, troca campo (digitando) | Varia pelo contexto, mostrado na barra de estado |
| Espaço | Gira 90° ou vira sentido (pilar, porta, janela, lado da parede) | No modo B de navegação, o deslocamento é só com o botão direito (não usa o espaço) |
| S | Selecionar | |
| Z / Shift+Z | Enquadrar tudo / seleção | |
| H / I / Shift+H | Ocultar / Isolar / Mostrar tudo | Temporários |
| B | Caixa de corte | |
| Q | Plano de corte | |
| R | Medir (régua) | |
| N | Nível | |
| E | Eixos | |
| P | Parede | |
| L | Laje | |
| K | Pilar | |
| V | Viga | |
| D | Porta | |
| J | Janela | |
| M | Mover | Também pelo botão do grupo Editar, pela mini-barra e pelo clique direito (só com seleção) |
| C | Copiar | Igual a Mover: botão Editar, mini-barra, clique direito |
| G | Girar | Igual a Mover: botão Editar, mini-barra, clique direito |
| F | Espelhar | Igual a Mover: botão Editar, mini-barra, clique direito |
| A | Alinhar | Igual a Mover: botão Editar, mini-barra, clique direito |
| T | Aparar e estender | Igual a Mover: botão Editar, mini-barra, clique direito |
| Ctrl+Z / Ctrl+Y | Desfazer / Refazer | Ctrl+Shift+Z também refaz |
| Ctrl+S / Ctrl+N / Ctrl+O | Salvar / Novo / Abrir | |
| Ctrl+1 / Ctrl+2 / Ctrl+3 | Mostrar ou esconder Propriedades / Navegador / Caixa de ferramentas | |
| Ctrl+E | Editar tipo do selecionado | |
| Shift (segurando) | Trava na horizontal ou vertical | Durante o desenho |

Conflitos verificados na lista: nenhuma letra está duplicada; **A** e **D** não conflitam com campos numéricos porque as letras de ferramenta ficam desligadas durante a digitação. As letras seguem a regra "primeira letra do nome em português" onde foi possível; D (porta) e K (pilar) e R (medir) são os casos que fogem, para não colidir. A combinação completa de atalhos é nossa, **não** copia o pacote de nenhum programa; os dois modos de mouse chamam-se "Modo A" e "Modo B" (não "modo Revit"), como a ficha recomenda.

---

## 4. Decisões para o PO

Cada pergunta tem uma recomendação. Se você concordar com todas, basta responder "de acordo".

> Observação: a ficha de pesquisa traz 11 propostas na seção "Decisão", mas não tem uma lista numerada de cinco perguntas. Estas são as cinco decisões que, na leitura da ficha, mais precisam de resposta antes de especificar.

**1. Telhado e escada: em que fase entram?**
O plano `v2/02` coloca os dois na **F4**, não na F3 nem na F2. A ficha concorda que não há fatia de F2 para eles.
Recomendação: **manter na F4**. Na F2, nada. Neste catálogo ficam só como resumo.

**2. Mudar a altura de um pavimento: oferecemos uma ou duas ações?**
O Revit tem uma (mudar a cota: o nível e o que depende dele se movem). O ArchiCAD tem duas: mudar a **cota** (altera os vizinhos) e mudar a **altura** (desloca todos os de cima). Ter as duas confunde.
Recomendação: **só "mudar a cota do nível"**, com aviso de quantos elementos se movem e aviso de elementos que ficariam invertidos. "Mudar altura entre níveis" entra depois, como ação separada.

**3. Nomes dos modos de mouse e do cubo.**
Os nomes "Revit" e "ArchiCAD" são marcas e "ViewCube" também. Propostas: "Modo A" e "Modo B" para os mouses; "Cubo de vistas" para o cubo; "Ajustes salvos" no lugar de "favoritos"; "Campos junto ao cursor" no lugar de "Tracker".
Recomendação: **aprovar esses nomes** (você pode trocar, desde que não sejam nomes de produto).

**4. Recuperação automática: manter a meta de 30 segundos?**
Nem Revit nem ArchiCAD prometem isso. Nossa meta é mais exigente.
Recomendação: **manter a meta de 30 s** (está no aceite do F2-S01), mas escrever na tela de recuperação que ela **pode falhar** em caso de falha grave; e **nunca zerar a lista de desfazer** ao mexer em pavimentos.

**5. O que adiamos da F2 para não inchar?**
Itens que os dois programas têm, mas que pedem muito trabalho ou dado extra no `.obim`: **trava de alinhamento** (cadeado), **matriz** (copiar em grade), **elevar**, **poço que atravessa níveis**, **abertura solta** (sem porta) e **ajustes salvos**.
Recomendação: **adiar todos**. Porta e janela entram sempre presas à parede (assim "mover a porta move o vão", como o aceite do F2-S07 pede).

### Testes que o PO pode fazer para confirmar o que a ficha não confirmou
Se tiver tempo, no Revit e no ArchiCAD que você usa, com modelo próprio (nada vai para o repositório):
1. Junção L, T e X com camadas diferentes (o caderno de joins).
2. Digitar o comprimento durante o desenho da parede (contar as teclas).
3. Mover uma porta: o vão acompanha?
4. Mudar a cota de um nível: o que se move?
5. Parede baixa e o plano de corte da planta.
6. Orbitar com e sem seleção (o centro da rotação muda?).
7. Tab com paredes ligadas: pega a corrente inteira?
8. Os modos de aparar do ArchiCAD (conteúdo não lido na pesquisa).
