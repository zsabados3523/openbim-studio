# SPDX-License-Identifier: AGPL-3.0-or-later
cmake_minimum_required(VERSION 3.20)
project(cpp_probe LANGUAGES CXX)

find_package(Python 3.12 REQUIRED COMPONENTS Interpreter Development.Module)
execute_process(COMMAND "${Python_EXECUTABLE}" -m nanobind --cmake_dir
                OUTPUT_VARIABLE NB_DIR OUTPUT_STRIP_TRAILING_WHITESPACE)
list(APPEND CMAKE_PREFIX_PATH "${NB_DIR}")
find_package(nanobind CONFIG REQUIRED)
find_package(OpenCASCADE CONFIG REQUIRED)
find_package(Qt6 COMPONENTS Core REQUIRED)

nanobind_add_module(cpp_probe probe.cpp)
target_include_directories(cpp_probe PRIVATE ${OpenCASCADE_INCLUDE_DIR})
target_link_libraries(cpp_probe PRIVATE TKPrim TKBRep TKTopAlgo TKGeomBase TKMath TKernel Qt6::Core)
