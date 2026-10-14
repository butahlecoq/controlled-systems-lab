# Target and installation ownership for reachability. Included from the project root.

csl_add_library(csl_nominal_forward STATIC src/reachability/nominal_forward.cpp)

target_link_libraries(csl_nominal_forward PUBLIC CSL::polyhedral CSL::resolved_problem)

csl_install_headers(reachability)
