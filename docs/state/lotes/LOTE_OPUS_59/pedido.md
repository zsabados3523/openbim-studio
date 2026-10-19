<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
# LOTE_OPUS_59: regra e oráculo do T29 (reinício planejado) e especificação do T32 (protótipo descartável da troca de geometria) (F0-S04-T29 e T32)
Pedido do líder (2026-10-18), **classe TA (planejamento), esforço médio. O Opus especifica; ninguém implementa neste lote.** Módulo: viewport e ponte, S04. Escreva só `docs/state/lotes/LOTE_OPUS_59/resultado.md`; não edite nenhum outro arquivo, **não escolha pelo PO o que é dele e não implemente**. Pergunte ao PO, em lista, o que for ambiguidade; não invente.

Retorno em estilo caveman (curto) na mensagem final; o `resultado.md` em português normal e claro.

## Regra do PO (2026-10-17): padrão rigoroso
Nenhuma opção pode afrouxar meta, régua, limite ou teste existente (6.000 MB, 60 s, 200 ms, `limite_peca_s`, M5, orçamento por quadro 2 MiB e 4 ms). Mudar o orçamento por quadro só com ok do PO (A31: não decidir agora). `fluxo_a.py` é régua: não mexer (A29); teto de lote, se escolhido, fica dentro do C++ (`cena`). Decisões já dadas em `docs/state/PO.md` (A24 a A31): bloco padrão 250 para todo arquivo (detalhado e simples não podem piorar), prova da memória com 5 aberturas ou 3 em dois dias, vale a pior; meta de 200 ms vale também para parede vinda do arquivo. O PO deixou a escolha de G e da opção para o líder seguir a recomendação do Opus.

## Padrão de evidência
Toda causa vem com número. Hipótese vem marcada "hipótese" com o teste que a confirma. Estimativa vem marcada "estimativa". Não invente ganho. Windows não foi medido (F0-S03-T28): diga o que vale só pelo desenho.

## Contexto fechado (só leitura; nada fora desta lista)
`docs/state/lotes/LOTE_OPUS_58/resultado.md` (§1 a §3), `docs/state/reports/F0-S04-T26.md` (R-0), `docs/state/reports/F0-S04-T27.md` (G-0a), `docs/state/reports/F0-S04-T25.md`, `docs/state/reports/F0-S04-T24.md` (§7, §13), `docs/state/cards/F0-S04/F0-S04-T29.md`, `F0-S04-T30.md`, `F0-S04-T32.md`, `docs/state/PO.md` (A24 a A31). Código (só leitura): `prototypes/viewport_qrhi/carregador.py`, `prototypes/viewport_qrhi/processo_malhas.py`, `prototypes/s04/obimcore/nucleo/motor.h`, `cena.h`, `cena.cpp`.

## Item 1: T29, escolher G e fechar a regra R-A, e especificar o oráculo (T29b)
Fato novo (T26, números gravados do T24, sem IFC novo): R-A serve com G de 0,5 a 2,0 GB (0 reinícios falsos em 12 aberturas; maior bloco leve cresce 340 MB); tempo perdido 0,57 a 1,77 s (tela real); pior total 53,31 a 54,51 s (57,10 a 58,30 s na leitura conservadora com +3,79 s); a regra "memória que sobrou antes do bloco" foi refutada; o primeiro bloco de cada filho cresce 914 a 965 MB, então R-A precisa isentar esse bloco (para G = 0,5 GB). Limite declarado da simulação: o T24 parou o filho limpo no fim do bloco; matar no meio do bloco e o custo real só a implementação mede.
O que tratar:
1. **Recomendar um valor de G** (e se vale "G fixo" ou "G dependente de algo"), com o critério (folga contra reinício falso × tempo perdido × folga da memória de 106 MB), e a **isenção do primeiro bloco** de cada filho. Conferir os números do T26 e dizer se há erro ou conclusão forte demais.
2. **Matar o filho no meio do bloco** (o que o T26 não mede): riscos (peças já entregues e não entregues, ids, `desl`, mensagens em voo, `espera`/`seguidos`/`acusadas`/`iso`, vigia de 20 s, cancelamento no meio do reinício), conta A da memória (pai + maior filho) e o que o pai faz com o que chegar depois da decisão.
3. **Fechar o cartão T29** (campo "Regra escolhida", arquivos permitidos, divisão em cartões de ≤ 400 linhas cada, ordem) e especificar o **oráculo do T29b** (quem escreve, o que verifica: por peça, forma canônica exata, controle normal contra normal, ganchos `OBIM_TESTE_REINICIO_BLOCO`), mais o **teste barato antes de investir** (sintético em tela virtual quando bastar; arquivo do PO só com ok e horário dele).
4. Medida oficial futura (5 aberturas do pesado, simples, detalhado, 25 MB; placa real; Windows): o que ela precisa registrar, incluindo o maior silêncio do filho e o tempo perdido até cruzar G.
5. Classe, risco, o que NÃO vale.

## Item 2: T32, especificar o protótipo descartável do salto no desenho (2-G) à luz do T27
Fato novo (T27, cena sintética inteira de 805,7 MiB, tela virtual, 3 rodadas): o modelo "quadros = teto(lote tocado ÷ 2 MiB) + 1" **não vale** em 45 de 45 trocas; toda troca leva cerca de 404 quadros (403 em 4), de 1 KB a 285 MiB; vale "cena inteira ÷ 2 MiB + 1" (dentro de 1 quadro em 45 de 45). Pedaços por quadro: mediana 2, máximo 8 a 31 (3,9% a 8,8% dos quadros com 3 ou mais). A placa se esvazia (mínimo 0) em 45 de 45; `contextos` não muda em 54 de 54; "criar parede" = 2 pedaços e 2 quadros em 9 de 9. Achado sem causa: `bytes_copia` foi de 844,9M para 1.160,7M ao fim, nas 3 rodadas. A causa de "a cena inteira é reenviada" não foi isolada.
O que tratar:
1. **Ler `cena.h`, `cena.cpp` e `motor.h`** (o Opus ainda não os leu) e dizer, com linha de código, **onde a troca reenvia a cena inteira** e se isso é limpar-e-reenviar em `atualizar`. Corrigir o que o lote 58 §3 supôs e estiver errado.
2. **O que muda para as opções do T30**: 2-A (reenviar só o lote tocado) passa a exigir mudança no C++ (não é só "teto de lote")? A 2-G (pular a faixa da peça antiga) ainda é a melhor? Há uma opção nova ("não limpar a placa", reenvio incremental)? Para cada uma: o que muda, classe, o que cada número permite afirmar e o que NÃO permite, risco para a trava `Motor::m_` → `DadosCena::m_` → `mc_`.
3. **Reescrever o cartão T32** com critérios de aceite que as medidas do T27 tornam possíveis (instrumentação por quadro dentro do C++, `drawIndexed` com primeiro índice no OpenGL em software, troca atômica, custo de desenho com saltos), as **pastas e arquivos permitidos**, o oráculo (Opus especifica, outro agente escreve o que faltar), e o que NÃO é medido (D3D11, seleção, caixa, perda de contexto).
4. **Explicar o `bytes_copia`** (844,9M → 1.160,7M) se o código mostrar a causa; senão, marcar hipótese e o teste.
5. Divisão do T30 em T30a a T30d (≤ 400 linhas cada) dado o que o T32 vai decidir.

## O que o Opus entrega no `resultado.md`
1. Por item, a especificação pedida, **2 a 3 opções** onde houver escolha, **uma recomendação por item** e o que NÃO vale.
2. **Erros e contradições** que achar nos relatórios T26, T27, T25 e T24.
3. **Ordem sugerida** entre T29/T29b e T32/T30 e quais podem rodar ao mesmo tempo (um implementador por vez por conjunto de arquivos).
4. **Lista de perguntas ao PO** (só o que é decisão dele).
5. **Resumo de 5 linhas em português simples, sem siglas**.
6. O que registrar no LOG e o texto dos cartões T29 e T32 prontos para colar (o líder grava).
O Opus não implementa e não revisa o que ele mesmo escreveu em tarefa anterior (oráculo e implementação seguem em subagentes diferentes).
