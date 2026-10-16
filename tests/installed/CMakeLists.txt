cmake_minimum_required(VERSION 3.31)
project(CSLInstalledConsumer LANGUAGES CXX)
find_package(CSL 0.1 CONFIG REQUIRED)

# Expectations come from the package-building configuration. Optional clients may
# be skipped only when the corresponding adapter was deliberately disabled.
foreach(adapter HIGHS QHULL)
  if(DEFINED CSL_EXPECT_${adapter})
    if(adapter STREQUAL "HIGHS")
      set(expected_targets CSL::highs_lp CSL::highs_convex)
    else()
      set(expected_targets CSL::qhull_conversion)
    endif()
    foreach(target IN LISTS expected_targets)
      if(CSL_EXPECT_${adapter} AND NOT TARGET ${target})
        message(FATAL_ERROR "Enabled adapter missing from installed package: ${target}")
      elseif(NOT CSL_EXPECT_${adapter} AND TARGET ${target})
        message(FATAL_ERROR "Disabled adapter leaked into installed package: ${target}")
      endif()
    endforeach()
  endif()
endforeach()
add_executable(installed_input_client input_client.cpp)
target_link_libraries(installed_input_client PRIVATE CSL::input)
set_target_properties(installed_input_client PROPERTIES CXX_EXTENSIONS OFF)
add_test(NAME installed_input_client COMMAND installed_input_client)

if(TARGET CSL::highs_lp AND TARGET CSL::qhull_conversion)
add_executable(installed_conversion_client conversion_client.cpp)
target_link_libraries(installed_conversion_client PRIVATE CSL::qhull_conversion CSL::highs_lp)
set_target_properties(installed_conversion_client PROPERTIES CXX_EXTENSIONS OFF)
add_test(NAME installed_conversion_client COMMAND installed_conversion_client)
set_tests_properties(installed_conversion_client PROPERTIES
  PASS_REGULAR_EXPRESSION "Installed Qhull conversion client: registered square conversion and literal vertices passed")

endif()
add_executable(installed_polyhedral_intersection_client polyhedral_intersection_client.cpp)
target_link_libraries(installed_polyhedral_intersection_client PRIVATE CSL::polyhedral)
set_target_properties(installed_polyhedral_intersection_client PROPERTIES CXX_EXTENSIONS OFF)
add_test(NAME installed_polyhedral_intersection_client COMMAND installed_polyhedral_intersection_client)
set_tests_properties(installed_input_client PROPERTIES
  PASS_REGULAR_EXPRESSION "Installed input client: owning scenario, literal identity and original cost passed")
if(TARGET CSL::highs_convex)
add_executable(installed_convex_client convex_client.cpp)
target_link_libraries(installed_convex_client PRIVATE CSL::highs_convex)
set_target_properties(installed_convex_client PROPERTIES CXX_EXTENSIONS OFF)
add_test(NAME installed_convex_client COMMAND installed_convex_client)
set_tests_properties(installed_convex_client PROPERTIES
  PASS_REGULAR_EXPRESSION "Installed convex client: original norm, squared provenance and numerical KKT passed")

endif()
add_executable(installed_resolved_problem_client resolved_problem_client.cpp)
target_link_libraries(installed_resolved_problem_client PRIVATE CSL::resolved_problem)
set_target_properties(installed_resolved_problem_client PROPERTIES CXX_EXTENSIONS OFF)
add_test(NAME installed_resolved_problem_client COMMAND installed_resolved_problem_client)
set_tests_properties(installed_resolved_problem_client PROPERTIES
  PASS_REGULAR_EXPRESSION "Installed resolved problem client: literal identity, retained data and actual strategy admission passed")
add_executable(installed_execution_client execution_client.cpp)
target_link_libraries(installed_execution_client PRIVATE CSL::execution)
set_target_properties(installed_execution_client PROPERTIES CXX_EXTENSIONS OFF)
add_test(NAME installed_execution_client COMMAND installed_execution_client)
set_tests_properties(installed_execution_client PROPERTIES
  PASS_REGULAR_EXPRESSION "Installed execution client: retained analytic tasks, isolated modes and literal outcomes passed")
add_executable(installed_public_headers_client public_headers_client.cpp)
target_link_libraries(installed_public_headers_client PRIVATE CSL::numeric)
set_target_properties(installed_public_headers_client PROPERTIES CXX_EXTENSIONS OFF)
add_test(NAME installed_public_headers_client COMMAND installed_public_headers_client)
set_tests_properties(installed_public_headers_client PROPERTIES
  PASS_REGULAR_EXPRESSION "Public headers client: retained layout, signed oracle and zero ports passed")
add_executable(installed_public_headers_lp_first_client public_headers_client.cpp)
target_link_libraries(installed_public_headers_lp_first_client PRIVATE CSL::numeric)
target_compile_definitions(installed_public_headers_lp_first_client PRIVATE CSL_PUBLIC_HEADERS_LP_FIRST=1)
set_target_properties(installed_public_headers_lp_first_client PROPERTIES CXX_EXTENSIONS OFF)
add_test(NAME installed_public_headers_lp_first_client COMMAND installed_public_headers_lp_first_client)
set_tests_properties(installed_public_headers_lp_first_client PROPERTIES
  PASS_REGULAR_EXPRESSION "Public headers client: retained layout, signed oracle and zero ports passed")
add_executable(installed_model_client model_client.cpp)
target_link_libraries(installed_model_client PRIVATE CSL::model)
set_target_properties(installed_model_client PROPERTIES CXX_EXTENSIONS OFF)
add_test(NAME installed_model_client COMMAND installed_model_client)

add_executable(installed_finite_feedback_client finite_feedback_client.cpp)
target_link_libraries(installed_finite_feedback_client PRIVATE CSL::finite_feedback_port)
set_target_properties(installed_finite_feedback_client PROPERTIES CXX_EXTENSIONS OFF)
add_test(NAME installed_finite_feedback_client COMMAND installed_finite_feedback_client)
set_tests_properties(installed_finite_feedback_client PROPERTIES
  PASS_REGULAR_EXPRESSION "Installed finite feedback client: registered winning action passed")
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

add_executable(installed_provider_client provider_client.cpp)
target_link_libraries(installed_provider_client PRIVATE CSL::registry CSL::optimization)
set_target_properties(installed_provider_client PROPERTIES CXX_EXTENSIONS OFF)
add_test(NAME installed_provider_client COMMAND installed_provider_client)
set_tests_properties(installed_provider_client PROPERTIES
  PASS_REGULAR_EXPRESSION "Installed provider client: frozen method and changing owned requests passed")

add_executable(installed_sets_client sets_client.cpp)
target_link_libraries(installed_sets_client PRIVATE CSL::sets)
set_target_properties(installed_sets_client PROPERTIES CXX_EXTENSIONS OFF)
add_test(NAME installed_sets_client COMMAND installed_sets_client)
set_tests_properties(installed_sets_client PROPERTIES
  PASS_REGULAR_EXPRESSION "Installed sets client: retained H segment and elementary zero-dimensional cases passed")

add_executable(installed_generators_client generators_client.cpp)
target_link_libraries(installed_generators_client PRIVATE CSL::geometry_generators)
set_target_properties(installed_generators_client PROPERTIES CXX_EXTENSIONS OFF)
add_test(NAME installed_generators_client COMMAND installed_generators_client)
set_tests_properties(installed_generators_client PROPERTIES
  PASS_REGULAR_EXPRESSION "Installed generators client: retained factor identity and affine literal passed")

add_executable(installed_generator_adapter_client generator_adapter_client.cpp)
target_link_libraries(installed_generator_adapter_client PRIVATE CSL::generator_adapter)
set_target_properties(installed_generator_adapter_client PROPERTIES CXX_EXTENSIONS OFF)
add_test(NAME installed_generator_adapter_client COMMAND installed_generator_adapter_client)
set_tests_properties(installed_generator_adapter_client PROPERTIES
  PASS_REGULAR_EXPRESSION "Installed generator adapter client: prepared box image and literal V conversion passed")

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

if(TARGET CSL::highs_lp)
add_executable(installed_highs_client highs_client.cpp)
target_link_libraries(installed_highs_client PRIVATE CSL::highs_lp)
set_target_properties(installed_highs_client PROPERTIES CXX_EXTENSIONS OFF)
add_test(NAME installed_highs_client COMMAND installed_highs_client)
set_tests_properties(installed_highs_client PROPERTIES
  PASS_REGULAR_EXPRESSION "Installed HiGHS client: registered offset optimum and neutral evidence passed")


endif()
add_executable(installed_problem_client problem_client.cpp)
target_link_libraries(installed_problem_client PRIVATE CSL::problem)
set_target_properties(installed_problem_client PROPERTIES CXX_EXTENSIONS OFF)
add_test(NAME installed_problem_client COMMAND installed_problem_client)
set_tests_properties(installed_problem_client PROPERTIES
  PASS_REGULAR_EXPRESSION "Installed problem client: immutable domains and full-history literals passed")

add_executable(installed_phase_one_client phase_one_client.cpp)
target_link_libraries(installed_phase_one_client PRIVATE CSL::phase_one)
set_target_properties(installed_phase_one_client PROPERTIES CXX_EXTENSIONS OFF)
add_test(NAME installed_phase_one_client COMMAND installed_phase_one_client)
set_tests_properties(installed_phase_one_client PROPERTIES
  PASS_REGULAR_EXPRESSION "Installed phase one client: signed coefficients, original basis and numerical evidence passed")
add_executable(installed_run_statistics_client run_statistics_client.cpp)
target_link_libraries(installed_run_statistics_client PRIVATE CSL::artifacts)
set_target_properties(installed_run_statistics_client PROPERTIES CXX_EXTENSIONS OFF)
add_test(NAME installed_run_statistics_client COMMAND installed_run_statistics_client)
set_tests_properties(installed_run_statistics_client PROPERTIES
  PASS_REGULAR_EXPRESSION "Installed statistics client: immutable identities and portable lifetime round trip passed")

if(TARGET CSL::highs_lp)
add_executable(installed_hull_reducer_client hull_reducer_client.cpp)
target_link_libraries(installed_hull_reducer_client PRIVATE CSL::hull CSL::highs_lp)
set_target_properties(installed_hull_reducer_client PROPERTIES CXX_EXTENSIONS OFF)
add_test(NAME installed_hull_reducer_client COMMAND installed_hull_reducer_client)
set_tests_properties(installed_hull_reducer_client PROPERTIES
  PASS_REGULAR_EXPRESSION "Installed hull client: each membership LP passed registered-provider admission")


endif()
if(TARGET CSL::highs_lp)
add_executable(installed_affine_sum_client affine_sum_client.cpp)
target_link_libraries(installed_affine_sum_client PRIVATE CSL::affine_sum CSL::highs_lp)
set_target_properties(installed_affine_sum_client PROPERTIES CXX_EXTENSIONS OFF)
add_test(NAME installed_affine_sum_client COMMAND installed_affine_sum_client)
set_tests_properties(installed_affine_sum_client PROPERTIES
  PASS_REGULAR_EXPRESSION "Installed affine/sum client: selected LP and hull providers produced a numerical set result")


endif()
add_executable(installed_terminal_minimizers_client terminal_minimizers_client.cpp)
target_link_libraries(installed_terminal_minimizers_client PRIVATE CSL::terminal_minimizers)
set_target_properties(installed_terminal_minimizers_client PROPERTIES CXX_EXTENSIONS OFF)
add_test(NAME installed_terminal_minimizers_client COMMAND installed_terminal_minimizers_client)
set_tests_properties(installed_terminal_minimizers_client PROPERTIES
  PASS_REGULAR_EXPRESSION "Installed terminal-minimizers client: public outcome contract is available")

add_executable(installed_projection_predecessor_client projection_predecessor_client.cpp)
target_link_libraries(installed_projection_predecessor_client PRIVATE CSL::polyhedral)
set_target_properties(installed_projection_predecessor_client PROPERTIES CXX_EXTENSIONS OFF)
add_test(NAME installed_projection_predecessor_client COMMAND installed_projection_predecessor_client)
set_tests_properties(installed_projection_predecessor_client PROPERTIES
  PASS_REGULAR_EXPRESSION "Installed predecessor client: existential integrator interval and unestablished support passed")

if(TARGET CSL::highs_lp AND TARGET CSL::qhull_conversion)
add_executable(installed_nominal_forward_client nominal_forward_client.cpp)
target_link_libraries(installed_nominal_forward_client PRIVATE CSL::nominal_forward CSL::affine_sum CSL::qhull_conversion CSL::highs_lp)
set_target_properties(installed_nominal_forward_client PROPERTIES CXX_EXTENSIONS OFF)
add_test(NAME installed_nominal_forward_client COMMAND installed_nominal_forward_client)
set_tests_properties(installed_nominal_forward_client PROPERTIES
  PASS_REGULAR_EXPRESSION "Installed nominal-forward client: provider-backed integrator tube and authored labels passed")


endif()
add_executable(installed_ts01_evidence_client ts01_evidence_client.cpp)
target_link_libraries(installed_ts01_evidence_client PRIVATE CSL::strategy_ts01)
set_target_properties(installed_ts01_evidence_client PROPERTIES CXX_EXTENSIONS OFF)
if(MSVC)
  target_compile_options(installed_ts01_evidence_client PRIVATE /W4 /WX /permissive-)
else()
  target_compile_options(installed_ts01_evidence_client PRIVATE -Wall -Wextra -Wpedantic -Werror)
endif()
add_test(NAME installed_ts01_evidence_client COMMAND installed_ts01_evidence_client)
set(CMAKE_TRY_COMPILE_CONFIGURATION "${CMAKE_BUILD_TYPE}")
unset(ts01_issuer_forge_compiled CACHE)
try_compile(ts01_issuer_forge_compiled
  "${CMAKE_CURRENT_BINARY_DIR}/ts01-issuer-forge-compile"
  SOURCES "${CMAKE_CURRENT_SOURCE_DIR}/ts01_issuer_forge_client.cpp"
  LINK_LIBRARIES CSL::contracts
  OUTPUT_VARIABLE ts01_issuer_forge_output)
if(ts01_issuer_forge_compiled)
  message(FATAL_ERROR "Installed contracts API accepted downstream replacement of the complete-family publisher:\n${ts01_issuer_forge_output}")
endif()
if(NOT ts01_issuer_forge_output MATCHES "(error C[0-9]+|error:|fatal error:)")
  message(FATAL_ERROR "Installed contracts API compile probe failed for an unrelated reason:\n${ts01_issuer_forge_output}")
endif()
message(STATUS "Installed complete-family publisher replacement was rejected by the compiler")
unset(ts01_callback_forge_compiled CACHE)
try_compile(ts01_callback_forge_compiled
  "${CMAKE_CURRENT_BINARY_DIR}/ts01-callback-forge-compile"
  SOURCES "${CMAKE_CURRENT_SOURCE_DIR}/ts01_callback_forge_client.cpp"
  LINK_LIBRARIES CSL::registry
  OUTPUT_VARIABLE ts01_callback_forge_output)
if(ts01_callback_forge_compiled)
  message(FATAL_ERROR "Installed registry API accepted a caller-supplied verifier callback:\n${ts01_callback_forge_output}")
endif()
if(NOT ts01_callback_forge_output MATCHES "(error C[0-9]+|error:|fatal error:)")
  message(FATAL_ERROR "Installed registry API compile probe failed for an unrelated reason:\n${ts01_callback_forge_output}")
endif()
message(STATUS "Installed caller-supplied verifier callback was rejected by the compiler")
unset(ts01_relation_factory_forge_compiled CACHE)
try_compile(ts01_relation_factory_forge_compiled
  "${CMAKE_CURRENT_BINARY_DIR}/ts01-relation-factory-forge-compile"
  SOURCES "${CMAKE_CURRENT_SOURCE_DIR}/ts01_relation_factory_forge_client.cpp"
  LINK_LIBRARIES CSL::strategy_ts01
  OUTPUT_VARIABLE ts01_relation_factory_forge_output)
if(ts01_relation_factory_forge_compiled)
  message(FATAL_ERROR "Installed T-S01 API accepted a downstream relation factory definition:\n${ts01_relation_factory_forge_output}")
endif()
if(NOT ts01_relation_factory_forge_output MATCHES "(error C[0-9]+|error:|fatal error:)")
  message(FATAL_ERROR "Installed T-S01 API relation-factory probe failed for an unrelated reason:\n${ts01_relation_factory_forge_output}")
endif()
message(STATUS "Installed downstream relation factory definition was rejected by the compiler")

unset(farkas_factory_forge_compiled CACHE)
try_compile(farkas_factory_forge_compiled
  "${CMAKE_CURRENT_BINARY_DIR}/farkas-factory-forge-compile"
  SOURCES "${CMAKE_CURRENT_SOURCE_DIR}/farkas_factory_forge_client.cpp"
  LINK_LIBRARIES CSL::optimization
  OUTPUT_VARIABLE farkas_factory_forge_output)
if(farkas_factory_forge_compiled)
  message(FATAL_ERROR "Installed optimization API accepted downstream ExactFarkasEvidence construction:\n${farkas_factory_forge_output}")
endif()
if(NOT farkas_factory_forge_output MATCHES "(error C[0-9]+|error:|fatal error:)")
  message(FATAL_ERROR "Installed optimization API Farkas construction probe failed for an unrelated reason:\n${farkas_factory_forge_output}")
endif()
if(NOT farkas_factory_forge_output MATCHES "(C2248|private|inaccessible)")
  message(FATAL_ERROR "Installed optimization API rejected the Farkas probe for a reason other than inaccessible evidence construction:\n${farkas_factory_forge_output}")
endif()
message(STATUS "Installed downstream ExactFarkasEvidence construction was rejected by the compiler")

if(TARGET CSL::highs_lp)
add_executable(installed_witness_selector_client witness_selector_client.cpp)
target_link_libraries(installed_witness_selector_client PRIVATE CSL::witness_selector CSL::highs_lp)
set_target_properties(installed_witness_selector_client PROPERTIES CXX_EXTENSIONS OFF)
add_test(NAME installed_witness_selector_client COMMAND installed_witness_selector_client)

endif()

# A separate translation unit per contract prevents umbrella/include-order masking.
set(installed_contract_headers
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
foreach(header IN LISTS installed_contract_headers)
  string(MAKE_C_IDENTIFIER "${header}" header_name)
  set(source "${CMAKE_CURRENT_BINARY_DIR}/header-checks/${header_name}.cpp")
  file(GENERATE OUTPUT "${source}" CONTENT "#include <csl/${header}>\n")
  add_library(installed_header_${header_name} OBJECT "${source}")
  target_link_libraries(installed_header_${header_name} PRIVATE CSL::contracts)
endforeach()

if(TARGET CSL::application)
add_executable(installed_application_client application_client.cpp)
target_link_libraries(installed_application_client PRIVATE CSL::application)
set_target_properties(installed_application_client PROPERTIES CXX_EXTENSIONS OFF)
add_test(NAME installed_application_client COMMAND installed_application_client)
set_tests_properties(installed_application_client PROPERTIES
  PASS_REGULAR_EXPRESSION "Installed application client: guarded profile rejection passed")
endif()
