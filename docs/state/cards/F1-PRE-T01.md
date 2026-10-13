# F1-PRE-T01: Comportamento básico de janela e navegação (testes de regressão)
- Classe: **T2** com a parte da viewport (zoom, seleção, câmera) em lote Opus (esses trechos tocam `viewport.cpp`; se o conserto exigir mexer em C++ crítico, vira T3) · Tamanho: G, dividir em 3 PRs de até 400 linhas (janela / navegação e zoom / caminhos e atalhos) · Implementa: sonnet (esforço alto) · Oráculo: sonnet (outro agente) · Revisa: sonnet; 1 em 3 vai ao lote opus; viewport sempre opus
- Depende de: S04 concluída (T11b e T12) · Deve estar pronto **antes da Fase 1**
- Origem: pedido do PO (2026-10-13), a partir de críticas da comunidade OSArch a programas feitos com IA ("para cada defeito corrigido surgem três novos"; janelas que não redimensionam, navegação e seleção estranhas, zoom da roda que quebra).
## Objetivo
Garantir, com testes que rodam sempre no CI, que o básico do programa não quebra: um conjunto de comportamentos de janela e navegação com teste de regressão automático.
## Arquivos permitidos
`tests/test_comportamento_janela.py`, `tests/test_comportamento_navegacao.py`, `tests/test_comportamento_caminhos.py` (oráculo); correções no que os testes revelarem em `src/` ou `prototypes/s04/` (implementador, só depois do oráculo).
## Critérios de aceite
1. **Janela:** redimensionar (maior, menor, mínimo) mantém painéis e viewport sem sobrepor; maximizar/restaurar; fechar e reabrir; mudança de monitor e de escala de tela (100%, 125%, 150%); sem tela real (`xvfb-run`).
2. **Zoom e câmera:** a roda do mouse aproxima e afasta na direção certa, em passos proporcionais, em todos os modos (orbitar, deslocar); zoom no cursor; limites (nunca atravessa o modelo nem vira NaN); enquadrar tudo; o zoom da roda é testado também **depois** de abrir outro projeto, trocar de vista e redimensionar (o caso "funcionava e quebrou").
3. **Seleção:** clicar seleciona a peça certa em 100%, 125%, 150%, 200%; clique no vazio limpa; selecionar depois de orbitar, aproximar e redimensionar; borda da janela.
4. **Atalhos:** cada atalho do catálogo (`docs/design/catalogo-ferramentas-f1-f2.md`) dispara a ação; não dispara com um campo de texto em foco nem com número sendo digitado; sem conflito entre atalhos; reconfigurar um atalho persiste.
5. **Caminhos configuráveis:** pasta de projetos, de recuperação e de configuração mudam por configuração (variável de ambiente e arquivo), com espaços, acentos e (no Windows) caminho longo; nada fixo em `~`; tudo que falta é criado ou dá erro claro em pt-BR.
6. **Regressão:** cada defeito de usabilidade que o PO ou a comunidade reportar ganha, antes de ser consertado, um teste que o reproduz (regra permanente, anotada em `docs/dev-setup.md`).
7. Roda em Windows e Linux no CI; macOS informativo.
## Regras
`xvfb-run` apenas. Oráculo por outro agente que o implementador. Implementador não edita o oráculo. Nenhum teste de tempo apertado no CI (régua do CI virtual).
## Próximo passo
Aguarda a S04. Não iniciar antes de T12.
