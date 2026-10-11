# Relatório do lote Opus 2: licenças e empacotamento
- Data: 2026-10-11 · Papel: Arquiteto/Revisor crítico (opus) · Pedido: `docs/state/LOTE_OPUS_2.md`
- Feito sem rede e sem instalar nada. **Não é parecer jurídico**: é leitura técnica de licenças por quem não é advogado.
- Além dos arquivos do pedido, olhei três coisas locais, só leitura, porque o adendo pedia conferir o `REMOVIDOS.md` gerado: o AppImage já extraído em `/tmp/appimage_extracted_…` (montagem de 2026-10-10 17:45, poda de 139 pacotes), as pastas `info/licenses` de cinco pacotes no cache do conda (occt, qt6-main, pyside6, ifcopenshell, tbb-devel) e a lista de exceções SPDX dentro do ambiente `reuse`. O instalador Windows não foi aberto (só existe no CI); o que digo dele vem da leitura dos scripts.

## Resultado por item
| Item | Objeto | Resultado |
|---|---|---|
| 1 | Tabela mestre v2 (S01-T11) | **APROVADA**, 12 de 12 defeitos corrigidos. `THIRD_PARTY.md`: 1 ajuste. `F0-S01.md`: desatualizado, 3 ajustes. Detalhe em `docs/research/2026-10-10-licencas-revisao-opus.md` (seção final) |
| 2 | `v2/05` §3 | **APROVADO**; bate com o ADR-009. 4 observações |
| 3 | AppImage P1 (S02-T10) | **REPROVADO**, 7 defeitos (nenhum pede refazer a montagem) |
| 3b | Instalador Windows (S02-T11, adendo) | **REPROVADO**, 4 defeitos; o CI verde continua valendo como prova de que instala, abre e desinstala |
| 4 | Sonda C++ (S02-T16) | Amostra **aprovada**. Fecha os testes 2 e 3 **só no Linux**; ADR-005 atualizado |
| 5 | CI e inventário | Feito; 1 defeito que impede fechar o teste 9, mais riscos listados. Exceção do `tbb-devel`: **aceitável** |

## Item 1: tabela mestre
Aprovada. O identificador `OCCT-exception-1.0` foi **conferido** (existe na lista SPDX que a ferramenta REUSE traz). Achado novo: o pacote `occt` do conda-forge não traz o texto dessa exceção; ver item 3, defeito 2.
A fazer pelo líder (mecânico, T0, sem voltar ao opus): 4 observações na tabela, 1 ajuste em `THIRD_PARTY.md`, 3 em `F0-S01.md`. Depois disso a S01 pode ser fechada.

## Item 2: `v2/05` §3
**Aprovado.** As três mudanças pedidas pelo ADR-009 §6 estão no texto e não contradizem o ADR:
- linha "LGPL-2.1-only": só como biblioteca ligada dinamicamente, sem modificação; copiar código, não (igual ao ADR-009 §4.2 e §5.1);
- linha "GPL-3 ou posterior": combinação pela seção 13, a parte GPL continua GPL-3 (igual ao §4.2);
- nota da libdxfrw: corrigida e com a decisão "fica fora" (igual ao §5.2).

Observações (não bloqueiam; o líder propõe, o PO aprova, como antes):
1. O parágrafo "Checagem de licenças" ainda diz "ainda não verificados: nanobind/pybind11, PlaneGCS". Já foram verificados (BSD-3-Clause; LGPL-2.1-or-later).
2. A primeira linha da tabela não cita BSL-1.0 (Boost), que o ADR-009 §4.2 permite. Acrescentar.
3. A libslvs aparece como exemplo de "GPL-3 ou posterior", mas a tabela mestre diz que o "ou posterior" dela só está no README. Trocar o rótulo da linha para "GPL-3 (só 3 ou posterior)".
4. Lacuna que existe **também no ADR-009**: os dois textos dizem que código GPL-3 pode ser copiado para os nossos arquivos, mas não dizem que o arquivo que recebe a cópia passa a levar a etiqueta GPL-3 (como já está dito para MPL). Sugiro a frase "arquivo com código GPL-3 copiado continua GPL-3, com etiqueta SPDX própria" nos dois. Não mexi no ADR-009 (fora dos meus arquivos permitidos).

## Item 3: AppImage P1 (S02-T10): REPROVADO
### O que está certo (conferido na imagem extraída)
- **Bibliotecas LGPL em arquivos separados:** sim. Modo pasta, Qt, OCCT e IfcOpenShell como `.so` em `env/lib`, nada estático (os `.a` são apagados), nenhum executável único.
- **Sem trava contra troca:** sim. Não há conferência de hash nem de assinatura.
- **`PYTHONHOME` fixo no `AppRun`: não atrapalha a troca.** Ele aponta para a pasta `env/` ao lado do próprio `AppRun`, que é justamente onde o usuário troca os arquivos; serve para o programa não pegar o Python do sistema. Vale tanto montado quanto na pasta extraída. Único cuidado técnico, sem relação com licença: a variável é herdada por programas que o app venha a chamar; quando o app passar a chamar programas externos, limpar a variável antes.
- **`LGPL-COMO-TROCAR.md`: as instruções funcionam** (extrair, trocar o arquivo de mesmo nome, testar pelo `AppRun`, remontar ou usar a pasta). Os caminhos conferem com a imagem.
- **A poda apagou o que disse que apagou:** dos 14.716 arquivos dos 139 pacotes removidos, sobraram 0. Não há `libav*`, `libx264`, `libx265` nem `libvtk*` no pacote.

### Defeitos (numerados; todos de correção curta)
1. **Faltam os textos de licença de quase todos os pacotes.** `licenses/pacotes/` tem só 6 pastas (gcc-libs, libgfortran, libstdc++, sdl2-compat, SDL3, VTK), porque o script copia `env/share/licenses`, que quase nenhum pacote conda usa. Ficam sem aviso os 152 pacotes distribuídos, entre eles Qt, PySide6, OCCT, IfcOpenShell e Python. O ADR-009 §5.3 (item 3) exige os textos. Correção: usar no Linux o mesmo `scripts/collect_package_licenses.py` que o Windows já usa (os textos estão no cache do conda, em `info/licenses` de cada pacote; conferi occt, qt6-main, pyside6 e ifcopenshell).
2. **Falta o texto da exceção do OCCT**, no AppImage e no instalador Windows. O pacote `occt` traz só `LICENSE_LGPL_21.txt`. É condição expressa do ADR-009 §5.1. Correção: pôr `LICENSES/OCCT-exception-1.0.txt` no repositório e copiá-lo para `licenses/`. Obter o texto oficial é ação de rede: pede ok do PO (pergunta 2).
3. **Os textos da LGPL-3, LGPL-2.1 e GPL-3 vêm da máquina que monta** (`/usr/share/common-licenses`), com `|| true`: fora de Debian/Ubuntu eles somem sem aviso. Correção: guardar os três textos em `LICENSES/` do repositório, copiar de lá e falhar se faltar. O instalador Windows hoje não leva esses três na raiz de `licenses/`.
4. **Nenhum teste automático cobre as obrigações de licença no Linux.** O job `appimage` só roda o autoteste e mede o tamanho. O teste 8 do ADR-005 pede também: `licenses/` presente, `--appimage-extract` funciona, abre com um `.so` do Qt trocado. Acrescentar ao job: presença de `licenses/AGPL…`, LGPL-3, LGPL-2.1, GPL-3, exceção do OCCT, `INVENTARIO.md`, `REMOVIDOS.md`, `FONTES.md`, `LGPL-COMO-TROCAR.md`; texto da LGPL dentro de `pacotes/`; troca de um `.so` na pasta extraída seguida do autoteste; e ausência de `libav*`, `libx26*` e `libvtk*`.
5. **Resíduo `libTKIVtk`.** Ficam 3 arquivos (`libTKIVtk.so`, `.so.8.0`, `.so.8.0.1`) que não carregam: faltam 11 bibliotecas do VTK. Também ficam três pastas vazias (`lib/vtk-9.7`, `site-packages/vtkmodules`, `vtk-9.7.0.dist-info`). Não é problema de licença (é código do próprio OCCT), mas é uma biblioteca quebrada dentro do pacote e confunde qualquer ferramenta que confira dependências. Correção: apagar `libTKIVtk*` e as pastas vazias na montagem e dizer isso no `REMOVIDOS.md` ("arquivo do pacote occt retirado"). Retirar um arquivo não é "modificar o OCCT" no sentido do ADR-009.
6. **A poda tirou mais do que o PO decidiu, sem registro.** A decisão foi "podar vtk/viskores" (opção 1 da ficha) e depois o ffmpeg. O fechamento de dependências levou junto o Mesa (`mesalib`, `mesa-libgallium`, `mesa-llvmpipe`, `mesa-lavapipe`), que era a **opção 4** da ficha, marcada "risco de quebrar a renderização por software do Qt; não testado". Efeito provável: em máquina sem driver de vídeo funcionando (máquina virtual, acesso remoto), o programa passa a depender do Mesa do sistema. Pode ser aceitável (é o costume em AppImage), mas é decisão do PO e precisa de teste (pergunta 1). Também saíram openvino, hdf5, proj, pillow, libcurl e pulseaudio; nenhum pacote mantido declara precisar deles.
7. **Ficha e relatório descrevem a poda antiga.** `docs/research/2026-10-10-appimage-p1.md` e `F0-S02-appimage.md` falam na variável `PODA_PADROES` e em 565 MB; o script atual usa `prune_packages.py` (139 pacotes) e o tamanho novo não está registrado. Atualizar os dois, com a lista do que saiu e o tamanho medido no CI.

### Antes da primeira publicação pública (não bloqueia a prova P1)
8. **`FONTES.md` promete o que ainda não existe.** (a) Diz que "o código-fonte exato é mantido junto da publicação": nada faz isso hoje. (b) O endereço modelo `<nome>-feedstock` está errado para pacotes que saem de uma receita com outro nome (qt6-main, libgcc, libstdcxx e outros). (c) A oferta escrita não tem prazo; a LGPL 2.1 pede validade de 3 anos. Correção: gerar, para os pacotes LGPL e GPL que ficam no pacote, uma tabela com nome, versão, build e endereço do fonte original (cada pacote conda guarda a receita usada em `info/recipe`), guardar cópia dos fontes junto do release e escrever "válida por 3 anos".
9. **Os artefatos do CI já são distribuição.** O repositório é público e os jobs `appimage` e `windows` publicam o AppImage e o instalador como artefatos, que qualquer pessoa com conta no GitHub baixa. Enquanto os defeitos 1 a 3 e o 8 não forem corrigidos, esses arquivos saem sem os avisos completos (pergunta 3).
10. Não existe a tela "Sobre > Licenças de terceiros" (ADR-009 §5.3, item 3). Normal num app esqueleto; precisa de cartão antes do primeiro release público.

### Observações
11. `INVENTARIO.md` lista os 291 pacotes e só avisa no rodapé que 139 saíram. Melhor uma coluna "vai no pacote: sim/não".
12. `LGPL-COMO-TROCAR.md`: trocar "bibliotecas do sistema" por "bibliotecas do programa"; dizer que sem tela o teste pede `QT_QPA_PLATFORM=offscreen`; citar o terceiro caminho (recompilar pelo código-fonte).
13. Fato preexistente, que não vem da poda: 25 módulos do PySide6 (Charts, Multimedia, 3D, WebEngine, Pdf e outros) não carregam porque o `qt6-main` não traz as bibliotecas Qt correspondentes. Não afeta o app hoje (QPdfWriter fica no QtGui). Registrar no ADR-005: quem precisar de um desses módulos tem de acrescentar o pacote Qt e refazer o inventário.
14. Ficam no pacote ferramentas de compilação que o app não usa (`ld_impl_linux-64`, pacotes `-devel`, libclang de 148 MB). Licença em ordem; é só tamanho.

### Os avisos de licença do que foi removido precisam ficar?
**Não.** Aviso de licença acompanha o que é distribuído; do que não vai no pacote, não há obrigação. Mantê-los "por cortesia" não faz mal. Duas ressalvas: o texto da licença do VTK deve ficar enquanto `libTKIVtk` ficar (ela foi compilada com cabeçalhos do VTK); apagada a biblioteca (defeito 5), ele também pode sair. E a poda **não deixa aviso incompleto por si só**: o aviso incompleto vem do defeito 1, que atinge os pacotes que ficaram.

### A poda por fechamento de dependências é segura e suficiente?
- **Segura quanto ao que os pacotes declaram: sim.** Conferi na imagem: o único pacote mantido que declara depender de algo removido é o `occt` (do `vtk`), e a única biblioteca que ficou quebrada por causa da poda é `libTKIVtk`. O critério do script (só remove um pacote se todos os que dependem dele saem) está correto.
- **Três limites do script:** (i) as raízes informadas são removidas sem conferir quem depende delas; o script deve listar os pacotes mantidos que ficaram com dependência removida e falhar se a lista for diferente da esperada (hoje, só `occt`); (ii) ele só enxerga dependência declarada; o que um pacote carrega sem declarar passa despercebido, então o teste do defeito 4 e o teste com geometria real da S04 continuam necessários; (iii) ele remove mais do que se imagina (defeito 6): o `REMOVIDOS.md` deve ser lido a cada mudança de versão.
- **Suficiente quanto à GPL: sim.** ffmpeg, x264 e x265 saíram. O que resta com GPL é compatível com a AGPL v3: readline (GPL-3, usada pelo Python; seção 13), bibliotecas de apoio do GCC (GPL-3 com exceção própria), FreeImage e FreeType e GMP e dbus (licença dupla, escolhemos a opção compatível), CGAL (compilado dentro do IfcOpenShell; seção 13). Nenhum pacote mantido é só GPL-2.0. Bibliotecas "LGPL-2.1-only" além do OCCT: geos, libiconv, libnsl, libraw, sob as mesmas condições do OCCT. Essa conferência foi feita por mim, à mão: o CI ainda não a faz (item 5, defeito 1).

### Parecer: appimagetool vindo da tag móvel `continuous`, sem checksum
Para um experimento local que nunca foi publicado, aceitável. Para o CI e para qualquer release, não: uma tag móvel muda sem aviso e, sem checksum, não se sabe o que montou o pacote. O CI já corrige isso (versão 1.9.1 com sha256 conferido), e está bom. Dois complementos: (1) o sha256 foi calculado por nós no primeiro download, então ele garante "é o mesmo arquivo de sempre", não "é o arquivo que o autor publicou"; basta para a F0. (2) **De memória, a conferir:** o appimagetool atual baixa da internet, na hora de montar, o pequeno programa de partida que vai **dentro** do nosso AppImage (o "runtime"), também de uma tag `continuous`. Se for isso mesmo, essa peça entra no nosso pacote sem versão fixa e sem aviso de licença. Correção: baixar o runtime numa versão fixa, conferir o sha256 e passá-lo ao appimagetool com `--runtime-file`; registrar a licença dele (MIT, com bibliotecas embutidas a verificar) no inventário.

## Item 3b: instalador Windows (S02-T11): REPROVADO
O que está certo: NSIS como ferramenta (licença zlib, não se mistura com a AGPL); instalação por usuário sem administrador (`RequestExecutionLevel user`, pasta em `%LOCALAPPDATA%\Programs`, registro só em `HKCU`); DLLs em arquivos separados; o lançador não confere hash; coleta dos textos de licença por pacote, com teste que procura o texto da LGPL; o CI instala, abre e desinstala sem sobras.

Defeitos:
1. **Risco de apagar arquivos do usuário na desinstalação.** O desinstalador faz `RMDir /r "$INSTDIR"` (apaga a pasta inteira). Se a pessoa digitar como destino uma pasta que já tem coisas (por exemplo "Documentos"), a desinstalação apaga tudo. A proteção atual (existir `app\OpenBIM-Studio.pyw`) não evita isso. Correção: apagar só o que o instalador criou (`env\`, `app\`, `licenses\` e os arquivos soltos conhecidos) e depois remover a pasta apenas se estiver vazia.
2. **O isolamento do Python não funciona no Windows.** O lançador define `PYTHONNOUSERSITE` depois que o Python já iniciou, quando não tem mais efeito, e herda `PYTHONPATH` e `PYTHONHOME` do usuário. Quem tiver PySide6 ou ifcopenshell instalados no Python pessoal pode carregar uma segunda cópia do Qt ou do IfcOpenShell (o tipo de problema do risco R1). O teste do CI usa ambiente limpo e não pega. Correção: atalho com `pythonw.exe -I` (modo isolado) e um teste com essas variáveis "sujas".
3. **O teste 7 do ADR-005 está incompleto.** Faltam: abrir com uma DLL do Qt trocada; instalar por cima de uma versão anterior (hoje a extração mistura arquivos velhos e novos; limpar `env\` e `app\` antes); medir instalação (meta 5 min) e primeira abertura (meta 10 s) com falha se passar.
4. Textos de licença: os mesmos defeitos 2 e 3 do AppImage (exceção do OCCT; LGPL-3, LGPL-2.1 e GPL-3 na raiz de `licenses\`).

Riscos e observações:
5. **`tar.exe` do Windows na extração.** Existe no Windows 10 (desde 2018) e no 11; o CI prova no Windows Server 2025. A conferir no teste do PO (T14): Windows 10 real; caminhos longos (usuário com nome comprido somado às pastas fundas do ambiente pode passar de 260 caracteres); antivírus deixando a extração lenta. Faltam: barra de progresso durante a extração (a janela parece travada por minutos), checagem de espaço em disco (`AddSize`) e limpeza se a extração falhar no meio.
6. **NSIS do conda-forge sem versão fixa** (`conda create nsis`, pega a mais recente). Fixar versão e build, como foi feito com o appimagetool. O mesmo vale para `reuse` e `miniforge-version: latest`.
7. O Windows usa `packaging/linux/runtime-environment.yml`. Mover para `packaging/` e, de preferência, gerar arquivo de trava também do ambiente de runtime e para win-64.

## Item 4: sonda C++ (S02-T16): amostra aprovada
- **Teste 2 (o que vem no pacote do IfcOpenShell): fechado no Linux, aberto no Windows.** As quatro respostas são "sim" e a evidência é boa: cabeçalhos presentes; bibliotecas compartilhadas `libifcopenshell.parse/geometry`; nenhum `.a`; e o módulo Python declara precisar dessas bibliotecas e não define nenhum símbolo `ifcopenshell::file` próprio. Mas a meta do teste é "por sistema". **O Windows é o caso duvidoso** (de memória, a conferir: no Windows o IfcOpenShell costuma ser compilado como biblioteca estática, e aí o módulo Python embute a própria cópia, que é o risco R1). É só leitura e cabe num passo do job `windows`: listar `Library\include\ifcparse`, as `.lib` e `.dll` do IfcOpenShell e as dependências do `_ifcopenshell_wrapper*.pyd`. **Fazer antes de abrir a S04.**
- **Teste 3 (módulo nanobind + OCCT + Qt): passa no Linux local; não fecha.** Faltam o Windows e o tempo de criar o ambiente, que a meta de 60 min inclui. E 2,4 s medem um módulo de 17 linhas: não dizem nada sobre o custo real (a própria ficha reconhece). Complemento barato, classe T2: uma sonda "3b" que inclua `ifcparse/file.h` e ligue em `libifcopenshell.parse` usando o `IfcOpenShellConfig.cmake` do pacote, sem trocar dados com o Python. Mede o tempo de compilar os cabeçalhos pesados e mostra cedo se falta algum cabeçalho de terceiros.
- **`ifcopenshell::file` muda o teste 5?** Não muda o que se prova (verificações a até g ficam). Muda o texto da especificação e acrescenta cuidados: nomes novos de classes, cabeçalhos e bibliotecas; a API C++ da 0.9 foi reorganizada, então a versão **e o build** do pacote ficam travados; e a especificação T3 tem de ser escrita lendo os cabeçalhos instalados, não a documentação antiga.

### O que a S04 deve provar (resumo; detalhe no ADR-005 §7)
1. Teste 5 inteiro, a até g, nos dois sistemas, com os nomes da 0.9.
2. Como o C++ recebe o modelo que o Python abriu, sem cópia, e **quem é dono dele**: o objeto Python continua dono; o C++ só pega emprestado; o teste tem de mostrar que nada quebra quando o Python fecha o arquivo.
3. Uma cópia só de cada núcleo (IfcOpenShell e OCCT) no processo; no Windows isso depende do teste 2.
4. Mesmo compilador e mesmo modo de compilação do pacote (no Windows, nunca "Debug").
5. Uso com threads e desempenho da ponte, que o teste 5 deixa de fora.
6. Com o pacote já podado (sem VTK): geometria real, não só uma parede.
Especificação e oráculo: opus (T3). Implementação: sonnet. Revisão: opus, em lote.

## Item 5: CI, inventário de licenças
1. **Defeito: o inventário não compara com uma lista de licenças permitidas.** O ADR-009 §7 (item 2) e o teste 9 do ADR-005 pedem isso; `license_inventory.py` só barra licença vazia e canal errado. Exemplo real: o pacote `cuda-version`, que declara um contrato proprietário da NVIDIA, passa sem aviso (é só um marcador, sem arquivos, e sai na poda; mas mostra o furo). Correção: lista de licenças permitidas no script, com as exceções nomeadas uma a uma, rodando sobre os pacotes **que ficam** no instalador. Até lá o teste 9 não fecha.
2. **Exceção do `tbb-devel`: aceitável.** O metadado está vazio, mas o próprio pacote traz o arquivo de licença (Apache 2.0, conferido no cache), e ele sai da mesma receita do `tbb`. Condições: amarrar a exceção à versão (2023.1.0), para ser reconferida quando mudar; e trocar a justificativa por "arquivo de licença do próprio pacote". Ele nem vai nos pacotes (sai na poda).
3. **Cache de pacotes do conda.** A chave usa os arquivos `.yml`, que só fixam cinco versões; o resto flutua. Com a chave igual, o cache nunca é regravado e vai ficando velho, e o tempo de "build limpo" medido com cache não é limpo (armadilha já escrita no cartão T06). Sugestão: incluir o arquivo de trava ou a semana na chave e medir uma vez por semana sem cache. Segurança: baixo risco (cache de PR de fora não grava no ramo principal).
4. **O CI não usa o arquivo de trava** (`environment.linux-64.lock` existe só para Linux e para o ambiente de desenvolvimento). O teste 10 (reprodutibilidade) segue aberto.
5. `appimagetool` 1.9.1 com sha256: bom (ver parecer no item 3).
6. `REUSE.toml`: correto e simples. Lembrar que os textos novos em `LICENSES/` (defeitos 2 e 3 do AppImage) só passam no `reuse lint` se alguma etiqueta do repositório usar essas licenças; se o lint reclamar de "licença não usada", guardar esses textos em `packaging/licenses-texts/`.
7. O `THIRD_PARTY.md` gerado do inventário (ADR-009 §7, item 4) ainda não existe.

## O que o líder faz em seguida
1. BOARD e LOG: T11 da S01 aprovada; S02-T10 e S02-T11 reprovadas pela primeira vez; S02-T16 com amostra aprovada; ADR-005 atualizado (segue esboço).
2. Correções mecânicas da S01 (item 1) e fechar a S01.
3. Um cartão de correção para o AppImage (defeitos 1 a 7) e um para o Windows (defeitos 1 a 4), cada um abaixo de 400 linhas; voltam ao opus para conferência do diff. Os itens 8 a 10 do AppImage viram um cartão "antes do primeiro release".
4. Um cartão pequeno (T2): teste 2 no Windows e sonda 3b. Antes da S04.
5. Um cartão (T2): lista de licenças permitidas no inventário (item 5, defeito 1).
6. Anotar a cota desta sessão em `QUOTA.md` (pedir os percentuais ao PO).

## Perguntas ao PO (com recomendação)
1. **A poda tirou também o "Mesa", a peça que desenha a tela quando o computador não tem driver de vídeo funcionando.** Isso era a opção 4, que você não tinha escolhido. Mantemos fora? **Recomendo manter fora** (é o costume em AppImage e economiza espaço), com duas condições: registrar a decisão e testar o AppImage numa máquina virtual sem aceleração de vídeo no roteiro T14. Se não abrir ali, o Mesa volta.
2. **Posso mandar o líder baixar da internet os textos oficiais de quatro licenças** (exceção do Open CASCADE, LGPL 3, LGPL 2.1 e GPL 3) para guardar no repositório? **Recomendo sim**: sem eles os pacotes saem incompletos.
3. **Os instaladores gerados pelo CI ficam baixáveis por qualquer pessoa com conta no GitHub.** Enquanto as correções de licença não entram, **recomendo** reduzir a guarda desses arquivos para 7 dias e tratá-los como "build de teste, não é versão publicada". Alternativa: parar de publicá-los até a correção.
