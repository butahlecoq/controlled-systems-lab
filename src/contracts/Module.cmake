# Target and installation ownership for contracts. Included from the project root.

csl_add_library(csl_contracts STATIC src/contracts.cpp)

install(FILES include/csl/contracts.hpp DESTINATION ${CMAKE_INSTALL_INCLUDEDIR}/csl)
