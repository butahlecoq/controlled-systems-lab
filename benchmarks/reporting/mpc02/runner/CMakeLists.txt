cmake_minimum_required(VERSION 3.31)
project(CSLMPC02Measurement LANGUAGES C CXX)

if(NOT DEFINED CSL_SOURCE_ROOT)
  message(FATAL_ERROR "CSL_SOURCE_ROOT must name the pinned clean solver checkout")
endif()
if(NOT CMAKE_BUILD_TYPE STREQUAL "Release")
  message(FATAL_ERROR "The MPC-02 measurement runner requires CMAKE_BUILD_TYPE=Release")
endif()
if(CMAKE_CONFIGURATION_TYPES)
  message(FATAL_ERROR "Use a single-configuration generator for an auditable Release build")
endif()
execute_process(
  COMMAND git -C "${CSL_SOURCE_ROOT}" status --porcelain --untracked-files=all
  OUTPUT_VARIABLE CSL_SOURCE_STATUS
  OUTPUT_STRIP_TRAILING_WHITESPACE
  COMMAND_ERROR_IS_FATAL ANY)
if(NOT CSL_SOURCE_STATUS STREQUAL "")
  message(FATAL_ERROR "CSL_SOURCE_ROOT must be a clean checkout before configure")
endif()
set(BUILD_TESTING OFF CACHE BOOL "Build repository tests" FORCE)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON CACHE BOOL "Retain the exact compiler invocation" FORCE)
add_subdirectory("${CSL_SOURCE_ROOT}" csl-source)
execute_process(
  COMMAND git -C "${CSL_SOURCE_ROOT}" rev-parse HEAD
  OUTPUT_VARIABLE CSL_SOURCE_COMMIT
  OUTPUT_STRIP_TRAILING_WHITESPACE
  COMMAND_ERROR_IS_FATAL ANY)
add_executable(csl_mpc02_slew_measure "${CMAKE_CURRENT_LIST_DIR}/../../mpc02_slew_direct_vs_lift.cpp")
target_link_libraries(csl_mpc02_slew_measure PRIVATE CSL::input CSL::strategy_b CSL::highs_convex)
target_compile_features(csl_mpc02_slew_measure PRIVATE cxx_std_20)
target_compile_definitions(csl_mpc02_slew_measure PRIVATE NDEBUG
  CSL_SOURCE_COMMIT="${CSL_SOURCE_COMMIT}"
  CSL_BUILD_TYPE="${CMAKE_BUILD_TYPE}"
  CSL_COMPILER_ID="${CMAKE_CXX_COMPILER_ID}"
  CSL_COMPILER_VERSION="${CMAKE_CXX_COMPILER_VERSION}")
add_executable(csl_mpc02_four_track_measure "${CMAKE_CURRENT_LIST_DIR}/../../mpc02_four_track_direct.cpp")
target_link_libraries(csl_mpc02_four_track_measure PRIVATE CSL::input CSL::strategy_b CSL::highs_convex)
target_compile_features(csl_mpc02_four_track_measure PRIVATE cxx_std_20)
target_compile_definitions(csl_mpc02_four_track_measure PRIVATE NDEBUG
  CSL_SOURCE_COMMIT="${CSL_SOURCE_COMMIT}"
  CSL_BUILD_TYPE="${CMAKE_BUILD_TYPE}"
  CSL_COMPILER_ID="${CMAKE_CXX_COMPILER_ID}"
  CSL_COMPILER_VERSION="${CMAKE_CXX_COMPILER_VERSION}")
if(MSVC)
  target_compile_options(csl_mpc02_four_track_measure PRIVATE /W4 /WX /permissive-)
else()
  target_compile_options(csl_mpc02_four_track_measure PRIVATE -Wall -Wextra -Wpedantic -Werror)
endif()
