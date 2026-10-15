<!--
SPDX-License-Identifier: AGPL-3.0-or-later
-->
# Lote Opus 29: revisão da S01 (resultado)
Data: 2026-10-15 · Revisor: Opus (subagente, contexto fechado) · Pedido: `docs/state/lotes/LOTE_OPUS_29/pedido.md` · Objeto: lista numerada no fim de `docs/state/arquivo/F0-S01/F0-S01-revisao.md`.

**Aviso de independência.** O parecer da tabela de licenças (lote 2) foi meu. Por isso não julgo de novo o mérito daquela tabela: aqui confiro só o processo, as evidências e as partes novas (linha do Qt Shader Tools, mudança do ReportLab, coerência e testes). O aceite final continua com o PO.

**O que conferi fora dos textos do pedido (só existência):** `LICENSE`, `LICENSES/AGPL-3.0-or-later.txt`, `REUSE.toml`, passo "REUSE" no `ci.yml` (com `reuse lint`), READMEs e CONTRIBUTING nos dois idiomas (READMEs com 37 linhas cada), pastas `app/ prototypes/ packaging/ corpus/ tests/ docs/`, `BOARD.md` (linha da S01 já cita a R2), `reports/F0-S01.md`, `PAINEL_DO_PROJETO.md`, os arquivos `.qsb` em `prototypes/viewport_qrhi/shaders/`. No GitHub, li o resumo da execução de CI `38653866732`: `linux`, `windows`, `appimage` e `instalador-windows` verdes, `macos` vermelho com aviso de "não bloqueia". O registro detalhado dos jobs foi recusado pelo GitHub (acesso negado), então não li as contagens de teste.

## Veredito por item
1. **R1, seção 1 (9 critérios): APROVADO.** Os 9 critérios batem com o texto da S01 no plano, e cada um tem evidência que existe. As marcas "Parcial" (SINAPI) e "Não, adiado" (Codeberg) estão honestas. Ressalva de texto: o critério 8 ainda diz "aceite do PO pendente", mas o PO aceitou em 2026-10-15 (recomendação 1).
2. **R1, seção 2 (cobertura e lacunas): APROVADO.** Os 12 itens do plano têm linha na tabela. Qt Shader Tools ganhou linha própria; as dependências transitivas estão bem separadas: a tabela cobre o que escolhemos, o inventário do CI cobre o que vai no pacote. Ressalva: com a linha nova a tabela tem 24 linhas, não 23 (recomendação 2).
3. **R2, Qt Shader Tools ("Sim, só com a condição"): APROVADO.** O processo foi bom: fonte primária (documentação do Qt) citada com data, fonte secundária divergente (Debian) registrada sem esconder, e a condição protege o caso pior. O ponto que decide é verdadeiro e conferido: os `.qsb` já estão no repositório, então a ferramenta `qsb` (só GPL-3 ou comercial) é usada só na preparação e não vai ao instalador. Ressalvas: a palavra "Condição" na regra de virada conflita com o veredito atual "Sim, só com a condição" (recomendação 3); e a linha ainda diz "proposto, aguarda Opus e PO" (recomendação 4).
4. **R2, ReportLab e SINAPI: APROVADO.** SINAPI como "não verificado" é o certo: o site bloqueia leitura automática, não foi contornado, e a informação do PO está marcada como "de leitura própria, não verificada por nós", com a autorização da CAIXA virando requisito da F5. ReportLab: a pergunta foi superada pela decisão do PO ("Sim, com condição"). Aceito a decisão porque a condição está escrita na tabela (o leitor de XML com licença GPL fica de fora, e o arquivo de licença da versão travada será lido quando o pacote entrar, na F5). Ressalva: a seção 3 e o item 4 do relatório ainda descrevem o estado antigo ("PRECISA_PO", "manter fora") (recomendação 5).
5. **R3, coerência e pendências: APROVADO.** As 3 correções existem: o cabeçalho da tabela diz "APROVADA no lote Opus 2"; a linha da S01 no `BOARD.md` já cita a R2 e as decisões de 2026-10-15; `reports/F0-S01.md` existe para a nota. Deixar o `CLAUDE.md` sem editar (precisa de cartão aprovado pelo PO) e o painel do PO parado até o aceite está certo pelas regras. Toda pendência tem dono e prazo (T23 ou F5).
6. **R3, números de teste: APROVADO, com limite.** O estado dos jobs bate com o CI (conferido). As contagens não puderam ser lidas daqui, mas são coerentes entre si: 163 + 169 = 332 no Linux e 161 + 171 = 332 no Windows (mesmo total), e 127 + 1 pulado = 128 no passo do módulo. Observação: o GitHub mostra essa execução como disparada há cerca de 1 hora (2026-10-15) no ramo `claude/project-thread-6k0mor`, e o relatório diz 2026-10-14; provavelmente é uma nova tentativa da mesma execução. Anotar a data certa (recomendação 6).

**Resultado do lote: APROVADO (6 de 6), com 6 ajustes de texto que não precisam voltar ao Opus.**

## Recomendações (todas de texto, classe mecânica)
1. `F0-S01-revisao.md`, critério 8 e "Resumo de 5 linhas", item 5: trocar "aceite do PO pendente" e a pergunta por "PO aceitou em 2026-10-15".
2. Tabela mestre ("Conferência do lote opus 2") e `F0-S01-revisao.md` seção 2: atualizar a contagem para 24 linhas (com Qt Shader Tools). O ADR-009 §3 (que diz 24) pode ficar como está.
3. Linha do Qt Shader Tools: deixar a regra de virada sem ambiguidade, por exemplo "se a biblioteca for embarcada e só houver opção GPL-3, o veredito muda e vai ao PO". Acrescentar que a saída do `qsb` (os `.qsb`) é nosso material gerado e fica com a nossa licença, e conferir se o `REUSE.toml` cobre esses arquivos.
4. Tabela mestre: tirar "proposto, aguarda Opus e PO" do cabeçalho e da linha do Qt Shader Tools, com "aprovada no lote Opus 29 (2026-10-15)".
5. `F0-S01-revisao.md` seção 3 e item 4 da lista: registrar a decisão do PO sobre o ReportLab (de "PRECISA_PO" para "Sim, com condição, decisão do PO em 2026-10-15"), para não ficarem dois estados no mesmo relatório.
6. `F0-S01-revisao.md` seção 5: anotar que a contagem foi lida pelo líder no registro do job e a data da tentativa usada (o resumo do GitHub mostra 2026-10-15). Quando o líder ler o registro de novo, conferir que as contagens são da tentativa verde.

## O que fica aberto (nada bloqueia a F0)
- Termos do conda-forge: dono líder, reler na T23.
- SINAPI: dono PO; autorização da CAIXA antes da F5.
- ReportLab: ler o arquivo de licença da versão travada na F5.
- `THIRD_PARTY.md` com data velha: reconferir na T23.
- Espelho no Codeberg: adiado pelo PO.
