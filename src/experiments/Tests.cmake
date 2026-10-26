add_executable(batch_runner_tests tests/unit/experiments/batch_runner_tests.cpp)
target_link_libraries(batch_runner_tests PRIVATE CSL::experiments CSL::strategy_ts01 doctest::doctest)
target_include_directories(batch_runner_tests SYSTEM PRIVATE ${csl_json_SOURCE_DIR}/single_include)
target_compile_definitions(batch_runner_tests PRIVATE CSL_SWEEP_RUN_FIXTURE="${CMAKE_CURRENT_SOURCE_DIR}/tests/artifacts/fixtures/run-statistics-v3.json")
add_test(NAME batch_runner_tests COMMAND batch_runner_tests)
csl_test_target(batch_runner_tests experiments)

add_executable(replay_comparison_tests tests/integration/replay_comparison.cpp)
target_link_libraries(replay_comparison_tests PRIVATE CSL::experiments doctest::doctest)
target_include_directories(replay_comparison_tests SYSTEM PRIVATE ${csl_json_SOURCE_DIR}/single_include)
target_compile_definitions(replay_comparison_tests PRIVATE
  CSL_VIZ04_REPLAY_FIXTURE="${CMAKE_CURRENT_SOURCE_DIR}/docs/examples/viz04-replay-comparison.json")
add_test(NAME replay_comparison_tests COMMAND replay_comparison_tests)
csl_test_target(replay_comparison_tests experiments)
