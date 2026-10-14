# Target and installation ownership for execution. Included from the project root.

csl_add_library(csl_execution STATIC src/execution/executor.cpp)

target_link_libraries(csl_execution PUBLIC CSL::registry Threads::Threads)

install(FILES docs/contracts/timing-collector.md DESTINATION ${CMAKE_INSTALL_DATADIR}/CSL/docs/contracts)

csl_install_headers(execution)
