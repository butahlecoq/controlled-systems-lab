set(sets_data_header_source "${CMAKE_CURRENT_BINARY_DIR}/header-checks/sets_data_hpp.cpp")
file(GENERATE OUTPUT "${sets_data_header_source}" CONTENT "#include <csl/sets/data.hpp>\n")
add_library(header_sets_data_hpp OBJECT "${sets_data_header_source}")
target_link_libraries(header_sets_data_hpp PRIVATE CSL::sets)

add_executable(sets_tests tests/unit/sets/data_tests.cpp)
target_link_libraries(sets_tests PRIVATE CSL::sets doctest::doctest)
add_test(NAME sets_tests COMMAND sets_tests)
csl_test_target(sets_tests sets)

add_executable(sets_public_client tests/installed/sets_client.cpp)
target_link_libraries(sets_public_client PRIVATE CSL::sets)
add_test(NAME sets_public_client COMMAND sets_public_client)
csl_test_target(sets_public_client sets)
