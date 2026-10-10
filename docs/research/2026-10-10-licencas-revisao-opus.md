# Revisão da tabela mestre de licenças (F0-S01-T11)
- Revisor: opus (papel Arquiteto/Revisor crítico), lote 1 · Data: 2026-10-10
- Objeto: `docs/research/2026-10-10-licencas-tabela-mestre.md`, conferida contra as fichas dos grupos A a D.
- **Não é parecer jurídico.** É leitura técnica das licenças por quem não é advogado. Antes de publicar um instalador para o público, vale uma consulta a advogado de propriedade intelectual sobre os pontos 1, 3 e 4.
- Feito sem rede. O que eu afirmo "de memória" está marcado assim e precisa ser conferido na fonte antes de virar regra.
- Fora do meu pacote de leitura (não conferidos): `THIRD_PARTY.md`, `docs/state/reports/F0-S01.md` e a lista de componentes de `v2/03` S01. Os critérios 1, 3 e 4 do cartão ficam por conferir.

## Veredito: REPROVADO (correções pequenas, sem refazer pesquisa)
A coleta está boa e as fichas são honestas sobre o que não foi verificado. Nenhuma dependência precisa ser trocada. A tabela é reprovada porque, como está, não pode servir de base ao ADR-009: tem duas condições escritas de forma errada, quatro células "Pendente" que agora têm resposta, e lacunas de cobertura. As correções cabem em um diff curto (estimativa: 30 a 50 linhas).

### Defeitos (numerados)
1. **LibreDWG e libslvs: condição errada.** A tabela diz "conjunto fica GPL-3+" e "conjunto fica GPL-3". Não é assim: a AGPL v3 e a GPL v3 têm uma cláusula recíproca (seção 13 de cada uma) que permite juntar as duas; cada parte continua na sua licença e a exigência de rede da AGPL continua valendo para o conjunto. Trocar por: "Combinação permitida pela seção 13; a parte GPL continua GPL-3, o nosso código continua AGPL-3".
2. **Coluna "Compatível" mistura quatro situações diferentes** e isso esconde a condição real de cada linha: (a) código copiado para dentro dos nossos arquivos; (b) biblioteca ligada ao programa; (c) ferramenta de build ou de empacotamento, que não entra no programa; (d) canal de distribuição, que não é licença. Acrescentar uma coluna "Como entra" com um desses quatro valores. A regra de relink só existe em (b); "contamina?" só faz sentido em (c).
3. **OCCT: "Pendente" passa a "Sim, com condição"** (resposta 1 abaixo). Grafar a licença como `LGPL-2.1-only WITH OCCT-exception-1.0` (identificador SPDX de memória; conferir na lista de exceções do SPDX).
4. **libdxfrw: "Pendente" passa a "Fora (decisão)"** (resposta 2).
5. **conda-forge: "Pendente" passa a "Condição"** (resposta 4b), e a linha deve dizer que canal não é licença: quem redistribui os binários somos nós, pacote a pacote.
6. **WiX: "Pendente" passa a "Fora por padrão"** (resposta 4a).
7. **PyInstaller: a condição "parecer jurídico não verificado" não se aplica ao nosso caso** (resposta 4c). Trocar por: "Ferramenta; mesmo sem a exceção, GPL-2.0-or-later pode ser usada como GPL-3, que combina com AGPL-3".
8. **Falta a dependência transitiva.** A tabela cobre só os componentes diretos. O instalador vai carregar dezenas de outros pacotes (o próprio Python, e o que OCCT, IfcOpenShell e Qt puxam). De memória, a conferir: CPython (PSF-2.0), Eigen (MPL-2.0), Boost (BSL-1.0), TBB (Apache-2.0), HDF5 (BSD), libxml2 (MIT), FreeType (FTL ou GPL-2: escolher FTL), CGAL (maior parte GPL-3-or-later, se o IfcOpenShell do conda-forge for compilado com ele), bibliotecas de terceiros dentro do Qt, e o runtime do Visual C++ no Windows (proprietário, redistribuível pelos termos da Microsoft). Não se resolve à mão: acrescentar na tabela a nota "inventário completo gerado do arquivo de trava do ambiente na S02" e criar essa tarefa (ver ADR-005, teste 9).
9. **Versões consultadas não são as que vamos distribuir.** Exemplos: Qt 6.12 e PySide6 6.12.0 nas fichas, mas o par disponível no conda-forge é 6.11.2; o cabeçalho do QPdfWriter foi lido no qtbase 6.9. `v2/05` §3 manda reconfirmar pelo arquivo de licença da versão fixada. Acrescentar a coluna "Versão consultada" (já existe nas fichas) e a nota "reconfirmar na versão travada (S02)".
10. **Qt: lacuna de pesquisa a registrar.** De memória, a conferir: o módulo Qt Shader Tools (que compila os shaders usados pelo QRhi, `v2/02` §5) é oferecido só sob GPL-3 ou comercial, e não aparece na lista de 14 módulos da ficha B. Com AGPL v3 isso continua compatível, mas fura a regra que a própria tabela escreveu ("evitar os módulos só GPL-3"). Acrescentar em "Não verificado": "licença do Qt Shader Tools e se ele vai no instalador ou só é usado no build".
11. **PlaneGCS: falta a condição prática.** Não é uma biblioteca separada; é uma pasta dentro do FreeCAD. Usar significa copiar código (situação (a) do defeito 2): comentário de origem, registro em `THIRD_PARTY.md`, e licenças do que ele usa (Eigen, Boost). Só interessa na 2.0.
12. **Divergência entre documentos não anotada.** `v2/05` §3 fala em libdxfrw "GPLv2 ou LGPLv2+"; a ficha C diz que não há menção a LGPL em nenhum arquivo. A tabela deve registrar que a ficha C corrige o texto de `v2/05`.

### Linhas com que concordo sem ressalva
IfcOpenShell C++ e Python · pythonocc-core · PySide6 (opção LGPL-3) · nanobind · pybind11 · QPdfWriter · ReportLab ("Condição" está certo; fica fora até alguém ler o arquivo de licença do pacote) · fpdf2 · CairoSVG · ezdxf · vcpkg · Briefcase · conda-constructor · NSIS · linuxdeploy · appimagetool.

Observação sobre "somente versão 3": PySide6, fpdf2 e (talvez) libslvs são "3.0-only". O nosso código é "AGPL-3.0-or-later", mas o programa distribuído, como conjunto, só pode ser usado hoje sob a versão 3. Isso não é defeito; fica registrado no ADR-009.

## Respostas às quatro pendências

### 1. OCCT (LGPL-2.1-only + Open CASCADE Exception 1.0) com AGPL v3 por ligação dinâmica
**Compatível, com condições.** Raciocínio:
- O nosso programa apenas *usa* a biblioteca. A LGPL 2.1 (seção 6) permite distribuir um programa que usa a biblioteca sob a licença que quisermos, desde que essa licença deixe o usuário modificar o programa para uso próprio e fazer engenharia reversa para depurar. A AGPL v3 deixa. O OCCT continua LGPL-2.1; o nosso código continua AGPL.
- A palavra "only" só pesaria se copiássemos código do OCCT para dentro dos nossos arquivos. Não vamos fazer isso. (Mesmo nesse caso, a seção 3 da LGPL 2.1 permite converter uma cópia para a GPL de versão posterior; não precisamos desse caminho.)
- A exceção da Open CASCADE ajuda: o nosso módulo C++ inclui cabeçalhos do OCCT com muito código "inline" e moldes; a exceção tira a dúvida sobre esses trechos irem parar no nosso binário.
- O IfcOpenShell (LGPL-3-or-later) já é distribuído ligado ao OCCT nessas mesmas condições.

Condições:
1. Ligação dinâmica: o OCCT vai como arquivos `.dll`/`.so` separados, nunca fundido no nosso binário.
2. Não modificar o OCCT. Se um dia modificarmos, as mudanças são publicadas sob LGPL-2.1.
3. O instalador leva o texto da LGPL 2.1 e o da exceção, e o programa avisa que usa o OCCT ("Sobre > Licenças").
4. Oferecemos o código-fonte da versão exata do OCCT que distribuímos (ver resposta 3, item 5).
5. Nada no programa ou nos termos de uso proíbe trocar a biblioteca ou depurar.
6. `v2/05` §3 deve ganhar uma linha para "LGPL-2.1-only: sim, só como biblioteca ligada dinamicamente; copiar código, não". Quem edita é o líder, com ok do PO.

### 2. libdxfrw
**Fica fora.** A leitura mais provável é "GPL-2.0-or-later": quando os cabeçalhos dos arquivos dizem "versão 2 ou posterior", é isso que costuma valer, e o arquivo `COPYING` é só o texto da licença (a etiqueta "GPL-2.0" do GitHub vem dele). Mas não precisamos decidir essa disputa: o ezdxf (MIT) já foi escolhido, e a política manda deixar fora o que é ambíguo. Reabrir só se o ezdxf falhar no teste de DXF da F5, e então conferindo o cabeçalho de cada arquivo que fosse usado. Enquanto isso: nenhum código da libdxfrw no repositório, nem como base.

### 3. Relink da LGPL (Qt/PySide6, IfcOpenShell, OCCT, pythonocc): o que o empacotamento precisa garantir
Ponto central: **como o nosso programa é aberto e publicamos todo o código e os scripts de build, a exigência de "poder religar" já é atendida pela via do código-fonte** (qualquer pessoa pode recompilar com outra versão da biblioteca). Mesmo assim, o pacote deve tornar a troca fácil e não pode atrapalhá-la. Garantias, válidas para o instalador Windows e para o AppImage:
1. **Bibliotecas LGPL como arquivos separados.** Nada de Qt estático. Nada de executável único que esconde tudo: se for PyInstaller, modo pasta ("one-folder"), não "one-file".
2. **Sem trava contra troca.** O programa não confere assinatura nem hash das bibliotecas ao iniciar. A assinatura de código do Windows vale para o nosso executável e para o instalador, e não pode impedir que o programa abra com uma DLL substituída.
3. **Textos de licença dentro do pacote:** AGPL-3, GPL-3, LGPL-3, LGPL-2.1, exceção do OCCT e os avisos de copyright dos demais. Numa pasta `licenses/` e na tela "Sobre > Licenças de terceiros", com a lista de bibliotecas e versões.
4. **Instrução de troca** em um arquivo curto (`LGPL-COMO-TROCAR.md`): no Windows, onde ficam as DLLs; no Linux, que o AppImage se desmonta com `--appimage-extract`, troca-se o `.so` e remonta-se com o appimagetool (ou roda-se direto da pasta extraída).
5. **Código-fonte das bibliotecas, da versão exata.** Como nós redistribuímos os binários (vindos do conda-forge), a obrigação de oferecer o fonte é nossa, não do conda-forge. A cada release: lista com nome, versão, número de build e endereço do fonte e da receita de cada pacote LGPL/GPL; rota mais segura, guardar junto do release uma cópia dos pacotes de fonte. O arquivo de trava do ambiente vai junto.
6. **IfcOpenShell dentro do nosso módulo C++:** se a ligação for estática (possível, depende de como o conda-forge o compila; ver ADR-005), continua permitido pela via do código-fonte, mas o ADR-005 deve preferir biblioteca compartilhada, que também é o que o risco R1 pede (uma cópia só no processo).
7. Um teste de aceite do empacotamento prova o item 1 e o 2 (ADR-005, testes 7 e 8).

### 4. WiX, conda-forge e canal `defaults`, PyInstaller
**a) WiX e o Open Source Maintenance Fee: fora por padrão; usar NSIS.** O código do WiX é MS-RL, mas o projeto condiciona o download dos binários oficiais e o uso com receita ao pagamento da taxa. Para um projeto sem receita a taxa talvez não se aplique (não consegui confirmar o texto), mas: é um termo extra que pode mudar; o projeto pode vir a receber doações; e `CLAUDE.md` proíbe gasto sem ok do PO. Não há ganho que justifique o risco na F0. O WiX só volta à comparação se o PO aceitar os termos por escrito e o teste do ADR-005 mostrar que o NSIS não atende. Nota: o pequeno programa instalador (do NSIS ou do WiX) é um programa à parte que só carrega o nosso; as licenças dele (zlib, bzip2, CPL do módulo LZMA) não se misturam com a AGPL.

**b) conda-forge: pode usar, com condição. Canal `defaults`: proibido.**
- conda-forge é um canal comunitário; não muda a licença de nenhum pacote. O que vale é a licença de cada pacote e a nossa obrigação como redistribuidores (resposta 3, item 5). Os termos de uso do próprio canal continuam não verificados (página fora do ar): manter em "Não verificado" e pedir ao PO que abra a página no navegador quando puder; não bloqueia a F0.
- Condições: instalar com ferramenta que já nasce apontada só para o conda-forge (Miniforge, micromamba ou pixi; nunca o instalador Anaconda/Miniconda); configuração com `conda-forge` como único canal e `nodefaults`; o CI falha se algum pacote do ambiente vier de outro canal.
- Canal `defaults`: os termos da Anaconda de 2025 restringem o uso gratuito por tamanho de organização. Para o PO sozinho provavelmente seria gratuito, mas um colaborador de empresa grande não poderia reproduzir o build. Proibir é simples e não custa nada.

**c) Exceção do PyInstaller: não dependemos dela.** O PyInstaller é GPL-2.0-or-later. "Or later" permite usá-lo sob a GPL-3, e a GPL-3 combina com a AGPL-3 (seção 13). Logo, mesmo que a exceção do bootloader não existisse, o nosso programa AGPL poderia ser distribuído com ele. A exceção só é decisiva para programas fechados. Condição única: levar no pacote o aviso de licença do PyInstaller. A escolha entre PyInstaller, Briefcase e conda-constructor é técnica (ADR-005), não de licença.

## O que fazer com esta revisão
1. O líder abre uma correção curta da tabela (defeitos 1 a 12), sem nova pesquisa na rede, e a devolve ao próximo lote opus para conferência do diff.
2. O ADR-009 deste lote foi escrito com base nas respostas acima, não na tabela reprovada. Ele não depende da correção para valer; depende do ok do PO.
3. Pendências que seguem abertas, nenhuma bloqueia a F0: termos do canal conda-forge; lista de módulos só comerciais do Qt; licença do Qt Shader Tools; texto de licença do ReportLab; termos do SINAPI; identificador SPDX da exceção do OCCT.
