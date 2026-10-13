<!--
SPDX-License-Identifier: AGPL-3.0-or-later
-->
# Catálogo de ferramentas de anotação e documentação (Fases 3 e 4)

- Autor: agente sonnet (documentação, T1) · Data: 2026-10-13
- Para: Rafael (PO), que vai desenhar o visual à mão a partir deste documento. Continua o catálogo `docs/design/catalogo-ferramentas-f1-f2.md` (mesmo formato; leia a seção "Como ler cada ficha" de lá).
- Base: a ficha `docs/research/2026-10-13-ferramentas-anotacao-revit-archicad-f3-f4.md`, o plano `v2/02` (F3, F4 e §6) e as falas da entrevista da S09 (parte 1: muito tempo em rótulos, tags, textos, chamadas, detalhes, legendas, tabelas e carimbo; prefeitura = simples, executivo = detalhado).
- Estado: **proposta**. Nada aqui vira especificação sem a sua aprovação. Nomes e palavras são nossos. Onde a pesquisa não confirmou um comportamento: **"a confirmar com teste do PO"**.
- Marcas: **[1.0]** obrigatório na 1.0 ("Must" do plano v2/02 §8) · **[talvez 1.0]** "Should": entra se o calendário permitir (o plano põe **revisões** e **detalhes 2D** aí; o pedido do PO é tratá-los como fora da 1.0) · **[fora da 1.0]** sem lugar no plano.

## A regra de ouro desta parte
O arquivo `.ifc` fica limpo. **Cotas, textos, tags, símbolos, quadros, pranchas, carimbos e revisões vivem no arquivo lateral `.obim`**, ao lado do `.ifc`, ligados aos elementos pelo identificador (GlobalId) mais uma âncora geométrica (v2/02 §6). Só o que é dado do edifício vai para o `.ifc`: ambientes, tipos, materiais, números de marca, quantidades. Se um elemento sumir, a cota ou tag ligada a ele **não é apagada**: fica cinza tracejada ("órfã") e entra no painel "Referências quebradas".

Sempre que uma ficha diz **"Altera o modelo? Só o `.obim`"**, o `.ifc` não muda um byte.

---

## 1. O que muda no mapa de tela (continuação da seção 1 do catálogo F1/F2)

### 1.1 Grupo "Anotar" na caixa de ferramentas
Entre "Medir" e os ajustes salvos, a caixa de ferramentas ganha um grupo **Anotar**, só ativo em vistas 2D (planta, corte, fachada):

```
| -- Anotar --        |
| [Cota]  (linear, nível, ...) |
| [Texto]              |
| [Tag]   (categoria, ambiente) |
| [Símbolo]            |
| [Hachura]            |
| [Quadro]  -> painel de tabelas |
| [Nuvem de revisão]   |
| -- Desenho 2D --     |  <- fora da 1.0
| [Linha de detalhe]   |
| [Região preenchida]  |
| [Chamada]            |
```
Na F1/F2 o grupo existe vazio (ou escondido). Em vista 3D ele fica apagado; a barra de estado mostra a escala da vista ("1:50").

### 1.2 Barra de opções
Muda sozinha como as outras. Exemplos: **Cota** → Tipo [linear/alinhada/nível] · Estilo [ v ] · Referência [face / eixo / centro] · [x] Segue o desenho. **Tag** → Estilo [ v ] · [ ] Linha de chamada · Orientação [horizontal/vertical]. **Texto** → Estilo · Tamanho em milímetros no papel · Alinhamento.

### 1.3 Painel de propriedades
Selecionar uma anotação mostra: estilo, texto, referência (a que elemento está ligada) e **estado** ("ligada", "movida", "órfã"). Tamanhos de texto aparecem **em milímetros no papel**, não no desenho.

### 1.4 Navegador do projeto: novos grupos
Abaixo de "Vistas": **Quadros** (áreas, esquadrias, materiais), **Legendas** e **Pranchas** (lista de pranchas, com número e nome). Duplo clique abre o quadro, a legenda ou a prancha. Arrastar uma vista do navegador para a prancha aberta cria o viewport.

### 1.5 Painel de tabelas (novo, em aba ao lado do navegador)
Mostra um quadro em linhas e colunas, com a lista de colunas à direita. Editar uma célula pede confirmação e **altera o elemento no `.ifc`** (ver ficha Q2); quadros de áreas são só leitura na primeira versão. Atalho **Ctrl+4**.

### 1.6 Editor de prancha (novo, abre como aba da área de trabalho)
```
+-----------------------------------------------------------+
| Barra de opções: Formato [A1 v]  Escala padrão [1:50 v]   |
+----------+------------------------------------+-----------+
| Lista de | FOLHA (papel, com carimbo)         | Propri-   |
| vistas e |  +-----------+ +--------+          | edades da |
| quadros  |  | viewport  | | quadro |          | seleção   |
| (arrastar|  +-----------+ +--------+          |           |
|  para a  |                    [carimbo]       |           |
|  folha)  |                                     |           |
+----------+------------------------------------+-----------+
| Barra de estado: dica | posição na folha em mm | escala    |
+-----------------------------------------------------------+
```
Duplo clique no viewport entra na vista para editar (cotas, tags); duplo clique fora volta à folha. Atalho **Ctrl+5** abre a lista de pranchas.

---

## 2. Fichas das ferramentas

Siglas: **Rv** = como o Revit faz; **Ac** = como o ArchiCAD faz (só para reconhecer o fluxo; não copiamos nada).

Índice, por grupo da caixa de ferramentas:

**Base da documentação** (não fica no grupo Anotar): B1 Ambiente · B2 Vistas de planta e corte · B3 Gráfico por categoria e hachuras
**Cotas:** C1 Cota linear e alinhada · C2 Cota de nível · C3 Cota angular e radial · C4 Cota de ponto · C5 Cota que comanda (travada)
**Textos e tags:** T1 Texto · T2 Tag de ambiente · T3 Tag por categoria · T4 Símbolo · T5 Painel de referências quebradas
**Quadros e legendas:** Q1 Quadro de áreas · Q2 Quadro de esquadrias · Q3 Quadro de materiais · Q4 Legenda
**Pranchas:** P1 Prancha e carimbo · P2 Viewport · P3 Exportar PDF · P4 Pacote `.obimpack`
**Revisões:** R1 Revisão e nuvem de revisão
**Desenho 2D (fora da 1.0 por pedido; "Should" no plano):** D1 Linha de detalhe · D2 Região preenchida · D3 Componente de detalhe 2D · D4 Chamada e vista de detalhe

---

### Base da documentação

#### B1. Ambiente (F3-S01) [1.0]
- **O que faz:** cria um ambiente (sala, quarto, banheiro) com nome, número, área, perímetro e pé-direito a partir do fechamento das paredes.
- **Como se usa:**
  1. Ferramenta **Ambiente** (**Alt+A**, ver atalhos), em planta.
  2. Passar o cursor dentro de um espaço fechado: o contorno aparece pré-visualizado.
  3. Clicar: o ambiente é criado. Opção "Etiquetar ao criar" põe a tag de ambiente (T2) junto.
  4. No painel de propriedades: nome, número, categoria (dormitório, cozinha...), pé-direito.
  5. Se o espaço não fecha, a barra de estado diz onde está a brecha.
- **Na tela:** área colorida translúcida sobre o piso, com a área em m² conforme o estilo.
- **Altera o modelo?** **Sim.** Cria um ambiente (`IfcSpace`) no `.ifc`, com área e perímetro como quantidades. A cor e o texto exibidos ficam no `.obim`.
- **Entra em:** F3-S01.
- **Comparação e proposta:** Rv cria o ambiente por clique dentro do espaço fechado e mantém "ambiente" e "tag" separados; Ac chama de "zona", com categoria que define cor e etiqueta. **Proposta:** clique dentro, categorias com cor (do pacote Brasil), tag separada. **Recomendação:** adotar. Aceite: áreas conferem com o cálculo manual do PO (±0,01 m²).

#### B2. Vistas de planta e corte (F3-S02) [1.0]
- **O que faz:** gera planta e corte a partir do modelo, como vistas salvas.
- **Como se usa:** (1) planta: duplo clique no pavimento no navegador cria/abre a planta; (2) corte: ferramenta de corte, dois cliques para a linha e um clique para a direção de olhar; (3) propriedades da vista: escala, alcance (altura do plano de corte da planta), profundidade.
- **Na tela:** a vista em linhas (projeção "limpa", sem renderização), o marcador do corte na planta com bolha e letra.
- **Altera o modelo?** Só o `.obim` (a vista salva). O `.ifc` não muda.
- **Entra em:** F3-S02 (planta, corte). Fachadas e cortes múltiplos: F4.
- **Comparação e proposta:** Rv e Ac fazem plano de corte com alcance configurável. **Proposta:** alcance simples (altura do corte, abaixo, acima). **Recomendação:** adotar. Aceite: PO compara com prancha de referência.

#### B3. Gráfico por categoria e hachuras (F3-S03) [1.0]
- **O que faz:** define como cada categoria se desenha: espessura de linha cortado/visto, hachura por material, em 3 escalas.
- **Como se usa:** menu Vista > Gráfico por categoria; tabela de categorias (parede, laje, porta...) com colunas: linha cortada, linha vista, hachura, cor. Ajustes por vista ou por modelo de vista. "Aplicar à vista" grava.
- **Na tela:** janela com tabela e pré-visualização em escala.
- **Altera o modelo?** Só o `.obim`.
- **Entra em:** F3-S03 (modelo brasileiro de vistas). PO aprova visualmente em 1:50, 1:100 e 1:200.
- **Comparação e proposta:** Rv: visibilidade e gráficos por categoria; Ac: sobreposições gráficas com regras. **Proposta:** tabela de categorias (simples) mais regras por propriedade já existentes (V12). **Recomendação:** adotar. Os "modelos de vista" que o PO transfere entre projetos vêm daqui: ver decisão 5.

---

### Cotas

#### C1. Cota linear e alinhada (F3-S04) [1.0]
- **O que faz:** mede uma distância entre dois pontos de referência e escreve o valor, e **segue o desenho** quando o elemento muda.
- **Como se usa:**
  1. Tecla **Alt+C** (ou botão Cota). Barra de opções: tipo "Linear" (horizontal/vertical) ou "Alinhada" (paralela ao elemento).
  2. Clicar o primeiro ponto de referência (face de parede, eixo, centro de porta, pilar); o marcador de captura mostra o que será referenciado.
  3. Clicar o segundo; o programa pode seguir com mais cliques para cota em cadeia.
  4. Mover o mouse para afastar a linha da cota; clicar para fixar.
  5. **Esc** termina. Clicar no número permite substituir por texto (o valor automático continua guardado).
- **Na tela:** linhas de chamada, linha de cota com marcas nas pontas e texto no tamanho de papel. Em vista salva, escala muda → tamanho no papel fica igual.
- **Altera o modelo?** Só o `.obim`: guarda o GlobalId, a âncora (ex.: "face de acabamento externa") e a última posição. **Mover a parede atualiza a cota** (aceite F3-S04). Se a âncora não for achada, a cota fica cinza tracejada.
- **Entra em:** F3-S04.
- **Comparação e proposta:** Rv: cotas permanentes lineares, com opção de alinhada; o cadeado cria restrição (ver C5). Ac: linear associativa; a associação depende do tipo de ponto de referência. **Proposta:** associativa por padrão, sem cadeado nesta fase; "cadeia" e "igualdade em partes" ficam para depois. **Recomendação:** adotar. **A confirmar com teste do PO:** quais referências ele cota mais (eixo, face de acabamento, face estrutural).

#### C2. Cota de nível (F3-S04) [1.0]
- **O que faz:** escreve a altura de um nível ou de um ponto (piso acabado, topo de laje) em corte, fachada e planta.
- **Como se usa:** **Alt+C**, tipo "Nível"; clicar a linha de nível (ou ponto no corte), mover para o lado e clicar; "Origem" escolhe o zero (nível 0,00 da obra ou altitude).
- **Na tela:** símbolo de nível (triângulo e linha) com a altura em metros, duas casas.
- **Altera o modelo?** Só o `.obim`. O valor segue o nível: **mudar a cota do nível (M3) atualiza a cota de nível**. Mudar o valor na própria cota **não** move o nível.
- **Entra em:** F3-S04 (nível). Cota de ponto e inclinação: C4 (F4).
- **Comparação e proposta:** Ac separa "elevação" (corte, fachada) de "nível" (planta). Rv usa a cota de ponto para os dois. **Proposta:** um tipo só, "Nível", que funciona em planta e corte. **Recomendação:** adotar, sem separar.

#### C3. Cota angular e radial (F4) [1.0, mas depois da F3]
- **O que faz:** mede o ângulo entre duas linhas e o raio de um arco.
- **Como se usa:** **Alt+C**, tipo "Angular" ou "Radial"; clicar as duas linhas (ou o arco), mover e clicar.
- **Na tela:** arco de ângulo com valor em graus; seta de raio com "R".
- **Altera o modelo?** Só o `.obim`.
- **Entra em:** F4 (o plano F3 só cita cotas lineares e de nível). **Recomendação:** adiar para o fim da F3 ou F4; em casa residencial é pouco usada: **a confirmar com teste do PO**.
- **Comparação:** Rv e Ac têm as duas. **Proposta:** só depois.

#### C4. Cota de ponto: elevação, coordenada, inclinação (F4) [1.0 em elevação; resto fora]
- **O que faz:** marca altura (e depois coordenada e inclinação) de um ponto de uma superfície.
- **Como se usa:** **Alt+C**, tipo "Ponto"; clicar o ponto; mover e clicar. Para inclinação (telhado, rampa): **a confirmar com teste do PO**.
- **Na tela:** marcador + valor. **Altera o modelo?** Só o `.obim`.
- **Entra em:** F4 (elevação junto com telhado/escada). Coordenada e inclinação: sem fatia; **fora da 1.0** a menos que o PO peça.
- **Comparação e proposta:** Rv tem as três em estilos próprios; Ac usa a de nível/elevação. **Recomendação:** só elevação.

#### C5. Cota que comanda: travada (sem fatia) [fora da 1.0]
- **O que faz:** quando você digita um valor numa cota travada, o desenho se move para respeitar.
- **Como se usa:** (como no Revit) cadeado na cota; destravar, digitar o valor novo, o elemento move.
- **Altera o modelo?** **Sim** (o `.ifc`: a parede muda de lugar) e cria uma regra no `.obim`. É a ficha que mais **aumenta o risco**: pode ficar "restrição demais" e travar o projeto.
- **Entra em:** nenhuma fatia do plano. **Proposta:** **não fazer na 1.0**. O PO já tem "eixo que segura parede" (F2-S03) como forma de restrição. Ver decisão 4.

---

### Textos e tags

#### T1. Texto (F4) [1.0]
- **O que faz:** escreve uma nota na vista, com ou sem linha de chamada.
- **Como se usa:** **Alt+T**; clicar o ponto (com chamada: clicar a ponta da seta e depois o texto); digitar; **Enter** em linha em branco ou clique fora termina.
- **Na tela:** caixa de texto no tamanho de papel (ex.: 2,5 mm, 3,5 mm); estilos prontos ("nota", "título de vista", "especificação") do pacote Brasil. Barra: estilo, alinhamento, [ ] chamada.
- **Altera o modelo?** Só o `.obim`. Se o texto citar campo ("área", "marca") o valor vem do elemento.
- **Entra em:** F4 (o plano F3 não inclui texto livre). **Recomendação:** subir um mínimo de texto para a F3, porque a planta legal e o quadro precisam de títulos e notas. Ver decisão 3.
- **Comparação e proposta:** Rv: nota de texto com linha opcional, tamanho por escala; Ac: blocos de texto formatáveis e rótulos. **Proposta:** estilos de texto em mm no papel.

#### T2. Tag de ambiente (F3-S04) [1.0]
- **O que faz:** escreve nome, número e área do ambiente na planta.
- **Como se usa:** **Alt+R**, tipo "Ambiente"; clicar dentro do ambiente; a tag aparece no centro, arrastar para deslocar. Opção "Etiquetar todos".
- **Na tela:** texto em duas ou três linhas (nome, área). Estilo "prefeitura" mostra só nome e área; estilo "executivo" soma pé-direito e revestimento (pacote Brasil).
- **Altera o modelo?** Só o `.obim`. O conteúdo vem do ambiente no `.ifc`; renomear o ambiente (painel ou quadro) atualiza as tags.
- **Entra em:** F3-S04.
- **Comparação e proposta:** Rv: tag de ambiente com número, nome, área e volume, igual no quadro; Ac: etiqueta de zona, cuja aparência vem da categoria. **Proposta:** estilos por categoria, como o Ac; edição do nome pelo painel, como o Rv. **Recomendação:** adotar.

#### T3. Tag por categoria (F4) [1.0]
- **O que faz:** escreve a identificação de um elemento (marca da porta, tipo da janela).
- **Como se usa:** **Alt+R**, tipo "Por categoria"; clicar o elemento; a tag da categoria certa entra; opção "Etiquetar todos da vista". Barra: [ ] linha de chamada (presa ou livre), horizontal/vertical.
- **Na tela:** bolha ou texto pequeno; o campo vem do elemento (marca, tipo, largura × altura).
- **Altera o modelo?** A tag, não. **A marca (ex.: P1, J3) é dado do elemento:** quando criada ou renumerada, **muda o `.ifc`**. Renumerar automático por ordem na planta: opção.
- **Entra em:** F4 (junto com o quadro de esquadrias).
- **Comparação e proposta:** Rv numera pela "marca"; Ac usa rótulos associativos (detalhe: **a confirmar com teste do PO**). **Recomendação:** adotar o fluxo do Rv; lembrar que a marca é o elo com o quadro Q2.

#### T4. Símbolo (F4) [1.0]
- **O que faz:** coloca um símbolo gráfico (seta de norte, indicação de sentido, bolha de eixo, símbolo de acessibilidade) na vista.
- **Como se usa:** **Alt+S**; escolher na lista de símbolos; clicar para posicionar; **Espaço** gira 90°.
- **Na tela:** símbolo vetorial, nosso, no tamanho de papel; rotação e escala no painel.
- **Altera o modelo?** Só o `.obim`.
- **Entra em:** F4. Biblioteca própria de símbolos (desenhada por nós, sem copiar os de outros programas).
- **Comparação e proposta:** Rv: símbolos de anotação; Ac: salvar 2D como objeto. **Proposta:** biblioteca fixa na 1.0; criar símbolos próprios é depois.

#### T5. Painel de referências quebradas (F4) [1.0]
- **O que faz:** lista as cotas e tags que perderam a referência e deixa religar.
- **Como se usa:** abre sozinho ao abrir o projeto se houver órfãs (contagem por vista e por prancha); selecionar mostra a anotação; "Religar" pede clicar o novo elemento; "Manter órfã" marca como resolvida sem religar.
- **Na tela:** lista em painel lateral; anotação órfã cinza tracejada na vista.
- **Altera o modelo?** Só o `.obim`. Nunca apaga em silêncio.
- **Entra em:** F4 (v2/02 §6.3). Como as cotas entram na F3, **recomendamos adiantar a versão mínima** (só contagem e lista) para a F3. Ver decisão 6.
- **Comparação:** os dois reclamam quando o elemento some, de formas diferentes; nossa regra é a de v2/02.

---

### Quadros e legendas

#### Q1. Quadro de áreas (F3-S07) [1.0]
- **O que faz:** monta o quadro de áreas dos ambientes (e totais) e o coloca na prancha.
- **Como se usa:** menu Documentar > Novo quadro > "Áreas"; escolher colunas (número, nome, área, pé-direito), agrupar por pavimento ou categoria, ligar totais; arrastar o quadro do navegador para a prancha.
- **Na tela:** painel de tabelas (ver 1.5) e, na prancha, uma tabela vetorial.
- **Altera o modelo?** Ler: não. Mudar um nome ou número direto no quadro **altera o ambiente no `.ifc`**; na primeira versão o quadro é **só leitura**.
- **Entra em:** F3-S07. Aceite: igual ao cálculo manual do PO. O quadro legal brasileiro (áreas computáveis, taxa de ocupação, etc.): pacote Brasil; **textos da norma não entram**, só as colunas.
- **Comparação e proposta:** Rv e Ac fazem tabelas ligadas ao modelo, editáveis. **Recomendação:** só leitura na 1.0; edição na F4.

#### Q2. Quadro de esquadrias (F4) [1.0]
- **O que faz:** lista portas e janelas (marca, tipo, largura, altura, peitoril, quantidade).
- **Como se usa:** como Q1, tipo "Esquadrias"; ordenar por marca; separar portas e janelas; colocar na prancha.
- **Altera o modelo?** Ler: não. Editar uma célula **altera o `.ifc`** (tipo ou parâmetro da instância; mudar tipo muda todos do tipo; avisar quantos).
- **Entra em:** F4. **Comparação:** Rv e Ac: edição direta; o PO usa propriedades de especificação (marca, modelo, link, preço) no executivo, que são colunas daqui.
- **Proposta:** adotar, com aviso antes de editar.

#### Q3. Quadro de materiais (F4) [1.0]
- **O que faz:** soma quantidades por material ou por tipo (m², m³, unidades).
- **Como se usa:** como Q1, tipo "Materiais"; escolher agrupamento (por material, por pavimento).
- **Altera o modelo?** Não (só leitura).
- **Entra em:** F4 (depende das quantidades automáticas, também F4). **Proposta:** adotar.

#### Q4. Legenda (F4) [1.0]
- **O que faz:** monta uma vista de legenda (convenções de hachura, símbolos, tipos de porta) para a prancha.
- **Como se usa:** menu Documentar > Nova legenda; arrastar amostras de hachura, símbolos e tipos da lista; digitar o texto de cada uma; colocar na prancha.
- **Na tela:** vista em branco com os itens; amostras **não contam** nas quantidades do modelo.
- **Altera o modelo?** Só o `.obim`. **Entra em:** F4. **Comparação:** Rv tem vista de legenda; Ac: a confirmar com teste do PO. **Proposta:** adotar, só com itens do projeto.

---

### Pranchas

#### P1. Prancha e carimbo (F3-S05) [1.0]
- **O que faz:** cria uma folha A0 a A4 com carimbo (moldura e dados do projeto).
- **Como se usa:** (1) clicar "Nova prancha"; (2) formato, orientação e carimbo (modelo do pacote Brasil); (3) preencher número, nome, autor, data nos campos do carimbo; (4) a lista de pranchas vive no navegador.
- **Na tela:** a folha em escala real de papel, com margens. O carimbo é editável em um editor próprio (campos, logotipo do escritório). Campos podem vir do projeto (nome da obra, endereço, responsável).
- **Altera o modelo?** Só o `.obim` (`sheets/<id>.json`, `titleblocks/*`).
- **Entra em:** F3-S05. Aceite: montar uma prancha em até 15 minutos.
- **Comparação e proposta:** Rv: folha com carimbo (família); Ac: Livro de layouts com layout mestre. **Proposta:** carimbo como modelo que se escolhe e edita; "layout mestre" nosso nome: "modelo de prancha". **Recomendação:** adotar. **A confirmar com teste do PO:** quais campos do carimbo a prefeitura da cidade dele exige a mais.

#### P2. Viewport: vista na prancha (F3-S05) [1.0]
- **O que faz:** coloca uma vista (planta, corte, quadro, legenda) na prancha, com escala e título.
- **Como se usa:** arrastar a vista do navegador para a folha (um clique solta); arrastar o viewport move; no painel: escala, título, [ ] mostrar linha de título; duplo clique entra na vista (cotas e tags editáveis); duplo clique fora volta.
- **Na tela:** retângulo da vista com título ("PLANTA TÉRREO — 1:50"); o enquadramento (o que aparece) se ajusta pelas alças. Mudar a escala altera o tamanho de papel do desenho, **não** o tamanho do texto no papel.
- **Altera o modelo?** Só o `.obim`.
- **Entra em:** F3-S05. **Comparação:** Rv: escala vem da vista (a mesma vista só entra em uma prancha); Ac: o desenho é uma cópia da vista na prancha. **Proposta:** como o Rv (uma vista, uma prancha) na primeira versão; **a confirmar com teste do PO** se ele precisa da mesma planta em duas pranchas.

#### P3. Exportar PDF (F3-S06) [1.0]
- **O que faz:** gera o PDF vetorial de uma prancha ou de todas.
- **Como se usa:** **Ctrl+P**; escolher pranchas, formato de papel, "tudo em um arquivo" ou um por prancha; **Exportar**. Barra de progresso no rodapé.
- **Altera o modelo?** Não. **Entra em:** F3-S06. Aceite: imprime em A1 com as espessuras certas (conferir com régua).
- **Comparação e proposta:** os dois exportam PDF vetorial. **Proposta:** só PDF na 1.0; DXF na F4.

#### P4. Pacote `.obimpack` (F3-S05) [1.0]
- **O que faz:** junta `.ifc`, `.obim` e carimbos num arquivo único para enviar.
- **Como se usa:** Arquivo > Exportar pacote; abrir o pacote em outra máquina e ver a mesma coisa.
- **Altera o modelo?** Não. **Entra em:** F3-S05. **Comparação:** Rv e Ac têm pacote próprio. **Proposta:** adotar. Um colega com Revit ou ArchiCAD recebe só o `.ifc` mais PDFs.

---

### Revisões

#### R1. Revisão e nuvem de revisão (F4) [1.0 só a nuvem de revisão; revisões completas depois, decisão do PO 2026-10-13]
- **O que faz:** registra as mudanças entre emissões e marca as áreas alteradas na vista.
- **Como se usa:**
  1. Menu Documentar > Revisões: criar "Revisão A", data, descrição.
  2. Ferramenta **Nuvem de revisão** (**Alt+N**): clicar os pontos do contorno; **Enter** fecha; escolher a revisão.
  3. A tabela de revisões do carimbo lista sozinha as revisões das nuvens daquela prancha.
  4. Ao emitir, a revisão anterior fica travada (só a última edita).
- **Na tela:** nuvem de arcos em volta da área; tabela no carimbo.
- **Altera o modelo?** Só o `.obim` (`revisions.json`).
- **Entra em:** F4. No plano (v2/02 §8) "revisões" está na coluna "Should" da 1.0, ou seja, só se o calendário permitir. Pede decisão: ver decisão 2.
- **Comparação e proposta:** Rv: revisões com nuvens e tabela no carimbo; Ac: mudanças ligadas a elementos, que numeram sozinhas as pranchas afetadas. **Proposta:** modelo do Rv (nuvem manual), mais simples; ligar a elementos fica para depois.

---

### Desenho 2D [pedido do PO: fora da 1.0; no plano v2/02 §8 é "Should"]

Em todos os quatro, o `.ifc` não muda; vive no `.obim` dentro da vista. O PO diz que no projeto executivo "o que não se modela vira detalhe de anotação": por isso estas fichas existem, e a decisão 1 pergunta se sobem.

#### D1. Linha de detalhe [1.0, decisão do PO 2026-10-13]
- **O que faz:** desenha linhas e polilinhas 2D soltas na vista (para detalhar o que o modelo não tem).
- **Como se usa:** **Alt+L**; estilo de linha (cheia, tracejada, traço e ponto) e espessura; clicar os pontos; **Enter** termina. Capturas nos pontos do modelo (como M13).
- **Altera o modelo?** Não. Só a vista. **Comparação:** Rv e Ac têm; o Rv ainda permite deixar o modelo em meio-tom. **Proposta:** com os mesmos snaps do modelo.

#### D2. Região preenchida (hachura manual) [1.0, decisão do PO 2026-10-13]
- **O que faz:** desenha uma área 2D com contorno e padrão (concreto, terra, brita).
- **Como se usa:** **Alt+H**; escolher padrão; desenhar o contorno por cliques; **Enter** fecha; contorno pode ficar invisível.
- **Na tela:** padrão de **desenho** (acompanha a escala da vista) ou de **modelo** (medida real): opção na barra.
- **Altera o modelo?** Não. **Comparação:** os dois têm, com categorias de hachura. Nota: as hachuras **automáticas por material** (B3) estão na F3 e **não** dependem desta.

#### D3. Componente de detalhe 2D [1.0, decisão do PO 2026-10-13]
- **O que faz:** coloca um elemento 2D de uma biblioteca (peça de fixação, perfil, manta) para montar detalhes.
- **Como se usa:** pelo botão (sem tecla); escolher na lista, clicar para posicionar; **Espaço** gira 90°; há também repetição em fila.
- **Altera o modelo?** Não. **Comparação:** Rv tem componentes de detalhe e repetição; Ac guarda símbolos 2D. **Proposta:** depende de uma **biblioteca** (desenhada por nós ou pelo PO). Sem biblioteca, a ferramenta é vazia.

#### D4. Chamada e vista de detalhe [depois da 1.0, decisão do PO 2026-10-13]
- **O que faz:** marca uma região na planta ou no corte e abre uma vista ampliada (1:20, 1:10) onde se desenha e se anota.
- **Como se usa:** **Alt+Q**; clicar dois cantos do retângulo; a bolha aparece com número; duplo clique na bolha abre a vista de detalhe; na prancha a bolha mostra "detalhe/prancha".
- **Altera o modelo?** Não. Só o `.obim`. **Comparação:** Rv: a chamada cria vista com anotações de detalhe; Ac: detalhe é só 2D e por padrão não traz cotas e anotações; ao refazer, o que foi desenhado à mão precisa ser refeito (**risco** para nós também). **Proposta:** a vista de detalhe é "recorte ampliado do modelo + camada 2D por cima"; regenerar não apaga a camada 2D.

---

## 3. Tabela resumo

"Altera o modelo?" = muda o `.ifc`. "Só o `.obim`" = documentação. "Não" = nada gravado.

| # | Ferramenta | Tecla | Fatia | 1.0? | Altera o modelo? |
|---|---|---|---|---|---|
| B1 | Ambiente | Alt+A | F3-S01 | Sim | **Sim** (`IfcSpace`) |
| B2 | Vistas de planta e corte | menu | F3-S02 | Sim | Só o `.obim` |
| B3 | Gráfico por categoria e hachuras | menu | F3-S03 | Sim | Só o `.obim` |
| C1 | Cota linear e alinhada | Alt+C | F3-S04 | Sim | Só o `.obim` |
| C2 | Cota de nível | Alt+C | F3-S04 | Sim | Só o `.obim` |
| C3 | Cota angular e radial | Alt+C | F4 | Depois da F3 | Só o `.obim` |
| C4 | Cota de ponto | Alt+C | F4 | Só elevação | Só o `.obim` |
| C5 | Cota que comanda (travada) | (cadeado) | nenhuma | **Fora** | **Sim** |
| T1 | Texto | Alt+T | F4 (pedimos F3) | Sim | Só o `.obim` |
| T2 | Tag de ambiente | Alt+R | F3-S04 | Sim | Só o `.obim` |
| T3 | Tag por categoria | Alt+R | F4 | Sim | A marca: **Sim**; a tag: `.obim` |
| T4 | Símbolo | Alt+S | F4 | Sim | Só o `.obim` |
| T5 | Referências quebradas | painel | F4 (versão mínima na F3) | Sim | Só o `.obim` |
| Q1 | Quadro de áreas | menu, Ctrl+4 | F3-S07 | Sim | Não (só leitura) |
| Q2 | Quadro de esquadrias | menu, Ctrl+4 | F4 | Sim | Editar: **Sim** |
| Q3 | Quadro de materiais | menu, Ctrl+4 | F4 | Sim | Não |
| Q4 | Legenda | menu | F4 | Sim | Só o `.obim` |
| P1 | Prancha e carimbo | Ctrl+5 | F3-S05 | Sim | Só o `.obim` |
| P2 | Viewport | arrastar | F3-S05 | Sim | Só o `.obim` |
| P3 | Exportar PDF | Ctrl+P | F3-S06 | Sim | Não |
| P4 | Pacote `.obimpack` | menu | F3-S05 | Sim | Não |
| R1 | Revisão e nuvem | Alt+N | F4 | Talvez (Should) | Só o `.obim` |
| D1 | Linha de detalhe | Alt+L | F4+ | Fora (pedido) / Should | Só o `.obim` |
| D2 | Região preenchida | Alt+H | F4+ | Fora (pedido) / Should | Só o `.obim` |
| D3 | Componente de detalhe 2D | botão | F4+ | Fora (pedido) / Should | Só o `.obim` |
| D4 | Chamada e vista de detalhe | Alt+Q | F4+ | Fora (pedido) / Should | Só o `.obim` |

Total: 26 fichas (3 de base, 5 de cotas, 5 de textos e tags, 4 de quadros e legendas, 4 de pranchas, 1 de revisão, 4 de desenho 2D). Pelo plano v2/02, C3, C4, T1, T3, T4, T5, Q2, Q3, Q4 e R1 são F4, e D1 a D4 são "detalhes" da F4 ("Should").

### Atalhos de teclado propostos para anotações
As letras soltas dos catálogos F1/F2 (S Z H I B Q R N E P L K V D J M C G F A T) **continuam como estão**. Para não colidir, as anotações usam **Alt + letra**, só em vista 2D. Combinações novas: Ctrl+4, Ctrl+5, Ctrl+P. Nenhuma repete as do catálogo F1/F2 (Ctrl+1, 2, 3, E, S, N, O, Z, Y). Atenção: Alt+letra também é usado pelos menus em alguns sistemas; nossos menus **não** terão letra sublinhada de acesso, para evitar conflito.

| Tecla | Faz | Observação |
|---|---|---|
| Alt+C | Cota | o tipo (linear, nível...) se troca na barra de opções |
| Alt+T | Texto | |
| Alt+R | Tag (ambiente ou por categoria) | |
| Alt+S | Símbolo | |
| Alt+A | Ambiente | |
| Alt+N | Nuvem de revisão | [A decidir] |
| Alt+L / Alt+H / Alt+Q | Linha de detalhe / Região preenchida / Chamada | [fora da 1.0] |
| Ctrl+4 | Painel de tabelas | |
| Ctrl+5 | Lista de pranchas | |
| Ctrl+P | Exportar PDF | |
| Espaço | Gira 90° o símbolo ou o componente | igual ao catálogo F1/F2 |
| Enter / Esc | Conclui / cancela | regras gerais |

Conferido: nenhuma combinação se repete; Alt+C, Alt+A e Alt+L não têm conflito conhecido com os menus do programa, mas a conferência final depende do desenho dos menus.

---

## 4. Decisões para o PO

Se concordar com tudo, basta responder "de acordo".

**1. Detalhes 2D (linha, região preenchida, componente, chamada) entram na 1.0?**
O plano v2/02 lista como "Should" (só se o calendário permitir) e você pediu tratar como fora, mas você disse que no executivo "o que não se modela vira detalhe". Sem eles, a prancha de detalhe sai com outro programa.
Recomendação: **manter fora da 1.0, mas subir um mínimo**: linha de detalhe, região preenchida e texto, em vista de **corte e planta já geradas** (D1, D2 e T1), sem chamada e sem biblioteca de componentes. Cobre a maior parte do detalhe de obra residencial e custa menos que D3 e D4. Chamada e componentes ficam para depois da 1.0.

**2. Revisões e nuvem de revisão entram na 1.0?**
O plano as põe na F4 e como "Should" da 1.0; você disse que o executivo "tem revisões".
Recomendação: **adiar para depois da 1.0** e, enquanto isso, o carimbo tem um campo livre "revisão" (letra e data) editável à mão. Sem nuvem automática.

**3. Texto livre sobe para a F3?**
O plano põe "textos/tags/símbolos" na F4, mas a planta legal precisa de títulos e notas.
Recomendação: **sim, só texto simples (T1) vai para a F3** (junto da tag de ambiente). Tags por categoria e símbolos ficam na F4.

**4. Cota que comanda (cadeado) fica de fora?**
Move paredes ao digitar o valor da cota; é potente, mas arriscado, e o eixo que segura a parede (F2-S03) já cobre a maior parte.
Recomendação: **fora da 1.0**. A cota só mostra e segue o desenho.

**5. Transferir padrões entre projetos (modelos de vista, estilos de linha, estilos de texto, carimbos) entra quando?**
Você diz que reaproveita muito por transferência de padrões. Neste catálogo ficam no `.obim` (modelos de vista em B3; carimbos em P1; estilos de texto em T1).
Recomendação: **na F3, "importar padrões de outro projeto" (vistas, estilos, carimbo) como uma única ação**, depois da primeira prancha pronta; sem sincronização contínua.

**6. Referências quebradas: adiantar a versão mínima para a F3?**
O plano põe o painel na F4, mas as cotas já nascem na F3 e podem ficar órfãs.
Recomendação: **adiantar uma versão mínima** (lista e contagem; religar fica para a F4).

### Testes que o PO pode fazer para confirmar o que a ficha não confirmou
No Revit (e no ArchiCAD, se quiser), com modelo próprio (nada vai para o repositório):
1. Cota alinhada contra linear: quais você usa mais? Elas mudam sozinhas quando a parede se move?
2. Cota de nível em planta, corte e fachada: onde você põe a origem (zero da obra ou altitude)?
3. Tag de porta e janela: a marca é digitada à mão ou numerada sozinha? Renumerar muda o quadro de esquadrias?
4. Quadro de esquadrias: quais colunas você usa de verdade (marca, tipo, medidas, peitoril, especificação)? Você edita pelo quadro?
5. Prancha de prefeitura contra a de executivo: o que a prefeitura exige a mais no carimbo, nas cotas e no quadro de áreas?
6. A mesma planta em duas pranchas: você precisa?
7. Detalhe: o que você desenha em 2D por cima do modelo no executivo? (linhas, hachuras, textos, componentes? quantos por casa?)
8. Revisão: você usa nuvem de revisão ou só a letra no carimbo?
