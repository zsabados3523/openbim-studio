# Tabela mestre de licenças (F0-S01-T11)
- Autor: líder (sonnet) · Data: 2026-10-10 · Base: fichas dos grupos A a D (mesma pasta). Não é parecer jurídico.
- **Status: aguardando revisão do opus (lote 1).** Nada aqui é "aprovado provisoriamente".

Legenda de compatibilidade com AGPL v3: **Sim** · **Condição** · **Pendente** (opus decide) · **Não**.

| Componente | Licença | Compatível | Condições | Ficha |
|---|---|---|---|---|
| IfcOpenShell (C++) | LGPL-3.0-or-later | Sim | Atribuição; relink | A |
| ifcopenshell-python | LGPL-3.0-or-later | Sim | Idem | A |
| OCCT | LGPL-2.1-only + Open CASCADE Exception 1.0 | **Pendente** | "only" fora da tabela de `v2/05` §3 | A |
| pythonocc-core | LGPL-3.0 (conda-forge: "or-later") | Sim | Relink; divergência de fontes | A |
| Qt 6 (módulos LGPL) | LGPL-3.0 (ou GPL-3 / comercial) | Sim | Relink; evitar os 14 módulos só GPL-3 | B |
| PySide6 | LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only | Sim (opção LGPL-3) | Relink; GPL-2.0-only não vale | B |
| nanobind | BSD-3-Clause | Sim | Aviso de copyright | B |
| pybind11 | BSD-3-Clause | Sim | Aviso de copyright | B |
| QPdfWriter (Qt) | como Qt | Sim | Idem Qt | B |
| ReportLab | BSD-3-Clause (site cita parser GPL) | Condição | Confirmar o que vai no pacote | B |
| fpdf2 | LGPL-3.0-only | Sim | Relink | B |
| CairoSVG | LGPL-3.0 (PyPI or-later; conda only) | Sim | cairo: LGPL-2.1 OU MPL-1.1 | B |
| ezdxf | MIT | Sim | Aviso de copyright | C |
| LibreDWG | GPL-3.0-or-later | Sim | Conjunto fica GPL-3+ | C |
| libdxfrw | disputada: GPL-2.0-or-later (README) vs GPLv2 (COPYING/API) | **Pendente** | Fora até decisão | C |
| PlaneGCS | LGPL-2.1-or-later | Sim | Relink | C |
| libslvs | GPL-3.0 ("ou posterior" só no README) | Sim | Conjunto fica GPL-3 | C |
| conda-forge (canal) | termos do canal não verificados | Pendente | Não usar `defaults` (termos Anaconda 2025) | D |
| vcpkg | MIT | Sim | — | D |
| PyInstaller | GPL-2.0-or-later + exceção do bootloader | Sim (pelo texto) | Parecer jurídico não verificado | D |
| Briefcase, conda-constructor | BSD-3-Clause | Sim | — | D |
| WiX Toolset | MS-RL + taxa de manutenção (OSMF) | **Pendente** | Custo/termo extra | D |
| NSIS | zlib/libpng; bzip2; LZMA sob CPL 1.0 | Sim (pelo COPYING) | Versão não verificada | D |
| linuxdeploy, appimagetool | MIT | Sim | — | D |

Nenhum componente é "Não". Alternativas: DXF (ezdxf no lugar da libdxfrw), instalador (NSIS no lugar do WiX), PDF (QPdfWriter ou fpdf2 no lugar do ReportLab).

## Para o opus decidir
1. OCCT LGPL-2.1-only com AGPL v3 e a exceção da Open CASCADE.
2. libdxfrw: manter fora, ou aceitar a leitura "GPL-2.0-or-later"?
3. Relink da LGPL (Qt, IfcOpenShell, OCCT) e o formato de empacotamento.
4. WiX e o Open Source Maintenance Fee; termos do conda-forge; parecer sobre a exceção do PyInstaller.

## Não verificado (consolidado)
Termos próprios do conda-forge · lista de módulos só comerciais do Qt · texto do LICENSE do ReportLab · versão oficial da LGPL do pythonocc-core · SPDX da exceção do OCCT · versão do NSIS · termos do SINAPI (site da CAIXA inacessível).
