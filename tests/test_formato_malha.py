# SPDX-License-Identifier: AGPL-3.0-or-later
"""F0-RG-04: o formato de vértices e de objetos é o mesmo em Python e em C++. Lê os números escritos no código C++ (sem
precisar compilar) e compara com `prototypes/formato_malha.py`; se um lado mudar sem o outro, este teste falha."""
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "prototypes"))

import formato_malha as fm  # noqa: E402

NUCLEO = RAIZ / "prototypes" / "s04" / "obimcore" / "nucleo"


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
    c = _numeros("cena.cpp", ["BYTES_OBJETO", "O_PI", "O_NI", "O_PV", "O_NV", "O_MIN", "O_MAX"])
    d = fm.DTYPE_OBJETO
    assert c["BYTES_OBJETO"] == fm.BYTES_OBJETO == 66
    assert (c["O_PI"], c["O_NI"], c["O_PV"], c["O_NV"]) == tuple(d.fields[k][1] for k in (
        "primeiro_indice", "n_indices", "primeiro_vertice", "n_vertices"))
    assert (c["O_MIN"], c["O_MAX"]) == (d.fields["caixa_min"][1], d.fields["caixa_max"][1])


def test_posicao_do_vertice_fica_no_inicio():
    # o C++ lê a posição nos 12 primeiros bytes de cada vértice (cena.cpp, selecao.cpp)
    assert fm.DTYPE_VERTICE.fields["pos"][1] == 0 and fm.DTYPE_VERTICE.fields["pos"][0].itemsize == 12


def test_carregador_e_fluxo_a_usam_o_mesmo_formato():
    sys.path.insert(0, str(RAIZ / "prototypes"))
    from viewport_qrhi import carregador
    assert carregador.DTYPE_VERTICE is fm.DTYPE_VERTICE and carregador.DTYPE_OBJETO is fm.DTYPE_OBJETO
    assert carregador.LoteMalha is fm.LoteMalha
    assert "viewport_qrhi" not in (RAIZ / "prototypes" / "s04" / "fluxo_a" / "fluxo_a.py").read_text(encoding="utf-8")
