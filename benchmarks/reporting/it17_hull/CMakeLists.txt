cmake_minimum_required(VERSION 3.31)
project(CSLITIS17HullExploration LANGUAGES C CXX)

set(BUILD_TESTING OFF CACHE BOOL "" FORCE)
set(CSL_BUILD_REPORTS OFF CACHE BOOL "" FORCE)
if(NOT DEFINED CSL_ROOT)
  get_filename_component(CSL_ROOT "${CMAKE_CURRENT_LIST_DIR}/../../../../" ABSOLUTE)
endif()
execute_process(COMMAND git -C "${CSL_ROOT}" rev-parse HEAD
  OUTPUT_VARIABLE CSL_SOURCE_COMMIT OUTPUT_STRIP_TRAILING_WHITESPACE
  COMMAND_ERROR_IS_FATAL ANY)
add_subdirectory("${CSL_ROOT}" csl)

add_executable(csl_it17_hull_preliminary preliminary_driver.cpp)
target_link_libraries(csl_it17_hull_preliminary PRIVATE
  CSL::hull CSL::quickhull_2d CSL::highs_lp)
target_compile_features(csl_it17_hull_preliminary PRIVATE cxx_std_20)
target_compile_definitions(csl_it17_hull_preliminary PRIVATE
  CSL_SOURCE_COMMIT="${CSL_SOURCE_COMMIT}")
set_target_properties(csl_it17_hull_preliminary PROPERTIES CXX_EXTENSIONS OFF)
