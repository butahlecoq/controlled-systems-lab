add_executable(model_tests tests/unit/model/linear_system_tests.cpp)
target_link_libraries(model_tests PRIVATE CSL::model doctest::doctest Threads::Threads)
add_test(NAME model_tests COMMAND model_tests)
csl_test_target(model_tests model)

add_executable(affine_dynamics_tests tests/unit/model/affine_dynamics_test.cpp)
target_link_libraries(affine_dynamics_tests PRIVATE CSL::model CSL::sets doctest::doctest)
add_test(NAME affine_dynamics_tests COMMAND affine_dynamics_tests)
csl_test_target(affine_dynamics_tests model)

add_executable(observation_model_tests tests/unit/model/observation_model_test.cpp)
target_link_libraries(observation_model_tests PRIVATE CSL::model doctest::doctest)
add_test(NAME observation_model_tests COMMAND observation_model_tests)
csl_test_target(observation_model_tests model)

add_executable(model_public_client tests/installed/model_client.cpp)
target_link_libraries(model_public_client PRIVATE CSL::model)
add_test(NAME model_public_client COMMAND model_public_client)
csl_test_target(model_public_client model)
