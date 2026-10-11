# ADR-005: Dependências, build e empacotamento
- Status: **esboço** · **Decisão: pendente** (fecha na F0-S02-T15, com os números dos testes abaixo) · Autor: opus, lote 1 · Data: 2026-10-10 · Cartão: F0-S02-T02
- Base: ficha de disponibilidade (`docs/research/2026-10-10-dependencias-disponibilidade.md`), fichas de licença do grupo D, revisão de licenças do lote 1, `v2/02` §5 e §12.
- **Atualização de 2026-10-11 (opus, lote 2):** resultados parciais dos testes 2, 3, 7, 8 e 9 na seção 3.1; nomes da API 0.9 e alcance da S04 na seção 7.1. O status continua **esboço** e a decisão continua pendente.
- Feito sem rede e sem instalar nada. O que está marcado "de memória" precisa ser conferido. As condições de licença citadas não são parecer jurídico (ver ADR-009).

## 1. Contexto
O programa junta quatro peças grandes que precisam ser da mesma "safra": Python, Qt/PySide6, Open CASCADE (OCCT) e IfcOpenShell. O nosso módulo C++ (`obimcore`) e a parte Python têm de enxergar **o mesmo modelo IFC na memória, sem cópia** (`v2/02` §5). Isso só funciona se o IfcOpenShell usado pelo C++ e o usado pelo Python forem exatamente o mesmo binário (risco R1). Além disso, o build Windows + Linux é o risco R2 (alto) da F0.

Decisões a tomar: (a) de onde vêm os binários; (b) como montar o programa numa pasta que rode sem Python instalado; (c) que formato de instalador usar no Windows e no Linux.

Metas da S02: build limpo ≤ 60 min · build incremental ≤ 10 min · instalador ≤ 600 MB.

## 2. Opções
### 2.1 Fonte dos binários
| Opção | A favor | Contra |
|---|---|---|
| **A. conda-forge como fonte única** | Único lugar com OCCT 8.0.1 + IfcOpenShell 0.9.0 + pythonocc da mesma série, em win-64 e linux-64. Qt com cabeçalhos (`qt6-main`). Compiladores do próprio canal | Não sabemos se o pacote do IfcOpenShell traz cabeçalhos e bibliotecas C++. PySide6 parado em 6.11.2 enquanto o Qt do canal já é 6.12 (precisa fixar o par). Termos do canal não lidos |
| B. vcpkg + pacotes do PyPI | vcpkg é MIT e simples no CMake | vcpkg não tem IfcOpenShell nem PySide6; PyPI não tem OCCT. Teríamos de compilar o IfcOpenShell nós mesmos e ainda casar com o Python do PyPI |
| C. Só PyPI para o Python (PySide6 6.12, ifcopenshell 0.9.0) | Instalação mais simples; PySide6 mais novo | Os pacotes do PyPI não trazem cabeçalhos nem bibliotecas para ligar o nosso C++: cada um embute a sua cópia de Qt e de OCCT. Duas cópias no mesmo processo é exatamente o risco R1 |
| **D. conda-forge + IfcOpenShell compilado por nós** (plano B da opção A) | Uma cópia só, com cabeçalhos garantidos e as opções de build que quisermos (biblioteca compartilhada) | Tempo de build bem maior; receita própria para manter |

### 2.2 Montagem do programa (Python embutido)
| Opção | A favor | Contra |
|---|---|---|
| **P1. Pasta do ambiente inteira + pequeno lançador** (o ambiente conda copiado para dentro do pacote; no Windows pode ser via conda-constructor) | Nada some; o que roda no desenvolvimento é o que vai ao usuário; bibliotecas LGPL já ficam em arquivos separados | Pacote maior: leva tudo o que o ambiente tem |
| **P2. PyInstaller em modo pasta** | Leva só o que o programa usa; pacote menor | Precisa de ajustes para achar bibliotecas do OCCT, do IfcOpenShell e plugins do Qt; erro típico só aparece na máquina do usuário |
| P3. Briefcase | Licença simples | De memória, a conferir: monta a partir de pacotes do PyPI (opção C, descartada pelo R1) e gera MSI por meio do WiX. Provavelmente fora |

### 2.3 Formato de instalador
| Sistema | Opções | Situação |
|---|---|---|
| Windows | **NSIS** · MSI via WiX | Confirmado pelo PO em 2026-10-10: parte do NSIS. WiX fica fora por padrão por causa da taxa de manutenção (revisão de licenças, resposta 4a). Só volta se o PO aceitar os termos por escrito **e** o NSIS falhar em alguma meta do teste 7 |
| Linux | **AppImage** (linuxdeploy ou appimagetool, ambos MIT) | Flatpak fica para a 1.0 (`v2/02` §12) |

## 3. Números medidos
Disponibilidade lida em páginas públicas em 2026-10-10. Os primeiros números medidos estão na seção 3.1.
| Componente | conda-forge (win-64 e linux-64) | Observação |
|---|---|---|
| OCCT | 8.0.1 | |
| IfcOpenShell | 0.9.0, exige OCCT 8.0.x, Python 3.11 a 3.14 | Cabeçalhos e bibliotecas C++: **presentes no linux-64** (seção 3.1); win-64 não verificado |
| PySide6 / Qt | 6.11.2 / `qt6-main` 6.11.2 (existe 6.12.0 do Qt, sem PySide6 correspondente) | Fixar o par em 6.11.2 |
| nanobind, pybind11 | 3.1.0 | |
| pythonocc-core | 8.0.1.1, exige OCCT 8.0.1 | Só para protótipo; não é ponte de produção (`v2/02` §5) |

### 3.1 Resultados parciais (2026-10-11)
Fontes: `docs/research/2026-10-10-sonda-cpp.md`, `docs/research/2026-10-10-appimage-p1.md`, `docs/state/BOARD.md`, `docs/state/reports/LOTE_OPUS_2.md`. "Fechado" quer dizer meta atingida em todos os sistemas pedidos.

| # | Teste | Medido | Situação |
|---|---|---|---|
| 2 | Conteúdo do pacote do IfcOpenShell | **linux-64: 4 de 4 "sim".** Cabeçalhos em `include/ifcparse` (28 arquivos) e `include/ifcgeom` (27); bibliotecas compartilhadas `libifcopenshell.parse`, `.geometry`, `.geometry.writer`, `.plugin` (`.so.0.9`), nenhuma estática; arquivo de configuração do CMake presente; o módulo Python declara precisar dessas bibliotecas e não embute cópia. **win-64: não testado** | **Aberto.** Aprovado no Linux. O Windows é o caso duvidoso (de memória, a conferir: lá o IfcOpenShell costuma ser compilado estático). Rodar no job `windows`, só leitura, **antes da S04** |
| 3 | Módulo C++ mínimo (nanobind + OCCT + Qt6 Core) | linux-64 local: compila e passa (caixa 2×3×4, volume 24). Limpo **2,4 s**, incremental **0,9 s**, com g++ 15.3 e CMake 4.4 do conda-forge. Criação do ambiente: não medida. win-64 e CI: não testado | **Aberto.** As metas de tempo estão atendidas com folga no Linux, mas o número é de um módulo de 17 linhas e não representa o custo real. Complemento recomendado ("3b"): a mesma sonda incluindo `ifcparse/file.h` e ligando em `libifcopenshell.parse`, nos dois sistemas |
| 7 | Instalador Windows (P1 + NSIS) | **482 MB** (meta 600); o CI instala em silêncio, abre o autoteste e desinstala sem sobras; sem administrador. O ambiente vai num `tar.gz` extraído pelo `tar.exe` do Windows, porque o NSIS não aguentou dezenas de milhares de arquivos soltos | **Aberto.** Faltam: DLL trocada, instalar por cima, tempos de instalação e de abertura, Windows 10 e 11 reais. Revisão opus: reprovado, 4 defeitos |
| 8 | AppImage (P1 + appimagetool 1.9.1) | Sem poda: 971 MB (**meta não atingida**). Com poda de vtk e viskores: **565 MB**. Com a poda ampliada (139 pacotes, inclui ffmpeg): o job confere ≤ 600 MB; valor exato a registrar. Abre sem Python do sistema; primeira abertura 8,5 s sem FUSE e 0,5 s com FUSE; `--appimage-extract` funciona; abre com `.so` do Qt alterado | **Aberto.** Faltam Ubuntu LTS, Fedora e duplo clique. Revisão opus: reprovado, 7 defeitos (textos de licença) |
| 9 | Inventário de licenças | Gerado no CI: 291 pacotes no ambiente de runtime (152 ficam no pacote), 0 fora do conda-forge, 1 metadado vazio (`tbb-devel`, exceção aceita) | **Aberto.** Falta comparar com a lista de licenças permitidas |
| 1, 4, 5, 6, 10, 11 | — | Sem resultado registrado neste ADR | Aberto |

O que os resultados já dizem:
1. **A opção A (conda-forge como fonte única) se sustenta no Linux:** o plano da seção 8 (sem cabeçalhos) não é necessário ali. A escolha entre A e D depende agora do teste 2 no Windows.
2. **P1 puro passa do tamanho; P1 com poda cabe nos dois sistemas.** A poda passa a fazer parte da montagem P1. P2 (PyInstaller) não é necessário por tamanho.
3. **A poda tem custo:** o módulo de visualização do OCCT (`TKIVtk`) deixa de funcionar e o Mesa sai do pacote. Nada que o programa use hoje; registrar na seção 9.
4. **O PySide6 do conda-forge traz módulos sem a biblioteca Qt correspondente** (Charts, Multimedia, 3D, WebEngine, Pdf e outros não carregam com o `qt6-main` sozinho). Quem precisar de um deles acrescenta o pacote Qt e refaz inventário e tamanho.

## 4. Decisão
**Pendente.** Fecha na S02-T15 com a tabela "meta × medido" dos testes da seção 6.

Regras que já valem, por virem do ADR-009 e não de teste: só o canal conda-forge; bibliotecas LGPL em arquivos separados; nada de executável único; pasta de licenças e lista de fontes em todo pacote.

## 5. Opção provisória recomendada (para a S02-T03 usar já)
Marcada como **provisória**: serve para montar o ambiente de desenvolvimento, não decide o ADR.
1. **Fonte:** opção A, conda-forge como canal único, com `nodefaults`.
2. **Ferramenta de ambiente:** Miniforge (ou micromamba). Nunca o instalador Anaconda/Miniconda. Alternativa a comparar no teste 1: pixi, que gera um arquivo de trava único para os dois sistemas; antes de adotar, precisa de uma linha na tabela de licenças (não tem ficha). Instalar qualquer uma delas exige ok do PO.
3. **Versões fixas:** Python 3.12 · `occt` 8.0.1 · `ifcopenshell` 0.9.0 · `pyside6` 6.11.2 com `qt6-main` 6.11.2 · `nanobind` 3.1.0 · pytest. `pythonocc-core` fica fora do ambiente base.
4. **Arquivo de trava obrigatório**, além do `environment.yml`: sem ele as dependências indiretas mudam de uma semana para outra e o inventário de licenças do ADR-009 não tem de onde sair. O cartão S02-T03 hoje só permite `environment.yml`; o líder deve acrescentar o arquivo de trava aos arquivos permitidos e registrar que arquivo gerado não conta no limite de 400 linhas.
5. **Compilador (quando houver C++):** os do próprio conda-forge no Linux; Visual Studio 2022 no Windows (é o que o canal usa; misturar compiladores quebra a compatibilidade binária). CMake e Ninja pelo canal.
6. **Montagem e instalador, para os cartões T10 e T11 começarem:** P1 (pasta do ambiente + lançador), NSIS no Windows, AppImage no Linux. P2 entra como comparação se o tamanho de P1 passar da meta.

## 6. Plano de testes que fecha a decisão
Cada teste roda nos dois sistemas obrigatórios, salvo indicação. "Cartão" diz onde o teste cabe hoje.

| # | Teste | O que mede | Meta | Cartão |
|---|---|---|---|---|
| 1 | **Ambiente resolve.** Criar o ambiente da seção 5 do zero, com arquivo de trava | Resolve em win-64 e linux-64; pacotes vindos de fora do conda-forge; tempo de criação; tamanho em disco | Resolve nos 2 sistemas · **0** pacotes de outro canal · criação ≤ 15 min sem cache · tamanho anotado | T03, T06, T07 |
| 2 | **O que vem no pacote do IfcOpenShell.** Listar o conteúdo do pacote instalado | Há cabeçalhos (`ifcparse/`, `ifcgeom/`)? Há biblioteca C++ para ligar? É compartilhada ou estática? O módulo Python usa essa biblioteca ou embute a própria cópia? | 4 respostas sim/não por sistema. "Aprovado" = cabeçalhos presentes **e** biblioteca compartilhada usada também pelo módulo Python | **sem cartão** (cabe na T03, só leitura) |
| 3 | **Módulo C++ mínimo.** Um módulo nanobind de poucas linhas que usa Python, Qt e OCCT do ambiente (cria uma caixa, devolve o volume) | Compila e passa; tempo de build limpo e incremental | Passa nos 2 sistemas · limpo ≤ 60 min (contando criar o ambiente, sem cache) · incremental ≤ 10 min | **sem cartão** (ver nota) |
| 4 | **Um Qt só.** Abrir uma janela PySide6 com um componente desenhado pelo nosso C++ ligado ao `qt6-main` | Cópias do Qt carregadas no processo; versão; existência dos cabeçalhos do QRhi no pacote | **1** cópia · versão 6.11.2 nos dois lados · cabeçalhos presentes | **sem cartão** (S03) |
| 5 | **Prova do R1: mesmo IFC, mesma versão, mesma ABI.** Ver seção 7 | Seção 7 | Seção 7 | **sem cartão** (S04; ou sonda na S02) |
| 6 | **Plano B: IfcOpenShell compilado por nós** (só se o teste 2 ou o 5 reprovar) | Tempo de build com e sem cache; teste 5 repetido | Limpo ≤ 60 min no total com o pacote guardado em cache do CI · teste 5 aprovado | sem cartão |
| 7 | **Instalador Windows.** P1 + NSIS (P2 se P1 estourar o tamanho) | Tamanho; tempo de geração no CI; instala sem senha de administrador; abre em Windows sem Python; tempo até a janela; instalar por cima de versão anterior; desinstala sem sobras; programa abre com uma DLL do Qt trocada por outra compilação da mesma versão; pasta `licenses/` presente | ≤ 600 MB · geração ≤ 15 min · instalação ≤ 5 min · janela em ≤ 10 s na primeira abertura · 0 arquivos restantes · abre com a DLL trocada | T11, T13, T14 |
| 8 | **AppImage.** P1 + appimagetool ou linuxdeploy | Tamanho; abre em Ubuntu LTS e Fedora por duplo clique; funciona sem a biblioteca FUSE antiga; `--appimage-extract` funciona; abre com um `.so` do Qt trocado; pasta `licenses/` presente | ≤ 600 MB · abre nas 2 distribuições sem terminal · abre com a biblioteca trocada · janela em ≤ 10 s | T10, T13, T14 |
| 9 | **Inventário de licenças.** Gerar do arquivo de trava a lista nome/versão/licença | Pacotes sem licença declarada ou fora da lista permitida do ADR-009 | **100%** com licença · **0** fora da lista | T06 (junto do REUSE) |
| 10 | **Reprodutibilidade.** Recriar o ambiente pelo arquivo de trava em outro dia e em outra máquina (CI) | Diferença na lista de pacotes | **0** diferenças | T06, T07 |
| 11 | **macOS (melhor esforço).** Testes 1 e 3 em osx-arm64 | Resolve e compila | Informativo; falha não bloqueia | T08 |

**Nota importante sobre os cartões da S02.** Como estão escritos, o app esqueleto é só Python (a T03 põe "compilar C++" fora de escopo). Então as metas "build limpo ≤ 60 min" e "incremental ≤ 10 min" seriam medidas sem nenhum C++ e sem compilar contra OCCT e IfcOpenShell: o número sairia bom e não provaria nada sobre o risco R2. Recomendação: incluir na S02 os testes 2 e 3 (um cartão novo e pequeno) e medir as metas de build com eles. O teste 5 mexe na ponte C++/Python e portanto é **T3** (especificação e revisão do opus); pode ficar para a S04, mas o teste 2, que é só leitura, deve rodar já, porque decide entre a opção A e a D.

**MSI ou NSIS não se escolhe por gosto.** O que o teste 7 mede serve para os dois; a diferença está em: custo e termos de uso (WiX tem taxa); instalar por cima e desinstalar limpo; instalação sem administrador; associação dos arquivos `.ifc`, `.obim` e `.obimpack`; funcionar com a assinatura da SignPath na v0.3. Instalação em massa por empresas (ponto forte do MSI) não é requisito da 1.0.

## 7. Qual teste prova que o IfcOpenShell do C++ e o do Python são o mesmo (R1)
É o **teste 5**. Um módulo nanobind de sonda, compilado contra os cabeçalhos e a biblioteca do IfcOpenShell do próprio ambiente, recebe um arquivo aberto pelo Python (`ifcopenshell.open`) e confere:
| Verificação | Meta |
|---|---|
| a) Versão do IfcOpenShell vista na compilação do C++ = versão que o Python informa em execução | iguais |
| b) O endereço de memória do modelo visto pelo C++ = o endereço guardado pelo objeto Python | iguais (prova que não houve cópia) |
| c) Contagem de paredes e de todos os elementos pelo C++ = contagem pelo Python, em 3 IFCs (2x3, 4 e 4.3) | iguais |
| d) O Python cria um elemento e o C++ enxerga sem reabrir; o C++ muda um nome e o Python lê o nome novo | 2 de 2 |
| e) Bibliotecas carregadas no processo: cópias do núcleo do IfcOpenShell e do núcleo do OCCT | **1** de cada |
| f) Repetir c) e d) 1.000 vezes, incluindo fechar e reabrir o arquivo | **0** travamentos, **0** diferenças |
| g) Tudo acima em win-64 e linux-64 | 2 de 2 sistemas |

Se a) a f) passam, versão e ABI são compartilhadas. Se e) mostrar duas cópias, o teste reprova mesmo que o resto passe: duas cópias funcionam por acaso e quebram depois. Desempenho e uso com threads ficam para a S04, que é a prova completa do R1; este teste só diz se o caminho de build escolhido permite a ponte.

### 7.1 Atualização de 2026-10-11: nomes da versão 0.9 e o que a S04 deve provar
A sonda mostrou que a API C++ da 0.9 foi reorganizada: o modelo é `ifcopenshell::file` (cabeçalho `ifcparse/file.h`), e as bibliotecas são `libifcopenshell.parse` e `libifcopenshell.geometry`, não mais `IfcParse::IfcFile` e `libIfcParse`. **As verificações a) a g) continuam as mesmas.** Mudam o texto da especificação e os cuidados:
1. A especificação T3 do teste 5 é escrita pelo opus lendo os cabeçalhos instalados da versão travada, não a documentação de versões anteriores.
2. Travar versão **e build** do pacote `ifcopenshell`. A verificação a) passa a comparar também o build, e as bibliotecas levam a versão no nome (`.so.0.9`): trocar de versão é trocar de ABI.
3. Ligar pelo `IfcOpenShellConfig.cmake` do próprio pacote, para herdar as mesmas opções de compilação.
4. Mesmo compilador e mesmo modo do pacote: compiladores do conda-forge no Linux; no Windows, Visual Studio 2022 e nunca modo "Debug" (a biblioteca padrão de depuração é incompatível com a do pacote).

A S04 deve provar:
| # | Prova | Meta |
|---|---|---|
| 1 | Teste 5 inteiro, a) a g), com os nomes da 0.9 | Como na tabela acima, em win-64 e linux-64 |
| 2 | Passagem do modelo do Python para o C++ sem cópia, com regra de posse escrita: o objeto Python é o dono, o C++ só pega emprestado | Endereços iguais; 0 travamentos quando o Python fecha o arquivo antes, durante e depois de uma chamada ao C++ (1.000 repetições) |
| 3 | Uma cópia só no processo | 1 núcleo do IfcOpenShell e 1 do OCCT carregados, nos dois sistemas |
| 4 | Threads: leitura pelo C++ fora da thread da interface enquanto o Python não escreve; regra do bloqueio do interpretador escrita na especificação | 0 travamentos e 0 diferenças em 1.000 repetições |
| 5 | Custo da ponte | Tempo por chamada e por elemento percorrido, comparado com o Python puro e com o C++ puro (`v2/03` S04) |
| 6 | Geometria real com o pacote podado (sem VTK) | Tesselação de pelo menos 1 IFC do corpus igual no ambiente de desenvolvimento e dentro do AppImage e do instalador |

Pré-requisito da S04: teste 2 aprovado no Windows. Se reprovar, vale a seção 8, item 2 (opção D) antes de qualquer código da ponte.

## 8. Se o conda-forge não trouxer os cabeçalhos do IfcOpenShell
Em ordem, parando no primeiro que passar no teste 5:
1. **Há biblioteca compartilhada, faltam só os cabeçalhos:** pegar os cabeçalhos da mesma tag do código-fonte (v0.9.0) e compilar a sonda. Aceitável apenas se o teste 5 passar inteiro, porque cabeçalho e binário podem ter sido gerados com opções diferentes.
2. **Não há biblioteca compartilhada (o módulo Python embute a própria cópia):** passar à opção D. Compilar o IfcOpenShell (biblioteca C++ e módulo Python juntos) a partir da tag, contra o OCCT do conda-forge, partindo da receita pública do canal, e gerar um pacote local usado pelo desenvolvimento e pelo CI. Custo: teste 6.
3. **Em paralelo, sem bloquear:** sugerir à receita do conda-forge um pacote com cabeçalhos e biblioteca compartilhada. É ação de rede em nome do projeto: só com ok do PO.
4. **Nunca:** usar o pacote do PyPI para o Python e compilar outro IfcOpenShell para o C++. São duas cópias (R1).
5. **Se 1 e 2 falharem, ou o build passar de 60 min sem saída:** parar e levar ao PO com opções. É o gatilho do R2 e toca o ADR-001 (C++ puro com Python só para plugins).

## 9. Consequências (da opção provisória)
- O ambiente de desenvolvimento e o do CI saem do mesmo arquivo de trava; o PO precisa autorizar a instalação do gerenciador de ambientes.
- Ficamos presos ao ritmo do conda-forge: hoje, Qt 6.11.2 e não 6.12.
- P1 tende a gerar pacote grande; se passar de 600 MB, a saída é P2 ou retirar pacotes do ambiente de distribuição, nunca cortar em silêncio. **Medido em 2026-10-10:** passou (971 MB no Linux); a saída adotada foi a poda (`scripts/prune_packages.py`), com a lista do que sai gravada em `licenses/REMOVIDOS.md`. A lista é conferida a cada mudança de versão, e todo item novo que saia (como o Mesa) é decisão registrada do PO.
- Redistribuir binários do conda-forge traz as obrigações do ADR-009 (pasta de licenças, lista de fontes por release).
- Se cair na opção D, o projeto passa a manter uma receita de build do IfcOpenShell.

## 10. O que nos faria mudar de ideia
1. Teste 2 ou 5 reprovado: opção D; se D reprovar, levar ao PO (ADR-001).
2. Par PySide6/Qt do conda-forge com defeito que só o 6.12 resolve: reavaliar PyPI para a interface, o que reabre o problema do Qt duplicado (teste 4).
3. Instalador acima de 600 MB mesmo com P2: rever a meta com o PO ou separar componentes opcionais.
4. NSIS falhar em instalar por cima, desinstalar limpo ou conviver com a assinatura: reabrir o WiX, com ok escrito do PO sobre a taxa.
5. conda-forge publicar termos que restrinjam redistribuição, ou abandonar um dos pacotes: opção D ampliada ou vcpkg para a parte C++.
6. Build limpo acima de 60 min: guardar pacotes prontos no cache do CI; se não bastar, é gatilho do R2 (mais de 4 semanas sem build nos dois sistemas: simplificar e reportar).

## 11. Não verificado
Conteúdo do pacote do IfcOpenShell no conda-forge **em win-64** (linux-64 verificado) · de onde o appimagetool tira o programa de partida que vai dentro do AppImage, e a licença dele · manutenção da receita do PySide6 no conda-forge · cabeçalhos do QRhi no `qt6-main` · como o Briefcase monta e gera MSI · licença do pixi e do micromamba · termos do canal conda-forge · tamanho real do ambiente.

## Resumo para o PO (5 linhas)
1. Ainda não há decisão: este documento diz o que testar e com que número cada teste passa. Em 2026-10-11 já há resultados parciais (seção 3.1): no Linux o caminho simples serve; falta o mesmo teste no Windows.
2. Para começar a trabalhar, recomendo provisoriamente pegar todas as bibliotecas de um lugar só (conda-forge), com versões travadas; é o único lugar onde as peças são da mesma "safra" no Windows e no Linux.
3. O ponto mais arriscado é a parte C++ e a parte Python usarem exatamente o mesmo IfcOpenShell. O teste 5 prova isso; o teste 2, que é só olhar o conteúdo de um pacote, já diz se o caminho simples serve. Se não servir, compilamos o IfcOpenShell nós mesmos.
4. Instalador: NSIS no Windows e AppImage no Linux. O WiX fica de fora por cobrar taxa; só volta com o seu ok por escrito e se o NSIS falhar.
5. O cartão extra da parte C++ foi feito no Linux: compila em segundos, mas com um módulo mínimo. Os dois pacotes cabem em 600 MB depois de retirar o que o programa não usa (482 MB no Windows; 565 MB no Linux na primeira poda). Faltam o teste 2 no Windows e a prova completa da ponte (S04).
