csl_add_library(csl_controllers STATIC
  src/controllers/observed_replay.cpp
  src/controllers/finite_policy.cpp
  src/controllers/continuous_policy.cpp)
target_link_libraries(csl_controllers PUBLIC CSL::model CSL::problem)
csl_install_headers(controllers)
install(FILES docs/contracts/information-patterns.md DESTINATION ${CMAKE_INSTALL_DATADIR}/CSL/docs/contracts)
