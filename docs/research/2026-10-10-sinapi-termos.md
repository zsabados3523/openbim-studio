# Ficha de pesquisa: termos de uso e redistribuição do SINAPI
- Autor: líder (sonnet), coleta feita por haiku · Data: 2026-10-10 · Fatia relacionada: F0-S01-T10 (uso real só na F5)
## Pergunta
Podemos redistribuir as tabelas do SINAPI junto com o programa? O que a CAIXA diz sobre uso e redistribuição?
## Fontes consultadas
| # | Fonte | Tipo | URL ou referência | Licença | Data de acesso |
|---|---|---|---|---|---|
| 1 | Página do SINAPI no site da CAIXA | doc pública | caixa.gov.br/poder-publico/apoio-a-gestao-publica/sinapi/ | desconhecida | 2026-10-10 |
## O que aprendemos (com nossas palavras, sem copiar texto)
**Nada.** O site da CAIXA respondeu com redirecionamento em loop (HTTP 302 para a mesma página, com um cookie de segurança) e nunca entregou conteúdo. Não tentamos contornar a proteção. Termos de uso, redistribuição e licença dos dados: **não verificado**.
## Comportamento de referência (testes do PO, se houver)
Nenhum.
## Código aberto lido
Nenhum.
## Decisão para o OpenBIM Studio
Mantém-se a regra de `v2/05` §4: só importar a planilha que o próprio usuário baixar; registrar mês, UF e fonte; não distribuir planilhas nem apresentar como orçamento oficial. Consulta formal à CAIXA continua prevista para a F5 (decisão J).
## Riscos de IP identificados
Risco desconhecido enquanto os termos não forem lidos. Sugestão: o PO abre a página no navegador dele, procura termos de uso/redistribuição e cola aqui o endereço ou o texto (opcional, não bloqueia nada).
## Revisado por: não revisada, **ficha incompleta** (R2, 2026-10-14)
Nova tentativa em 2026-10-14: a página do SINAPI no site da CAIXA bloqueia leitura automática (robots), então os termos seguem **não verificados**. Não tentamos contornar. Dono: PO, que pode abrir a página no navegador e colar o endereço ou o texto (opcional). **Informação do PO (2026-10-15, de leitura própria, não verificada por nós):** o uso gratuito do banco de dados é permitido, mas software que automatiza processos ou buscas precisa de **autorização da CAIXA**. Efeito: a importação automática na F5 depende dessa autorização; a regra de `v2/05` §4 (importar só a planilha que o usuário baixar) continua e a consulta formal à CAIXA passa a ser requisito da F5. Prazo: antes da F5 (só importa lá). Até lá a regra de `v2/05` §4 vale: importar só a planilha que o usuário baixar.
