# ADR-009: Licenças e política de conteúdo
- Status: **aceito** (aprovado pelo PO no chat em 2026-10-10) · Autor: opus, lote 1 · Data: 2026-10-10 · Cartão: F0-S01-T12
- Base: revisão da tabela mestre (`docs/research/2026-10-10-licencas-revisao-opus.md`), fichas dos grupos A a D, ficha do SINAPI, `v2/05` §3 e §4.
- **Não é parecer jurídico.** É a regra de trabalho do projeto, escrita por quem não é advogado. Antes de publicar conteúdo ou pacote sobre o qual reste dúvida, consultar advogado de propriedade intelectual (`v2/05`).
- Aviso de processo: a tabela mestre foi **reprovada** na revisão por defeitos de redação e cobertura. Este ADR usa as respostas da revisão, não a tabela; a correção da tabela não muda nenhuma decisão daqui.

## 1. Contexto
O OpenBIM Studio é um programa de mesa, aberto, para Windows e Linux. O núcleo é geral, sem país; o Brasil é o primeiro pacote regional (decisão do PO de 2026-10-10). O programa se apoia em bibliotecas grandes de terceiros (IfcOpenShell, Open CASCADE, Qt/PySide6) e vai lidar com conteúdo brasileiro que tem dono (normas ABNT, NBR 15965, layers AsBEA, SINAPI, TCPO). Precisamos de três coisas: a licença do nosso código, uma regra para aceitar ou recusar código e ferramentas de terceiros, e uma regra para conteúdo. E precisamos de um jeito automático de fiscalizar, porque o PO não lê código.

## 2. Opções consideradas
| Tema | Opções | Escolha |
|---|---|---|
| Licença do código | AGPL-3.0-only · **AGPL-3.0-or-later** · GPL-3 · permissiva (MIT/Apache) | AGPL-3.0-or-later, **já decidida pelo PO** |
| Bibliotecas com licença ambígua | aceitar a leitura mais provável · **deixar fora até resolver** | Deixar fora |
| Conteúdo de normas e bases | embutir valores e tabelas · **mecanismo configurável + arquivo do usuário** | Mecanismo configurável |
| Fiscalização | revisão manual · **automática no CI (REUSE/SPDX + inventário)** | Automática, com revisão humana só no que a máquina não vê |

## 3. Números medidos
Este ADR não depende de medição de desempenho. Os números são de contagem (fichas de 2026-10-10):
- 26 componentes avaliados em 24 linhas da tabela mestre. **Nenhum incompatível** com a AGPL v3.
- 4 pendências levadas ao opus, 4 respondidas (seção 5). Resultado: 1 "sim, com condição" (OCCT), 2 "fora por decisão" (libdxfrw, WiX), 1 "pode, com condição" (conda-forge).
- 6 itens seguem não verificados e não bloqueiam a F0 (seção 9).
- Inventário das dependências indiretas: **0% feito**; meta de 100% na S02 (seção 7).

## 4. Decisão

### 4.1 Licença do projeto
1. Todo o código do projeto é **AGPL-3.0-or-later**. Cada arquivo leva a etiqueta SPDX de licença `AGPL-3.0-or-later` (no cabeçalho ou no `REUSE.toml`).
2. O programa montado (instalador, AppImage) inclui bibliotecas que são "somente versão 3" (por exemplo PySide6). Por isso o **conjunto distribuído vale, hoje, sob a versão 3**. O "ou posterior" protege o nosso código para o futuro; não muda a licença de ninguém.
3. A tela "Sobre" mostra a licença, o endereço do código-fonte e a lista de bibliotecas de terceiros.
4. Não há dupla licença comercial. (Isso também mantém o projeto elegível à assinatura gratuita da SignPath, `v2/02` §12.)
5. Ficam para decisão do PO, sem bloquear a F0: licença do esquema do arquivo `.obim` e dos modelos de projeto (seção 10, pergunta 1) e a forma de aceitar contribuições de terceiros.

### 4.2 Regras de compatibilidade
A regra depende de **como** a coisa entra no projeto:

| Como entra | Pode | Não pode | Condição |
|---|---|---|---|
| **Código copiado** para os nossos arquivos | MIT, BSD, ISC, Apache-2.0, BSL-1.0, MPL-2.0, LGPL-2.1-or-later, LGPL-3, GPL-3, AGPL-3 | GPL-2.0-only, LGPL-2.1-only, sem licença, proprietário, licença ambígua | Comentário com origem, licença e commit; registro em `THIRD_PARTY.md`; arquivo MPL continua MPL |
| **Biblioteca ligada** ao programa | As de cima e também **LGPL-2.1-only** (caso OCCT) | GPL-2.0-only, proprietário, SDK fechado (ODA, RealDWG) | LGPL: seção 5.3. GPL-3: combinação pela seção 13; a parte GPL continua GPL-3 |
| **Ferramenta** de build ou de empacotamento | Qualquer licença de código aberto cujo resultado não fique preso a ela | Ferramenta com taxa, termo de uso restritivo ou custo sem ok do PO | Levar o aviso de licença do trecho da ferramenta que vai dentro do pacote |
| **Programa externo** chamado pelo usuário (ex.: conversor de DWG) | Qualquer um que o usuário instale por conta própria | Empacotar junto sem passar pela linha "biblioteca" | Não distribuímos; só chamamos |
| **Dados, ícones, fontes** | CC0, CC-BY (com atribuição), licenças abertas de fonte | CC-BY-NC, CC-BY-ND, material de associação ou editora, cópias de outros programas | Origem e licença declaradas por arquivo |

Regras gerais:
1. **Ambíguo é "não"** até uma revisão opus resolver. O líder e o implementador não resolvem dúvida de licença sozinhos.
2. Toda dependência nova entra por ficha em `docs/research/` e por linha na tabela mestre **antes** do código.
3. A licença é reconferida no arquivo de licença **da versão travada**, não da versão mais recente.
4. Só o canal conda-forge. O canal `defaults` da Anaconda é proibido.
5. Preferimos biblioteca compartilhada (arquivo separado) a ligação estática, sempre.

### 4.3 Política de conteúdo (núcleo geral, pacotes regionais)
Princípio: **o núcleo não contém conteúdo de país nenhum.** Formatos de folha, carimbos, espessuras, regras de verificação, classificações e bases de custo vivem em pacotes regionais. O pacote Brasil é o primeiro. Todo arquivo de conteúdo de um pacote regional declara origem e licença.

| Conteúdo | O que fazemos | O que não fazemos |
|---|---|---|
| **Normas ABNT** | Mecanismos configuráveis. Os valores padrão do pacote Brasil são escolhas do projeto, descritas como "prática corrente", ou digitados pelo usuário a partir da norma que ele possui. Citar o número da norma é permitido | Copiar texto, tabela ou figura, inclusive em código, testes, documentação e mensagens de agentes. Distribuir PDF. Dizer "conforme ABNT" ou "certificado" |
| **NBR 15965** | Suporte a qualquer classificação carregada de arquivo do usuário | Embutir as tabelas. A planilha pública da CAIXA (SINAPI × NBR 15965) só entra depois de lidos os termos |
| **Layers AsBEA** | Mapa de layers configurável, com modelo padrão de nomes próprios; o usuário importa o mapa dele | Distribuir manual, arquivo ou a lista de nomes da AsBEA |
| **SINAPI** | Importar a planilha que o usuário baixou; guardar mês, UF e fonte | Distribuir planilhas no programa ou no repositório; chamar o resultado de "orçamento oficial". Vale até a resposta da consulta formal à CAIXA (antes da F5) |
| **TCPO** | Importar arquivo de usuário licenciado | Distribuir qualquer parte |
| **Códigos de obras municipais** | Parâmetros por município, enviados pela comunidade, com a fonte (lei e artigo) | Copiar anexos gráficos sem checar |
| **Bibliotecas de fabricantes** | Só com licença escrita de redistribuição | Converter famílias Revit ou objetos ArchiCAD |

Na dúvida sobre um conteúdo, ele sai (gatilho do risco R8) e a pergunta vai ao PO.

## 5. Respostas às dúvidas abertas da T11
### 5.1 OCCT (LGPL-2.1-only + exceção da Open CASCADE)
**Entra, como biblioteca ligada dinamicamente.** A LGPL 2.1 permite que um programa que apenas usa a biblioteca tenha outra licença, se essa licença deixar o usuário modificar e depurar; a AGPL v3 deixa. O "only" só impede copiar código do OCCT para os nossos arquivos, o que fica proibido. Condições: arquivos separados, OCCT sem modificação, textos de licença e da exceção no pacote, fonte da versão exata disponível.

### 5.2 libdxfrw
**Fica fora.** A leitura provável é "GPL-2.0 ou posterior", mas há contradição entre os arquivos e não precisamos dela: o DXF usa o ezdxf (MIT). Reabrir só se o ezdxf falhar na F5.

### 5.3 Relink da LGPL no empacotamento (Qt/PySide6, IfcOpenShell, OCCT, pythonocc)
Como publicamos todo o código e os scripts de build, o direito de trocar a biblioteca já é atendido pelo código-fonte. O pacote ainda deve garantir:
1. Bibliotecas LGPL em arquivos separados; nada de Qt estático nem de executável único que embute tudo.
2. O programa não recusa abrir com uma biblioteca trocada (sem conferência de assinatura ou hash das bibliotecas).
3. Textos de licença e lista de bibliotecas com versão, numa pasta `licenses/` e em "Sobre".
4. Um arquivo curto ensinando a troca no Windows e no AppImage.
5. A cada release, a lista dos fontes exatos das bibliotecas LGPL/GPL que distribuímos, com cópia guardada junto do release, e o arquivo de trava do ambiente.

### 5.4 Demais pendências
- **WiX:** fora por padrão por causa da taxa de manutenção; o instalador Windows parte do NSIS (ADR-005).
- **conda-forge:** permitido como canal único; a responsabilidade pelas licenças dos binários que redistribuímos é nossa.
- **PyInstaller:** permitido; para um programa AGPL a exceção do bootloader nem é necessária.

## 6. Consequências
- Quem modificar e distribuir o programa (ou oferecer como serviço em rede) precisa publicar o código das modificações. Empresas que queiram embutir o programa em produto fechado não podem.
- Cada release ganha trabalho fixo: pasta de licenças, lista de fontes, arquivo de trava. Deve ser automatizado na S02.
- O pacote Brasil não pode "vir pronto com a norma": o PO preenche valores padrão como escolhas do projeto. Isso é trabalho do PO nas fases F2, F3 e F5.
- O recurso de SINAPI só importa arquivo do usuário até a CAIXA responder.
- `v2/05` §3 precisa de três ajustes de texto (o líder propõe, o PO aprova): linha para LGPL-2.1-only; separar "copiar código" de "ligar biblioteca"; corrigir a nota sobre a libdxfrw.
- A tabela mestre precisa da correção listada na revisão e de nova conferência em lote opus.

## 7. Como fiscalizamos
| # | Verificação | Onde | Bloqueia merge? |
|---|---|---|---|
| 1 | **REUSE**: todo arquivo tem licença e copyright declarados (linha SPDX ou `REUSE.toml`); textos em `LICENSES/` | CI, a partir da S02 | Sim |
| 2 | **Inventário de dependências** gerado do arquivo de trava: nome, versão, licença SPDX; comparado com uma lista de licenças permitidas | CI | Sim, para licença fora da lista ou vazia |
| 3 | **Canal**: nenhum pacote vem de fora do conda-forge | CI | Sim |
| 4 | **`THIRD_PARTY.md`** em dia com o inventário (gerado, não escrito à mão) | CI | Sim |
| 5 | **Conteúdo regional**: todo arquivo de dados tem campos de origem e licença preenchidos | CI | Sim |
| 6 | **Pacote**: pasta `licenses/` presente; bibliotecas LGPL como arquivos separados; programa abre com biblioteca trocada | Teste de empacotamento (ADR-005, testes 7 e 8) | Sim, no release |
| 7 | **Texto de norma copiado**: a máquina não detecta. Item fixo da lista do revisor em toda tarefa que toque o pacote Brasil; ficha de pesquisa obrigatória | Revisão | Sim |

Instalar a ferramenta REUSE é uma ação que precisa do ok do PO (regra de `CLAUDE.md`).

## 8. O que nos faria mudar de ideia
1. Um advogado de PI discordar da leitura sobre o OCCT ou sobre o relink: rever a seção 5 e o empacotamento antes do primeiro instalador público.
2. A Open CASCADE mudar a licença do OCCT, ou a Qt Company tirar a opção LGPL de módulo que usamos: travar a última versão boa e reavaliar o stack (ADR-001).
3. A CAIXA responder com termos claros de redistribuição do SINAPI: reescrever a linha do SINAPI (para mais ou para menos).
4. A ABNT ou a AsBEA publicarem conteúdo sob licença aberta, ou a NBR 15965 aparecer no bSDD: o pacote Brasil pode embutir esse conteúdo.
5. O inventário da S02 achar dependência indireta incompatível (GPL-2.0-only, proprietária): trocar a dependência ou a fonte do binário (gatilho do risco R7).
6. O conda-forge publicar termos que restrinjam redistribuição: passar ao plano B do ADR-005 (compilar as bibliotecas nós mesmos).
7. O PO decidir aceitar financiamento que exija outra licença: este ADR é reaberto inteiro; enquanto só houver código do projeto, a troca é possível; depois de contribuições de terceiros, só com o acordo deles.
8. O ezdxf não atender ao DXF na F5: reabrir a libdxfrw, arquivo por arquivo.

## 9. Não verificado (não bloqueia a F0)
Termos de uso do canal conda-forge · lista de módulos só comerciais do Qt · licença do Qt Shader Tools · texto de licença do ReportLab · identificador SPDX da exceção do OCCT · termos do SINAPI.

## 10. Perguntas ao PO (com recomendação)
1. **Licença do esquema do `.obim` e dos modelos de projeto.** `v2/02` §6.2 diz "licença aberta" sem dizer qual. Recomendo uma licença bem permissiva para o esquema (para qualquer programa poder ler o arquivo) e para os modelos de projeto (para o desenho do usuário nunca herdar obrigação nossa). Pode ficar para o ADR-003.
2. **Ajustes de texto em `v2/05` §3** (seção 6). **Autorizado pelo PO em 2026-10-10**: o líder propõe o texto.

## Resumo para o PO (5 linhas)
1. O programa é AGPL v3 "ou posterior": quem distribuir uma versão modificada tem de abrir o código dela.
2. Nenhuma biblioteca escolhida é incompatível. O Open CASCADE entra como arquivo separado, sem modificação; a libdxfrw e o WiX ficam de fora (usamos ezdxf e NSIS).
3. O instalador vai levar as licenças de terceiros, deixar as bibliotecas trocáveis e indicar onde está o código-fonte de cada uma.
4. O núcleo não traz conteúdo de país. O pacote Brasil não copia ABNT, NBR 15965, AsBEA, SINAPI nem TCPO: oferece mecanismos configuráveis e importa arquivos que o usuário já tem.
5. A fiscalização é automática no CI a partir da S02; onde a máquina não enxerga (texto de norma copiado), é item fixo de revisão. Não é parecer jurídico.
