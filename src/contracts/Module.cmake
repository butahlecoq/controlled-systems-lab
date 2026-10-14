# Target and installation ownership for contracts. Included from the project root.

csl_add_library(csl_contracts STATIC
  src/contracts/model.cpp
  src/contracts/problem.cpp
  src/contracts/geometry.cpp
  src/contracts/outcomes.cpp
  src/contracts/execution.cpp
  src/contracts/synthesis.cpp)

install(FILES include/csl/contracts.hpp DESTINATION ${CMAKE_INSTALL_INCLUDEDIR}/csl)

csl_install_headers(core)
csl_install_headers(evidence)
