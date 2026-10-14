add_executable(scenario_loader_tests tests/unit/input/scenario_loader_tests.cpp)
target_link_libraries(scenario_loader_tests PRIVATE CSL::input doctest::doctest)
add_test(NAME scenario_loader_tests COMMAND scenario_loader_tests)
csl_test_target(scenario_loader_tests input)

add_executable(scenario_file_tests tests/contract/input/scenario_file_tests.cpp)
target_link_libraries(scenario_file_tests PRIVATE CSL::input doctest::doctest)
add_test(NAME scenario_file_tests COMMAND scenario_file_tests "${CMAKE_CURRENT_SOURCE_DIR}" "${CMAKE_CURRENT_BINARY_DIR}/input-file-fixtures")
csl_test_target(scenario_file_tests input)

add_executable(scenario_template_catalogue_tests tests/examples/scenario_template_catalogue_tests.cpp)
target_link_libraries(scenario_template_catalogue_tests PRIVATE CSL::input doctest::doctest)
target_compile_definitions(scenario_template_catalogue_tests PRIVATE
    CSL_SCENARIO_TEMPLATE_DIR="${CMAKE_CURRENT_SOURCE_DIR}/examples/scenarios")
add_test(NAME scenario_template_catalogue_tests COMMAND scenario_template_catalogue_tests)
csl_test_target(scenario_template_catalogue_tests input)

add_executable(input_public_client tests/installed/input_client.cpp)
target_link_libraries(input_public_client PRIVATE CSL::input)
add_test(NAME input_public_client COMMAND input_public_client)
csl_test_target(input_public_client input)
