if(TARGET CSL::highs_convex AND TARGET CSL::highs_lp)
  add_executable(terminal_minimizers_tests tests/unit/synthesis/terminal_minimizers_tests.cpp)
  target_link_libraries(terminal_minimizers_tests PRIVATE CSL::terminal_minimizers CSL::highs_lp CSL::highs_convex doctest::doctest)
  add_test(NAME terminal_minimizers_tests COMMAND terminal_minimizers_tests)
  csl_test_target(terminal_minimizers_tests synthesis)
endif()

add_executable(terminal_minimizers_public_client tests/installed/terminal_minimizers_client.cpp)
target_link_libraries(terminal_minimizers_public_client PRIVATE CSL::terminal_minimizers)
add_test(NAME terminal_minimizers_public_client COMMAND terminal_minimizers_public_client)
csl_test_target(terminal_minimizers_public_client synthesis)

if(TARGET CSL::highs_convex AND TARGET CSL::highs_lp AND TARGET CSL::qhull_conversion)
  add_executable(strategy_a_tests tests/synthesis/strategy_a/strategy_tests.cpp)
  target_link_libraries(strategy_a_tests PRIVATE CSL::strategy_a CSL::affine_sum CSL::qhull_conversion CSL::highs_lp CSL::highs_convex doctest::doctest)
  target_compile_features(strategy_a_tests PRIVATE cxx_std_20)

  add_test(NAME strategy_a_tests COMMAND strategy_a_tests)
  csl_strict_warnings(strategy_a_tests)
  csl_test_target(strategy_a_tests synthesis)

  add_executable(strategy_a_runtime_receipt_tests tests/synthesis/strategy_a/runtime_receipt_tests.cpp)
  target_link_libraries(strategy_a_runtime_receipt_tests PRIVATE CSL::strategy_a CSL::affine_sum CSL::qhull_conversion CSL::highs_lp CSL::highs_convex doctest::doctest)
  target_include_directories(strategy_a_runtime_receipt_tests PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/src/registry)
  target_compile_features(strategy_a_runtime_receipt_tests PRIVATE cxx_std_20)
  add_test(NAME strategy_a_runtime_receipt_tests COMMAND strategy_a_runtime_receipt_tests)
  csl_strict_warnings(strategy_a_runtime_receipt_tests)
  csl_test_target(strategy_a_runtime_receipt_tests synthesis)
endif()

add_executable(strategy_a_public_client tests/synthesis/strategy_a/public_client.cpp)
target_compile_features(strategy_a_public_client PRIVATE cxx_std_20)
target_link_libraries(strategy_a_public_client PRIVATE CSL::strategy_a)
add_test(NAME strategy_a_public_client COMMAND strategy_a_public_client)
csl_test_target(strategy_a_public_client synthesis)

add_executable(control_recovery_tests tests/unit/synthesis/control_recovery_tests.cpp)
target_link_libraries(control_recovery_tests PRIVATE CSL::control_recovery doctest::doctest)
add_test(NAME control_recovery_tests COMMAND control_recovery_tests)
csl_test_target(control_recovery_tests synthesis)

add_executable(finite_action_histories_tests tests/unit/synthesis/finite_action_histories_tests.cpp)
target_link_libraries(finite_action_histories_tests PRIVATE CSL::finite_action_histories doctest::doctest)
add_test(NAME finite_action_histories_tests COMMAND finite_action_histories_tests)
csl_test_target(finite_action_histories_tests synthesis)

add_executable(finite_mixed_branch_tests tests/unit/synthesis/finite_mixed_branch_tests.cpp)
target_link_libraries(finite_mixed_branch_tests PRIVATE CSL::finite_mixed_branch doctest::doctest)
add_test(NAME finite_mixed_branch_tests COMMAND finite_mixed_branch_tests)
csl_test_target(finite_mixed_branch_tests synthesis)

if(TARGET CSL::highs_convex AND TARGET CSL::highs_lp AND TARGET CSL::qhull_conversion)
  add_executable(finite_mixed_branch_strategy_tests
    tests/synthesis/finite_mixed_branch_strategy_tests.cpp)
  target_link_libraries(finite_mixed_branch_strategy_tests PRIVATE CSL::finite_mixed_branch
    CSL::strategy_a CSL::affine_sum CSL::qhull_conversion CSL::highs_lp CSL::highs_convex
    CSL::finite_action_nominal
    highs doctest::doctest)
  add_test(NAME finite_mixed_branch_strategy_tests COMMAND finite_mixed_branch_strategy_tests)
  csl_strict_warnings(finite_mixed_branch_strategy_tests)
  csl_test_target(finite_mixed_branch_strategy_tests synthesis)
endif()

add_executable(finite_mixed_branch_public_client tests/installed/finite_mixed_branch_client.cpp)
target_link_libraries(finite_mixed_branch_public_client PRIVATE CSL::finite_mixed_branch)
add_test(NAME finite_mixed_branch_public_client COMMAND finite_mixed_branch_public_client)
csl_test_target(finite_mixed_branch_public_client synthesis)

add_executable(control_recovery_public_client tests/installed/control_recovery_client.cpp)
target_link_libraries(control_recovery_public_client PRIVATE CSL::control_recovery)
add_test(NAME control_recovery_public_client COMMAND control_recovery_public_client)
csl_test_target(control_recovery_public_client synthesis)

add_executable(hybrid_path_program_tests tests/unit/synthesis/hybrid_path_program_tests.cpp)
target_link_libraries(hybrid_path_program_tests PRIVATE CSL::hybrid_path_program doctest::doctest)
target_include_directories(hybrid_path_program_tests PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/src/synthesis)
add_test(NAME hybrid_path_program_tests COMMAND hybrid_path_program_tests)
csl_test_target(hybrid_path_program_tests synthesis)

add_executable(hybrid_reachability_public_client tests/installed/hybrid_reachability_client.cpp)
target_link_libraries(hybrid_reachability_public_client PRIVATE CSL::hybrid_path_program)
add_test(NAME hybrid_reachability_public_client COMMAND hybrid_reachability_public_client)
csl_test_target(hybrid_reachability_public_client synthesis)

if(TARGET CSL::highs_convex AND TARGET CSL::highs_lp AND TARGET CSL::strategy_a AND TARGET CSL::affine_sum AND TARGET CSL::qhull_conversion)
  add_executable(direct_joint_strategy_tests tests/synthesis/strategy_b/direct_joint_tests.cpp)
  target_link_libraries(direct_joint_strategy_tests PRIVATE CSL::strategy_b CSL::strategy_a CSL::problem CSL::affine_sum CSL::qhull_conversion CSL::highs_lp CSL::highs_convex CSL::artifacts CSL::input doctest::doctest)
  target_include_directories(direct_joint_strategy_tests PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/src/registry)
  target_compile_definitions(direct_joint_strategy_tests PRIVATE
    CSL_TEMPORAL_SCENARIO_PATH="${CMAKE_CURRENT_SOURCE_DIR}/examples/scenarios/temporal-slew-integrator.json"
    CSL_MPC02_SCENARIO_DIR="${CMAKE_CURRENT_SOURCE_DIR}/examples/scenarios")
  add_test(NAME direct_joint_strategy_tests COMMAND direct_joint_strategy_tests)
  csl_test_target(direct_joint_strategy_tests synthesis)
endif()

add_executable(strategy_ts01_analytic_profile_tests tests/synthesis/strategy_ts01/analytic_profile_tests.cpp)
target_link_libraries(strategy_ts01_analytic_profile_tests PRIVATE CSL::strategy_ts01 doctest::doctest)
target_include_directories(strategy_ts01_analytic_profile_tests PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/src/registry)
target_compile_features(strategy_ts01_analytic_profile_tests PRIVATE cxx_std_20)

add_test(NAME strategy_ts01_analytic_profile_tests COMMAND strategy_ts01_analytic_profile_tests)
csl_strict_warnings(strategy_ts01_analytic_profile_tests)
csl_test_target(strategy_ts01_analytic_profile_tests synthesis)

add_executable(strategy_ts01_artifact_policy_tests tests/synthesis/strategy_ts01/artifact_policy_tests.cpp)
target_link_libraries(strategy_ts01_artifact_policy_tests PRIVATE CSL::strategy_ts01 CSL::artifacts doctest::doctest)
target_compile_features(strategy_ts01_artifact_policy_tests PRIVATE cxx_std_20)

add_test(NAME strategy_ts01_artifact_policy_tests COMMAND strategy_ts01_artifact_policy_tests)
csl_strict_warnings(strategy_ts01_artifact_policy_tests)
csl_test_target(strategy_ts01_artifact_policy_tests synthesis)

if(TARGET CSL::highs_convex AND TARGET CSL::highs_lp AND TARGET CSL::qhull_conversion)
  add_executable(witness_selector_tests tests/synthesis/witness_selector_tests.cpp)
  target_link_libraries(witness_selector_tests PRIVATE CSL::witness_selector CSL::strategy_a CSL::strategy_b CSL::affine_sum CSL::qhull_conversion CSL::highs_lp CSL::highs_convex doctest::doctest)
  add_test(NAME witness_selector_tests COMMAND witness_selector_tests)
  csl_test_target(witness_selector_tests synthesis)
endif()
