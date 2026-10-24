# Target and installation ownership for reachability. Included from the project root.

csl_add_library(csl_nominal_forward STATIC src/reachability/nominal_forward.cpp)

target_link_libraries(csl_nominal_forward PUBLIC CSL::polyhedral CSL::resolved_problem
  PRIVATE CSL::artifacts)

csl_add_library(csl_fixed_plan_disturbance STATIC src/reachability/fixed_plan_disturbance.cpp)

target_link_libraries(csl_fixed_plan_disturbance PUBLIC CSL::model CSL::sets)

csl_add_library(csl_finite_feedback STATIC src/reachability/finite_feedback.cpp)

csl_add_library(csl_finite_feedback_port STATIC src/reachability/finite_feedback_port.cpp)
target_link_libraries(csl_finite_feedback_port PUBLIC CSL::finite_feedback CSL::registry)

csl_install_headers(reachability)
