# LOTE_OPUS_53: resultado

**APROVADO.** As correções pedidas pelo lote 52 estão feitas e provadas. Nada novo quebrou. O que sobra são recomendações que **não bloqueiam** o merge.

Revisor: Opus, independente (não escreveu nada desta tarefa). Revisado: ramo `s04-t17a-impl`, commits `0328f55` (oráculo) e `8d580bf` (implementador), diff total contra `origin/main` (`f07e8c8`, que é o `main` remoto atual). CI: execução `39029741398` do pedido 152, no commit `8d580bf`.

## Ensaio do revisor
Tudo em pasta temporária minha, sem tela, sem instalar nem baixar nada, sem tocar a worktree do implementador nem os ambientes.

- **Sabotagem da trava do RPATH (achado 1).** Tirei o trecho Python do `build.sh` (linhas 37 a 101) e o rodei contra bibliotecas pequenas que compilei com `gcc`. Em cada caso de sabotagem, o ligador **juntou de verdade** o nome com o final do RPATH; conferi com `readelf -p .dynstr`. Resultado:

  | Caso | O que o nome reaproveita | Resultado |
  |---|---|---|
  | NEEDED `libbar.so` | final de `…:/tmp/libbar.so` | **recusou**, arquivo intacto |
  | símbolo `lib` (`.dynsym`) | final de `…:/opt/lib` | **recusou** |
  | SONAME `env/lib` | final de `…:/opt/env/lib` | **recusou** |
  | versão definida `VLIB` (verdef) | final de `…:/opt/VLIB` | **recusou** |
  | versão pedida `GLIBC_2.2.5` (verneed) | final de `…:/opt/GLIBC_2.2.5` | **recusou** |
  | caminho absoluto primeiro | — | **recusou** ("o primeiro caminho não é relativo") |
  | duas entradas RPATH/RUNPATH (forjada) | — | **recusou** ("esperava 1 … achei 2") |
  | cabeçalho big-endian, 32 bits ou arquivo de texto, com `python3 -OO` e `PYTHONOPTIMIZE=2` | — | **recusou** nos três (a conferência não some com otimização) |
  | caso normal (relativo + absoluto) | — | aceitou; mudou só os 36 bytes do trecho absoluto; permissão 755 mantida; segunda passada idêntica (idempotente) |
  | RUNPATH (`--enable-new-dtags`) | — | aceitou e encurtou, como esperado |

- **Módulo real.** Rodei a reescrita numa cópia de um `_obimcore` real anterior à reescrita, com RPATH `$ORIGIN/../../env/lib:/home/rafael/miniforge3/envs/openbim/lib`.
  - Mudaram 41 bytes, e o resultado ficou **idêntico byte a byte** ao módulo reescrito pelo implementador.
  - A permissão `rwxrwxr-x` foi mantida.
  - O módulo carrega com o Python do ambiente `openbim`: `versao()` responde, e as bibliotecas OCCT vêm do ambiente.
- **Conferência nova do `build_appimage.sh` (achado 11).** Rodei o script numa cópia do ramo (`git archive`), com um ambiente falso só até a conferência.
  - Com o módulo antigo, **parou** antes de apagar ou copiar qualquer coisa, com a mensagem "recompile com …/build.sh".
  - Com o módulo reescrito, passou da conferência.
  - O caminho reserva em Python puro (sem `readelf`) dá a mesma saída que o `readelf` nos três arquivos testados.
- **CI do pedido 152** (logs lidos com `gh api`, só leitura):
  - `linux`: `build.sh` imprime `RPATH … = $ORIGIN/../../env/lib` no build limpo e no incremental, e `tests/test_s04_ponte.py` dá **21 passed**.
  - Transporte do módulo: no `linux`, "Cache saved with key: obimcore-39029741398"; no `appimage`, "Cache hit … obimcore-39029741398".
  - Montagem: passou, com R-ABI e a conferência nova do RPATH.
  - `test_appimage.sh`: verde, incluindo `licenses/tsl-robin-map-MIT.txt` dentro do pacote; AppImage de **390 MB**.
  - R1-j: freeze `ok`, maps `ok`, filho spawn `valor=42 isolado=1` com Python e obimcore do pacote, **9 passed**, 0 pulados.
  - `reuse lint`: conforme.
  - `windows` e `instalador-windows`: verdes.

## a) Achados 1, 2, 3, 4, 11, 12, 13 e 15 do lote 52
1. **Achado 1 (trava contra apagar texto compartilhado): corrigido** (OK). `prototypes/s04/obimcore/build.sh:57-96`.
   - A conta de sobreposição está certa: um nome que começa antes do fim do RPATH e termina depois do ponto de corte é recusado.
   - Os casos de borda estão certos. Um nome vazio no fim não é recusado, o que é correto. Uma segunda passada não dá falso alarme.
   - Os formatos de verneed e verdef (`<HHIII>`/`<IHHII>`, `<HHHHIII>`/`<II>`) e o uso de `sh_info` como contagem estão certos.
   - A trava falha fechado: na dúvida, recusa. Por exemplo, ela também lê entradas depois do primeiro `DT_NULL`. Um falso alarme é aceitável aqui, porque só faz o build parar com mensagem clara.
   - **Informativo, não bloqueia:** as marcas `DT_AUDIT`, `DT_DEPAUDIT`, `DT_CONFIG` e `DT_USED` também apontam para textos e não são lidas. O ligador não as gera para este módulo. Só importaria se alguém passasse `--audit`/`--depaudit` ao ligador.
2. **Achado 2 (permissão): corrigido** (OK). `build.sh:99`. Provado com 755 e 775.
3. **Achado 3 (`assert` e `EI_DATA`): corrigido** (OK). `build.sh:40-47`. Não sobrou nenhum `assert`; a função `erro()` sai com código 1. A conferência pega `b[4] == 2` (64 bits) e `b[5] == 1` (little-endian); provado com `-OO`.
4. **Achado 4 (nota de desenvolvimento): feito** (OK). `docs/dev-setup.md:24` explica o RPATH único e avisa que o módulo só deve rodar com o Python do ambiente `openbim`.
5. **Achado 11 (conferência do RPATH antes de copiar): feito** (OK). `packaging/linux/build_appimage.sh:37-60`. Provado com o módulo antigo (recusa) e com o novo (passa). A comparação é exata, então uma segunda entrada também reprova.
6. **Achado 12 (comentários do `freeze_support`): corrigido** (OK). `app/openbim_app/main.py:12-13` e `packaging/linux/AppRun:18-19` agora dizem a verdade. Conferi no Python 3.12 do ambiente:
   - `context.freeze_support` só age com `win32` e `frozen`;
   - `spawn._fixup_main_from_name` não reexecuta `*.__main__`;
   - o AppRun usa `run_module("openbim_app", run_name="__main__")`, então o nome que o filho recebe é `openbim_app.__main__`.
7. **Achado 13 (aviso MIT do `tsl::robin_map`): corrigido.** Detalhes no item c).
8. **Achado 15 (nota do inventário): feito** (OK). `build_appimage.sh:104-106` (comentário e nota) cita:
   - nanobind e robin_map, compilados dentro do módulo;
   - Eigen e Boost, só como cabeçalhos;
   - IfcOpenShell, OCCT e Qt, por bibliotecas dinâmicas.

## b) Nome do passo R1-j e a regra do `main`
9. **Confirmado: o `appimage` é obrigatório; a premissa do achado 7 do lote 52 estava errada** (OK).
   - O conjunto de regras `proteger-main` (id 24852429, ativo, atualizado em 2026-10-14) exige `linux`, `windows`, `appimage` e `instalador-windows`. Li isso com `gh api …/rulesets/24852429`.
   - O nome novo do passo (`ci.yml:769`) diz a verdade. O R1-j bloqueia o merge, e o merge automático espera por ele.
   - **Retiro as duas condições do achado 7:** "não ligar o merge automático" e "levar ao PO tornar o R1-j bloqueante". O job agregador também não é mais necessário.
   - **Ponto que não abre brecha:** o GitHub conta como aprovada uma verificação obrigatória cujo job foi pulado por `needs`. Aqui o `appimage` só é pulado quando o `linux` não passou, e o `linux` também é obrigatório. Então não há caminho de merge sem o R1-j rodar e passar.
10. **Comentários antigos no `ci.yml` contradizem a regra** (BAIXA; **não bloqueia**).
    - `ci.yml:688` diz "Não bloqueia o merge; o nome do job não é usado na regra". `ci.yml:18` cita só `linux` e `windows` como jobs da regra.
    - Os dois comentários vêm do `main` (commits de 10 e 11/10), não desta tarefa. Mas foram eles que levaram o lote 52 ao erro do achado 7.
    - Não mudam as verificações exigidas, por isso não reprovo. Uma correção agora mudaria o conteúdo aprovado.
    - **Pedido:** corrigir numa próxima tarefa T0 de texto.
11. **O `CLAUDE.md` está desatualizado nesse ponto** (BAIXA; decisão do PO). As linhas 58 e 60 dizem que só `linux` e `windows` são obrigatórios, mas a regra real tem quatro jobs. O `CLAUDE.md` só muda com o ok do PO: levar a ele.
    - Informativo para a mesma conversa: na regra, só o `linux` está preso ao aplicativo GitHub Actions (`integration_id` 15368). `windows`, `appimage` e `instalador-windows` aceitam um resultado vindo de qualquer fonte com permissão de escrita no repositório. O risco é baixo num repositório de um dono só.

## c) Aviso do `tsl::robin_map`
12. **Texto literal certo e dentro do pacote** (OK).
    - `packaging/licenses-texts/tsl-robin-map-MIT.txt` é **idêntico** às linhas 2 a 22 do cabeçalho `nanobind/ext/robin_map/include/tsl/robin_map.h` do ambiente `openbim`, tirando só o ` * ` do comentário (conferi com `diff`).
    - Os três cabeçalhos do robin_map (`robin_map.h`, `robin_hash.h`, `robin_growth_policy.h`) têm o mesmo aviso, e o pacote do nanobind não traz um `LICENSE` próprio do robin_map. Então o cabeçalho é a fonte certa.
    - O arquivo é ASCII, termina em quebra de linha e conta como texto verbatim de licença.
    - Ele entra no pacote:
      - pelo laço de `build_appimage.sh:98`, que falha se faltar;
      - foi conferido no CI por `test_appimage.sh`;
      - está listado em `LEIA-ME.md:15` e em `THIRD_PARTY.md:18`.
    - O aviso do nanobind continua idêntico ao `LICENSE` do pacote 3.1.0 (`cmp`).
13. **Versão do robin_map na tabela** (BAIXA; texto; não bloqueia). `THIRD_PARTY.md:18` põe "3.1.0 (do nanobind)" na coluna de versão. Esse número é a versão do nanobind, não a do robin_map. Melhor escrever "a que vem no nanobind 3.1.0" numa próxima tarefa de texto.
14. **Outro titular de direitos dentro do nanobind** (BAIXA; recomendação; não bloqueia).
    - O `src/nb_datetime.cpp` do nanobind é compilado dentro do `_obimcore` (aparece no log de build do CI). Ele traz "Copyright (c) 2023 Hudson River Trading LLC" além do Wenzel Jakob, e remete à mesma licença BSD do nanobind, que já vai no pacote. A licença está coberta.
    - Para seguir a letra da BSD ("reproduzir o aviso de copyright"), a nota do `INVENTARIO.md` pode citar esse segundo titular numa próxima tarefa de texto.
    - Os cabeçalhos com outros titulares (`stl/complex.h`, `eigen/tensor.h`) não são incluídos pelo `obimcore` (procurei nos `.cpp`).

## d) Nada novo quebrou
15. **Oráculo intocado** (OK).
    - `git diff origin/main...HEAD` está vazio para `tests/`, `packaging/linux/test_appimage_ponte.sh` e `packaging/linux/ponte_no_pacote.py`.
    - `packaging/linux/test_appimage.sh` difere do `main` em **uma linha só**, a lista de licenças, que ganhou `nanobind-BSD-3-Clause.txt` e `tsl-robin-map-MIT.txt`. Ela veio de dois commits só de oráculo (`f25f556` e `0328f55`); o `8d580bf` do implementador não toca esse arquivo.
    - Como no lote 52, o git **não prova** que foi outro agente: o autor e o coautor Sonnet são os mesmos nos dois commits. Fica pela palavra do líder.
16. **O `8d580bf` não muda comportamento além do pedido** (OK).
    - No `ci.yml`, só mudou o nome do passo R1-j. O resto são o `build.sh`, o `build_appimage.sh`, textos, comentários e notas. Todos os jobs obrigatórios estão verdes.
17. **macOS vermelho: já estava assim, não é desta tarefa** (OK; informativo).
    - O job `macos` falha também nas duas últimas execuções do `main` (`f07e8c8` e `a5f35a3`), pelos mesmos testes de tempo da viewport (`test_viewport_processo`, `test_viewport_responsivo`).
    - Aqui falhou um terceiro teste de tempo (`test_viewport_carregador:474`, 0,198 s contra o limite de 0,05 s). A T17a não toca a viewport.
    - Ela também não toca o macOS: a mudança no CMake está sob `UNIX AND NOT APPLE`, e a reescrita só roda no Linux.
    - O macOS não bloqueia o merge. O próprio CI pede para registrar o motivo em LOG.md.

## e) Tamanho do diff
18. **Abaixo de 400 linhas** (OK). `git diff --numstat origin/main...HEAD`: 257 linhas (+246 −11) em 14 arquivos. Sem os dois textos verbatim de licença (26 + 21 = 47 linhas), ficam **210 linhas**.

## O que o líder deve registrar
- **LOG.md:** preencher a linha 181 assim: "Lote opus 53 | APROVADO | T17a: correções do lote 52 conferidas (trava do RPATH sabotada em 8 casos, aviso do robin_map literal, R1-j obrigatório pela regra `proteger-main`); achado 7 do lote 52 retirado (premissa errada); recomendações sem bloqueio: comentários antigos do `ci.yml:18/688`, versão do robin_map no `THIRD_PARTY.md`, segundo titular do nanobind na nota do inventário, marcas DT_AUDIT/DEPAUDIT/CONFIG na trava."
- **LOG.md:** registrar o motivo do macOS vermelho (testes de tempo da viewport, os mesmos do `main`; mais um nesta execução, `test_viewport_carregador`).
- **Ampliação dos arquivos permitidos:** já está na linha 180 do LOG e no cartão. O `8d580bf` voltou a mexer em `build.sh`, `THIRD_PARTY.md` e `docs/dev-setup.md`, dentro do que a linha 180 já aceita. Nada novo a registrar.
- **Merge:** a autorização permanente (item 3) permite, porque o conteúdo exato (`8d580bf`) está aprovado aqui e `linux`, `windows`, `appimage` e `instalador-windows` estão verdes. Avisar o PO depois, em resumo curto. Qualquer commit novo neste ramo antes do merge precisa de nova aprovação.
- **Levar ao PO (sem pressa, não bloqueia):** o `CLAUDE.md` diz que só `linux` e `windows` são obrigatórios, e a regra real tem quatro jobs (achado 11).
- **Continuam abertas do lote 52, sem bloqueio:**
  - achado 10: R-ABI também contra o ambiente real;
  - achado 16: etiqueta REUSE dos textos de licença (decisão do PO);
  - achado 20: cartão de oráculo para a prova 6 do ADR-005;
  - achado 21: tamanho antes e depois no relatório do pedido. O deste pedido é 390 MB; falta copiar o do `main`.
- **Nova tarefa T0 de texto:** achados 10, 13 e 14 deste lote.
