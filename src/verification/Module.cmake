# Target and installation ownership for verification. Included from the project root.

csl_add_library(csl_verification STATIC src/verification/trajectory.cpp)

target_link_libraries(csl_verification PUBLIC CSL::resolved_problem CSL::optimization CSL::registry)

csl_install_headers(verification)
