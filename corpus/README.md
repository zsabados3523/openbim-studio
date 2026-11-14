# corpus

Somente manifestos e arquivos públicos com licença conhecida. Projetos do PO ficam fora do repositório.

## Formato do manifesto (`corpus/manifestos/<nome>.json`)
Cada modelo do corpus possui um arquivo JSON em `corpus/manifestos/<nome>.json` (mesmo nome-base do modelo) com os campos obrigatórios:
- `nome`, `origem`, `versao_ou_commit`, `data_acesso`
- `sha256` (hexadecimal SHA-256 do arquivo), `tamanho_bytes` (inteiro)
- `licenca`: `CC-BY-4.0`, `MIT`, `Apache-2.0`, `dominio-publico`, `propria` (ou `CC-BY-ND-4.0` / `KIT` apenas com `pode_ir_no_git` = `"nao"`)
- `atribuicao`, `pode_ir_no_git` (`"sim"` ou `"nao"`)
- `esquema`, `programa_de_origem`, `contagens`, `valores_conhecidos`, `cobre`, `observacoes`

Modelos grandes ou com restrição de redistribuição usam `pode_ir_no_git: "nao"`: a ausência do arquivo local não gera erro, e `sha256` / `tamanho_bytes` só são conferidos quando o arquivo existe na pasta.

## Como rodar a conferência
```bash
~/miniforge3/envs/openbim/bin/python scripts/conferir_corpus.py tests/amostras corpus/manifestos
```

## Modelos grandes gerados (benchmark, F0-S03-T02)
Gerados por `scripts/gerar_modelo_grande.py`; ficam aqui só na sua máquina (`.gitignore` ignora tudo exceto este README).

    ~/miniforge3/envs/openbim/bin/python scripts/gerar_modelo_grande.py corpus/modelo-grande-1m.ifc --paredes 83334

- Cada parede é uma caixa de 12 triângulos; andares de 200 paredes. A saída é igual a cada execução (mesmo SHA-256).
- Medido com o iterador de geometria do ifcopenshell 0.9.0 no arquivo inteiro (não é estimativa):
  83334 paredes, 417 andares, **1.000.008 triângulos**, arquivo de ~74 MB (SHA-256 `0d4639449d5a18f1...`).
- Tempo para gerar: ~60 s. Contar triângulos: ~10 s (multi-thread).
