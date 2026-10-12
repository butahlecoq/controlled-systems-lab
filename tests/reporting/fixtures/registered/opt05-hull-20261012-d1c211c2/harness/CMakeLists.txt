cmake_minimum_required(VERSION 3.31)
project(CSLHullReportHarness LANGUAGES C CXX)

set(BUILD_TESTING OFF CACHE BOOL "" FORCE)
set(CSL_BUILD_REPORTS OFF CACHE BOOL "" FORCE)
get_filename_component(CSL_REPOSITORY_ROOT "${CMAKE_CURRENT_LIST_DIR}/../../../../" ABSOLUTE)
add_subdirectory("${CSL_REPOSITORY_ROOT}" csl)

add_executable(csl_hull_measure hull_measure.cpp)
target_link_libraries(csl_hull_measure PRIVATE CSL::hull CSL::highs_lp)
target_compile_features(csl_hull_measure PRIVATE cxx_std_20)
set_target_properties(csl_hull_measure PROPERTIES CXX_EXTENSIONS OFF)
