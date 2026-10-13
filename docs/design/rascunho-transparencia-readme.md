<!--
SPDX-License-Identifier: AGPL-3.0-or-later
-->
# Rascunho: texto de transparência para o README (NÃO aplicado)

Para o PO aprovar. Depois do seu ok, entra no `README.md` e no `README.en.md`, logo abaixo de "Estágio".

---

## Transparência: quem faz, como e para quem

**Quem faz.** O OpenBIM Studio é um projeto de uma pessoa: Rafael, arquiteto, que define o que o programa precisa fazer e aceita (ou recusa) cada etapa. Ele não escreve código. O código é escrito por agentes de inteligência artificial (modelos Claude, da Anthropic), conduzidos por um "líder técnico", que também é uma IA. Não há, hoje, uma equipe de programadores experientes por trás.

**Como o código é feito.** Cada tarefa nasce de um cartão escrito, com critério de aceite. Quem escreve os **testes** é uma IA diferente da que escreve o **código**, e o código não passa se os testes dela não passarem. Partes delicadas (a ponte entre Python e C++, tarefas com várias linhas de execução, o salvamento dos arquivos) passam por uma **revisão cruzada** feita por um modelo mais forte, e só entram depois de aprovadas. Todos os testes rodam sozinhos, em Windows e Linux, a cada mudança; nada entra no código principal com teste vermelho. Os relatórios dessas revisões ficam públicos em `docs/state/reports/`.

**O que isso não garante.** Teste automático e revisão de IA pegam muita coisa, mas não tudo. Projetos feitos com IA costumam errar em detalhes de uso: janelas que não redimensionam, navegação e seleção estranhas, coisas que funcionavam e quebram depois. Por isso vamos ter testes de regressão específicos para isso (janela, zoom, seleção, atalhos) antes de qualquer versão utilizável, e queremos **revisão humana externa** das partes críticas.

**Para quem.** Para arquitetos que não podem pagar assinaturas caras de programas BIM, especialmente quem está começando e trabalha em cidades pequenas do Brasil, onde uma assinatura pode pesar até 20% da receita do ano. É por isso que o programa é aberto (AGPL-3.0), sem conta, sem nuvem e sem telemetria.

**O que ainda NÃO existe.** Não existe versão utilizável. Hoje há provas técnicas: abrir e mostrar modelos, selecionar peças, a ponte entre Python e C++ e medições de desempenho. Ainda não existe modelagem, nem pranchas, nem PDF, nem DXF, nem qualquer garantia de data. Também não existe, ainda, comunidade nem revisão externa. Se você quiser olhar o código e criticar, é bem-vindo: veja [CONTRIBUTING.md](CONTRIBUTING.md).

**Sistemas.** Windows e Linux: suportados. **macOS: melhor esforço, sem garantia**; o programa pode compilar lá, mas ninguém testa à mão e falhas lá não bloqueiam nada.
