# tests

Testes automatizados do projeto, executados em Windows e Linux. Rode com `QT_QPA_PLATFORM=offscreen pytest` (a configuração está em `pytest.ini`).

## Pulo vira falha (chaves de obrigatório)
Um teste que não pode rodar (sem módulo, sem tela, sem localidade) pula com um aviso em destaque. No CI isso não pode passar em silêncio, então há chaves que transformam o pulo em falha:
- `OBIM_CI=1` liga de uma vez todas as chaves `OBIM_S04_*_OBRIGATORIO` (lista em `tests/obrigatorio.py`). Use só onde o módulo C++ foi compilado.
- `OBIM_TELA_OBRIGATORIA=1`: testes de tela da S03 (com Xvfb e Mesa no Linux).
- `OBIM_LOCALIDADE_OBRIGATORIA=1`: testes que dependem da localidade pt_BR.

O fim de cada execução imprime `pytest: N passaram, M falharam, K PULADOS`; no CI a mesma linha vai para o resumo do job.
