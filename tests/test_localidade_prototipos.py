# SPDX-License-Identifier: AGPL-3.0-or-later
"""Os protótipos do viewport também não deixam a vírgula decimal depois de criar o QApplication.

Roda em SUBPROCESSO sem LC_ALL (o conftest.py põe LC_ALL=C no pytest e esconderia o defeito).
Sem localidade pt_BR na máquina, pula COM MENSAGEM EM DESTAQUE; nunca passa em silêncio.
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest
from obrigatorio import pular as pular_chave

PROTO = Path(__file__).resolve().parent.parent / "viewport" / "viewport_qrhi"

CODIGO_VIRGULA = "import locale; locale.setlocale(locale.LC_NUMERIC, ''); print(locale.localeconv()['decimal_point'])"
CODIGO_MEDIR = """
import locale, sys
sys.path.insert(0, %r)
import medir
from PySide6.QtWidgets import QApplication
app = QApplication([])
antes = locale.localeconv()['decimal_point']
locale.setlocale(locale.LC_NUMERIC, 'C')   # a mesma linha que medir.medir() e __main__.main() executam
print(antes, locale.localeconv()['decimal_point'])
""" % str(PROTO)
CODIGO_SEM_QT = "import sys; sys.path.insert(0, %r); import medir; print('PySide6' in sys.modules)" % str(PROTO)


def _env():
    env = {k: v for k, v in os.environ.items() if not k.startswith("LC_") and k not in ("LANG", "LANGUAGE")}
    env.update(QT_QPA_PLATFORM="offscreen", LANG="pt_BR.UTF-8", LC_NUMERIC="pt_BR.UTF-8")
    env.pop("DISPLAY", None)
    env.pop("WAYLAND_DISPLAY", None)
    return env


def _py(codigo):
    p = subprocess.run([sys.executable, "-c", codigo], env=_env(), capture_output=True, text=True, timeout=120)
    assert p.returncode == 0, f"subprocesso falhou:\n{p.stdout}\n{p.stderr}"
    return p.stdout.strip().splitlines()[-1]


@pytest.fixture(scope="module")
def tem_pt_br():
    if sys.platform == "win32":
        pytest.skip("\n!!! localidade pt_BR: caso só roda no Linux; NAO FOI EXECUTADO !!!\n")
    if _py(CODIGO_VIRGULA) != ",":
        pular_chave("\n!!! SEM LOCALIDADE pt_BR NESTA MAQUINA: teste de localidade dos protótipos NAO FOI EXECUTADO "
              "(Linux: locale-gen pt_BR.UTF-8) !!!\n", "OBIM_LOCALIDADE_OBRIGATORIA")


def test_prototipo_deixa_ponto_decimal_depois_do_qapplication(tem_pt_br):
    antes, depois = _py(CODIGO_MEDIR).split()
    assert antes == ",", "o canário parou de reproduzir: o QApplication não troca mais a localidade; revise o teste de localidade dos protótipos"
    assert depois == "."


def test_importar_medir_nao_carrega_qt():
    assert _py(CODIGO_SEM_QT) == "False"
