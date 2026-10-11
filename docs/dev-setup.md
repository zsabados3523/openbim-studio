# Preparar o ambiente de desenvolvimento

Para quem vai mexer no código. O PO não precisa fazer isto: o líder técnico faz.

## Primeira vez (Linux)
1. Instale o Miniforge (gerenciador de ambientes que já usa só o canal conda-forge). **Não use** o instalador Anaconda/Miniconda: o canal "defaults" tem termos comerciais (ADR-009).
2. Crie o ambiente a partir do arquivo do projeto:
   ```bash
   conda env create -f environment.yml
   ```
   Leva cerca de 2 minutos. O arquivo fixa as versões; o arquivo `environment.linux-64.lock` lista todos os pacotes exatos (gerado, não editar à mão).
3. Teste:
   ```bash
   conda activate openbim
   pytest
   ```

## Regras
- Canal único: conda-forge, com `nodefaults`. Pacote de outro canal é erro.
- Ao mudar `environment.yml`, gere o arquivo de trava de novo: `conda list --explicit --md5 > environment.linux-64.lock`.
- Windows: o ambiente é montado pelo CI (ver seção CI) e na VM do PO.

## CI
O fluxo `.github/workflows/ci.yml` roda a cada push e pull request em `main`, em três jobs com estes nomes exatos (usados na regra de bloqueio de merge; não renomear):

| Job | Sistema | Bloqueia merge? |
|---|---|---|
| `linux` | ubuntu-latest | sim |
| `windows` | windows-latest | sim |
| `macos` | macos-14 (Apple Silicon) | não: `continue-on-error`, a falha vira aviso |

Cada job cria o ambiente do `environment.yml` só com conda-forge, roda `pytest -q tests` sem tela (o teste de sonda de `prototypes/cpp_probe` fica fora), gera o inventário de licenças (falha se algum pacote não for do conda-forge ou não tiver licença; a checagem contra a lista de licenças permitidas é só informativa no ambiente de desenvolvimento e **reprova** na montagem do AppImage e do instalador, sobre os pacotes que vão dentro deles), guarda como artefato o inventário e um `app.tar.gz` (`openbim-ci-linux`, `-windows`, `-macos`) e registra o tempo total no resumo da execução, dizendo que o ambiente foi montado sem cache (build limpo; o incremental ainda não é medido). Só o `linux` roda `reuse lint` (a ferramenta REUSE é instalada só no CI, em ambiente separado). Os passos usam `bash` em todos os sistemas. Se o `macos` falhar, o motivo vai para `docs/state/LOG.md`, sem esforço de correção. Não usa segredos.

Estado: os jobs `windows` e `macos` foram escritos mas ainda não foram executados em runner (o push depende de autenticação); só valem como prova depois de uma execução verde com log.
