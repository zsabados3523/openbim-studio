# SPDX-License-Identifier: AGPL-3.0-or-later
"""Script auxiliar da T26 (ver tests/test_localidade.py). Roda UM caso por processo e imprime um JSON na última linha.

Uso: python localidade_aux.py <caso>. O processo é lançado SEM LC_ALL, com LANG/LC_NUMERIC em pt_BR no Linux.
Este arquivo não importa nada do programa antes de escolher o caso: o canário (L1) não depende de localidade.py.
"""
import json
import locale
import sys
import threading

PONTOS = [(2799.9999999999995, 0.5, 1e-7), (-0.001, 0.0, 0.0)]


def ponto_decimal():
    return locale.localeconv()["decimal_point"]


def forcar_virgula():
    """Força à mão uma localidade numérica com vírgula (Windows e Linux). Devolve o nome aceito ou None."""
    for nome in ("pt_BR.UTF-8", "Portuguese_Brazil.1252", "Portuguese_Brazil.utf8", "pt_BR", "pt-BR"):
        try:
            locale.setlocale(locale.LC_NUMERIC, nome)
        except locale.Error:
            continue
        if ponto_decimal() == ",":
            return nome
    return None


def texto_ifc():
    import ifcopenshell

    f = ifcopenshell.file()
    for p in PONTOS:
        f.createIfcCartesianPoint(p)
    return f


def linhas_dados(texto):
    return [l for l in texto.splitlines() if l.startswith("#")]


def gravar_e_reabrir(tmp):
    """Grava o modelo em arquivo e reabre; devolve linhas gravadas e as coordenadas relidas."""
    import ifcopenshell

    f = texto_ifc()
    caminho = f"{tmp}/p.ifc"
    f.write(caminho)
    with open(caminho, encoding="utf-8") as a:
        linhas = linhas_dados(a.read())
    g = ifcopenshell.open(caminho)
    pts = [tuple(p.Coordinates) for p in g.by_type("IfcCartesianPoint")]
    return {"linhas": linhas, "linhas_to_string": linhas_dados(f.to_string()), "pontos": pts}


def caso(nome, tmp):
    r = {"caso": nome}
    if nome == "provar_locale":
        r["nome"] = forcar_virgula()
    elif nome == "ref":  # referência: processo em localidade C, sem Qt
        r["ponto"] = ponto_decimal()
        r.update(gravar_e_reabrir(tmp))
    elif nome == "l1":  # QApplication SEM a correção
        from PySide6.QtWidgets import QApplication

        r["antes"] = ponto_decimal()
        QApplication([])
        r["depois"] = ponto_decimal()
        r["texto"] = texto_ifc().to_string()
    elif nome == "l3ref":  # interface SEM a correção: é com ela que o L3 compara fora do Linux
        from PySide6.QtCore import QLocale
        from PySide6.QtWidgets import QApplication

        QApplication([])
        r["fmt"] = QLocale().toString(1234.5, "f", 2)
        r["nome_qt"] = QLocale().name()
    elif nome == "l1w":  # força à mão, sem a correção e sem Qt
        r["nome"] = forcar_virgula()
        r["ponto"] = ponto_decimal()
        r["texto"] = texto_ifc().to_string()
    else:
        from openbim_app import localidade

        if nome != "l4" and nome != "l1w":
            forcar_virgula()  # no Windows o Qt não troca sozinho; no Linux já vem com vírgula do ambiente
        from PySide6.QtWidgets import QApplication  # noqa: F401  (só para falhar cedo se faltar Qt)

        localidade.criar_aplicacao([])
        r["numerico_ok"] = localidade.numerico_ok()
        r["ponto"] = ponto_decimal()
        if nome == "l2":
            r.update(gravar_e_reabrir(tmp))
        elif nome == "l3":
            from PySide6.QtCore import QLocale

            r["fmt"] = QLocale().toString(1234.5, "f", 2)
            r["nome_qt"] = QLocale().name()
            r["time"] = locale.setlocale(locale.LC_TIME)
            r["ctype"] = locale.setlocale(locale.LC_CTYPE)
        elif nome == "l4":
            try:
                locale.setlocale(locale.LC_ALL, "")  # outra biblioteca desfazendo a correção
            except locale.Error:
                pass
            if ponto_decimal() != ",":
                forcar_virgula()
            r["desfeito"] = ponto_decimal()
            r["garantiu"] = localidade.garantir_numerico_c()
            r["depois_ok"] = localidade.numerico_ok()
            r.update(gravar_e_reabrir(tmp))
        elif nome == "l5":
            saida = {}
            t = threading.Thread(target=lambda: saida.update(gravar_e_reabrir(tmp)))
            t.start()
            t.join()
            r.update(saida)
    return r


if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        print(json.dumps(caso(sys.argv[1], tmp)))
