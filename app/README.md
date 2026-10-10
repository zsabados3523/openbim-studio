# app

Código do aplicativo OpenBIM Studio. Nesta fase (F0) contém apenas o esqueleto; o conteúdo é definido nas próximas fatias.

## Como rodar

Com o ambiente `openbim` ativo, na raiz do repositório:

```
PYTHONPATH=app python -m openbim_app
```

Testes (sem tela):

```
QT_QPA_PLATFORM=offscreen pytest -q
```

O `tests/conftest.py` já inclui `app/` no caminho, então o `PYTHONPATH` só é necessário para rodar o aplicativo.
