# tests

Testes automáticos do projeto, executados no CI em Windows e Linux (e na máquina do PO).

- Rodar tudo: `QT_QPA_PLATFORM=offscreen ~/miniforge3/envs/openbim/bin/pytest` (ver `docs/dev-setup.md`).
- `conftest.py`: põe `app/` no caminho, força Qt sem tela e isola o registro de erros.
- `test_*.py`: um arquivo por assunto. Os de nome `test_s04_*` são as provas da fatia S04 (ponte Python↔C++); os `test_viewport_*` são as da S03 (viewport); o resto cobre o app esqueleto, a localidade, o inventário de licenças e o registro de erros.
- `*_aux.py` e `localidade_aux.py`: ajudantes dos testes, sem teste próprio.
- Testes de oráculo (escritos por agente diferente do que escreve o código) são congelados: não se afrouxa número nem se remove caso.
- Teste que depende de tela, placa de vídeo ou módulo C++ pula quando falta; no CI as chaves `OBIM_*_OBRIGATORIO` transformam o pulo em falha (ver `.github/workflows/ci.yml`).
