# Relatório do lote Opus 3: conferência das correções, amostra T19/T20 e ADR-005
- Data: 2026-10-11 · Papel: Arquiteto/Revisor crítico (opus) · Pedido: lote Opus 3 (colado pelo PO no chat)
- Feito sem rede e sem instalar nada. **Não é parecer jurídico**: é leitura técnica de licenças por quem não é advogado.
- Contexto fechado: li só os arquivos do pedido. **Não vi** a saída bruta do CI, o `BOARD.md`, o `environment.yml`, o `THIRD_PARTY.md`, o roteiro T14, a ficha `docs/research/2026-10-10-appimage-p1.md` nem `scripts/collect_package_licenses.py`. Onde a evidência depende deles, está escrito "não conferido".
- Única execução: chamei a função `expr_ok` de `scripts/license_inventory.py` com 13 expressões inventadas (resultado no item 2).

## Resultado por item
| Item | Objeto | Resultado |
|---|---|---|
| 1a | AppImage (S02-T17) | **APROVADO.** 7 de 7 defeitos corrigidos; 4 observações que não bloqueiam |
| 1b | Instalador Windows (S02-T18) | **APROVADO** nos 4 defeitos do lote 2. **1 defeito novo** (N1), que vira cartão curto antes do roteiro T14 |
| 1c | CI: lista de licenças permitidas | **Corrigido em parte**: a lista existe e reprova a montagem, mas o leitor de expressões tem um furo (item 2, D1) |
| 1d | Pendências aceitas pelo líder | **Aceitável**, com 3 condições |
| 2a | T19 (teste 2 no Windows, sonda 3b) | Amostra **aprovada**; 4 lembretes para a S04 |
| 2b | T20 (inventário rigoroso) | Amostra **reprovada**: 1 defeito e 3 ajustes, todos curtos; revisão sonnet basta |
| 3 | ADR-005 | Escrito como decisão e **aprovado pelo PO no chat em 2026-10-11** (status "aceito") |

## Item 1a: AppImage (T17): APROVADO
| # | Defeito do lote 2 | Situação | Evidência |
|---|---|---|---|
| 1 | Faltavam os textos de licença dos pacotes | Corrigido | `build_appimage.sh` linha 63 chama `collect_package_licenses.py`; `test_appimage.sh` linhas 24 a 26 exige texto da LGPL e pelo menos 200 pastas em `licenses/pacotes`; relatório: 277 pacotes |
| 2 | Faltava a exceção do OCCT | Corrigido | `packaging/licenses-texts/OCCT-exception-1.0.txt` (origem na tag V8_0_1, em `LEIA-ME.md`); copiado nas linhas 56 a 59; o teste exige o arquivo |
| 3 | LGPL-3, LGPL-2.1 e GPL-3 vinham da máquina, com `\|\| true` | Corrigido | Os três textos estão no repositório; a montagem para com erro se faltar algum (linha 57); não há mais `\|\| true` |
| 4 | Nenhum teste das obrigações de licença | Corrigido | `test_appimage.sh`: arquivos de licença, extração, ausência do que foi podado, abertura com `libQt6Core.so.6` alterada; chamado pelo job `appimage` |
| 5 | Resíduo `libTKIVtk` e pastas vazias | Corrigido | Linhas 40 a 43 apagam; `REMOVIDOS.md` explica; o teste procura `libTKIVtk*` |
| 6 | Mesa saiu sem registro | Corrigido | Decisão do PO de 2026-10-11 em `F0-S02-appimage.md` e no ADR-005 §9; teste em máquina virtual vai para o roteiro T14 (roteiro não conferido) |
| 7 | Ficha e relatório descreviam a poda antiga | Corrigido no relatório | `F0-S02-appimage.md` ganhou a seção de atualização (139 pacotes, 389 MB). Ficha de pesquisa: não conferida |

Extra pedido no lote 2 e feito: `prune_packages.py` lista os pacotes mantidos que dependem de algo removido e para com erro se a lista não for a esperada (`--esperado=occt`).

Observações (não bloqueiam; T0/T1, sem voltar ao opus):
1. **"Todos os pacotes que ficam" não está provado.** São 277 pastas para 291 pacotes: 14 não trouxeram texto, e nada diz se algum deles fica no pacote. Fazer a montagem listar os pacotes **mantidos** sem texto e parar se a lista não for a esperada. O teste também deveria exigir, pelo nome, as pastas de `qt6-main`, `pyside6`, `occt`, `ifcopenshell` e `python`.
2. **O job `appimage` não bloqueia merge.** Então, no Linux, nem o teste de licenças nem o inventário rigoroso seguram um merge (no Windows seguram, pelo job `windows`). Ver pergunta 1.
3. A "troca de biblioteca" do teste acrescenta um byte ao arquivo. Prova o que a licença pede (não há trava de hash nem de assinatura). Não prova compatibilidade com outra compilação do Qt; isso fica para o primeiro release.
4. Textos velhos: `F0-S02.md` ainda diz 482 MB e "AppImage só na máquina do líder"; `packaging/README.md` linha 7 ficou truncada; o comentário da linha 42 do script promete um teste de pastas do VTK com arquivos que não existe; o padrão `libav*` do teste também pegaria `libavif` (erraria para o lado seguro).

Lembrete para a S04, vindo do texto da exceção do OCCT: quando o nosso C++ incluir cabeçalhos do OCCT, a documentação e a tela "Sobre" precisam dizer com destaque que o programa usa o Open CASCADE Technology.

## Item 1b: instalador Windows (T18): APROVADO, com 1 defeito novo
| # | Defeito do lote 2 | Situação | Evidência |
|---|---|---|---|
| 1 | Desinstalar apagava a pasta inteira | Corrigido | `openbim-studio.nsi` linhas 63 a 69: apaga só `env\`, `app\`, `licenses\` e os arquivos soltos; `RMDir` sem `/r` no fim. `test_installer.sh` linhas 69 a 77: um arquivo do usuário sobrevive |
| 2 | Isolamento do Python não funcionava | Corrigido | Atalhos com `pythonw.exe -I` (linhas 46 e 48); o teste abre com `PYTHONPATH`, `PYTHONHOME` e `PYTHONUSERBASE` "sujos" |
| 3 | Teste 7 incompleto | Corrigido | DLL do Qt alterada; instalar por cima (limpa antes e o teste confere que a DLL original voltou); para com erro se instalar passar de 300 s ou abrir passar de 10 s |
| 4 | Textos de licença | Corrigido | Os mesmos 4 textos na raiz de `licenses\`; a montagem para se faltar; o teste exige |

Riscos 5 a 7 do lote 2: `AddSize` feito; limpeza se a extração falhar feita; NSIS fixo em versão e build; `reuse` fixo em versão; `runtime-environment.yml` movido. **Não feitos:** barra de progresso (há só uma frase avisando que a janela pode parecer parada; o cartão pedia a barra), `miniforge-version: latest`, arquivo de trava do ambiente de runtime.

Defeito novo:
- **N1. Instalar numa pasta que já tem coisas ainda pode apagar arquivos do usuário.** Antes de extrair, o instalador faz `RMDir /r` em `env`, `app` e `licenses` dentro da pasta escolhida (linhas 28 a 30). Se a pessoa escolher uma pasta dela que já tenha uma subpasta com um desses nomes, o conteúdo some sem aviso; o desinstalador faz o mesmo. É bem menos provável que o defeito original, mas é perda de dados. Parte disso veio da minha própria recomendação no lote 2 ("limpar `env\` e `app\` antes"). Correção curta: na página de escolha da pasta, se a pasta existe, não está vazia e não é uma instalação nossa (não tem `Uninstall.exe` e `app\OpenBIM-Studio.pyw`), recusar ou acrescentar `\OpenBIM Studio` ao caminho. Teste objetivo no CI: instalar numa pasta com `app\meu.txt` e conferir que o arquivo continua lá. Classe T2, revisão sonnet. **Fazer antes de o PO rodar o roteiro T14 na máquina dele.**

Aprovo o T18 porque os 4 defeitos pedidos estão corrigidos e provados no CI; N1 é achado novo, com teste automático como oráculo, e não precisa de nova rodada do opus.

Observações:
1. O teste abre o programa chamando `python.exe -I` direto; se alguém tirar o `-I` do atalho, o teste não percebe. Conferir o texto do `.nsi` no teste já resolve.
2. Se a extração falha, sobram `app\` e `licenses\`, e a mensagem diz "nada foi instalado". Limpar os três.
3. Mensagem velha: "cerca de 480 MB" (hoje são 309 MB). O teste do Windows não conta as pastas de `licenses\pacotes` (o do Linux conta).
4. `packaging/runtime-environment.yml` ainda se descreve como "pacote Linux".

## Item 1d: as pendências aceitas pelo líder são aceitáveis?
**Sim**, para builds de teste da F0, com três condições:
1. O cartão "antes do primeiro release" existe no quadro (não conferi) e **bloqueia qualquer release público**. Entram nele: itens 8 a 10 do lote 2 **e** fixar o "runtime" do appimagetool.
2. Enquanto isso, os artefatos do CI continuam com guarda de 7 dias e tratados como "build de teste" (já está no `ci.yml`).
3. Ajuste de uma linha, agora (T0): o `FONTES.md` afirma que "o código-fonte exato é mantido junto da publicação". Hoje isso não é verdade. Trocar por um texto que diga o que existe (endereço exato de cada pacote e receita do conda-forge) até o cartão do release cumprir a promessa.

Sobre o runtime do appimagetool: segue "de memória, a conferir" que ele é baixado na hora da montagem. Se for, uma peça sem versão fixa entra no pacote. Aceitável em build de teste; não em release.

## Item 2a: T19 (teste 2 no Windows e sonda 3b): amostra aprovada
- **Os resultados batem com as conclusões.** `sonda_ifcopenshell.py` lê a tabela de importação do `.pyd` e procura bibliotecas `ifc*`; o método é correto para a pergunta "o módulo Python liga em DLL separada ou embute cópia". O relato (DLLs `parse`, `geometry`, `plugin`; o `.pyd` importa essas DLLs) sustenta "4 de 4 sim". Não vi a saída bruta do CI.
- **Sonda 3b:** o programa inclui `ifcparse/file.h`, liga pelo `IfcOpenShellConfig.cmake` e abre um IFC de 87 entidades nos dois sistemas. Como só há um arquivo-fonte, o "incremental" é o custo de recompilar um arquivo com o cabeçalho pesado: cerca de 4 s no Linux e 6 s no Windows. A conclusão "não é problema de tempo" vale para os cabeçalhos de leitura; os de geometria (com OCCT) não foram medidos.

Lembretes para a S04 (já no ADR-005 §7.1, provas 7 a 10):
1. O teste 3 original (nanobind + OCCT + Qt) **não rodou no Windows**. A sonda 3b é um executável simples e não o substitui.
2. A sonda instala `zlib`, `libxml2-devel` e `libboost-devel` na hora, sem versão. Eles têm de ir para o `environment.yml` e para a trava.
3. Os dois passos do CI são informativos: nunca reprovam. Um build novo do pacote com biblioteca estática passaria sem aviso. O `ifcopenshell` está fixo só na versão, não no build.
4. O MSVC usado é o do runner. O runtime do Visual C++ que vai no instalador tem de ser igual ou mais novo que o do compilador.

## Item 2b: T20 (inventário de licenças): amostra reprovada
O desenho está certo: lista de licenças permitidas, regra para "OR" e "AND", exceções uma a uma presas à versão, checagem só sobre o que fica no pacote, e a montagem para se reprovar. Os testes cobrem o que o cartão pediu.

Defeito:
- **D1. Expressão com parênteses passa sem ser conferida.** O leitor corta o texto em "OR" antes de olhar os parênteses. Testei: `(MIT OR Proprietary) AND LicenseRef-NVIDIA` é **aceita**; `MIT AND (GPL-2.0-only OR BSD-3-Clause)` é aceita pelo motivo errado. É um portão de licença que abre quando devia fechar. Correção: ler os parênteses de verdade ou, mais simples, reprovar toda expressão que tenha parênteses internos (o pacote então entra como exceção nomeada). Acrescentar testes com esses dois exemplos.

Ajustes:
1. Tirar `AFL-2.1` e `FreeImage` da lista. Sozinhas não são compatíveis com a GPL; só aparecem em licença dupla (dbus, FreeImage), e a regra do "OR" já aprova esses pacotes pela opção GPL. Testei: continuam passando.
2. Exceção do `cgal-cpp`: trocar "GPL-3.0-only **OR** LGPL-3.0-only" por "GPL-3.0-or-later **AND** LGPL-3.0-or-later". O CGAL não oferece escolha: parte dele é GPL, parte é LGPL. O resultado não muda (as duas são permitidas), mas o registro atual sugere uma escolha que não existe.
3. Teste que falta: um pacote qualquer declarando `LicenseRef-Microsoft-Redistributable` tem de reprovar. O código já faz isso (testei); o teste com esse nome não confere.

Sugestão: prender cada `LicenseRef-*` da lista ao nome do pacote que a usa.

**As exceções de versão fixa são aceitáveis?**
| Exceção | Parecer |
|---|---|
| `tbb-devel` 2023.1.0 | Aceitável, como no lote 2 |
| `ucrt`, `vc14_runtime`, `vcomp14` | **Aceitáveis.** São as bibliotecas de apoio do compilador da Microsoft, que ela permite redistribuir junto de programas e que todo programa C++ no Windows leva. Na AGPL v3 elas entram como "bibliotecas de sistema" e não precisam ter o código-fonte fornecido. Condições: só os arquivos da lista redistribuível, sem alteração, e os termos anotados no `THIRD_PARTY.md` (não conferido). É o ponto em que mais vale ouvir um advogado antes do primeiro release, por causa das bibliotecas LGPL-2.1 (OCCT e outras) que ligam nelas. Opcional: o `ucrt` já vem no Windows 10 e 11 e poderia sair na poda, o que elimina uma exceção |
| `cgal-cpp` 6.2.1 | Aceitável, com o ajuste 2 |

Prender à versão só funciona se a versão não mudar sozinha: hoje o ambiente de runtime não tem arquivo de trava, então uma atualização do conda-forge pode reprovar a montagem de um dia para o outro. É o lado seguro, mas vai parar o CI sem aviso (ADR-005 §9.1, item 2).

**A troca do MKL pelo OpenBLAS cobre a obrigação?** **Sim.** `libblas=*=*openblas` faz o conda escolher a família OpenBLAS (BSD), e há segunda proteção: se o MKL voltar por outro caminho, a licença dele não está na lista e a montagem para. A queda de 482 para 309 MB é coerente com a saída do MKL. Dois complementos: (1) pôr a mesma linha no `environment.yml` (não conferido), para testar com a mesma biblioteca que é distribuída; (2) acrescentar `mkl*.dll` à lista de ausências do `test_installer.sh`.

**O teste 9 do ADR-005** fica "atingido nos números" e fecha quando D1 for corrigido com a montagem ainda verde.

## Item 3: ADR-005
Arquivo: `docs/adr/ADR-005-dependencias-e-build.md`. Entregue como "proposto, aguardando o PO"; o PO aprovou no chat em 2026-10-11 e o status passou a **"aceito"**.
- §3.1 e §3.2: resultados e tabela "meta × medido" (309 MB em ~1004 s; 389 MB; Linux ~94 s).
- §4: decisão (conda-forge como fonte única; pasta do ambiente com poda; NSIS e AppImage; sem MKL; MSVC no Windows), resposta explícita sobre versão e ABI, e a frase sobre o portão da F0 (o NO-GO parcial não disparou).
- §7.1: o que a S04 deve provar, agora com 10 provas (as 6 do lote 2 e mais 4).
- §9.1: o que continua em aberto, a começar pelo build incremental do Windows (~16 min contra 10 min).

O cartão T15 pedia status "aceito"; segui o pedido do lote ("proposto, aguardando o PO"), porque ADR é aprovado pelo PO.

## O que o líder faz em seguida
1. BOARD, LOG e `PO.md`: T17 e T18 aprovadas; T19 amostra aprovada; T20 amostra reprovada (1ª vez); T15 concluída, ADR-005 aceito pelo PO; registrar as duas respostas do PO abaixo.
2. Cartão T2 curto: N1 do instalador, com o teste de pasta já ocupada. Antes do roteiro T14.
3. Cartão T2 curto: D1 e os 3 ajustes do inventário. Revisão sonnet.
4. Cartão T0/T1: observações dos itens 1a e 1b e a frase do `FONTES.md`.
5. Conferir que o cartão "antes do primeiro release" existe e inclui o runtime do appimagetool.
6. Incluir o job `appimage` na regra de bloqueio do `main` (autorizado pelo PO; a alteração da regra é do líder, não foi feita neste lote).
7. Anotar a cota desta sessão em `QUOTA.md` (pedir os percentuais ao PO).

## Perguntas ao PO (com recomendação): respondidas "sim para tudo" no chat em 2026-10-11
1. **O teste do pacote Linux (AppImage) hoje não impede um merge; o do Windows impede.** Posso pedir ao líder que inclua o job `appimage` na regra de bloqueio do `main`? **Recomendo sim**: custa cerca de 3 minutos por execução e é o único lugar onde as licenças do pacote Linux são conferidas. Mexe na regra do `main`, por isso precisa do seu ok.
2. **Aprovar o ADR-005 como proposto?** Recomendei sim. **Resposta: sim.**

Resposta à pergunta 1: **sim.**
