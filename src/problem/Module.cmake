# Target and installation ownership for problem. Included from the project root.

csl_add_library(csl_problem STATIC src/problem/domains.cpp src/problem/constraints.cpp src/problem/initial_information.cpp)

target_link_libraries(csl_problem PUBLIC CSL::model CSL::sets)

csl_add_library(csl_resolved_core STATIC src/problem/identity.cpp src/problem/resolved.cpp)

target_link_libraries(csl_resolved_core PUBLIC CSL::problem CSL::objectives)

csl_add_library(csl_resolved_problem STATIC src/problem/validator.cpp src/problem/temporal_lifts.cpp)

target_link_libraries(csl_resolved_problem PUBLIC CSL::resolved_core CSL::registry)

csl_install_headers(problem)
