# Cartões de tarefa

Um arquivo por tarefa: `F0-S04-T03.md`. Quadro em `../BOARD.md`. Diff máximo por cartão: 400 linhas.

Onde ficam:
- Fatias abertas: uma pasta por fatia aqui (`F0-S04/`, `F0-S05/`...).
- Cartões soltos (plano da F0, pré-F1): direto nesta pasta.
- Fatias fechadas (S01, S02, S03): `../arquivo/F0-Sxx/cartoes/`.

Formato fixo (`v2/04` §5): título com ID · linha de classe/modelo/oráculo · linha de dependência e tamanho · Objetivo · Ler antes · Arquivos permitidos · Critérios de aceite · Armadilhas conhecidas · Fora de escopo.

Retorno do implementador:
```
STATUS: SUCESSO | FALHA | BLOQUEADO | PRECISA_PO | AGUARDA_OPUS
TAREFA: <id>
RESUMO: <≤ 5 linhas>
EVIDENCIAS: <testes n/n, caminhos de capturas/vídeo/relatório>
PERGUNTA_PO: <se houver, pt-BR simples, com recomendação>
```
