add_executable(execution_tests tests/unit/execution/executor_tests.cpp)
target_link_libraries(execution_tests PRIVATE CSL::execution CSL::optimization doctest::doctest Threads::Threads)
add_test(NAME execution_tests COMMAND execution_tests)
csl_test_target(execution_tests execution)

add_executable(execution_public_client tests/installed/execution_client.cpp)
target_link_libraries(execution_public_client PRIVATE CSL::execution)
add_test(NAME execution_public_client COMMAND execution_public_client)
csl_test_target(execution_public_client execution)
