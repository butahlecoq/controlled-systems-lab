csl_add_library(csl_controllers STATIC
  src/controllers/observed_replay.cpp
  src/controllers/finite_policy.cpp
  src/controllers/continuous_policy.cpp
  src/controllers/discrete_mpc.cpp)
target_link_libraries(csl_controllers PUBLIC CSL::model CSL::model_catalogue CSL::problem
  CSL::optimization CSL::sets CSL::nominal_quadratic_history)
csl_install_headers(controllers)
