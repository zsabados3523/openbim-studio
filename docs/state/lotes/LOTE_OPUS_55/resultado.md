# LOTE_OPUS_55: resultado

**REPROVADO.** Há 2 correções obrigatórias, e nenhuma muda a lógica já revisada.
- O pedido 155 tem **441 linhas** e passa do limite de 400. A saída é dividir em dois pedidos, como foi feito no T17a.
- O CI não roda o autoteste do oráculo, e o lote 54 tinha pedido isso.

O conteúdo técnico dos itens a) a d) está correto. A regra nova do oráculo resistiu a todas as tentativas de sabotagem. O `detecta` cobre o que o R1-j usa. O pacote desta execução está limpo.

Revisor: Opus, independente (não escreveu nada desta tarefa). O que revisei:
- ramo `s04-t17b-impl`, HEAD `7d91aac`, base `dbee8ee` (igual a `origin/main`);
- commits novos `5a7c500` (implementador) e `7d91aac` (oráculo);
- CI: execução `39058071304`, no commit `7d91aac`. Os jobs `linux`, `windows`, `appimage` e `instalador-windows` estão verdes. O `macos` está vermelho, como no `main`.

## Ensaio do revisor
Rodei tudo sem tela, sem instalar nem baixar nada e sem tocar a worktree do implementador.
- `test_instalador_ponte.sh --autoteste` (Python do ambiente `openbim`): `ok`. `bash -n` não acusou erro de sintaxe.
- **Sabotagem da `classificar`.** Importei o oráculo no Linux e troquei `os.path` pelo `ntpath`, para valer a regra do Windows (maiúsculas e minúsculas, barra invertida). Rodei 25 casos sem resolver nomes curtos, e os 25 deram o resultado esperado:
  - `MpOAV.dll` (antivírus, em `C:\ProgramData\...`): só AVISO.
  - **Reprovam:**
    - DLL de nome diferente numa pasta do PATH (`...\Git\mingw64\bin\liblzma-5.dll`);
    - a mesma pasta do PATH escrita toda em maiúsculas;
    - pasta do PATH com barra no fim;
    - qualquer coisa sob `C:\Users\runneradmin\miniconda3` (também com maiúsculas trocadas);
    - DLL de nome diferente do que o pacote tem, mas importada por um arquivo do pacote (`LIBLZMA.DLL`, `TBB12.dll`);
    - DLL com o mesmo nome de uma do pacote (`ZLIB.DLL`, `QWINDOWS.DLL`);
    - nome curto 8.3 que não se resolveu (`TKERNE~1.DLL`, `TKBREP~1.DLL`);
    - núcleo (`Qt6Gui.dll`);
    - `vcomp140`, `vccorlib140` e `concrt140`, vindas de fora ou do `System32`;
    - `MSVCP140_1` e `qt6core` vindas do `System32`;
    - cópia na pasta de montagem `inst-out\pacote` (reprova por ter o mesmo nome).
  - **Passam:** `kernel32.dll` e `amsi.dll` do Windows, e `Qt6Core.dll` do próprio pacote.
  - Uma pasta de nome parecido com a do pacote (`OpenBIM-ponte-falso`) não conta como "dentro" do pacote: só AVISO, como deve ser.
- **Leitor da tabela de importação** (`importados`): testei em 16 executáveis Windows de verdade, de 32 e de 64 bits (`distlib` e `setuptools`). Todos saíram certos, por exemplo `kernel32`, `shlwapi`, `user32`, `api-ms-win-crt-*` e `vcruntime140`.
- **`detecta`:** testei a expressão do CI contra 12 caminhos.
  - Dão `false`: só documentação, `README.md` e `prototypes/s04/fluxo_a/`.
  - Dão `true`: `prototypes/s04/obimcore/`, `tests/`, `.github/actions/`, `ci.yml`, `packaging/`, `app/`, a trava e `LICENSES/`.
- **Log do `instalador-windows`** (job 117474966446, lido com `gh api`, só leitura):
  - `instalador=true (o PR mexe no empacotamento)`.
  - O cache do módulo foi encontrado (`obimcore-win-39058071304`).
  - O conda foi instalado em `C:\Users\runneradmin\miniconda3` (a pasta `hostedtoolcache` guarda só o arquivo de instalação).
  - Linha impressa: `prefixos do ambiente de DESENVOLVIMENTO ...: C:\Users\runneradmin\miniconda3`. É a raiz real dos ambientes `openbim` e `nsis`; não é mais `D:\a` por coincidência.
  - `pastas do PATH herdado fora do pacote e do Windows: 66`.
  - **Único AVISO** nas duas auditorias (etapa `dlls` e dentro do pytest): `...\Windows Defender\Platform\4.18.26090.9-0\MpOAV.dll`.
  - Prova 7: as 22 cópias do runtime (agora contando também `vcomp140`, `vccorlib140` e `concrt140`) estão em 14.51.36247.0, com ligador 14.51. As carregadas vêm de `env\`.
  - Os dois filhos spawn deram `valor=42 isolado=1`. O pytest deu **9 passed**, 12 deselected. Depois disso o `test_installer.sh` ficou verde.
  - Instalador: **310 600 792 bytes**.

## Achados

### a) Achados 1, 2, 3 e 8 do lote 54
1. **Achado 1 corrigido de verdade** (OK).
   - O módulo de fora agora reprova pela forma como entrou no processo:
     - de uma pasta do PATH herdado (busca pelo nome);
     - pelo nome que algum arquivo do pacote importa;
     - além do prefixo de desenvolvimento, do mesmo nome e do núcleo, que já existiam.
   - `OBIM_DEV_PREFIXES` sai de raízes de ambiente de verdade: a pasta de cada candidato que tem `conda-meta`. Os candidatos são `CONDA_PREFIX`, `CONDA`, `CONDA_EXE`, o `python` e o `conda` do PATH e `OBIM_PYTEST_SITE`.
   - O valor sai impresso no log.
   - A etapa reprova se o valor vier vazio ou só com a letra do disco, e o Python também reprova se vier vazio.
   - Os casos `liblzma` e `libgmp`, que o lote 54 viu passar só com aviso, agora reprovam pelas duas formas.
2. **Achado 2 corrigido** (OK).
   - O nome base agora sai de `basename(norm(c))`, depois de `GetLongPathNameW`.
   - Nome 8.3 que não se resolve reprova.
3. **Achado 3 corrigido** (OK).
   - `classificar` é uma função pura.
   - O `autoteste` cobre os casos pedidos: antivírus, PATH, prefixo, mesmo nome, importada, núcleo, 8.3 resolvido e não resolvido, Windows, `vcomp140` e `concrt140`.
   - Ele também cobre uma tabela de importação fabricada e um arquivo que não é PE.
4. **Achado 8 corrigido** (OK). `vcomp140`, `concrt140` e `vccorlib140` entraram em `RT` e em `NUCLEO`, e o log mostra as três na prova 7.
5. **O CI não roda o `autoteste` do oráculo** (MÉDIA, **obrigatória**; correção do **implementador** no `ci.yml`).
   - A correção pedida no lote 54 dizia: "Novo CI verde ... com o log mostrando ... o autoteste com os casos novos".
   - Nenhum job chama `test_instalador_ponte.sh --autoteste`. No CI, a `classificar` só é exercida pela execução real, que tem um único caso (o `MpOav`).
   - Se alguém estragar a regra no futuro, nada acusa.
   - **Correção:** 1 linha no job `linux`, que é obrigatório e tem Python: `bash packaging/windows/test_instalador_ponte.sh --autoteste`. Conferir `ok` no log.
   - Informativo: o par do Linux (`test_appimage_ponte.sh`) também não roda o próprio autoteste no CI. Fica para uma tarefa à parte; não entra neste pedido.
6. **Ordem das regras na `classificar`** (BAIXA; recomendação ao agente de oráculo, numa tarefa futura).
   - A conferência do nome 8.3 vem depois do ramo "do Windows".
   - Se o `GetLongPathNameW` falhar, `C:\Windows\System32\TKERNE~1.DLL` passa como OK: está no meu ensaio, e `tk[a-z0-9]+\.dll` não casa com `~`. Na prática o Windows resolve esses nomes, por isso não bloqueia.
   - **Correção:** pôr a conferência de `~\d` antes do ramo do Windows.
7. **Lacunas pequenas da regra nova** (BAIXA; recomendação para depois).
   - **(i) Pasta atual de trabalho.** Ela entra na busca de nome do Windows, antes do PATH, e não está na lista de pastas que reprovam. No CI é a cópia do repositório, sem DLL na raiz. Antes ela era coberta por acaso pelo `D:\a`.
   - **(ii) A `importados` falha calada.** Se não conseguir ler um arquivo do pacote, devolve uma lista vazia sem avisar. Ela também não lê as importações atrasadas (*delay-load*). A regra do PATH cobre o caso principal.
   - **Recomendação:** pôr `os.getcwd()` na lista de pastas que reprovam e imprimir quantos arquivos do pacote foram lidos.
8. **O cabeçalho do `test_instalador_ponte.sh` (linhas 18 a 22, "MUDANCA DO ORACULO") ficou velho** (BAIXA; texto, agente de oráculo).
   - Ainda descreve só as regras (a) prefixo, (b) mesmo nome e (c) núcleo, sem o PATH, a importação e o 8.3.
   - O código e a docstring da `classificar` estão certos.

### b) Achado 15 (`detecta`) e o caminho "não monta"
9. **Corrigido** (OK). `ci.yml:573` agora inclui `prototypes/s04/obimcore/`, `tests/` e `.github/(workflows/ci.yml|actions/)`.
   - O que o R1-j usa está coberto:
     - `test_s04_ponte.py` e `s04_aux.py`;
     - o `scripts/gerar_modelo_grande.py`, que só a R1-h importa e que fica fora do `-k` do R1-j.
   - "Na dúvida, ligado" continua valendo: evento `push` ou falha ao buscar a base dão `true`.
10. **O caminho "não monta" continua passando** (OK).
    - Todos os passos do job depois do `detecta` têm `if: steps.detecta.outputs.instalador == 'true'`, menos o "Tempo total" (`always()`), que já era assim.
    - Pedido só de documentação dá `false`, e o job passa sem montar nada.
    - Custo informativo: como `tests/` inteiro liga o instalador, quase todo pedido com teste vai gastar cerca de 14 min nesse job. Não bloqueia.

### c) Achados 20 e 23 no cartão
11. **Registrados** (OK). As duas notas estão no cartão T17 (`5a7c500`). Há três correções pequenas de texto (BAIXA; o líder corrige junto):
    - **(i)** A nota do achado 20 cita `packaging/licenses-texts/`, mas o diff do T17b não mexe nessa pasta. Os arquivos fora da lista são só `THIRD_PARTY.md` e `docs/dev-setup.md`.
    - **(ii)** O "depois" de 310 535 928 bytes é da execução anterior (`39053772557`). No commit que vai ao `main` (execução `39058071304`), o log mostra **310 600 792 bytes**: +936 544 sobre os 309 664 248 de antes, ainda bem abaixo de 600 MB.
      - Entre as duas execuções o instalador variou 64 864 bytes sem mudança no pacote. A montagem não sai igual byte a byte. É informativo.
    - **(iii)** A descrição do pedido 155 ainda não traz os tamanhos. O critério 4 do cartão pede os números lá.

### d) Quem mexeu no oráculo
12. **Separação respeitada** (OK).
    - `7d91aac` mexe só em `ponte_no_pacote_win.py` e `test_instalador_ponte.sh`.
    - `5a7c500` mexe só no `ci.yml` e no cartão.
    - Como nos lotes anteriores, o git não prova quem foi cada agente (autor e coautor são os mesmos). Fica pela palavra do líder.

### e) Tamanho do diff
13. **O T17b passa de 400 linhas** (ALTA, **obrigatória**; correção do **líder**, sem mexer no código).
    - **A conta.** Usei a mesma medida do lote 54 (pedido 155 contra `origin/main`): `git diff origin/main...HEAD` = **374 inseridas + 67 apagadas = 441 linhas**, em 10 arquivos. Sem `docs/`, ainda são 435.
    - **De onde vêm as linhas:**

      | Parte | Commits | Linhas |
      |---|---|---|
      | Implementação | `a18e1d3`, `01a983c`, `5a7c500` | 137 |
      | Oráculo (as três mudanças depois das falhas do CI) | `3d388ba`, `de61e2a`, `7d91aac` | 304 |

      O pedido do oráculo que já entrou (154) tinha 399.
    - **Por que não há saída por exceção.** Nenhuma das isenções vale aqui: não há texto de licença nem arquivo gerado. Os precedentes de exceção no LOG (434, 520 e 650 linhas) são de antes da regra do PO de 2026-10-15 ("sem exceções, dividir").
    - **Correção:** dividir, como no T17a (pedidos 151 e 152):
      1. Um pedido só do oráculo, com o conteúdo de `ponte_no_pacote_win.py` e `test_instalador_ponte.sh` como está em `7d91aac`: 304 linhas.
      2. O pedido 155 fica só com a implementação: 137 linhas, mais a linha do achado 5.
      3. O do oráculo entra primeiro. O 155 roda o CI completo depois disso.
    - **Proposta ao líder:** o conteúdo revisado e correto é o desses arquivos em `7d91aac`. Depois de dividir, o líder pode conferir com `git diff 7d91aac <novo HEAD> -- packaging/ .github/ docs/ THIRD_PARTY.md`.
      - Esse diff deve vir vazio, menos a linha nova do autoteste no `ci.yml` e as notas de texto do achado 11.
      - Se vier assim, o conteúdo exato é o que este lote leu.
      - Quem decide se precisa de nova releitura do Opus é o líder.

## Correções pedidas
1. **Líder** (achado 13): dividir em dois pedidos, o do oráculo (304 linhas) primeiro e o da implementação (137 linhas, mais o achado 5) depois. O conteúdo não muda.
2. **Implementador** (achado 5): pôr `bash packaging/windows/test_instalador_ponte.sh --autoteste` no job `linux` e mostrar `ok` no log.
3. **Líder** (achado 11): três ajustes de texto:
   - tirar `packaging/licenses-texts/` da nota do cartão;
   - pôr 310 600 792 bytes (execução `39058071304`) como o "depois", ou o número da execução final do pedido;
   - pôr os tamanhos na descrição do pedido.
4. **Novo CI verde** nos 4 jobs obrigatórios, com:
   - o `autoteste` `ok`;
   - o prefixo `C:\Users\runneradmin\miniconda3` impresso;
   - o `MpOAV.dll` como único AVISO.

## O que o líder deve registrar
- **LOG.md:** "Lote opus 55 | REPROVADO | T17b, releitura: achados 1, 2, 3, 8 e 15 do lote 54 corrigidos de verdade.
  - Classificação de DLL de fora agora reprova pela forma de entrada (pasta do PATH herdado, nome importado pelo pacote) e pelo prefixo real `C:\Users\runneradmin\miniconda3`, impresso no CI. O único aviso é `MpOAV.dll`.
  - `detecta` cobre `prototypes/s04/obimcore`, `tests/` e `.github/actions`.
  - Reprovado por forma: pedido 155 com 441 linhas (> 400). Dividir em oráculo (304) e implementação (137), como no T17a.
  - O CI não roda o autoteste do oráculo; vai 1 linha no job `linux`.
  - Conteúdo revisado: arquivos em `7d91aac`."
- **LOG.md:** a mudança do oráculo `7d91aac`, depois de falha do CI, foi revista e aprovada neste lote. Ela substitui a regra de `de61e2a`.
- **Cartão T17:** os 3 ajustes de texto do achado 11. Fica de pé a nota do lote 54 sobre a prova 7: ela vai falhar de propósito quando o runner trouxer um compilador mais novo que a trava. A saída é subir a trava.
- **Recomendações para depois** (sem bloqueio), numa tarefa de oráculo:
  - achado 6: 8.3 antes do ramo do Windows;
  - achado 7: pasta atual de trabalho na lista e contagem de arquivos lidos pela `importados`;
  - achado 8: cabeçalho do `test_instalador_ponte.sh`;
  - autoteste do `test_appimage_ponte.sh` no CI.
  - Continuam abertos os itens 21 e 22 do lote 54.
- **Merge:** só depois da divisão, do autoteste no CI e dos 4 jobs obrigatórios verdes, com o conteúdo conferido igual ao de `7d91aac`, como proposto no achado 13.

---
## Resposta do líder (2026-10-17)
Lote reprovou por processo, sem mexer na lógica: pedido de 441 linhas (limite 400) e autoteste do oráculo fora do CI. Feito: separação em dois pedidos, 156 (só o teste do instalador, mesclado no `main`) e 155 (só a implementação); autoteste do oráculo no job `linux`. Releitura no lote 56.
