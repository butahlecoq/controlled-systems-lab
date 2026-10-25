cmake_minimum_required(VERSION 3.31)

# Script mode checks both exit status and observable output, including rejections.
if(DEFINED EXAMPLE_EXE)
  if(DEFINED COMPARISON_EXPORT)
    execute_process(COMMAND "${EXAMPLE_EXE}" "${EXAMPLE_ARGUMENT}" "${COMPARISON_EXPORT}"
      RESULT_VARIABLE status OUTPUT_VARIABLE output ERROR_VARIABLE error)
    if(NOT "${status}" STREQUAL "0")
      message(FATAL_ERROR "Comparison/export failed: ${status}: ${output}${error}")
    endif()
    file(READ "${COMPARISON_EXPORT}" exported)
    if(NOT "${exported}" STREQUAL "${output}")
      message(FATAL_ERROR "Saved JSON differs from stdout")
    endif()
    function(expect_json expected)
      string(JSON actual GET "${exported}" ${ARGN})
      if(NOT "${actual}" STREQUAL "${expected}")
        message(FATAL_ERROR "${ARGN}: expected ${expected}, observed ${actual}")
      endif()
    endfunction()
    expect_json("csl.example.synthesis-comparison/1" schema)
    string(JSON export_status GET "${exported}" family_payload_export)
    if(NOT export_status MATCHES "^unavailable:.*cannot reconstruct a family$")
      message(FATAL_ERROR "Export must declare unavailable family payload")
    endif()
    string(JSON count LENGTH "${exported}" results)
    if(NOT count EQUAL 2)
      message(FATAL_ERROR "Expected two strategy results, observed ${count}")
    endif()
    string(JSON problem GET "${exported}" problem)
    set(strategy_ids csl.synthesis.reach-back csl.synthesis.strategy-b)
    foreach(index RANGE 0 1)
      list(GET strategy_ids ${index} strategy)
      expect_json("${strategy}" results ${index} strategy)
      expect_json("${strategy}" results ${index} family_source strategy)
      expect_json("${strategy}" results ${index} strategy_provenance 0 actual)
      expect_json("${problem}" results ${index} problem)
      expect_json("${problem}" results ${index} family_source problem)
      expect_json("${problem}" results ${index} family_source request objective)
      expect_json("ts01_exact_integrator" results ${index} family_source request profile)
      expect_json("exact_optimal_relation" results ${index} family_source request target)
      expect_json("numerical" results ${index} family_source request assurance)
      expect_json("csl.polyhedron.h" results ${index} family_source request representation)
      expect_json("completed" results ${index} termination)
      expect_json("optimal" results ${index} outcome)
      expect_json("csl.selector.ts01-directions" results ${index} selector_provenance 0 actual)
      expect_json("csl.lp.highs" results ${index} membership_provenance 0 actual)
      expect_json(2 results ${index} distinct_witnesses)
      string(JSON witnesses LENGTH "${exported}" results ${index} witnesses)
      if(NOT witnesses EQUAL 2)
        message(FATAL_ERROR "Expected two witness histories")
      endif()
      foreach(witness RANGE 0 1)
        # Literal independent oracle: u=(0,1) or (1,0), x=(0,u0,1), cost=0.
        math(EXPR other "1-${witness}")
        expect_json(${witness} results ${index} witnesses ${witness} controls 0 0)
        expect_json(${other} results ${index} witnesses ${witness} controls 1 0)
        expect_json(0 results ${index} witnesses ${witness} states 0 0)
        expect_json(${witness} results ${index} witnesses ${witness} states 1 0)
        expect_json(1 results ${index} witnesses ${witness} states 2 0)
        expect_json(0 results ${index} witnesses ${witness} original_objective)
        expect_json(0 results ${index} witnesses ${witness} recomputed_objective)
        foreach(check bindings feasibility objective)
          expect_json("numerical_pass" results ${index} witnesses ${witness} verification ${check})
        endforeach()
        foreach(check optimality completeness)
          expect_json("unsupported" results ${index} witnesses ${witness} verification ${check})
        endforeach()
      endforeach()
    endforeach()
    return()
  endif()
  execute_process(COMMAND "${EXAMPLE_EXE}" ${EXAMPLE_ARGUMENT}
    RESULT_VARIABLE status OUTPUT_VARIABLE output ERROR_VARIABLE error)
  set(combined_output "${output}${error}")
  string(REGEX REPLACE "[\r\n]+" " " combined_output "${combined_output}")
  if(NOT "${status}" STREQUAL "${EXPECTED_STATUS}")
    message(FATAL_ERROR "Expected exit ${EXPECTED_STATUS}, got ${status}: ${combined_output}")
  endif()
  if(NOT "${combined_output}" MATCHES "${EXPECTED_OUTPUT}")
    message(FATAL_ERROR "Expected ${EXPECTED_OUTPUT}, got: ${combined_output}")
  endif()
  message(STATUS "${output}${error}")
  return()
endif()

project(CSLExamples LANGUAGES CXX)
find_package(CSL 0.1 CONFIG REQUIRED)
enable_testing()

# Partial packages run every example whose required public targets are present.
function(csl_example example)
  foreach(dependency IN LISTS ARGN)
    if(NOT TARGET ${dependency})
      return()
    endif()
  endforeach()
  add_executable(${example} ${example}.cpp)
  target_link_libraries(${example} PRIVATE ${ARGN})
  target_compile_features(${example} PRIVATE cxx_std_20)
  set_target_properties(${example} PROPERTIES CXX_EXTENSIONS OFF)
  if(MSVC)
    target_compile_options(${example} PRIVATE /W4 /WX /permissive-)
  else()
    target_compile_options(${example} PRIVATE -Wall -Wextra -Wpedantic -Werror)
  endif()
endfunction()

csl_example(registered_lp CSL::highs_lp)
csl_example(registered_convex CSL::highs_convex)
csl_example(resolved_scenario CSL::resolved_problem)
csl_example(scenario_file CSL::input)
csl_example(scenario_cli CSL::input CSL::application CSL::strategy_a CSL::strategy_b
  CSL::witness_selector CSL::verification CSL::highs_lp CSL::highs_convex
  CSL::qhull_conversion CSL::affine_sum)
csl_example(backend_substitution CSL::highs_lp CSL::phase_one)
csl_example(registered_synthesis_comparison CSL::input CSL::strategy_a CSL::strategy_b
  CSL::witness_selector CSL::verification CSL::highs_lp CSL::highs_convex CSL::qhull_conversion CSL::affine_sum)
csl_example(nominal_linear_exact_2d CSL::strategy_a CSL::highs_lp CSL::highs_convex
  CSL::qhull_conversion CSL::affine_sum)
csl_example(continuous_policy CSL::controllers CSL::model)

function(example_check name executable argument status output)
  if(NOT TARGET ${executable})
    return()
  endif()
  add_test(NAME ${name} COMMAND "${CMAKE_COMMAND}"
    "-DEXAMPLE_EXE=$<TARGET_FILE:${executable}>" "-DEXAMPLE_ARGUMENT=${argument}"
    "-DEXPECTED_STATUS=${status}" "-DEXPECTED_OUTPUT=${output}"
    -P "${CMAKE_CURRENT_SOURCE_DIR}/CMakeLists.txt")
  set_tests_properties(${name} PROPERTIES TIMEOUT 30)
endfunction()

example_check(lp_triangle registered_lp "" 0 "x=0 y=1 original_cost=5")
example_check(convex_original_norm registered_convex "" 0 "original_cost=4.1231056.*squared_cost=17")
example_check(resolved_history resolved_scenario "" 0 "states=0,0.25,1 controls=0.25,0.75 original_cost=0")
example_check(continuous_policy_all_generators continuous_policy "" 0
  "scope=all_joint_uncertainty assurance=numerical generators=4.*initial=0,0 action=0 terminal=0,0.*initial=0,1 action=0 terminal=1,1.*initial=1,0 action=1 terminal=1.5,1.*initial=1,1 action=1 terminal=2.5,2")
example_check(scenario_cli_valid scenario_cli "--validate-only;${CMAKE_CURRENT_SOURCE_DIR}/scenarios/two-stage-integrator.json" 0
  "validation=valid.*schema=csl.scenario/1.*requested=comparison.*mode=validate_only solvers=not_invoked")
example_check(scenario_cli_missing scenario_cli "--validate-only;${CMAKE_CURRENT_BINARY_DIR}/no-such-scenario.json" 2
  "Input rejected: category=io.*expected")
example_check(scenario_cli_run_ts01 scenario_cli "--run;${CMAKE_CURRENT_SOURCE_DIR}/scenarios/two-stage-integrator.json;--seed;42;--threads;2" 0
  "mode=run profile=ts01_exact_integrator strategy=csl.synthesis.reach-back.*seed=42 threads=2.*verification=numerical_pass")
example_check(scenario_cli_run_double_integrator_generality scenario_cli
  "--run;${CMAKE_CURRENT_SOURCE_DIR}/scenarios/double-integrator-generality.json;--profile;nominal_open_loop"
  0 "mode=run profile=nominal_open_loop strategy=csl.synthesis.strategy-b.*outcome=undetermined family=candidate selected=0 incumbents=1 verification=not_passed incumbent_evidence=numerical")
example_check(scenario_cli_run_missing scenario_cli "--run;${CMAKE_CURRENT_BINARY_DIR}/no-such-scenario.json" 2
  "Input rejected: category=io.*expected")
example_check(scenario_cli_run_unknown_backend scenario_cli
  "--run;${CMAKE_CURRENT_SOURCE_DIR}/scenarios/two-stage-integrator.json;--lp;missing-backend" 1
  "Strategy preparation rejected.*missing-backend")
example_check(scenario_cli_run_unsupported_profile scenario_cli
  "--run;${CMAKE_CURRENT_SOURCE_DIR}/scenarios/two-stage-integrator.json;--profile;unsupported-profile" 2
  "Unsupported profile.*unsupported-profile")
if(TARGET scenario_cli)
  add_test(NAME scenario_cli_run_export_roundtrip
    COMMAND ${CMAKE_COMMAND}
      "-DSCENARIO_CLI=$<TARGET_FILE:scenario_cli>"
      "-DSCENARIO_INPUT=${CMAKE_CURRENT_SOURCE_DIR}/scenarios/two-stage-integrator.json"
      "-DOUTPUT_DIRECTORY=${CMAKE_CURRENT_BINARY_DIR}/scenario-cli-export-roundtrip"
      -P "${CMAKE_CURRENT_SOURCE_DIR}/scenario_cli_export_check.cmake")
  set_tests_properties(scenario_cli_run_export_roundtrip PROPERTIES TIMEOUT 30)
  add_test(NAME scenario_cli_double_integrator_generality_export
    COMMAND ${CMAKE_COMMAND}
      "-DSCENARIO_CLI=$<TARGET_FILE:scenario_cli>"
      "-DSCENARIO_INPUT=${CMAKE_CURRENT_SOURCE_DIR}/scenarios/double-integrator-generality.json"
      "-DSCENARIO_PROFILE=nominal_open_loop"
      "-DEXPECTED_FAMILY_KIND=candidate"
      "-DOUTPUT_DIRECTORY=${CMAKE_CURRENT_BINARY_DIR}/scenario-cli-double-integrator-generality"
      -P "${CMAKE_CURRENT_SOURCE_DIR}/scenario_cli_export_check.cmake")
  set_tests_properties(scenario_cli_double_integrator_generality_export PROPERTIES TIMEOUT 30)
endif()
example_check(scenario_cli_malformed scenario_cli "--validate-only;${CMAKE_CURRENT_BINARY_DIR}/malformed.json" 2
  "Input rejected: category=syntax.*expected")
file(READ "${CMAKE_CURRENT_SOURCE_DIR}/scenarios/two-stage-integrator.json" validation_scenario)
string(JSON unsupported_validation_scenario SET "${validation_scenario}" temporal "{}")
file(WRITE "${CMAKE_CURRENT_BINARY_DIR}/unsupported-validation.json" "${unsupported_validation_scenario}")
example_check(scenario_cli_unsupported scenario_cli "--validate-only;${CMAKE_CURRENT_BINARY_DIR}/unsupported-validation.json" 2
  "Input unsupported: path=/temporal feature=temporal")
string(JSON unsupported_representation_scenario SET "${validation_scenario}" run "{\"backends\":{\"representation\":\"csl.polyhedron.v\"}}")
file(WRITE "${CMAKE_CURRENT_BINARY_DIR}/unsupported-representation.json" "${unsupported_representation_scenario}")
example_check(scenario_cli_run_unsupported_representation scenario_cli
  "--run;${CMAKE_CURRENT_BINARY_DIR}/unsupported-representation.json" 2
  "Input unsupported: path=/run/backends/representation observed=csl.polyhedron.v.*expected csl.polyhedron.h")
string(JSON explicit_h_representation_scenario SET "${validation_scenario}" run "{\"backends\":{\"representation\":\"csl.polyhedron.h\"}}")
file(WRITE "${CMAKE_CURRENT_BINARY_DIR}/explicit-h-representation.json" "${explicit_h_representation_scenario}")
example_check(scenario_cli_run_explicit_h_representation scenario_cli
  "--run;${CMAKE_CURRENT_BINARY_DIR}/explicit-h-representation.json" 0
  "mode=run profile=ts01_exact_integrator strategy=csl.synthesis.reach-back.*seed=31 threads=1.*verification=numerical_pass")
example_check(file_history scenario_file "${CMAKE_CURRENT_SOURCE_DIR}/scenarios/two-stage-integrator.json" 0
  "states=0,0.25,1 controls=0.25,0.75 original_cost=0")
example_check(substitution_highs backend_substitution csl.lp.highs 0 "backend=csl.lp.highs version=1.1.0.highs.1.11.0")
example_check(substitution_phase_one backend_substitution phase-one-bland 0 "backend=phase-one-bland version=1")
example_check(nominal_linear_exact_2d_complete_face nominal_linear_exact_2d "" 0
  "state_dimension=2 control_dimension=2 horizon=1.*exact_optimum=1.*verified_complete_family=true assurance=numerical")
example_check(lp_unknown_backend registered_lp missing-backend 2 "Selection rejected.*missing-backend")
example_check(convex_unknown_backend registered_convex missing-backend 2 "Selection rejected.*missing-backend")
example_check(substitution_unknown_backend backend_substitution missing-backend 2 "Selection rejected.*missing-backend")
example_check(file_missing scenario_file "${CMAKE_CURRENT_BINARY_DIR}/no-such-scenario.json" 2 "Input rejected.*expected")
file(WRITE "${CMAKE_CURRENT_BINARY_DIR}/malformed.json" "{ invalid JSON")
example_check(file_malformed scenario_file "${CMAKE_CURRENT_BINARY_DIR}/malformed.json" 2 "Input rejected.*expected")
example_check(file_no_argument scenario_file "" 2 "Usage: scenario_file")
if(TARGET registered_synthesis_comparison)
example_check(synthesis_comparison registered_synthesis_comparison "${CMAKE_CURRENT_SOURCE_DIR}/scenarios/two-stage-integrator.json" 0
  "schema.*csl.example.synthesis-comparison/1.*csl.synthesis.reach-back.*csl.synthesis.strategy-b")
add_test(NAME synthesis_comparison_export COMMAND "${CMAKE_COMMAND}"
  "-DEXAMPLE_EXE=$<TARGET_FILE:registered_synthesis_comparison>"
  "-DEXAMPLE_ARGUMENT=${CMAKE_CURRENT_SOURCE_DIR}/scenarios/two-stage-integrator.json"
  "-DCOMPARISON_EXPORT=${CMAKE_CURRENT_BINARY_DIR}/comparison-results.json"
  -P "${CMAKE_CURRENT_SOURCE_DIR}/CMakeLists.txt")
set_tests_properties(synthesis_comparison_export PROPERTIES TIMEOUT 30)
example_check(synthesis_missing registered_synthesis_comparison "${CMAKE_CURRENT_BINARY_DIR}/no-such-scenario.json" 2 "Input rejected.*expected")
example_check(synthesis_malformed registered_synthesis_comparison "${CMAKE_CURRENT_BINARY_DIR}/malformed.json" 2 "Input rejected.*expected")
example_check(synthesis_no_argument registered_synthesis_comparison "" 2 "Usage: registered_synthesis_comparison")
example_check(synthesis_output_failure registered_synthesis_comparison
  "${CMAKE_CURRENT_SOURCE_DIR}/scenarios/two-stage-integrator.json;${CMAKE_CURRENT_BINARY_DIR}" 2 "Output rejected")
file(READ "${CMAKE_CURRENT_SOURCE_DIR}/scenarios/two-stage-integrator.json" teaching_scenario)
string(REPLACE "\"horizon\": 2" "\"horizon\": 3" unsupported_scenario "${teaching_scenario}")
file(WRITE "${CMAKE_CURRENT_BINARY_DIR}/unsupported-synthesis.json" "${unsupported_scenario}")
example_check(synthesis_unsupported_profile registered_synthesis_comparison "${CMAKE_CURRENT_BINARY_DIR}/unsupported-synthesis.json" 1 "Strategy preparation rejected")
string(JSON overridden_scenario SET "${teaching_scenario}" run "{\"seed\":42}")
file(WRITE "${CMAKE_CURRENT_BINARY_DIR}/overridden-synthesis.json" "${overridden_scenario}")
example_check(synthesis_run_override registered_synthesis_comparison "${CMAKE_CURRENT_BINARY_DIR}/overridden-synthesis.json" 2 "Input rejected.*does not accept run overrides")
endif()
