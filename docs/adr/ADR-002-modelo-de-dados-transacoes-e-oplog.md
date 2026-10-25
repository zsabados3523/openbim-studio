<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
# ADR-002: Modelo de dados, transações e diário

Status: aceito

## Contexto
Toda mudança no projeto precisa poder ser desfeita, anotada na hora (para recuperar uma queda) e gravada sem deixar o par `Casa.ifc` + `Casa.obim` pela metade. O protótipo anterior tinha transação só do IFC, histórico de 100.000 passos sem limite de memória e gravava direto por cima do destino.

O que o ifcopenshell 0.9.0 faz (lido em `ifcopenshell/file.py`) condiciona o desenho:
- sem transação aberta, a edição não é registrada e some do desfazer em silêncio;
- ao passar de `history_size` (padrão 64), o passo mais antigo é jogado fora sem aviso;
- `undo` e `redo` tiram o passo da pilha antes de aplicar; se falharem (`UndoSystemError`), o modelo fica pela metade;
- `rollback` engole erros ao restaurar valores, e erro engolido não se detecta em execução;
- o estado do desfazer mora num dicionário da classe (`file.registry`), que nunca é limpo.

## Opções
- **Registro só nosso, sem o `Transaction` do ifcopenshell.** Rejeitada: reescreve o que já funciona (ids STEP idênticos depois de gravar, reabrir e desfazer tudo: 0 diferenças em 1,4 milhão de entidades) e que o Bonsai usa.
- **Diário por referência ("desfazer o registro 17").** Rejeitada: quebra quando o diário zera na gravação e o desfazer continua valendo.
- **`.bak` por renomear o original.** Rejeitada: se a troca seguinte falhar, o original só existiria como `.bak`.
- **Gravar o par inteiro dentro de `escrever()`.** Rejeitada: trava painéis e autosave por segundos (ADR-004). Só o carimbo de revisão usa `escrever()`.
- **SHA-256 por registro do diário.** CRC-32 basta para detectar registro cortado (não é segurança) e custa menos.

## Decisão
**Duas camadas de registro.** Camada 1: o `Transaction` do ifcopenshell mais a lista de operações do lateral; serve para desfazer, refazer e reaplicar o diário sobre o mesmo arquivo base. Camada 2: ao fechar cada transação, o conjunto de GlobalIds criados, alterados e apagados; serve à tela e a um futuro merge. Objeto sem GlobalId (posição, valor de propriedade) sobe pelos inversos até o objeto dono; relação nunca é dona.

**Transação única** (`transacao.py`, classe `Historico`). Uma transação nossa é exatamente um `Transaction` do ifcopenshell mais a lista do lateral, e as duas pilhas andam juntas. Fora da nossa transação, `arquivo.transaction` vira um objeto sentinela que levanta `EdicaoForaDeTransacao` antes de aplicar. Só `SessaoModelo.escrever()` (`sessao_modelo.py`) abre transação. Exceção dentro da transação: `discard_transaction` e o lateral volta na ordem inversa. `UndoSystemError` deixa o histórico "quebrado" (`HistoricoQuebrado`); o caminho é reabrir pela recuperação, que reconstrói o estado da base e do diário.

**Lateral provisório** (`lateral.py`). Coleções de objetos JSON puros por id; operações `criar`, `alterar` (troca o objeto inteiro) e `apagar`. Referência ao modelo só por GlobalId. Apagar uma parede não mexe no lateral (órfão visível). Em disco, um ZIP com `manifest.json` (`versao_formato` "0.1.0", `provisorio: true`) e um JSON por objeto; o formato final é decisão futura.

**Diário** (`diario.py`). Fica em `<base>/projetos/<LadoId>/diario/diario.obimlog`; `<base>` é `OBIM_PASTA_LOCAL` (testes), `%LOCALAPPDATA%\OpenBIMStudio` no Windows ou `$XDG_DATA_HOME/OpenBIMStudio` nos outros. Uma linha por registro: `<crc32 em 8 dígitos hex> <JSON compacto>`. Primeiro registro `base` (sha256 e tamanho do IFC, sha256 do `.obim`, `lado_id`); depois `transacao`, `desfazer` e `refazer`, cada um com as operações inteiras (nunca referência a registro anterior). Registro confirmado = linha escrita e `flush`; `fsync` 2 s depois do primeiro registro pendente, ao gravar e ao fechar. Leitura: linha cortada ou com CRC errado é ignorada com aviso; buraco em `seq` para ali e aplica até a anterior. O diário zera depois de cada gravação do par. Operações viram JSON como o ifcopenshell serializa; `inverses` vai como lista de pares. Valor que não vira JSON levanta `OperacaoNaoSerializavel` e a transação é descartada.

**Gravação de um arquivo** (`gravacao_atomica.py`). Etapas, nesta ordem: `escrever` (em `Casa.ifc.tmp`, mesma pasta), `fsync`, `conferir` (começo e fim do texto IFC), `bak` (`os.link` do destino para `.bak.tmp` e `os.replace`; o destino nunca deixa de existir), `trocar` (`os.replace`, 6 tentativas com espera dobrando se o Windows recusar), `fsync_pasta` (Linux e macOS). Falha antes de `trocar` apaga os temporários e deixa destino e `.bak` intactos.

**Gravação do par** (`gravacao_par.py`). Escreve o carimbo `Revisao` + 1 e `LadoId` no pset `OBIM_Projeto` numa `escrever()` curta fora do histórico, e grava o resto dentro de `ler()`. Um diário de gravação (`projetos/<LadoId>/gravacao.json`, trocado atomicamente) guarda destinos, sha256 novos e antigos. Ao reabrir, 10 estados de queda (E1 a E10) têm resposta definida: antes de qualquer troca, volta ao par antigo; com os dois temporários conferidos pelos sha256, conclui; IFC trocado e lateral não, conclui ou devolve o IFC do `.bak`; sha256 desconhecido (outro programa mexeu) ou cópia do projeto com o mesmo `LadoId`, não mexe em nada e avisa. A recuperação é idempotente e o diário de gravação é resolvido antes do diário de transações.

**Desfazer depois de gravar e limite de memória.** Gravar não mexe no histórico, então desfazer continua valendo até fechar o projeto (os ids sobrevivem à gravação). O custo de um passo é o tamanho do registro JSON vezes 12 (maior razão Python/JSON medida, 7 a 12). Limite inicial de 256 MiB sobre histórico mais refazer; passando, saem os passos mais antigos, nunca no meio de uma transação. Em ordem de grandeza: cerca de 1.600 criações de parede, cerca de 80 apagamentos de 50 paredes ou mais de 11 mil mudanças de posição.

**Recuperação.** Ao abrir `Casa.ifc` com diário além da base (mesmo sha256), pergunta se recupera o trabalho; sim reaplica até o último registro inteiro e nunca grava por cima do arquivo sozinho. Depois de recuperar, o histórico de desfazer começa vazio.

## Números medidos (Linux, NVMe ext4)
| Fato | Número |
|---|---|
| Transação média / p95 em modelo de 50 MB (ms) | nome 0,059 / 0,073; posição 0,939 / 1,809; criar parede 4,321 / 5,992; apagar 50 em lote 96,79 / 115,67 |
| Registro JSON por transação | posição 1.934 B; criar parede 13.845 B; apagar 50 em lote 268.442 B |
| Linha de 120 B: `flush` / `flush` + `fsync` | 0,001 / 0,647 ms |
| Troca atômica de 1 MB sem / com `fsync` da pasta | 2,2 / 2,9 ms |
| `file.registry` com modelo de 50 MB aberto | +246 MB; `registry.clear()` solta |

## Consequências
- Quem escreve contra estes módulos não inventa nome nem formato; mudar um nome passa por este ADR.
- A sentinela mexe em estado interno do ifcopenshell (`arquivo.transaction`); trocar a versão da biblioteca exige rodar de novo os testes de `tests/test_s05_t04_*`.
- Um `UndoSystemError` custa ao usuário reabrir pela recuperação; nada se perde além do histórico.
- Fechar o projeto limpa `history`, `future`, `transaction` e a entrada de `file.registry`.

## O que nos faria mudar de ideia
- Média acima de 5 ms em edição pequena com o resumo por dono: o resumo sai da transação; acima de 50 ms, abre a linha de Rust (ADR-001).
- `json.dumps` do registro de lote acima de 100 ms: codificar em outra thread.
- Diferença por conteúdo em algum tipo de operação depois de reaplicar o diário: passar a diário por operação de alto nível.
- Erro engolido pelo `rollback` aparecendo nos testes: conferência depois de cada desfazer.
- `os.link` recusado com frequência no Windows ou no OneDrive: `.bak` só por cópia.

## O que ficou em aberto
- Windows: `fsync`, `os.replace` com arquivo preso e `os.link` em NTFS e OneDrive não foram medidos.
- Autosave a cada 300 s e a ordem de abertura (gravação pendente, autosave, diário) estão especificados mas ainda não existem em `app/`.
- Merge de duas cópias: previsto por estado e por dono tocado, sem implementação.
- Não há varredura completa de quais funções de `ifcopenshell.api` abrem transação própria; a conferência de `HistoricoQuebrado` as detecta.
- Escolhas sem número medido: CRC-32, `uuid5` do sha256 para o `LadoId` provisório, 6 tentativas da troca, fator 12 do limite de memória.
