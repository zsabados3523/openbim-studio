# Cartões de tarefa

Um arquivo por tarefa: `F0-S01-T03.md`. Quadro em `../BOARD.md`. Diff máximo por cartão: 400 linhas.

Formato fixo (`v2/04` §5): título com ID · linha de classe/modelo/oráculo · linha de dependência e tamanho · Objetivo · Ler antes · Arquivos permitidos · Critérios de aceite · Armadilhas conhecidas · Fora de escopo.

Retorno do implementador:
```
STATUS: SUCESSO | FALHA | BLOQUEADO | PRECISA_PO | AGUARDA_OPUS
TAREFA: <id>
RESUMO: <≤ 5 linhas>
EVIDENCIAS: <testes n/n, caminhos de capturas/vídeo/relatório>
PERGUNTA_PO: <se houver, pt-BR simples, com recomendação>
```
