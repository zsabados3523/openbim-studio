# Fichas de licença, grupo D: distribuição e empacotamento
- Autor: líder (sonnet), coleta feita por haiku · Data: 2026-10-10 · Fatia: F0-S01-T09
- Fontes: repositórios e páginas oficiais, lidos em 2026-10-10. Resumos com palavras nossas. Não é parecer jurídico.
- Revisão pendente: opus (lote 1).

| Item | Licença / termos | Versão consultada | Fonte primária | A licença da ferramenta contamina o programa gerado? | Se não usarmos |
|---|---|---|---|---|---|
| conda-forge (canal) | **Termos próprios do canal: não verificados** (a página `conda-forge.org/docs/user/tos/` deu 404) | — | conda-forge.org/docs | Cada pacote mantém a licença dele; ver tabela mestre | Alternativa: vcpkg + pacotes prontos do PyPI |
| Canal "defaults" da Anaconda | Termos de Serviço da Anaconda de 15/07/2025: uso gratuito para pessoa física não comercial, universidade, ONG/pesquisa elegível e empresa com até 200 empregados ou contratados; acima disso, plano pago | 15/07/2025 | anaconda.com/legal/terms-of-service | — | **Não usar `defaults`**; só conda-forge. O conda-forge diz ser incompatível com `defaults` desde 2024 |
| vcpkg | MIT | tag 2026.07.29 | `LICENSE.txt` em github.com/microsoft/vcpkg | Não | — |
| PyInstaller | GPL-2.0-or-later **com exceção do bootloader** | tag v6.22.3 | `COPYING.txt` em github.com/pyinstaller/pyinstaller | **Pelo texto da exceção, não**: o programa empacotado com o bootloader sem modificação não fica obrigado a GPL por isso. Leitura do texto, não parecer jurídico | Briefcase ou conda-constructor |
| Briefcase (BeeWare) | BSD-3-Clause | tag v0.4.5 | `LICENSE` em github.com/beeware/briefcase | Não | — |
| conda-constructor | BSD-3-Clause (a API do GitHub mostra "NOASSERTION", o arquivo é BSD-3) | tag 3.17.3 | `LICENSE.txt` em github.com/conda/constructor | Não | — |
| WiX Toolset | Código-fonte sob MS-RL (v4, v5, v7). **Mas** o README e o texto OSMF exigem o "Open Source Maintenance Fee" para baixar releases e para uso que gere receita; isso contradiz a leitura permissiva do `LICENSE.TXT` | v4.0.0, v5.0.2, v7.0.0 | github.com/wixtoolset/wix (`LICENSE.TXT`, `README.md`, `OSMFEULA.txt`) | Não pelo texto, mas há **custo/termo extra** de uso | NSIS |
| NSIS | zlib/libpng (código principal); módulo bzip2 sob licença bzip2; módulo LZMA sob CPL 1.0 | trunk (sem tag) | `COPYING` no SourceForge e nsis.sourceforge.io/License | Não | WiX |
| linuxdeploy | MIT | tag 1-alpha-20251107-1 | `LICENSE.txt` em github.com/linuxdeploy/linuxdeploy | Não | — |
| appimagetool | MIT para a ferramenta; o texto diz que não se aplica ao conteúdo dos AppImage (cada app mantém a licença própria) | tag "continuous" | `LICENSE` em github.com/AppImage/appimagetool | Não | — |

## Para o opus decidir
- WiX: o Open Source Maintenance Fee se aplica a um projeto AGPL de um único mantenedor sem receita? (Se houver dúvida, a rota segura é NSIS.)
- Condição de relink da LGPL (Qt, IfcOpenShell, OCCT) no formato de empacotamento escolhido.

## Não verificado
- Termos próprios do conda-forge e cobertura exata do canal `defaults` pelos termos da Anaconda.
- Parecer jurídico sobre a exceção do PyInstaller.
- WiX v4.0.0: só o início do texto foi comparado.
- NSIS: versão de release (o repositório é SVN sem tag).

## Decisão para o OpenBIM Studio
Nenhuma (ADR-005 decide a ferramenta).

## Riscos de IP identificados
Nenhum conteúdo copiado.
