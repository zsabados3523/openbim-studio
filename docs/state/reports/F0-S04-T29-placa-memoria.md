<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
# F0-S04-T29: medição oficial de memória do arquivo PESADO na placa real (relatório)
Autor: sonnet (subagente de medição). Data: 2026-10-21. **Só medição**: nenhum arquivo de produto, teste, meta ou `v2/` foi alterado; nada commitado. Só números; nada do arquivo do PO (318 MB, apelido PESADO) foi copiado ou lido além dos números do JSON.

## Como foi medido
- Checkout: `main` em `016287e` (T29 bloco 250 com reinício; T29e mesclado). Padrão do produto: 8 fios, **bloco 250** (passado explicitamente com `--bloco 250`, porque o padrão do `medir.py` é 1000; o do `CarregadorMalhas` é 250).
- Comando por rodada: `medir.py "$PESADO" --bloco 250` (sem `xvfb-run`, sem `XV`), `DISPLAY=:0`, `QT_QPA_PLATFORM=xcb`, sob `flock ~/openbim-medicao/medicao.lock`, `timeout 600`, uma rodada por vez.
- Máquina: i5-12600KF, 16 núcleos lógicos, 23 GiB, sessão x11. Placa: **NVIDIA GeForce RTX 3070**, driver 580.178.04; `glxinfo -B`: `OpenGL renderer string: NVIDIA GeForce RTX 3070/PCIe/SSE2`. Memória disponível antes e depois de cada rodada: 17 a 18 GB (nunca perto de 3 GB). O JSON desta versão do `medir.py` **não tem** o campo `desenho.software`; a prova da placa é só o `glxinfo` (a "segunda prova" do passo 0, de dentro do `Cena`, não foi rodada: o roteiro dela usa o fluxo A do S04, fora desta tarefa).
- O RustDesk estava ativo (serviço e servidor rodando; ele não foi tocado). Ele pode afetar a medida de quadros (`fps`, `atraso_*`): a captura de tela remota usa CPU e GPU. A medida de memória é do processo e não depende dele de forma relevante.
- Saídas (fora do repositório): `/home/rafael/openbim-medicao/2026-10-21-placa-memoria/` (`sondas_PESADO_{1,2,3}.json` = última linha; `maquina.txt`, `free_*`, `rc_*`).

## Resultados por repetição
| campo | rod. 1 | rod. 2 | rod. 3 | mediana | meta | passou? (1/2/3) |
|---|---|---|---|---|---|---|
| `abrir_s` (s) | 51,67 | 51,61 | 50,84 | **51,61** | ≤ 60 | sim / sim / sim |
| `pico_pai_mb` | 937 | 948 | 952 | 948 | n/a | n/a |
| `pico_filho_mb` | 4.926 | 4.926 | 4.909 | 4.926 | n/a | n/a |
| `pico_somado_mb` (conta A = pai + maior filho) | 5.863 | 5.874 | 5.861 | **5.863** | < 6.000 | sim / sim / sim |
| `soma_amostrada_max_mb` (conta B, 10 amostras/s) | 5.371 | 5.421 | 5.379 | 5.379 | informativo | n/a |
| `atraso_max_ms` | 46,0 | 45,2 | 62,7 | 46,0 | < 200 | sim / sim / sim |
| `atraso_p95_ms` | 0,2 | 0,2 | 0,2 | 0,2 | < 200 | sim / sim / sim |
| `fps` | 56,8 | 60,4 | 60,4 | 60,4 | n/a | n/a |
| `simplificadas.quantidade` | 0 | 0 | 0 | 0 | n/a | n/a |
| `sem_malha` | 6 | 6 | 6 | 6 | n/a | n/a |
| `filhos_sobrando` | 0 | 0 | 0 | 0 | 0 | sim / sim / sim |

Outros campos iguais nas 3: 14.804 peças com malha, 8.595.714 triângulos, 132 lotes, `estado` "concluido", 8 fios, bloco 250; `primeiro_lote_visivel_s` 5,39 na rodada 1 (as outras não foram extraídas); `bytes_gpu_mb` 708 (rodada 1).

**Campo da meta de memória:** a meta "< 6.000 MB" vale pelo `pico_somado_mb` (conta A, pico do pai + maior pico entre os filhos), pela **pior** das três aberturas (T24 §1 e §2: "conta A = a da meta"; regra do lote 57; roteiro S04 passo 7: "pico somado < 6,0 GB"). Pior das três aqui: **5.874 MB (passou)**. A `soma_amostrada_max_mb` é a conta B (informativa, sempre menor).

## Reinícios (bloco, fonte, tempo perdido)
**Não medido.** O `medir.py` do `main` não grava `reinicios` nem `registro_reinicio` no JSON (os campos existem no resumo do carregador, mas a sonda não os imprime), e o stderr não foi lido por regra de privacidade (o `grep -c reinic` nos `.err` deu 0 nas três). Indício indireto, não prova: `pico_filho_mb` 4.926 contra 4.920 do filho novo da variante 1-B bloco 250 do T24 (`rb250`); mas nenhum campo confirma que o reinício disparou. Para obter bloco/fonte/tempo perdido, é preciso que a sonda imprima `resumo.reinicios` e `resumo.registro_reinicio` (mudança de código de sonda; não feita aqui).

## O que NÃO prova
- Não prova que o reinício planejado do T29 disparou nem em qual bloco (ver acima).
- Não prova o desenho pela RTX 3070 de dentro do Qt do ambiente (Mesa do conda): só o `glxinfo` do sistema mostra a placa; `desenho.software` não está no JSON desta versão.
- Não vale para outra máquina, outro arquivo (só PESADO; SIMPLES e DETALHADO não foram medidos), Windows ou RAM menor.
- `fps` e `atraso_*` podem ter sido afetados pelo RustDesk e pelo uso remoto; 3 rodadas não dão estatística (variação de memória entre rodadas: 13 MB; variação entre dias já chegou a 100 MB no T24).
- Não prova saída igual (contagens iguais nas 3, mas sem comparação byte a byte) nem uso confortável pelo usuário.
