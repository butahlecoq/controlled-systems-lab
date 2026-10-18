if(TARGET CSL::highs_convex)
  add_executable(highs_convex_tests tests/contract/convex/highs_tests.cpp)
  target_link_libraries(highs_convex_tests PRIVATE CSL::highs_convex doctest::doctest Threads::Threads)
  target_compile_definitions(highs_convex_tests PRIVATE
      "CSL_HIGHS_PATCHED_SOURCE_SHA256=\"${CSL_HIGHS_PATCHED_SOURCE_SHA256}\"")
  add_test(NAME highs_convex_tests COMMAND highs_convex_tests)
  csl_test_target(highs_convex_tests adapters)
endif()

if(TARGET CSL::highs_convex)
  add_executable(convex_backend_contract tests/contract/optimization/convex_backend_contract.cpp)
  target_link_libraries(convex_backend_contract PRIVATE CSL::highs_convex doctest::doctest Threads::Threads)
  add_test(NAME convex_backend_contract COMMAND convex_backend_contract)
  csl_test_target(convex_backend_contract adapters)
endif()

if(TARGET CSL::highs_convex)
  add_executable(convex_public_client tests/installed/convex_client.cpp)
  target_link_libraries(convex_public_client PRIVATE CSL::highs_convex)
  add_test(NAME convex_public_client COMMAND convex_public_client)
  csl_test_target(convex_public_client adapters)
endif()

if(TARGET CSL::highs_lp)
  add_executable(highs_public_client tests/installed/highs_client.cpp)
  target_link_libraries(highs_public_client PRIVATE CSL::highs_lp)
  add_test(NAME highs_public_client COMMAND highs_public_client)
  csl_test_target(highs_public_client adapters)
endif()

if(TARGET CSL::highs_lp)
  add_library(csl_highs_lp_test STATIC src/adapters/lp/highs.cpp)
  target_compile_features(csl_highs_lp_test PUBLIC cxx_std_20)
  target_compile_options(csl_highs_lp_test PRIVATE $<$<CXX_COMPILER_ID:MSVC>:/W4;/WX;/permissive-> $<$<NOT:$<CXX_COMPILER_ID:MSVC>>:-Wall;-Wextra;-Wpedantic;-Werror>)
  target_include_directories(csl_highs_lp_test PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/tests/support
    ${csl_highs_SOURCE_DIR} ${csl_highs_SOURCE_DIR}/highs ${csl_highs_BINARY_DIR})
  target_compile_definitions(csl_highs_lp_test PRIVATE CSL_HIGHSLP_TESTING
    "CSL_HIGHS_PATCHED_SOURCE_SHA256=\"${CSL_HIGHS_PATCHED_SOURCE_SHA256}\"")
  target_link_libraries(csl_highs_lp_test PUBLIC CSL::optimization CSL::registry PRIVATE highs)
  add_executable(highs_lp_tests tests/contract/lp/highs_tests.cpp)
  target_link_libraries(highs_lp_tests PRIVATE csl_highs_lp_test doctest::doctest Threads::Threads)
  target_include_directories(highs_lp_tests PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/tests/support)
  target_compile_definitions(highs_lp_tests PRIVATE
      "CSL_HIGHS_PATCHED_SOURCE_SHA256=\"${CSL_HIGHS_PATCHED_SOURCE_SHA256}\"")
  add_test(NAME highs_lp_tests COMMAND highs_lp_tests)
  csl_test_target(highs_lp_tests adapters)
endif()

if(TARGET CSL::highs_lp)
  add_executable(lp_backend_contract tests/contract/optimization/lp_backend_contract.cpp)
  target_link_libraries(lp_backend_contract PRIVATE CSL::highs_lp doctest::doctest)
  add_test(NAME lp_backend_contract COMMAND lp_backend_contract)
  add_test(NAME lp_analytic_catalogue_consistency COMMAND ${CMAKE_COMMAND}
      "-DTEST05_EXE=$<TARGET_FILE:lp_backend_contract>"
      "-DTEST05_CATALOGUE=${CMAKE_CURRENT_SOURCE_DIR}/tests/fixtures/optimization/analytic_lp_cases.json"
      -P "${CMAKE_CURRENT_SOURCE_DIR}/tests/contract/optimization/check_lp_catalogue.cmake")
  set_tests_properties(lp_backend_contract PROPERTIES TIMEOUT 60)
  set_tests_properties(lp_analytic_catalogue_consistency PROPERTIES TIMEOUT 20)
  set_tests_properties(lp_analytic_catalogue_consistency PROPERTIES LABELS adapters)
  csl_test_target(lp_backend_contract adapters)
endif()
