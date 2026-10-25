# Preparar o ambiente de desenvolvimento

Para quem vai mexer no código.

## Primeira vez (Linux)
1. Instale o Miniforge (gerenciador de ambientes que já usa só o canal conda-forge). **Não use** o instalador Anaconda/Miniconda: o canal "defaults" tem termos comerciais de uso.
2. Crie o ambiente a partir do arquivo do projeto:
   ```bash
   conda env create -f environment.yml
   ```
   Leva cerca de 2 minutos. O arquivo fixa as versões; o arquivo `environment.linux-64.lock` lista todos os pacotes exatos, com o build do `ifcopenshell` (gerado, não editar à mão). Para um ambiente idêntico ao do CI, use a trava: `conda create -n openbim --file environment.linux-64.lock`.
3. Teste:
   ```bash
   conda activate openbim
   QT_QPA_PLATFORM=offscreen pytest
   ```

## Regras
- Canal único: conda-forge, com `nodefaults`. Pacote de outro canal é erro.
- Ao mudar `environment.yml`, gere o arquivo de trava de novo: `conda list --explicit --md5 > environment.linux-64.lock`.
- Windows: o ambiente é montado pelo CI (ver seção CI) e em máquina virtual. A trava do Windows é `environment.win-64.lock`.
- Para compilar contra o IfcOpenShell (o módulo `obimcore`), o ambiente traz `zlib`, `libxml2-devel` e `libboost-devel` (versões em `environment.yml`; o `ifcopenshell` tem o build travado nas travas, porque trocar o build é trocar de ABI). Nenhum script instala pacote na hora.

- O módulo `obimcore` (Linux) sai com um único RPATH, relativo ao pacote (`$ORIGIN/../../env/lib`); o `build.sh` tira o caminho absoluto que o compilador do conda acrescenta. No ambiente de desenvolvimento esse caminho não existe e o carregador cai no RPATH do próprio Python do conda (`$ORIGIN/../lib`). Por isso o módulo só deve ser carregado pelo Python do ambiente `openbim`; com o Python do sistema ele acharia as bibliotecas do sistema.
- No Windows o `.pyd` não tem RPATH: o `__init__.py` gerado pelo `build.sh` mostra ao carregador a pasta `Library\bin` do `sys.prefix`. No instalador essa pasta é a do `env\` do pacote; o `vcruntime140*.dll` do pacote tem de ser igual ou mais novo que o do compilador (o oráculo `packaging/windows/test_instalador_ponte.sh` confere).

## Travas do ambiente
- Cada sistema gera a própria trava no CI (`conda list --explicit --md5`, sem ferramenta nova) no passo "Trava do ambiente" e a anexa ao artefato `openbim-ci-linux` / `openbim-ci-windows` (`out/environment.<sistema>.lock`). O passo é só informativo: diz se a trava gerada é igual à do repositório.
- Quem mantém o ambiente baixa o artefato e guarda `environment.linux-64.lock` e `environment.win-64.lock` na raiz. Enquanto o arquivo de um sistema não existir, o CI cria o ambiente pelo `environment.yml`; quando existir, cria pela trava (`conda create --file`), e a mudança em `environment.yml` ou na trava invalida o cache de pacotes.
- Fora do CI, nada acima baixa ferramenta nova: só `conda`/`mamba` do ambiente.

## CI
O fluxo `.github/workflows/ci.yml` roda a cada push e pull request em `main`, em três jobs com estes nomes exatos (usados na regra de bloqueio de merge; não renomear):

| Job | Sistema | Bloqueia merge? |
|---|---|---|
| `linux` | ubuntu-latest | sim |
| `windows` | windows-latest | sim |
| `macos` | macos-14 (Apple Silicon) | não: `continue-on-error`, a falha vira aviso |

Cada job cria o ambiente do `environment.yml` só com conda-forge, roda `pytest -q tests` sem tela, gera o inventário de licenças (falha se algum pacote não for do conda-forge ou não tiver licença; a checagem contra a lista de licenças permitidas é só informativa no ambiente de desenvolvimento e **reprova** na montagem do AppImage e do instalador, sobre os pacotes que vão dentro deles), guarda como artefato o inventário e um `app.tar.gz` (`openbim-ci-linux`, `-windows`, `-macos`) e registra o tempo total no resumo da execução, dizendo que o ambiente foi montado sem cache (build limpo; o incremental ainda não é medido). Só o `linux` roda `reuse lint` (a ferramenta REUSE é instalada só no CI, em ambiente separado). Os passos usam `bash` em todos os sistemas. Se o `macos` falhar, a falha é só um aviso, sem esforço de correção. Não usa segredos.

**Quando o instalador do Windows é testado:** os passos que montam o instalador (NSIS) e rodam "instala, abre, desinstala" (cerca de 10 min) só rodam em push no `main` e, em pull request, quando o diff contra a base toca `packaging/`, `app/`, `environment*.yml`, `environment.*.lock`, `pyproject*`, `.github/workflows/ci.yml`, `LICENSES/` ou os scripts de empacotamento (`prune_packages.py`, `license_inventory.py`, `collect_package_licenses.py`). Nos demais PRs esses passos são pulados (contam como sucesso) e o job `windows` continua reportando com o mesmo nome. Na dúvida (a comparação falhar), o instalador é testado.

## Testes gráficos sem abrir janela na tela
Para o desenho 3D rodar numa tela virtual (nada aparece na sua tela):
`env -u DISPLAY -u WAYLAND_DISPLAY xvfb-run -a -s "-screen 0 1280x800x24" env QT_QPA_PLATFORM=xcb LIBGL_ALWAYS_SOFTWARE=1 ~/miniforge3/envs/openbim/bin/pytest`

## Localidade numérica
O Qt troca a localidade numérica do processo ao criar a aplicação, e em pt_BR o IfcOpenShell passa a gravar vírgula decimal (IFC corrompido que ainda reabre). Regras: a aplicação só é criada por `openbim_app.localidade.criar_aplicacao`, que já corrige; toda gravação de IFC e de `.obim` chama `garantir_numerico_c()` antes de gravar (se devolver verdadeiro, registrar um aviso); números mostrados ao usuário vêm do `QLocale`, nunca de funções do C; o `AppRun` não define `LC_ALL`. O `tests/conftest.py` mantém `LC_ALL=C`, por isso os testes de `tests/test_localidade.py` rodam em subprocesso sem `LC_ALL`.
