# Private benchmark build hook: use with CMAKE_PROJECT_CSL_INCLUDE when
# configuring the repository itself, so tests and the probe reuse one build.
function(_csl_review05_add_phase_probe)
  add_executable(csl_review05_family_query
    "${PROJECT_SOURCE_DIR}/benchmarks/reporting/review05/family_query_ladder.cpp")
  target_link_libraries(csl_review05_family_query PRIVATE
    CSL::input CSL::application CSL::strategy_a CSL::strategy_b CSL::polyhedral CSL::affine_sum
    CSL::qhull_conversion CSL::highs_lp CSL::highs_convex CSL::witness_selector)
  target_compile_features(csl_review05_family_query PRIVATE cxx_std_20)
  if(MSVC)
    target_compile_options(csl_review05_family_query PRIVATE /W4 /WX /permissive-)
  else()
    target_compile_options(csl_review05_family_query PRIVATE -Wall -Wextra -Wpedantic -Werror)
  endif()
endfunction()
cmake_language(DEFER CALL _csl_review05_add_phase_probe)
