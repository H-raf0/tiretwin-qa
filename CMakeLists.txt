cmake_minimum_required(VERSION 3.21)

project(tiretwin_qa
  VERSION 1.0.0
  DESCRIPTION "Functional validation bench for a C++ indirect TPMS algorithm"
  LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

option(TIRETWIN_BUILD_TESTS "Build the GoogleTest suites and the test dataset" ON)
option(TIRETWIN_COVERAGE "Instrument the build for gcov/gcovr (GCC or Clang)" OFF)

# Single-config generators (Ninja, Makefiles) default to an optimised build.
if(NOT CMAKE_BUILD_TYPE AND NOT CMAKE_CONFIGURATION_TYPES)
  set(CMAKE_BUILD_TYPE Release CACHE STRING "Build type" FORCE)
endif()

# Warnings are part of the quality gate: they are errors for our own targets.
add_library(tiretwin_warnings INTERFACE)
if(MSVC)
  target_compile_options(tiretwin_warnings INTERFACE /W4 /WX /permissive-)
  # fopen/getenv are fine here; keep the code portable instead of using the *_s variants.
  target_compile_definitions(tiretwin_warnings INTERFACE _CRT_SECURE_NO_WARNINGS)
else()
  target_compile_options(tiretwin_warnings INTERFACE
    -Wall -Wextra -Wpedantic -Wconversion -Wshadow -Werror)
endif()

# MinGW: link the GCC runtime statically. Otherwise the executables load whichever
# libstdc++-6.dll comes first in PATH (Git for Windows ships its own, with a
# different ABI), which crashes at run time.
if(MINGW)
  add_link_options(-static)
endif()

if(TIRETWIN_COVERAGE)
  if(MSVC)
    message(FATAL_ERROR "TIRETWIN_COVERAGE requires GCC or Clang")
  endif()
  add_compile_options(--coverage -O0 -g)
  add_link_options(--coverage)
endif()

add_subdirectory(algo)
add_subdirectory(cli)

if(TIRETWIN_BUILD_TESTS)
  enable_testing()
  add_subdirectory(tests)
endif()

# `cmake --build --preset coverage --target coverage`, to be run after the tests.
# Only the algorithm library is measured: it is the software under test.
if(TIRETWIN_COVERAGE)
  find_program(GCOVR_EXECUTABLE gcovr REQUIRED)
  add_custom_target(coverage
    COMMAND ${CMAKE_COMMAND} -E make_directory ${CMAKE_BINARY_DIR}/coverage
    COMMAND ${GCOVR_EXECUTABLE}
            --root ${PROJECT_SOURCE_DIR} --filter ${PROJECT_SOURCE_DIR}/algo/
            --txt --print-summary
            --xml ${CMAKE_BINARY_DIR}/coverage/cobertura.xml
            --html-details ${CMAKE_BINARY_DIR}/coverage/index.html
            --fail-under-line 90
            ${CMAKE_BINARY_DIR}
    WORKING_DIRECTORY ${PROJECT_SOURCE_DIR}
    COMMENT "Measuring the coverage of the algorithm library with gcovr"
    VERBATIM)
endif()
