# Relatório do lote Opus 1: licenças e dependências
- Data: 2026-10-10 · Papel: Arquiteto/Revisor crítico (opus) · Pedido: `docs/state/arquivo/lotes-1-a-28/LOTE_OPUS_1/pedido.md`
- Feito sem rede e sem instalar nada. Não é parecer jurídico.
- Li, além do pacote fechado, `docs/state/BOARD.md` e os 27 cartões (item 4). Não li `THIRD_PARTY.md`, `v2/03` nem `docs/state/reports/F0-S01.md`.

## Resultado por item
| Item | Cartão | Resultado | Arquivo |
|---|---|---|---|
| 1 | F0-S01-T11 (revisão da tabela mestre) | **REPROVADO**, 12 defeitos, todos de redação ou cobertura; nenhuma biblioteca precisa ser trocada | `docs/research/2026-10-10-licencas-revisao-opus.md` |
| 2 | F0-S01-T12 (ADR-009) | Escrito; status "proposto", aguarda ok do PO | `docs/adr/ADR-009-licencas-e-conteudo.md` |
| 3 | F0-S02-T02 (esboço do ADR-005) | Escrito; decisão pendente, 11 testes com meta | `docs/adr/ADR-005-dependencias-e-build.md` |
| 4 | Conferência da classificação | Feita; lista abaixo | este arquivo |

## As quatro pendências, em uma linha cada
1. **OCCT:** pode entrar, como arquivo separado (ligação dinâmica), sem modificação, com os textos de licença no pacote.
2. **libdxfrw:** fica fora; o DXF usa o ezdxf.
3. **Relink da LGPL:** já atendido por publicarmos o código; o pacote ainda precisa de bibliotecas em arquivos separados, nenhuma trava contra troca, pasta de licenças e lista dos fontes por release.
4. **WiX:** fora por causa da taxa (usar NSIS). **conda-forge:** pode, como canal único; `defaults` proibido. **PyInstaller:** pode; para programa AGPL a exceção nem é necessária.

## O que o líder faz em seguida
1. Atualizar BOARD e LOG: T11 reprovada (primeira reprovação); T12 e S02-T02 entregues, aguardando o PO.
2. Abrir a correção da tabela mestre (defeitos 1 a 12 da revisão) e pôr a conferência do diff em `QUEUE_OPUS.md`, junto com `THIRD_PARTY.md` e o relatório F0-S01, que ficaram fora deste lote.
3. Levar ao PO as perguntas do fim deste relatório.
4. Observação de processo: a T12 dependia de "T11 aprovada". Escrevi o ADR-009 sobre as respostas da revisão, não sobre a tabela reprovada, porque o pedido do lote mandava seguir. Nenhuma decisão do ADR depende da correção da tabela. Registrar no LOG.

## Item 4: conferência da classificação e do limite de 400 linhas
1. **S01 e S02 sem T3: concordo**, enquanto a S02 continuar só em Python. Se entrar a sonda do item 3, ela é T3.
2. **A S02 não compila nenhum C++** (T03 põe isso fora de escopo). As metas de build (T13) seriam medidas num app só Python e não diriam nada sobre o risco R2, e o risco R1 não é tocado antes da S04. Recomendo um cartão novo e pequeno na S02 com os testes 2 e 3 do ADR-005 (olhar o conteúdo do pacote do IfcOpenShell; compilar um módulo C++ mínimo). Classe T2. O teste 5 (ponte C++/Python) é **T3** e pode abrir a S04.
3. **S02-T03, limite de 400 linhas em risco.** O ambiente precisa de arquivo de trava, que tem milhares de linhas e hoje nem está nos "arquivos permitidos". Acrescentar o arquivo e registrar a exceção "arquivo gerado não conta", como foi feito para o texto da licença na S01-T02.
4. **S02-T06, limite em risco.** A checagem REUSE exige os textos completos das licenças numa pasta `LICENSES/` (só a AGPL passa de 600 linhas). Mesma exceção. O cartão também junta CI, artefato, REUSE e, pelo ADR-005, o inventário de licenças: se o diff sem os textos passar de 250 linhas, separar o inventário em cartão próprio.
5. **S02-T10 e T11 (AppImage e instalador): manter T2, mas com revisão opus obrigatória**, não por sorteio de 1 em 3. São eles que cumprem as obrigações de licença do ADR-009 e carregam o risco R2. Trocar no critério 3 a referência "ficha D" por "ADR-009 §5.3 e ADR-005 testes 7 e 8".
6. **S02-T10 e T11, tamanho em risco** se cada um tiver de comparar duas formas de montar o programa (P1 e P2 do ADR-005). Começar só com P1; P2 vira cartão separado e só se o tamanho passar de 600 MB.
7. **S02-T05: T2 está certo.** A abertura na thread da interface é provisória e está marcada; não promover a T3.
8. **Fatias sem cartão, para quando forem detalhadas:** a S03 (viewport) não está marcada como contendo T3 no quadro, mas `v2/02` §5 põe o desenho em threads C++: ou o protótipo é declarado de uma thread só, ou tem tarefa T3. A S07 (tipo paramétrico) grava IFC: contém T3.
9. **S02-T15:** o critério 2 já admite "se não testado, a prova fica para a S04". Com o cartão do item 2 desta lista, a resposta parcial (teste 2) já sai na S02.

## Respostas do PO (chat, 2026-10-10): "sim, aprovo e autorizo tudo"
Perguntas 1 a 4 abaixo: **todas aprovadas**. O líder deve copiar para `docs/state/PO.md` e agir:
1. ADR-009 passa a "aceito" (já marcado no arquivo).
2. WiX fora; instalador Windows parte do NSIS (anotado no ADR-005, que continua esboço).
3. Criar o cartão novo da S02 (testes 2 e 3 do ADR-005) e registrar no LOG a exceção "arquivo gerado não conta no limite de 400 linhas" para S02-T03 e S02-T06.
4. Propor ao PO o texto novo de `v2/05` §3.
A aprovação não cobre instalar ferramentas, usar rede nem fazer push: isso continua pedindo ok por ação.

## Perguntas ao PO (com recomendação)
1. **Aprova o ADR-009?** Recomendo aprovar. Resumo de 5 linhas no fim do arquivo.
2. **WiX fica de fora e o instalador Windows parte do NSIS?** Recomendo sim; evita taxa e termo extra.
3. **Um cartão a mais na S02** para testar a parte C++ (itens 2 a 4 acima) e as exceções de limite para arquivos gerados? Recomendo sim; sem isso a S02 mede um número que não prova nada.
4. **Ajustar o texto de `v2/05` §3** (LGPL-2.1-only como biblioteca; separar "copiar código" de "ligar biblioteca"; nota da libdxfrw)? Recomendo sim; o líder propõe o texto.
5. Opcional, sem pressa: abrir no seu navegador a página de termos do conda-forge e a do SINAPI na CAIXA e colar o endereço ou o texto no chat do líder.
