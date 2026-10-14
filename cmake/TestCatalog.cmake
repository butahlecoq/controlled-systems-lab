# Test-only verifier authorities. Never exported or installed.

add_library(csl_verifiers_test STATIC src/registry/compiled_verifiers.cpp)

target_compile_definitions(csl_verifiers_test PRIVATE CSL_TEST_VERIFIER_CATALOG)

target_link_libraries(csl_verifiers_test PUBLIC CSL::contracts CSL::resolved_core CSL::sets)

add_library(csl_registry_test STATIC src/registry/registry.cpp)

target_link_libraries(csl_registry_test PUBLIC CSL::contracts CSL::resolved_core csl_verifiers_test)

add_library(csl_resolved_problem_test STATIC src/problem/validator.cpp)

target_link_libraries(csl_resolved_problem_test PUBLIC CSL::resolved_core csl_registry_test)

foreach(target csl_verifiers_test csl_registry_test csl_resolved_problem_test)
  csl_target_policy(${target})
  target_include_directories(${target} PRIVATE ${PROJECT_SOURCE_DIR}/src/registry)
endforeach()
