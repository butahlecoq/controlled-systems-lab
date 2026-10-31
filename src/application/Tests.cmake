add_executable(application_comparison_tests tests/application/comparison_tests.cpp)
target_link_libraries(application_comparison_tests PRIVATE CSL::application doctest::doctest)
add_test(NAME application_comparison_tests COMMAND application_comparison_tests)
csl_test_target(application_comparison_tests application)

if(TARGET CSL::highs_lp AND TARGET CSL::highs_convex AND TARGET CSL::qhull_conversion)
  add_executable(application_comparison_integration_tests tests/application/comparison_integration_tests.cpp)
  target_link_libraries(application_comparison_integration_tests PRIVATE
    CSL::application CSL::strategy_a CSL::strategy_b CSL::witness_selector
    CSL::affine_sum CSL::approximation CSL::qhull_conversion CSL::highs_lp CSL::highs_convex doctest::doctest)
  target_include_directories(application_comparison_integration_tests SYSTEM PRIVATE ${csl_json_SOURCE_DIR}/single_include)
  add_test(NAME application_comparison_integration_tests COMMAND application_comparison_integration_tests)
  csl_test_target(application_comparison_integration_tests application)
endif()
