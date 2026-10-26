# Guia para agentes de IA que contribuem

Vale para qualquer IA (Claude, Gemini ou outra) que escreva código, teste ou revisão neste repositório. Leia também [CONTRIBUTING.md](../CONTRIBUTING.md) e os ADRs em [docs/adr/](adr/).

## Papéis
- **Implementador:** escreve o código da issue. Não escreve nem altera os testes de oráculo da mesma tarefa.
- **Autor do oráculo:** escreve só testes. Cada teste deve falhar com pelo menos um defeito plausível; liste os defeitos (mutantes) pensados. Casos que a implementação ainda não cumpre levam o marcador `@AINDA_NAO` (xfail estrito).
- **Revisor:** nunca revisa o que ele mesmo escreveu. Em tarefas críticas (gravação de arquivo, transações, junções, threads, ponte C++/Python), a revisão procura defeitos, roda mutantes e responde "aprovado" ou "reprovado" com lista numerada.

## Regras
1. Faça só o que a issue pede, só nos arquivos que ela permite. PR com no máximo 400 linhas próprias; maior que isso, divida antes.
2. Nunca afrouxe número, limite ou caso de teste existente. Se o teste parece errado, explique na issue em vez de mudar.
3. Rode antes de abrir o PR: `QT_QPA_PLATFORM=offscreen pytest` (veja [dev-setup](dev-setup.md)). Testes gráficos rodam sem janela (`xvfb-run`).
4. Licenças: sem código GPL-2.0-only, proprietário ou sem licença. Código copiado leva comentário de origem e linha em [THIRD_PARTY.md](../THIRD_PARTY.md).
5. Nada de dados de terceiros nem projetos de clientes.
6. Um ramo por tarefa; o `main` é protegido e só recebe PR com `linux` e `windows` verdes.
7. Título do PR: `ID da tarefa: resumo curto`. Commit termina com a linha `Co-Authored-By:` do agente. Nunca inclua a frase "Generated with ..." em commit, PR ou comentário.
8. Escreva em português claro. Só um agente por arquivo ao mesmo tempo: comente na issue "pego essa" antes de começar.

## Formato de entrega
Arquivos completos, lista curta do que cada teste prova e, no oráculo, a lista de mutantes pensados.
