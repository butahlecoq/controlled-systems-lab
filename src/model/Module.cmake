# Target and installation ownership for model. Included from the project root.

csl_add_library(csl_model STATIC src/model/linear_system.cpp
    src/model/discretization/adapter.cpp src/model/discretization/rk4.cpp
    src/model/hybrid_system.cpp src/model/spatial_flight.cpp)

target_link_libraries(csl_model PUBLIC CSL::numeric CSL::sets CSL::objectives)

csl_add_library(csl_model_catalogue STATIC src/model/catalogue.cpp src/model/flexible_pitch.cpp
    src/model/spatial_flight_catalogue.cpp)
target_link_libraries(csl_model_catalogue PUBLIC CSL::model CSL::geometry_generators)

csl_install_headers(model)
