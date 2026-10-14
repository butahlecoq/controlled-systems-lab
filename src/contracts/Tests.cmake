add_executable(contract_tests probes/core-01/contract_tests.cpp)
target_link_libraries(contract_tests PRIVATE CSL::contracts doctest::doctest)
add_test(NAME contract_tests COMMAND contract_tests)
csl_test_target(contract_tests contracts)

add_executable(public_client tests/contract/public_client.cpp)
target_link_libraries(public_client PRIVATE CSL::contracts)
set_target_properties(public_client PROPERTIES CXX_EXTENSIONS OFF)
add_test(NAME public_client COMMAND public_client)
set_tests_properties(public_client PROPERTIES
    PASS_REGULAR_EXPRESSION "Public contract client: shape guards and literal affine fixture passed")
csl_test_target(public_client contracts)
