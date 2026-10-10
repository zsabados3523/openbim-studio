# Tabela mestre de licenças (F0-S01-T11, versão 2: corrigida após a revisão do opus)
- Autor: líder (sonnet) · Data: 2026-10-10 · Base: fichas dos grupos A a D (mesma pasta) e `2026-10-10-licencas-revisao-opus.md`. Não é parecer jurídico.
- **Status: correção entregue; aguarda conferência do diff pelo opus (próximo lote).** A versão 1 foi reprovada (12 defeitos); esta versão aplica os defeitos 1 a 12 sem nova pesquisa.
- Reconfirmar cada licença na **versão travada** do ambiente (S02); as versões abaixo são as consultadas em 2026-10-10, não necessariamente as distribuídas.

**Como entra:** (a) código copiado para nossos arquivos · (b) biblioteca ligada ao programa · (c) ferramenta de build ou empacotamento (não entra no programa) · (d) canal de distribuição (não é licença). Regra de relink só vale em (b).

| Componente | Licença | Como entra | Veredito | Condições |
|---|---|---|---|---|
| IfcOpenShell (C++) | LGPL-3.0-or-later (tag v0.9.0) | b | Sim | Atribuição; bibliotecas separadas e trocáveis |
| ifcopenshell-python | LGPL-3.0-or-later (v0.9.0) | b | Sim | Idem |
| OCCT | `LGPL-2.1-only WITH OCCT-exception-1.0` (identificador SPDX de memória, a conferir) (V8_0_1) | b | **Sim, com condição** | Arquivos `.dll`/`.so` separados, sem modificar, textos da LGPL 2.1 e da exceção no pacote, aviso em "Sobre", oferta do fonte da versão exata. "Only" só pesaria se copiássemos código (a) |
| pythonocc-core | LGPL-3.0 (conda-forge "or-later") (8.0.1.1) | b | Sim | Relink; divergência entre fontes registrada |
| Qt 6 (módulos LGPL) | LGPL-3.0 (ou GPL-3/comercial) (6.12; no conda-forge 6.11.2) | b | Sim | Relink; evitar módulos só GPL-3. Lacuna: licença do Qt Shader Tools (compila shaders do QRhi) não verificada; confirmar se vai no instalador |
| PySide6 | LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only (PyPI 6.12.0; conda 6.11.2) | b | Sim (opção LGPL-3) | Relink; GPL-2.0-only não vale |
| nanobind, pybind11 | BSD-3-Clause (3.1.0) | b (cabeçalhos no build) | Sim | Aviso de copyright |
| QPdfWriter (Qt) | como Qt (cabeçalho lido no qtbase 6.9, não na versão travada) | b | Sim | Idem Qt; reconfirmar |
| ReportLab | BSD-3-Clause (site cita parser GPL) (5.0.1) | b | Condição | Fora até alguém ler a licença do pacote |
| fpdf2 | LGPL-3.0-only (2.8.9) | b | Sim | Relink |
| CairoSVG (+ cairocffi, cairo) | LGPL-3.0 (PyPI or-later; conda only); cairo LGPL-2.1 OU MPL-1.1 | b | Sim | Relink |
| ezdxf | MIT | b | Sim | Aviso de copyright |
| LibreDWG | GPL-3.0-or-later (0.14) | b | Sim | Combinação com AGPL permitida pela seção 13 de cada licença; a parte GPL continua GPL-3 e o nosso código continua AGPL-3 |
| libdxfrw | disputada: README/cabeçalhos "GPL-2.0-or-later"; COPYING e API "GPL-2.0". **A ficha C corrige `v2/05` §3**, que citava "GPLv2 ou LGPLv2+": nenhum arquivo menciona LGPL | — | **Fora (decisão do opus)** | Nenhum código no repositório; DXF usa ezdxf. Reabrir só se o ezdxf falhar na F5 |
| PlaneGCS | LGPL-2.1-or-later (commit 604afdd) | a (pasta dentro do FreeCAD, não é biblioteca separada) | Sim, só na 2.0 | Comentário de origem, linha em `THIRD_PARTY.md`, licenças do que ele usa (Eigen, Boost) |
| libslvs | GPL-3.0 ("ou posterior" só no README) (v3.2) | b | Sim | Seção 13 (igual LibreDWG); só na 2.0 |
| conda-forge | canal; termos próprios não verificados | d | **Condição** | Canal único com `nodefaults`; CI falha se vier pacote de outro canal; **`defaults` da Anaconda proibido**. Canal não é licença: quem redistribui os binários somos nós, pacote a pacote |
| vcpkg | MIT | c | Sim | — |
| PyInstaller | GPL-2.0-or-later + exceção do bootloader | c | Sim | Ferramenta; mesmo sem a exceção, GPL-2.0-or-later pode ser usada como GPL-3, que combina com AGPL-3. Levar o aviso dele no pacote |
| Briefcase, conda-constructor | BSD-3-Clause | c | Sim | — |
| WiX Toolset | MS-RL + taxa de manutenção (OSMF) | c | **Fora por padrão** | Instalador Windows parte do NSIS |
| NSIS | zlib/libpng; módulos bzip2 e LZMA (CPL 1.0) | c | Sim | Versão não verificada |
| linuxdeploy, appimagetool | MIT | c | Sim | — |

## Dependências transitivas (defeito 8)
O instalador carregará dezenas de pacotes além dos listados (Python, e o que OCCT, IfcOpenShell e Qt puxam). Candidatos citados pelo opus **de memória, a conferir**: CPython (PSF-2.0), Eigen (MPL-2.0), Boost (BSL-1.0), TBB (Apache-2.0), HDF5, libxml2, FreeType (escolher FTL), CGAL (possivelmente GPL-3-or-later), componentes de terceiros dentro do Qt e o runtime do Visual C++ no Windows (proprietário, redistribuível pelos termos da Microsoft). **O inventário completo será gerado do arquivo de trava do ambiente na S02** (ADR-005, teste 9).

## Notas
- "Somente versão 3": PySide6, fpdf2 e (talvez) libslvs são "3.0-only"; o nosso código é AGPL-3.0-or-later, mas o conjunto distribuído só pode ser usado hoje sob a versão 3 (registrado no ADR-009).
- Nenhum componente é "Não" sem alternativa: DXF → ezdxf; instalador → NSIS; PDF → QPdfWriter ou fpdf2.

## Não verificado (consolidado)
Termos próprios do conda-forge · lista de módulos só comerciais do Qt · licença do Qt Shader Tools · texto do LICENSE do ReportLab · versão oficial da LGPL do pythonocc-core · identificador SPDX da exceção do OCCT · versão do NSIS · termos do SINAPI (site da CAIXA inacessível).
