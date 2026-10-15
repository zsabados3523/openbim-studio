<!--
SPDX-License-Identifier: AGPL-3.0-or-later
-->
# Revisão da S01 (repositório, licenças e pesquisa)
Data: 2026-10-14 · Cartões: F0-S01-R1 (seções 1 e 2, abaixo), R2 (seção 3, a escrever) e R3 (seções 4 a 6 e a lista final). Roteiro: `PROPOSTA_REVISAO_F0.md` §3. Status: **R1, R2 e R3 prontas; PO aceitou o parecer em 2026-10-15; falta o lote Opus 29**.

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

## 3. Pendências de licença (cartão R2, 2026-10-14)
Só leitura de páginas públicas. Nada baixado. Veredito de componente existente **não foi mudado**.

| Item | Resultado | Fonte e data de acesso | Situação |
|---|---|---|---|
| S01-b SINAPI | Site da CAIXA bloqueia leitura automática (robots). Não contornado. | caixa.gov.br, 2026-10-14 | **Não verificado.** Dono: PO (opcional, abre no navegador). Prazo: antes da F5. Ficha agora diz "incompleta" |
| S01-c Qt Shader Tools | Biblioteca de execução: comercial, LGPL-3.0 ou GPL-2.0 (desde Qt 6.3). Ferramenta `qsb`: GPL-3.0 ou comercial, usada só no build. Debian lista o módulo como GPL-3.0-only (fonte secundária, diverge). Os `.qsb` já estão no repositório e as travas do ambiente não trazem `qt6-shadertools` | doc.qt.io/qt-6/qtshadertools-index.html; metadata.ftp-master.debian.org (qt6-shadertools), 2026-10-14 | **Fechada com condição.** Linha nova na tabela, marcada "proposto". Se um dia a biblioteca for embarcada e vier só GPL-3, vai ao PO |
| S01-d conda-forge | A linha já diz "canal, não licença; vale a licença de cada pacote". Páginas de docs do conda-forge não trazem termos de uso. Receitas: BSD de 3 cláusulas (staged-recipes, 2015-2023) | conda-forge.org/docs/user/introduction e /tipsandtricks; github.com/conda-forge/staged-recipes LICENSE.txt, 2026-10-14 | **Linha correta; termos do canal seguem não verificados.** Dono: líder; reler na T23 (antes do primeiro lançamento) |
| S01-d ReportLab | PyPI (3.1.44) e docs.reportlab.com dizem BSD. O parser GPL citado é o `pyRXP`, pacote separado. LICENSE.txt da versão travada não lido (repositório inacessível) | pypi.org/project/reportlab; docs.reportlab.com/developerfaqs, 2026-10-14 | **PRECISA_PO:** hoje a tabela diz "fora até alguém ler". As fontes oficiais apontam BSD, mas não mudei o veredito. Recomendo: manter fora até a F5 e ler o LICENSE da versão travada na hora de usar |

## 4. Coerência dos documentos (passo 3 do roteiro)
| # | Onde | Divergência | Ação |
|---|---|---|---|
| 1 | Cabeçalho da tabela mestre | Dizia "aguarda conferência do diff pelo opus", mas o lote 2 já aprovou | Corrigido (1 linha) |
| 2 | `BOARD.md`, linha da S01 | Lista de abertos igual à de 10/10, sem a R2 | Corrigido |
| 3 | `reports/F0-S01.md`, item 7 | Lista de abertos velha | Nota de atualização acrescentada |
| 4 | `CLAUDE.md` | Cita planos antigos pela raiz; eles estão em `docs/arquivo/` (D2) | **Não editado** (item A8 em `PO.md`, precisa de cartão aprovado) |
| 5 | `THIRD_PARTY.md` | "Nenhum código copiado até agora (2026-10-10)": data velha, afirmação não reconferida | Aberto: reconferir na T23 (antes do primeiro lançamento) |
| 6 | `PAINEL_DO_PROJETO.md` | Diz S01 "Feita"; correto, mas não menciona a revisão em curso | Aceito: o painel é do PO e só muda quando ele aceitar a S01 |
READMEs em português e inglês têm o mesmo tamanho (37 linhas) e o mesmo aviso sobre macOS.

## 5. Testes (passo 4)
Run de CI `38653866732` (PR 93 atualizado com o `main`, 2026-10-14): `linux`, `windows`, `appimage` e `instalador-windows` **verdes**; `macos` falhou (não bloqueia, melhor esforço). A suíte cobre o repositório inteiro, não só a S01.

| Sistema | Suíte principal | Outros passos |
|---|---|---|
| Linux | 163 passam, 169 pulam, 0 falham | 128, 2, 21 e 61 passam (módulo, viewport, fluxo B) |
| Windows | 161 passam, 171 pulam, 0 falham | 127 (1 pula), 2, 21 e 61 passam |

Contagem lida do registro do job; os "pulam" são testes que precisam de tela ou do arquivo do PO.

## 6. Qualidade e plano (passos 5 e 6)
- Os arquivos da S01 (README, CONTRIBUTING, `THIRD_PARTY.md`, `REUSE.toml`, fichas) não têm duplicação nem texto sobrando que justifique reescrita. Nada foi reescrito além das 3 correções da seção 4.
- **Velocidade (P2):** a S01 foi feita de 2026-10-10 a 2026-10-11 e é fatia fácil (texto, sem código). Não serve para calibrar S04 a S06; o calendário não foi recalculado.
- **O que muda no plano:** nada em `v2/`. Dois itens vão ao PO: parecer sobre S01-a (D6) e ReportLab (A14).

## Lista numerada para o lote Opus (preencher: aprovado ou reprovado)
1. R1, seção 1: os 9 critérios estão certos, com evidência suficiente? → _
2. R1, seção 2: a cobertura dos 12 itens está correta e as duas lacunas (Qt Shader Tools, dependências transitivas) estão tratadas? → _
3. R2: a linha nova do Qt Shader Tools ("Sim, só com a condição") é correta, dada a divergência entre a documentação do Qt e o arquivo de copyright do Debian? → _
4. R2: manter ReportLab "fora" e SINAPI "não verificado" é a decisão certa? → _
5. R3: as 3 correções de coerência e a lista de pendências estão corretas? → _
6. R3: os números de teste (seção 5) batem com o CI? → _

## Respostas do PO (2026-10-15)
1. Aceita o parecer da IA como aceite da S01.
2. ReportLab é BSD (PyPI): tabela passou a "Sim, com condição" (sem pyRXP).
3. SINAPI: uso gratuito, mas automação exige autorização da CAIXA; requisito da F5.
4. Uso do Opus parado por ora (créditos iniciais), sem percentuais.
