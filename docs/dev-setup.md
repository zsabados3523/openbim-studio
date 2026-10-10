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
- Windows: o ambiente é montado pelo CI (ver seção CI, quando existir) e na VM do PO.
