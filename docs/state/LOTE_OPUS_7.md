# Pedido do lote Opus 7: revisão da T08 (0, A, B1, B2, C, D) e da T26

> Para colar numa sessão **Opus** aberta na pasta do projeto. Preparado em 2026-10-12 pelo líder (sonnet). Cota semanal usada: 24% (restante 76%, acima do mínimo de 25%). Lote anterior: `docs/state/reports/LOTE_OPUS_6.md`.

## Cole isto na sessão Opus
Você é o papel Arquiteto/Revisor crítico do OpenBIM Studio (BIM aberto, AGPL v3 ou posterior, Windows e Linux). O PO, Rafael, é arquiteto e não programa: resumos em pt-BR **simples, sem siglas**, com recomendação. **Regra de execução: nenhum teste gráfico pode abrir janela na tela real; use `xvfb-run` (comando em `docs/dev-setup.md`).** O arquivo real do PO (`../openbim-studio-referencia/ifc/biblioteca-3pav-ifc4.ifc`) é só leitura: nunca copiar nem enviar a serviço online.

**Contexto fechado.** `git fetch` e leia:
- Sua especificação: `docs/state/reports/LOTE_OPUS_6.md` §2 (T08) e §3 (T26).
- Relatórios de medição: `docs/state/reports/F0-S03-T08.md` (T08-C) e `F0-S03-T08-D.md` (ramo `s03-t08-d`), e as linhas do LOG de 2026-10-12.
- Pilha da T08, todos ainda sem merge, cada PR empilhado no anterior: PR 28 `s03-t08-0` (oráculo P1 a P12), PR 30 `s03-t08-a`, PR 31 `s03-t08-b1`, PR 32 `s03-t08-b2`, PR 33 `s03-t08-c`, PR 34 `s03-t08-d`. Diff de cada um: `git diff origin/<base>...origin/<ramo>`.
- T26: PR 35, ramo `s03-t26` (oráculo e implementação juntos, base `main`).
- Decisões do PO: `docs/state/PO.md` (meta de memória aceita como "atingida na prática" para este arquivo; valor final na S04).

### Item 1 (obrigatório, T3): revisar a pilha da T08
Para cada PR (28, 30, 31, 32, 33, 34): aprovado ou reprovado, com lista numerada. Pontos pedidos pelos implementadores: (a) no modo isolado, id sem geometria menor que a peça lenta pode ser tomado como culpado (custa uma espera extra); (b) se o filho da caixa falha, a caixa vira cubo de 0,5 m na origem; (c) caminho de sólido extrudado da caixa sem teste; (d) `produtos_feitos` e `indice_lote` reescritos pelo pai; (e) mensagem extra sobre queda; (f) T08-D libera vértices e índices no pai depois do envio à placa: a troca de contexto gráfico perde os lotes (`lotes_perdidos`); aceitável no protótipo? (g) `pico_memoria_mb(ident)` no Windows com `Process.sentinel`, não testado; (h) o oráculo do 28 cobre mesmo o que você especificou? Conferir que nenhum número da T05 foi afrouxado e que as emendas só valem com `requer_processo`. Ordem de merge sugerida (cada um com `linux` e `windows` verdes): 28, 30, 31, 32, 33, 34.

### Item 2 (obrigatório, T3): revisar a T26 (PR 35)
Oráculo L1 a L6 (escrito por agente diferente do implementador) e `localidade.py`/`main.py`/`ci.yml`/`dev-setup.md`. Aprovado ou reprovado com lista. O passo do CI que cria pt_BR no executor Linux foi autorizado pelo PO e ainda não rodou no GitHub: ver o aviso do job.

### Item 3: seguimento
Cartão futuro a especificar (se couber): aplicar a correção da localidade em `prototypes/viewport_qrhi/__main__.py` e `medir.py` depois do merge da pilha; aviso ao abrir IFC já estragado (S05).

## Arquivos que você pode criar ou editar
`docs/state/reports/LOTE_OPUS_7.md` (novo)

## Formato da resposta final no chat
STATUS: SUCESSO | FALHA | PRECISA_PO
TAREFA: Lote Opus 7
RESUMO: ≤ 8 linhas em pt-BR simples
EVIDENCIAS: item 1 (PRs 28 a 34), item 2 (PR 35)
PERGUNTA_PO: se houver, com recomendação

Depois, o PO volta ao líder com "Leia docs/state e continue".
