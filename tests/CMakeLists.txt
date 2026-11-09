include(FetchContent)

# GoogleTest is fetched at configure time: nothing to install on the machine.
FetchContent_Declare(googletest
  URL https://github.com/google/googletest/archive/refs/tags/v1.15.2.zip
  URL_HASH SHA256=f179ec217f9b3b3f3c6e8b02d3e7eda997b49e4ce26d6b235c9053bec9c0bf9f
  DOWNLOAD_EXTRACT_TIMESTAMP TRUE)
set(gtest_force_shared_crt ON CACHE BOOL "" FORCE)  # same C runtime as our targets on MSVC
set(INSTALL_GTEST OFF CACHE BOOL "" FORCE)
set(BUILD_GMOCK OFF CACHE BOOL "" FORCE)
FetchContent_MakeAvailable(googletest)

set(TIRETWIN_REPORT_DIR ${CMAKE_BINARY_DIR}/reports)
file(MAKE_DIRECTORY ${TIRETWIN_REPORT_DIR})

# Registers a GoogleTest executable in CTest and makes it write a JUnit report,
# which is the input of the CI test widgets and of tools/traceability.py.
function(tiretwin_add_gtest name)
  add_test(NAME ${name}
    COMMAND ${name} --gtest_output=xml:${TIRETWIN_REPORT_DIR}/${name}.xml)
endfunction()

# --- Unit tests: one class at a time, synthetic inputs, no file -------------
add_executable(unit_tests
  unit/test_wheel_speed_filter.cpp
  unit/test_underinflation_detector.cpp)
target_link_libraries(unit_tests PRIVATE tiretwin::algo GTest::gtest_main tiretwin_warnings)
tiretwin_add_gtest(unit_tests)

# --- Python tooling needed to derive the tests and their stimuli ------------
find_package(Python3 3.10 REQUIRED COMPONENTS Interpreter)
execute_process(
  COMMAND ${Python3_EXECUTABLE} -c "import can, yaml"
  RESULT_VARIABLE TIRETWIN_PYTHON_DEPS_MISSING
  OUTPUT_QUIET ERROR_QUIET)
if(TIRETWIN_PYTHON_DEPS_MISSING)
  message(FATAL_ERROR
    "${Python3_EXECUTABLE} cannot import 'can' and 'yaml'.\n"
    "Install the tooling with: python -m pip install -r requirements-dev.txt\n"
    "(or point CMake to another interpreter with -DPython3_EXECUTABLE=...)")
endif()

set(TIRETWIN_PYTHON_SOURCES
  ${PROJECT_SOURCE_DIR}/data/generate_scenarios.py
  ${PROJECT_SOURCE_DIR}/tools/can_codec.py
  ${PROJECT_SOURCE_DIR}/tools/can_replay.py
  ${PROJECT_SOURCE_DIR}/tools/py_reference.py
  ${PROJECT_SOURCE_DIR}/tools/build_dataset.py)

# Test dataset: CAN traces (.log), replayed inputs (.csv), Python reference outputs (.ref.csv).
set(TIRETWIN_SCENARIO_DIR ${CMAKE_BINARY_DIR}/scenarios)
add_custom_command(
  OUTPUT ${TIRETWIN_SCENARIO_DIR}/dataset.stamp
  COMMAND ${Python3_EXECUTABLE} ${PROJECT_SOURCE_DIR}/tools/build_dataset.py --out ${TIRETWIN_SCENARIO_DIR}
  COMMAND ${CMAKE_COMMAND} -E touch ${TIRETWIN_SCENARIO_DIR}/dataset.stamp
  DEPENDS ${TIRETWIN_PYTHON_SOURCES}
  COMMENT "Generating CAN scenarios and Python reference outputs"
  VERBATIM)
add_custom_target(scenarios DEPENDS ${TIRETWIN_SCENARIO_DIR}/dataset.stamp)

# Test cases derived from the requirements.
set(TIRETWIN_GENERATED_DIR ${CMAKE_BINARY_DIR}/generated)
add_custom_command(
  OUTPUT ${TIRETWIN_GENERATED_DIR}/requirement_cases.inc
  COMMAND ${Python3_EXECUTABLE} ${PROJECT_SOURCE_DIR}/tools/gen_requirement_tests.py
          ${PROJECT_SOURCE_DIR}/requirements.yaml ${TIRETWIN_GENERATED_DIR}/requirement_cases.inc
  DEPENDS ${PROJECT_SOURCE_DIR}/requirements.yaml
          ${PROJECT_SOURCE_DIR}/tools/gen_requirement_tests.py
          ${PROJECT_SOURCE_DIR}/data/generate_scenarios.py
  COMMENT "Generating test cases from requirements.yaml"
  VERBATIM)

# --- Functional tests: one test per requirement verification ----------------
add_executable(functional_tests
  functional/test_requirements.cpp
  ${TIRETWIN_GENERATED_DIR}/requirement_cases.inc)
target_include_directories(functional_tests PRIVATE ${TIRETWIN_GENERATED_DIR})
target_compile_definitions(functional_tests PRIVATE
  TIRETWIN_SCENARIO_DIR="${TIRETWIN_SCENARIO_DIR}")
target_link_libraries(functional_tests PRIVATE tiretwin_io GTest::gtest_main tiretwin_warnings)
add_dependencies(functional_tests scenarios)
tiretwin_add_gtest(functional_tests)
