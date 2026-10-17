# Componentes de terceiros

Licença do projeto: AGPL-3.0-or-later

Nenhum código de terceiros foi copiado para o repositório até agora (2026-10-10).

| Componente | Versão | Licença SPDX | Origem | Arquivos | Atribuição |
|---|---|---|---|---|---|
| (nenhum copiado) | | | | | |

## Distribuídos nos pacotes (não copiados para o repositório)
O instalador e o AppImage levam centenas de pacotes de terceiros (Python, Qt, OCCT, IfcOpenShell e dependências). A lista exata, com versão e licença, é gerada do ambiente: `licenses/INVENTARIO.md` dentro de cada pacote e `license-inventory.md` no artefato do CI. As condições de cada licença estão em [docs/research/2026-10-10-licencas-tabela-mestre.md](docs/research/2026-10-10-licencas-tabela-mestre.md). Código copiado para o repositório entra na tabela acima.

### Ligado estaticamente ao módulo `obimcore` (só nos pacotes)
| Componente | Versão | Licença SPDX | Origem | Atribuição |
|---|---|---|---|---|
| nanobind | 3.1.0 | BSD-3-Clause | pacote conda-forge `nanobind` (só no ambiente de desenvolvimento) | Aviso de copyright em `licenses/nanobind-BSD-3-Clause.txt` (AppImage); texto em `packaging/licenses-texts/nanobind-BSD-3-Clause.txt`. Compilado dentro de `_obimcore`; não foi copiado para o repositório. |

### Runtimes da Microsoft (somente no instalador Windows)
`ucrt` (Universal CRT do Windows SDK 10), `vc14_runtime` e `vcomp14` (runtimes do Visual C++ 2015-2022) são DLLs proprietárias que a Microsoft permite **redistribuir** junto de programas, e todo programa em C++ no Windows as leva. Aceitas por exceção nomeada e amarrada à versão em `scripts/license_inventory.py` (decisão do PO em 2026-10-11). Condição: distribuir só como estão, sem modificar, e manter os arquivos de licença em `licenses/pacotes/`. Não é parecer jurídico. O MKL da Intel (licença proprietária) **não** entra: o ambiente de runtime usa OpenBLAS.

