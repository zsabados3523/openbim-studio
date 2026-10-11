# corpus

Somente manifestos e arquivos públicos com licença conhecida. Projetos do PO ficam fora do repositório.

## Modelos grandes gerados (benchmark, F0-S03-T02)
Gerados por `scripts/gerar_modelo_grande.py`; ficam aqui só na sua máquina (`.gitignore` ignora tudo exceto este README).

    ~/miniforge3/envs/openbim/bin/python scripts/gerar_modelo_grande.py corpus/modelo-grande-1m.ifc --paredes 83334

- Cada parede é uma caixa de 12 triângulos; andares de 200 paredes. A saída é igual a cada execução (mesmo SHA-256).
- Medido com o iterador de geometria do ifcopenshell 0.9.0 no arquivo inteiro (não é estimativa):
  83334 paredes, 417 andares, **1.000.008 triângulos**, arquivo de ~74 MB (SHA-256 `0d4639449d5a18f1...`).
- Tempo para gerar: ~60 s. Contar triângulos: ~10 s (multi-thread).
