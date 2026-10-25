# OpenBIM Studio

[English](README.en.md)

Programa BIM aberto e geral, com o IFC como verdade do modelo. O núcleo não é preso a nenhum país; o primeiro pacote regional, que define a versão 1.0, é o **Brasil**: projeto legal e executivo residencial no padrão ABNT. Outros países entram depois como pacotes regionais.

> O nome "OpenBIM Studio" é provisório.

## Estágio
**Fase 0: provas técnicas.** Ainda não existe versão utilizável. Nada aqui promete data de entrega.

## Transparência: quem faz, como e para quem

**Quem faz.** O OpenBIM Studio é um projeto de uma pessoa: Rafael, arquiteto, que define o que o programa precisa fazer e aceita (ou recusa) cada etapa. Ele não escreve código. O código é escrito por agentes de inteligência artificial (modelos Claude, da Anthropic), conduzidos por um "líder técnico", que também é uma IA. Não há, hoje, uma equipe de programadores experientes por trás.

**Como o código é feito.** Cada tarefa nasce de um cartão escrito, com critério de aceite. Quem escreve os **testes** é uma IA diferente da que escreve o **código**, e o código não passa se os testes dela não passarem. Partes delicadas (a ponte entre Python e C++, tarefas com várias linhas de execução, o salvamento dos arquivos) passam por uma **revisão cruzada** feita por um modelo mais forte, e só entram depois de aprovadas. Todos os testes rodam sozinhos, em Windows e Linux, a cada mudança; nada entra no código principal com teste vermelho. Os relatórios dessas revisões ficam públicos em `docs/state/reports/`.

**O que isso não garante.** Teste automático e revisão de IA pegam muita coisa, mas não tudo. Projetos feitos com IA costumam errar em detalhes de uso: janelas que não redimensionam, navegação e seleção estranhas, coisas que funcionavam e quebram depois. Por isso vamos ter testes de regressão específicos para isso (janela, zoom, seleção, atalhos) antes de qualquer versão utilizável, e queremos **revisão humana externa** das partes críticas.

**Para quem.** Para arquitetos que não podem pagar assinaturas caras de programas BIM, especialmente quem está começando e trabalha em cidades pequenas do Brasil, onde uma assinatura pode pesar até 20% da receita do ano. É por isso que o programa é aberto (AGPL-3.0), sem conta, sem nuvem e sem telemetria.

**O que ainda NÃO existe.** Não existe versão utilizável. Hoje há provas técnicas: abrir e mostrar modelos, selecionar peças, a ponte entre Python e C++ e medições de desempenho. Ainda não existe modelagem, nem pranchas, nem PDF, nem DXF, nem qualquer garantia de data. Também não existe, ainda, comunidade nem revisão externa. Se você quiser olhar o código e criticar, é bem-vindo: veja [CONTRIBUTING.md](CONTRIBUTING.md).

**Sistemas.** Windows e Linux: suportados. **macOS: melhor esforço, sem garantia**; o programa pode compilar lá, mas ninguém testa à mão e falhas lá não bloqueiam nada.

## O que o projeto quer ser
- Instalável no **Windows e no Linux**. macOS: melhor esforço, sem garantia.
- Foco da versão 1.0 (pacote Brasil): casa residencial, da modelagem às pranchas com carimbo, em PDF, DXF e IFC.
- Sem conta, sem nuvem, sem telemetria: seus arquivos são seus.
- Um projeto são **dois arquivos com o mesmo nome**: `Casa.ifc` (o modelo, limpo, abre em qualquer programa BIM) e `Casa.obim` (vistas, pranchas e cotas, num formato aberto).

## Licença
GNU Affero General Public License v3 ou posterior (AGPL-3.0-or-later). Texto completo em [LICENSE](LICENSE). Componentes de terceiros: [THIRD_PARTY.md](THIRD_PARTY.md).

## Para saber mais
- Resumo do plano: [v2/00_resumo_executivo.md](v2/00_resumo_executivo.md)
- Como contribuir: [CONTRIBUTING.md](CONTRIBUTING.md)
