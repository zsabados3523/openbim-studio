# LOTE_OPUS_35: pedido (S04-T14c parte 3, PR 135; Windows windows-fluxo-b, run 38838633409, job 116773315921: 18 ok, 2 falhas)

**Falha 2 (mensagem "inv�lida"): defeito do oráculo.** O executável escreve UTF-8 (MSVC `/utf-8`); `rodar` decodificava com `text=True` (localidade = cp1252 no Windows). Prova no log: `'leg�\xadvel'` (o `í` = C3 AD lido em cp1252 vira `Ã` + hífen suave U+00AD). Reproduzido no Linux: a saída real decodificada em cp1252 reprova `"base inválida" in msg`; em UTF-8 aprova.
Conserto (feito): `tests/s04_fluxo_b_janela_aux.py` `rodar`: `encoding="utf-8", errors="replace"`. Não afrouxa: um executável que escreva cp1252 vira U+FFFD e continua reprovando (provado com emissor falso).

**Falha 1 (TKernel ausente): o teste era falso positivo no Linux; o conserto é no executável.**
- Não é a lista truncada (4096 módulos) nem o padrão (o filtro do `bibliotecas()` usa `tkernel` em minúsculas; `TKernel.dll` casaria).
- O executável não usa NENHUM símbolo do TKernel (`nm`: 0). O Linux o carrega só porque o `ld` guarda o NEEDED; o MSVC descarta a importação sem uso. Mesma causa: o Windows lista só `parse_schema_ifc4`, o Linux os quatro esquemas.
- O OCCT entra de verdade pelo plugin `ifcopenshell_geometry_kernel_opencascade` (NEEDED `libTKernel`), carregado por `dlopen`/`LoadLibrary` na 1a malha (`malha.cpp`, núcleo híbrido). Provado no Linux (LD_DEBUG): `--versao` não carrega o plugin; a rodada do roteiro R carrega o plugin e o TKernel de um caminho só.
- Logo o `--versao` olhava o processo antes da geometria: a régua "1 cópia por núcleo" nunca viu o OCCT da geometria em nenhum dos dois sistemas.

Oráculo (feito, mais estrito): `test_sem_python_no_processo_e_esquema_ifc4_registrado_por_codigo` mantém `TKernel == 1` e exige exatamente 1 `geometry_kernel_opencascade` na lista. NÃO entrou em `s04_aux.NUCLEOS` (também serve ao processo Python). No Linux, com o executável atual: 19 ok, 1 falha (a nova régua, `0 == 1`), como esperado.

**Executável (para o Sonnet; arquivo permitido: `prototypes/s04/fluxo_b/autotestes.cpp`):** no ramo `--versao` de `fluxo_b::autoteste`:
1. manter `reg` calculado PRIMEIRO (antes de qualquer modelo);
2. depois, `Paredes p; p.criar_tipo("PAR", {0.02, 0.11, 0.02}); auto g = p.criar_parede("PAR", 4, 2.8, 0.15);` e `auto m = obim::malhas_do_arquivo(p.arquivo(), g);` (include `malha.h`), exigindo malha não vazia (senão exceção: o main sai com erro);
3. só então `bibliotecas()` e o `resultado(...)`; atualizar o comentário ("depois de uma malha real: o OCCT entra pelo plugin").
Pronto quando: Linux e Windows verdes em `tests/test_s04_fluxo_b_janela.py` (20/20). O Opus revisa o diff.
