# Target and installation ownership for optimization. Included from the project root.

csl_add_library(csl_objectives STATIC src/optimization/objective_reformulation.cpp)

target_link_libraries(csl_objectives PUBLIC CSL::numeric)

include(cmake/ObjectivesDependencies.cmake)

csl_add_library(csl_optimization STATIC src/optimization/linear_program.cpp src/optimization/lp_backend.cpp
  src/optimization/linear_infeasibility_certificate.cpp)

target_link_libraries(csl_optimization PUBLIC CSL::numeric)

csl_add_library(csl_phase_one STATIC src/optimization/phase_one/program.cpp src/optimization/phase_one/simplex.cpp)

target_link_libraries(csl_phase_one PUBLIC CSL::optimization CSL::registry)

target_include_directories(csl_phase_one SYSTEM PRIVATE ${csl_objectives_eigen_SOURCE_DIR})

target_compile_definitions(csl_phase_one PRIVATE EIGEN_MPL2_ONLY EIGEN_DONT_PARALLELIZE)

csl_add_library(csl_convex STATIC src/optimization/convex_backend.cpp)

target_link_libraries(csl_convex PUBLIC CSL::objectives CSL::optimization)

csl_add_library(csl_zoutendijk_projection STATIC src/optimization/zoutendijk/projection.cpp)

target_link_libraries(csl_zoutendijk_projection PUBLIC CSL::optimization)

csl_add_library(csl_worst_case_vertex STATIC src/optimization/worst_case_vertex.cpp)

target_link_libraries(csl_worst_case_vertex PUBLIC CSL::objectives CSL::sets)

csl_add_library(csl_finite_action_minimax STATIC src/optimization/finite_action_minimax.cpp)

target_link_libraries(csl_finite_action_minimax PUBLIC CSL::fixed_plan_disturbance CSL::worst_case_vertex)

csl_add_library(csl_finite_action_minimax_port STATIC src/optimization/finite_action_minimax_port.cpp)

target_link_libraries(csl_finite_action_minimax_port PUBLIC CSL::finite_action_minimax CSL::registry)

csl_install_headers(optimization)
