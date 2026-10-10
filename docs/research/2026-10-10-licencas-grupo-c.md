# Fichas de licença, grupo C: formatos e solver
- Autor: líder (sonnet), coleta feita por haiku · Data: 2026-10-10 · Fatia: F0-S01-T08
- Fontes: arquivos de licença e cabeçalhos nos repositórios oficiais, lidos em 2026-10-10 (commits abaixo). Resumos com palavras nossas. Não é parecer jurídico.
- Revisão pendente: opus (lote 1).

| Componente | Licença (SPDX) | Versão consultada | Fonte primária | Compatível com AGPL v3? | Entra em | Condições |
|---|---|---|---|---|---|---|
| ezdxf | MIT | commit 7c64bce (sem release publicada) | `LICENSE` em github.com/mozman/ezdxf | **Sim** | DXF, F5 | Manter aviso de copyright |
| LibreDWG | GPL-3.0-or-later (README e cabeçalhos; a API do GitHub mostra só "GPL-3.0") | tag 0.14 | `COPYING` (texto GPLv3), `README`, `dwg.h` em github.com/LibreDWG/libredwg | **Sim** | DWG como bônus, F5 | Copyleft: o conjunto distribuído segue GPL-3 ou posterior. Compatível com AGPL v3 |
| libdxfrw | **Disputada**: README.md e cabeçalhos dizem GPL-2.0-or-later; `COPYING` é o texto GPLv2; a API do GitHub lê "GPL-2.0" | commit 25a2f8d (sem release) | github.com/LibreCAD/libdxfrw (`COPYING`, `README.md`, `drw_base.h`) | **Não confirmado**: se for "ou posterior", pode ser usada sob GPL-3; se for GPLv2-only, não entra | DXF alternativo | Não há menção a LGPL em nenhum arquivo. **Registrar a disputa; não usar como código até o opus decidir.** Nossa escolha padrão para DXF é o ezdxf (MIT) |
| PlaneGCS (FreeCAD) | LGPL-2.1-or-later (SPDX e `LICENSE`); o bloco de texto dos cabeçalhos cita "versão 2 ou posterior" e o nome antigo "Library GPL" | commit 604afdd | `src/Mod/Sketcher/App/planegcs/` em github.com/FreeCAD/FreeCAD | **Sim**, "ou posterior" confirmado nos arquivos | Solver, 2.0 | Relink (usuário pode trocar a biblioteca). Divergência de versão entre SPDX e bloco textual anotada |
| libslvs (SolveSpace) | GPL-3.0; `COPYING.txt` é só o texto GPLv3, "ou posterior" aparece apenas no README.md; `slvs.h` não tem aviso de licença | tag v3.2, commit ef96633 | github.com/solvespace/solvespace | **Sim**, sob GPL-3 | Solver, 2.0 | "Ou posterior" só afirmado no README. Mesmo assim GPL-3 é compatível com AGPL v3 |

## Para o opus decidir
1. libdxfrw: a disputa "GPLv2-only vs ou posterior" se resolve? Se não, fica fora.
2. O fato de "ou posterior" constar só no README do libslvs muda algo? (aparentemente não, pois GPL-3 é compatível com AGPL v3 em qualquer caso).

## Não verificado
- A versão exata (2.1 vs "versão 2") do PlaneGCS não foi resolvida pelas fontes.

## Decisão para o OpenBIM Studio
Nenhuma ainda (ADR-009).

## Riscos de IP identificados
Nenhum conteúdo copiado. DWG via SDK fechado continua proibido (`v2/05` §1).
