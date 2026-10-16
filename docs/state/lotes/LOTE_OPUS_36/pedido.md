# LOTE_OPUS_36: pedido
Revisão independente (T3, contexto fechado) da F0-S04-T14d, ramo `s04-t14d-corrida-a`. Cartão e oráculo (e25e8b7, 14d7020) de outro Opus; implementação 531fa63 (Sonnet).
Julgar: (1) cumpre o cartão e equivale à regra do fluxo B (`t_cam` em main.cpp): instante tomado depois de a Cena voltar, 5 comandos, 2 quadros, falha em ~10 s, só com janela, `janela=False` intacto; (2) sem deadlock nem reordenação de travas, sem mudar M2..M5; `_bombear` seguro; (3) nenhum teste existente editado, oráculo reprova mutantes (espera 1 quadro; marca só `enquadrar`); (4) ci.yml só acrescenta o arquivo às duas listas `OBIM_CI`; (5) oráculo + `test_s04_fluxo_a.py` com `OBIM_S04_T11_OBRIGATORIO=1`, 2 vezes, sob xvfb-run.
Saída: APROVADO ou REPROVADO com lista numerada.
