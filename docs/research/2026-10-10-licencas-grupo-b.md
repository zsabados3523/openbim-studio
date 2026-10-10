# Fichas de licença, grupo B: interface, ponte e PDF
- Autor: líder (sonnet), coleta feita por haiku · Data: 2026-10-10 · Fatia: F0-S01-T07
- Fontes: páginas oficiais, repositórios e metadados de PyPI/conda-forge, lidos em 2026-10-10. Resumos com palavras nossas. Não é parecer jurídico.
- Revisão pendente: opus (lote 1).

| Componente | Licença (SPDX) | Versão consultada | Fonte primária | Compatível com AGPL v3? | Condições |
|---|---|---|---|---|---|
| Qt 6 | comercial, LGPL-3.0 ou GPL-3.0 (à escolha) | 6.12 | doc.qt.io/qt-6/licensing.html | **Sim**, usando a opção LGPL-3.0 | Relink: o usuário deve poder trocar o Qt. 14 módulos só estão sob GPL-3 (não LGPL): Canvas Painter, CoAP, Graphs, GRPC, HTTP Server, Lottie Animation, MQTT, Network Authorization, QML Compiler, Quick 3D, Quick 3D Physics, Quick Timeline, Virtual Keyboard, Wayland Compositor. Com AGPL v3 o GPL-3 também seria aceitável, mas **evitaremos esses módulos** por não terem opção LGPL |
| PySide6 | LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only | PyPI 6.12.0 (conda-forge 6.11.2: LGPL-3.0-only) | `LICENSES/` da tag v6.12.0 em github.com/pyside/pyside-setup; PyPI | **Sim**, pela opção LGPL-3.0-only | Mesmas do Qt (relink). Usar só a opção LGPL-3 ou GPL-3; a GPL-2.0-only não é compatível |
| nanobind | BSD-3-Clause | 3.1.0 | `LICENSE` em github.com/wjakob/nanobind | **Sim** | Manter aviso de copyright |
| pybind11 | BSD-3-Clause | 3.1.0 | `LICENSE` em github.com/pybind/pybind11 | **Sim** | Manter aviso de copyright |

## Bibliotecas de PDF (candidatas levantadas pelo líder; nenhuma foi testada)
| Candidata | Licença | Compatível? | Gera PDF vetorial? / depende de | Observações |
|---|---|---|---|---|
| QPdfWriter (parte do Qt) | mesmas opções do Qt (cabeçalho do qtbase 6.9: comercial OR LGPL-3.0 OR GPL-2.0 OR GPL-3.0) | **Sim** (opção LGPL-3) | Pelo desenho do Qt (QPainter), sai vetorial, a confirmar | Já vem com o Qt; página de documentação deu 404 |
| ReportLab (open source) | BSD-3-Clause (PyPI e conda-forge) | **Sim** | Sim, PDF vetorial, é biblioteca Python | O site oficial cita um parser RML sob GPL; não verificamos se vai no pacote PyPI. Texto do LICENSE do repositório oficial inacessível (403/404) |
| fpdf2 | LGPL-3.0-only | **Sim** | Sim, PDF vetorial, Python | Sem divergências |
| CairoSVG | LGPL-3.0 (PyPI "or-later", conda-forge "only") | **Sim** | Converte SVG para PDF, vetorial; usa a biblioteca cairo via cairocffi (BSD-3) | cairo é LGPL-2.1 OU MPL-1.1 (escolha por arquivo) |

## Não verificado
- Lista de módulos do Qt vendidos só sob licença comercial (a página oficial não lista).
- PySide6: licença do conda-forge 6.11.2 e do PyPI 6.12.0 não foram cruzadas na mesma versão.
- ReportLab: texto de LICENSE no repositório oficial e se o parser GPL entra no pacote.
- CairoSVG: "or-later" (PyPI) vs "only" (conda-forge).

## Pontos para o opus
- A condição de relink (LGPL) afeta o empacotamento: um executável único que embute o Qt pode impedir a troca (S02-T10/T11).
- Escolha da biblioteca de PDF não é desta ficha.

## Decisão para o OpenBIM Studio
Nenhuma ainda (ADR-009 e ADR-005).

## Riscos de IP identificados
Nenhum conteúdo copiado.
