# Copy only consumer inputs into a separate source tree. Its sole product
# dependency is find_package(CSL CONFIG), resolved from the installed prefix.
if(NOT DEFINED CSL_BUILD_PARALLELISM)
  set(CSL_BUILD_PARALLELISM 4)
endif()
if(NOT DEFINED CSL_ENABLE_CASADI)
  set(CSL_ENABLE_CASADI OFF)
endif()
set(casadi_args)
if(CSL_ENABLE_CASADI)
  if(NOT IS_ABSOLUTE "${CSL_CASADI_DIR}" OR NOT EXISTS "${CSL_CASADI_DIR}/casadi-config.cmake")
    message(FATAL_ERROR "The optional installed consumer requires the configured CasADi package directory")
  endif()
  list(APPEND casadi_args "-Dcasadi_DIR=${CSL_CASADI_DIR}")
endif()
if(NOT CSL_BUILD_PARALLELISM MATCHES "^[1-9][0-9]*$")
  message(FATAL_ERROR "CSL_BUILD_PARALLELISM must be a positive integer")
endif()
if(IS_ABSOLUTE "${CSL_INSTALL_LIBDIR}" OR
   IS_ABSOLUTE "${CSL_INSTALL_INCLUDEDIR}" OR
   IS_ABSOLUTE "${CSL_INSTALL_DATADIR}")
  message(FATAL_ERROR
    "installed_public_client requires relative install directories; absolute destinations are outside its temporary prefix")
endif()
set(work "${CSL_BUILD_DIR}/installed-consumer")
file(MAKE_DIRECTORY "${work}/source")
set(prefix "${work}/prefix")
file(MAKE_DIRECTORY "${work}/source")
file(COPY "${CSL_SOURCE_DIR}/tests/installed/CMakeLists.txt" DESTINATION "${work}/source")
# Installed consumers are curated by tests/installed/CMakeLists.txt. Stage all
# consumer translation units from that directory so adding a target cannot
# silently omit its source from this isolated package check.
file(GLOB installed_consumer_sources
  "${CSL_SOURCE_DIR}/tests/installed/*.cpp")
if(NOT installed_consumer_sources)
  message(FATAL_ERROR "No installed consumer sources found")
endif()
file(COPY ${installed_consumer_sources} DESTINATION "${work}/source")
foreach(consumer_source IN LISTS installed_consumer_sources)
  get_filename_component(consumer_name "${consumer_source}" NAME)
  if(NOT EXISTS "${work}/source/${consumer_name}")
    message(FATAL_ERROR "Installed consumer was not staged: ${consumer_name}")
  endif()
endforeach()
file(COPY "${CSL_SOURCE_DIR}/tests/contract/public_client.cpp" DESTINATION "${work}/source")
file(COPY "${CSL_SOURCE_DIR}/tests/contract/public_headers_client.cpp" DESTINATION "${work}/source")
file(COPY
  "${CSL_SOURCE_DIR}/examples/native_slide50_reachability.cpp"
  "${CSL_SOURCE_DIR}/examples/native_model_catalogue.cpp"
  "${CSL_SOURCE_DIR}/examples/native_four_state_reachability.cpp"
  "${CSL_SOURCE_DIR}/examples/native_discrete_models.cpp"
  "${CSL_SOURCE_DIR}/examples/native_flexible_pitch.cpp"
  "${CSL_SOURCE_DIR}/examples/nominal_quadratic_history_2d.cpp"
  "${CSL_SOURCE_DIR}/examples/native_spatial_flight.cpp"
  "${CSL_SOURCE_DIR}/examples/native_catalogue_projection.hpp"
  "${CSL_SOURCE_DIR}/examples/quadcopter_mpc.cpp"
  "${CSL_SOURCE_DIR}/examples/quadcopter_mpc_task.cpp"
  "${CSL_SOURCE_DIR}/examples/quadcopter_mpc_task.hpp"
  "${CSL_SOURCE_DIR}/examples/quadcopter_mpc_scalar_contract.cpp"
  "${CSL_SOURCE_DIR}/examples/quadcopter_mpc_check.cmake"
  DESTINATION "${work}/source")
if(CSL_STAGE_ONLY)
  return()
endif()
execute_process(COMMAND "${CMAKE_COMMAND}" --install "${CSL_BUILD_DIR}"
  --config "${CSL_CONFIG}" --prefix "${prefix}" COMMAND_ERROR_IS_FATAL ANY)
# Installed packages expose behavior through headers and executable consumers;
# Markdown working documents stay in the source repository and are not packaged.
file(GLOB_RECURSE installed_markdown_docs LIST_DIRECTORIES false
  "${prefix}/${CSL_INSTALL_DATADIR}/CSL/*.md"
  "${prefix}/${CSL_INSTALL_DATADIR}/doc/CSL/*.md")
if(installed_markdown_docs)
  message(FATAL_ERROR
    "Markdown working documents must not be installed: ${installed_markdown_docs}")
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
  ${casadi_args}
  "-DCMAKE_CXX_COMPILER=${CSL_CXX_COMPILER}"
  "-DCMAKE_CXX_COMPILER_LAUNCHER=${CSL_CXX_COMPILER_LAUNCHER}"
  "-DCMAKE_CXX_FLAGS=${CSL_CXX_FLAGS}"
  "-DCMAKE_EXE_LINKER_FLAGS=${CSL_EXE_LINKER_FLAGS}"
  "-DCSL_EXPECT_HIGHS=${CSL_EXPECT_HIGHS}" "-DCSL_EXPECT_QHULL=${CSL_EXPECT_QHULL}"
  COMMAND_ERROR_IS_FATAL ANY)
execute_process(COMMAND "${CMAKE_COMMAND}" --build "${work}/build"
  --config "${CSL_CONFIG}" --parallel "${CSL_BUILD_PARALLELISM}"
  COMMAND_ERROR_IS_FATAL ANY)
execute_process(COMMAND "${CMAKE_CTEST_COMMAND}" --test-dir "${work}/build"
  -C "${CSL_CONFIG}" --output-on-failure --no-tests=error COMMAND_ERROR_IS_FATAL ANY)

# Exercise the README examples as a second, isolated installed-package consumer.
# Copy only their public sources/template: no repository include or build paths.
set(example_source "${work}/examples-source")
file(MAKE_DIRECTORY "${example_source}/scenarios")
foreach(example_file CMakeLists.txt registered_lp.cpp registered_convex.cpp
    resolved_scenario.cpp scenario_file.cpp backend_substitution.cpp registered_synthesis_comparison.cpp
    nominal_linear_exact_2d.cpp scenario_cli.cpp continuous_policy.cpp
    source_index_geometry_2d.cpp adaptive_ode_replay.cpp scenario_backend_substitution.cpp
    native_slide50_reachability.cpp native_model_catalogue.cpp native_four_state_reachability.cpp
    native_discrete_models.cpp native_model_tracking.cpp native_catalogue_projection.hpp
    quadcopter_mpc.cpp quadcopter_mpc_task.cpp quadcopter_mpc_task.hpp quadcopter_mpc_scalar_contract.cpp
    quadcopter_mpc_check.cmake native_flexible_pitch.cpp
    nominal_quadratic_history_2d.cpp native_spatial_flight.cpp
    scenario_backend_artifact_check.cpp)
  file(COPY "${CSL_SOURCE_DIR}/examples/${example_file}" DESTINATION "${example_source}")
endforeach()
file(COPY "${CSL_SOURCE_DIR}/examples/scenario_cli_export_check.cmake"
  "${CSL_SOURCE_DIR}/examples/scenario_cli_methods_export_check.cmake"
  "${CSL_SOURCE_DIR}/examples/scenario_cli_identity_check.cmake"
  "${CSL_SOURCE_DIR}/examples/scenario_backend_substitution_check.cmake"
  DESTINATION "${example_source}")
file(COPY "${CSL_SOURCE_DIR}/examples/scenarios/two-stage-integrator.json"
  "${CSL_SOURCE_DIR}/examples/scenarios/two-stage-integrator-highs.json"
  "${CSL_SOURCE_DIR}/examples/scenarios/two-stage-integrator-phase-one.json"
  DESTINATION "${example_source}/scenarios")
file(COPY "${CSL_SOURCE_DIR}/examples/scenarios/double-integrator-generality.json"
  DESTINATION "${example_source}/scenarios")
execute_process(COMMAND "${CMAKE_COMMAND}" -S "${example_source}" -B "${work}/examples-build"
  ${generator_args} "-DCMAKE_PREFIX_PATH=${prefix}" "-DCMAKE_BUILD_TYPE=${CSL_CONFIG}"
  ${casadi_args}
  "-DCMAKE_CXX_COMPILER=${CSL_CXX_COMPILER}" "-DCMAKE_CXX_FLAGS=${CSL_CXX_FLAGS}"
  "-DCMAKE_CXX_COMPILER_LAUNCHER=${CSL_CXX_COMPILER_LAUNCHER}"
  "-DCMAKE_EXE_LINKER_FLAGS=${CSL_EXE_LINKER_FLAGS}"
  COMMAND_ERROR_IS_FATAL ANY)
execute_process(COMMAND "${CMAKE_COMMAND}" --build "${work}/examples-build"
  --config "${CSL_CONFIG}" --parallel "${CSL_BUILD_PARALLELISM}"
  COMMAND_ERROR_IS_FATAL ANY)
execute_process(COMMAND "${CMAKE_CTEST_COMMAND}" --test-dir "${work}/examples-build"
  -C "${CSL_CONFIG}" --output-on-failure --no-tests=error COMMAND_ERROR_IS_FATAL ANY)
