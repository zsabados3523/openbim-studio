# Resultado do lote 78: ADR-002 rascunho
STATUS do autor: SUCESSO, com 3 perguntas ao PO (resumo no topo do ADR). Diff 205 linhas (2 arquivos), commit ed8e2b7.
Decisões principais: uma transação nossa = um `Transaction` do ifcopenshell mais a lista do lateral; sentinela em `arquivo.transaction` recusa edição fora de transação; `UndoSystemError` deixa o histórico quebrado (reabrir pela recuperação); diário em JSONL com CRC-32 por linha, registros autossuficientes, `inverses` como lista de pares (falha do T02); gravação do par em `preparar`/`confirmar` com cópia de segurança por link; estados E1 a E8; custo de memória = JSON x 12; merge por estado e por dono.
Oráculos: régua R1 a R4; T04 com 12 casos (semente 20261023); T06 com 13 casos (inclui Windows).
Notas do autor ao líder: gancho `ao_concluir(seq)`; `fora_do_historico` no T04; pasta local dentro de `diario.py`; `escrever()` curta para o carimbo.
Não medido (vai ao T10): `json.dumps` do registro de lote, Windows (fsync, troca, link), custo do resumo por dono.
Revisão: lote 79 reprovou; correções no commit 9a171ec (ver `LOTE_OPUS_79/resultado.md`).
