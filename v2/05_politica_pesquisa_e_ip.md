# 05. Política de pesquisa e propriedade intelectual

> Não é parecer jurídico. Em caso de dúvida concreta, consultar advogado de propriedade intelectual antes de publicar o conteúdo.

## 1. Regra formal (vale para PO e todos os agentes)
1. **Fontes permitidas para aprender como um recurso deve funcionar:**
   - documentação pública e ajuda online de Revit, ArchiCAD e outros (manuais, ajuda, vídeos oficiais, Revit API docs, manual GDL);
   - normas e especificações abertas: IFC (buildingSMART), IDS, BCF, bSDD, mvdXML;
   - código open source com licença identificada: IfcOpenShell/Bonsai, FreeCAD, Dynamo, That Open/web-ifc, xeokit, OCCT etc.;
   - artigos acadêmicos e livros (apenas ideias, não texto copiado);
   - **testes de comportamento**: o PO usa o software que licitamente possui com modelos próprios e descreve/filma o resultado.
2. **Proibido:**
   - engenharia reversa, decompilação, desmontagem, inspeção de binários ou de formatos proprietários (`.rvt`, `.rfa`, `.pln`, `.gsm` binário, DWG via SDK fechado), inclusive com ferramentas como "rea";
   - uso de SDKs/APIs proprietários com licença que restrinja (ex.: ODA, RealDWG) dentro do produto;
   - copiar ícones, telas, textos de ajuda, nomes de marca ou conteúdo de bibliotecas proprietárias (famílias Revit, objetos ArchiCAD);
   - copiar código de projeto sem licença ou com licença incompatível com AGPL v3;
   - colar trechos de normas ABNT em código, docs, testes ou mensagens de agentes.
3. **Toda funcionalidade inspirada em outro software precisa de uma ficha de pesquisa** em `docs/research/` antes da especificação. O revisor recusa especificação sem ficha.
4. Interface: imitar **conceitos e fluxos** (níveis, vistas, tipos, pranchas, propriedades) é permitido; copiar **aparência específica** (ícones, layout idêntico, nomes comerciais) não.

## 2. Modelo de ficha de pesquisa (`docs/research/AAAA-MM-DD-<tema>.md`)
```markdown
# Ficha de pesquisa: <tema> (ex.: Join de paredes com camadas)
- Autor: <agente/PO> · Data: <AAAA-MM-DD> · Fatia relacionada: <F2-S04>
## Pergunta
O que o usuário espera que aconteça? (1–3 frases)
## Fontes consultadas
| # | Fonte | Tipo (doc pública / código aberto / norma aberta / teste de comportamento) | URL ou referência | Licença | Data de acesso |
## O que aprendemos (com nossas palavras, sem copiar texto)
## Comportamento de referência (testes do PO, se houver)
- Modelo usado (do PO), passos, resultado observado, capturas próprias
## Código aberto lido
- Projeto, arquivo, licença; reaproveitado? (não / ideia / código com atribuição)
## Decisão para o OpenBIM Studio
## Riscos de IP identificados (nenhum / descrever)
## Revisado por: <papel> em <data>
```

## 3. Reaproveitamento de código aberto
| Licença de origem | Pode entrar no nosso código AGPL v3? | Condição |
|---|---|---|
| MIT, BSD, Apache-2.0, ISC, MPL-2.0 | sim | Manter aviso de copyright; MPL: arquivos MPL continuam MPL |
| LGPL-2.1+/3, GPL-3, AGPL-3 | sim | Atribuição; GPL-2.0-*only* **não** é compatível com AGPL-3 |
| GPL-2.0-only | **não** | Usar só como referência de ideia |
| Sem licença / proprietário | **não** | Nem como base |
| CC-BY (dados, ícones) | sim, com atribuição | CC-BY-NC/ND: **não** |

Todo código copiado: comentário com origem, licença e commit; registro em `THIRD_PARTY.md`. Ferramenta de checagem de licenças (ex.: REUSE/SPDX) no CI a partir da F0.

**Checagem de licenças das dependências (F0-S01):** a Revisão 2 verificou na web (detalhes e fontes em `07` §1): IfcOpenShell LGPL-3.0-or-later; Bonsai GPL-3.0-or-later (só referência); OCCT **LGPL-2.1-only** + Open CASCADE Exception 1.0; PySide6 LGPLv3/GPLv2/GPLv3 ou comercial (evitar módulos comerciais); pythonocc-core LGPL (3 segundo distribuições); ezdxf MIT; LibreDWG GPL-3.0-or-later; libslvs GPL-3 (via SolveSpace); web-ifc MPL-2.0. **Atenção:** libdxfrw tem licença disputada (GPLv2 ou LGPLv2+); se for GPLv2-only é incompatível. Ainda não verificados: nanobind/pybind11 (esperado BSD), PlaneGCS (esperado LGPL). A F0-S01 reconfirma tudo pelo arquivo LICENSE da versão fixada.

## 4. Política de conteúdo: normas e bases brasileiras
| Conteúdo | Status | O que fazemos | O que NÃO fazemos |
|---|---|---|---|
| Normas ABNT (NBR 6492, 16861, 16752, 9050, 15575, 12721, 13532 etc.) | Protegidas por direito autoral; venda pela ABNT | Implementamos **mecanismos configuráveis** (espessuras, formatos de folha, campos de carimbo, regras de verificação parametrizadas). Valores padrão são **escolhas do projeto**, descritos como "inspirado em prática corrente", ou inseridos pelo usuário a partir da norma que possui. Citar o número da norma como referência é permitido | Copiar texto, tabelas, figuras ou trechos; distribuir PDFs; dizer "certificado ABNT" |
| NBR 15965 (classificação) | Protegida | Suporte a qualquer sistema de classificação carregável (arquivo do usuário). Pesquisa de 2026-10-10 não achou distribuição aberta nem carga no bSDD; existe planilha pública da CAIXA de correspondência SINAPI × NBR 15965 (avaliar termos) **[verificado em 2026-10-10; `07` §2]** | Embutir as tabelas sem licença confirmada |
| Layers AsBEA | Material da associação | Mapa de layers configurável; template padrão com nomes próprios. Usuário pode importar seu próprio mapa | Distribuir arquivos/manuais AsBEA |
| SINAPI (CAIXA/IBGE) | Publicados por obrigação legal (Decreto 7.983/2013); **termos de redistribuição não encontrados** **[não verificado: página da CAIXA inacessível em 2026-10-10]** | Importar planilha baixada pelo próprio usuário; registrar mês/UF/fonte; consulta formal à CAIXA antes da F5 | Distribuir planilhas SINAPI com o programa ou no repositório (até haver termos claros); apresentar como orçamento oficial |
| TCPO | Proprietário (editora) | Somente importação de arquivo do usuário licenciado | Distribuir |
| Códigos de obras municipais | Leis públicas | Parâmetros por município fornecidos pela comunidade, com fonte | — |
| Bibliotecas de fabricantes | Variam | Só com licença explícita de redistribuição | Converter famílias Revit/objetos ArchiCAD |

## 5. Dados do PO e privacidade
- Projetos do PO usados como gabarito ficam **fora do repositório público** salvo autorização escrita no chat.
- Nunca enviar projetos do PO a serviços online (incluindo validador web) sem autorização; usar validação local.
