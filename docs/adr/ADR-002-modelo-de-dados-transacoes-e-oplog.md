<!--
SPDX-License-Identifier: AGPL-3.0-or-later
-->
# ADR-002: Modelo de dados, transações e oplog
- Status: **rascunho (aguarda PO)**. Versão final com os números do T10 e do T11: cartão T12.
- Autor: opus (cartão F0-S05-T03, classe TA, lote A) · Data: 2026-10-23
- Base: `v2/02` §6.1 a §6.7; `v2/03` F0-S05 e §3; T00 (G1 a G6, M1, M2); decisões P1 a P5 do PO (`cards/F0-S05/README.md`, 2026-10-23); relatório do T02 (`reports/F0-S05-T02.md`, PR 282, ainda fora do `main`); ADR-001 §9; ADR-004 §5 (porta 3C) e §5.1; `app/openbim_app/sessao_modelo.py`; `prototypes/s04/fluxo_a/fluxo_a.py` (`_transacao` linhas 204 a 226, `_desfaz_ou_refaz` 350 a 370, `_c_gravar` 383 a 389, `set_history_size` 61); ifcopenshell 0.9.0, `ifcopenshell/file.py` (citado como `file.py:N`).
- Escopo: o tema "Modelo de dados, transações e oplog" de `v2/03` §3. Fora: formato final do `.obim` (ADR-003, S06), `.obimpack`, HLC e CRDT. Não muda `v2/` nem `CLAUDE.md`.

## Resumo para o PO (5 linhas)
1. Toda mudança no projeto passa por um "pacote" único que mexe no modelo e na documentação juntos; desfazer volta os dois juntos, e cada pacote é anotado na hora num caderno de segurança na pasta do programa.
2. Ao gravar, o programa escreve cópias novas ao lado, confere, guarda uma cópia da versão anterior e só então troca; se cair no meio, ao reabrir ele termina ou volta a gravação, e você nunca fica com um arquivo cortado ou com os dois arquivos desencontrados.
3. Pergunta: depois de gravar, o desfazer continua valendo até você fechar o projeto? **Recomendo sim** (é o que você já tem hoje no protótipo e não custa nada a mais).
4. Pergunta: o desfazer guarda até 256 megabytes de memória, o que dá no mínimo umas 1.650 criações de parede ou 106 apagamentos de 50 paredes de uma vez, e milhares de edições pequenas; passou disso, os passos mais antigos saem. **Recomendo aceitar 256** e confirmar com a medição do fim da fatia.
5. Pergunta: depois de recuperar o trabalho de uma queda, a lista de desfazer começa vazia (o que foi recuperado fica, mas não dá para desfazer passo a passo). **Recomendo aceitar na fase 0**; melhorar depois, se você sentir falta.

## 1. Contexto
`v2/02` §6.5 pede um oplog único (IFC pelo mecanismo do ifcopenshell, lateral por operações JSON, desfazer dos dois juntos) e a gravação atômica do par com diário. `v2/02` §6.7 pede operações identificadas por GlobalId ou id estável do lateral, para desfazer, autosave, recuperação e, na 2.0, merge. `v2/03` F0-S05 fixa as metas (10.000 operações e desfazer tudo; matar no meio da sequência; matar na gravação do par; menos de 5 ms por operação em 50 MB; merge como insumo) e alerta para `UndoSystemError`. O protótipo de hoje (`fluxo_a.py`) tem transação só do IFC, histórico de 100.000 passos sem limite de memória (linha 61) e grava direto por cima do destino (linha 388), que o T00 G1 proíbe copiar.

## 2. O que o ifcopenshell faz (lido em `file.py`, 0.9.0)
- `begin_transaction` cria um `Transaction` (`file.py:553`); cada criar, editar e apagar chama `store_create`/`store_edit`/`store_delete` se houver transação aberta (`file.py:661`, `:844`; `entity_instance.py:205`); **sem transação, a edição não é registrada e some do desfazer em silêncio**.
- `end_transaction` empilha e, passando de `history_size` (padrão 64, `file.py:505`), **joga fora o passo mais antigo sem avisar** (`file.py:557` a `:563`).
- `undo`/`redo` tiram o passo da pilha **antes** de `rollback`/`commit`; se estes falham, sobe `UndoSystemError`, o passo não volta para nenhuma pilha e o modelo fica pela metade (`file.py:570` a `:588`).
- `rollback` engole erros com `except: pass` ao restaurar valores (`file.py:194`, `:202`); `commit` engole na criação (`file.py:224`). **Erro engolido não se detecta em tempo de execução.**
- `delete` guarda `inverses` como dicionário com chave numérica (`file.py:164` a `:171`).
- O estado do desfazer mora em `file.registry`, dicionário da **classe**, com chave `int(self.this)` (`file.py:514` a `:522`); nada o limpa.

## 3. Números (T02, Linux, NVMe ext4; Windows não medido)
| Fato | Número | Fonte |
|---|---|---|
| ids STEP depois de gravar e reabrir; depois de desfazer tudo (302 transações) | 0 diferenças em 1.417.528 e em 1.003.606 entidades | T02 §1 |
| Operações por JSON cru, depois desfazer | `TypeError` em 4 de 6 tipos, modelo parcial; com chaves de `inverses` voltadas a número: 6 de 6, 0 diferenças | T02 §1 |
| Tamanho por transação, JSON / Python | nome 84 / 696 B; propriedade 231 / 1.960; posição 1.934 / 13.576; criar parede 13.845 / 162.709; apagar 5.369 / 51.420; apagar 50 em lote 268.442 / 2.530.074; Python/JSON = 8 a 12 vezes | T02 §2 |
| Transação média / p95 (ms, 50 MB) | nome 0,059 / 0,073; propriedade 0,072 / 0,088; posição 0,939 / 1,809; criar parede 4,321 / 5,992; apagar 2,049 / 3,734; lote 96,79 / 115,67 | T02 §3 |
| Linha de 120 B: `flush`; `flush` + `fsync` (média / p95) | 0,001 / 0,001 ms; 0,647 / 0,832 ms | T02 §4 |
| Troca atômica 1 MB sem / com `fsync` da pasta | 2,173 / 2,940 ms (pasta: cerca de +0,7 ms) | T02 §4 |
| `registry` | modelo de 50 MB aberto: +246 MB; com histórico o arquivo nunca solta; `registry.clear()` solta | T02 §5 |
Não medidos: tempo de `json.dumps` por registro (o de 268 KB do lote importa para "anotar na hora"); `fsync` e `os.replace` no Windows; custo do resumo por dono (§4.1). Vão ao T10.

## 4. Decisões
### 4.1 Duas camadas de registro (item 1)
- **Camada 1, nativa (id STEP):** o `Transaction` do ifcopenshell, mais a lista de operações do lateral. Serve para desfazer, refazer e **reaplicar o diário sobre o mesmo arquivo base**, porque os ids sobrevivem a gravar e reabrir (T02 §1). **Não serve para juntar duas cópias:** as duas criam objetos novos com os mesmos ids.
- **Camada 2, resumo por elemento:** ao fechar cada transação, o conjunto de GlobalIds criados, alterados e apagados (e `(coleção, id)` do lateral), conforme `v2/02` §6.3 e §6.7. Serve à tela, ao merge (T11) e ao painel de referências. Regra de dono para o que não tem GlobalId:
  1. `IfcObjectDefinition` com GlobalId: ele mesmo.
  2. `IfcRelationship`: os objetos que entraram ou saíram das listas dele (diferença entre antigo e novo), e o objeto "relacionador" se ele mudou; relação criada ou apagada: todos os objetos dela. A relação nunca é dona (senão duas cópias que põem paredes diferentes no mesmo pavimento dariam conflito falso).
  3. `IfcPropertyDefinition` (pset, quantidades): os objetos que ela define (via `IfcRelDefinesByProperties`, ou o tipo via `HasPropertySets`).
  4. Sem GlobalId (posição, geometria, valor de propriedade): sobe pelos inversos até chegar a 1, 2 ou 3; todos os donos alcançados. Sem limite de abrangência no protótipo; o custo vai ao T10 e ao T11.
- O resumo é calculado dentro da transação e **conta nos 5 ms** (mais exigente que a P3; o T10 mostra as duas colunas, com e sem resumo).

### 4.2 Transação única (item 2)
- Uma transação nossa = **exatamente um** `Transaction` do ifcopenshell (mesmo vazio: `end_transaction` empilha sempre, `file.py:557`) + a lista do lateral. As duas pilhas andam juntas; `set_history_size` vai a `sys.maxsize` e só o nosso limite (§4.6) descarta passos, sempre dos dois lados (evita o descarte silencioso do `file.py:560`).
- **Guarda:** fora da nossa transação, `arquivo.transaction` recebe um objeto sentinela que repete o filtro da biblioteca (só entidade com `id()` diferente de 0, como `store_create`/`store_edit`, `file.py:136` a `:149`; valor tipado sem id passa) e cujos `store_edit`, `store_delete`, `batch` e `unbatch` levantam `EdicaoForaDeTransacao` **antes** de aplicar; `store_create` (chamado depois de criar, `file.py:661`) remove o objeto criado e levanta. Em `file.add` (`file.py:722` a `:730`) não dá para limpar tudo: levanta e marca o histórico como quebrado. Durante `undo`, `redo`, `discard_transaction` e a reaplicação do diário (`Transaction.commit`/`rollback`, que mexe em `GlobalId` na criação, `file.py:186` a `:188`) a sentinela sai e volta no fim.
- Começo: só dentro de `SessaoModelo.escrever()` (recebe a `Escrita`; `esc.arquivo` já recusa fora da porta, `sessao_modelo.py:33` a `:38`). Transação dentro de transação: `TransacaoAberta`.
- **Fim normal:** `end_transaction`, depois o lateral confirma, depois o resumo, depois o registro no diário (§4.4). **Exceção dentro:** `discard_transaction` (nunca `undo`, que desfaria a anterior: `fluxo_a.py:211`) e o lateral volta na ordem inversa; histórico e refazer ficam como estavam.
- **Desfazer:** IFC primeiro; se der `UndoSystemError`, o lateral **não** é mexido e o histórico fica **quebrado** (`HistoricoQuebrado`: toda transação, desfazer e refazer seguintes recusam; o caminho é reabrir pela recuperação do §4.7, que reconstrói o estado a partir da base e do diário). Se o IFC voltou e o lateral falhar, o IFC é refeito antes de subir o erro (padrão de `_desfaz_ou_refaz`, `fluxo_a.py:363` a `:365`). Refazer: espelho. Desfazer ou refazer com transação aberta: `TransacaoAberta`.
- **Erro engolido pelo `rollback`:** não detectável em execução (`file.py:194`, `:202`). Fica com a régua do T04: a comparação por conteúdo (P1) aparece como falha. Não se adiciona conferência em execução na S05 (custo não medido; ver §7).
- **Fechar projeto:** limpar `history`, `future`, `transaction` e tirar a entrada `int(arquivo.this)` de `file.registry` (T02 §5).

### 4.3 Lateral provisório (item 3, P2)
- Em memória: coleções (nome `[a-z_]{1,32}`, nunca `manifest`) de objetos JSON por id (texto `[A-Za-z0-9_-]{1,64}`; o programa gera UUID4; nos testes, gerador injetado). Só tipos JSON puros (sem NaN nem infinito; chaves texto); senão `ObjetoInvalido`.
- Operações: `criar(c, id, obj)`, `alterar(c, id, obj)` (troca o objeto **inteiro**, guarda o antigo: granularidade "por objeto" de `v2/02` §6.7), `apagar(c, id)` (guarda o antigo). Referência ao modelo só por GlobalId (`v2/02` §6.3), nas chaves `ifc_guid` (um) ou `ifc_guids` (lista). Apagar uma parede **não** apaga nem muda o lateral (órfão visível, `v2/02` §6.3).
- JSON canônico: `json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)` em UTF-8.
- Em disco (T07): ZIP com `manifest.json` (campos de `v2/02` §6.2, mais `"provisorio": true` e `versao_formato` `"0.1.0"`) e um arquivo `<coleção>/<id>.json` por objeto. Formato final: ADR-003.

### 4.4 Diário de transações (item 4, P4)
- Onde: `<base>/projetos/<LadoId>/diario/diario.obimlog` (`v2/02` §6.1). `<base>` = `OBIM_PASTA_LOCAL` se definida (testes); senão `%LOCALAPPDATA%\OpenBIMStudio` no Windows e `$XDG_DATA_HOME/OpenBIMStudio` (ou `~/.local/share/OpenBIMStudio`) nos outros. Histórico não viaja com o projeto: pasta local, não a "roaming".
- `LadoId`: o do pset `OBIM_Projeto`; se o IFC não tem (arquivo de outro programa, nunca gravado por nós), um provisório `uuid5` do sha256 do arquivo aberto, para a reabertura achar a mesma pasta; vira o definitivo na primeira gravação.
- Formato: uma linha por registro, `<crc32 em 8 dígitos hexadecimais minúsculos> <JSON compacto>\n`, com o CRC-32 (`zlib.crc32`) sobre os bytes UTF-8 do JSON. Campos: `v` (1), `seq` (inteiro consecutivo), `tipo`, `hora` (UTC, ISO 8601). Primeiro registro `tipo: "base"`: `ifc_sha256`, `ifc_tamanho`, `ifc_caminho`, `obim_sha256` (ou `null`), `lado_id`. Demais: `tipo` em `transacao`, `desfazer`, `refazer`, com `ifc` (operações codificadas) e `lado` (operações do lateral).
- **Registros autossuficientes:** `desfazer` e `refazer` levam as operações inteiras do passo, nunca uma referência a registro anterior; assim o desfazer depois de gravar (§4.6) se reaplica sobre a base nova. Reaplicar: `transacao`/`refazer` = `Transaction.commit()`; `desfazer` = `Transaction.rollback()` (`file.py:182`, `:217`), lateral na mesma direção.
- **Codificação das operações (T02 §1):** referências e valores como o próprio ifcopenshell serializa (`{"id": n}` ou `{"type", "value"}`); tuplas viram listas; `inverses` vai como **lista de pares** `[[id, [[índice, valor], ...]], ...]` e volta a dicionário de chave inteira. Validado em 6 tipos de operação; tipo novo entra na régua do T05. Valor que não vira JSON (bytes, NaN): `OperacaoNaoSerializavel`, e a transação é **descartada** (codifica-se antes de confirmar).
- **Confirmada** = linha escrita e `flush` feito (protege contra o processo morrer; T02 §4: 0,001 ms). `fsync` (P4): 2 s depois do primeiro registro não sincronizado (temporizador com trava própria do diário, que nunca toca o modelo), ao gravar e ao fechar. Queda de energia perde até 2 s.
- Leitura: linha final sem `\n` ou com CRC errado = registro cortado, ignorado com aviso; linha ruim no meio ou `seq` com buraco = para ali, aplica até a anterior e avisa. Nunca aplica meio registro.
- Zera (novo arquivo só com `base`, por troca atômica) depois de cada gravação do par e de cada autosave. Base de outro sha256 não se aplica (T05 item 4). Fechar sem gravar ou recusar a recuperação: o diário vira `diario-descartado.obimlog` (uma geração).

### 4.5 Gravação de um arquivo e do par (item 5, G1 a G6)
**Um arquivo (T06):** em duas chamadas, para o par poder intercalar: `preparar` faz `escrever`, `fsync` e `conferir`; `confirmar` faz `bak`, `trocar` e `fsync_pasta`. Etapas, nesta ordem e com estes nomes: `escrever` (em `Casa.ifc.tmp`, mesma pasta, G1) → `fsync` (do temporário; na mesma passada lê sha256 e tamanho) → `conferir` (G5: para IFC, começa com `ISO-10303-21;` e termina com `END-ISO-10303-21;`; reabrir inteiro só nos testes, custo não medido) → `bak` (G3: `os.link` do destino para `Casa.ifc.bak.tmp`, ou cópia com `fsync` se o link falhar, e `os.replace` para `Casa.ifc.bak`; o destino nunca deixa de existir, ao contrário de renomear o original) → `trocar` (`os.replace`; `PermissionError`: 6 tentativas, espera 0,05 s dobrando, cerca de 1,55 s ao todo, valor inicial sem medida, G2) → `fsync_pasta` (Linux e macOS; no Windows não há chamada em Python; T02 §4: +0,7 ms). Falha antes de `trocar`: temporários apagados, destino e `.bak` antigos intactos. Falha em `trocar`: o temporário **fica**, e a mensagem diz onde (G2).
**Par (T07, `v2/02` §6.5, G4):** o carimbo do pset `OBIM_Projeto` (`Revisao` + 1, `LadoId`) é escrito numa `escrever()` curta **fora do histórico** (não se desfaz); a gravação segue em `ler()`. Se a gravação falhar, o carimbo volta ao valor anterior. Estados, e o que a reabertura faz em cada um (o diário de gravação `projetos/<LadoId>/gravacao.json`, gravado por troca atômica, guarda destinos, sha256 novos e antigos, `Revisao` nova e o `seq` do último registro incluído):
| Estado (onde morreu) | Reabertura |
|---|---|
| E1 antes dos temporários; E2 com `Casa.ifc.tmp` (inteiro ou cortado); E3 com os dois temporários | sem `gravacao.json`: par antigo; temporários apagados |
| E4 `gravacao.json` escrito, nada trocado; E5 `.bak` feitos | temporários conferem com os sha256 do diário: **conclui** (troca os dois); senão **desfaz** (apaga temporários) |
| E6 IFC trocado, lateral não | `Casa.obim.tmp` confere: conclui; senão volta `Casa.ifc` do `.bak` (cópia + troca, o `.bak` fica) |
| E7 os dois trocados, `gravacao.json` ainda lá | conclui: apaga `gravacao.json` e zera o diário de transações |
| E8 `gravacao.json` apagado, diário de transações não zerado | par novo; o diário tem base antiga (sha256 diferente) e não se aplica; vira descartado |
Recuperar é idempotente (cada passo confere os sha256 de novo). Zerar o diário de transações (E7, E8) é um gancho `ao_concluir(seq)` passado pelo chamador: `gravacao_par.py` não importa `diario.py` (ver §9 item 5). A gravação inteira roda dentro de `ler()`, então nenhum registro novo entra entre o retrato e o zerar do diário. O diário de gravação é resolvido **antes** do diário de transações.

### 4.6 Desfazer depois de gravar e limite de memória (item 6, M1, M2)
- Padrão proposto: gravar **não** mexe no histórico; desfazer depois de gravar vale na mesma sessão (pergunta 1 ao PO). Funciona porque os ids sobrevivem à gravação (T02 §1) e os registros são autossuficientes (§4.4).
- Custo de um passo = bytes do registro JSON (que o diário já produz) × 12, o maior Python/JSON medido (T02 §2: 8 a 12). Limite inicial 256 MiB (M1) sobre a soma do histórico e do refazer; passando, saem os passos **mais antigos do histórico**, dos dois lados juntos, nunca no meio de uma transação; o refazer nunca é cortado (M2). Um passo maior que o limite fica sozinho. O diário não depende do histórico (M2 por construção).
- Aviso só quando um desfazer pedido não é mais possível porque o passo saiu. Medida (T08): memória do processo e `tracemalloc` numa sequência longa, contra a estimativa. Pelo T02 §2, 256 MiB cabem cerca de 1.650 "criar parede", 106 "apagar 50", 19,8 mil "posição".

### 4.7 Recuperação, autosave e merge (item 7, P5)
- Ao abrir `Casa.ifc`: primeiro o `gravacao.json` (§4.5); depois, se há diário com registros além da base e a base é o próprio `Casa.ifc` (mesmo sha256) ou o autosave cuja `origem_ifc_sha256` é a do `Casa.ifc`, pergunta "Recuperar o trabalho de HH:MM?" (hora local do último registro inteiro; na S05 uma função passada pelo chamador, sem Qt). Sim: abre a base, reaplica até o último registro inteiro, marca "recuperado, não gravado" e **nunca grava por cima** de `Casa.ifc` sozinho. Não: diário descartado (§4.4). Base que não casa: não aplica, avisa. Depois de recuperar, o histórico começa vazio (pergunta 3 ao PO).
- Autosave a cada 300 s, só se houve transação desde a última gravação ou autosave; em `ler()`; não carimba nem muda o modelo; grava o par com a rotina do T07 em `projetos/<LadoId>/autosave/`, com `"autosave": true` e `origem_ifc_sha256` no manifesto; depois zera o diário com base no autosave. Gravação normal bem-sucedida apaga o autosave (é nosso, na pasta local).
- Merge (T11, protótipo em `prototypes/s05/merge/`, não é portão): **por estado, não por operação**. Cada cópia dá o conjunto de donos tocados (§4.1) desde a base; conflito = interseção; o resto junta copiando o estado do dono da cópia que o mudou (subgrafo próprio, com ids novos e referências por GlobalId). Nada resolvido sozinho.

### 4.8 Módulos novos em `app/openbim_app/` (item 8; sem Qt, sem `obimcore`)
| Módulo | Cartão | Conteúdo público |
|---|---|---|
| `lateral.py` | T04 | `Lateral(objetos=None)`, `obter(c, id)` (cópia ou `None`), `ids(c)`, `colecoes()`, `canonico()` (bytes do lateral inteiro), `json_canonico(obj)`; `ObjetoInvalido`, `IdRepetido`, `IdInexistente` |
| `transacao.py` | T04 (T05 e T07 ligam; T08 limite) | `Historico(sessao, lateral, limite_bytes=None)`; `transacao(esc)` (gerenciador; dá `t.ifc` e `t.lado` com `criar`/`alterar`/`apagar`; depois de sair, `t.resumo`); `desfazer(esc)`, `refazer(esc)` (devolvem `Resumo` ou `None`); `pode_desfazer`, `pode_refazer`, `quebrado`, `descartados`; `encerrar()`; `Resumo(criados, alterados, apagados, lado_criados, lado_alterados, lado_apagados)`; `EdicaoForaDeTransacao`, `TransacaoAberta`, `HistoricoQuebrado`; `fora_do_historico(esc)` (gerenciador, só para o carimbo do pset `OBIM_Projeto`; não entra no histórico nem no diário) |
| `diario.py` | T05 | `pasta_base()`, `pasta_projeto(lado_id)`, `lado_id_de(arquivo, ifc_sha256)`; `codificar_ifc(ops)`, `decodificar_ifc(lista)`, `Diario` (abrir, anotar, sincronizar, zerar, fechar), `ler_diario(caminho)`, `recuperar(...)`; `OperacaoNaoSerializavel` |
| `gravacao_atomica.py` | T06 | `preparar(destino, escrever, conferir=None)` → `Preparado(destino, temporario, sha256, tamanho)`; `confirmar(preparado)` → `Gravado(caminho, sha256, tamanho, bak)`; `gravar_atomico(destino, escrever, conferir=None)` = `confirmar(preparar(...))`; `conferir_ifc(caminho)`; `limpar_temporarios(destino)`; `FalhaGravacao(etapa, motivo, caminho, gravado)`; `ETAPAS`; `_etapa(nome, caminho)`, chamada no começo de cada etapa (ponto de falha e de morte) |
| `gravacao_par.py` | T07 | gravar o par (usa `preparar`/`confirmar`), ZIP do lateral, manifesto, `gravacao.json`, `resolver_gravacao_pendente(...)`, gancho `ao_concluir(seq)` |
| `autosave.py` | T09 | `Autosave` (intervalo `INTERVALO_AUTOSAVE_S = 300`) |
Variáveis de ambiente: `OBIM_PASTA_LOCAL` (pasta base); `OBIM_S05_FALHA_EM=<etapa>` (a etapa levanta `OSError` EIO); `OBIM_S05_MORRER_EM=<etapa>` (a etapa chama `os._exit(86)`); `OBIM_S05_OBRIGATORIO=1` (pulo vira falha). A régua de comparação por conteúdo (P1) é código de teste do autor do oráculo (`tests/s05_conteudo_aux.py`), não de `app/`.

## 5. Opções consideradas
- **Oplog só nosso, sem o `Transaction` do ifcopenshell.** Contra: reescreve o que já funciona com 0 diferenças (T02 §1) e o Bonsai usa (`v2/03` F0-S05). Rejeitada.
- **Diário por referência ("desfazer o registro 17").** Contra: quebra quando o diário zera na gravação e o desfazer continua valendo (§4.6). Rejeitada.
- **`.bak` por renomear o original.** Contra: se a troca seguinte falhar, o original só existe como `.bak` (fere G3). Rejeitada.
- **Gravar o par todo em `escrever()`.** Contra: trava painéis e autosave durante segundos (ADR-004 §5). Só o carimbo usa `escrever()`.
- **Sha256 por registro do diário.** CRC-32 basta para registro cortado (não é segurança) e custa menos. Escolhido CRC-32.

## 6. Consequências
- T04 a T09 escrevem contra a §4.8; o implementador não inventa nome nem formato. Mudar um nome passa por este ADR.
- A guarda da §4.2 mexe em estado do ifcopenshell (`arquivo.transaction`); troca de versão do ifcopenshell exige rodar de novo os oráculos do T04 (ADR-005 fixa versão).
- Um `UndoSystemError` custa ao usuário reabrir pela recuperação; nada se perde além do histórico.
- O `fluxo_a.py` e o `lote.py` não mudam (régua, A29).

## 7. O que nos faria mudar de ideia
- Média acima de 5 ms em edição pequena com o resumo (T10): resumo sai da transação (calculado depois, fora da medida) e se leva ao PO; acima de 50 ms, gatilho do Rust (ADR-001 §9).
- `json.dumps` do registro de lote acima de 100 ms (T10): codificar em outra thread, com a confirmação esperando.
- Diferença por conteúdo em algum tipo de operação depois de reaplicar o diário (T05): ids não estáveis naquele caso; diário por operação de alto nível.
- Erro engolido pelo `rollback` aparecendo no oráculo do T04: conferência depois de cada desfazer, com custo medido.
- `os.link` recusado com frequência no Windows ou no OneDrive (T06, T10): `.bak` só por cópia.
- O merge do T11 com conflito falso por causa da regra de dono: revisar §4.1 antes da 2.0.

## 8. Não verificado
- Windows: `fsync`, `os.replace` com arquivo preso, `os.link` em NTFS e em pasta do OneDrive (vão ao T06 e ao T10).
- Se alguma função de `ifcopenshell.api` abre transação própria (a guarda da §4.2 quebraria); coberto pelos tipos de operação do oráculo do T04.
- Durabilidade do `os.replace` no Windows sem `fsync` da pasta.
- Escolhas deste ADR sem número medido (podem mudar sem nova decisão do PO): CRC-32, `uuid5` do sha256 para o `LadoId` provisório, código de saída 86, as pastas `%LOCALAPPDATA%` e `$XDG_DATA_HOME`, as 6 tentativas da troca e o fator 12 (este com base no T02 §2).

## 9. Ambiguidades e conflitos encontrados (resolvidos aqui; o PO pode mudar)
1. README da S05: "a gravação dentro de `ler()`", mas o carimbo `Revisao`/`LadoId` (G4) é escrita no modelo. Resolvido: carimbo numa `escrever()` curta fora do histórico, o resto em `ler()` (§4.5). Autosave não carimba.
2. `v2/03` pede "ifcdiff vazio"; a P1 trocou por comparação própria por conteúdo. Vale a P1.
3. P3 conta "edição pequena em memória com o registro do desfazer"; o resumo por dono é custo a mais. Resolvido do lado exigente: conta nos 5 ms (§4.1).
4. T02 sem Windows; o T10 mede.
5. **Para o líder (cartões):** (a) zerar o diário na gravação do par precisa do T05, mas o T07 não depende dele: resolvido com o gancho `ao_concluir(seq)` (§4.5); quem liga é o T09 ou o T05. (b) `fora_do_historico` fica no T04 (cerca de 5 linhas), porque o T07 só pode mexer no módulo do par; o oráculo do T04 já o cobre. (c) O T05 só pode criar "o módulo do diário": por isso a pasta local ficou dentro de `diario.py`, não em módulo próprio.

## 10. Perguntas ao PO
1. **Desfazer depois de gravar** vale até fechar o projeto? Recomendo **sim** (§4.6).
2. **Limite do desfazer em 256 megabytes**, conferido no T08 e no T10? Recomendo **sim** (§4.6).
3. **Depois de recuperar uma queda, desfazer começa vazio** na fase 0? Recomendo **sim** (§4.7).
