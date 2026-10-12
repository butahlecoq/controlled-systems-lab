cmake_minimum_required(VERSION 3.31)

# Script mode checks both exit status and observable output, including rejections.
if(DEFINED EXAMPLE_EXE)
  execute_process(COMMAND "${EXAMPLE_EXE}" ${EXAMPLE_ARGUMENT}
    RESULT_VARIABLE status OUTPUT_VARIABLE output ERROR_VARIABLE error)
  if(NOT "${status}" STREQUAL "${EXPECTED_STATUS}")
    message(FATAL_ERROR "Expected exit ${EXPECTED_STATUS}, got ${status}: ${output}${error}")
  endif()
  if(NOT "${output}${error}" MATCHES "${EXPECTED_OUTPUT}")
    message(FATAL_ERROR "Expected ${EXPECTED_OUTPUT}, got: ${output}${error}")
  endif()
  message(STATUS "${output}${error}")
  return()
endif()

project(CSLExamples LANGUAGES CXX)
find_package(CSL 0.1 CONFIG REQUIRED)
enable_testing()

foreach(example registered_lp registered_convex resolved_scenario scenario_file backend_substitution)
  add_executable(${example} ${example}.cpp)
  target_compile_features(${example} PRIVATE cxx_std_20)
  set_target_properties(${example} PROPERTIES CXX_EXTENSIONS OFF)
  if(MSVC)
    target_compile_options(${example} PRIVATE /W4 /WX /permissive-)
  else()
    target_compile_options(${example} PRIVATE -Wall -Wextra -Wpedantic -Werror)
  endif()
endforeach()
target_link_libraries(registered_lp PRIVATE CSL::highs_lp)
target_link_libraries(registered_convex PRIVATE CSL::highs_convex)
target_link_libraries(resolved_scenario PRIVATE CSL::resolved_problem)
target_link_libraries(scenario_file PRIVATE CSL::input)
target_link_libraries(backend_substitution PRIVATE CSL::highs_lp CSL::phase_one)

function(example_check name executable argument status output)
  add_test(NAME ${name} COMMAND "${CMAKE_COMMAND}"
    "-DEXAMPLE_EXE=$<TARGET_FILE:${executable}>" "-DEXAMPLE_ARGUMENT=${argument}"
    "-DEXPECTED_STATUS=${status}" "-DEXPECTED_OUTPUT=${output}"
    -P "${CMAKE_CURRENT_SOURCE_DIR}/CMakeLists.txt")
  set_tests_properties(${name} PROPERTIES TIMEOUT 30)
endfunction()

example_check(lp_triangle registered_lp "" 0 "x=0 y=1 original_cost=5")
example_check(convex_original_norm registered_convex "" 0 "original_cost=4.1231056.*squared_cost=17")
example_check(resolved_history resolved_scenario "" 0 "states=0,0.25,1 controls=0.25,0.75 original_cost=0")
example_check(file_history scenario_file "${CMAKE_CURRENT_SOURCE_DIR}/scenarios/two-stage-integrator.json" 0
  "states=0,0.25,1 controls=0.25,0.75 original_cost=0")
example_check(substitution_highs backend_substitution csl.lp.highs 0 "backend=csl.lp.highs version=1.0.0.highs.1.11.0")
example_check(substitution_phase_one backend_substitution phase-one-bland 0 "backend=phase-one-bland version=1")
example_check(lp_unknown_backend registered_lp missing-backend 2 "Selection rejected.*missing-backend")
example_check(convex_unknown_backend registered_convex missing-backend 2 "Selection rejected.*missing-backend")
example_check(substitution_unknown_backend backend_substitution missing-backend 2 "Selection rejected.*missing-backend")
example_check(file_missing scenario_file "${CMAKE_CURRENT_BINARY_DIR}/no-such-scenario.json" 2 "Input rejected.*expected")
file(WRITE "${CMAKE_CURRENT_BINARY_DIR}/malformed.json" "{ invalid JSON")
example_check(file_malformed scenario_file "${CMAKE_CURRENT_BINARY_DIR}/malformed.json" 2 "Input rejected.*expected")
example_check(file_no_argument scenario_file "" 2 "Usage: scenario_file")
