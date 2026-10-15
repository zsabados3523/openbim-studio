# Tabela mestre de licenças (F0-S01-T11, versão 2: corrigida após a revisão do opus)
- Autor: líder (sonnet) · Data: 2026-10-10 · Base: fichas dos grupos A a D (mesma pasta) e `2026-10-10-licencas-revisao-opus.md`. Não é parecer jurídico.
- **Status: APROVADA no lote Opus 2 (2026-10-11, 12 de 12 defeitos corrigidos); a linha do Qt Shader Tools (R2, 2026-10-14) foi aprovada no lote Opus 29 (2026-10-15).** A versão 1 foi reprovada (12 defeitos); esta versão aplica os defeitos 1 a 12 sem nova pesquisa.
- Reconfirmar cada licença na **versão travada** do ambiente (S02); as versões abaixo são as consultadas em 2026-10-10, não necessariamente as distribuídas.

**Como entra:** (a) código copiado para nossos arquivos · (b) biblioteca ligada ao programa · (c) ferramenta de build ou empacotamento (não entra no programa) · (d) canal de distribuição (não é licença). Regra de relink só vale em (b).

| Componente | Licença | Como entra | Veredito | Condições |
|---|---|---|---|---|
| IfcOpenShell (C++) | LGPL-3.0-or-later (tag v0.9.0) | b | Sim | Atribuição; bibliotecas separadas e trocáveis |
| ifcopenshell-python | LGPL-3.0-or-later (v0.9.0) | b | Sim | Idem |
| OCCT | `LGPL-2.1-only WITH OCCT-exception-1.0` (identificador SPDX conferido na lista oficial de exceções do SPDX, lote opus 2) (V8_0_1) | b | **Sim, com condição** | Arquivos `.dll`/`.so` separados, sem modificar, textos da LGPL 2.1 e da exceção no pacote, aviso em "Sobre", oferta do fonte da versão exata. "Only" só pesaria se copiássemos código (a) |
| pythonocc-core | LGPL-3.0 (conda-forge "or-later") (8.0.1.1) | b | Sim | Relink; divergência entre fontes registrada |
| Qt 6 (módulos LGPL) | LGPL-3.0 (ou GPL-3/comercial) (6.12; no conda-forge 6.11.2) | b | Sim | Relink; evitar módulos só GPL-3. Qt Shader Tools: linha própria abaixo (R2, 2026-10-14) |
| Qt Shader Tools (R2, 2026-10-14; **aprovada no lote Opus 29, 2026-10-15**) | biblioteca de execução: comercial, LGPL-3.0 ou GPL-2.0 (desde Qt 6.3); ferramenta `qsb`: GPL-3.0 (ou comercial). Fonte: doc.qt.io/qt-6/qtshadertools-index.html, acesso 2026-10-14. Divergência: o arquivo de copyright do Debian lista o módulo inteiro como GPL-3.0-only (fonte secundária; o `qsb` com exceção do Qt para a saída) | biblioteca: b; `qsb`: c (só no build) | Sim, só com a condição | `qsb` não vai ao instalador (os `.qsb` são gerados antes e ficam no repositório; as travas do ambiente não trazem `qt6-shadertools`). Se algum dia a biblioteca for embarcada e só houver a opção GPL-3, o veredito muda e vai ao PO. Os `.qsb` gerados pela ferramenta são material nosso e ficam com a licença do projeto (o `REUSE.toml` cobre `**`) |
| PySide6 | LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only (PyPI 6.12.0; conda 6.11.2) | b | Sim (opção LGPL-3) | Relink; GPL-2.0-only não vale |
| nanobind, pybind11 | BSD-3-Clause (3.1.0) | b (cabeçalhos no build) | Sim | Aviso de copyright |
| QPdfWriter (Qt) | como Qt (cabeçalho lido no qtbase 6.9, não na versão travada) | b | Sim | Idem Qt; reconfirmar |
| ReportLab | BSD-3-Clause (site cita parser GPL) (5.0.1) | b | **Sim, com condição** (decisão do PO, 2026-10-15) | PyPI e docs.reportlab.com dizem BSD; o parser GPL é o pyRXP, pacote separado e **não pode entrar**. Reconferir o LICENSE.txt da versão travada quando o pacote entrar no ambiente (F5) |
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
O instalador e o AppImage carregam dezenas de pacotes além dos listados (Python, e o que OCCT, IfcOpenShell e Qt puxam). Candidatos citados pelo opus **de memória, a conferir**: CPython (PSF-2.0), Eigen (MPL-2.0), Boost (BSL-1.0), TBB (Apache-2.0), HDF5, libxml2, FreeType (escolher FTL), CGAL (possivelmente GPL-3-or-later), componentes de terceiros dentro do Qt e o runtime do Visual C++ no Windows (proprietário, redistribuível pelos termos da Microsoft). **O inventário completo será gerado do arquivo de trava do ambiente na S02** (ADR-005, teste 9).

## Notas
- "Somente versão 3": PySide6, fpdf2 e (talvez) libslvs são "3.0-only"; o nosso código é AGPL-3.0-or-later, mas o conjunto distribuído só pode ser usado hoje sob a versão 3 (registrado no ADR-009).
- Nenhum componente é "Não" sem alternativa: DXF → ezdxf; instalador → NSIS; PDF → QPdfWriter ou fpdf2.

## Não verificado (consolidado)
Termos próprios do conda-forge (R2: duas páginas de docs sem termos; receitas em BSD-3 no staged-recipes; segue não verificado) · lista de módulos só comerciais do Qt · ~~licença do Qt Shader Tools~~ (fechada pela R2, ver linha) · texto do LICENSE do ReportLab (BSD em fontes oficiais; PO aceitou em 2026-10-15; arquivo da versão travada a reconferir na F5) · versão oficial da LGPL do pythonocc-core · identificador SPDX da exceção do OCCT · versão do NSIS · termos do SINAPI (site da CAIXA inacessível; R2: o robô de leitura é bloqueado pelo site, não contornado).

## Conferência do lote opus 2 (2026-10-11)
- Tabela aprovada (12 de 12 defeitos corrigidos). Lista real dos pacotes distribuídos: `licenses/INVENTARIO.md` de cada pacote e `license-inventory.md` no artefato do CI (gerados do ambiente de runtime; nada é escrito à mão).
- Escolhas de licença vistas no inventário real: FreeType (`GPL-2.0-only OR FTL`: escolhida FTL), FreeImage (escolhida GPL-3), GMP (escolhida LGPL-3), cairo (`LGPL-2.1-only OR MPL-1.1`), dbus (`AFL-2.1 OR GPL-2.0-or-later`), readline (GPL-3.0-only, usada pelo Python: combina pela seção 13 da AGPL), CGAL (GPL-3/LGPL-3, compilado dentro do IfcOpenShell: seção 13). Outras bibliotecas "LGPL-2.1-only" além do OCCT: geos, libiconv, libnsl, libraw, com as mesmas condições do OCCT.
- Versões consultadas que faltavam: ezdxf, vcpkg, Briefcase/conda-constructor, WiX, linuxdeploy: copiar das fichas (`docs/research/2026-10-10-licencas-grupo-*.md`); appimagetool: 1.9.1 (a do CI).
- Contagem: 24 linhas de componentes na tabela (com Qt Shader Tools, 2026-10-14) (o ADR-009 §3 diz 24 linhas; ajustar quando o ADR for tocado de novo).
