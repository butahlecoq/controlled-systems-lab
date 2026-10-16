add_executable(observed_replay_tests tests/unit/controllers/observed_replay_tests.cpp)
target_link_libraries(observed_replay_tests PRIVATE CSL::controllers CSL::model doctest::doctest)
add_test(NAME observed_replay_tests COMMAND observed_replay_tests)
csl_test_target(observed_replay_tests controllers)
