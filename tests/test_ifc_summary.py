# SPDX-License-Identifier: AGPL-3.0-or-later
"""Testes do resumo de IFC (F0-S02-T05): arquivos gerados no próprio teste."""
import ifcopenshell
import ifcopenshell.api
import ifcopenshell.guid
import pytest
from PySide6.QtWidgets import QApplication

from openbim_app.ifc_summary import IfcSummaryError, count_by_class, format_summary
from openbim_app.main_window import MainWindow


def _make(path, schema, walls, slabs):
    """IFC com `walls` paredes e `slabs` lajes; devolve o caminho."""
    f = ifcopenshell.file(schema=schema)
    for cls, n in (("IfcWall", walls), ("IfcSlab", slabs)):
        for _ in range(n):
            if schema == "IFC2X3":  # a API root exige owner history nesse esquema
                f.create_entity(cls, GlobalId=ifcopenshell.guid.new())
            else:
                ifcopenshell.api.run("root.create_entity", f, ifc_class=cls)
    f.write(str(path))
    return path


def test_ifc4_exact_counts_and_oracle(tmp_path):
    path = _make(tmp_path / "a.ifc", "IFC4", walls=7, slabs=3)
    s = count_by_class(path)
    assert (s.file_name, s.schema, s.total) == ("a.ifc", "IFC4", 10)
    assert s.by_class == {"IfcSlab": 3, "IfcWall": 7}
    # oráculo independente: leitura direta do ifcopenshell
    model = ifcopenshell.open(str(path))
    assert s.by_class["IfcWall"] == len(model.by_type("IfcWall", include_subtypes=False))
    assert s.by_class["IfcSlab"] == len(model.by_type("IfcSlab", include_subtypes=False))
    assert s.total == len(model.by_type("IfcProduct"))


@pytest.mark.parametrize("schema", ["IFC2X3", "IFC4", "IFC4X3"])
def test_schema_reported(tmp_path, schema):
    path = _make(tmp_path / "x.ifc", schema, walls=2, slabs=1)
    s = count_by_class(path)
    assert s.schema == schema
    assert s.total == 3
    assert s.by_class["IfcWall"] == len(ifcopenshell.open(str(path)).by_type("IfcWall"))


def test_invalid_and_missing(tmp_path):
    bad = tmp_path / "ruim.ifc"
    bad.write_text("isto não é IFC")
    with pytest.raises(IfcSummaryError, match="não é um IFC válido"):
        count_by_class(bad)
    with pytest.raises(IfcSummaryError, match="não encontrado"):
        count_by_class(tmp_path / "nao_existe.ifc")


def test_format_summary(tmp_path):
    text = format_summary(count_by_class(_make(tmp_path / "a.ifc", "IFC4", 2, 1)))
    assert "Esquema: IFC4" in text and "IfcWall: 2" in text and "Total de elementos: 3" in text


@pytest.fixture
def window():
    QApplication.instance() or QApplication([])
    w = MainWindow()
    w.show_error_dialogs = False
    yield w
    w.close()


def test_window_open_ok(window, tmp_path):
    assert window.open_ifc(_make(tmp_path / "ok.ifc", "IFC4", 4, 2)) is None
    assert "IfcWall: 4" in window.centralWidget().text()
    assert "ok.ifc" in window.statusBar().currentMessage()


def test_window_open_errors_do_not_raise(window, tmp_path):
    bad = tmp_path / "ruim.ifc"
    bad.write_text("lixo")
    for p in (bad, tmp_path / "nada.ifc"):
        msg = window.open_ifc(p)
        assert msg and p.name in msg
        assert window.last_error == msg
