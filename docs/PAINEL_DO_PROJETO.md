<!--
SPDX-License-Identifier: AGPL-3.0-or-later
-->
# Painel do projeto OpenBIM Studio

Para o PO. Uma página para saber **onde estamos, o que está decidido, o que entra onde e o que falta decidir**. Atualizado em 2026-10-18 (S04 com a medição oficial feita; lote 57 do Opus em execução; plano `v2/02` na Revisão 3). O líder atualiza no fim de cada sessão. Detalhes: `docs/state/BOARD.md` (quadro), `docs/state/PO.md` (decisões), `v2/02_plano_mestre_v2.md` (plano).

## 1. Em que fase estamos
**Fase 0 (provas técnicas), com a S04 em andamento, na fase de decisões.** Das 10 fatias, 3 estão concluídas e aceitas por você (S01, S02, S03). A S04 (ponte entre Python e C++) voltou a andar depois da revisão geral: a ponte em C++ já está no AppImage e no instalador do Windows, e a **medição oficial na sua placa de vídeo foi feita em 2026-10-17**. Três metas ficaram **não atingidas** e você mandou manter todas, sem afrouxar nada (seção 3). Agora o Opus planeja as opções de redução (lote 57, em execução) e depois vêm as suas decisões: opções de memória e de atualização da geometria, e as decisões de arquitetura (ADR-001 e ADR-004, T19). A S09 (interface com você) tem a entrevista aceita (15/10); faltam os desenhos de tela. Ainda não existe programa utilizável.
**Cota (Claude Pro; `QUOTA.md`):** em 2026-10-17 o uso semanal estava entre 84% e 87%, e a semana renova em 2026-10-21 às 09:00 (UTC). A janela de 5 h passou de 100% duas vezes em 16 e 17/10. O registro de cota termina em 17/10: não há percentuais depois dessa data, nem o consumo do lote 57.

## 2. Plano principal (as 7 fases)
**Atenção aos prazos:** a tabela abaixo ainda mostra a faixa antiga. O escopo cresceu um pouco com as decisões de 13/10, mas os prazos **não foram recalculados**: serão refeitos depois da medição da Fase 0 (portão S10), com a velocidade real. Se a faixa subir mais de 30%, cortamos escopo primeiro; os candidatos são fundações, importar padrões e a biblioteca de itens de detalhe.

| Fase | O que entrega | Prazo estimado (acumulado) | Situação |
|---|---|---|---|
| **F0** Provas técnicas | Decidir se a arquitetura funciona (Python + C++), instaladores, testes automáticos | 2 a 4 meses | **Em andamento** |
| **F1** Visualizador (v0.1) | Abrir IFC, navegar em 3D, árvore, propriedades, medir, cortes, salvar sem perder dados, instalador | 4 a 8 meses | Não iniciada |
| **F2** Modelagem básica (v0.2) | Desenhar casa: níveis, eixos, paredes, piso, forro, rodapé, pilares, vigas, portas, janelas, desenho 2D de detalhe, editar, desfazer | 8 a 16 meses | Não iniciada |
| **F3** Documentação essencial (v0.3, "Planta Legal") | Ambientes, plantas e cortes, cotas, texto, pranchas com carimbo, importar padrões, PDF, quadro de áreas | 11 a 22 meses | Não iniciada |
| **F4** Modelagem residencial completa (v0.5) | Telhado, escada, guarda-corpo, terreno, bibliotecas, tipos por script | 14 a 29 meses | Não iniciada |
| **F5** Documentação executiva (v0.8) | Fachadas, cortes múltiplos, nuvem de revisão, tabelas, DXF, religar referências | 18 a 36 meses | Não iniciada |
| **F6** Estabilização e **1.0** | Desempenho, manual, tutoriais, instalador assinado, testes com arquitetos reais | **21 a 42 meses** | Não iniciada |

Portões (você decide se passa): F0 (go ou não go da arquitetura), F1 (roteiro de 30 min com 3 IFCs), F2 (casa de 60 m² em até 2 h), v0.3 (planta, corte e quadro de áreas em 1 dia), F4 (sobrado com telhado de 4 águas e escada), F5 (projeto legal + 5 pranchas executivas), 1.0 (um projeto real seu, sem outro programa, 8 h sem travar).

## 3. Plano ramificado: a Fase 0 em fatias
| Fatia | O que é | Situação |
|---|---|---|
| S01 | Repositório, licenças, pesquisa | **Feita** |
| S02 | Testes automáticos Windows + Linux e programa esqueleto | **Feita** (você aceitou) |
| S03 | Protótipo de visualização 3D | **Feita** (você aprovou o portão) |
| **S04** | **Ponte entre Python e C++ (decide a arquitetura)** | **Em andamento; aguarda você** (ver abaixo) |
| S05 | Desfazer, refazer e gravar o par `.ifc` + `.obim` | Não iniciada (depende da S04) |
| S06 | Planta e corte automáticos (HLR) | Não iniciada |
| S07 | Tipo paramétrico por script | Não iniciada |
| S08 | Corpus de modelos de teste | Contínua |
| **S09** | **Interface com você (entrevista e desenhos de tela)** | **Entrevista feita e aceita (15/10, com um ajuste); faltam os desenhos de tela** |
| S10 | Calibração e portão da F0 | Não iniciada |

### Dentro da S04 (23 tarefas numeradas, algumas em partes; em andamento)
| Tarefa | O que é | Situação |
|---|---|---|
| T01 a T04c | Ambiente de compilação e a ponte básica | Feitas |
| T05 a T08 | Janela 3D em C++ dentro do Python, desenho e captura | Feitas |
| T09, T10, T10c | Câmera, clique com precisão de triângulo e escala de tela | Feitas |
| T11, T11b, T11c | Fluxo A: comandos em Python (criar, mover, desfazer) | Feitas |
| T12 | Medições e comparação A × B (código das provas) | Feita; a rodada oficial rodou em 17/10 (T18) |
| T13, T14, T14a a T14d | Fluxo B: paredes em C++, núcleo sem janela e agora com janela Qt | Feitas |
| T15 (a a i) | Threads: provas, medições no Linux, no Windows do CI e na placa real, relatório | Feitas; falta confirmar 3 rodadas seguidas do Windows no CI sem queda (T15f/g) |
| T16, T16b | Abertura de arquivos grandes (peças lentas) | Feitas |
| T17 (a Linux, b Windows) | Módulo `obimcore` dentro do AppImage e do instalador | **Feita** (pedidos 152 e 155 mesclados em 17/10; instalador de 310,6 MB; Opus aprovou nos lotes 53 e 56) |
| T18 | Tempos de build, medição oficial e relatório da fatia | **Medição feita (17/10)** e relatório no `main`; falta o roteiro de aceite, que depende do T19 |
| T19 | **Decisões de arquitetura (ADR-001 e ADR-004), com você** | Não iniciada; números oficiais prontos; vem depois do lote 57 |
| T20 | Memória do viewport abaixo de 6,0 GB (cartão-mãe) | Pausada; meta mantida; a implementação espera a sua escolha |
| T21 | Onde vai a memória ao abrir o arquivo pesado | Medição feita e relatório no `main` (pedido 163) |
| T22 | O que pesa na troca de geometria em IFC real | Relatório completo no `main` (pedido 161) |
| T23 | Encurtar a cadeia de testes do Windows no CI (meta de 10 min) | Rascunho; **espera o seu ok** e 3 respostas |
| T04b | Registro local de mensagens e fim do mutex | Pausada |

### Medição oficial da S04 (2026-10-17, Linux, RTX 3070; `reports/F0-S04.md`)
| Meta | Resultado | Situação |
|---|---|---|
| Base de 3.000 paredes: M2, M2b, M3, M4, M5, saída igual | Todas passaram (M2b: p95 de 65,9 ms contra 200 ms) | Atingidas |
| Abrir os 3 arquivos reais em até 60 s | 1,75 s, 19,2 s e 40,5 s | Atingida |
| Memória do arquivo pesado, menos de 6,0 GB | **6,84 GB** (simples 0,98 GB; detalhado 5,06 GB) | **Não atingida** |
| Trocar a geometria em IFC real (M2b), menos de 200 ms | **399 ms** (25 MB) e **6.749 ms** (detalhado) | **Não atingida** (na base sintética passa) |
| Threads: parede de 150 aberturas | Forma 2 (fatias na janela): cerca de 200 ms contra o limiar de 101,6 ms; forma 1 (thread à parte): 2 a 9 ms | **Forma 2 reprova**; decisão formal no T19 |
Decisão sua (17/10): manter metas e réguas rigorosas; cartões T21 e T22 para entender, T20 para reduzir; threads no T19. O T22 mostrou que quase todo o tempo é espera do quadro novo (74%, 97% e 99,6% do total), com a cena inteira provavelmente reenviada a cada troca; é hipótese, ainda não provada. O T21 mostrou que o processo filho tem cerca de 5,7 dos 6,8 GB e que nenhuma combinação de fios e blocos cumpre memória e tempo ao mesmo tempo.

### Lotes do Opus (revisão e planejamento)
| Lote | O que foi | Resultado |
|---|---|---|
| 52 e 53 | Módulo no AppImage (T17a) | 52 reprovou; 53 aprovou depois das correções |
| 54, 55 e 56 | Módulo no instalador do Windows (T17b) | 54 reprovou; 55 reprovou só por processo (pedido de 441 linhas, acima do limite de 400, dividido em dois; e o autoteste do oráculo não rodava no CI, passou a rodar); 56 aprovou, com o CI verde antes da mesclagem |
| 57 | **Planejamento** das reduções de memória (T20, fase 1) e do M2b (T22): 2 a 3 opções para cada, sem implementar | **Em execução em 2026-10-18** |

## 4. O que entra onde (ferramentas)
**F1** (ver): navegar em 3D, **voar (botão direito do mouse mais W, A, S, D)**, atalhos configuráveis, cubo de vistas, enquadrar, selecionar, filtro por classe, navegador do projeto e árvore, propriedades, ocultar/isolar, transparência, cor por propriedade, **"Por que não vejo isto?" (versão mínima)**, caixa e plano de corte, medir, salvar sem perdas, instalador. Antes da F1: **testes de comportamento básico de janela e navegação** (cartão F1-PRE-T01).

**F2** (modelar): desfazer/refazer e recuperação, novo projeto com modelo brasileiro, níveis, eixos, paredes com camadas e junções, **Piso** (laje e piso numa ferramenta só), **Forro** e **Rodapé** (depois das portas; por contorno e por parede), pilar, viga, porta, janela, snaps, digitar medida, cotas temporárias, mover, copiar, girar, espelhar, alinhar, aparar, atalhos de duas letras, tipos e propriedades, navegador organizável em pastas, favoritos, e **desenho 2D de detalhe (linha, região preenchida e itens de uma biblioteca pequena nossa)**, ainda antes da F3.

**F3** (documentar): ambientes e áreas, plantas e cortes automáticos, gráfico por categoria e hachuras, cotas que acompanham o desenho (linear, alinhada e de nível), tag de ambiente, **texto simples**, tag por atributo (sem criar família nova), "Por que não vejo isto?" completo, folha por modelo de folha, pranchas com carimbo (campo livre "revisão"), PDF, quadro de áreas, **importar padrões de outro projeto (escolhendo quais)**, versão mínima de referências quebradas (lista e contagem), forro e rodapé "por ambiente".

**F4** (completar): telhado, escada, guarda-corpo, terreno, revestimentos por ambiente (só o que não for piso), componentes de biblioteca, tipos por script, **fundações (candidatas; só o elemento, sem cálculo)**, tags por categoria, quadro de esquadrias e de materiais, legendas.

**F5** (executivo): fachadas, cortes múltiplos, planta de cobertura, **nuvem de revisão**, símbolos, tabelas na prancha, DXF, **religar referências quebradas**, IFC para outros programas.

**Fora da 1.0 (2.0 ou depois):** cota que move a parede, chamada e vista de detalhe, controle completo de revisões (letra, data, tabela), vista mestre estilo ArchiCAD, análises (solar, iluminação, energia, estrutural; possíveis como plugin opcional), editor gráfico de famílias, colaboração em tempo real, macOS com garantia.

## 5. O que está decidido
- **Produto:** programa aberto (AGPL), Windows e Linux obrigatórios, macOS "melhor esforço, sem garantia"; Brasil como primeiro pacote regional; sem conta, nuvem ou telemetria.
- **Arquivos:** IFC limpo + arquivo lateral `.obim` (vistas, pranchas, cotas); pacote `.obimpack` para enviar.
- **Interface:** híbrida (navegador e propriedades à Revit; caixa de ferramentas e favoritos à ArchiCAD); vistas independentes como no Revit; abas de vistas; navegador e propriedades em abas no mesmo painel; atalhos de duas letras configuráveis (TR, AL, MM, MI, RR, CC, TG, WA).
- **Escopo (13/10), já aplicado ao plano `v2/02` (Revisão 3):** detalhes 2D e nuvem de revisão entram na 1.0; texto simples na F3; importar padrões com seleção na F3; referências quebradas mínimas na F3; Piso unificado, forro e rodapé na F2; fundações candidatas da F4 (só o elemento); telhado e escada na F4; voar no 3D e "Por que não vejo isto?" na F1; navegador organizável em pastas; atalhos de duas letras (uma letra só como opção em Preferências); tags por atributo; folha por modelo de folha; análises fora do núcleo. Prazos **não recalculados** até a medição da F0.
- **Processo:** testes escritos por agente diferente do que escreve o código; revisão do Opus para partes críticas; tudo registrado em `docs/state/` (relatórios, lotes Opus e LOG).
- **Metas da S04 (17/10):** padrão rigoroso. Manter todas as metas e réguas; as 3 metas não atingidas viram cartões de análise (T21, T22) e de redução (T20), sem afrouxar nada; nenhuma opção que só passe porque uma peça deixou de ser desenhada vale. Mudar métrica ou meta só aparece como decisão sua, nunca como recomendação para fechar a tarefa. O portão da F0 é reavaliado com as metas originais.
- **CI do Windows (17/10):** manter a meta de 10 min do build incremental, sem folga, e abrir cartão para encurtar (T23). Arquivos reais seus liberados só para os cartões T21 e T22; roteiro de aceite da S04 escrito depois do T19.
- **Transparência:** texto no README sobre quem faz e como; revisão externa será convidada quando você decidir.

## 6. O que ainda precisa decidir (com recomendação)
| # | Decisão | Quando | Recomendação |
|---|---|---|---|
| 1 | ~~Aprovar a atualização do plano (`v2/02`) com as 14 mudanças de escopo~~ | **Resolvido (13/10)** | Aprovado; plano na Revisão 3. **Prazos não recalculados**: refazer a faixa de 21 a 42 meses depois da medição da F0 (S10) |
| 2 | **Aceite da entrevista** (resumo, respostas, híbrido): você disse "de acordo" | Feito | Wireframes podem começar |
| 3 | **Wireframes** (desenhos de tela): quando você mandar as imagens da pasta `design/` | Quando puder | Mandar as imagens que já fez; o líder cruza com o catálogo |
| 4 | **ADR-004** (processos, threads e trava do modelo; rascunho no PR 101) e **ADR-001** (híbrido ou C++ puro), no cartão T19 | Depois do lote 57; números oficiais já prontos (`reports/F0-S04.md` e `F0-S04-threads.md`) | Ler os números e escolher. A parede de 150 aberturas reforça o cálculo da malha em thread própria; para comandos Python longos o relatório prefere, por margem pequena, a forma 2 (fatias na janela), e você observou no chat que os números reforçam a forma 1 (thread à parte). A escolha formal é sua |
| 5 | ~~Execução na tela real do Linux (medida oficial)~~ | **Resolvido (17/10)** | Feita, 18:25 a 19:04. O Windows com placa real segue pendente (T28, dono: você, antes da entrega final) |
| 6 | **Meta do portão F0**: 3 metas não atingidas (memória do pesado, M2b em IFC real, parede de 150 aberturas na forma 2) | Registradas em 17/10; memória e M2b: opções no lote 57; threads: T19 | Escolher entre as opções do Opus sem afrouxar meta. Mudar métrica ou meta só entra como decisão sua, com o impacto e a meta original ao lado, nunca como recomendação |
| 7 | **Quando e para quem enviar o convite de revisão externa** | Quando quiser | Depois da S04 fechada |
| 8 | ~~Navegador do projeto: pastas livres ou categorias fixas~~ | **Resolvido (13/10)** | Pastas livres + agrupamentos prontos (F1-S03 e F2-S10) |
| 9 | ~~"Por que não vejo isto?" na F1 em versão mínima~~ | **Resolvido (13/10)** | Sim (F1-S05; versão completa na F3) |
| 10 | **8 testes no Revit** (cota alinhada, tag de porta, quadro de esquadrias etc.) | Antes da F2-S08 e da F3 | Fazer quando estiver com o programa aberto |
| 11 | **Cota que move a parede** (versão futura) e **chamada de detalhe** (depois da 1.0) | Já decidido como "depois" | Reabrir só se mudar de ideia |
| 12 | **Pendências menores sem prazo:** assinatura do instalador, placa de vídeo real no Windows (risco da S10), cartão T23 da S02 (antes do primeiro release) | S10 e F1 | Só informar |
| 13 | **Detalhes da fatia de desenho 2D** (F2-S11): tamanho e se a biblioteca de itens vira fatia própria | No planejamento da F2 | O líder propõe na hora de planejar |
| 14 | **Refazer a faixa de prazo (21 a 42 meses)** | Depois da S10 (medição da F0) | Só então; sem chutar números antes |
| 15 | **Escolher as opções do lote 57** (memória do arquivo pesado e atualização da geometria em IFC real): resumo de 5 linhas do Opus | Quando o lote 57 terminar | O Opus recomenda uma opção por item; as opções que mudam métrica ou meta (C, D e E do M2b) entram sem recomendação, como decisão sua |
| 16 | **Cartão T23 da S04** (CI do Windows em 10 min): ok ao rascunho e 3 respostas (como contar os 10 min; cartão irmão para o Linux; o que fazer se o CI sozinho parar em 15 a 17 min) | Quando puder; sem o ok não começa | Contar do começo ao fim do Windows numa alteração pequena; cartão irmão para o Linux depois da T23b; se parar em 15 a 17 min, parar e decidir com você |
| 17 | **Roteiro de aceite da S04** (o que você confere no AppImage e no instalador) | Depois da decisão do T19 | Nada a responder agora |
| 18 | **Texto do `CLAUDE.md`** (RG-28) e **limpeza de ramos antigos no GitHub** | Quando puder | Aprovar o texto exato; apagar ramos só com a sua palavra |
| 19 | **Perguntas menores abertas em `PO.md`:** confirmar que as exceções de ausência acabaram (A9), ambiente do instalador pela trava (A3), critério do instalador para o AppImage (A4), folga nos testes de tempo do Windows (A5), `/usage` para o registro de cota (A10), nomes dos colegas de estágio (A11), autorização da CAIXA para o SINAPI na F5 (A15) | Sem prazo | Ver a recomendação de cada uma em `PO.md` |
