<!--
SPDX-License-Identifier: AGPL-3.0-or-later
-->
# F0-S04-T15c-estabilizar: teste instável de `test_s04_t15c_conferencias.py:130`
- Classe: **T2** (só o teste de controle, sem afrouxar número) · Tamanho: P · Implementa: sonnet · Oráculo: o próprio teste · Revisa: Opus, em lote (muda teste de oráculo)
- Origem: falhou no CI do Linux nas PRs 278 e 285 (2026-10-23 e 24), sempre no job `linux-testes (5)`, com o mesmo aviso: "controle positivo falhou: mediana de 5 medidas da razão com a principal ocupada em Python > 0,7" (valores vistos: 0,728; 0,71, 0,99, 0,58, 1,02, 0,51). Passa na repetição. Antes só falhava no Windows; ficou mais provável depois que o CI do Linux passou a rodar as partes em paralelo (T23L).
## Objetivo
Tornar o controle positivo estável sob carga de vários jobs na mesma máquina, sem afrouxar o limite de 0,7 e sem tirar caso.
## O que olhar
1. Por que a razão varia tanto (0,51 a 1,02) sob carga: medida de relógio com a principal ocupada; considerar contar trabalho em vez de tempo, ou mais amostras com a mediana, ou isolar da carga.
2. Só mudar a medição, nunca o limite. Mudar a guarda do teste de oráculo exige revisão Opus (CLAUDE.md, regras do processo).
## Critérios de aceite
1. 30 passadas seguidas no Linux em carga (rodando 4 partes em paralelo localmente) sem falha.
2. Limite 0,7 e casos iguais; CI verde em 3 rodadas.
## Próximo passo
Não urgente (a repetição do CI resolve); fazer antes do portão da F0 se falhar de novo.
