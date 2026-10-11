cmake_minimum_required(VERSION 3.31)
project(CSLInstalledConsumer LANGUAGES CXX)
find_package(CSL 0.1 CONFIG REQUIRED)
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
