# LOTE_OPUS_52: resultado

**REPROVADO** (2 correções obrigatórias no código, 1 condição de merge e 1 registro de processo; o resto está correto).

Revisor: Opus, independente (não escreveu nada desta tarefa). Revisado: ramo `s04-t17a-impl`, 4 commits (`680a70b`, `241f49c`, `0b5a1ca`, `f25f556`), diff contra `origin/main` (`f07e8c8`), 12 arquivos, 150 linhas.

## Ensaio do revisor (local, sem tela, sem instalar nada, sem tocar a worktree do implementador)
Cópia do ramo (`git archive`) numa pasta temporária minha:
- **Compilação:** `build.sh` compilou e reescreveu o RPATH: `$ORIGIN/../../env/lib`. Ressalva: o ambiente `openbim` local não tem o pacote `zlib` que a trava tem (só `libz.so.1`), e o CMake só configurou com `-DZLIB_LIBRARY=.../libz.so.1`, que pus só na minha cópia. O ambiente local está atrás da trava. Isso não afeta o CI, que cria o ambiente pela trava.
- **Antes da reescrita:** religuei o módulo sem a reescrita. O RPATH original era `$ORIGIN/../../env/lib:/home/rafael/miniforge3/envs/openbim/lib`, com o relativo primeiro. A reescrita mudou **só 41 bytes**, exatamente o trecho `:/home/...lib`; o resto do binário é idêntico byte a byte.
- **Desenvolvimento:** `tests/test_s04_ponte.py` com o módulo reescrito: **21 passaram, 0 pulados**. O Python do conda tem `DT_RPATH $ORIGIN/../lib`, então a reserva descrita no CMakeLists funciona.
- **Pacote:** montei o AppDir com o `build_appimage.sh` do ramo e o runtime local, sem appimagetool. A poda tirou 139 pacotes, o mesmo número do CI. O R1-j (`test_appimage_ponte.sh` na pasta) passou: freeze, maps, filho spawn (valor 42, isolado, Python e obimcore do pacote) e **9 casos passaram** de R1-a/d/e/i. Todas as dependências diretas do módulo estão em `env/lib`, menos libc, libm e ld-linux.
- **Controle negativo:** com o módulo de RPATH absoluto no AppDir, o oráculo reprovou no passo do RPATH, como devia.
- **Outros:** `reuse lint` na worktree do ramo: conforme (467/467). Cópia da licença do nanobind: idêntica ao `LICENSE` do pacote (`cmp`).

## Achados por item do pedido

### Item 1: reescrita do RPATH em `build.sh` e o mesmo binário nos dois usos
1. **Leitura do ELF correta; falta trava contra "cauda compartilhada"** (MÉDIA, **obrigatória**). `prototypes/s04/obimcore/build.sh:36-60`.
   - Os deslocamentos estão certos: `e_shoff` 0x28, `e_shentsize/e_shnum` 0x3A, `Elf64_Shdr` `<IIQQQQII`, `.dynamic` → `sh_link` = `.dynstr`, `Elf64_Dyn` de 16 bytes, tags 15/29.
   - O preenchimento com NUL mantém o tamanho do arquivo e não move nada. É idempotente (na segunda passada o primeiro item já é o único) e só roda no Linux.
   - **O risco:** o ligador GNU junta, na `.dynstr`, textos que são o final de outro texto (*tail merging*). Se algum nome de símbolo, `NEEDED`, `SONAME` ou nome de versão apontar para dentro do trecho zerado, esse nome vira vazio e o binário fica corrompido.
   - Conferi a compilação atual com um leitor próprio: 678 referências, **nenhuma** dentro do trecho. O risco é baixo, mas o pedido manda reprovar RPATH que *possa* corromper, e a trava custa poucas linhas.
   - **Correção:** antes de zerar, percorrer as referências à `.dynstr`: `.dynsym` (`st_name`), entradas da `.dynamic` com texto (tags 1, 14, 15, 29), `SHT_GNU_verneed` (`vn_file`, `vna_name`) e `SHT_GNU_verdef` (`vda_name`). Falhar se alguma cair em `(ini+len(novo), fim]`.
2. **A permissão de execução do `.so` se perde** (BAIXA, corrigir junto). `build.sh:57-58`. O `open(arq + ".novo", "wb")` cria o arquivo com a máscara padrão: o meu ficou `rw-rw-r--`, o original era `rwxrwxr-x`. Não impede o carregamento, mas muda o arquivo sem motivo. **Correção:** `os.chmod(arq + ".novo", os.stat(arq).st_mode)` antes do `os.replace`.
3. **Conferências por `assert`** (BAIXA, corrigir junto). `build.sh:40,53,56`.
   - Com `PYTHONOPTIMIZE` no ambiente, os `assert` somem. O CI ainda pega o erro pela comparação exata em `ci.yml:134-135`; uma compilação local, não.
   - Também falta conferir `EI_DATA == 1` (little-endian; `b[5]`).
   - **Correção:** trocar os `assert` por `if ...: sys.exit("OBIMCORE: ...")` e acrescentar a conferência de `b[5]`.
4. **O mesmo binário serve aos dois usos sem esconder problema** (OK, com 1 observação).
   - No pacote, `$ORIGIN/../../env/lib` aponta para o `env/lib` do pacote.
   - No desenvolvimento, esse caminho não existe (`out/env/lib`), e o carregador usa o `DT_RPATH $ORIGIN/../lib` do Python do conda. Ficou `RPATH`, não `RUNPATH` (`--disable-new-dtags`). Só assim o RPATH do executável vale de reserva, e ele também ganha do `LD_LIBRARY_PATH` do usuário. A escolha está certa, e os 21 casos de desenvolvimento e o controle negativo confirmam.
   - **Observação:** fora de um Python do conda (por exemplo, o Python do sistema com `PYTHONPATH`), o módulo agora cairia nas bibliotecas do sistema, quando antes achava as do ambiente pelo caminho absoluto. Ninguém deve rodar assim, e o R1-e no job `linux` pegaria o problema. Só registrar em `docs/dev-setup.md` numa próxima tarefa de documentação.
   - Alternativa que não peço: reescrever só a cópia em `build_appimage.sh`. Ela tem a desvantagem de o binário do pacote deixar de ser o mesmo que o job `linux` testou. A opção do implementador é melhor.

### Item 2: envio por `actions/cache` e `needs: linux`
5. **O transporte por cache é confiável e falha fechado** (OK).
   - `ci.yml:137-144` usa `lookup-only: true`: com a chave nova não há acerto, e o passo final da ação grava. O `actions/cache` só grava se o job inteiro passou (`post-if: success()`); o comentário da linha 137 está certo.
   - `ci.yml:726-733` usa `fail-on-cache-miss: true`: sem o módulo, o job `appimage` reprova, sem montar o pacote errado.
   - A chave `obimcore-${{ github.run_id }}` é única por execução, e não há `restore-keys`, então o cache de outra execução não pode ser pego. Um PR não grava no escopo do `main`. Os arquivos são pequenos (módulo de ~370 kB e pytest), sem risco para o limite de cache.
   - A cópia para `$RUNNER_TEMP` (`ci.yml:125-136`) acontece logo depois do teste do módulo. Assim vai ao pacote o binário exato que o `tests/test_s04_ponte.py` testou, conferido por `readelf`. Com `bash -e`, a linha `ci.yml:131` (`[ -e ] && cp` no laço) não derruba o passo; conferi.
   - Risco baixo de reexecução: em "Re-run all jobs", a chave já existe, o `linux` não grava de novo e o `appimage` usa o módulo da 1ª tentativa. É o mesmo commit, então serve.
6. **`needs: linux` não muda as regras do `main`** (OK). As verificações obrigatórias continuam sendo `linux` e `windows`. O `appimage` não é obrigatório: se o `linux` falhar, o `appimage` é pulado e o merge já está bloqueado pelo `linux`. Os dois passos novos no `linux` só **acrescentam** um motivo de falha (RPATH errado) a uma verificação obrigatória. Nenhuma verificação obrigatória foi enfraquecida.
7. **CONDIÇÃO DE MERGE: o R1-j não bloqueia o merge** (ALTA, de processo; não é defeito do implementador).
   - `ci.yml:769` põe o R1-j no job `appimage`, que não é obrigatório.
   - A especificação diz o contrário: LOTE_OPUS_9 §1.5 ("Todos rodam em `linux` e `windows` do CI, bloqueando o merge"), a linha M1 de §2.2 ("R1-a a R1-j … bloqueia") e §2.4.
   - O cartão (critérios 1 e 5) aceitou o job `appimage`. Há um **conflito entre cartão e especificação**, e quem decide é o PO.
   - **Perigo concreto:** o merge automático está ligado no projeto, e agora o `appimage` só começa depois do `linux`. O PR 152 pode entrar no `main` com `linux` e `windows` verdes enquanto o R1-j ainda roda, ou já falhou.
   - **Pedido:**
     - a) **não** ligar o merge automático neste PR; o líder confere à mão que o `appimage` (R1-j) está verde antes do merge;
     - b) levar ao PO a escolha de tornar o R1-j bloqueante. O caminho mais simples segue o padrão que o `windows` já usa: o job atual vira `linux-testes`, e um job `linux` agregador faz `needs: [linux-testes, appimage]`. O nome da regra não muda. Isso mexe em regra de processo, então o PO aprova antes.
8. **Fuga do cartão: artefato trocado por cache** (MÉDIA, processo). O cartão (§Como 1) pedia `upload-artifact`/`download-artifact` e "perguntar ao líder antes" de outro caminho. A escolha é tecnicamente boa: não acrescenta ação nova e falha fechado. O líder tem de registrar a aceitação em LOG.md e no cartão.

### Item 3: conferência R-ABI e falha sem `OBIMCORE_DIR`
9. **A falha sem o módulo está correta** (OK). `packaging/linux/build_appimage.sh:26-30`: vazio, pasta errada ou sem `_obimcore*.so` dá falha com mensagem clara, antes de apagar ou copiar qualquer coisa.
10. **A R-ABI faz o que o cartão pede, mas compara arquivos do repositório, não os ambientes** (BAIXA; recomendação).
    - `build_appimage.sh:32-36` compara os builds de `ifcopenshell`, `occt`, `pyside6` e `qt6-main` nas duas travas; hoje são iguais.
    - No CI isso basta, porque os dois ambientes nascem das travas (`conda create --file`). Numa montagem local (README passo 4), o ambiente real pode estar atrás da trava, como o meu. O R1-a cobre o build do `ifcopenshell`; o Qt e o OCCT não.
    - **Recomendação:** comparar também `"$ENV_DIR"/conda-meta/<pacote>-*.json` (o ambiente que vai no pacote) com a trava de desenvolvimento.
    - Informativo: o `python` difere de build entre as travas (`3.12.15 …_1` no desenvolvimento, `…_2` no runtime). A ABI é a mesma (3.12), e o R1-j passou; anotar no relatório do PR.
11. **`build_appimage.sh` não confere o RPATH do módulo que empacota** (BAIXA; recomendação). Quem montar à mão com um módulo antigo, de antes da T17a, só descobre no oráculo. Acrescentar a mesma conferência de `ci.yml:134-135` antes de copiar (linha 62).

### Item 4: `freeze_support()`
12. **Posição correta, mas a chamada não faz nada aqui; o comentário promete demais** (BAIXA; texto).
    - `app/openbim_app/main.py:12` (primeira linha de `main()`, antes de criar a aplicação) e `packaging/linux/AppRun:20` (antes do `run_module`) estão onde o cartão pede, e o oráculo confirma.
    - No Python 3.12, `freeze_support()` só age com `sys.platform == "win32"` e `sys.frozen`; no Linux, e no Windows com `python.exe` comum, não faz nada.
    - O que evita uma segunda janela no filho `spawn` é outra regra do `multiprocessing`: o filho não reexecuta módulos `*.__main__`, e o AppRun roda `openbim_app.__main__` (`spawn.py`, `_fixup_main_from_name`).
    - O comentário de `main.py:12` diz que a chamada impede a segunda janela; isso não é verdade. **Correção de texto:** "exigido pelo lote 7 (pacotes congelados); hoje não faz nada; o filho spawn não reexecuta openbim_app.__main__".
    - O oráculo prova o filho `spawn` com `ponte_no_pacote` como programa principal, não pelo AppRun real. Pela regra acima o risco é baixo; fica registrado.

### Item 5: licença do nanobind e do que vem junto
13. **Falta o aviso MIT do `tsl::robin_map`, compilado dentro do `_obimcore`** (MÉDIA, **obrigatória**; risco de licença).
    - O nanobind é ligado estaticamente: não há `libnanobind` no `NEEDED`. O núcleo dele (`nanobind/src/nb_internals.h`, `nb_combined.cpp`, `nb_enum.cpp`) usa `tsl::robin_map`, de `nanobind/ext/robin_map`, sob licença MIT (Copyright (c) 2017 Thibaut Goetghebuer-Planchon). A MIT exige o aviso em toda cópia.
    - Nada no pacote, no `THIRD_PARTY.md` ou em `packaging/` menciona o robin_map; procurei.
    - **Correção:**
      - criar `packaging/licenses-texts/robin-map-MIT.txt` com o aviso **literal** do cabeçalho de `nanobind/ext/robin_map/include/tsl/robin_map.h`, no ambiente `openbim`, sem baixar nada;
      - acrescentar a linha em `packaging/licenses-texts/LEIA-ME.md`;
      - pôr `robin-map-MIT` no laço de `build_appimage.sh:74`;
      - citar na nota de `build_appimage.sh:81` e na tabela de `THIRD_PARTY.md:14-17`.
    - A linha correspondente em `test_appimage.sh` é do agente de oráculo, não do implementador.
14. **O nanobind está certo** (OK).
    - O texto é idêntico ao `LICENSE` do pacote 3.1.0.
    - Entra no AppImage (o laço falha se faltar), está em `LEIA-ME.md` e tem linha em `THIRD_PARTY.md:17` e nota no `INVENTARIO.md`.
    - O instalador do Windows ainda não leva o módulo (é a T17b), então não precisa do texto agora; conferi que `packaging/windows/` não tem lista exata que o arquivo novo quebre.
15. **Outros códigos de terceiros que entram pelo cabeçalho** (BAIXA; recomendação). O `ifcgeom/taxonomy.h` puxa o Eigen (MPL-2.0) e o Boost (BSL-1.0), e o módulo usa cabeçalhos do Qt, do OCCT e do IfcOpenShell (LGPL).
    - O Eigen está no `INVENTARIO.md` (MPL-2.0, mantido), em `FONTES.md` e em `licenses/pacotes/eigen`; a fonte fica disponível.
    - A BSL não exige aviso em binário.
    - As LGPL estão cobertas pelos textos e pelo `LGPL-COMO-TROCAR.md`, que agora cita `app/obimcore`.
    - **Recomendação:** a nota de `build_appimage.sh:81` diz que o módulo leva Eigen e Boost (só cabeçalhos) e que usa IfcOpenShell, OCCT e Qt por biblioteca dinâmica.
16. **REUSE** (BAIXA, decisão do PO; não bloqueia). O `reuse lint` passa. Mas a regra `path = "**"` do `REUSE.toml` (agregada) etiqueta o texto BSD do nanobind como `AGPL-3.0-or-later` do projeto, o mesmo que já acontece com os textos LGPL/GPL guardados. Uma anotação própria para `packaging/licenses-texts/*` corrigiria a etiqueta; como mexe em licença, fica para o PO decidir.

### Item 6: arquivos do oráculo e escopo do implementador
17. **Oráculo intocado** (OK). `git diff origin/main...HEAD` está vazio para `packaging/linux/test_appimage_ponte.sh`, `packaging/linux/ponte_no_pacote.py` e `tests/`.
    - `packaging/linux/test_appimage.sh` mudou numa linha só (`:34`, acrescenta `licenses/nanobind-BSD-3-Clause.txt`), num commit separado (`f25f556`).
    - O git **não prova** que foi outro agente: todos os commits têm o mesmo autor. Fica pela palavra do líder.
18. **O implementador editou arquivos fora da lista permitida** (MÉDIA, processo). O cartão permite `packaging/`, `main.py` (só o freeze) e `ci.yml` (jobs nomeados), e diz "não editar … o código do módulo". O diff também mexe em `prototypes/s04/obimcore/CMakeLists.txt:75-80`, `prototypes/s04/obimcore/build.sh:33-61` e `THIRD_PARTY.md:14-17`.
    - As mudanças são necessárias e pequenas. Mas o `build.sh` e o `CMakeLists.txt` mudam o binário da ponte C++/Python que todos os testes do `linux` usam (área T3 pela matriz do CLAUDE.md).
    - **Pedido ao líder:** registrar em LOG.md e no cartão a ampliação dos arquivos permitidos. Este lote serve de revisão Opus dessas linhas.

### Item 7: o que o ensaio local não provou e o que o CI tem de mostrar
19. **O ensaio local** (o meu e, pelo pedido, o do implementador) **não provou:**
    - a imagem `.AppImage` real (squashfs gerada pelo appimagetool 1.9.1) nem a montagem por FUSE (caminho `/tmp/.mount_*`); rodei o oráculo na pasta;
    - a ordem do RPATH com o compilador do runner do CI (aqui o relativo veio primeiro; se vier ao contrário, a conferência falha alto, sem passar em silêncio);
    - o transporte pelo cache entre os jobs;
    - as bibliotecas do sistema do runner Ubuntu;
    - a poda do vtk/ffmpeg no CI e o tamanho final em MB;
    - o efeito no `instalador-windows`.
20. **A prova 6 do ADR-005 §7.1 fica só em parte** (MÉDIA; oráculo novo, outro agente; não bloqueia este código).
    - A prova 6 pede "tesselação … igual no ambiente de desenvolvimento e dentro do AppImage".
    - O R1-i no pacote compara o C++ com o Python **dentro do mesmo pacote**; não há referência guardada do desenvolvimento (`tests/test_s04_ponte.py:236-244` calcula a referência na hora).
    - **Recomendação:** cartão de oráculo pequeno. O job `linux` grava um resumo (contagem de triângulos, caixa e volume) de 1 IFC do corpus junto do cache do módulo, e o `appimage` compara dentro do pacote.
21. **Tamanho antes e depois** (BAIXA). `ci.yml:768` só aponta para "a última execução no main". O cartão (§Como 6, critério 4) pede os dois números no relatório do PR: o líder copia o tamanho do `main` e o deste PR.

## Correções pedidas para a nova revisão (curtas; o mesmo lote pode conferir)
1. Achado 13: aviso MIT do robin_map (texto literal + `LEIA-ME.md` + laço `build_appimage.sh:74` + nota `:81` + `THIRD_PARTY.md`). A linha em `test_appimage.sh` fica com o agente de oráculo.
2. Achados 1 a 3: em `build.sh`, trava contra referência dentro do trecho zerado, manter a permissão, trocar os `assert` por saída com erro e conferir `EI_DATA`.
3. Achado 12: corrigir o comentário de `main.py:12` (e o de `AppRun:18`).
4. Líder (achados 8 e 18): registrar em LOG.md e no cartão o cache no lugar do artefato e os arquivos fora da lista.
5. Líder (achado 7): merge só com o `appimage` verde, conferido à mão; levar ao PO a escolha de tornar o R1-j bloqueante.

Recomendações sem bloqueio: achados 4 (nota no dev-setup), 10, 11, 15, 16 (PO), 20 (cartão de oráculo) e 21.

## O que conferir no CI do pedido 152
- [ ] `linux` verde, com o passo "Entregar…" mostrando a conferência do RPATH (`$ORIGIN/../../env/lib`) e os dois arquivos do módulo listados.
- [ ] No fim do `linux`, o passo final do cache diz que gravou `obimcore-<run_id>`.
- [ ] `appimage`: o cache foi restaurado (sem "cache miss") e a montagem passou com a R-ABI.
- [ ] `test_appimage.sh` verde (autoteste, extração, FUSE com `OBIM_EXIGIR_FUSE=1`, troca de `.so`, licenças com `nanobind-BSD-3-Clause.txt` e, depois da correção, o arquivo do robin_map); tamanho ≤ 600 MB e o número comparado com o último `main`.
- [ ] R1-j verde: freeze `ok`, maps `ok`, filho spawn `valor=42 isolado=1` com caminhos dentro do pacote e **9 passed** (R1-a, R1-d ×4, R1-e ×3, R1-i), 0 pulados.
- [ ] `reuse lint` verde no `linux`.
- [ ] `windows` e `instalador-windows` verdes (o `ci.yml` e o `packaging/` mudaram, então o instalador roda neste PR).
- [ ] Merge só depois de tudo acima; sem merge automático neste PR.

## Resposta do líder (2026-10-17)
- **Achado 7 (R1-j não bloqueia o merge):** partiu de premissa errada. O job `appimage` é obrigatório na regra `proteger-main`, junto com `linux`, `windows` e `instalador-windows`. Logo o R1-j, que roda dentro do `appimage`, já bloqueia o merge; não há decisão a levar ao PO sobre isso.
- **Corrigidos no commit `8d580bf`:** achados 1, 2, 3, 4, 11, 12, 13 e 15.
- **Ficam como recomendação:** achados 10, 16, 20 e 21. O 16 é decisão do PO: o `REUSE.toml` segue como está.
- **Registrados no LOG.md:** achados 8 e 18 (cache no lugar do artefato; arquivos editados fora da lista do cartão).
