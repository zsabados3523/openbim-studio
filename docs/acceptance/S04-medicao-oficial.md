<!--
SPDX-License-Identifier: AGPL-3.0-or-later
-->
# S04: roteiro da medição oficial (tela real do Linux, com os 3 IFC do PO)

Fontes: `LOTE_OPUS_9/resultado.md` §2 e §2.3, `LOTE_OPUS_21`, `reports/F0-S04-threads.md` ("Como reproduzir"), cartão T20. Uma sessão só, de 30 a 60 min, com a máquina parada. **Ensaio completo feito em 2026-10-17** (tela virtual `xvfb-run`, desenho por software, nunca na tela real; pasta `~/openbim-medicao/ensaio/`): todos os comandos abaixo rodaram, com as correções que o ensaio mostrou. Os tempos "ensaio" são de software (llvmpipe): na placa real os passos gráficos (1, 2, 4, 5, 6, 7) tendem a ser iguais ou menores; os passos sem janela (gerar a base, juiz) não mudam. Os 3 IFC aparecem só por apelido: SIMPLES (38 MB), DETALHADO (222 MB), PESADO (318 MB).

## Para o PO
1. Combine o horário comigo: a máquina fica parada por até 1 hora, sem você usar.
2. Antes: feche navegador, e-mail, chat, jogos, downloads e atualizações; deixe só o Claude Code aberto. Notebook: na tomada.
3. Desligue a proteção de tela, o bloqueio de tela e o modo de descanso (se a tela apagar, a medição perde o valor).
4. Durante: não toque no mouse nem no teclado. Janelas abrem, giram e fecham sozinhas; o ventilador acelerar é normal.
5. Deixe pelo menos 20 GB livres no disco. Se a máquina parecer travada, espere 5 minutos antes de me avisar no chat.
6. As duas peças que faltavam no ambiente (zlib e libxml2; pendência A7) já foram instaladas com o seu ok de 17/10; nada mais mudou no ambiente. Nada a fazer aqui.
7. Seus arquivos não saem da máquina: resultados ficam na pasta `~/openbim-medicao/DATA` (fora do projeto); só números entram no relatório. Apagar essa pasta depois é decisão sua.

## Para o líder
### O que cada comando mede
| Passo | Comando (resumo) | Responde | Saída |
|---|---|---|---|
| A | `tests/test_s04_metas.py roteiro_ifc` (fluxo A, roteiro R) | ADR-001: M2, M2b, M3, M4, M5 | `A/…/medicao.json` + IFC do passo 7 |
| B | `fluxo_b_janela --base --roteiro --saida` (fluxo B em C++) | ADR-001: o mesmo, no C++ puro | `B/oficial/medicao.json` + IFC |
| J | `prototypes/s04/medir_s04.py --a --b --estrito --json` (o juiz) | veredito M2 a M5 (p95), M6 (razão A÷B; pesa se folga < 2), saída igual | `oficial_juiz.json` |
| T | `fluxo_a/lote.py` (formas 1 e 2; M5, M5b) | ADR-004: thread do comando Python longo | `A/threads.json` |
| C | `fluxo_a/conferencias.py` | ADR-004: `exec()` solta o bloqueio?, causa do F7, desenho com bloqueio preso, forma 3 | `A/conferencias.json` |
| P | `lote.main_pesada` (parede de 150 aberturas) | ADR-004: portão de metade de `malha_ms` | `A/pesada.json` |
| O | `viewport_qrhi/medir.py` (S03: carregador em processos, `CuboViewport`) | ADR-004 abertura e memória; T20 (< 6,0 GB, abertura ≤ 60 s) | `sondas/abrir_*.json` |
| U | `medir.py` com `OBIM_TESTE_PECA_LENTA` (opcional) | custo do modo uma-peça (lote 21, rec. 3) | `sondas/uma_peca.json` |
| X | `roteiro_ifc` nos IFC do PO (opcional) | informativo: como M2 a M5 escalam | `X/…` |

O modo uma-peça (um iterador por peça) só roda se uma peça passar de `limite_peca_s` (20 s) ou o filho cair. `medir.py` não tem opção para isso nem imprime o modo: se `simplificadas.quantidade` for 0, o relatório diz "não disparou"; o passo U o força pelo gancho de teste (`processo_malhas.py`, cabeçalho).

### Antes do horário do PO (sem placa real)
- Ambiente (**feito**): faltavam `include/libxml2` e `zlib.h`. Instalados só `zlib=1.3.2=h25fd6f3_3` e `libxml2-devel=2.15.4=h7df9aa5_1` (as versões da trava, já no cache local; `conda install --no-deps --offline`). Conferido por `conda list` antes e depois: a única diferença são essas duas linhas novas (315 pacotes antes, 317 depois).
- Compilar (**feito**, Release, Ninja; refazer só se o código mudar), com `conda activate openbim`, em `"$REPO"`: `CLEAN=1 bash prototypes/s04/obimcore/build.sh ~/openbim-medicao/build` (8,3 s) e `CLEAN=1 bash prototypes/s04/fluxo_b/build.sh ~/openbim-medicao/build` (10,8 s); saem `obimcore/`, `fluxo_b_paredes*.so` e `fluxo_b_janela` em `~/openbim-medicao/build`. Se o repositório mudar de commit antes do dia, recompilar.
- **Ensaio** (**feito**: passos 0 a 8 e 9 sob `xvfb-run -a`, com `MED=~/openbim-medicao/ensaio`, pasta separada: números de software não podem se misturar com os oficiais). Os números do ensaio ficam em `ensaio/` e **não** entram no relatório oficial.
- Execução pela ferramenta Bash: variáveis não persistem entre chamadas, então guardar o bloco abaixo em `~/openbim-medicao/env.sh` e começar toda chamada com `source ~/openbim-medicao/env.sh`; nenhum passo passou de 3 min no ensaio (o 7 inteiro, 9 rodadas, levou 4 min 40 s), então o limite de 10 min da ferramenta só importa para o passo 7 e o 9: rodar o passo 7 com `run_in_background`. O caminho do repositório tem espaços: aspas em tudo.
```
REPO="${REPO:-/home/rafael/00 - PROJETOS/openbim-studio}"   # raiz do repositório (ajustar se for outra worktree)
export MED="${MED:-$HOME/openbim-medicao/AAAA-MM-DD}"; mkdir -p "$MED"/{tmp,A,B,X,sondas}   # data fixa do dia
PY="$HOME/miniforge3/envs/openbim/bin/python"; export PYTHONPATH="$HOME/openbim-medicao/build" TMPDIR="$MED/tmp"
export QT_QPA_PLATFORM=xcb LC_ALL=C OBIM_LIMITE=7200; unset LIBGL_ALWAYS_SOFTWARE QSG_RHI_PREFER_SOFTWARE_RENDERER
REF="$REPO/../openbim-studio-referencia/ifc"; mapfile -t F < <(ls -S "$REF"/*-ifc4.ifc); [ ${#F[@]} -eq 3 ] || echo "ERRO: esperava 3 arquivos"
PESADO="${F[0]}"; DETALHADO="${F[1]}"; SIMPLES="${F[2]}"   # só estes 3, listados pelo PO; nunca abrir outro
XV=("${XV[@]}")   # tela: ensaio = XV=(xvfb-run -a -s "-screen 0 1280x1024x24") definido ANTES do source; oficial (tela real) = vazio
```
O modelo pronto já está em `~/openbim-medicao/env.sh`. Uso no ensaio: `export MED=~/openbim-medicao/ensaio; XV=(xvfb-run -a -s "-screen 0 1280x1024x24"); source ~/openbim-medicao/env.sh`. Uso oficial: `export MED=~/openbim-medicao/AAAA-MM-DD; source ~/openbim-medicao/env.sh` (sem `XV`). **Todo comando gráfico abaixo leva `"${XV[@]}"` na frente**: no oficial a lista é vazia e o comando roda na tela real; no ensaio vira `xvfb-run`. **Cuidado:** os nomes dos arquivos do PO não valem como esquema (ver "Achados do ensaio"): o SIMPLES (o de 38 MB) é IFC2X3 por dentro, apesar de o nome terminar em `ifc4`.
`TMPDIR` evita cópias em `/tmp`; `OBIM_LIMITE` (padrão 600) mataria `roteiro_ifc` aos 580 s. Rodar pelo pytest NÃO serve: o `caso()` força `xvfb-run` e `LIBGL_ALWAYS_SOFTWARE=1`. Todo comando sobre IFC do PO redireciona stdout **e** stderr para `$MED` (o stderr do carregador cita nomes de peças).

### Sessão (na ordem; tempos = ensaio em software, entre parênteses; `cd "$REPO"` salvo onde dito; `source ~/openbim-medicao/env.sh` no começo de cada chamada)
Total no ensaio: passos 0 a 6 = 3 min 20 s; com o 7 = 8 min; com 8 e `--threads 4` = 11 min. Na placa real o desenho pode mudar os passos 1, 2, 4, 5, 6 e 7 (não muda a base nem o juiz); a janela de 30 a 60 min fica como margem (primeira rodada fria, disco, máquina quente).
0. (1 s) Placa e máquina, **sem** `XV` no oficial: `{ lscpu | grep -E "Model name|^CPU\(s\)"; free -g; nvidia-smi --query-gpu=name,driver_version --format=csv; "${XV[@]}" glxinfo -B | grep -E "renderer|version"; echo $XDG_SESSION_TYPE; } > "$MED/maquina.txt"`. Sem a linha da placa real (não llvmpipe) a rodada não vale. Segunda prova, de dentro do `Cena`: em `"$REPO/prototypes/s04/fluxo_a"`, `"${XV[@]}" "$PY" -c "import lote, tempfile, pathlib; lote._caminhos(); import ifcopenshell, fluxo_a; f=fluxo_a.FluxoA(None, janela=True, saida=pathlib.Path(tempfile.mkdtemp())); print(f.cena.info(), f.cena.desenho_por_software()); f.fechar()" | tee -a "$MED/maquina.txt"`. Esperado: RTX 3070 e `False`. No ensaio deu `Mesa llvmpipe ... True` (software, como deveria). **Atenção:** o Qt do ambiente `openbim` usa o Mesa do conda (26.2.4), diferente do Mesa do sistema (25.2.8, do `glxinfo`); só a segunda prova mostra se a placa NVIDIA é de fato usada. Se vier `True`, parar (não medir) e levar ao PO.
1. (25 s; antes estimado 5 a 10 min) Fluxo A, base oficial: `"$PY" scripts/gerar_modelo_grande.py "$MED/base3000.ifc" --paredes 3000` (2 s) e `/usr/bin/time -v "${XV[@]}" "$PY" tests/test_s04_metas.py roteiro_ifc "$MED/base3000.ifc" > "$MED/A/oficial.out" 2> "$MED/A/oficial.time"` (23 s; pico de memória 0,4 GB). Conferir a linha `RESULTADO` (sai código 0 mesmo com `"erro"` dentro); `DA=$(sed -n 's/^RESULTADO //p' "$MED/A/oficial.out" | jq -er '.arquivo_medicao|sub("/medicao.json$";"")')` (o `-e` falha se `arquivo_medicao` for nulo). Guardar `DA` em arquivo (`echo "$DA" > "$MED/DA.txt"`), porque a variável não persiste entre chamadas.
2. (18 s) Fluxo B, **o mesmo** `base3000.ifc`: `"${XV[@]}" "$HOME/openbim-medicao/build/fluxo_b_janela" --base "$MED/base3000.ifc" --roteiro "$REPO/prototypes/s04/fluxo_a/roteiro_r.json" --saida "$MED/B/oficial" > "$MED/B/oficial.out" 2> "$MED/B/oficial.err"` (última linha `MEDICAO …`; só IFC4).
3. (27 s) Juiz estrito: `DA=$(cat "$MED/DA.txt"); OBIM_S04_ESTRITO=1 "$PY" prototypes/s04/medir_s04.py --a "$DA" --b "$MED/B/oficial" --json "$MED/oficial_juiz.json" > "$MED/juiz.out" 2>&1` (igual a `--estrito`; exige `base.produtos` ≥ 3000 e igual em A e B). Código 0 aprova, 1 reprova, 2 entrada inválida. Linhas (M7, 0 s): `"$PY" prototypes/s04/medir_s04.py --linhas --raiz prototypes/s04 --json "$MED/linhas.json"` (ensaio: obimcore 1259, fluxo A 1013, fluxo B 1278).
4. (68 s) Forma 1 x 2, em `"$REPO/prototypes/s04/fluxo_a"`: `"${XV[@]}" "$PY" lote.py "$MED/A/threads.json" --base 3000 --quantidade 1000 --rodadas 3 > "$MED/A/threads.out" 2>&1`.
5. (39 s) Mesma pasta: `"${XV[@]}" "$PY" conferencias.py "$MED/A/conferencias.json" --base 3000 --quantidade 1000 --rodadas 3 > "$MED/A/conferencias.out" 2>&1`.
6. (18 s) Mesma pasta: `"${XV[@]}" "$PY" -c "import ifcopenshell, lote; lote.main_pesada(['$MED/A/pesada.json','--base','300','--aberturas','150','--rodadas','3'])" > "$MED/A/pesada.out" 2>&1` (base 300, a do relatório `F0-S04-threads.md`).
7. (4 min 40 s no total; antes estimado 15 a 25 min) Abertura, 3 repetições (T20 pede a mediana), do menor ao maior; padrão = 8 fios, bloco 1.000. Parar o arquivo se uma rodada passar de 10 min ou a memória livre ficar abaixo de 3 GB (`free -g`). Em `"$REPO/prototypes/viewport_qrhi"`:
`for a in SIMPLES DETALHADO PESADO; do for i in 1 2 3; do "${XV[@]}" "$PY" medir.py "${!a}" > "$MED/sondas/abrir_${a}_$i.json" 2> "$MED/sondas/abrir_${a}_$i.err"; done; done`
Tempos de parede por rodada no ensaio: SIMPLES 6 s, DETALHADO 33 s, PESADO 54 s. **O JSON é a última linha do arquivo** (as 5 primeiras são avisos de localidade do Qt, que saem no stdout): ler sempre com `tail -n 1 arquivo | jq ...`.
Opcional, 1 vez no PESADO: `--threads 4` (60 s; mapa memória x tempo; é o que a T20 discute): mesma linha com `--threads 4` e saída `abrir_PESADO_t4.json`.
8. (opcional; 130 s) Uma-peça: `G=$("$PY" -c "import ifcopenshell,sys; print(ifcopenshell.open(sys.argv[1]).by_type('IfcWall')[0].GlobalId)" "$DETALHADO" 2>/dev/null)` (a variável **nunca** é impressa) e `OBIM_TESTE_PECA_LENTA="$G=40" "${XV[@]}" "$PY" medir.py "$DETALHADO" > "$MED/sondas/uma_peca.json" 2> "$MED/sondas/uma_peca.err"` (`G` e o comando têm de ficar na mesma chamada). No ensaio disparou (`simplificadas.quantidade` = 1) e `carga_s` foi 123 s contra 26 s sem o gancho; descontando a espera de 40 s do gancho e os 20 s do limite, o custo do modo é da ordem de 35 s (método não validado, o líder registra a conta).
9. (opcional, só com tempo) `roteiro_ifc` completo nos IFC do PO, sempre com saída em `"$MED/X/"` (nunca as do passo 1) e `timeout`: `/usr/bin/time -v timeout 3600 "${XV[@]}" "$PY" tests/test_s04_metas.py roteiro_ifc "$DETALHADO" > "$MED/X/detalhado.out" 2> "$MED/X/detalhado.time"`; depois o juiz só com `--a` (sem `--b` e sem `--estrito`): `"$PY" prototypes/s04/medir_s04.py --a "$DX" --json "$MED/X/juiz_detalhado.json"`, com `DX` tirado do `RESULTADO` como no passo 1. **O SIMPLES não serve** (é IFC2X3 por dentro; ver "Achados"). **No ensaio o DETALHADO (1 min 30 s, 4,2 GB) e o PESADO (3 min, 6,6 GB) terminaram com `TimeoutError` (nenhum quadro em 10 s) no meio do roteiro, sem `medicao.json`.** Na placa real pode passar; se o `RESULTADO` vier com `"erro"`, registrar só a classe do erro e seguir. Ler o erro sem expor nomes: `sed -n 's/^RESULTADO //p' arq | jq -r .erro | tail -n 2`.
10. Comparabilidade: o relatório das threads usou base 300 e software; aqui são base 3000 e placa real (duas mudanças juntas). Se houver 3 min, repetir o passo 4 com `--base 300` em `"$MED/A/threads300.json"` (no ensaio, base 3000 levou 68 s; a 300 deve levar menos).

### Achados do ensaio (para o líder e para o PO)
1. **Nomes dos arquivos enganam.** Pelo cabeçalho (FILE_SCHEMA, só essa linha): o arquivo SIMPLES (38 MB, nome terminado em `ifc4`) é **IFC2X3**; o arquivo de 25 MB do mesmo conjunto (nome terminado em `ifc2x3`, fora da lista do PO) é **IFC4**. Por isso o `roteiro_ifc` no SIMPLES falha de imediato (`mudar_comprimento só funciona em IFC4`). A abertura (passo 7) não é afetada. Opções ao PO: liberar o arquivo de 25 MB (na verdade IFC4) como SIMPLES do passo 9, ou deixar o passo 9 só com o DETALHADO.
2. **Meta de memória na abertura (software, 3 rodadas, medianas):** SIMPLES abre em 1,9 s e 1,06 GB somados; DETALHADO 26,3 s e 5,09 GB; **PESADO 47,9 s e 6,90 GB (acima de 6,0 GB)**; com `--threads 4` o PESADO deu 54,4 s e 6,57 GB (ainda acima). A memória vem do carregador (filho, 5,8 GB), não da placa: é provável que a rodada oficial também passe de 6,0 GB no PESADO. Atraso máximo do laço de eventos: SIMPLES 31 ms, DETALHADO 438 ms, PESADO 550 ms (meta < 200 ms; no software o desenho pesa; a placa real é que decide). `simplificadas.quantidade` = 0 e `filhos_sobrando` = 0 em todas.
3. **Base sintética de 3000 (software): tudo aprovado.** Juiz estrito: `aprovado: true`, `saida_igual.ok: true`; M2 p95 46 ms, M2b p95 63 ms, M3 p95 1,1 ms, M4 2,17 s, M5 maior intervalo 18 ms (parado 30 ms); M6: razão A÷B de M2 0,96, M2b 0,99, M3 0,30, M4 13,5; folga mínima 3,16, `pesa: false`. São números de software; só valem como ensaio.
4. Passo 4 (forma 1 x 2, software, base 3000): forma 1 tem M5b mediana de 228 a 920 ms (cresce a cada rodada) e `pulso_maior` até 1,6 s; forma 2 tem M5b mediana de 14 ms mas p95 de 565 a 636 ms, `pulso_maior` de 698 a 765 ms (maior fatia: `spatial.assign_container`). Passo 6: `malha_ms` 212 ms, 3012 triângulos, M5b máximo da forma 1 entre 2 e 8 ms e da forma 2 entre 203 e 224 ms (portão: `malha_ms/2` = 106 ms; a forma 2 passa de 106 ms no software).
5. Nenhum IFC do PO foi copiado para o repositório; `git status --short` do repositório principal só mostra o `AGENTS.md` que já estava; `find "$REPO" -name '*.ifc' -newer "$MED/maquina.txt"` vazio.

### Parada
Se M2 a M5 reprovarem em estrito, ou a abertura passar de 60 s ou 6,0 GB: não repetir até passar; registrar o número e levar ao PO com opções (lote 9 §3; CLAUDE.md).

### Números que vão ao relatório
- Passo 3: `jq '{aprovado,erros,metas,m6}' "$MED/oficial_juiz.json"` e `.saida_igual.ok`. Placa: nome e `False`.
- Passo 4: `jq '{formas:(.formas|map_values(map(.resumo))), controle:(.controle|map_values(map(.resumo)))}'` (M5: maior intervalo e janelas; M5b: mediana, p95 e máximo; `pulso_maior_ms`); a decisão forma 1 ou 2 é do PO (T19).
- Passo 6: `jq '.pesada|{malha_ms,triangulos}, (.formas|map_values(map(.resumo.M5b.max_ms)))' "$MED/A/pesada.json"` contra o portão `malha_ms/2`.
- Passo 7: `tail -n 1 arquivo | jq 'del(.simplificadas.lista)'` (o JSON é a última linha): `abrir_s`, `pico_pai_mb`, `pico_filho_mb`, `pico_somado_mb`, `soma_amostrada_max_mb`, `atraso_max_ms`, `atraso_p95_ms`, `fps`, `simplificadas.quantidade`, `sem_malha`, `filhos_sobrando`; mediana das 3 por arquivo. Metas S03: abrir ≤ 60 s, pico somado < 6,0 GB, atraso < 200 ms.
- Registrar ao lado das metas originais (D8) a máquina (`maquina.txt`: processador, memória total, placa e driver).

### Privacidade (repositório público e serviço online)
- Tudo vai para `$MED`, fora do repositório. Não usar `--png` (imagem do modelo); não rodar pytest com os IFC do PO; não copiar IFC.
- O líder só lê números extraídos com `jq`. Não ler `*.err`, `simplificadas.lista` nem o `medicao.json` bruto de um IFC do PO (têm GlobalIds, nomes de peças e caminho); no relatório só apelidos e tamanhos.
- No fim: `git -C "$REPO" status --short` vazio e `find "$REPO" -name '*.ifc' -newer "$MED/maquina.txt"` vazio. Apagar `$MED` só com ordem do PO.

## Lacunas
1. **Ambiente:** resolvido (17/10, com o ok do PO): `zlib` e `libxml2-devel` instalados nas versões da trava; build do `obimcore` e do `fluxo_b_janela` funciona.
2. **Prova da placa no JSON** (opcional, não implementado): `medicao.json` e `threads.json` só gravam `rhi: "gl"`. Acrescentar `"desenho": {"info": cena.info(), "software": cena.desenho_por_software()}` leva umas 3 linhas (`fluxo_a.py` em `executar_roteiro` e `lote.py` em `main`; talvez ajuste do oráculo da T11, outro agente). Serviria ao número "a rodada usou a RTX 3070" dentro do próprio resultado, em vez de só no `maquina.txt`. Até lá vale o passo 0 (segunda prova).
3. **`lote.py` e `conferencias.py` com IFC externo** (opcional, não necessário para o oficial): `--ifc ARQ`, umas 4 linhas em cada (`add_argument` e usar o arquivo no lugar de `gerar_modelo_grande.gerar`). Serviria a "M5/M5b e conferências num modelo real do PO". `main_pesada` não serve (cria a própria parede). Risco: `preparar` abre tudo dentro do processo, sem isolamento por peça.
4. **Fluxo A sem linha de comando própria:** o passo 1 usa o `__main__` de um arquivo de teste. Uma CLI espelhando a do B seriam umas 10 linhas em `fluxo_a.py`; não é necessária.
5. **Custo do modo uma-peça:** sem opção em `medir.py` (`limite_peca_s` fixo em 20 s) nem campo de modo no JSON; medir de verdade pede umas 5 linhas (um `--limite-peca` e a lista de modos no resumo) ou fica o passo 8.
6. **Limite de 10 s por quadro no `roteiro_ifc` (novo):** `_quadro(..., limite_ms=10000)` em `fluxo_a.py` (linha 420) estoura no DETALHADO e no PESADO (ensaio em software, quadro de sequência 13 e 39). Tornar o limite configurável por variável de ambiente (`OBIM_QUADRO_MS`) leva umas 2 linhas e serviria ao número M2b/M3 em modelo real, caso a placa real também estoure; só decidir depois do passo 9 na máquina real.
7. **Saída do `medir.py` suja o stdout (novo, sem código obrigatório):** o aviso de localidade do Qt (`LC_ALL=C`) sai no stdout antes do JSON; contornado com `tail -n 1`. Trocar para `LC_ALL=C.UTF-8` evitaria o aviso mas muda o ambiente de teste; decisão do líder.
8. **Nomes dos IFC do PO (novo):** o nome do SIMPLES diz IFC4 e o conteúdo é IFC2X3; o de 25 MB faz o inverso (cabeçalho). O SIMPLES não roda o `roteiro_ifc`; ver "Achados" 1.
9. **Windows:** fora desta sessão (sem placa real; T28 e S10).
