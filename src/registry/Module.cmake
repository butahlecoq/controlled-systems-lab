# Target and installation ownership for registry. Included from the project root.

csl_add_library(csl_registry STATIC src/registry/registry.cpp)

target_link_libraries(csl_registry PUBLIC CSL::contracts)

csl_add_library(csl_verifiers STATIC
  src/registry/compiled_verifiers.cpp
  src/registry/nominal_linear_exact_verifier.cpp)

target_link_libraries(csl_verifiers PUBLIC CSL::contracts CSL::resolved_core CSL::sets)

target_link_libraries(csl_registry PUBLIC CSL::verifiers)

target_link_libraries(csl_registry PUBLIC CSL::resolved_core)

csl_install_headers(registry)
