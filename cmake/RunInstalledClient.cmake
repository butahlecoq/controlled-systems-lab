# Copy only consumer inputs into a separate source tree. Its sole product
# dependency is find_package(CSL CONFIG), resolved from the installed prefix.
if(IS_ABSOLUTE "${CSL_INSTALL_LIBDIR}" OR
   IS_ABSOLUTE "${CSL_INSTALL_INCLUDEDIR}" OR
   IS_ABSOLUTE "${CSL_INSTALL_DATADIR}")
  message(FATAL_ERROR
    "installed_public_client requires relative install directories; absolute destinations are outside its temporary prefix")
endif()
set(work "${CSL_BUILD_DIR}/installed-consumer")
file(MAKE_DIRECTORY "${work}/source")
file(COPY "${CSL_SOURCE_DIR}/tests/installed/witness_selector_client.cpp" DESTINATION "${work}/source")
set(prefix "${work}/prefix")
file(MAKE_DIRECTORY "${work}/source")
file(COPY "${CSL_SOURCE_DIR}/tests/installed/CMakeLists.txt" DESTINATION "${work}/source")
file(COPY "${CSL_SOURCE_DIR}/tests/contract/public_client.cpp" DESTINATION "${work}/source")
file(COPY "${CSL_SOURCE_DIR}/tests/contract/public_headers_client.cpp" DESTINATION "${work}/source")
file(COPY "${CSL_SOURCE_DIR}/tests/installed/numeric_client.cpp" DESTINATION "${work}/source")
file(COPY "${CSL_SOURCE_DIR}/tests/installed/model_client.cpp" DESTINATION "${work}/source")
file(COPY "${CSL_SOURCE_DIR}/tests/installed/hybrid_path_program_client.cpp" DESTINATION "${work}/source")
file(COPY "${CSL_SOURCE_DIR}/tests/installed/simulation_client.cpp" DESTINATION "${work}/source")
file(COPY "${CSL_SOURCE_DIR}/tests/installed/box_parallelotope_client.cpp" DESTINATION "${work}/source")
file(COPY "${CSL_SOURCE_DIR}/tests/installed/ellipsoidal_client.cpp" DESTINATION "${work}/source")
file(COPY "${CSL_SOURCE_DIR}/tests/installed/lazy_geometry_client.cpp" DESTINATION "${work}/source")
file(COPY "${CSL_SOURCE_DIR}/tests/installed/zonotope_reduction_client.cpp" DESTINATION "${work}/source")
file(COPY "${CSL_SOURCE_DIR}/tests/installed/finite_feedback_client.cpp" DESTINATION "${work}/source")
file(COPY "${CSL_SOURCE_DIR}/tests/installed/finite_action_minimax_client.cpp" DESTINATION "${work}/source")
file(COPY "${CSL_SOURCE_DIR}/tests/installed/finite_action_histories_client.cpp" DESTINATION "${work}/source")
file(COPY "${CSL_SOURCE_DIR}/tests/installed/validated_finite_action_minimax_client.cpp" DESTINATION "${work}/source")
file(COPY "${CSL_SOURCE_DIR}/tests/installed/validated_finite_action_minimax_port_client.cpp" DESTINATION "${work}/source")
file(COPY "${CSL_SOURCE_DIR}/tests/installed/problem_client.cpp" DESTINATION "${work}/source")
file(COPY "${CSL_SOURCE_DIR}/tests/installed/resolved_problem_client.cpp" DESTINATION "${work}/source")
file(COPY "${CSL_SOURCE_DIR}/tests/installed/execution_client.cpp" DESTINATION "${work}/source")
file(COPY "${CSL_SOURCE_DIR}/tests/installed/experiments_client.cpp" DESTINATION "${work}/source")
file(COPY "${CSL_SOURCE_DIR}/tests/installed/optimization_client.cpp" DESTINATION "${work}/source")
file(COPY "${CSL_SOURCE_DIR}/tests/installed/zoutendijk_projection_client.cpp" DESTINATION "${work}/source")
file(COPY "${CSL_SOURCE_DIR}/tests/installed/feasible_directions_client.cpp" DESTINATION "${work}/source")
file(COPY "${CSL_SOURCE_DIR}/tests/installed/registry_client.cpp" DESTINATION "${work}/source")
file(COPY "${CSL_SOURCE_DIR}/tests/installed/application_client.cpp" DESTINATION "${work}/source")
file(COPY "${CSL_SOURCE_DIR}/tests/installed/provider_client.cpp" DESTINATION "${work}/source")
file(COPY "${CSL_SOURCE_DIR}/tests/installed/sets_client.cpp" DESTINATION "${work}/source")
file(COPY "${CSL_SOURCE_DIR}/tests/installed/generators_client.cpp" DESTINATION "${work}/source")
file(COPY "${CSL_SOURCE_DIR}/tests/installed/generator_adapter_client.cpp" DESTINATION "${work}/source")
file(COPY "${CSL_SOURCE_DIR}/tests/installed/objectives_client.cpp" DESTINATION "${work}/source")
file(COPY "${CSL_SOURCE_DIR}/tests/installed/highs_client.cpp" DESTINATION "${work}/source")
file(COPY "${CSL_SOURCE_DIR}/tests/installed/phase_one_client.cpp" DESTINATION "${work}/source")
file(COPY "${CSL_SOURCE_DIR}/tests/installed/hull_reducer_client.cpp" DESTINATION "${work}/source")
file(COPY "${CSL_SOURCE_DIR}/tests/installed/affine_sum_client.cpp" DESTINATION "${work}/source")
file(COPY "${CSL_SOURCE_DIR}/tests/installed/terminal_minimizers_client.cpp" DESTINATION "${work}/source")
file(COPY "${CSL_SOURCE_DIR}/tests/installed/convex_client.cpp" DESTINATION "${work}/source")
file(COPY "${CSL_SOURCE_DIR}/tests/installed/run_statistics_client.cpp" DESTINATION "${work}/source")
file(COPY "${CSL_SOURCE_DIR}/tests/installed/plot_data_client.cpp" DESTINATION "${work}/source")
file(COPY "${CSL_SOURCE_DIR}/tests/installed/plot_request_client.cpp" DESTINATION "${work}/source")
file(COPY "${CSL_SOURCE_DIR}/tests/installed/input_client.cpp" DESTINATION "${work}/source")
file(COPY "${CSL_SOURCE_DIR}/tests/installed/continuous_discretization_client.cpp" DESTINATION "${work}/source")
file(COPY "${CSL_SOURCE_DIR}/tests/installed/conversion_client.cpp" DESTINATION "${work}/source")
file(COPY "${CSL_SOURCE_DIR}/tests/installed/polyhedral_intersection_client.cpp" DESTINATION "${work}/source")
file(COPY "${CSL_SOURCE_DIR}/tests/installed/hybrid_reachability_client.cpp" DESTINATION "${work}/source")
file(COPY "${CSL_SOURCE_DIR}/tests/installed/projection_predecessor_client.cpp" DESTINATION "${work}/source")
file(COPY "${CSL_SOURCE_DIR}/tests/installed/nominal_forward_client.cpp" DESTINATION "${work}/source")
file(COPY "${CSL_SOURCE_DIR}/tests/installed/ts01_evidence_client.cpp" DESTINATION "${work}/source")
file(COPY "${CSL_SOURCE_DIR}/tests/installed/ts01_issuer_forge_client.cpp" DESTINATION "${work}/source")
file(COPY "${CSL_SOURCE_DIR}/tests/installed/ts01_callback_forge_client.cpp" DESTINATION "${work}/source")
file(COPY "${CSL_SOURCE_DIR}/tests/installed/ts01_relation_factory_forge_client.cpp" DESTINATION "${work}/source")
file(COPY "${CSL_SOURCE_DIR}/tests/installed/farkas_factory_forge_client.cpp" DESTINATION "${work}/source")
execute_process(COMMAND "${CMAKE_COMMAND}" --install "${CSL_BUILD_DIR}"
  --config "${CSL_CONFIG}" --prefix "${prefix}" COMMAND_ERROR_IS_FATAL ANY)
set(hybrid_contract "${prefix}/${CSL_INSTALL_DATADIR}/CSL/docs/contracts/hybrid-systems.md")
if(NOT EXISTS "${hybrid_contract}")
  message(FATAL_ERROR "Installed hybrid API contract is missing: ${hybrid_contract}")
endif()
# Inspect the installed artifacts, ignoring comments that discuss dependency names.
set(notices_root "${prefix}/${CSL_INSTALL_DATADIR}/CSL/notices")
if(NOT EXISTS "${notices_root}/nlohmann-json-3.11.3/LICENSE.MIT")
  message(FATAL_ERROR "Installed input dependency notice is missing")
endif()
foreach(eigen_notice IN ITEMS
    "${notices_root}/Eigen-3.4.0/COPYING.README"
    "${notices_root}/Eigen-3.4.0/COPYING.MPL2"
    "${notices_root}/Eigen-3.4.0/COPYING.BSD"
    "${notices_root}/Eigen-3.4.0/COPYING.APACHE"
    "${notices_root}/Eigen-3.4.0/COPYING.MINPACK")
  if(NOT EXISTS "${eigen_notice}")
    message(FATAL_ERROR "Installed Eigen dependency notice is missing: ${eigen_notice}")
  endif()
endforeach()
if(CSL_EXPECT_HIGHS)
  foreach(highs_notice IN ITEMS
      "${notices_root}/HiGHS-1.11.0/LICENSE.txt"
      "${notices_root}/HiGHS-1.11.0/extern/filereaderlp/LICENSE"
      "${notices_root}/HiGHS-1.11.0/extern/pdqsort/license.txt")
    if(NOT EXISTS "${highs_notice}")
      message(FATAL_ERROR "Installed HiGHS dependency notice is missing: ${highs_notice}")
    endif()
  endforeach()
endif()
if(CSL_EXPECT_QHULL AND NOT EXISTS
    "${notices_root}/Qhull-8.0.2/COPYING.txt")
  message(FATAL_ERROR "Installed Qhull dependency notice is missing")
endif()
set(exports_file "${prefix}/${CSL_INSTALL_LIBDIR}/cmake/CSL/CSLTargets.cmake")
if(NOT EXISTS "${exports_file}")
  message(FATAL_ERROR "Installed CMake target export is missing: ${exports_file}")
endif()
file(READ "${exports_file}" input_export)
if(input_export MATCHES "nlohmann|csl_json")
  message(FATAL_ERROR "Private input JSON dependency leaked into exports")
endif()
file(GLOB_RECURSE doctest_install_artifacts LIST_DIRECTORIES false
  "${prefix}/*/doctest/*"
  "${prefix}/*/cmake/doctest/*")
if(doctest_install_artifacts)
  message(FATAL_ERROR
    "Test-only doctest artifacts were installed: ${doctest_install_artifacts}")
endif()
file(GLOB_RECURSE public_headers
  "${prefix}/${CSL_INSTALL_INCLUDEDIR}/csl/*.hpp")
if(NOT public_headers)
  message(FATAL_ERROR "No installed CSL public headers found for dependency audit.")
endif()
foreach(header IN LISTS public_headers)
  file(READ "${header}" header_source)
  string(REGEX REPLACE "/\\*([^*]|\\*+[^*/])*\\*+/" "" header_source "${header_source}")
  string(REGEX REPLACE "//[^\n]*" "" header_source "${header_source}")
  if(header_source MATCHES "#[ \t]*include[ \t]*[<\"][^>\"\n]*(Eigen/|eigen3/|Highs[^>\"\n]*|highs/|nlohmann/|doctest/)" OR
     header_source MATCHES "(Eigen|nlohmann|doctest)[ \t\n]*::" OR
     header_source MATCHES "(^|[^A-Za-z0-9_])(Highs|HighsLp|HighsModel|HighsSparseMatrix|HighsHessian)([^A-Za-z0-9_]|$)")
    message(FATAL_ERROR "Selected private dependency leaked into installed public header: ${header}")
  endif()
endforeach()
message(STATUS "Installed public header dependency audit passed (${public_headers})")
set(generator_args -G "${CSL_GENERATOR}")
if(CSL_PLATFORM)
  list(APPEND generator_args -A "${CSL_PLATFORM}")
endif()
if(CSL_TOOLSET)
  list(APPEND generator_args -T "${CSL_TOOLSET}")
endif()
execute_process(COMMAND "${CMAKE_COMMAND}" -S "${work}/source" -B "${work}/build"
  ${generator_args} "-DCMAKE_PREFIX_PATH=${prefix}" "-DCMAKE_BUILD_TYPE=${CSL_CONFIG}"
  "-DCMAKE_CXX_COMPILER=${CSL_CXX_COMPILER}"
  "-DCMAKE_CXX_COMPILER_LAUNCHER=${CSL_CXX_COMPILER_LAUNCHER}"
  "-DCMAKE_CXX_FLAGS=${CSL_CXX_FLAGS}"
  "-DCMAKE_EXE_LINKER_FLAGS=${CSL_EXE_LINKER_FLAGS}"
  "-DCSL_EXPECT_HIGHS=${CSL_EXPECT_HIGHS}" "-DCSL_EXPECT_QHULL=${CSL_EXPECT_QHULL}"
  COMMAND_ERROR_IS_FATAL ANY)
execute_process(COMMAND "${CMAKE_COMMAND}" --build "${work}/build"
  --config "${CSL_CONFIG}" --parallel 4 COMMAND_ERROR_IS_FATAL ANY)
execute_process(COMMAND "${CMAKE_CTEST_COMMAND}" --test-dir "${work}/build"
  -C "${CSL_CONFIG}" --output-on-failure --no-tests=error COMMAND_ERROR_IS_FATAL ANY)

# Exercise the README examples as a second, isolated installed-package consumer.
# Copy only their public sources/template: no repository include or build paths.
set(example_source "${work}/examples-source")
file(MAKE_DIRECTORY "${example_source}/scenarios")
foreach(example_file CMakeLists.txt registered_lp.cpp registered_convex.cpp
    resolved_scenario.cpp scenario_file.cpp backend_substitution.cpp registered_synthesis_comparison.cpp
    nominal_linear_exact_2d.cpp scenario_cli.cpp continuous_policy.cpp)
  file(COPY "${CSL_SOURCE_DIR}/examples/${example_file}" DESTINATION "${example_source}")
endforeach()
file(COPY "${CSL_SOURCE_DIR}/examples/scenario_cli_export_check.cmake"
  DESTINATION "${example_source}")
file(COPY "${CSL_SOURCE_DIR}/examples/scenarios/two-stage-integrator.json"
  DESTINATION "${example_source}/scenarios")
file(COPY "${CSL_SOURCE_DIR}/examples/scenarios/double-integrator-generality.json"
  DESTINATION "${example_source}/scenarios")
execute_process(COMMAND "${CMAKE_COMMAND}" -S "${example_source}" -B "${work}/examples-build"
  ${generator_args} "-DCMAKE_PREFIX_PATH=${prefix}" "-DCMAKE_BUILD_TYPE=${CSL_CONFIG}"
  "-DCMAKE_CXX_COMPILER=${CSL_CXX_COMPILER}" "-DCMAKE_CXX_FLAGS=${CSL_CXX_FLAGS}"
  "-DCMAKE_CXX_COMPILER_LAUNCHER=${CSL_CXX_COMPILER_LAUNCHER}"
  "-DCMAKE_EXE_LINKER_FLAGS=${CSL_EXE_LINKER_FLAGS}"
  COMMAND_ERROR_IS_FATAL ANY)
execute_process(COMMAND "${CMAKE_COMMAND}" --build "${work}/examples-build"
  --config "${CSL_CONFIG}" --parallel 4 COMMAND_ERROR_IS_FATAL ANY)
execute_process(COMMAND "${CMAKE_CTEST_COMMAND}" --test-dir "${work}/examples-build"
  -C "${CSL_CONFIG}" --output-on-failure --no-tests=error COMMAND_ERROR_IS_FATAL ANY)
