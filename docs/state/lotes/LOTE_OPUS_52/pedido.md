# LOTE_OPUS_52: revisão do F0-S04-T17a (obimcore dentro do AppImage)
Pedido do líder (2026-10-17). Contexto fechado: pedido nº 152, ramo `s04-t17a-impl` (worktree `../openbim-studio-wt-t17a-impl`), diff contra `origin/main` (150 linhas, 12 arquivos); cartão `docs/state/cards/F0-S04/F0-S04-T17.md` (parte T17a); oráculo já mesclado (pedido 151: `packaging/linux/test_appimage_ponte.sh`, `ponte_no_pacote.py`, escritos por outro agente); especificação `docs/state/arquivo/lotes-1-a-28/LOTE_OPUS_9/resultado.md` §1.5 (R1-j) e ADR-005 §7.1.
Itens a julgar:
1. O RPATH do módulo é reescrito no lugar (sem `patchelf`) por Python puro em `prototypes/s04/obimcore/build.sh`; está correto e seguro (tamanho, preenchimento, idempotência, só Linux)? O mesmo binário serve ao pacote e ao desenvolvimento sem esconder problema?
2. O envio do módulo entre os jobs `linux` e `appimage` por `actions/cache` (chave por `run_id`, `fail-on-cache-miss`) é confiável e não enfraquece os checks obrigatórios? `needs: linux` muda algo nas regras do `main`?
3. A conferência R-ABI entre as duas travas e a falha do `build_appimage.sh` sem `OBIMCORE_DIR`.
4. `freeze_support()` em `main.py` e no `AppRun`: posição correta?
5. Licença do nanobind (BSD-3-Clause, estático): arquivo, `THIRD_PARTY.md`, inventário, `REUSE.toml`.
6. O implementador não tocou nos arquivos de oráculo (`test_appimage_ponte.sh`, `ponte_no_pacote.py`, `tests/test_s04_ponte.py`) e as mudanças em `test_appimage.sh` foram só a linha da licença (outro agente)?
7. O que o ensaio local NÃO provou (imagem real, FUSE, poda de vtk/ffmpeg) e o que o CI do pedido tem de mostrar antes do merge.
Saída: APROVADO ou REPROVADO, lista numerada de achados (com arquivo e linha) e recomendações; no fim, uma lista curta do que conferir no CI do pedido 152.
