# Target and installation ownership for adapters/highs. Included from the project root.

if(CSL_ENABLE_HIGHS)
  csl_add_library(csl_highs_lp STATIC src/adapters/lp/highs.cpp)

  target_link_libraries(csl_highs_lp PUBLIC CSL::optimization CSL::registry)

  include(cmake/HighsDependencies.cmake)

  csl_add_library(csl_highs_convex STATIC src/adapters/convex/highs.cpp)

  target_link_libraries(csl_highs_convex PUBLIC CSL::convex CSL::registry PRIVATE highs)

  target_compile_definitions(csl_highs_convex PRIVATE
    "CSL_HIGHS_PATCHED_SOURCE_SHA256=\"${CSL_HIGHS_PATCHED_SOURCE_SHA256}\"")

endif()

csl_install_headers(adapters/lp)

csl_install_headers(adapters/convex)
