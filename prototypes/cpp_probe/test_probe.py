# SPDX-License-Identifier: AGPL-3.0-or-later
import sys, math
sys.path.insert(0, sys.argv[1] if len(sys.argv) > 1 else ".")
import cpp_probe
v = cpp_probe.box_volume(2, 3, 4)
assert math.isclose(v, 24.0, rel_tol=1e-9), v
assert cpp_probe.qt_hello() == "qt-ok"
print("OK volume =", v)
