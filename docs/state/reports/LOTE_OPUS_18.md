<!--
SPDX-License-Identifier: AGPL-3.0-or-later
-->
# LOTE OPUS 18: revisão do PR 75 (F0-S04-T11, Fluxo A)
Revisor opus, só leitura, 2026-10-13. **APROVADO, com recomendações; nenhum achado bloqueante.** CI com os 4 jobs verdes (Linux, Windows, instalador, macOS).

## Conferido
- Critérios do cartão atendidos: roteiro R inteiro (611 repetições), uma transação por comando, GlobalIds por comando, exatamente um `Cena.atualizar` por transação/desfazer/refazer com a trava presa, `medicao.json`, localidade "C" depois de criar a aplicação e antes de gravar.
- Regra 7 (trava do modelo): sem janela de corrida; trava pega antes de `begin_transaction` e solta no `finally` só depois do `atualizar` (fluxo_a.py:153-161).
- `discard_transaction()` no erro está correto (o `undo()` desfaria a transação anterior); o texto errado é o do CONTRATO.md:14.
- Unidade mm conferida por execução; `ifcopenshell.validate` sem aviso.
- Desfazer/refazer seguem o estado resultante da cena (triângulos, imagem e seleção conferidos).
- Medições honestas (sem atalho), mas o oráculo recalcula a partir dos tempos que o próprio fluxo grava. M5 medida durante o lote: Linux 63 quadros/s, maior intervalo 17,8 ms; Windows 52–57 quadros/s, maior 32,7 ms. M2b não esconde o reenvio da cena inteira, só é pequeno nesta base (3.000 paredes ≈ 2 quadros a mais).
- Lacuna no CI: o caso de localidade com a aplicação aberta (`c_locale`) é pulado no Windows.

## Achados (recomendações)
1. [oráculo, condição da T12] Caso de validade do IFC vazio (tests/s04_fluxo_aux.py:153): o nível vem em minúsculas ("error") e o filtro procura "ERROR". Corrigir `.lower() == "error"` e ligar `express_rules=True`.
2. [oráculo, condição da T12] Tempos sem conferência de fora: tomar `obimcore.agora()` antes e depois (aux:136); exigir t0 ≥ início e todo `t_quadro_ms` > `t_comando_ms` ser entrada real de `relogio()` com sequência ≥ a devolvida; M3: conferir o texto do QLabel e um evento de pintura.
3. [oráculo] Caminhos de erro sem teste: falha depois de mudanças parciais (rollback) e falha em `_lote`/`Cena.atualizar` depois do `end_transaction`.
4. [código] Falha depois do commit deixa modelo e cena fora de sincronia (fluxo_a.py:157-158): usar `ifc.undo()` + `historico.pop()`. Em fluxo_a.py:301-304, `de.pop()` roda antes de `undo()/redo()`.
5. [contrato] CONTRATO.md:14: trocar "ifc.undo() da transação aberta" por "discard_transaction()".
6. [código, desempenho] Desfazer edição de propriedade reenvia a cena inteira (fluxo_a.py:308): guardar `geometria` no registro e refazer só essa malha (CONTRATO.md:23).
7. [núcleo, T12/ADR-001] Reenvio e fragmentação abertos (lote 15 achado 1): modelo de 1 milhão deve passar de 200 ms e piscar; medir M2b informativa com `corpus/modelo-grande-1m.ifc`; `lotes_` cresce a cada edição (compactar); anotar no ADR-001 a interface `atualizar(lote_novo, guids_remover)`.
8. [threads, T15] `ultimo`/`_ult_guid` fora da trava (fluxo_a.py:170-171, 371); `_c_selecionar` lê `self._cont.width()` na thread chamadora (336); `_bombear` não faz nada fora da thread principal (98); contagem da base fora da trava (360).
9. [menores] `mudar_comprimento` só IFC4 (274) (dar ValueError em IFC2X3); deslocamento sempre zero (205); id STEP na tabela do núcleo (204; passar 0); profundidade 2799,9999999999995 (arredondar).
10. [clique] Recomendações 1 e 2 do lote 17 ainda abertas (viewport.cpp:431 ainda dá ValueError na borda); abrir cartão antes de ligar o mouse real.
11. [oráculo, menor] Não confere que a câmera girou no 5b; não confere posição na grade com a base em mm; não testa o painel por sinal de outra thread; no Linux M5 depende de uma só janela de 1 s.
12. [processo] ci.yml fora dos arquivos permitidos (precedente aceito); fluxo_a.py com linhas muito densas: a T12 deve contar linhas depois de formatar (M7).

## Falta para a T12
Itens 1 e 2 como condição; M2b informativa no modelo de 1 milhão; rodada oficial com 3.000 paredes e `OBIM_S04_ESTRITO=1`; comparação A × B e "saída igual".

## Para o PO
O fluxo A funciona do começo ao fim: 200 paredes, edições, troca de comprimento, lote de 1.000 com a câmera girando, desfazer, refazer e gravar arquivo válido. Tempos bem abaixo dos limites nos dois sistemas; sem trapaça nas medições, mas o teste confia nos tempos que o próprio programa anota e a conferência de arquivo válido no teste está quebrada (o arquivo está bom). Corrigir antes da próxima etapa. Em modelos muito grandes, trocar uma peça ainda manda o desenho inteiro de novo.
