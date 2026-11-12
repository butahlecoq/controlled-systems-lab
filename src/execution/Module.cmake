# Target and installation ownership for execution. Included from the project root.

csl_add_library(csl_execution STATIC src/execution/executor.cpp)

target_link_libraries(csl_execution PUBLIC CSL::registry Threads::Threads)

csl_install_headers(execution)
