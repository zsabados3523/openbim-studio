# Relatório do dia, 2026-10-14 (para o PO)

## Em que pé estamos
Fase 0, fatia S04 (ponte Python↔C++). Faltam: T12 (juiz das metas, em revisão final), T14c (programa com janela, pronto, aguarda 83), medições oficiais na sua máquina, T15, T17, T18, T19 (ADRs, decisão sua). Nenhuma meta da F0 foi medida oficialmente ainda.

## Feito hoje (mesclado no main)
- T16b (pedido 78): abertura de arquivos com peças lentas (Opus aprovou).
- T13 (79): paredes em C++ (aprovada, lote 22). T14a (87): biblioteca abre a base e fica segura em threads (lote 26/27). T14b (90): núcleo em C++ puro (lote 26). T11c (82): uma camada de material por parede, custo linear (lotes 23–25).
- Instalador do Windows consertado (89) e CI do instalador só quando o empacotamento muda (91, você aprovou).
- Plano v2/02 Revisão 3 (14 mudanças de escopo, prazo não recalculado), painel do projeto, respostas 1–4 registradas.
- Relatórios Opus 21 a 27 em docs/state/reports/. LOG e PO.md atualizados.

## Em andamento
- Pedido 83 (T12): ferramenta e juiz das metas; 3 reprovações do Opus já corrigidas; lote 28 (releitura curta) rodando.
- T14c: branch s04-t14c pronta (501 linhas, exceção aceita), vira pedido depois do 83.

## Pulado ou adiado
- Opcionais do Opus: T14b (visibilidade hidden, guarda NOMINMAX), duração zero do juiz (limite conhecido), lote 24 de T16b (estado morto, sem_malha por peça, medir modo uma-peça no seu arquivo real).
- Medições oficiais (M1–M6) e M2b com 1 milhão de peças: só na sua máquina, com a base de 3.000 paredes.
- AppImage com o mesmo critério do instalador (recomendo sim, depois de ver o 91 funcionando).
- T04b (logger local), T23 antes da primeira versão, remoção das worktrees antigas.

## Problemas e erros meus
- Apaguei por engano o passo da T13 do CI ao resolver um conflito (corrigido no 82, registrado no LOG).
- Testes de tempo da janela oscilaram no CI por causa do teste pesado da T11c; corrigido isolando o teste.
- Reprovações do Opus: T11c 2×, T12 3×, T14a 1×, T16 1× (todas corrigidas ou em correção).

## Precisa da sua autorização / decisão
1. Rodada única na tela real do Linux (números oficiais da S04), quando o 83 e a T14c entrarem.
2. ADR-001 e ADR-004 com números (T19) e a nota da interface `atualizar(lote_novo, guids_remover)`: ADR é seu.
3. Travar o ambiente do instalador pela mesma trava `.lock` (recomendo sim).
4. Aplicar o critério do instalador também ao AppImage (recomendo sim).
5. Se os testes de tempo do Windows continuarem a oscilar: dar folga aos limites (muda metas: decisão sua).
6. Quando e a quem enviar o convite de revisão externa; wireframes S09; 8 testes no Revit.
7. Atualizar o ambiente local (zlib/libxml2) para compilar o fluxo B na sua máquina: instalar pede seu ok.

## Cota
Janela 5 h em 90% (renova às 20:50 UTC), semanal 13%. Opus gasto hoje: lotes 23 a 28 (~6).
