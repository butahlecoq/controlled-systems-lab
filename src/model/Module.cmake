# Target and installation ownership for model. Included from the project root.

csl_add_library(csl_model STATIC src/model/linear_system.cpp src/model/hybrid_system.cpp)

target_link_libraries(csl_model PUBLIC CSL::numeric CSL::sets CSL::objectives)

csl_install_headers(model)
