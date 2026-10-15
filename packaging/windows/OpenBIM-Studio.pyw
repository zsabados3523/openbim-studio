# SPDX-License-Identifier: AGPL-3.0-or-later
"""Lançador do pacote Windows: usa o Python da pasta env\\ e o código em app\\.

Não confere hash nem assinatura de nenhuma DLL: você pode trocar as bibliotecas (ver LGPL-COMO-TROCAR.md).
O atalho inicia o Python em modo isolado (`pythonw.exe -I`), que ignora PYTHONPATH, PYTHONHOME e o Python do usuário.
`pythonw.exe` não tem janela de texto: se algo falhar ao abrir, este arquivo grava o erro em `abertura.log` (mesma
pasta do registro do app) e mostra uma mensagem, em vez de falhar calado (F0-RG-11).
"""
import os
import sys
import traceback


def pasta_registros():  # mesma regra de app/openbim_app/registro.py (aqui o app ainda pode nem importar)
    forcada = os.environ.get("OPENBIM_LOG_DIR")
    if forcada:
        return forcada
    base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Local")
    return os.path.join(base, "OpenBIM Studio", "logs")


def avisar_falha(texto):
    pasta = pasta_registros()
    try:
        os.makedirs(pasta, exist_ok=True)
        with open(os.path.join(pasta, "abertura.log"), "a", encoding="utf-8") as f:
            f.write(texto + "\n")
    except OSError:
        pasta = "(não foi possível gravar o registro)"
    if os.environ.get("OPENBIM_SEM_DIALOGO"):
        return
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(
            None,
            "O OpenBIM Studio não conseguiu abrir.\n\nO erro foi gravado em:\n" + pasta + "\n\nMande o arquivo abertura.log para pedir ajuda.",
            "OpenBIM Studio", 0x10)
    except Exception:  # noqa: BLE001 - sem janela de aviso, o registro já foi gravado
        pass


def iniciar():
    aqui = os.path.dirname(os.path.abspath(__file__))  # ...\app
    env = os.path.join(os.path.dirname(aqui), "env")
    for sub in ("Library\\bin", "Library\\mingw-w64\\bin", "Library\\usr\\bin", "bin", "Scripts"):
        pasta = os.path.join(env, sub)
        if os.path.isdir(pasta):
            os.environ["PATH"] = pasta + os.pathsep + os.environ.get("PATH", "")
            os.add_dll_directory(pasta)
    sys.path.insert(0, aqui)
    from openbim_app.main import main
    return main()


if __name__ == "__main__":
    try:
        codigo = iniciar()
    except Exception:  # noqa: BLE001 - qualquer falha na abertura vira registro e mensagem
        avisar_falha(traceback.format_exc())
        codigo = 1
    sys.exit(codigo)
