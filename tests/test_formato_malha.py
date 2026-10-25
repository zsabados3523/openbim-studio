# SPDX-License-Identifier: AGPL-3.0-or-later
"""Formato de vértices e de objetos é o mesmo em Python e em C++. Lê os números escritos no código C++ (sem
precisar compilar) e compara com `viewport/formato_malha.py`; se um lado mudar sem o outro, este teste falha."""
import ast
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "viewport"))

import formato_malha as fm  # noqa: E402

NUCLEO = RAIZ / "native" / "obimcore" / "nucleo"


def _numeros(arquivo, nomes):
    texto = (NUCLEO / arquivo).read_text(encoding="utf-8")
    achados = {}
    for n in nomes:
        m = re.search(rf"\b{n}\s*=\s*(\d+)", texto)
        assert m, f"{arquivo}: constante {n} não encontrada (o teste lê o texto do C++; renomeou?)"
        achados[n] = int(m.group(1))
    return achados


def test_tamanho_do_vertice_igual_nos_dois_lados():
    assert fm.BYTES_VERTICE == 28
    assert _numeros("cena.h", ["BYTES_VERTICE"])["BYTES_VERTICE"] == fm.BYTES_VERTICE


def test_tabela_de_objetos_igual_nos_dois_lados():
    c = _numeros("cena.cpp", ["BYTES_OBJETO", "O_ID", "O_GUID", "N_GUID", "O_PI", "O_NI", "O_PV", "O_NV", "O_MIN", "O_MAX"])
    d = fm.DTYPE_OBJETO
    assert c["BYTES_OBJETO"] == fm.BYTES_OBJETO == 66
    assert (c["O_ID"], c["O_GUID"], c["N_GUID"]) == (d.fields["id_step"][1], d.fields["guid"][1], d.fields["guid"][0].itemsize)
    assert (c["O_PI"], c["O_NI"], c["O_PV"], c["O_NV"]) == tuple(d.fields[k][1] for k in (
        "primeiro_indice", "n_indices", "primeiro_vertice", "n_vertices"))
    assert (c["O_MIN"], c["O_MAX"]) == (d.fields["caixa_min"][1], d.fields["caixa_max"][1])


def test_posicao_do_vertice_fica_no_inicio():
    # o C++ lê a posição nos 12 primeiros bytes de cada vértice (cena.cpp, selecao.cpp)
    assert fm.DTYPE_VERTICE.fields["pos"][1] == 0 and fm.DTYPE_VERTICE.fields["pos"][0].itemsize == 12


def test_carregador_e_fluxo_a_usam_o_mesmo_formato():
    sys.path.insert(0, str(RAIZ / "viewport"))
    from viewport_qrhi import carregador
    assert carregador.DTYPE_VERTICE is fm.DTYPE_VERTICE and carregador.DTYPE_OBJETO is fm.DTYPE_OBJETO
    assert carregador.LoteMalha is fm.LoteMalha
    assert "viewport_qrhi" not in (RAIZ / "tools" / "s04" / "fluxo_a" / "fluxo_a.py").read_text(encoding="utf-8")


def test_tipos_numpy_escritos_na_ponte_cpp_sao_os_mesmos():
    """ponte_viewport.cpp monta os dtypes por texto; o texto tem de dar exatamente os dtypes de formato_malha.py."""
    import numpy as np
    texto = (NUCLEO.parent / "ponte_viewport.cpp").read_text(encoding="utf-8")
    achados = re.findall(r'nb::eval\("(\[.*?\])"\)', texto)
    assert len(achados) == 2, "ponte_viewport.cpp: esperava os dois nb::eval de dtype (vértice e objeto); o texto mudou?"
    vert, obj = (np.dtype(ast.literal_eval(a)) for a in achados)
    assert vert == fm.DTYPE_VERTICE and obj == fm.DTYPE_OBJETO


def test_atributos_do_vertice_no_motor_batem_com_o_formato():
    """motor.h diz à placa onde estão posição (0), normal (12) e cor (24) em cada vértice."""
    texto = (NUCLEO / "motor.h").read_text(encoding="utf-8")
    m = re.search(r"setAttributes\(\{\{0, 0, [\w:]+, (\d+)\}, \{0, 1, [\w:]+, (\d+)\},\s*\{0, 2, [\w:]+, (\d+)\}\}\)", texto)
    assert m, "motor.h: setAttributes dos três atributos de vértice não encontrado (o texto mudou?)"
    f = fm.DTYPE_VERTICE.fields
    assert tuple(int(x) for x in m.groups()) == (f["pos"][1], f["normal"][1], f["cor"][1])
