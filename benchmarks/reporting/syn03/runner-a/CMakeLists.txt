cmake_minimum_required(VERSION 3.31)
project(CSLSYN03StrategyAMeasurement LANGUAGES C CXX)

if(NOT DEFINED CSL_SOURCE_ROOT)
  message(FATAL_ERROR "CSL_SOURCE_ROOT must name the pinned clean solver checkout")
endif()
set(BUILD_TESTING OFF CACHE BOOL "Build repository tests" FORCE)
add_subdirectory("${CSL_SOURCE_ROOT}" csl-source)

add_executable(csl_syn03_strategy_a_report "${CMAKE_CURRENT_LIST_DIR}/../strategy_a_measure.cpp")
target_link_libraries(csl_syn03_strategy_a_report PRIVATE
  CSL::strategy_a CSL::polyhedral CSL::affine_sum CSL::qhull_conversion CSL::highs_lp CSL::highs_convex)
target_compile_features(csl_syn03_strategy_a_report PRIVATE cxx_std_20)
target_compile_definitions(csl_syn03_strategy_a_report PRIVATE $<$<CONFIG:Release>:NDEBUG>)
if(MSVC)
  target_compile_options(csl_syn03_strategy_a_report PRIVATE /W4 /WX /permissive-)
else()
  target_compile_options(csl_syn03_strategy_a_report PRIVATE -Wall -Wextra -Wpedantic -Werror)
endif()
