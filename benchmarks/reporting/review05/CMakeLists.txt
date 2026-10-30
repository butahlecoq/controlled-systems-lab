cmake_minimum_required(VERSION 3.31)
project(CSLReview05HorizonLadder LANGUAGES C CXX)

if(NOT DEFINED CSL_SOURCE_ROOT)
  message(FATAL_ERROR "CSL_SOURCE_ROOT must point to the checked-out solver source")
endif()

set(BUILD_TESTING OFF CACHE BOOL "Build repository tests" FORCE)
add_subdirectory("${CSL_SOURCE_ROOT}" csl-source)

add_executable(csl_review05_horizon_ladder horizon_ladder.cpp)
target_link_libraries(csl_review05_horizon_ladder PRIVATE
  CSL::input CSL::application CSL::strategy_a CSL::strategy_b CSL::polyhedral CSL::affine_sum
  CSL::qhull_conversion CSL::highs_lp CSL::highs_convex CSL::witness_selector)
target_compile_features(csl_review05_horizon_ladder PRIVATE cxx_std_20)
if(MSVC)
  target_compile_options(csl_review05_horizon_ladder PRIVATE /W4 /WX /permissive-)
else()
  target_compile_options(csl_review05_horizon_ladder PRIVATE -Wall -Wextra -Wpedantic -Werror)
endif()
