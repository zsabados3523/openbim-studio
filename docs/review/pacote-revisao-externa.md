<!--
SPDX-License-Identifier: AGPL-3.0-or-later
-->
# Pacote para revisão humana externa (rascunho, NADA ENVIADO)

Quem decide quando e para quem enviar: o PO. Este documento só organiza o material.

## O que pedimos
Uma pessoa experiente em C++ e Python (ou em IFC) que olhe, em cerca de 3 a 4 horas, as partes críticas e diga onde está errado, perigoso ou frágil. Não precisa entender o programa todo.

## Parte 1: a ponte Python/C++ (pronta para revisão)
Resumo: uma biblioteca em C++ (`obimcore`, nanobind) desenha o modelo e responde ao clique; o Python (PySide6 + ifcopenshell) edita o modelo. As duas conversam sem copiar o arquivo.
- Código: `prototypes/s04/obimcore/` (`ponte.cpp`, `malha.cpp`, `viewport.cpp`, `cena.*`, `camera.*`, `selecao.*`).
- Regras de posse e threads: `docs/state/reports/LOTE_OPUS_9.md` §1.4 e §5.2; achados e correções nos lotes 10 a 18 (`docs/state/reports/`).
- Testes: `tests/test_s04_ponte.py`, `test_s04_viewport*.py`, `test_s04_cena.py`, `test_s04_selecao*.py`, `test_s04_profundidade.py`, `test_s04_fluxo_a.py`.
- Perguntas ao revisor: (1) a regra "Python é dono, C++ nunca guarda endereço" tem furo? (2) o mutex provisório de geometria e a ordem dos mutex estão certos? (3) o uso do contador do Python (`GIL`) em `atualizar` e `selecionar`; (4) a viewport em thread própria dentro de uma janela do Qt: onde pode travar ou perder contexto? (5) o reenvio da cena inteira a cada troca de peça é um problema real?

## Parte 2: salvamento (ainda NÃO pronta)
Gravação do par `Casa.ifc` + `Casa.obim` (oplog, transações, recuperação). Será preparada depois da S05; este pacote será atualizado antes de qualquer envio.

## Como entregar
Uma pasta com os arquivos acima, `docs/state/reports/LOTE_OPUS_*.md` e instruções de build (`docs/dev-setup.md`); ou o link do repositório público no ramo `main`. O revisor responde por issue ou e-mail; as respostas viram achados numerados em `docs/state/reports/`.

---

# Texto de convite (rascunho)

Assunto: Pedido de revisão de código: ponte Python/C++ de um programa BIM aberto

Olá,

Sou Rafael, arquiteto, e conduzo o OpenBIM Studio (AGPL-3.0), um programa BIM aberto pensado para arquitetos brasileiros que não podem pagar assinaturas. Sou transparente sobre uma coisa: o código é escrito por agentes de IA, que revisam uns aos outros e passam por testes automáticos, mas não há ainda um desenvolvedor experiente olhando. Por isso estou pedindo ajuda.

Gostaria de uma revisão crítica (3 a 4 horas, no seu tempo) da ponte entre Python e C++ (nanobind, threads, posse de memória) e, mais tarde, do salvamento de arquivos. Tudo está público: o repositório, os testes e os relatórios das revisões internas. Não peço que conserte nada, só que aponte onde isso pode dar errado.

Posso preparar um pacote com as perguntas específicas e as instruções de build. Se não for possível, uma resposta de duas linhas já ajuda.

Obrigado,
Rafael
