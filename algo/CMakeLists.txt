# The algorithm library: pure C++17, no I/O, no dependency.
# This is the "software under test" of the whole repository.
add_library(tiretwin_algo STATIC
  src/wheel_speed_filter.cpp
  src/underinflation_detector.cpp)
add_library(tiretwin::algo ALIAS tiretwin_algo)

target_include_directories(tiretwin_algo PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>)
target_compile_features(tiretwin_algo PUBLIC cxx_std_17)
target_link_libraries(tiretwin_algo PRIVATE tiretwin_warnings)

install(TARGETS tiretwin_algo ARCHIVE DESTINATION lib)
install(DIRECTORY include/ DESTINATION include)
