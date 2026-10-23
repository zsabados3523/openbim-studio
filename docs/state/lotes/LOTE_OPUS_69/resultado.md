<!--
SPDX-License-Identifier: AGPL-3.0-or-later
-->
# LOTE_OPUS_69: resultado (especificação e oráculo de V1, V1b e P1; opus, esforço médio, 2026-10-21)
Autor: Opus. Não escrevi o ADR-004 de 2026-10-21 (lote 68) nem `lote.py`, `fluxo_a.py` ou `ponte_malha.cpp`. Li o contexto fechado do pedido (ADR-004 e ADR-001 do ramo `s04-adr-001-004`; `F0-S04-threads.md` (só a parte citada no ADR); `lote.py`, `CONTRATO.md`, `fluxo_a.py`; `ponte.cpp` e `ponte_malha.cpp`; lote 9 §1.4 e §2.3; testes do T15 e do T30d3; README dos cartões; `acceptance/S04-medicao-oficial.md` e `PO.md` só para os apelidos dos arquivos). Não li `~/openbim-medicao` nem IFC. Nada de commit, push ou merge. Construí o `obimcore` só no rascunho da sessão, para rodar os oráculos.

## 1. Entregas (no worktree, sem commit)
| Arquivo | Linhas | O quê |
|---|---|---|
| `docs/state/arquivo/F0-S04/cartoes/F0-S04-V1.md` | 43 | Validar a forma mista (T3) |
| `docs/state/arquivo/F0-S04/cartoes/F0-S04-V1b.md` | 27 | `--ifc` e a maior fatia num IFC real (T2) |
| `docs/state/arquivo/F0-S04/cartoes/F0-S04-P1.md` | 35 | Porta única do modelo (T3) |
| `tests/test_s04_v1_mista_oraculo.py` | 393 | V1, regras 2 a 5 do §5.1, erro, comando composto; ensaio sem obimcore e caso real |
| `tests/test_s04_v1_veredito_oraculo.py` | 166 | V1, critério 1 (intactos por sha256), `veredito_mista` contra conta independente, `main_mista` |
| `tests/test_s04_p1_trava_oraculo.py` | 301 | P1, a trava de leitura e escrita, empréstimo, porta do C++ (Python puro) e regra 9 |
| `tests/test_s04_p1_obimcore_oraculo.py` | 155 | P1, o `obimcore.malhas` pela sessão |
| este arquivo | — | — |
Os oráculos passam de 400 linhas juntos. **Sugestão de PRs (cada um ≤ 400):** A = os três cartões e este arquivo; B = `test_s04_v1_mista_oraculo.py`; C = `test_s04_v1_veredito_oraculo.py` + `test_s04_p1_obimcore_oraculo.py` (321); D = `test_s04_p1_trava_oraculo.py`. As linhas do CI entram com a implementação de cada cartão (como no T15g).

## 2. O que cada cartão pede
- **V1 (T3)**: forma nova "mista" em `lote.py`: comando na thread da janela em fatias (como a forma 2) e cada malha inteira numa thread "lote-geometria", com a janela no laço de eventos até o resultado chegar por sinal enfileirado; `main_mista` (partes "lote" e "pesada") e `veredito_mista` (função pura com os critérios 3 a 6). Formas 1 e 2, `fluxo_a.py`, `main` e o `__main__` intactos (sha256). Medição em três máquinas; aprovado só com `veredito.ok` nas duas partes no Linux local e na placa (o Windows informa, não decide); reprovado = pergunta 4 volta ao PO com 4A e 4B lado a lado.
- **V1b (T2)**: `--ifc` e `--apelido` em `main_mista`; mediana da maior fatia da forma 2 e da mista num IFC real; acima de 1 s = a parte "comandos em fatias" reprova e vai ao PO.
- **P1 (T3)**: `app/openbim_app/sessao_modelo.py` (trava de leitura e escrita com preferência do escritor, reentrada proibida na hora, empréstimo da leitura pelo escritor parado) e `obimcore.malhas` aceitando a sessão e conferindo a trava antes de soltar o interpretador. Não liga a porta em ninguém (o fluxo A é régua; I1/RG-05 ligam).

## 3. Ordem sugerida
1. PRs A a D do oráculo (marcadores `@AINDA_NAO`; hoje 4 testes passam e 28 ficam em falha esperada).
2. **V1** (sonnet) e, em seguida ou junto (máximo 2 implementadores), **P1** (sonnet): arquivos diferentes, sem dependência entre si.
3. Autor do oráculo tira os marcadores de cada um; lote Opus revisa V1 e P1 juntos (mesmo módulo: threads e trava), 2 itens.
4. Medição do V1: Linux local (tela virtual) e Windows (passo temporário do CI); depois **uma** sessão na placa.
5. **V1b**, só depois do V1 no `main` e da liberação do arquivo.
6. I1 só com o V1 aprovado e o P1 no `main`.

## 4. Onde roda
| O quê | Tela virtual (`xvfb-run -a`) | Placa real | Windows |
|---|---|---|---|
| Oráculos do V1 (as duas partes) | sim (CI e local) | não | CI |
| Oráculos do P1 | não precisa de tela (Python puro e `obimcore` sem janela) | não | CI |
| Medição do V1 | Linux local, partes "lote" (base 300) e "pesada" | **uma sessão** (parte "lote" com base 3.000, "pesada" com base 300; cerca de 20 min, máquina parada; liberada pelo PO, horário com ele) | passo temporário do CI, informativo |
| V1b | sim, na máquina do PO (a fatia é processador, não placa) | não | não |

## 5. Verificação feita nesta sessão (Linux, `xvfb-run -a`, `obimcore` construído do `main` 0de3e74 no rascunho)
- Hoje, com `OBIM_S04_V1_OBRIGATORIO=1` e `OBIM_S04_P1_OBRIGATORIO=1`: V1 2 passaram e 12 em falha esperada; P1 2 passaram e 16 em falha esperada; **0 pulos**. Os que passam: critério 1 (intactos), ambiente, regra 9, caminho do arquivo no `obimcore`.
- **Correção de referência** (minha, temporária, já desfeita): V1 com `--runxfail` 14 de 14, **3 de 3** execuções (46 s cada); P1 18 de 18, **3 de 3**; `tests/test_s04_ponte.py` 21 de 21 com o C++ mudado; hashes da T15g e sentinelas do T15b verdes com a referência. Tamanho da referência: 142 linhas em `lote.py`; 133 em `sessao_modelo.py` e ~12 em `ponte_malha.cpp`.
- **Mutantes**, cada um reprovado pelo oráculo: V1 "objeto Qt na thread de geometria" (regra 5), "espera com `join` em vez do laço" (regras 2 e 4 e o caso real), "malha na thread da janela" (5 testes); P1 "sem preferência do escritor", "reentrada que espera", "porta frouxa (qualquer thread com escritor ativo)", "empréstimo que não espera o C++" e, no C++, "sem `_obimcore_sair` no erro".
- `git status`: só os 7 arquivos acima; `lote.py`, `ponte_malha.cpp` e `app/` intactos.
- Não verificado: Windows (o CI dirá); 10 ou mais execuções seguidas (o critério 1 dos cartões pede 3 depois dos marcadores).

## 6. Leituras do §5.1
Técnicas (o comando não existia ou a frase não diz o conjunto):
1. Critério 6 ("o lote de 1.000 com uma parede de 150 aberturas no meio"): nenhum comando do fluxo A faz isso; virou o comando composto lote 500 + `mover` da parede + lote 500, contra lote 500 + lote 500, só na mista.
2. Critério 4 ("nenhuma rodada da mista surda por mais de 1 s"): toda rodada da mista, das duas partes.
Resolvidas pelo texto aprovado (não reabrir no lote de revisão):
3. Critério 5 ("M5 inalterado: janela de 1 s com 20 quadros ou mais, maior intervalo < 200 ms"): vale a interseção, que nenhuma leitura chama de frouxa: o texto do ADR em TODA rodada e a régua do T15b no limite dela (100 ms em tela virtual; 200 ms com `OBIM_S04_ESTRITO=1`, gravado por `main_mista` em `estrito`). Está no oráculo (`_m5` e os casos sintéticos 4 e 5).
4. Critério 7 ("Windows informativo, não bloqueia"): o V1 aprova ou reprova pelo Linux local e pela placa; o Windows vai ao relatório ao lado, com toda reprovação dita.

Custo no CI (não bloqueia, mas o líder deve saber antes de pôr as linhas): os quatro oráculos levam ~47 s por job no Linux local (V1 ~46 s, P1 ~2 s); no Windows, provavelmente o dobro, com a cadeia já em 17 min contra a meta de 10 (T23).

As correções de referência (`ref_mista.py`, `sessao_modelo_ref.py` e o trecho de `ponte_malha.cpp`) ficaram só no rascunho desta sessão, como evidência para o lote Opus de revisão. **Não vão ao implementador** (oráculo e implementação em agentes diferentes).

## 7. Perguntas ao PO (só o que é dele)
1. **V1b: qual arquivo seu?** Recomendação: só o de 25 MB (por dentro é IFC4; o SIMPLES de 38 MB é IFC2X3 por dentro e o comando de lote pode não rodar igual), em tela virtual. Ele já foi liberado em 17/10 para o ensaio da medição; o líder só confirma se vale também para este cartão.
2. **Horário da sessão na placa para o V1** (uma só, cerca de 20 min, máquina parada). A sessão já está liberada; falta o horário.

## 8. Resumo para o PO (5 linhas, sem siglas)
1. Escrevi as regras e os testes automáticos de três tarefas: validar a sua ideia mista, medir a maior parada num arquivo seu e a "porta única" do modelo.
2. A validação mede a mistura com as mesmas réguas de antes; se não passar em alguma máquina, a escolha volta a você com as duas formas puras e os números.
3. Os testes já rodam: hoje falham onde ainda não há código, e uma versão de ensaio que escrevi e apaguei passou neles 3 vezes; versões com erro de propósito foram pegas.
4. A medição pede uma sessão de cerca de 20 minutos na sua placa de vídeo, no horário que você escolher.
5. Para medir num arquivo seu, recomendo o de 25 megabytes, em tela virtual; preciso que você confirme.

## 9. Linha do LOG
`2026-10-21 | F0-S04-V1, V1b, P1 | LOTE_OPUS_69 (opus, médio, T3 especificação e oráculo) | cartões V1 (forma mista, T3), V1b (--ifc, T2, espera arquivo do PO) e P1 (porta única, T3); oráculos test_s04_v1_mista (393), test_s04_v1_veredito (166), test_s04_p1_trava (301), test_s04_p1_obimcore (155) com @AINDA_NAO: hoje 4 passam, 28 em falha esperada, 0 pulos; referência temporária 14/14 e 18/18 em 3 de 3 execuções; 8 mutantes pegos; PRs do oráculo em 4 partes de até 400 linhas; 2 perguntas ao PO (arquivo do V1b, horário da placa) | docs/state/lotes/LOTE_OPUS_69/resultado.md`
