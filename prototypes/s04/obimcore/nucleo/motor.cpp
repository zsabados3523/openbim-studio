// SPDX-License-Identifier: AGPL-3.0-or-later
// Dados fixos do motor (S04-T14b): relógio do C++ e shaders QSB da S03 (bytes embutidos pelo CMake). C++ puro; o resto do motor está em motor.h.
#include "motor.h"
namespace obim {
double agora_ms() { return std::chrono::duration<double, std::milli>(Rel::now().time_since_epoch()).count(); }
const unsigned char QSB_VERT[] = {
#include "malha_vert.inc"
};
const unsigned char QSB_FRAG[] = {
#include "malha_frag.inc"
};
const size_t QSB_VERT_N = sizeof QSB_VERT, QSB_FRAG_N = sizeof QSB_FRAG;
}  // namespace obim
