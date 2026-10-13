# SPDX-License-Identifier: AGPL-3.0-or-later
# Módulo `obimcore` (S04-T03): ponte Python/C++ sobre o MESMO ifcopenshell.file do Python.
# Liga pelo IfcOpenShellConfig.cmake do pacote conda (ADR-005 §7.1 item 3); não copia cabeçalho nem compila fonte do IfcOpenShell.
cmake_minimum_required(VERSION 3.20)
project(obimcore LANGUAGES CXX)
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
# Windows: sempre Release (a biblioteca padrão de depuração é incompatível com a do pacote).
if(NOT CMAKE_BUILD_TYPE AND NOT CMAKE_CONFIGURATION_TYPES)
  set(CMAKE_BUILD_TYPE Release)
endif()

if(NOT DEFINED ENV{CONDA_PREFIX})
  message(FATAL_ERROR "CONDA_PREFIX não definido: ative o ambiente openbim")
endif()
file(TO_CMAKE_PATH "$ENV{CONDA_PREFIX}" CONDA)
list(APPEND CMAKE_PREFIX_PATH "${CONDA}" "${CONDA}/Library")

find_package(Python 3.12 REQUIRED COMPONENTS Interpreter Development.Module)
execute_process(COMMAND "${Python_EXECUTABLE}" -m nanobind --cmake_dir
                OUTPUT_VARIABLE NB_DIR OUTPUT_STRIP_TRAILING_WHITESPACE COMMAND_ERROR_IS_FATAL ANY)
list(APPEND CMAKE_PREFIX_PATH "${NB_DIR}")
find_package(nanobind CONFIG REQUIRED)
find_package(IfcOpenShell CONFIG REQUIRED)
find_package(OpenCASCADE CONFIG REQUIRED)
find_package(Qt6 COMPONENTS Core Gui Widgets GuiPrivate REQUIRED)  # GuiPrivate: QRhi é semi-público (R13; versão do Qt fixa na trava)

# Versão e build do ifcopenshell vistos na compilação (a trava do ambiente fixa os dois; R1-a compara com a execução).
file(GLOB META "${CONDA}/conda-meta/ifcopenshell-[0-9]*.json")
list(GET META 0 META)
file(READ "${META}" META_JSON)
string(JSON IFC_VERSAO GET "${META_JSON}" version)
string(JSON IFC_BUILD GET "${META_JSON}" build)
message(STATUS "ifcopenshell ${IFC_VERSAO} build ${IFC_BUILD}")

# O .pyd/.so fica dentro do pacote `obimcore` (a pasta de saída), ao lado do __init__.py gerado pelo build.sh.
file(TO_CMAKE_PATH "${OBIM_SAIDA}" OBIM_SAIDA)
# Shaders da S03 (QSB já compilados) embutidos como bytes: o módulo não procura arquivo em tempo de execução.
set(OBIM_SHADERS "${CMAKE_CURRENT_SOURCE_DIR}/../../viewport_qrhi/shaders" CACHE PATH "shaders QSB da S03")
foreach(sh malha_vert malha_frag)
  string(REPLACE "_" "." arq "${sh}")
  set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS "${OBIM_SHADERS}/${arq}.qsb")
  file(READ "${OBIM_SHADERS}/${arq}.qsb" hex HEX)
  string(REGEX REPLACE "([0-9a-f][0-9a-f])" "0x\\1," hex "${hex}")
  file(WRITE "${CMAKE_CURRENT_BINARY_DIR}/${sh}.inc" "${hex}")
endforeach()
nanobind_add_module(_obimcore ponte.cpp malha.cpp viewport.cpp)
target_include_directories(_obimcore PRIVATE "${CMAKE_CURRENT_BINARY_DIR}")
set_target_properties(_obimcore PROPERTIES LIBRARY_OUTPUT_DIRECTORY "${OBIM_SAIDA}/obimcore")
foreach(cfg DEBUG RELEASE RELWITHDEBINFO MINSIZEREL)
  set_target_properties(_obimcore PROPERTIES LIBRARY_OUTPUT_DIRECTORY_${cfg} "${OBIM_SAIDA}/obimcore")
endforeach()
target_compile_definitions(_obimcore PRIVATE OBIM_IFC_VERSAO="${IFC_VERSAO}" OBIM_IFC_BUILD="${IFC_BUILD}")
target_include_directories(_obimcore PRIVATE ${OpenCASCADE_INCLUDE_DIR})
target_link_libraries(_obimcore PRIVATE
  IfcOpenShell::IfcParse IfcOpenShell::IfcGeom IfcOpenShell::parse_schema_ifc2x3 IfcOpenShell::parse_schema_ifc4
  IfcOpenShell::parse_schema_ifc4x1 IfcOpenShell::parse_schema_ifc4x3_add2
  TKernel Qt6::Core Qt6::Gui Qt6::Widgets Qt6::GuiPrivate)
if(MSVC)
  target_compile_options(_obimcore PRIVATE /utf-8)
endif()
if(WIN32)
  # O Boost aparece nas dependências só pelo nome (boost_*.lib): o MSVC precisa saber onde o conda guarda as bibliotecas.
  target_link_directories(_obimcore PRIVATE "${CONDA}/Library/lib")
  target_link_libraries(_obimcore PRIVATE psapi winmm)  # winmm: timeBeginPeriod (relógio de 1 ms para a thread de desenho)
elseif(UNIX AND NOT APPLE)
  # As bibliotecas dos esquemas se registram ao carregar; sem isto o ligador as descarta.
  target_link_options(_obimcore PRIVATE -Wl,--no-as-needed)
endif()
