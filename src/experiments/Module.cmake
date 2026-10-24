# Target and installation ownership for bounded scenario sweeps.

csl_add_library(csl_experiments STATIC src/experiments/batch_runner.cpp)
target_link_libraries(csl_experiments PUBLIC CSL::application CSL::execution CSL::artifacts)
csl_install_headers(experiments)
