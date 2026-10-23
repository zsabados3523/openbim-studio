# LOTE_OPUS_72: revisão do relatório de medição V1m (forma mista)
Revisor: opus (effort médio), contexto fechado. Não escreveu o oráculo nem o código do V1 (o Opus 71 revisou o código; este lote só olha o relatório).
## Leia (só estes)
- `docs/state/arquivo/F0-S04/cartoes/F0-S04-V1.md` (critérios 2, 3, 4, 5)
- `docs/adr/ADR-004-processos-threads-e-trava.md` §5.1 e §9
- `docs/state/reports/F0-S04-V1.md` (o que se revisa)
- JSON brutos: `~/openbim-medicao/2026-10-21-V1m-linux/{lote,pesada}.json`, `~/openbim-medicao/2026-10-21-V1m-placa/{lote,pesada}.json`, `~/openbim-medicao/2026-10-21-V1m-windows/v1m-win.txt`
## Perguntas
1. Os números do relatório batem com os JSON (veredito e brutos)? Conferir ao menos 6 por máquina.
2. A execução seguiu o cartão (base, quantidade, rodadas, 1 execução por parte, régua 100 ms em tela virtual e 200 ms com ESTRITO na placa, sem afrouxar nada)?
3. A conclusão "V1 aprovado" decorre do critério 5 (ok nas duas partes no Linux local e na placa; Windows só informativo)? As margens abaixo de 5% estão ditas e não escondem um risco que mude o veredito?
4. A frase marcada "interpretação" está corretamente marcada, ou deve ser cortada?
5. O que falta para ADR-004 passar de "aprovado texto" a "aceito" (a medição de fechamento M1F é do S04)?
## Saída
APROVADO ou REPROVADO + lista numerada de correções.
