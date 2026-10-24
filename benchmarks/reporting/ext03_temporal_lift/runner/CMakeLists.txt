cmake_minimum_required(VERSION 3.31)
project(CSLEXT03TemporalLiftMeasurement LANGUAGES C CXX)

if(NOT DEFINED CSL_SOURCE_ROOT)
  message(FATAL_ERROR "CSL_SOURCE_ROOT must name the clean solver checkout")
endif()
set(BUILD_TESTING OFF CACHE BOOL "Build repository tests" FORCE)
add_subdirectory("${CSL_SOURCE_ROOT}" csl-source)

add_executable(csl_ext03_temporal_lift_report
  "${CMAKE_CURRENT_LIST_DIR}/../temporal_lift_measure.cpp")
target_link_libraries(csl_ext03_temporal_lift_report PRIVATE CSL::resolved_problem)
target_compile_features(csl_ext03_temporal_lift_report PRIVATE cxx_std_20)
target_compile_definitions(csl_ext03_temporal_lift_report PRIVATE $<$<CONFIG:Release>:NDEBUG>)
if(MSVC)
  target_compile_options(csl_ext03_temporal_lift_report PRIVATE /W4 /WX /permissive-)
else()
  target_compile_options(csl_ext03_temporal_lift_report PRIVATE -Wall -Wextra -Wpedantic -Werror)
endif()
