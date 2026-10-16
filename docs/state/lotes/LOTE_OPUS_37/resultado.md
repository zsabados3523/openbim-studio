# LOTE_OPUS_37: resultado — APROVADO (o Windows só se prova no CI)

**(1) Causa do TKernel: certa.** Log do Windows: o `--versao` listava só `parse_schema_ifc4`, `parse`, `geometry`, `plugin`, `Qt6Core`, sem plugin de núcleo nem TKernel. Executável novo no Linux: aparecem `ifcopenshell_geometry_kernel_{cgalsimple,cgal,opencascade}.so` e um `libTKernel.so.8.0.1` só. O carregamento acontece em `kernels::construct("hybrid-cgal-simple-opencascade")` (malha.cpp:40), ou seja, na primeira malha. A régua não afrouxa: `TKernel == 1` continua, e a nova linha só acrescenta uma exigência. Contraprova: o executável anterior (scratchpad/o14c1) reprova a régua. Agora a régua vê de fato o OCCT da geometria: 1 TKernel no processo, carregado pelo plugin. O padrão `geometry_kernel_opencascade` não casa `tree_opencascade_*` nem `ifcopenshell.geometry` (NUCLEOS usa ponto).
Windows: as DLLs seguem o mesmo nome dos plugins (`ifcopenshell_parse_schema_ifc4.dll` no log), então o plugin será `ifcopenshell_geometry_kernel_opencascade.dll`. A régua não diferencia maiúsculas e o conjunto conta caminhos distintos, então duas cópias em pastas diferentes reprovariam. Se o plugin não carregar, `construct` lança exceção, o main sai com 1 e o teste reprova com mensagem clara (nunca um falso verde). O roteiro R, que já usa malha, passou no Windows: o carregador acha o plugin lá.

**(2) UTF-8: correto, não esconde falha.** O executável escreve UTF-8 (`/utf-8`). `errors="replace"` faz um "inválida" em cp1252 virar U+FFFD, que não contém o trecho exato `base inválida`, e o teste reprova. As outras chamadas com `text=True` (test:48, :53) leem o Python filho, não o executável, e passaram no Windows.

**(3) autotestes.cpp: mínimo e correto.** `reg` continua calculado antes de qualquer modelo. A parede usa os mesmos números de `t_memoria`. Malha vazia ou `idx` vazio lança `runtime_error`, que o main captura e transforma em saída 1. Roda antes do QApplication (sem mexer na localidade), numa thread só. Nenhum outro autoteste nem o roteiro mudaram.

**(4)** `git diff origin/main --stat`: 295+/2−, dentro do limite. `ci.yml` só acrescenta o passo da T14c nos dois jobs; nada foi removido.

**(5)** Executável e obimcore recompilados no scratchpad (l37; links zlib/libxml2 em scratchpad/dev; `__init__.py` gerado como no build.sh). Comando: `OBIM_CI=1 OBIM_S04_T14_OBRIGATORIO=1 xvfb-run -a pytest tests/test_s04_fluxo_b_janela.py`. Rodada 1: 20 passaram em 60,6 s. Rodada 2: 20 passaram em 60,0 s. 0 pulados.

Observações (nenhuma bloqueia):
1. (baixa) autotestes.cpp:173: `malhas_do_arquivo(p.arquivo(), …)` roda sem `p.pegar(true)`, enquanto paredes.h:54 pede a trava de quem chama. Aqui é inofensivo (uma thread só, objeto local); fica só como nota de estilo.
2. (informativo) O comentário diz "carregado na 1a malha". Mais exato: o plugin carrega quando o núcleo híbrido é construído, e isso só acontece numa malha real.
3. (informativo) A prova do Windows depende do job windows-fluxo-b verde no CI.
