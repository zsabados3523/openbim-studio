<!--
SPDX-License-Identifier: AGPL-3.0-or-later
-->
# F1-CI: cadeia do instalador no CI do Windows (herdeiro do F0-S04-T23d)
- Classe: **T3** (mexe em `packaging/` e no módulo `obimcore`) · Tamanho: M · Implementa: sonnet · Oráculo: tempos do CI (3 rodadas) e contagens de teste · Revisa: opus, em lote
- Origem: decisão do PO em 2026-10-23 (aceitar cerca de 12 min no Windows para fechar a S04; a meta de 10 min do ADR-005 continua como objetivo). `reports/F0-S04-T23d.md` (fila mediana 11:58, antes 17:48).
## Objetivo
Levar a fila do Windows no CI para até 10 min numa alteração pequena, sem tirar teste e sem afrouxar limite. Depois do T23d (testes em 11 partes) o piso é a cadeia `windows-obimcore` (4:33 a 5:39) mais `instalador-windows` (4:41 a 6:43): 9:17 a 11:58 sozinha, e os trabalhos de teste ficam em 9 a 11 min.
## O que olhar
1. Ambiente do `windows-obimcore` (2:40 a 2:50 dos cerca de 5 min): cache e instalação do conda.
2. Compressão do instalador em `packaging/` (`gzip -9` mais LZMA sólido) e o tempo do R1-j.
3. `test_s04_metas.py` leva 230 a 300 s sozinho; só dividir o arquivo com revisão Opus, sem mudar número nem caso.
4. Custo fixo por parte nova (ambiente 2:20 a 5:16 mais módulo 50 a 90 s): dividir mais só compensa acima de cerca de 5 min de testes por parte.
## Critérios de aceite (rascunho)
1. Mediana de 3 rodadas novas, sem outro CI junto, do começo do primeiro trabalho obrigatório do Windows ao fim do último: até 10 min.
2. Mesmas contagens de teste; nomes dos checks obrigatórios iguais.
3. Se não chegar, parar e levar opções com números ao PO.
## Próximo passo
Entra na F1 depois do portão da F0; detalhar com a medida do `windows-obimcore` e do instalador.
