add_executable(validator_tests tests/unit/problem/validator_tests.cpp)
target_link_libraries(validator_tests PRIVATE CSL::resolved_problem CSL::optimization doctest::doctest)
add_test(NAME validator_tests COMMAND validator_tests)
csl_test_target(validator_tests problem)

add_executable(resolved_problem_public_client tests/installed/resolved_problem_client.cpp)
target_link_libraries(resolved_problem_public_client PRIVATE CSL::resolved_problem)
add_test(NAME resolved_problem_public_client COMMAND resolved_problem_public_client)
csl_test_target(resolved_problem_public_client problem)

add_executable(problem_public_client tests/installed/problem_client.cpp)
target_link_libraries(problem_public_client PRIVATE CSL::problem)
add_test(NAME problem_public_client COMMAND problem_public_client)
csl_test_target(problem_public_client problem)

add_executable(problem_tests tests/unit/problem/data_tests.cpp)
target_link_libraries(problem_tests PRIVATE CSL::problem doctest::doctest Threads::Threads)
add_test(NAME problem_tests COMMAND problem_tests)
csl_test_target(problem_tests problem)

add_executable(caller_example probes/core-01/caller_example.cpp)
target_link_libraries(caller_example PRIVATE CSL::resolved_core Threads::Threads)
add_test(NAME caller_example COMMAND caller_example)
csl_test_target(caller_example problem)
