# Standalone entry point for the in-tree OPT-04 report harness.
cmake_minimum_required(VERSION 3.31)
project(CSLOPT04Report LANGUAGES C CXX)
if(NOT CSL_ROOT)
  message(FATAL_ERROR "Set CSL_ROOT to the repository root")
endif()
set(CSL_BUILD_OPT04_REPORT ON CACHE BOOL "" FORCE)
set(BUILD_TESTING OFF CACHE BOOL "" FORCE)
add_subdirectory("${CSL_ROOT}" csl)
