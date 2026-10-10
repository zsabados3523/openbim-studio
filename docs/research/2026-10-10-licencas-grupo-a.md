# Fichas de licença, grupo A: núcleo BIM e geometria
- Autor: líder (sonnet), coleta feita por haiku · Data: 2026-10-10 · Fatia: F0-S01-T06
- Fontes: arquivos LICENSE/COPYING dos repositórios oficiais, lidos em 2026-10-10 (URLs na tabela). Resumos com palavras nossas. Não é parecer jurídico.
- Revisão pendente: opus (lote 1), exigida pelo aceite de `v2/03` S01.

| Componente | Licença (SPDX) | Versão consultada | Fonte primária | Compatível com AGPL v3? | Condições |
|---|---|---|---|---|---|
| IfcOpenShell (núcleo C++: ifcparse, ifcgeom) | LGPL-3.0-or-later | tag v0.9.0 | `COPYING.LESSER` e README da tag v0.9.0 em github.com/IfcOpenShell/IfcOpenShell | **Sim** | Atribuição; quem recebe deve poder trocar a biblioteca por outra versão (relink). A raiz também tem `COPYING` (GPL-3) que cobre só ferramentas GPL à parte (Bonsai etc.), que não usamos como código |
| ifcopenshell-python | LGPL-3.0-or-later | tag v0.9.0 | README da tag (marca o módulo Python junto com o núcleo) | **Sim** | Mesmas do núcleo. PyPI não preenche o campo de licença (só classificador LGPLv3+); conda-forge diz LGPL-3.0-or-later |
| Open CASCADE (OCCT) | **LGPL-2.1-only** + Open CASCADE Exception 1.0 | V8_0_1 | `LICENSE_LGPL_21.txt` e `OCCT_LGPL_EXCEPTION.txt` da tag V8_0_1 em github.com/Open-Cascade-SAS/OCCT | **Condição, para o opus decidir** | A exceção permite distribuir código objeto que incorpore trechos de cabeçalhos. Existe também licença comercial da Open CASCADE (não usada). A tabela de `v2/05` §3 cobre "LGPL-2.1+/3"; "2.1-only" é caso à parte |
| pythonocc-core | LGPL-3.0 (README: "version 3") | release 8.0.1.1 | `LICENSE` e README no master de github.com/tpaviot/pythonocc-core | **Sim** (LGPL-3), com divergência anotada | conda-forge declara "or-later"; PyPI mostra versão 0.16 e licença "LGPL" sem versão. Não sabemos qual é o pacote PyPI oficial; usar a fonte do ADR-005 |

## Pontos para o opus decidir
1. OCCT LGPL-2.1-only com AGPL v3: a ligação dinâmica é compatível? A exceção ajuda? (nenhum "aprovado provisoriamente").
2. Relink da LGPL (IfcOpenShell, OCCT, pythonocc): o empacotamento (S02-T10/T11) precisa deixar as bibliotecas substituíveis.

## Não verificado
- Identificador SPDX oficial da Open CASCADE Exception (não encontrado).
- Qual versão da LGPL o pythonocc-core declara de forma oficial ("only" vs "or-later") e qual é o pacote PyPI oficial.
- No master do IfcOpenShell o último commit é de 2024-04-18; usamos a tag v0.9.0 (branch padrão do repositório).

## Decisão para o OpenBIM Studio
Nenhuma ainda. Esta ficha só informa; a decisão fica no ADR-009 (S01-T12).

## Riscos de IP identificados
Nenhum conteúdo copiado. Risco de licença restrito aos dois pontos acima.
