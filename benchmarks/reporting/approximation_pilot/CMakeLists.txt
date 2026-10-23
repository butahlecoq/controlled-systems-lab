cmake_minimum_required(VERSION 3.31)
project(CSLApproximationMatchedPilot LANGUAGES C CXX)

set(BUILD_TESTING OFF CACHE BOOL "" FORCE)
set(CSL_BUILD_REPORTS OFF CACHE BOOL "" FORCE)
get_filename_component(CSL_ROOT "${CMAKE_CURRENT_LIST_DIR}/../../../" ABSOLUTE)
execute_process(COMMAND git -C "${CSL_ROOT}" rev-parse HEAD
  OUTPUT_VARIABLE CSL_SOURCE_COMMIT OUTPUT_STRIP_TRAILING_WHITESPACE
  COMMAND_ERROR_IS_FATAL ANY)
add_subdirectory("${CSL_ROOT}" csl)

add_executable(csl_approximation_matched_pilot driver.cpp)
target_link_libraries(csl_approximation_matched_pilot PRIVATE
  CSL::approximation CSL::geometry_generators CSL::quickhull_2d)
target_compile_features(csl_approximation_matched_pilot PRIVATE cxx_std_20)
target_compile_definitions(csl_approximation_matched_pilot PRIVATE
  CSL_SOURCE_COMMIT="${CSL_SOURCE_COMMIT}")
set_target_properties(csl_approximation_matched_pilot PROPERTIES CXX_EXTENSIONS OFF)
