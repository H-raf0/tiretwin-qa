# CSV I/O shared by the command-line runner and the functional tests.
# Kept out of tiretwin_algo on purpose: the algorithm library stays free of file I/O.
add_library(tiretwin_io STATIC csv_io.cpp)
target_include_directories(tiretwin_io PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})
target_link_libraries(tiretwin_io PUBLIC tiretwin::algo PRIVATE tiretwin_warnings)

add_executable(tiretwin_cli main.cpp)
target_link_libraries(tiretwin_cli PRIVATE tiretwin_io tiretwin_warnings)

install(TARGETS tiretwin_cli RUNTIME DESTINATION bin)
