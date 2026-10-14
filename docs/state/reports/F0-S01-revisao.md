<!--
SPDX-License-Identifier: AGPL-3.0-or-later
-->
# Revisão da S01 (repositório, licenças e pesquisa)
Data: 2026-10-14 · Cartões: F0-S01-R1 (seções 1 e 2, abaixo), R2 (seção 3, a escrever) e R3 (seções 4 a 6 e a lista final). Roteiro: `PROPOSTA_REVISAO_F0.md` §3. Status: **R1 pronta; relatório ainda não fechado**.

## Resumo de 5 linhas para o PO (D6)
1. A S01 entregou o que o plano pede: repositório público com `main` protegida, licença AGPL v3 conferida, READMEs em dois idiomas e tabela de licenças com 23 linhas e nenhum componente incompatível sem alternativa.
2. O parecer da tabela foi dado por IA (Opus no papel de arquiteto, lote 2, aprovada). O plano pede "revisada pelo papel Arquiteto": hoje esse papel foi feito por IA, não por pessoa.
3. Quatro pontos seguem sem confirmação: termos do SINAPI (site da CAIXA em loop), licença do Qt Shader Tools, termos do conda-forge e texto da licença do ReportLab. Nenhum bloqueia a F0; o cartão R2 tenta fechar cada um.
4. O espelho no Codeberg foi adiado por decisão sua (2026-10-10).
5. **Pergunta:** você aceita o parecer da IA como o aceite da S01? Recomendo sim, com a ressalva de que os quatro pontos acima ficam registrados com data e dono.

## 1. Aceite contra o plano (`v2/03`, F0-S01)
Critério sem evidência conta como não atendido.

| # | Critério de `v2/03` | Evidência | Atendido |
|---|---|---|---|
| 1 | Repositório no GitHub | `github.com/zsabados3523/openbim-studio`, público; `main` protegida com `linux` e `windows` obrigatórios (`reports/F0-S01.md` itens 1; `CLAUDE.md`) | Sim |
| 2 | Espelho no Codeberg | Adiado por decisão do PO (`LOG.md` 2026-10-10, T01; `PO.md` P6) | **Não, adiado** (S01-f) |
| 3 | AGPL v3 | `LICENSE`, `LICENSES/AGPL-3.0-or-later.txt`, `REUSE.toml`; passo REUSE no CI (`.github/workflows/ci.yml`, "REUSE"); hash do LICENSE no `LOG.md` 2026-10-10 | Sim |
| 4 | README pt-BR e en, CONTRIBUTING | `README.md`, `README.en.md`, `CONTRIBUTING.md`, `CONTRIBUTING.en.md` | Sim |
| 5 | Estrutura mínima de pastas | `app/`, `prototypes/`, `packaging/`, `corpus/`, `tests/`, `docs/` (P4 aprovado por PO) | Sim |
| 6 | Auditoria de licenças com ficha em `docs/research/` | Fichas grupos A a D e tabela mestre (`docs/research/2026-10-10-licencas-*.md`); `THIRD_PARTY.md` | Sim |
| 7 | Reconfirmar com fonte primária os itens Parcial ou Não verificado de `07` | OCCT: sim (tag V8_0_1; lote 2 conferiu o identificador, e achou que o pacote `occt` do conda-forge não traz o texto da exceção). libdxfrw: sim (corrige `v2/05` §3). nanobind e pybind11: sim (BSD-3). PlaneGCS: sim (commit 604afdd). **SINAPI: não** (site em loop; ficha com "Revisado por: pendente") | **Parcial** (SINAPI) |
| 8 | Tabela "licença / compatível / condições" revisada pelo papel Arquiteto | Lote 1 reprovou a v1 (12 defeitos); lote 2 aprovou a v2 (12 de 12) em `reports/LOTE_OPUS_2.md`. Revisor = IA | **Sim por IA; aceite do PO pendente** (S01-a, D6) |
| 9 | Nenhuma incompatível sem alternativa | Tabela, notas: "Nenhum componente é Não sem alternativa" (DXF→ezdxf, instalador→NSIS, PDF→QPdfWriter ou fpdf2). WiX e libdxfrw "fora" | Sim |

## 2. Cobertura da lista de componentes de `v2/03`
Todos os 12 itens têm linha na tabela mestre (23 linhas, 26 nomes).

| Item de `v2/03` | Linha na tabela | Observação |
|---|---|---|
| IfcOpenShell | "IfcOpenShell (C++)" | LGPL-3.0-or-later |
| ifcopenshell-python | "ifcopenshell-python" | idem |
| OCCT | "OCCT" | LGPL-2.1-only com exceção; condição de relink |
| pythonocc-core | "pythonocc-core" | divergência entre fontes anotada |
| Qt 6 / PySide6 | "Qt 6" e "PySide6" | **lacuna: Qt Shader Tools** (vai ao R2) |
| nanobind / pybind11 | "nanobind, pybind11" | BSD-3 |
| ezdxf | "ezdxf" | MIT |
| LibreDWG | "LibreDWG" | GPL-3.0-or-later |
| PlaneGCS | "PlaneGCS" | só na 2.0 |
| libslvs | "libslvs" | só na 2.0 |
| conda-forge / vcpkg | "conda-forge", "vcpkg" | conda-forge: "termos não verificados" (R2) |
| Bibliotecas de PDF | "QPdfWriter", "ReportLab", "fpdf2", "CairoSVG" | ReportLab "fora até alguém ler a licença" (R2) |

Lacunas achadas, sem corrigir aqui:
- **Qt Shader Tools** não está na tabela (R2).
- **Dependências transitivas** (o que OCCT, IfcOpenShell e Qt puxam) aparecem na tabela como "candidatos citados". A cobertura real vem do inventário de licenças do CI (S02-T20), não da tabela. Registro: a tabela cobre o que escolhemos; o inventário cobre o que vai no pacote.
- O cabeçalho da tabela diz "aguarda conferência do diff pelo opus", mas o lote 2 já aprovou. Texto velho; corrigir na R3 (coerência).

## S01-f: espelho no Codeberg
Adiado por decisão do PO em 2026-10-10. Dono: PO. Condição para voltar: quando o PO quiser um segundo endereço público; não bloqueia nenhuma fatia.
