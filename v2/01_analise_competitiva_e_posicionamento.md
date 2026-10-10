# 01. Análise competitiva e posicionamento

> Status das afirmações (Revisão 2): itens marcados **[verificado em 2026-10-10]** foram checados na web; fontes e ressalvas em `07_verificacoes_web.md`. Licenças e capacidades mudam; a F0-S01 reconfirma com o arquivo LICENSE.

## 1. Pergunta central
Por que um arquiteto (a 1.0 mira o brasileiro, primeiro pacote regional) usaria o OpenBIM Studio em vez de (a) Revit/ArchiCAD pagos, (b) Bonsai (Blender) gratuito, (c) FreeCAD BIM gratuito?

Resposta proposta: **porque é o único programa gratuito, instalável como um programa normal no Windows e no Linux, que entrega pranchas de projeto legal e executivo residencial no padrão brasileiro, com fluxo de trabalho familiar a quem vem do Revit/ArchiCAD, e grava IFC limpo.** Nenhum concorrente aberto reúne os quatro pontos hoje.

## 2. Mapa dos concorrentes

| Produto | Licença (a confirmar) | Pontos fortes | Lacunas para o nosso público |
|---|---|---|---|
| **Bonsai** (ex-BlenderBIM), sobre IfcOpenShell | GPL-3.0-or-later (add-on), IfcOpenShell LGPL-3.0-or-later **[verificado em 2026-10-10]**. Versão na Blender Extensions: 0.8.5-post1 (abr/2026); 0.9 anunciada | IFC nativo mais completo do mundo aberto; ifcopenshell.api; desenhos via IfcAnnotation + `SvgSerializer`, com layout de prancha em SVG e estilo em CSS fora do IFC; IDS, BCF, clash, custos, 4D | Depende do Blender (0.8.5 sem suporte a Blender 5.1+): interface de modelagem 3D genérica, curva de aprendizado alta para arquiteto Revit/ArchiCAD; desempenho com modelos grandes limitado pela pilha Python/Blender **[não verificado: exige benchmark próprio]**; pranchas exigem ajuste manual; sem conteúdo ABNT |
| **FreeCAD BIM** (workbench BIM, FreeCAD 1.x) | LGPL-2+ | Programa dedicado e multiplataforma; OCCT; paramétrico via Sketcher; TechDraw para desenhos; NativeIFC desde a 1.0; **FreeCAD 1.1 (mar/2026)** trouxe objetos 2D nativos em IFC (linhas, textos, cotas), ferramenta Drawing View e painel BIM Views com pranchas **[verificado em 2026-10-10]** | Modelo interno não é IFC por padrão (NativeIFC ainda marcado como "em andamento" na wiki); fluxo de arquiteto lento; desenhos 2D trabalhosos; problema histórico de "naming topológico" (melhorou na 1.0); sem ABNT |
| **That Open Company** (web-ifc, Components) | MPL-2.0 (web-ifc) **[verificado em 2026-10-10]** | Leitura/visualização IFC muito rápida no navegador; base para apps web | É biblioteca/plataforma web, não um autor de projeto completo; sem documentação 2D madura |
| **Speckle** | Apache-2.0 (servidor; conectores variam) **[verificado em 2026-10-10]** | Troca de dados entre softwares, versionamento na nuvem | Não é ferramenta de autoria; depende de servidor |
| **xeokit / IFC.js viewers, BIMvision** | variadas | Visualização | Só visualização |
| **Revit / ArchiCAD** (referência, não concorrente direto em preço) | proprietários | Fluxo maduro de documentação, famílias/GDL, colaboração, conteúdo | Caros; Revit sem Linux/Mac; IFC é exportação, não nativo |
| **Outros abertos menores** (ex.: Sverchok/IfcSverchok, BlenderBIM forks, OpenBIM experimentais) | variadas | nichos | Sem foco em documentação brasileira |

## 3. Análise de lacunas: onde existe espaço real

| Necessidade do arquiteto BR residencial | Revit | ArchiCAD | Bonsai | FreeCAD BIM | **Nós (1.0)** |
|---|---|---|---|---|---|
| Instalar como programa comum no Windows | sim | sim | via Blender | sim | **sim (requisito)** |
| Linux e Mac | não / não | não / sim | sim | sim | **Linux sim; Mac pós-1.0** |
| Gratuito e aberto | não | não | sim | sim | **sim** |
| Fluxo "nível, vista, tipo, prancha" | excelente | excelente | parcial | parcial | **foco principal** |
| Planta/corte/fachada gerados do modelo com gráfico ABNT | configurável | configurável | possível, manual | possível, manual | **pronto no template BR** |
| Quadro de áreas, esquadrias, quantitativos | sim | sim | sim (técnico) | parcial | **sim, pronto para prefeitura** |
| IFC como arquivo nativo | não | não | **sim** | parcial | **sim** |
| SINAPI | plugins pagos | plugins | não | não | **vínculo básico 1.0, completo 2.0** |
| Famílias paramétricas completas | excelente | GDL | parcial | Sketcher | **simples na 1.0, completo 2.0** |
| Colaboração | worksharing | Teamwork | git/IFC | não | **2.0** |

**Diferencial competitivo em ordem de força** (o que defendemos):
1. **Documentação regional pronta, começando pelo Brasil** (template, carimbo, gráfico por categoria, quadro de áreas, pranchas legais). Ninguém aberto faz; é onde o arquiteto perde mais tempo.
2. **UX de arquiteto** (ferramentas de parede/laje/esquadria, cotas temporárias, navegador de projeto, propriedades), em vez de um modelador 3D genérico.
3. **Programa dedicado no Windows e no Linux** com instalador normal (Mac depois).
4. **IFC nativo e limpo** validado continuamente (documentação em arquivo lateral aberto, nunca poluindo o IFC).
5. **Desempenho** aceitável em modelos residenciais e médios (não prometemos superar Revit em modelos gigantes).

**Diferencial que NÃO reivindicamos na 1.0:** famílias melhores que Revit, colaboração melhor que Teamwork, renderização, estrutura/instalações.

## 4. Coopetição: aproveitar o ecossistema em vez de competir com ele
- **IfcOpenShell é dependência, não concorrente.** Usamos ifcopenshell.api (mesma base do Bonsai). Correções de bugs em IfcOpenShell devem ser enviadas de volta ao projeto (upstream): reduz manutenção e cria boa relação.
- **Bonsai é a melhor referência pública de "como guardar X em IFC"** (tipos, materiais, quantidades). Para vistas e pranchas, a decisão do PO (Revisão 2) é **não** gravá-las no IFC: o IFC sai limpo e a documentação vai para o `.obim` (`02` §6). Consequência aceita: o Bonsai abre nosso modelo, mas não nossas vistas. Uma exportação opcional "vistas como IfcAnnotation no estilo Bonsai" fica para 2.0. Observação da pesquisa: o próprio Bonsai mantém o layout de prancha no SVG, fora do IFC **[verificado em 2026-10-10]**.
- **Ler o código aberto é permitido** (é a regra de pesquisa); copiar código GPL para dentro do nosso AGPL é compatível juridicamente, mas deve ser registrado com atribuição (ver `05`).

## 5. Público-alvo
- **Primário (1.0, pacote regional Brasil):** arquiteto ou pequeno escritório brasileiro (1 a 5 pessoas) que faz residências unifamiliares e pequenas multifamiliares, hoje usa AutoCAD/SketchUp ou Revit/ArchiCAD pirata ou com custo pesado, e precisa aprovar projeto na prefeitura e entregar executivo.
- **Secundário:** estudantes e professores de arquitetura (Linux/Mac, sem licença), consultores BIM que precisam de IFC limpo.
- **Fora do público na 1.0:** grandes escritórios com fluxos de worksharing, engenharia estrutural/MEP, infraestrutura (IFC 4.3 infra).

## 6. O que NÃO fazer
1. Não tentar paridade de recursos com Revit. Cada recurso precisa ligar-se a uma prancha de projeto residencial.
2. Não ser "mais um visualizador IFC": o visualizador é etapa, não produto.
3. Não reimplementar o que IfcOpenShell já faz bem (parsing, esquema, api, geometria IFC, quantidades).
4. Não criar formato proprietário paralelo ao IFC.
5. Não prometer colaboração em tempo real antes de o modelo de dados ter provado estabilidade em uso individual.
6. Não redistribuir conteúdo protegido (textos ABNT, bibliotecas de fabricantes sem licença).
7. Não começar pelo editor de famílias: é caro e o conteúdo inicial pode ser feito por tipos paramétricos simples.
8. Não buscar engenharia reversa de formatos `.rvt`/`.pln`.

## 7. Riscos competitivos
| Risco | Sinal | Resposta |
|---|---|---|
| Bonsai melhora UX e pranchas rapidamente | Lançamentos com "drawing/sheet" muito mais fluido | Nosso diferencial passa a ser ABNT + instalador dedicado + desempenho; avaliar contribuir com Bonsai em vez de duplicar |
| FreeCAD NativeIFC amadurece | FreeCAD 1.1 já tem 2D nativo em IFC e painel de pranchas (sinal ativo em 2026) | Mesmo raciocínio; manter foco BR/UX; reavaliar no portão F0 |
| Autodesk/Graphisoft baixam preço no Brasil | Planos regionais mais baratos | Liberdade, Linux/Mac e IFC nativo continuam diferenciais |

**Gatilho estratégico (revisar a cada portão):** se ao fim da F0 ou F1 ficar claro que um concorrente aberto já entrega 70%+ do diferencial 1 e 2, o PO decide entre continuar, ou redirecionar o esforço para um "pacote Brasil" sobre o Bonsai/FreeCAD (plano B de menor custo).
