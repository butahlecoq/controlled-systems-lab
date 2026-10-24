cmake_minimum_required(VERSION 3.31)
project(CSLOBS04InstrumentationComparison LANGUAGES C CXX)

if(NOT DEFINED CSL_SOURCE_ROOT)
  message(FATAL_ERROR "CSL_SOURCE_ROOT must name the pinned clean solver checkout")
endif()
set(BUILD_TESTING OFF CACHE BOOL "Build repository tests" FORCE)
add_subdirectory("${CSL_SOURCE_ROOT}" csl-source)

add_executable(csl_obs04_instrumentation_comparison instrumentation_comparison.cpp)
target_link_libraries(csl_obs04_instrumentation_comparison PRIVATE
  CSL::application CSL::strategy_a CSL::strategy_b CSL::polyhedral CSL::affine_sum
  CSL::qhull_conversion CSL::highs_lp CSL::highs_convex CSL::witness_selector)
target_compile_features(csl_obs04_instrumentation_comparison PRIVATE cxx_std_20)
target_compile_definitions(csl_obs04_instrumentation_comparison PRIVATE $<$<CONFIG:Release>:NDEBUG>)
if(MSVC)
  target_compile_options(csl_obs04_instrumentation_comparison PRIVATE /W4 /WX /permissive-)
else()
  target_compile_options(csl_obs04_instrumentation_comparison PRIVATE -Wall -Wextra -Wpedantic -Werror)
endif()
