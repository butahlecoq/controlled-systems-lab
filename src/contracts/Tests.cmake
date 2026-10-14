add_executable(contract_tests probes/core-01/contract_tests.cpp)
target_link_libraries(contract_tests PRIVATE CSL::contracts doctest::doctest)
add_test(NAME contract_tests COMMAND contract_tests)
csl_test_target(contract_tests contracts)

add_executable(public_client tests/contract/public_client.cpp)
target_link_libraries(public_client PRIVATE CSL::contracts)
set_target_properties(public_client PROPERTIES CXX_EXTENSIONS OFF)
add_test(NAME public_client COMMAND public_client)
set_tests_properties(public_client PROPERTIES
    PASS_REGULAR_EXPRESSION "Public contract client: shape guards and literal affine fixture passed")
csl_test_target(public_client contracts)

# A separate translation unit per contract prevents umbrella/include-order masking.
set(csl_contract_headers
  core/values.hpp
  core/diagnostics.hpp
  core/outcomes.hpp
  evidence/contracts.hpp
  model/contracts.hpp
  sets/contracts.hpp
  optimization/objective_contracts.hpp
  problem/contracts.hpp
  execution/contracts.hpp
  optimization/contracts.hpp
  geometry/contracts.hpp
  synthesis/contracts.hpp
  numeric/data.hpp
)
foreach(header IN LISTS csl_contract_headers)
  string(MAKE_C_IDENTIFIER "${header}" header_name)
  set(source "${CMAKE_CURRENT_BINARY_DIR}/header-checks/${header_name}.cpp")
  file(GENERATE OUTPUT "${source}" CONTENT "#include <csl/${header}>\n")
  add_library(header_${header_name} OBJECT "${source}")
  target_link_libraries(header_${header_name} PRIVATE CSL::contracts)
endforeach()
