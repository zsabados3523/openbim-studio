<!--
SPDX-License-Identifier: AGPL-3.0-or-later
-->
# Entrevista S09: resumo e saídas (partes 1 a 3, 13/10/2026)

Palavras do líder a partir da fala do PO, em partes de cerca de 20 min. Sem telas, ícones nem textos de marca. Aguarda o aceite do PO (roteiro, seção 7). Anotações brutas: `2026-10-13-entrevista-s09-parte1-anotacoes.md`, `...-parte2-anotacoes.md`.

## 1. Resumo (1 página)
O PO é arquiteto e fez todos os projetos da faculdade no Revit (conhece o ArchiCAD). Parte de um escopo, define programa de necessidades e volumetria, prepara a base do terreno (GeoSampa, via CAD), depois define níveis, eixos (que seguram as paredes), paredes, aberturas, pisos, revestimentos e coberturas. A documentação vem depois: layout de pranchas, propriedades, vistas e anotações. A modelagem é o que mais consome tempo; a documentação é rápida se o modelo estiver bem feito; correções voltam à modelagem. Projeto legal é simples; o executivo é detalhado (cortes de detalhe, vistas de cômodos, especificação por marca e modelo, quadros) e tem revisões.
Frases fortes: "evita retrabalho e ficar caçando dimensões ausentes" (cota que acompanha o desenho); "a mão no mouse o tempo todo é fundamental em BIM"; "automatização de cortes, vistas e detalhes, completamente essencial"; "tag consome mais tempo porque tenho que criar uma família nova para cada atributo".

## 2. Fluxos
1. **Começar um projeto:** terreno/envoltório (CAD) → volumetria → níveis → eixos → estrutura e paredes (as paredes podem ou não ficar presas aos eixos) → aberturas, pisos, revestimentos, coberturas. A ordem é o fluxo habitual do PO, não uma regra; o programa não deve obrigá-la (ajuste do PO em 2026-10-15).
2. **Colocar elemento:** escolher o tipo → clicar → prévia do corte/posição → clicar para confirmar (digitar medida quando tem certeza).
3. **Editar:** atalho de duas letras (mover, copiar, girar, espelhar, alinhar, aparar) com a mão no mouse; botões para o que usa menos.
4. **Documentar:** vistas geradas → arrastar vistas para a folha criada a partir de um modelo de folha (tamanho, carimbo, campos) → cotas e tags na própria vista (não na prancha) → textos e linhas só quando precisa.
5. **Especificar:** tipo com marca (ex.: PAL1, PAL2) e atributos (descrição, dimensões, material) → quadros (áreas, esquadrias, revestimentos, materiais) que leem os valores do tipo.
6. **Detalhar o que não foi modelado:** colocar um item de detalhe 2D configurado (ex.: caibro com descrição, modelo e dimensões) onde falta; **o usuário cria os itens, sem biblioteca pronta**.
7. **Revisar:** nuvem de revisão para indicar o que corrigir; revisões completas depois.

## 3. Decisões (seção 4 do roteiro)
| # | Resposta | Origem |
|---|---|---|
| 1 | A: lista em árvore (navegador) + abas das vistas abertas; organizável pelo usuário | partes 2 e 3 |
| 2 | A: painel fixo; pode dividir o espaço com o navegador por abas | parte 2 |
| 3 | Caixa de ferramentas com favoritos (híbrido) já aprovado; PO confirma atalhos de duas letras (Revit) | parte 3 |
| 4 | A: tipo antes, trocar depois possível | parte 2 |
| 5 | A com B opcional: clica na parede com prévia; digitar a medida quando quiser | parte 2 |
| 6 | A e B: digitar logo depois do primeiro clique ou só mouse | parte 2 |
| 7 | A: arrastar vistas para a folha; vista continua editável | parte 3 |
| 8 | **B, atalhos próprios e trocáveis**, tendo o Revit como ponto de partida, com ajustes sugeridos pelo PO (ver seção 5) | parte 3 |
| 9 | Botão do meio: deslocar e orbitar (modos A/B já no catálogo) + **voar** (WASD + botão direito); duplo clique do meio = enquadrar o visível; roda = zoom | partes 2 e 3 |
| 10 | Abas na 1.0; lado a lado (monitores grandes) depois | parte 2 |
| — | Duplo clique esquerdo "abre uma camada": na parede, abre o tipo/família (editor de tipo) | parte 3 |

## 4. Ferramentas prioritárias (ordem de importância e comportamento)
1. **Parede** com tipo escolhido antes, presa a eixo, prévia, digitar comprimento.
2. **Porta e janela** por clique na parede com prévia do vão.
3. **Níveis e eixos** (parede segue o eixo quando ele muda).
4. **Mover, copiar, girar, espelhar, alinhar, aparar** com atalho de duas letras e a mão no mouse.
5. **Cota alinhada e de nível, que acompanham o desenho** (se a parede muda, a cota muda).
6. **Tags de especificação por atributo** (descrição, marca, material) **sem criar uma família nova por atributo**; numeração de esquadrias automática.
7. **Quadros** (áreas de ambientes e pisos, esquadrias, revestimentos, materiais) com marca de tipo, dimensões, descrição, área, material; no quadro só se filtra, classifica e agrupa; os valores vêm do tipo.
8. **Vistas, cortes e detalhes automáticos** + navegador do projeto que o usuário organiza.

## 5. Atalhos pedidos pelo PO (padrão Revit, com ajustes)
Usa sem pensar: TR (aparar/estender no canto), AL (alinhar), MV (mover), MM (espelhar), RO (girar), CO (copiar), TG (tag), WA (parede). **Sugestões do PO:** mover = **MM**, espelhar = **MI**, girar = **RR**, copiar = **CC** (mais fáceis de teclar). Recomendação: o conjunto final é configurável; o padrão de fábrica segue o PO (TR, AL, MM, MI, RR, CC, TG, WA) e traz também as teclas do Revit como alternativa.

## 6. Anotação (para a F3/F4)
- Cotas: alinhada e de nível; **acompanhar o desenho é indispensável** (reforça F3-S04). Cota na vista, não na folha.
- Tags: por conjunto de famílias (porta, janela, piso), cada uma exibe os atributos configurados; rótulos de especificação são tags.
- Textos: especificações e texto solto; sem modelo de nota reutilizado.
- Detalhes 2D: itens criados pelo usuário; sem biblioteca pronta (alinha com a decisão do PO de 13/10).
- Folha: criada a partir de um **modelo de folha** (tamanho, carimbo, campos); carimbo varia, sempre com autores, vistas atuais, escala, data, revisão.
- Prefeitura: poucas exigências de desenho; mais carimbo e norma local de representação; o executivo exige mais.

## 7. Não pode perder
1. Automação de cortes, vistas e detalhes.
2. Navegador do projeto organizável pelo usuário.
3. Mão no mouse o tempo todo, com atalhos de duas letras.
(Também citados: cota que acompanha, tipo antes de colocar, eixos que seguram paredes, transferir padrões.)

## 8. Dores
1. Desorganização do projeto: informações escondidas, campos de propriedades difíceis de achar.
2. **Elemento que "some" da vista** por escala, filtro, workset ou ocultação (camadas de filtragem): o PO quer saber por quê. Proposta: um botão "Por que não vejo isto?" que lista a regra que esconde o elemento.
3. Tags: uma família nova por atributo consome tempo; automatizar seria útil (não essencial).

## 9. O que abandonaria sem dó
Análises (solar, iluminação, estrutural, energética): podem ser plugins opcionais, fora do núcleo.

## 10. Dúvidas que ficaram
- Mapa final de atalhos (conflitos com letras únicas já propostas no catálogo; as de duas letras têm prioridade).
- Como o usuário organiza o navegador (árvore livre estilo ArchiCAD ou categorias fixas estilo Revit): recomendação, **pastas livres do usuário** com agrupamentos prontos.
- "Por que não vejo isto?": entra na F1 (visibilidade) ou na F3? Recomendação: F1-S05 em versão mínima.
