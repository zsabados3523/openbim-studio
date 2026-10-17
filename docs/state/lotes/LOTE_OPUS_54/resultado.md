# LOTE_OPUS_54: resultado

**REPROVADO.** São 2 correções obrigatórias e curtas: uma no oráculo (para o agente de oráculo) e uma no `ci.yml` (para o implementador). O pacote em si está limpo, e a prova 7 está certa. O resto está correto ou fica como recomendação sem bloqueio.

Revisor: Opus, independente (não escreveu nada desta tarefa). Revisado: ramo `s04-t17b-impl`, commits `a18e1d3` e `01a983c` (implementação), `3d388ba` e `de61e2a` (oráculo), diff contra `origin/main` (`dbee8ee`): 9 arquivos, +272 −60 = 332 linhas (abaixo de 400). CI: execução `39053772557` do pedido 155, no commit `de61e2a` (o mesmo do ramo), tentativa 1.

## Ensaio do revisor (sem tela, sem instalar nem baixar nada, sem tocar a worktree do implementador)
- `test_instalador_ponte.sh --autoteste`: `ok`. `bash -n` nos dois scripts: sem erro de sintaxe.
- **Simulação da regra nova de DLLs.** Importei `ponte_no_pacote_win.py` no Linux e troquei só `modulos_carregados()` por uma lista falsa. `OBIM_DEV_PREFIXES` ficou com o mesmo formato do CI (`|<pasta>`). Resultado:

  | Módulo de fora do pacote | Resultado |
  |---|---|
  | `MpOav.dll` (antivírus) | AVISO (certo) |
  | `liblzma.dll` vinda da instalação base do conda, que o pacote **não tem** | **só AVISO** |
  | `libgmp-10.dll` (dependência da geometria) vinda do conda base | **só AVISO** |
  | `zlib.dll` (mesmo nome de um arquivo do pacote) | reprova (certo) |
  | `QT6COR~1.DLL` (nome curto 8.3) | reprova, mas por sorte: casa com `^qt6`. `TKERNE~1.DLL` não casaria |
  | arquivo sob o prefixo de desenvolvimento | reprova (certo) |

- **Logs do CI**, lidos com `gh api`, só leitura:
  - `windows-viewport-a`: "Cache saved with key: obimcore-win-39053772557". O `.pyd` tem 3 302 400 bytes.
  - `instalador-windows`: "Cache hit for: obimcore-win-39053772557". Montagem com R-ABI e prova 7 (ligador 14.51; todas as cópias do runtime 14.51.36247.0). Instalador de **310 535 928 bytes**.
  - Oráculo: todas as etapas passaram.
    - Carregadas de `env\`: `VCRUNTIME140`, `VCRUNTIME140_1`, `MSVCP140`, `MSVCP140_1` e `MSVCP140_2`, todas 14.51.36247.0.
    - Filho spawn: `python.exe` e `pythonw.exe` com `valor=42 isolado=1`, Python e `obimcore` do pacote.
    - Filhos sem `-I` nas 3 ordens: código 0.
    - **9 passed**, 12 deselected.
    - Único AVISO: `C:\ProgramData\Microsoft\Windows Defender\Platform\4.18.26090.9-0\MpOav.dll`.
  - Depois disso, `test_installer.sh` ficou verde.
- **No passo R1-j do CI**, o bloco `env:` do log (17:56:57) **não tem `CONDA_PREFIX`**: o shell é sem login, de propósito (`ci.yml:636`). Só aparece `CONDA: C:\Users\runneradmin\miniconda3`. Então o `OBIM_DEV_PREFIXES` desta execução foi só `|D:\a` (ver achado 1).

## Achados por item do pedido

### Item 1: as duas mudanças do oráculo depois das falhas do CI
1. **A regra nova de "módulo de fora do pacote" afrouxou a prova além do necessário, e a parte que devia segurar o vazamento não está ligada no CI** (ALTA, **obrigatória**; correção do **agente de oráculo**, não do implementador).
   - **Onde:** `packaging/windows/ponte_no_pacote_win.py:157-177` (`auditar_dlls`) e `packaging/windows/test_instalador_ponte.sh:61-62` (montagem do `OBIM_DEV_PREFIXES`).
   - **Antes:** qualquer módulo de fora do pacote e de fora do Windows reprovava.
   - **Agora:** ele só reprova se (a) estiver sob o prefixo de desenvolvimento, (b) tiver o mesmo nome de um arquivo do pacote ou (c) for núcleo. O resto vira AVISO.
   - **A parte (a) não funciona no CI:**
     - `CONDA_PREFIX` não existe no passo, e `DEVP` sai de `dirname(dirname(OBIM_PYTEST_SITE))`.
     - Lá, `OBIM_PYTEST_SITE` é uma cópia solta (`D:\a\_temp\pytest_site`), não um `<prefixo>\Lib\site-packages`. A conta dá `D:\a` por coincidência.
     - Ficam de fora: `C:\Users\runneradmin\miniconda3` (base e `envs\nsis`), `C:\Program Files\Git\mingw64\bin` e todas as outras pastas do PATH sujo que o próprio oráculo mantém de propósito para o vazamento aparecer.
     - Isso está quebrado pela forma como foi montado, não por acaso desta execução.
   - **O caso que deixou de ser pego:** a poda tira uma dependência do pacote, e o Windows acha uma DLL com esse nome por busca de nome numa pasta do PATH (por exemplo, algo carregado depois com `LoadLibrary` sem caminho). A regra antiga reprovava. A nova só avisa, a não ser que o nome coincida com um arquivo do pacote ou com a lista de núcleos. Os casos `liblzma` e `libgmp` da simulação mostram isso.
   - **O que segue garantido:**
     - uma cópia só de cada núcleo: um núcleo de fora reprova por (b) ou (c), e `nucleos_do_modulo` conta TKernel e Qt6Core;
     - nada de `System32` para os núcleos (regra igual à antiga).
   - **O que não fica garantido:** "nenhum vazamento do ambiente de desenvolvimento". Isso só vale dentro de `D:\a`.
   - **O pacote desta execução está limpo:** o único AVISO foi o `MpOav.dll`. O defeito é da prova, não do instalador.
   - **Correção pedida** (escolher uma das duas formas e, se quiser, somar as duas):
     - a) decidir pela forma como a DLL entrou no processo, não pelo nome: reprova o módulo de fora cuja pasta seja uma entrada do PATH herdado pelo processo (o antivírus é injetado por caminho absoluto, de uma pasta que não está no PATH);
     - b) reprova o módulo de fora cujo nome apareça na tabela de importação de algum PE do pacote (é dependência do pacote que veio de fora).
   - **Também pedido:**
     - montar o `OBIM_DEV_PREFIXES` a partir de raízes de ambiente de verdade (`CONDA`, `CONDA_EXE`, `CONDA_PREFIX` e a raiz do conda base), e não da cópia do pytest;
     - imprimir o valor no log;
     - reprovar se ele vier vazio fora do modo simulado.
2. **Nome curto (8.3) e maiúsculas** (BAIXA; corrigir junto com o achado 1). `ponte_no_pacote_win.py:165`.
   - O `base` sai do caminho cru. Um núcleo listado como `TKERNE~1.DLL` escaparia de `tk[a-z0-9]+\.dll`; `QT6COR~1` só casou por sorte.
   - **Correção:** `base = os.path.basename(norm(c))`. O `realpath` expande o nome curto.
   - Maiúsculas e minúsculas já estão cobertas: `normcase` em `dentro`, `.lower()` nos nomes e `re.I`.
3. **A regra precisa ser provável sem Windows** (MÉDIA; corrigir junto com o achado 1).
   - **Correção:** a classificação vira uma função pura (lista de módulos, pasta do Windows, prefixos, PATH e nomes do pacote → erros e avisos), chamada por `auditar_dlls` e coberta pelo `autoteste` (`ponte_no_pacote_win.py:340`).
   - Casos mínimos: `MpOav` dá AVISO; pasta do PATH, prefixo de desenvolvimento, mesmo nome e núcleo por nome curto reprovam.
   - É o mesmo padrão que o lote 53 conferiu na trava do RPATH.
4. **A mudança `3d388ba` só apertou a prova** (OK). Detalhes:
   - `dlls` agora exige `EXIGIDAS_FIM` (OCCT da geometria) e usa a geometria e o `obimcore.malhas` antes de listar;
   - `nucleos_do_modulo` exige 1 cópia de TKernel e de Qt6Core em `bibliotecas_carregadas()`, todas do pacote;
   - a lista de núcleos ficou mais larga (`pyside`, `.*ifcgeom`, `.*obimcore`);
   - os filhos sem `-I` acrescentam erros;
   - o erro do filho `spawn` volta pela fila e reprova do mesmo jeito.
   - Nada foi afrouxado.
5. **A reorganização do `test_instalador_ponte.sh` em `de61e2a` não abre brecha** (OK).
   - Cada etapa roda em subshell, e `falha` sai só dela.
   - A etapa que reprova ou que depende de outra reprovada entra em `FALHOU` ou `NAOEXEC`, e o fim sai com código 1.
   - As etapas antigas continuam todas lá (estrutura, licenças, freeze, vcrt, dlls, dois spawn, pytest).
   - Os `AVISO` aparecem no log mesmo quando a etapa passa.

### Item 2: prova 7 (runtime do Visual C++ ≥ compilador do `.pyd`)
6. **A leitura está correta** (OK).
   - O ligador é lido em `pe+26` e `pe+27`: assinatura PE (4 bytes), cabeçalho COFF (20 bytes), `Magic` (2 bytes), depois `MajorLinkerVersion` e `MinorLinkerVersion`.
   - A versão do arquivo vem do `VS_FIXEDFILEINFO`, com a conferência de `StrucVersion` 0x00010000. O `autoteste` cobre uma assinatura falsa antes da verdadeira.
   - O CI mostra ligador 14.51 e runtime 14.51.36247.0, tanto nas cópias do pacote quanto nas carregadas, e as carregadas vêm de `env\`.
   - A prova falha fechado: quando o runner trouxer um compilador 14.52, ela reprova até a trava subir o `vc14_runtime`. É o comportamento certo; o líder deve saber que vai acontecer.
7. **A cópia de `vcruntime140*.dll` de `Library\bin` para `env\` é segura** (OK). `build_installer.sh:75-79`.
   - Só copia o que falta e nunca sobrescreve.
   - O arquivo vem do mesmo pacote `vc14_runtime` da trava. A redistribuição junto do programa é permitida, e `THIRD_PARTY.md` já tem a seção dos runtimes da Microsoft.
   - Neste CI a cópia não fez nada: `env\` já tinha os arquivos, iguais aos de `Library\bin` (mesmos tamanhos e versões no log).
8. **Limites** (BAIXA; recomendação).
   - A comparação para em maior.menor e ignora o número de build. Isso basta para a regra da Microsoft.
   - `vcomp140`, `concrt140` e `vccorlib140` (estão em `env\`) ficam fora de `RT` (`:100`) e da lista de núcleos (`:28`). Uma cópia deles vinda do `System32` passaria calada.
   - **Recomendação:** acrescentar os três a `RT` e a `NUCLEO` na mesma correção do achado 1.

### Item 3: `build_installer.sh`
9. **`OBIMCORE_DIR` obrigatório: certo** (OK). `:22-27`. Sem a variável, sem `__init__.py` ou com um número de `.pyd` diferente de 1, a montagem para com mensagem clara, antes de apagar ou copiar qualquer coisa.
10. **R-ABI: certa, e agora também confere o ambiente real** (OK). `:28-36`.
    - Compara os builds de `ifcopenshell`, `occt`, `pyside6` e `qt6-main` nas duas travas win-64 (hoje iguais: `ifcopenshell-0.9.0-py312h062a554_1`, `occt-8.0.1-all_h6eddace_201`, `pyside6-6.11.2-py312hdb84042_1`, `qt6-main-6.11.2-pl5321hfcac499_0`).
    - Exige o `conda-meta/<build>.json` no ambiente de runtime. Isso fecha, no Windows, o achado 10 do lote 52.
    - O ambiente de desenvolvimento do `windows-viewport-a` nasce da trava (`.github/actions/ambiente-windows/action.yml:36-38`).
11. **Licenças: certas** (OK).
    - `nanobind-BSD-3-Clause` e `tsl-robin-map-MIT` entram no laço que falha se faltar algum (`:93`); o oráculo confere com `cmp`.
    - A nota do `INVENTARIO.md` (`:103`) diz a verdade: nanobind e robin_map compilados dentro do módulo; Eigen e Boost só como cabeçalhos; IfcOpenShell, OCCT e Qt por bibliotecas dinâmicas.
    - O Eigen (MPL-2.0) está na trava de runtime, então entra no inventário e em `licenses/pacotes/`.
12. **Trava de 600 MB: certa e coerente** (OK; registrar). `ci.yml:632`. É o mesmo teste que o `appimage` já tem (`ci.yml:828`) e cumpre o ADR-005 §9 ("não cortar em silêncio"). Não muda a meta, só faz o CI parar acima dela. Por ser um extra do implementador, o líder registra no LOG.

### Item 4: `ci.yml`
13. **Transporte por cache: certo** (OK). `ci.yml:319-338` e `:578-586`.
    - O cache grava no fim do `windows-viewport-a`, só se o job passou ("Cache saved with key: obimcore-win-39053772557").
    - A cópia é feita logo depois de o `tests/test_s04_ponte.py` passar, então vai ao pacote o binário testado. O passo confere que há exatamente um `.pyd`.
    - A chave vale por execução, sem `restore-keys`. O `fail-on-cache-miss` faz o instalador falhar se o módulo não vier.
    - Numa reexecução do mesmo commit, o instalador usa o módulo da 1ª tentativa, que é o mesmo.
14. **`needs` e job pulado: sem brecha** (OK).
    - Se o `windows-viewport-a` falhar ou for cancelado, o `instalador-windows` é pulado, e o GitHub conta como aprovada uma verificação obrigatória pulada.
    - Mas o agregador `windows` (`ci.yml:537-548`) inclui o `windows-viewport-a` e exige `success` de todos. O `windows` também é obrigatório (regra `proteger-main`: `linux`, `windows`, `appimage`, `instalador-windows`). Então não há merge sem o módulo compilado e testado.
    - Com `detecta` falso, o job continua passando sem montar nada, como antes.
15. **O `detecta` não liga o instalador quando muda o próprio módulo** (MÉDIA, **obrigatória**; brecha do CI; correção do **implementador**, dentro dos arquivos permitidos). `ci.yml:573`.
    - A expressão só olha `packaging/`, `app/`, as travas, `pyproject`, `ci.yml`, três scripts e `LICENSES/`.
    - Agora o instalador **leva** o `obimcore` e roda o R1-j, que depende de:
      - `prototypes/s04/obimcore/` (código, `build.sh`, `CMakeLists.txt`);
      - `tests/test_s04_ponte.py` e os auxiliares que ele importa;
      - `.github/actions/ambiente-windows/` (ambiente onde o módulo é compilado).
    - Um pedido que mexa só nesses caminhos entra no `main` sem o R1-j do instalador; o erro só aparece no `push` ao `main`.
    - O `appimage` não tem `detecta`, então a brecha é só do Windows. O cartão ("Armadilhas conhecidas") manda conferir justamente isso.
    - **Correção:** acrescentar `prototypes/s04/obimcore/`, `tests/` (no mínimo `test_s04_ponte.py`, `s04_aux*` e `gerar_modelo_grande*`) e `.github/actions/` à expressão.
16. **Limite de 75 min: razoável** (OK). O job levou 13 min 28 s nesta execução. O passo R1-j tem limite próprio de 30 min, e o oráculo, de 1 500 s.

### Item 5: `freeze_support()` e filho spawn
17. **Comentário honesto e posição certa** (OK). `OpenBIM-Studio.pyw:9` e `:58-61`.
    - `import multiprocessing` está no topo, e a chamada vem dentro do `if __name__ == "__main__"`, antes de `iniciar()`.
    - O comentário diz a verdade: a chamada não faz nada com o `python.exe` comum, e o que evita a segunda janela é o guarda `__main__` (o filho roda o arquivo como `__mp_main__`). Mesma lição do achado 12 do lote 52.
18. **Filho spawn provado com `python.exe` e `pythonw.exe`** (OK), ambos em `-I`, com `valor=42 isolado=1` e Python e `obimcore` do pacote.
    - Ressalva igual à do Linux (lote 52, achado 12): o programa principal do filho é o `ponte_no_pacote_win.py`, não o `.pyw` real. O risco é baixo pelo guarda `__main__`.

### Item 6: quem mexeu no oráculo e arquivos fora da lista
19. **O implementador não tocou no oráculo** (OK).
    - `a18e1d3` e `01a983c` não mexem em `ponte_no_pacote_win.py`, `test_instalador_ponte.sh` nem `tests/`.
    - `3d388ba` e `de61e2a` só mexem nesses dois arquivos de oráculo.
    - Como nos lotes 52 e 53, o git **não prova** quem foi cada agente: o autor e o coautor Sonnet são os mesmos. Fica pela palavra do líder.
    - A mudança `de61e2a` está anunciada no próprio cabeçalho do oráculo (`test_instalador_ponte.sh:18-22`), como pedia o processo.
20. **Arquivos fora da lista do cartão** (BAIXA; processo). `THIRD_PARTY.md` e `docs/dev-setup.md` (só texto) não estão na lista do cartão. A aceitação da linha 180 do LOG era do T17a. O líder registra de novo, para o T17b.
    - As mudanças no `windows-viewport-a` (`ci.yml:319-338`) cabem em "envio do artefato nos jobs de compilação".

### Item 7: o que o CI não prova e o que vem dos lotes 52 e 53
21. **O que o CI deste pedido não prova** (informativo; não bloqueia):
    - **Prova 6 do ADR-005 §7.1:** o R1-i compara o C++ com o Python **dentro do mesmo pacote**. Não há referência de tesselação vinda do desenvolvimento.
      - O R1-j rodou no pacote **já podado**, então a poda não quebrou R1-a/d/e/i.
      - Não está provado que a poda não muda a geometria em relação ao desenvolvimento.
    - **Pasta com espaço e acento:** o R1-j só rodou numa pasta sem espaço (`D:\a\_temp\OpenBIM-ponte`). O caso de pasta com acento e espaço, e a pasta padrão `...\Programs\OpenBIM Studio`, só foi testado pelo `test_installer.sh` (`--selftest`), sem o R1-j.
      - **Recomendação:** rodar o R1-j também na pasta com acento e espaço, numa tarefa futura de oráculo.
    - **Máquina real** (Windows 10 e 11 sem o Visual C++ instalado, usuário comum, nome de usuário com acento): fica para o roteiro de aceitação (T14). O runner tem o runtime no `System32`; o oráculo prova que ele **não** foi usado, mas não prova uma máquina sem ele.
    - **SmartScreen:** sem assinatura, ele avisa; esperado até a v0.3. O CI não testa.
22. **Herdados dos lotes 52 e 53** (sem bloqueio):
    - lote 52, achado 10 (R-ABI contra o ambiente real): **fechado no Windows** por este pedido; no Linux continua recomendação;
    - lote 52, achado 16 (etiqueta REUSE dos textos de licença): decisão do PO, segue como está;
    - lote 52, achado 20: cartão de oráculo para a prova 6 (ver o achado 21);
    - lote 53, achado 13: a versão do robin_map no `THIRD_PARTY.md` já diz "versão embutida no nanobind 3.1.0" no `main`; fechado;
    - lote 53, achado 14: o segundo titular do nanobind (Hudson River Trading, `nb_datetime.cpp`) também falta na nota do instalador (`build_installer.sh:103`); segue para a tarefa T0 de texto;
    - lote 53, achados 10 e 11: comentários antigos do `ci.yml` e o `CLAUDE.md` com a lista antiga de jobs obrigatórios; seguem abertos. O `ci.yml:18` já foi corrigido no `main`.
23. **Tamanho antes e depois** (BAIXA; o cartão pede no relatório do pedido, critério 4). A descrição do pedido 155 não traz os números. Os números:
    - antes: **309 664 248 bytes** (`main` `dbee8ee`, execução 39048216714);
    - depois: **310 535 928 bytes** (+871 680 bytes; o módulo soma 3 302 865 bytes sem compressão);
    - meta: ≤ 600 MB.

## Correções pedidas para a nova revisão (o mesmo lote pode conferir)
1. **Agente de oráculo** (achados 1, 2 e 3; e 8 se quiser):
   - regra de módulo de fora pela forma de entrada (pasta no PATH herdado e/ou nome importado por um PE do pacote);
   - `OBIM_DEV_PREFIXES` a partir de raízes de ambiente de verdade, impresso no log e obrigatório fora do modo simulado;
   - `basename(norm(c))`;
   - classificação como função pura coberta pelo `autoteste`;
   - de preferência, `vcomp140`, `concrt140` e `vccorlib140` em `RT` e `NUCLEO`.
   - O `MpOav.dll` tem de continuar passando como AVISO.
2. **Implementador** (achado 15): pôr `prototypes/s04/obimcore/`, `tests/` e `.github/actions/` no `detecta` do `instalador-windows`.
3. **Novo CI verde no mesmo pedido**, com o log mostrando:
   - o valor de `OBIM_DEV_PREFIXES`;
   - o `MpOav.dll` como único AVISO;
   - o `autoteste` com os casos novos.

## O que o líder deve registrar
- **LOG.md:** "Lote opus 54 | REPROVADO | T17b: regra nova do oráculo para DLL de fora do pacote afrouxou além do necessário e o prefixo de desenvolvimento não está ligado no CI (só `D:\a`); `detecta` não liga o instalador quando mudam `prototypes/s04/obimcore`, `tests/` ou `.github/actions`. Prova 7, R-ABI (agora com o ambiente real), licenças, cache, `needs` e `freeze_support` aprovados. Pacote desta execução limpo (só `MpOav.dll` como aviso)."
- **LOG.md:**
  - a trava de 600 MB no `instalador-windows` (extra do implementador, mesma regra do `appimage`);
  - `THIRD_PARTY.md` e `docs/dev-setup.md` editados fora da lista do cartão, agora no T17b;
  - as duas mudanças do oráculo depois de falha do CI (`3d388ba` só apertou; `de61e2a` vai ser refeita pelo achado 1).
- **Relatório do pedido 155:** os tamanhos do achado 23.
- **Cartão T17:** a prova 7 vai falhar de propósito quando o runner trouxer um compilador mais novo que o `vc14_runtime` da trava. A saída é subir a trava, nunca afrouxar.
- **Merge:** só depois de uma nova revisão aprovar o conteúdo exato dos commits novos e de os 4 jobs obrigatórios estarem verdes.
- **Recomendações para depois** (sem bloqueio): achado 8 (se não entrar agora), achado 21 (R1-j em pasta com acento e espaço; cartão da prova 6) e achado 22 (tarefa T0 de texto: segundo titular do nanobind, comentários antigos do `ci.yml`, `CLAUDE.md` com 4 jobs obrigatórios, levar ao PO).

---
## Resposta do líder (2026-10-17)
Lote reprovou o T17b. Correções feitas no pedido 155 (conferidas no lote 55): a regra de módulo de fora do pacote passou a decidir pela forma de entrada (PATH, prefixo de desenvolvimento, mesmo nome de arquivo do pacote, importado pelo pacote, núcleo, nome curto 8.3), com `MpOav.dll` só como aviso; prefixo de desenvolvimento ligado no CI; resolução do nome curto 8.3; `vcomp140`, `concrt140` e `vccorlib140` na lista; `detecta` do instalador passou a ligar também para `prototypes/s04/obimcore/`, `tests/` e `.github/actions/`.
