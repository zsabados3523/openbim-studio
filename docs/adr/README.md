# Decisões de arquitetura (ADR)

Cada ADR registra uma decisão que afeta a estrutura do projeto: o contexto, as opções, o que foi decidido, as consequências e o que ficou em aberto. Todos os ADRs estão em português.

| ADR | Tema | Código que explica |
|---|---|---|
| [001](ADR-001-stack-hibrido-e-ponte.md) | Stack híbrido Python + C++ e a ponte | `native/obimcore/` (módulo `obimcore`) |
| [002](ADR-002-modelo-de-dados-transacoes-e-oplog.md) | Modelo de dados, transações e diário | `app/openbim_app/transacao.py`, `diario.py`, `gravacao_atomica.py`, `gravacao_par.py` |
| [004](ADR-004-processos-threads-e-trava.md) | Processos, threads e trava do modelo | `app/openbim_app/sessao_modelo.py`, viewport |
| [005](ADR-005-dependencias-e-build.md) | Dependências, build e empacotamento | `environment.yml`, `packaging/` |

A numeração tem lacunas (003 e a partir de 006): são decisões ainda não escritas.

## Como propor uma decisão nova
1. Abra uma issue descrevendo o problema, as opções que você vê e o que pretende medir.
2. Depois da conversa, abra um PR com o arquivo `ADR-00N-tema.md` (próximo número livre) com as seções: Contexto, Opções, Decisão, Números medidos (quando houver), Consequências, O que nos faria mudar de ideia, O que ficou em aberto. Comece com a linha `Status: proposto`.
3. O status muda para `aceito` quando o PR é aprovado. Uma decisão antiga só é substituída por outro ADR que a cite; o texto antigo não é apagado.
