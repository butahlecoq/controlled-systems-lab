# Target and installation ownership for sets. Included from the project root.

csl_add_library(csl_sets STATIC src/sets/data.cpp)

target_link_libraries(csl_sets PUBLIC CSL::numeric)

csl_install_headers(sets)
