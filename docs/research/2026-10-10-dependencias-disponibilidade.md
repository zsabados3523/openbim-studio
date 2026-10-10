# Ficha: disponibilidade das dependências (conda-forge, vcpkg, PyPI)
- Autor: líder (sonnet), coleta por haiku · Data: 2026-10-10 · Fatia: F0-S02-T01
- Método: só leitura de páginas e APIs públicas (api.anaconda.org, pypi.org, repositórios das receitas e do vcpkg). Nada instalado nem baixado. Plataformas: win-64 e linux-64 (obrigatórias); macOS arm64 só como nota.
- Revisão pendente: opus (insumo do esboço do ADR-005).

## Tabela (versão mais recente; anteriores entre parênteses)
| Componente | conda-forge | vcpkg | PyPI |
|---|---|---|---|
| OCCT | `occt` 8.0.1 (8.0.0, 7.9.3); win-64, linux-64, osx-arm64 | `opencascade` 8.0.1; x64-windows, x64-linux, arm64-osx | **não existe** (o nome `occt` é outro projeto) |
| IfcOpenShell | `ifcopenshell` 0.9.0 (0.8.5, 0.8.4); win-64, linux-64, osx-arm64; Python 3.11 a 3.14; exige `occt >=8.0.1,<8.1` | **não existe** | 0.9.0; wheels Python 3.10 a 3.15 (win_amd64, manylinux x86_64, macOS arm64) |
| PySide6 | `pyside6` 6.11.2 (6.11.1, 6.11.0); Python 3.10 a 3.15; exige `qt6-main` 6.11.2 | **não existe** | 6.12.0 (6.11.2, 6.11.1); wheel abi3 para win_amd64, manylinux x86_64, macOS |
| shiboken6 | não é pacote separado | não existe | 6.12.0, mesmas wheels |
| Qt 6 | `qt6-main` 6.12.0 (6.11.2, 6.11.1); inclui cabeçalhos | `qtbase` 6.11.2 | vem dentro do PySide6 |
| nanobind | 3.1.0 (noarch) | 3.1.0 | 3.1.0 |
| pybind11 | 3.1.0 (noarch) | 3.1.0 | 3.1.0 |
| pythonocc-core | 8.0.1.1 (8.0.1, 7.9.3); win-64, linux-64, osx-arm64; Python 3.10 a 3.14; exige `occt ==8.0.1` | não existe | 0.16, **sem arquivos** (não instalável) |

## Respostas às perguntas do cartão
1. **IfcOpenShell C++ (cabeçalhos e bibliotecas) no conda-forge:** **não verificado.** A receita tem só dois pacotes (`ifcopenshell` e `bcf-client`), sem pacote "devel". A instalação copia tudo para o ambiente sem lista restritiva, então é provável que cabeçalhos e bibliotecas venham junto, mas isso exige abrir o pacote `.conda`. Teste real necessário.
2. **Mesma versão de OCCT e IfcOpenShell:** sim no conda-forge: `ifcopenshell` 0.9.0 é compilado contra `occt` 8.0.1 e exige a série 8.0. `pythonocc-core` também exige `occt` 8.0.1.
3. **Roda risco R1 (ABI compartilhada)?** Só no conda-forge existe a combinação OCCT + IfcOpenShell + pythonocc da mesma série. No vcpkg não há IfcOpenShell; no PyPI não há OCCT. Isso favorece conda-forge como fonte única.
4. **PySide6 e Qt no conda-forge estão descasados:** PySide6 6.11.2 pede Qt 6.11.2, mas o `qt6-main` mais recente é 6.12.0. O PySide6 6.12 só aparece no PyPI. A receita (feedstock) do PySide6 no conda-forge **não foi encontrada**, então não sabemos como é mantida.
5. **Python:** conda-forge só tem IfcOpenShell para 3.11 a 3.14. Escolher 3.12 ou 3.13 cabe em todos os pacotes acima.

## Conclusão em 5 linhas
- Viável: conda-forge cobre OCCT, IfcOpenShell, PySide6/Qt, nanobind, pybind11 e pythonocc-core em win-64 e linux-64.
- vcpkg não tem IfcOpenShell nem PySide6; só serviria para parte do C++ e exigiria compilar o resto.
- Wheels do PyPI cobrem IfcOpenShell e PySide6 (Windows e Linux), mas não OCCT; misturar PyPI com conda arrisca versões incompatíveis.
- Teste real necessário: (a) abrir o pacote `.conda` do IfcOpenShell e ver se traz cabeçalhos/bibliotecas; (b) par PySide6 + Qt (6.11.2 no conda); (c) compilar um módulo mínimo nanobind contra o Python escolhido, em win-64 e linux-64.
- Decisão: fica para o ADR-005.

## Não verificado
Conteúdo do pacote `.conda` do IfcOpenShell · versão do Qt embutida na wheel PySide6 6.12.0 · receita do PySide6 no conda-forge · se a wheel do IfcOpenShell traz cabeçalhos (presumivelmente não).

## Riscos de IP identificados
Nenhum.
