# 06. Decisões (Revisão 2)

> Se não houver resposta, a recomendação padrão vale como decisão assumida e fica registrada. Todas podem ser revistas no portão da F0.

## 1. Decisões já tomadas pelo PO (Revisão 2)
| # | Decisão | Onde foi aplicada |
|---|---|---|
| 1 | **Corte da 1.0 aprovado**: residencial, legal + executivo ABNT; tipos paramétricos simples por script na 1.0; editor gráfico de famílias, colaboração, opções de projeto, clash e COBie na 2.0 | `02` §3, §8 |
| 2 | **Assinatura: Claude Pro padrão** (não Max). Sessão principal em `sonnet`; `opus` só para especificações, ADRs e revisão crítica, em lote; `haiku` só trivial; 1–2 subagentes; orçamento semanal; F0 mede a cota e define gatilho para subir de plano | `04` inteiro; `02` §14; `03` S10 |
| 3 | **Projetos do PO** (3–5 IFC4, idealmente também 2x3, + PDFs de prancha) virão depois; hoje nenhum pronto. A F0 começa só com IFCs públicos; corpus do PO não bloqueia nada | `03` S08; `02` §10, R15 |
| 4 | **Hardware de teste**: PO testa Windows e Linux. Mac fica para depois: build de CI melhor esforço, sem teste manual; portão formal de Mac só pós-1.0 ou com tester | `02` D8, §12, R12; `03` S02 |
| 5 | **Opção 2: vistas, pranchas, carimbos, viewports e revisões em arquivo lateral `.obim`**, IFC limpo e válido, sem IfcAnnotation de prancha | `02` §6; `03` S06; `01` §4 |
| 6 | **Licença AGPL v3 confirmada** | `02` D2; `05` |
| 7 | **Sem gasto extra** se o gatilho de plano disparar (pergunta A): o líder apresenta opções e o PO decide caso a caso | `04`; `02` §14 |
| 8 | **Par `Casa.ifc` + `Casa.obim` lado a lado como padrão**; `.obimpack` só para envio (pergunta B) | `02` §6 |
| 9 | **Pset `OBIM_Projeto` dentro do IFC aceito**: uma única etiqueta de identificação no IfcProject | `02` §6 |

## 2. Perguntas realmente abertas
| # | Prioridade | Pergunta ao PO | Padrão assumido | Por quê |
|---|---|---|---|---|
| A (RESPONDIDA, #7) | Alta (até a semana 4 da F0) | Teto de gasto mensal aceitável caso o gatilho de plano dispare (Max 5x ou créditos de uso extra)? | Nenhum gasto extra; ao disparar, o líder apresenta opções e o PO decide | O calendário de 21–42 meses assume Pro (`02` §14) |
| B (RESPONDIDA, #8 e #9) | Média (até a F3) | Nome do pacote de envio: `.obimpack` está bom, ou prefere que "Salvar" grave sempre o pacote único (um arquivo só, menos risco de separar, mas o IFC fica "dentro" do ZIP)? | Par `Casa.ifc` + `Casa.obim` como padrão; `.obimpack` só para envio | IFC visível e limpo era a sua preferência; R14 tem gatilho para rever |
| C | Média | Hospedagem: GitHub principal + espelho Codeberg? | Sim | CI gratuito e ilimitado em repositório público **[verificado em 2026-10-10]** |
| D | Média | Interface: híbrido (navegador/propriedades estilo Revit; caixa de ferramentas/favoritos estilo ArchiCAD)? | Híbrido, confirmado na entrevista F0-S09 | — |
| E | Média | Seu hardware (CPU, RAM, GPU, sistema) para referência? | 4 núcleos, 16 GB, GPU integrada recente | Metas de desempenho |
| F | Média | Formato padrão de gravação IFC4, com exportação IFC2x3 como critério de portão? | Sim | IFC2x3 CV 2.0 ainda é o padrão certificado para troca com ArchiCAD/Revit **[verificado em 2026-10-10]** |
| G | Baixa | Assinatura de código Windows via SignPath Foundation (gratuita para OSS, exige projeto já lançado e política publicada)? | Candidatar na v0.3; builds sem assinatura até lá | Evita alerta do SmartScreen sem custo |
| H | Baixa | Nome definitivo do projeto | "OpenBIM Studio" provisório; verificar marca/domínio antes da 1.0 | "openBIM" é termo usado pela buildingSMART **[não verificado nesta rodada]** |
| I | Baixa | IA embutida no produto? | Não na 1.0; API de plugins permite depois | Foco |
| J | Baixa (antes da F5) | Autoriza consulta formal à CAIXA sobre redistribuição de tabelas SINAPI? | Sim, quando chegar a F5; até lá, só importação pelo usuário | Termos não encontrados na web (`07` §2) |

## 3. Perguntas originais (Q1–Q9) e destino
| Original | Destino |
|---|---|
| Q1 Licença | Decidida (#6) |
| Q2 Nome | H |
| Q3 Hardware | E (hardware de teste: decidida, #4) |
| Q4 Ferramentas | Resolvida (Claude Code) |
| Q5 Projetos reais | Decidida (#3) |
| Q6 Hospedagem | C |
| Q7 Interface | D |
| Q8 Windows/macOS | Decidida (#4) |
| Q9 Assinatura | Decidida (#2); gasto extra em A |
