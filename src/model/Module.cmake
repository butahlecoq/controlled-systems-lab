# Target and installation ownership for model. Included from the project root.

csl_add_library(csl_model STATIC src/model/linear_system.cpp
    src/model/discretization/adapter.cpp src/model/discretization/rk4.cpp
    src/model/hybrid_system.cpp)

target_link_libraries(csl_model PUBLIC CSL::numeric CSL::sets CSL::objectives)

csl_install_headers(model)

install(FILES docs/contracts/time-domains.md DESTINATION ${CMAKE_INSTALL_DATADIR}/CSL/docs/contracts)
