# SPDX-License-Identifier: AGPL-3.0-or-later
cmake_minimum_required(VERSION 3.20)
project(cpp_probe_3b LANGUAGES CXX)
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(IfcOpenShell CONFIG REQUIRED)

add_executable(probe_3b probe_3b.cpp)
target_link_libraries(probe_3b PRIVATE IfcOpenShell::IfcParse
                      IfcOpenShell::parse_schema_ifc4 IfcOpenShell::parse_schema_ifc2x3)
# As bibliotecas dos esquemas se registram ao carregar; sem isso o ligador do Linux as descarta.
if(UNIX AND NOT APPLE)
  target_link_options(probe_3b PRIVATE -Wl,--no-as-needed)
endif()
