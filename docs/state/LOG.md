# Log

Uma linha por tarefa concluída ou escalada, e por mudança de classe de tarefa. Formato: `data | tarefa | evento | detalhe`.

2026-10-10 | PREP | sessão 1 concluída (líder sonnet) | Criados CLAUDE.md, docs/state, READMEs de docs/, 27 cartões (S01: 12, S02: 15), BOARD, QUEUE_OPUS. Sem instalação, rede ou git.
2026-10-10 | S01, S02 | classificação | Nenhuma tarefa T3: nada toca oplog, joins, HLR, ponte C++/Python, threads ou gravação do par. S01-T11 vai ao opus porque o aceite de 03 (S01) exige revisão do papel Arquiteto, mesmo sendo T2.
2026-10-10 | S01-T02 | decisão do líder (pendente de ok do PO) | Texto verbatim da licença AGPL fica fora do limite de 400 linhas (não é conteúdo autoral).
2026-10-10 | S01-T03 | decisão do líder (pendente de ok do PO) | Estrutura de pastas proposta: app/, prototypes/, packaging/, corpus/, tests/, docs/, .github/workflows/ (03 pede só "o necessário", sem lista).
2026-10-10 | S02 | decisão do líder (pendente de ok do PO) | Viewport do app esqueleto = painel reservado (placeholder); a viewport real é a S03, que depende da S02.
2026-10-10 | S02 | estimativa | 03 diz "M→G"; para orçamento de cota tratada como G (9–20 sessões).
2026-10-10 | PO | respostas P1 a P7 | AGPL-3.0-or-later; rede para leitura pública autorizada (leitura por haiku); estrutura e LICENSE aprovados; viewport placeholder ok; git init local autorizado; hardware: i5-12600KF, RTX 3070, 24 GB, Linux nativo + VM Windows.
2026-10-10 | S01-T06..T10 | ajuste de execução | A pedido do PO, haiku faz a leitura das páginas públicas; sonnet interpreta e revisa. Classes não mudam.
2026-10-10 | S01-T01 | parcial | git init -b main feito (autorizado, P6). Sem commit: o git global está com identidade diferente da do PO; perguntar antes do primeiro commit. Remoto aguarda PO.
2026-10-10 | S01-T02 | feita | LICENSE AGPL v3 de gnu.org (haiku), sha256 0d96a4ff68ad6d4b6f1f30f713b18d5184912ba8dd389f86aa7710db079abcb0, 661 linhas, acesso 2026-10-10. Conferido pelo líder.
2026-10-10 | S01-T03..T05 | feitas | Esqueleto, README e CONTRIBUTING pt-BR (sonnet) e en (haiku). Autosave no .gitignore como `autosave/` genérico.
2026-10-10 | S01-T06..T10 | feitas | Coleta por haiku, fichas por sonnet. SINAPI: site da CAIXA em loop de redirecionamento, não verificado, sem contornar.
2026-10-10 | S01-T11 | escrita, aguarda opus | Tabela mestre sem nenhum "Não"; 4 pendências para o lote 1 (OCCT, libdxfrw, WiX, relink LGPL).
2026-10-10 | S01-T01 | feita | Commit 076d870 e push para github.com/zsabados3523/openbim-studio (ok do PO). Espelho Codeberg adiado por decisão do PO.
2026-10-10 | PO | decisão: posicionamento geral (opção A) | Núcleo sem país; Brasil = primeiro pacote regional e escopo da 1.0. Editados v2/00 (Rev. 2.1), v2/01, v2/02 (visão, princípio 5, D4), README pt/en, CLAUDE.md. Escopo da 1.0 e calendário inalterados.
2026-10-10 | S02-T01 | feita | Ficha de disponibilidade (haiku coleta, sonnet ficha). Conteúdo do pacote ifcopenshell do conda-forge segue não verificado (teste real).
2026-10-10 | LOTE-1 | pronto | Pedido em docs/state/LOTE_OPUS_1.md (itens 1 a 3; item 4 opcional). Aguarda PO abrir sessão Opus.
2026-10-10 | LOTE-1 | executado (opus) | Itens 1 a 4. S01-T11 REPROVADA (1ª reprovação, 12 defeitos de redação/cobertura, nenhuma lib trocada). ADR-009 e esboço do ADR-005 escritos. Opus avisa que o ADR-009 usou as respostas da revisão e não a tabela reprovada (T12 dependia de T11 aprovada).
2026-10-10 | S01-T11 | correção feita pelo líder | Tabela mestre v2 aplicando os defeitos 1 a 12; sem rede. Conferência do diff vai ao lote 2.
2026-10-10 | LOTE-1 | pendente de confirmação | O relatório do opus diz que o PO respondeu "sim, aprovo e autorizo tudo" na sessão Opus. O líder pede confirmação no chat do líder antes de agir (ADR-009 aceito, WiX fora, cartão novo S02, edição de v2/05 §3).
2026-10-10 | PO | confirmou os 4 itens do lote 1 | ADR-009 aceito; WiX fora (NSIS); cartão novo S02-T16; arquivos gerados fora do limite de 400 linhas (S02-T03, S02-T06 e texto de licença); v2/05 §3 ajustado pelo líder (conferência no lote 2).
2026-10-10 | S02-T10, T11 | classe mantida T2, revisão opus obrigatória | Decisão do opus no lote 1; cartões atualizados (ADR-009 §5.3, ADR-005 testes 7 e 8; começar só por P1).
2026-10-10 | PO | push | a5cbfdc no GitHub.
2026-10-10 | PO | autorizou instalar | Miniforge 26.7.2 (sha256 conferido) em ~/miniforge3, sem alterar o shell; ambiente `openbim` só conda-forge (315 pacotes, todos conda-forge), criado em 1 min 50 s.
2026-10-10 | S02-T03 | feita (líder) | environment.yml, environment.linux-64.lock (320 linhas, gerado), docs/dev-setup.md, tests/test_env_smoke.py (3 passam). CLAUDE.md atualizado com os comandos reais.
2026-10-10 | S02-T04 | feita (sonnet subagente) | Janela PySide6, menu, drag-and-drop. 7 testes passam (conferido pelo líder). Implementador criou __main__.py e tests/conftest.py, fora da lista literal de arquivos; aceitos (necessários).
2026-10-10 | S02-T05 | feita (sonnet subagente) | count_by_class, 15 testes passam (conferido). Leitura na thread da UI marcada TEMPORÁRIO (ADR-004). Sem threads.
2026-10-10 | S02-T16 | feita (sonnet subagente) | Teste 2 do ADR-005: cabeçalhos e libs compartilhadas libifcopenshell.* presentes, módulo Python liga nelas. Teste 3: módulo nanobind+OCCT+Qt compila (limpo 2,4 s, incremental 0,9 s) só no Linux local. API C++ da 0.9 usa ifcopenshell::file, relevante ao teste 5 (S04, T3).
