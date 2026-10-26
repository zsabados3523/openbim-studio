# Como contribuir

[English](CONTRIBUTING.en.md)

Obrigado pelo interesse. O projeto está numa fase inicial de provas técnicas; antes de enviar algo, abra uma issue descrevendo a ideia.

## Rodar os testes
O ambiente é um ambiente conda chamado `openbim`, só com o canal conda-forge. Passo a passo em [docs/dev-setup.md](docs/dev-setup.md). Resumo:

```bash
conda env create -f environment.yml
conda activate openbim
QT_QPA_PLATFORM=offscreen pytest
```

O CI roda a mesma coisa em Linux e Windows; os dois precisam ficar verdes para o merge. Não envie código sem teste.

## Pesquisa só em fontes públicas
Para aprender como um recurso deve funcionar, use apenas:
- documentação pública e ajuda online de outros programas;
- normas abertas (IFC, IDS, BCF, bSDD) e código aberto com licença identificada;
- artigos e livros (só as ideias, sem copiar texto);
- testes de comportamento feitos por você com um programa que você possui legalmente e modelos seus.

**Não aceitamos:** engenharia reversa ou inspeção de binários e formatos proprietários (`.rvt`, `.rfa`, `.pln`, DWG por SDK fechado); SDKs fechados (ODA, RealDWG); ícones, telas, textos de ajuda ou marcas de outros programas; trechos de normas ABNT em código, documentos ou testes.

## Como escolher e entregar uma tarefa
1. Veja as [issues com o rótulo `tarefa`](../../issues?q=is%3Aopen+label%3Atarefa). Cada uma diz o objetivo, os arquivos que podem mudar, os testes que precisam passar e as decisões (ADRs) que valem.
2. Comente "pego essa" na issue e espere a confirmação, para duas pessoas não fazerem o mesmo trabalho.
3. Faça um fork, crie um ramo e implemente só o que a issue pede. PR com no máximo 400 linhas próprias; se passar, divida.
4. Abra o PR com o modelo preenchido. O CI (`linux` e `windows`) precisa ficar verde. A revisão é feita por quem mantém o projeto.
5. Tarefas do tipo **crítica** (gravação de arquivo, transações, junções) exigem que os testes sejam escritos por outra pessoa ou IA, não por quem implementa. A issue diz quem escreve os testes.
6. Ideia nova ou funcionalidade inspirada em outro software: abra primeiro uma issue "Ficha de pesquisa".

## Ficha de pesquisa
Toda funcionalidade inspirada em outro software precisa de uma ficha antes da proposta de implementação. Abra uma issue (ou escreva no texto do PR) com este modelo:

```
Funcionalidade: (nome curto)
Software de referência: (nome e versão, se houver)
Fontes consultadas: (links para documentação pública, norma aberta, código aberto com licença)
Como o recurso se comporta: (descrição com suas palavras, sem copiar texto nem tela)
O que NÃO foi feito: (confirme: sem engenharia reversa, sem SDK fechado, sem copiar ícones, telas ou textos de ajuda)
Licença de qualquer código que pretende reaproveitar: (SPDX ou "nenhum")
Decisão proposta: (o que implementar e o que ficar de fora)
```

## Licenças
- O projeto é AGPL-3.0-or-later. Só entra código de licença compatível: MIT, BSD, Apache-2.0, ISC, MPL-2.0, LGPL, GPL-3 e AGPL-3.
- **Não entram:** GPL-2.0-only, código sem licença, código proprietário, material CC-BY-NC ou CC-BY-ND.
- Todo código copiado leva um comentário com origem, licença e versão, e uma linha em [THIRD_PARTY.md](THIRD_PARTY.md).
- **Não aceitamos código de origem proprietária**, mesmo com boa intenção.

## Decisões de arquitetura
Mudanças que afetam a estrutura (processos, formato de arquivo, dependências) passam por um ADR em [docs/adr/](docs/adr/). Veja o índice para saber como propor um.

## Dados pessoais
Nunca envie projetos de clientes ou de terceiros ao repositório público.
