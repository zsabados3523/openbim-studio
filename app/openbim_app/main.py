# SPDX-License-Identifier: AGPL-3.0-or-later
"""Ponto de entrada do aplicativo."""
import multiprocessing
import sys

from . import registro
from .localidade import criar_aplicacao, numerico_ok
from .main_window import MainWindow


def main(argv=None) -> int:
    # Exigido pelo cartão F0-S04-T17 (lote 7): protege a abertura em pacote congelado (Windows). No Linux e no Python comum não faz nada.
    # Quem evita a segunda janela no filho spawn é a regra do multiprocessing de não reexecutar módulos `*.__main__`.
    multiprocessing.freeze_support()
    argv = sys.argv if argv is None else argv
    selftest = "--selftest" in argv
    registro.iniciar(dialogo=not selftest)
    app = criar_aplicacao(argv)
    registro.instalar_qt()
    app.setApplicationName("OpenBIM Studio")
    if "--selftest-falha" in argv:  # só para o teste do instalador: prova que um erro na abertura fica no registro
        raise RuntimeError("falha provocada por --selftest-falha")
    window = MainWindow()
    if selftest:
        ok = bool(window.windowTitle()) and numerico_ok()
        registro.log.info("selftest %s", "OK" if ok else "FALHA")
        print("OK" if ok else "FALHA")
        window.close()
        return 0 if ok else 1
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
