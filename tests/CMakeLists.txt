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
