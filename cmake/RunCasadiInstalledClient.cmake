cmake_minimum_required(VERSION 3.31)
foreach(required CSL_SOURCE_DIR CSL_INSTALL_PREFIX CSL_WORK_DIR CSL_CASADI_DIR)
  if(NOT IS_ABSOLUTE "${${required}}")
    message(FATAL_ERROR "${required} must be an explicit absolute path")
  endif()
endforeach()
file(MAKE_DIRECTORY "${CSL_WORK_DIR}/source" "${CSL_WORK_DIR}/empty-path" "${CSL_WORK_DIR}/tmp")
file(COPY
  "${CSL_SOURCE_DIR}/tests/installed/fixed_tail_policy_client.cpp"
  "${CSL_SOURCE_DIR}/tests/unit/reachability/fixed_tail_validation_tests.cpp"
  "${CSL_SOURCE_DIR}/tests/unit/reachability/inner_template_tests.cpp"
  DESTINATION "${CSL_WORK_DIR}/source")
file(WRITE "${CSL_WORK_DIR}/source/CMakeLists.txt" [=[
cmake_minimum_required(VERSION 3.31)
project(CasadiInstalledConsumers LANGUAGES CXX)
find_package(CSL CONFIG REQUIRED)
add_executable(policy fixed_tail_policy_client.cpp)
target_link_libraries(policy PRIVATE CSL::casadi_fixed_tail)
add_executable(boundaries fixed_tail_validation_tests.cpp)
target_link_libraries(boundaries PRIVATE CSL::fixed_tail_policy)
add_executable(templates inner_template_tests.cpp)
target_link_libraries(templates PRIVATE CSL::inner_template)
]=])
execute_process(COMMAND "${CMAKE_COMMAND}" -S "${CSL_WORK_DIR}/source" -B "${CSL_WORK_DIR}/build" -G Ninja
  -DCMAKE_BUILD_TYPE=Release "-DCMAKE_PREFIX_PATH=${CSL_INSTALL_PREFIX}" "-Dcasadi_DIR=${CSL_CASADI_DIR}"
  COMMAND_ERROR_IS_FATAL ANY)
execute_process(COMMAND "${CMAKE_COMMAND}" --build "${CSL_WORK_DIR}/build" --parallel 1
  COMMAND_ERROR_IS_FATAL ANY)
foreach(client policy boundaries templates)
  execute_process(COMMAND /usr/bin/env -i "PATH=${CSL_WORK_DIR}/empty-path" "TMPDIR=${CSL_WORK_DIR}/tmp"
    OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 "${CSL_WORK_DIR}/build/${client}"
    COMMAND_ERROR_IS_FATAL ANY)
endforeach()
