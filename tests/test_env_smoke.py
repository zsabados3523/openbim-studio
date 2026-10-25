# SPDX-License-Identifier: AGPL-3.0-or-later
"""Teste de fumaça do ambiente: as versões fixadas em environment.yml."""
import sys

import ifcopenshell
import PySide6


def test_python_version():
    assert sys.version_info[:2] == (3, 12)


def test_pyside6_version():
    assert PySide6.__version__ == "6.11.2"


def test_ifcopenshell_version():
    assert ifcopenshell.version.startswith("0.9.0")
