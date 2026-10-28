cmake_minimum_required(VERSION 3.31)
project(CSLMPC02SlewMeasurement LANGUAGES C CXX)

if(NOT DEFINED CSL_SOURCE_ROOT)
  message(FATAL_ERROR "CSL_SOURCE_ROOT must name the pinned clean solver checkout")
endif()
set(BUILD_TESTING OFF CACHE BOOL "Build repository tests" FORCE)
add_subdirectory("${CSL_SOURCE_ROOT}" csl-source)

execute_process(
  COMMAND git -C "${CSL_SOURCE_ROOT}" rev-parse HEAD
  OUTPUT_VARIABLE CSL_SOURCE_COMMIT
  OUTPUT_STRIP_TRAILING_WHITESPACE
  COMMAND_ERROR_IS_FATAL ANY)

add_executable(csl_mpc02_slew_measure "${CMAKE_CURRENT_LIST_DIR}/../../mpc02_slew_direct_vs_lift.cpp")
target_link_libraries(csl_mpc02_slew_measure PRIVATE CSL::input CSL::strategy_b CSL::highs_convex)
target_compile_features(csl_mpc02_slew_measure PRIVATE cxx_std_20)
target_compile_definitions(csl_mpc02_slew_measure PRIVATE $<$<CONFIG:Release>:NDEBUG>)
target_compile_definitions(csl_mpc02_slew_measure PRIVATE CSL_SOURCE_COMMIT="${CSL_SOURCE_COMMIT}")
if(MSVC)
  target_compile_options(csl_mpc02_slew_measure PRIVATE /W4 /WX /permissive-)
else()
  target_compile_options(csl_mpc02_slew_measure PRIVATE -Wall -Wextra -Wpedantic -Werror)
endif()
