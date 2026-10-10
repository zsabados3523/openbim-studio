// SPDX-License-Identifier: AGPL-3.0-or-later
#include <nanobind/nanobind.h>
#include <nanobind/stl/string.h>
#include <BRepPrimAPI_MakeBox.hxx>
#include <BRepGProp.hxx>
#include <GProp_GProps.hxx>
#include <QString>

NB_MODULE(cpp_probe, m) {
    m.def("box_volume", [](double dx, double dy, double dz) {
        BRepPrimAPI_MakeBox box(dx, dy, dz);
        GProp_GProps props;
        BRepGProp::VolumeProperties(box.Shape(), props);
        return props.Mass();
    });
    m.def("qt_hello", [] { return QString("qt-ok").toStdString(); });
}
