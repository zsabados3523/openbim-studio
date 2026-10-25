<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
# ADR-005: Dependências, build e empacotamento

Status: aceito

## Contexto
O programa junta quatro peças grandes que precisam ser da mesma "safra": Python, Qt/PySide6, Open CASCADE (OCCT) e IfcOpenShell. O módulo C++ `obimcore` e a parte Python têm de enxergar o mesmo modelo IFC na memória, sem cópia (ADR-001), o que só funciona se o IfcOpenShell usado pelo C++ e pelo Python for o mesmo binário. Além disso, compilar e empacotar para Windows e Linux é o risco técnico mais alto do projeto.

Metas: build limpo em até 60 min, build incremental em até 10 min, instalador em até 600 MB.

## Opções
**Fonte dos binários**
- **A. conda-forge como fonte única.** Único lugar com OCCT 8.0.1, IfcOpenShell 0.9.0 e PySide6/Qt da mesma série em win-64 e linux-64, com cabeçalhos do Qt e compiladores no próprio canal.
- B. vcpkg mais PyPI. Descartada: vcpkg não tem IfcOpenShell nem PySide6, e o PyPI não tem OCCT.
- C. Só PyPI para o Python. Descartada: cada pacote embute a sua cópia de Qt e de OCCT, e sem cabeçalhos não há como ligar o nosso C++; duas cópias no mesmo processo é o risco que se quer evitar.
- D. conda-forge com IfcOpenShell compilado por nós. Plano B da opção A: uma cópia só e as opções de build que quisermos, ao custo de build longo e receita própria.

**Montagem**
- **P1. Pasta do ambiente inteira com um lançador pequeno**, podada de pacotes grandes e desnecessários.
- P2. PyInstaller em modo pasta: pacote menor, mas erros de biblioteca só aparecem na máquina do usuário.
- P3. Briefcase: monta a partir de pacotes do PyPI (opção C); fora.

**Instalador:** Windows com NSIS ou MSI via WiX; Linux com AppImage ou Flatpak.

## Decisão
1. **conda-forge, canal único, com `nodefaults`** (opção A). Python 3.12, `occt` 8.0.1, `ifcopenshell` 0.9.0 (versão e build travados), `pyside6` 6.11.2 com `qt6-main` 6.11.2, `nanobind` 3.1.0. Ambiente com Miniforge, nunca o instalador Anaconda ou Miniconda. A opção D só entra pelos gatilhos abaixo.
2. **Arquivos de trava** `environment.linux-64.lock` e `environment.win-64.lock` (desenvolvimento) e `packaging/runtime-environment.*.lock` (execução), usados pelo CI. A montagem dos pacotes falha se `ifcopenshell`, `occt`, `pyside6` ou `qt6-main` forem de compilações diferentes nas duas travas.
3. **Montagem P1 com poda** (`scripts/prune_packages.py`: 139 pacotes, entre eles VTK, ffmpeg e Mesa). A lista do que saiu vai em `licenses/REMOVIDOS.md`. Custo conhecido: o módulo de visualização do OCCT (`TKIVtk`) deixa de funcionar e o Mesa não vai no pacote.
4. **NSIS no Windows** (instalação por usuário, sem administrador; o ambiente vai num `tar.gz` extraído pelo `tar.exe` do sistema, porque o NSIS não aguentou dezenas de milhares de arquivos soltos) e **AppImage no Linux**, com appimagetool 1.9.1 de sha256 conferido (`packaging/README.md`). WiX e Flatpak ficam fora.
5. **Álgebra linear sem MKL**: `libblas=*=*openblas` no ambiente de execução, por licença. O inventário reprova a montagem se o MKL voltar.
6. **Compiladores:** os do conda-forge no Linux; MSVC (Visual Studio 2022) no Windows, sempre em Release, nunca MinGW. O C++ liga no IfcOpenShell pelo `IfcOpenShellConfig.cmake` do pacote. O `environment.yml` traz `zlib`, `libxml2-devel` e `libboost-devel`; nenhum script instala pacote na hora.
7. **Portões de todo pacote:** inventário de licenças (`scripts/license_inventory.py`) com lista de licenças permitidas, textos de licença em `licenses/` e testes de pacote nos dois sistemas (instala, abre isolado, abre com biblioteca trocada, desinstala sem sobras).

## Números medidos
| Item | Resultado |
|---|---|
| Pacote do IfcOpenShell (conda-forge) | traz cabeçalhos (`ifcparse`, `ifcgeom`) e bibliotecas compartilhadas, nenhuma estática, em linux-64 e win-64; o módulo Python usa essas bibliotecas |
| Programa C++ que inclui `ifcparse/file.h` e liga pelo CMake do pacote | compila e abre IFC nos dois; Linux: limpo 4,8 s, incremental 4,2 s; Windows: 19,4 s e 5,7 s |
| Módulo `obimcore` (nanobind, OCCT, Qt) | Linux 21,7 s limpo e 5,6 s incremental; Windows 87,5 s e 16,9 s |
| Instalador Windows | 309 MB (482 MB com MKL, que saiu por licença); instala sem administrador em até 300 s, abre em até 10 s |
| AppImage | 971 MB sem poda; 389 MB com poda; primeira abertura 0,5 s com FUSE e 8,5 s sem |
| Inventário de licenças | 100% dos pacotes que ficam têm licença; 0 fora do conda-forge; 5 exceções nomeadas e presas à versão (`tbb-devel`, `ucrt`, `vc14_runtime`, `vcomp14`, `cgal-cpp`) |
| Ambiente no CI | resolve em linux-64, win-64 e macOS; criação no Windows em cerca de 3 min |
| CI do Windows (ambiente, testes, instalador) | cerca de 12 min depois de dividir os testes em partes; meta de 10 min não atingida |

## Consequências
- Ficamos presos ao ritmo do conda-forge (hoje Qt 6.11.2, não 6.12) e ao par PySide6/Qt travado.
- Trocar de versão do `ifcopenshell` é trocar de ABI: exige refazer travas, testes da ponte e inventário.
- O pacote leva tudo o que o ambiente tem, menos o podado; a poda é conferida a cada mudança de versão e todo item novo removido é decisão registrada.
- Redistribuir binários do conda-forge traz obrigações de licença: pasta `licenses/`, lista de fontes por release (`packaging/linux/FONTES.md.in`) e instruções para trocar bibliotecas LGPL (`LGPL-COMO-TROCAR.md`). Os runtimes da Microsoft (`ucrt`, `vc14_runtime`, `vcomp14`) vão só no instalador Windows, sem modificação. Isto não é parecer jurídico.
- Se cair na opção D, o projeto passa a manter uma receita de build do IfcOpenShell.
- O `vcruntime140*.dll` do pacote tem de ser igual ou mais novo que o do compilador que gerou o `.pyd`; a montagem e o teste do instalador conferem.

## O que nos faria mudar de ideia
- Duas cópias do núcleo no processo, ou o modelo não ser o mesmo dos dois lados, ou um build novo do pacote com IfcOpenShell estático: opção D; se também falhar, rever o ADR-001.
- Um defeito do par PySide6/Qt que só o 6.12 resolva: reavaliar o PyPI para a interface, o que reabre o problema do Qt duplicado.
- Instalador acima de 600 MB mesmo com poda: P2 ou componentes opcionais.
- NSIS falhar em instalar por cima, desinstalar limpo ou conviver com assinatura de código: reabrir o WiX.
- O conda-forge restringir redistribuição ou abandonar um pacote: opção D ampliada ou vcpkg para a parte C++.
- Build limpo acima de 60 min: guardar pacotes prontos no cache do CI.
- A poda quebrar algo que o programa passe a usar (visualização do OCCT, vídeo, Mesa em máquina sem driver): o pacote volta, com novo inventário.

## O que ficou em aberto
- CI do Windows acima da meta de 10 min; as opções são guardar o ambiente pronto em cache ou montar o instalador só quando o pacote mudar.
- Fixar o runtime do appimagetool (`--runtime-file`) e registrar a licença dele, antes do primeiro release.
- Oferta de código-fonte por 3 anos, tabela de fontes por pacote junto do release e tela "Sobre > Licenças", antes do primeiro release.
- Assinatura de código no Windows (hoje o SmartScreen avisa).
- Máquinas reais: Windows 10 e 11, Ubuntu LTS, Fedora, duplo clique, máquina virtual sem aceleração de vídeo.
- Cabeçalhos do QRhi no `qt6-main` e termos do canal conda-forge: não verificados em fonte oficial.
