# Perguntas ao PO

> Cada pergunta traz a recomendação do líder. Sem resposta, vale a recomendação como decisão assumida, registrada aqui. Atualizado: 2026-10-10.

## Abertas
| # | Pergunta | Recomendação do líder | Resposta do PO |
|---|---|---|---|
| P1 | Quais os percentuais de `/usage` (janela de 5 h e semana), antes e depois desta sessão, para a primeira linha de QUOTA.md? | Informar os quatro números; se não anotou o "antes", informar só o "depois" | 2026-10-10: janela 22%→29%; semana 2%→3% (registrado em QUOTA.md) |
| P2 | Licença AGPL v3 "somente" ou "ou qualquer versão posterior"? (06 diz só "AGPL v3"; o texto vai nos cabeçalhos dos arquivos) | "Ou posterior" (AGPL-3.0-or-later): é o padrão recomendado pela FSF e mais flexível. O ADR-009 confirma | 2026-10-10: **ou posterior** (AGPL-3.0-or-later) |
| P3 | Posso ler páginas públicas na internet (arquivos LICENSE, páginas de pacotes) na sessão 2, sem baixar nem instalar nada? | Sim. Download e instalação continuam pedindo ok um a um | 2026-10-10: **sim**; PO pediu haiku para a leitura das páginas. Haiku busca e transcreve; sonnet interpreta e escreve a ficha |
| P4 | Aprova a estrutura de pastas proposta (`app/`, `prototypes/`, `packaging/`, `corpus/`, `tests/`, `docs/`, `.github/workflows/`) e o texto da licença AGPL ficar fora do limite de 400 linhas? | Sim aos dois | 2026-10-10: **aprovado** (estrutura e LICENSE fora do limite de 400) |
| P5 | No app esqueleto da S02, a área da viewport será só um painel reservado (a viewport real é a S03). Ok? | Sim | 2026-10-10: **ok** (painel reservado) |
| P6 | Posso rodar `git init` local na sessão 2? As contas no GitHub e no Codeberg e a criação do repositório vazio são suas; eu guio passo a passo | Sim; criar as contas antes da sessão 2 | 2026-10-10: **git init local autorizado**; contas e repositório remoto ainda a cargo do PO |
| P7 | Qual o hardware da sua máquina Linux e da Windows (CPU, RAM, placa de vídeo, sistema)? (pergunta E de 06) | Informar até a S03; o padrão é 4 núcleos, 16 GB, vídeo integrado recente | 2026-10-10: Linux nativo; Windows via VM. CPU i5-12600KF, GPU RTX 3070, 24 GB RAM |

## Decisões já tomadas (06 §1)
10 posicionamento geral, Brasil como primeiro pacote regional (2026-10-10) · 1 corte da 1.0 · 2 Claude Pro, sonnet líder · 3 corpus do PO depois da F0 · 4 PO testa Windows e Linux, Mac melhor esforço · 5 IFC limpo + `.obim` lateral · 6 AGPL v3 · 7 sem gasto extra · 8 par `.ifc` + `.obim` com `.obimpack` para envio · 9 pset `OBIM_Projeto` aceito.

## Padrões assumidos (06 §2, sem resposta ainda)
C hospedagem GitHub + espelho Codeberg · D interface híbrida (confirmar na S09) · F gravação IFC4 e exportação IFC2x3 como critério de portão · G SignPath na v0.3 · H nome provisório "OpenBIM Studio" · I sem IA embutida na 1.0 · J consulta à CAIXA (SINAPI) só na F5.
