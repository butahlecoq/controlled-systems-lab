add_executable(batch_runner_tests tests/unit/experiments/batch_runner_tests.cpp)
target_link_libraries(batch_runner_tests PRIVATE CSL::experiments CSL::strategy_ts01 doctest::doctest)
add_test(NAME batch_runner_tests COMMAND batch_runner_tests)
csl_test_target(batch_runner_tests experiments)
