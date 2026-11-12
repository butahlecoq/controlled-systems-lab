csl_add_library(csl_simulation STATIC src/simulation/nonlinear_replay.cpp)
target_link_libraries(csl_simulation PUBLIC CSL::contracts)
csl_install_headers(simulation)
