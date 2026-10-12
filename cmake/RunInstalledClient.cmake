# Copy only consumer inputs into a separate source tree. Its sole product
# dependency is find_package(CSL CONFIG), resolved from the installed prefix.
set(work "${CSL_BUILD_DIR}/installed-consumer")
set(prefix "${work}/prefix")
file(MAKE_DIRECTORY "${work}/source")
file(COPY "${CSL_SOURCE_DIR}/tests/installed/CMakeLists.txt" DESTINATION "${work}/source")
file(COPY "${CSL_SOURCE_DIR}/tests/contract/public_client.cpp" DESTINATION "${work}/source")
file(COPY "${CSL_SOURCE_DIR}/tests/contract/public_headers_client.cpp" DESTINATION "${work}/source")
file(COPY "${CSL_SOURCE_DIR}/tests/installed/numeric_client.cpp" DESTINATION "${work}/source")
file(COPY "${CSL_SOURCE_DIR}/tests/installed/model_client.cpp" DESTINATION "${work}/source")
file(COPY "${CSL_SOURCE_DIR}/tests/installed/problem_client.cpp" DESTINATION "${work}/source")
file(COPY "${CSL_SOURCE_DIR}/tests/installed/resolved_problem_client.cpp" DESTINATION "${work}/source")
file(COPY "${CSL_SOURCE_DIR}/tests/installed/execution_client.cpp" DESTINATION "${work}/source")
file(COPY "${CSL_SOURCE_DIR}/tests/installed/optimization_client.cpp" DESTINATION "${work}/source")
file(COPY "${CSL_SOURCE_DIR}/tests/installed/registry_client.cpp" DESTINATION "${work}/source")
file(COPY "${CSL_SOURCE_DIR}/tests/installed/sets_client.cpp" DESTINATION "${work}/source")
file(COPY "${CSL_SOURCE_DIR}/tests/installed/objectives_client.cpp" DESTINATION "${work}/source")
file(COPY "${CSL_SOURCE_DIR}/tests/installed/highs_client.cpp" DESTINATION "${work}/source")
file(COPY "${CSL_SOURCE_DIR}/tests/installed/convex_client.cpp" DESTINATION "${work}/source")
execute_process(COMMAND "${CMAKE_COMMAND}" --install "${CSL_BUILD_DIR}"
  --config "${CSL_CONFIG}" --prefix "${prefix}" COMMAND_ERROR_IS_FATAL ANY)
# Inspect the installed artifacts, ignoring comments that discuss dependency names.
file(GLOB_RECURSE public_headers "${prefix}/include/csl/*.hpp")
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
  "-DCMAKE_CXX_FLAGS=${CSL_CXX_FLAGS}"
  "-DCMAKE_EXE_LINKER_FLAGS=${CSL_EXE_LINKER_FLAGS}"
  COMMAND_ERROR_IS_FATAL ANY)
execute_process(COMMAND "${CMAKE_COMMAND}" --build "${work}/build"
  --config "${CSL_CONFIG}" --parallel 4 COMMAND_ERROR_IS_FATAL ANY)
execute_process(COMMAND "${CMAKE_CTEST_COMMAND}" --test-dir "${work}/build"
  -C "${CSL_CONFIG}" --output-on-failure --no-tests=error COMMAND_ERROR_IS_FATAL ANY)
