cmake_minimum_required(VERSION 3.31)
project(CSLInstalledConsumer LANGUAGES CXX)
find_package(CSL 0.1 CONFIG REQUIRED)
add_executable(installed_public_headers_client public_headers_client.cpp)
target_link_libraries(installed_public_headers_client PRIVATE CSL::numeric)
set_target_properties(installed_public_headers_client PROPERTIES CXX_EXTENSIONS OFF)
add_test(NAME installed_public_headers_client COMMAND installed_public_headers_client)
set_tests_properties(installed_public_headers_client PROPERTIES
  PASS_REGULAR_EXPRESSION "Public headers client: retained layout, signed oracle and zero ports passed")
add_executable(installed_model_client model_client.cpp)
target_link_libraries(installed_model_client PRIVATE CSL::model)
set_target_properties(installed_model_client PROPERTIES CXX_EXTENSIONS OFF)
add_test(NAME installed_model_client COMMAND installed_model_client)
set_tests_properties(installed_model_client PROPERTIES
  PASS_REGULAR_EXPRESSION "Installed model client: immutable LTI/LTV and scheduled observation literals passed")
add_executable(installed_public_client public_client.cpp)
target_link_libraries(installed_public_client PRIVATE CSL::contracts)
set_target_properties(installed_public_client PROPERTIES CXX_EXTENSIONS OFF)
enable_testing()
add_test(NAME installed_public_client COMMAND installed_public_client)
set_tests_properties(installed_public_client PROPERTIES
  PASS_REGULAR_EXPRESSION "Public contract client: shape guards and literal affine fixture passed")

add_executable(installed_numeric_client numeric_client.cpp)
target_link_libraries(installed_numeric_client PRIVATE CSL::numeric)
set_target_properties(installed_numeric_client PROPERTIES CXX_EXTENSIONS OFF)
add_test(NAME installed_numeric_client COMMAND installed_numeric_client)
set_tests_properties(installed_numeric_client PROPERTIES
  PASS_REGULAR_EXPRESSION "Installed numeric client: dense/CSR snapshots and retained literal fixture passed")

add_executable(installed_registry_client registry_client.cpp)
target_link_libraries(installed_registry_client PRIVATE CSL::registry)
set_target_properties(installed_registry_client PROPERTIES CXX_EXTENSIONS OFF)
add_test(NAME installed_registry_client COMMAND installed_registry_client)
set_tests_properties(installed_registry_client PROPERTIES
  PASS_REGULAR_EXPRESSION "Installed registry client: retained custom-port fixture and exclusive workspaces passed")

add_executable(installed_sets_client sets_client.cpp)
target_link_libraries(installed_sets_client PRIVATE CSL::sets)
set_target_properties(installed_sets_client PROPERTIES CXX_EXTENSIONS OFF)
add_test(NAME installed_sets_client COMMAND installed_sets_client)
set_tests_properties(installed_sets_client PROPERTIES
  PASS_REGULAR_EXPRESSION "Installed sets client: retained H segment and elementary zero-dimensional cases passed")

add_executable(installed_objectives_client objectives_client.cpp)
target_link_libraries(installed_objectives_client PRIVATE CSL::objectives)
set_target_properties(installed_objectives_client PROPERTIES CXX_EXTENSIONS OFF)
add_test(NAME installed_objectives_client COMMAND installed_objectives_client)
set_tests_properties(installed_objectives_client PROPERTIES
  PASS_REGULAR_EXPRESSION "Objective client: rectangular reformulation and independent original cost passed")

add_executable(installed_optimization_client optimization_client.cpp)
target_link_libraries(installed_optimization_client PRIVATE CSL::optimization CSL::registry)
set_target_properties(installed_optimization_client PROPERTIES CXX_EXTENSIONS OFF)
add_test(NAME installed_optimization_client COMMAND installed_optimization_client)
set_tests_properties(installed_optimization_client PROPERTIES
  PASS_REGULAR_EXPRESSION "Installed optimization client: immutable program, literal checks and exclusive attempts passed")
