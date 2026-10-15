# F0-S05-T00: Requisitos de gravação e de memória do desfazer (entram nos cartões da S05)
- Classe: T3 (gravação do par `.ifc` + `.obim`, transações) · Implementa: sonnet · Oráculo: **opus** (especificação e testes) · Revisa: opus, em lote
- Origem: revisão geral de 2026-10-15, achados A7, B5 e B26 (cartão F0-RG-06). Este cartão é **só texto**: nenhum código muda agora. Os cartões de implementação da S05 (criados quando a S05 começar) devem herdar estes requisitos como critérios de aceite.
- Depende de: S04 concluída. Fica parado até lá.
- Base nos documentos: `v2/02` §6.5 (gravação atômica do par, diário, autosave) e `v2/02` §6.2 (manifesto com `ifc_sha256`). Não altera `v2/`.

## Objetivo
Garantir que gravar nunca deixe `Casa.ifc` ou `Casa.obim` cortado, e que o histórico de desfazer não cresça sem limite.

## Requisitos de gravação (G)
- **G1. Arquivo temporário e troca.** Gravar em arquivo temporário **na mesma pasta** do destino (`Casa.ifc.tmp`), fechar, forçar a escrita no disco (`flush` + `os.fsync`) e só então trocar pelo nome final com `os.replace` (troca atômica no Windows e no Linux). Nunca gravar direto por cima do arquivo final (hoje o protótipo faz isso em `prototypes/s04/fluxo_a/fluxo_a.py`, função `_c_gravar`; não copiar esse padrão).
- **G2. Falha no meio não estraga nada.** Disco cheio, queda de energia ou erro ao gravar: o arquivo original continua inteiro e o temporário sobrando é apagado (ou achado e apagado na próxima abertura). No Windows, `os.replace` pode falhar se outro programa (antivírus, OneDrive) segura o arquivo: tentar de novo algumas vezes com espera curta e, se não der, avisar com mensagem clara, sem perder a cópia temporária.
- **G3. Cópia de segurança `.bak`.** Antes da troca, guardar a versão anterior como `Casa.ifc.bak` (e `Casa.obim.bak`), uma só geração. Se a troca falhar, o `.bak` e o original continuam lá.
- **G4. Mesma identificação no par.** `Casa.ifc` e `Casa.obim` gravados juntos levam a mesma `Revisao` e o mesmo `LadoId`; o manifesto guarda `ifc_sha256`, `ifc_tamanho` e `ifc_projeto_globalid` do IFC recém-gravado (`v2/02` §6.2). A ordem é a de `v2/02` §6.5: IFC primeiro, depois o lateral, com diário "gravação em andamento" na pasta local para a reabertura concluir ou desfazer.
- **G5. Conferir depois de gravar.** Reabrir o temporário (ou ler o hash) antes de trocar; se não abrir, abortar a troca.
- **G6. Caminhos reais.** Testar com acento e espaço no caminho (ex.: `C:\Users\João\Documentos\Residência\Casa.ifc`) e com pasta somente leitura (mensagem de erro clara).

## Requisito de memória do desfazer (M)
- **M1. Limite por memória, não por passos.** O protótipo usa `set_history_size(100000)` (`fluxo_a.py:60`), sem limite de memória. O produto deve limitar o histórico por **tamanho em memória** (valor inicial sugerido: 256 MB, ajustável, medido na S05) e descartar os passos mais antigos ao passar do limite, avisando o usuário só quando um desfazer pedido não for mais possível. Medir o custo por passo no modelo grande (`corpus/modelo-grande-1m.ifc`) antes de fixar o número.
- **M2.** Descartar passos antigos não pode corromper o refazer nem o diário de gravação.

## Critérios de aceite (para os cartões da S05)
1. Teste que mata o processo (ou simula erro) no meio da gravação: `Casa.ifc` e `Casa.obim` originais continuam abrindo, sem arquivo cortado.
2. Teste de disco cheio ou pasta somente leitura: erro claro, original intacto, temporário limpo.
3. Teste de caminho com acento e espaço.
4. Teste do par: após gravar, `Revisao`/`LadoId` iguais nos dois e `ifc_sha256` confere.
5. Teste do limite de memória do desfazer: passa do limite, descarta o mais antigo, memória estável.
6. T3: oráculo escrito pelo opus; revisão opus antes do merge.

## Fora de escopo
Autosave (outro cartão da S05), `.obimpack`, migração de formato, alterar `v2/`.

## Próximo passo
Aguarda a S05 começar; o líder copia G1–G6 e M1–M2 para os cartões de implementação.
