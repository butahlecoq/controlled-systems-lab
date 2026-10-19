# Target and installation ownership for model. Included from the project root.

csl_add_library(csl_model STATIC src/model/linear_system.cpp
    src/model/discretization/adapter.cpp src/model/discretization/rk4.cpp)

target_link_libraries(csl_model PUBLIC CSL::numeric)

csl_install_headers(model)
