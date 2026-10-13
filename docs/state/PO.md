# Perguntas ao PO

> Cada pergunta traz a recomendação do líder. Sem resposta, vale a recomendação como decisão assumida, registrada aqui. Atualizado: 2026-10-10.

## Abertas
| # | Pergunta | Recomendação do líder | Resposta do PO |
|---|---|---|---|
| P1 | Quais os percentuais de `/usage` (janela de 5 h e semana), antes e depois desta sessão, para a primeira linha de QUOTA.md? | Informar os quatro números; se não anotou o "antes", informar só o "depois" | 2026-10-10: janela 22%→29%; semana 2%→3% (registrado em QUOTA.md) |
| P2 | Licença AGPL v3 "somente" ou "ou qualquer versão posterior"? (06 diz só "AGPL v3"; o texto vai nos cabeçalhos dos arquivos) | "Ou posterior" (AGPL-3.0-or-later): é o padrão recomendado pela FSF e mais flexível. O ADR-009 confirma | 2026-10-10: **ou posterior** (AGPL-3.0-or-later) |
| P3 | Posso ler páginas públicas na internet (arquivos LICENSE, páginas de pacotes) na sessão 2, sem baixar nem instalar nada? | Sim. Download e instalação continuam pedindo ok um a um | 2026-10-10: **sim**; PO pediu haiku para a leitura das páginas. Haiku busca e transcreve; sonnet interpreta e escreve a ficha |
| P4 | Aprova a estrutura de pastas proposta (`app/`, `prototypes/`, `packaging/`, `corpus/`, `tests/`, `docs/`, `.github/workflows/`) e o texto da licença AGPL ficar fora do limite de 400 linhas? | Sim aos dois | 2026-10-10: **aprovado** (estrutura e LICENSE fora do limite de 400) |
| P5 | No app esqueleto da S02, a área da viewport será só um painel reservado (a viewport real é a S03). Ok? | Sim | 2026-10-10: **ok** (painel reservado) |
| P6 | Posso rodar `git init` local na sessão 2? As contas no GitHub e no Codeberg e a criação do repositório vazio são suas; eu guio passo a passo | Sim; criar as contas antes da sessão 2 | 2026-10-10: **git init local autorizado**; contas e repositório remoto ainda a cargo do PO |
| P7 | Qual o hardware da sua máquina Linux e da Windows (CPU, RAM, placa de vídeo, sistema)? (pergunta E de 06) | Informar até a S03; o padrão é 4 núcleos, 16 GB, vídeo integrado recente | 2026-10-10: Linux nativo; Windows via VM. CPU i5-12600KF, GPU RTX 3070, 24 GB RAM |

## Respostas do lote Opus 1 (2026-10-10, confirmadas pelo PO neste chat)
| # | Pergunta | Resposta |
|---|---|---|
| L1 | Aprovar o ADR-009? | **Sim** (aceito) |
| L2 | WiX fora; instalador Windows parte do NSIS? | **Sim** |
| L3 | Cartão novo na S02 (sonda C++) e arquivos gerados fora do limite de 400 linhas (S02-T03, S02-T06)? | **Sim** |
| L4 | Líder ajusta `v2/05` §3? | **Sim** (feito em 2026-10-10; conferência no lote 2) |
| L5 | Páginas de termos do conda-forge e do SINAPI no navegador | Opcional, aberto |

## Decisões já tomadas (06 §1)
10 posicionamento geral, Brasil como primeiro pacote regional (2026-10-10) · 1 corte da 1.0 · 2 Claude Pro, sonnet líder · 3 corpus do PO depois da F0 · 4 PO testa Windows e Linux, Mac melhor esforço · 5 IFC limpo + `.obim` lateral · 6 AGPL v3 · 7 sem gasto extra · 8 par `.ifc` + `.obim` com `.obimpack` para envio · 9 pset `OBIM_Projeto` aceito.

## Padrões assumidos (06 §2, sem resposta ainda)
C hospedagem GitHub + espelho Codeberg · D interface híbrida (confirmar na S09) · F gravação IFC4 e exportação IFC2x3 como critério de portão · G SignPath na v0.3 · H nome provisório "OpenBIM Studio" · I sem IA embutida na 1.0 · J consulta à CAIXA (SINAPI) só na F5.

## Decisões do PO após o lote Opus 2 (2026-10-11)
- Mesa fora do AppImage: manter fora; testar em máquina virtual sem aceleração no roteiro T14 (se não abrir, o Mesa volta).
- Download dos textos oficiais (exceção do OCCT, LGPL-3, LGPL-2.1, GPL-3) para o repositório: autorizado (uma vez, para esses quatro).
- Artefatos do CI: guarda de 7 dias; tratados como builds de teste.
- Build incremental do Windows (~16 min contra meta de 10): **opção 1, aceitar agora e revisitar na S04** (2026-10-11).
- Autorização permanente para ramos de trabalho, PR e merge de T0 a T2 aprovadas: registrada no `CLAUDE.md` (2026-10-11).
- Licenças do Windows (2026-10-11): trocar MKL por OpenBLAS no ambiente de runtime; aceitar `ucrt`, `vc14_runtime` e `vcomp14` (runtimes redistribuíveis da Microsoft) por exceção nomeada e amarrada à versão; incluir `BSD-3-Clause-Clear` na lista de permitidas.

## Decisões do PO após o lote Opus 4 (2026-10-11)
- S03: aceitar que a janela pare pelo tempo de um elemento muito pesado (0,2 s numa parede com 150 aberturas); solução fica para a S04/ADR-004.
- S03: a leitura de v2/03 "tesselação via IfcOpenShell C++" está atendida pelo iterador C++ do IfcOpenShell chamado do Python (sem módulo C++ nosso na S03).
- Modelo grande da S03: sintético por script; IFC real do PO só na T07, com arquivo indicado no chat.

## Decisões do PO após o lote Opus 6 (2026-10-12)
- S03/T08: biblioteca de geometria "híbrida" como padrão da visualização (comparação lado a lado antes de fechar a T08). Limite de 20 s por peça (peça lenta vira caixa laranja). Aprovado.
- T26: passo no job Linux do GitHub que cria a localidade pt_BR, só na máquina descartável. Aprovado.
- Tamanho: exceção aceita para o oráculo da T05 e o relatório da Parte B (>400 linhas).

## Decisões do PO após a T08-D (2026-10-12)
- Meta de memória de 6 GB: aceita "atingida na prática" para o arquivo real de 8,6 milhões de triângulos (maior soma ao mesmo tempo 6,2 GB com placa real; conta conservadora 6,8 GB). O valor final da meta é decidido na S04 com o modelo real e revisão do Opus. Windows: a VM do PO não tem placa real; vale só o teste automático (software) e o roteiro funcional.
- Execução única na tela real autorizada e feita (Linux, placa real): abrir 36,6 s, atraso máximo 62 ms, 60 FPS.

## Decisão do PO após o relatório da S03 (2026-10-12)
- Portão da S03 dado como atingido (Linux com placa real; Windows em software). Risco registrado: placa de vídeo real e Intel integrada no Windows só medidas num computador físico, antes do portão final da F0 (S10).

## Decisões do PO após o lote Opus 9 (2026-10-12)
- Regra do "3 vezes mais lento": o portão do híbrido são as metas absolutas (M1 a M5). A razão contra o C++ puro (M6) é número de acompanhamento, registrado no ADR-001; só pesa se alguma meta absoluta ficar com menos de 2× de folga.
- Ambiente: autorizado acrescentar `zlib`, `libxml2-devel` e `libboost-devel` (conda-forge) e guardar a lista travada de pacotes dos dois sistemas (cartão S04-T01). Qualquer outro pacote pede novo ok.
- Regra do processo: o líder abre o lote Opus como subagente e mescla T3 aprovada com testes verdes (CLAUDE.md, item 6 e 3, editado pelo PO).

## Decisões do PO sobre catálogo de ferramentas e entrevista S09 (2026-10-12)
- "Pode seguir com as recomendações" nas 5 decisões do catálogo (`docs/design/catalogo-ferramentas-f1-f2.md`): telhado e escada na F4 (o plano v2/02 prevalece); pavimento com uma única ação (mudar a cota); manter a meta de 30 s de recuperação com aviso honesto; PO testa à mão os 6 comportamentos antes da F2-S04 e F2-S08; nomes nossos em português ("Modo A/B", cubo de vistas, ajustes salvos).
- Entrevista S09: só anotações (sem áudio). Programa mais usado pelo PO: Revit (já usou ArchiCAD); referência de atalhos e navegação 3D = Revit.

## Exceção de ausência do PO (2026-10-12, pedida no chat)
- O PO vai ficar longe do computador e pediu que o desenvolvimento siga sozinho; "se precisar de autorização, abra esse período como exceção". Valor: o líder segue as próprias recomendações nas decisões que normalmente pediria ao PO, **dentro** da autorização permanente do CLAUDE.md. Continuam do PO e ficam na fila `PO.md` (o líder para essa frente e segue com outra): ADR, meta do portão, escopo, licença, regras do processo e CLAUDE.md, instalar ferramenta nova, baixar arquivo, cota extra, apagar dados, credenciais, `main` direto, execução na tela real, meta de F0 não atingida. Lotes Opus só com uso semanal >25% restante e janela <60%.

## Exceção de ausência do PO (2026-10-13, nova, pedida no chat)
- O PO vai ficar longe de novo (estágio) e pediu que o desenvolvimento siga sozinho, abrindo este período como exceção. Valem as mesmas regras da exceção de 2026-10-12 (acima): o líder segue as próprias recomendações, dentro da autorização permanente do CLAUDE.md; ficam na fila e **param essa frente** (o líder segue com outra) as decisões de ADR, meta do portão, escopo, licença, regras do processo e CLAUDE.md, instalar ferramenta nova, baixar arquivo, cota extra, apagar dados, credenciais, `main` direto, execução na tela real e meta de F0 não atingida. Lotes Opus só com uso semanal >25% restante e janela <60%.
- Perguntas guardadas para a volta: as 6 decisões do catálogo de anotação (`docs/design/catalogo-ferramentas-f3-anotacao.md`, seção 4), partes 2 e 3 da entrevista da S09, desenho de UI do PO (pasta `design/`).

## Decisões do PO (2026-10-13): transparência e macOS
- **macOS: "melhor esforço, sem garantia".** O build de macOS segue experimental, sem teste manual e sem bloquear merge. Isso **deve constar no aviso aos usuários**: README (feito no rascunho de transparência), página de download e instalador/notas de versão, em pt-BR e inglês. Nenhum texto pode prometer suporte a macOS.
- Pedido do PO após ler críticas da comunidade OSArch a programas feitos com IA: (1) texto de transparência no README (rascunho em `docs/design/rascunho-transparencia-readme.md`, **a aplicar só após o ok do PO**); (2) cartão `F1-PRE-T01` de comportamento básico de janela e navegação com testes de regressão, antes da Fase 1; (3) pacote e convite para revisão humana externa em `docs/review/` (**nada enviado; o PO decide quando e para quem**); (4) este registro do macOS. Nenhuma resposta ou publicação em fórum em nome do PO.
