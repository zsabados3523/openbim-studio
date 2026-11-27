# SPDX-License-Identifier: AGPL-3.0-or-later
# Modulo `obimvisib`: motor nativo de linhas visiveis (esqueleto N1, sem Qt nem IfcOpenShell).
cmake_minimum_required(VERSION 3.20)
project(obim_visib LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

if(NOT CMAKE_BUILD_TYPE AND NOT CMAKE_CONFIGURATION_TYPES)
  set(CMAKE_BUILD_TYPE Release)
endif()

if(NOT MSVC)
  foreach(var CMAKE_CXX_FLAGS CMAKE_CXX_FLAGS_RELEASE CMAKE_CXX_FLAGS_RELWITHDEBINFO)
    if(DEFINED ${var})
      string(REPLACE "-O3" "-O2" ${var} "${${var}}")
    endif()
  endforeach()
endif()

if(NOT DEFINED ENV{CONDA_PREFIX})
  message(FATAL_ERROR "CONDA_PREFIX nao definido: ative o ambiente openbim")
endif()
file(TO_CMAKE_PATH "$ENV{CONDA_PREFIX}" CONDA)
list(APPEND CMAKE_PREFIX_PATH "${CONDA}" "${CONDA}/Library")

find_package(Python 3.12 REQUIRED COMPONENTS Interpreter Development.Module)
execute_process(COMMAND "${Python_EXECUTABLE}" -m nanobind --cmake_dir
                OUTPUT_VARIABLE NB_DIR OUTPUT_STRIP_TRAILING_WHITESPACE COMMAND_ERROR_IS_FATAL ANY)
list(APPEND CMAKE_PREFIX_PATH "${NB_DIR}")
find_package(nanobind CONFIG REQUIRED)

nanobind_add_module(_obimvisib NOMINSIZE ponte_visib.cpp)

if(MSVC)
  set(OBIM_VISIB_FLAGS_FP /O2 /fp:precise)
  target_compile_options(_obimvisib PRIVATE /utf-8)
else()
  set(OBIM_VISIB_FLAGS_FP -O2 -ffp-contract=off)
endif()
target_compile_options(_obimvisib PRIVATE ${OBIM_VISIB_FLAGS_FP})
string(JOIN " " OBIM_VISIB_FLAGS_FP_STR ${OBIM_VISIB_FLAGS_FP})
target_compile_definitions(_obimvisib PRIVATE OBIM_VISIB_FLAGS_FP="${OBIM_VISIB_FLAGS_FP_STR}")

if(DEFINED OBIM_SAIDA)
  file(TO_CMAKE_PATH "${OBIM_SAIDA}" OBIM_SAIDA_CMAKE)
  set_target_properties(_obimvisib PROPERTIES LIBRARY_OUTPUT_DIRECTORY "${OBIM_SAIDA_CMAKE}/obimvisib")
  foreach(cfg DEBUG RELEASE RELWITHDEBINFO MINSIZEREL)
    set_target_properties(_obimvisib PROPERTIES LIBRARY_OUTPUT_DIRECTORY_${cfg} "${OBIM_SAIDA_CMAKE}/obimvisib")
  endforeach()
endif()

if(UNIX AND NOT APPLE)
  set_target_properties(_obimvisib PROPERTIES BUILD_WITH_INSTALL_RPATH ON INSTALL_RPATH "$ORIGIN/../../env/lib")
  target_link_options(_obimvisib PRIVATE -Wl,--disable-new-dtags)
endif()
