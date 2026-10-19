csl_add_library(csl_simulation STATIC src/simulation/nonlinear_replay.cpp)
target_link_libraries(csl_simulation PUBLIC CSL::contracts)
csl_install_headers(simulation)
install(FILES docs/contracts/nonlinear-replay.md DESTINATION ${CMAKE_INSTALL_DATADIR}/CSL/docs/contracts)
