# Ficha de pesquisa: viewport 3D com Qt RHI e IFC grande para o benchmark
- Autor: líder (sonnet) · Data: 2026-10-11 · Fatia relacionada: F0-S03 (cartões S03-T01 e S03-T02)
## Pergunta
Como desenhar um modelo IFC grande em 3D dentro do nosso programa (PySide6), com o mesmo código no Windows e no Linux, e de onde tirar um IFC público grande para medir desempenho?
## Fontes consultadas
| # | Fonte | Tipo | URL ou referência | Licença | Data de acesso |
|---|---|---|---|---|---|
| 1 | Documentação do Qt: classe QRhi | doc pública | https://doc.qt.io/qt-6/qrhi.html | documentação do Qt (uso para leitura) | 2026-10-11 |
| 2 | Documentação do Qt: classe QRhiWidget | doc pública | https://doc.qt.io/qt-6/qrhiwidget.html | idem | 2026-10-11 |
| 3 | Pesquisa por amostras públicas de IFC (buildingSMART, Steptools/KIT, Open IFC Model Repository, Molio-Huset) | doc pública | resultado de busca de 2026-10-11 (links na seção abaixo) | **não conferida** em nenhuma das fontes | 2026-10-11 |
| 4 | Conferência local do PySide6 6.11.2 instalado no ambiente `openbim` | teste local | `hasattr(QtWidgets, "QRhiWidget")` e classes `QRhi*` em `QtGui` | LGPL-3.0 (PySide6) | 2026-10-11 |
## O que aprendemos (com nossas palavras)
- **QRhi** é a camada do Qt que fala com a placa de vídeo (Direct3D, Vulkan, OpenGL, Metal) escolhendo a API na hora de rodar. Os shaders (programinhas da placa) são escritos uma vez e convertidos para cada API.
- **Estabilidade:** as classes de baixo nível (`QRhi`, `QShader`) **não têm garantia de compatibilidade** entre versões do Qt; só funcionam com a versão com que o programa foi compilado. Mudanças incompatíveis são raras e só em versões "menores" (6.7, 6.8). Já a classe **QRhiWidget** (Qt 6.7 em diante) é API pública: é um widget comum que mostra conteúdo 3D desenhado por QRhi. Isso reduz o risco que o `v2/03` apontava (QRhi semi-pública): usando QRhiWidget a janela é pública; só o desenho interno depende da versão do Qt, que já é fixa no nosso ambiente (6.11.2).
- **Padrão de API por sistema (QRhiWidget):** Direct3D 11 no Windows, OpenGL no Linux; dá para trocar (Vulkan, Direct3D 12) antes de mostrar a janela. Isso importa para vídeo integrado Intel no Windows (meta do portão).
- **Uso:** subclasse com duas funções, uma que cria os recursos da placa e outra que registra os comandos de desenho; chamar `update()` dentro do desenho dá redesenho contínuo.
- **PySide6:** conferido no nosso ambiente: `QRhiWidget` existe em `QtWidgets` e as classes `QRhi`, `QRhiBuffer`, `QShader` etc. existem em `QtGui` (o `v2/03` falava em precisar de `GuiPrivate`; no Python isso já vem exposto). **Ferramenta de shaders:** `qsb` já está no ambiente (`~/miniforge3/envs/openbim/lib/qt6/lib/qt6/bin/qsb`, pacote do Qt). **Não conferido ainda:** se dá para desenhar de verdade só em Python (será o objetivo da S03-T03).
- **Amostras de IFC:** existem várias coleções públicas, mas nenhuma ficha de licença foi conferida: buildingSMART (amostras por conceito, no GitHub), Steptools com modelos do KIT (por exemplo `AC20-FZK-Haus.ifc`, 2,5 MB, e `AC20-Institute-Var-2.ifc`, 10 MB: pequenos demais para a meta de ~100 MB), Open IFC Model Repository (Universidade de Auckland) e Molio-Huset (buildingSMART Dinamarca). Nenhum candidato de ~100 MB foi identificado ainda.
## Comportamento de referência (testes do PO, se houver)
- Nenhum. Os IFC do PO (fora do repositório, em `../openbim-studio-referencias/`) só entram com lista escrita no chat e nunca vão para o repositório.
## Código aberto lido
- Nenhum nesta etapa. Não foi lido código de outros viewers; se for, vira nova linha aqui com licença.
## Decisão para o OpenBIM Studio
1. Usar **QRhiWidget** (API pública do Qt 6.7+) atrás de uma interface nossa (`Viewport`), com o Qt fixo em 6.11.2. O desenho de baixo nível fica isolado em um único módulo.
2. Backend inicial: padrão de cada sistema; medir Vulkan e Direct3D 12 como opção na S03-T07 se o FPS não bater a meta.
3. Shaders: usar o `qsb` que já vem no ambiente (ferramenta só de montagem; os `.qsb` gerados entram no repositório). Conferir na S03-T03 se isso roda também no ambiente do CI do Windows.
4. IFC grande: **ainda sem candidato**. A S03-T02 deve (a) listar candidatos de ~100 MB com licença **conferida** na página da fonte, (b) trazer ao PO a fonte, o tamanho e a licença, e só então baixar (já autorizado em princípio pelo PO em 2026-10-11, condicionado a essa lista). Alternativa sem download: gerar um IFC sintético grande com `scripts/` próprio (por exemplo repetindo andares de `casa-simples.ifc`); serve para FPS, mas não para o tempo de abertura de um modelo real.
## Riscos de IP identificados
Nenhum até aqui (só documentação pública do Qt lida e resumida). Risco aberto: licença das amostras de IFC; nada será baixado nem redistribuído sem conferir.
## Revisado por: — (aguarda revisão sonnet)

## Atualização S03-T02 (2026-10-11): licenças das amostras de IFC grandes
| Candidato | O que a página diz | Pode ir ao repositório / ser baixado? |
|---|---|---|
| buildingSMART `Certification-datasets` (GitHub) | só "Copyright buildingSMART International"; sem licença nomeada; sem tamanhos | **Não** (sem licença explícita; regra do projeto: código/dado sem licença não entra) |
| Schependomlaan (conjunto de dados no GitHub) | dono dos dados permite uso "científico e acadêmico"; não é licença aberta; tamanho do pacote não confirmado | **Não** no repositório. Uso local só com ok do PO, e não resolve a licença |
| Steptools / KIT (AC20-FZK-Haus 2,5 MB, AC20-Institute-Var-2 10 MB) | licença não conferida; pequenos demais para a meta | Não, por tamanho e licença |
| Open IFC Model Repository (Auckland), Molio-Huset | termos não lidos | **Pendente** (precisa abrir a página de termos) |
**Conclusão:** nenhum IFC público de ~100 MB com licença aberta confirmada. Em vez de baixar algo duvidoso, recomendo:
1. **Modelo sintético gerado por script nosso** (`scripts/`), repetindo/duplicando andares da `casa-simples.ifc` até ~1 milhão de triângulos. Sem download, sem licença externa, reproduzível no CI. Serve para FPS, seleção e memória.
2. **Tempo de abrir um IFC real de ~100 MB**: medir só na máquina do PO com um projeto dele (fora do repositório; o PO lista o arquivo no chat). O número entra no relatório; o arquivo não.
3. Se o PO quiser um público de verdade, abrir a página de termos do Open IFC Model Repository e do Molio-Huset (ação de leitura) antes de qualquer download.
