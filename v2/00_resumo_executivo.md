# Resumo executivo (v2 do planejamento, Revisão 2)

> Para: Rafael (PO). Leitura: 5 minutos. Documentos detalhados: `01` a `07` nesta pasta. Os 3 documentos originais não foram alterados.

## O que muda, em uma frase
O plano original tentava construir um "Revit inteiro" com uma equipe que na prática é **você + agentes de IA**. A v2 encolhe a 1.0 para algo que dá para terminar e que ninguém oferece hoje: **um programa BIM instalável no Windows e no Linux que faz projeto legal e executivo residencial no padrão brasileiro, com um IFC limpo como verdade do modelo**.

## As mudanças principais
1. **Foco da 1.0 (aprovado): residencial, projeto legal + executivo ABNT.** Visualizar, modelar (paredes, lajes, esquadrias, cobertura, escada simples), ambientes com áreas, quantitativos, pranchas com carimbo, PDF/DXF/IFC.
2. **Saem da 1.0 (vão para 2.0):** editor gráfico de famílias, colaboração, opções de projeto, clash, COBie. **Entram simples:** tipos paramétricos por script e vínculo SINAPI básico (só importando a planilha que você baixar).
3. **Versão útil cedo (v0.3, "Planta Legal"):** casa térrea com planta, corte e quadro de áreas em PDF.
4. **Projeto = dois arquivos com o mesmo nome:** `Casa.ifc` (modelo, limpo e válido, abre em qualquer programa) + `Casa.obim` (vistas, pranchas, carimbos, cotas e revisões, num ZIP aberto com JSON). O programa avisa se os dois se separarem ou divergirem e ajuda a reassociar. Para mandar a um colega: **Arquivo > Exportar pacote** (`.obimpack`). Detalhes em `02` §6.
5. **Windows e Linux obrigatórios** desde o primeiro dia (CI e seus testes). **Mac fica para depois**: build automático "experimental", sem teste seu, portão formal só pós-1.0 ou com um tester.
6. **Processo de agentes para o Claude Pro:** sessão principal em Sonnet; Opus só para especificações, ADRs e revisão de código crítico, em lote; 1–2 subagentes; orçamento semanal de cota; a F0 mede o consumo real e define quando vale considerar subir de plano (`04`).
7. **Você verifica por roteiros, vídeos curtos e instaladores**, nunca lendo código.
8. **Regras de propriedade intelectual formais** (`05`), agora checadas na web (`07`).

## Calendário honesto (Claude Pro)
| Marco | Faixa (soma simples das fases) | Confiança |
|---|---|---|
| F0 (provas técnicas) | 1,8 a 3,7 meses | média |
| v0.1 Visualizador | 4,2 a 8,3 meses do início | média |
| v0.3 "Planta Legal" | 10,9 a 21,7 meses do início | baixa |
| 1.0 residencial ABNT | **~21 a ~42 meses** do início | baixa |

Como ler: o acumulado é a soma dos mínimos e dos máximos de cada fase. O máximo é **teto de incerteza** (todas as fases no pior caso), não previsão; o provável fica no meio. O plano anterior dizia "18–36 meses", mas as fases somavam na verdade 15,7–31,4. Com o Pro, cada fase fica ~30% mais longa (menos paralelismo e menos Opus): **o teto sobe de 36 para ~42 meses**. Se depois da F0 você subir para Max 5x, a expectativa volta para perto de 17–33 meses. A F0 recalibra tudo com dados reais; a regra continua sendo cortar escopo antes de aceitar atraso acima de 30%.

## O que a pesquisa na web corrigiu (detalhes em `07`)
- **O Bonsai não guarda tudo no IFC**: o layout das pranchas fica em SVG e o estilo em CSS. Isso reforça a sua escolha do arquivo lateral.
- **Qt RHI** (base da viewport) é API "semi-pública": pode quebrar entre versões do Qt. Novo risco R13, mitigado fixando a versão.
- **IFC2x3 ainda é o formato certificado** para troca com ArchiCAD/Revit: a exportação 2x3 vira critério de portão.
- **SINAPI**: não achamos termos que permitam redistribuir as tabelas; o programa só importa o arquivo que você baixar.
- **OCCT no conda-forge** não foi confirmado; o ADR-005 testa antes de decidir.
- **Cota do Pro**: a Anthropic confirma janelas de 5 h e limite semanal, mas não publica números. Por isso a F0 mede.
- **FreeCAD 1.1** (mar/2026) ganhou pranchas e 2D nativo em IFC: o concorrente avançou; revisamos no portão F0.

## Perguntas que ainda preciso de você (detalhes em `06` §2)
1. Teto de gasto extra se a cota do Pro não der conta (padrão: nenhum; você decide no gatilho).
2. Manter "dois arquivos lado a lado" como padrão, com pacote só para envio? (padrão: sim)

## Recomendação
Iniciar **apenas a Fase 0** com IFCs públicos. A F0 termina com uma decisão sim/não baseada em números (stack, desenho, arquivo lateral, build Windows+Linux e consumo de cota).

---

## Changelog
### Revisão 2 (2026-10-10)
- Aplicadas as decisões do PO: corte da 1.0 aprovado; AGPL v3 confirmada; **Claude Pro** (`04` reescrito; `02` §14 e `06` ajustados); Windows+Linux obrigatórios e macOS melhor esforço (`02` D8/§12/R12, `03` S02); **Opção 2: IFC limpo + arquivo lateral `.obim`** (`02` §6 reescrito, `03` S05/S06, `01` §4); corpus do PO depois da F0 (`03` S08, `02` §10/R15).
- Verificação na web de todos os itens verificáveis; marcadores trocados por "[verificado em 2026-10-10]" ou "[não verificado]" com motivo; novo `07_verificacoes_web.md`.
- Premissas corrigidas: Bonsai e vistas no IFC; QRhi semi-pública; IFC2x3 para troca; SINAPI sem termos de redistribuição; OCCT no conda-forge não confirmado; libdxfrw com licença disputada; soma real do calendário anterior (15,7–31,4 meses).
- Calendário recalibrado: 1.0 em ~21–42 meses (teto +6 meses pela cota do Pro).
- Novos riscos R12 (Mac sem teste), R13 (QRhi), R14 (separação IFC/lateral), R15 (corpus do PO atrasar); R9 (cota) sobe para alta.
