# SPDX-License-Identifier: AGPL-3.0-or-later
# Módulo `obimcore`: ponte Python/C++ sobre o MESMO ifcopenshell.file do Python.
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
find_package(Qt6 COMPONENTS Core Gui Widgets GuiPrivate REQUIRED)  # GuiPrivate: QRhi é semi-público (versão do Qt fixa na trava). Só Qt6::Gui NÃO compila (rhi/qrhi.h não é achado; testado no Linux)

# Versão e build do ifcopenshell vistos na compilação (a trava do ambiente fixa os dois; R1-a compara com a execução).
file(GLOB META "${CONDA}/conda-meta/ifcopenshell-[0-9]*.json")
list(GET META 0 META)
file(READ "${META}" META_JSON)
string(JSON IFC_VERSAO GET "${META_JSON}" version)
string(JSON IFC_BUILD GET "${META_JSON}" build)
message(STATUS "ifcopenshell ${IFC_VERSAO} build ${IFC_BUILD}")

# O .pyd/.so fica dentro do pacote `obimcore` (a pasta de saída), ao lado do __init__.py gerado pelo build.sh.
file(TO_CMAKE_PATH "${OBIM_SAIDA}" OBIM_SAIDA)
# Shaders do viewport Python (QSB já compilados) embutidos como bytes: o módulo não procura arquivo em tempo de execução.
set(OBIM_SHADERS "${CMAKE_CURRENT_SOURCE_DIR}/../../viewport_qrhi/shaders" CACHE PATH "shaders QSB do viewport Python")
foreach(sh malha_vert malha_frag)
  string(REPLACE "_" "." arq "${sh}")
  set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS "${OBIM_SHADERS}/${arq}.qsb")
  file(READ "${OBIM_SHADERS}/${arq}.qsb" hex HEX)
  string(REGEX REPLACE "([0-9a-f][0-9a-f])" "0x\\1," hex "${hex}")
  file(WRITE "${CMAKE_CURRENT_BINARY_DIR}/${sh}.inc" "${hex}")
endforeach()
# Camada C++ PURA: sem nanobind e sem Python; um executável Qt liga esta biblioteca. Posição independente (entra no módulo, que é .so/.pyd).
add_library(obimcore_nucleo STATIC nucleo/malha.cpp nucleo/cena.cpp nucleo/camera.cpp nucleo/selecao.cpp nucleo/motor.cpp)
set_target_properties(obimcore_nucleo PROPERTIES POSITION_INDEPENDENT_CODE ON)
target_include_directories(obimcore_nucleo PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}/nucleo" PRIVATE "${CMAKE_CURRENT_BINARY_DIR}" ${OpenCASCADE_INCLUDE_DIR})
target_compile_definitions(obimcore_nucleo PUBLIC OBIM_IFC_VERSAO="${IFC_VERSAO}" OBIM_IFC_BUILD="${IFC_BUILD}")
target_link_libraries(obimcore_nucleo PUBLIC
  IfcOpenShell::IfcParse IfcOpenShell::IfcGeom IfcOpenShell::parse_schema_ifc2x3 IfcOpenShell::parse_schema_ifc4
  IfcOpenShell::parse_schema_ifc4x1 IfcOpenShell::parse_schema_ifc4x3_add2
  TKernel Qt6::Core Qt6::Gui Qt6::Widgets Qt6::GuiPrivate)
# Módulo Python: só a ponte (adapta tipos do Python para o núcleo). Mutex: `Motor::m_` antes de `DadosCena::m_`; o Python é dono, o C++ não guarda endereço.
nanobind_add_module(_obimcore ponte.cpp ponte_malha.cpp ponte_viewport.cpp)
target_link_libraries(_obimcore PRIVATE obimcore_nucleo)
set_target_properties(_obimcore PROPERTIES LIBRARY_OUTPUT_DIRECTORY "${OBIM_SAIDA}/obimcore")
foreach(cfg DEBUG RELEASE RELWITHDEBINFO MINSIZEREL)
  set_target_properties(_obimcore PROPERTIES LIBRARY_OUTPUT_DIRECTORY_${cfg} "${OBIM_SAIDA}/obimcore")
endforeach()
target_include_directories(_obimcore PRIVATE ${OpenCASCADE_INCLUDE_DIR})
if(MSVC)
  target_compile_options(obimcore_nucleo PUBLIC /utf-8)
endif()
if(WIN32)
  # O Boost aparece nas dependências só pelo nome (boost_*.lib): o MSVC precisa saber onde o conda guarda as bibliotecas.
  target_link_directories(obimcore_nucleo PUBLIC "${CONDA}/Library/lib")
  target_link_libraries(obimcore_nucleo PUBLIC winmm)  # winmm: timeBeginPeriod (relógio de 1 ms para a thread de desenho)
  target_link_libraries(_obimcore PRIVATE psapi)
elseif(UNIX AND NOT APPLE)
  # As bibliotecas dos esquemas se registram ao carregar; sem isto o ligador as descarta.
  target_link_options(obimcore_nucleo INTERFACE -Wl,--no-as-needed)
  # O MESMO binário roda no pacote (AppImage) e no ambiente de desenvolvimento. Só um caminho relativo ao próprio arquivo:
  # no pacote, app/obimcore -> ../../env/lib (bibliotecas do pacote). Fora dele esse caminho não existe e o carregador cai no RPATH do
  # executável do Python do conda ($ORIGIN/../lib = bibliotecas do ambiente ativo). RPATH, não RUNPATH: só o RPATH do executável vale de reserva.
  # O compilador do conda ainda acrescenta o caminho absoluto do ambiente; o build.sh o tira depois da ligação.
  set_target_properties(_obimcore PROPERTIES BUILD_WITH_INSTALL_RPATH ON INSTALL_RPATH "$ORIGIN/../../env/lib")
  target_link_options(_obimcore PRIVATE -Wl,--disable-new-dtags)
endif()
