cmake_minimum_required(VERSION 3.31)
project(CSLOPT11ReportHarness LANGUAGES C CXX)

set(BUILD_TESTING OFF CACHE BOOL "" FORCE)
set(CSL_BUILD_REPORTS OFF CACHE BOOL "" FORCE)
if(NOT DEFINED CSL_ROOT)
  get_filename_component(CSL_ROOT "${CMAKE_CURRENT_LIST_DIR}/../../../../" ABSOLUTE)
endif()
get_filename_component(CSL_ROOT "${CSL_ROOT}" REALPATH)
execute_process(COMMAND git -C "${CSL_ROOT}" rev-parse HEAD
  OUTPUT_VARIABLE CSL_OPT11_SOURCE_COMMIT OUTPUT_STRIP_TRAILING_WHITESPACE
  RESULT_VARIABLE CSL_OPT11_GIT_STATUS)
if(NOT CSL_OPT11_GIT_STATUS EQUAL 0)
  message(FATAL_ERROR "OPT-11 report harness requires a Git source checkout")
endif()
file(SHA256 "${CMAKE_CURRENT_LIST_DIR}/recursive_hull_driver.cpp" CSL_OPT11_HARNESS_SHA256)
set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS
  "${CMAKE_CURRENT_LIST_DIR}/recursive_hull_driver.cpp")

add_subdirectory("${CSL_ROOT}" csl)
add_executable(csl_opt11_measure recursive_hull_driver.cpp)
target_link_libraries(csl_opt11_measure PRIVATE CSL::hull CSL::highs_lp)
target_compile_features(csl_opt11_measure PRIVATE cxx_std_20)
target_compile_definitions(csl_opt11_measure PRIVATE
  CSL_OPT11_SOURCE_COMMIT="${CSL_OPT11_SOURCE_COMMIT}"
  CSL_OPT11_HARNESS_SHA256="${CSL_OPT11_HARNESS_SHA256}"
  CSL_OPT11_CONFIG="$<CONFIG>")
set_target_properties(csl_opt11_measure PROPERTIES CXX_EXTENSIONS OFF)
