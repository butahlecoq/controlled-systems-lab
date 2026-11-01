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

csl_add_library(csl_feasible_directions STATIC src/optimization/feasible_directions/smooth_convex.cpp)

target_link_libraries(csl_feasible_directions PUBLIC CSL::zoutendijk_projection)

csl_add_library(csl_worst_case_vertex STATIC src/optimization/worst_case_vertex.cpp)

target_link_libraries(csl_worst_case_vertex PUBLIC CSL::objectives CSL::sets)

csl_add_library(csl_worst_case_interval STATIC src/optimization/worst_case_interval.cpp)

target_link_libraries(csl_worst_case_interval PUBLIC CSL::objectives CSL::sets)

csl_add_library(csl_finite_action_minimax STATIC src/optimization/finite_action_minimax.cpp)

target_link_libraries(csl_finite_action_minimax PUBLIC CSL::fixed_plan_disturbance CSL::worst_case_vertex CSL::artifacts)

csl_add_library(csl_finite_action_replay STATIC src/optimization/finite_action_replay.cpp)
target_link_libraries(csl_finite_action_replay PUBLIC CSL::fixed_plan_disturbance CSL::worst_case_vertex)

csl_add_library(csl_finite_action_box_minimax STATIC src/optimization/finite_action_box_minimax.cpp)
target_link_libraries(csl_finite_action_box_minimax PUBLIC CSL::finite_action_minimax CSL::finite_plan_box CSL::worst_case_vertex CSL::finite_action_replay)

csl_add_library(csl_finite_action_zonotope_minimax STATIC src/optimization/finite_action_zonotope_minimax.cpp)
target_link_libraries(csl_finite_action_zonotope_minimax PUBLIC CSL::finite_action_minimax CSL::finite_plan_zonotope CSL::finite_action_replay)

csl_add_library(csl_finite_action_parallelotope_minimax STATIC src/optimization/finite_action_parallelotope_minimax.cpp)
target_link_libraries(csl_finite_action_parallelotope_minimax PUBLIC CSL::finite_action_minimax CSL::finite_plan_parallelotope CSL::finite_action_replay)
csl_add_library(csl_finite_action_ellipsoid_minimax STATIC src/optimization/finite_action_ellipsoid_minimax.cpp)
target_link_libraries(csl_finite_action_ellipsoid_minimax PUBLIC CSL::finite_action_minimax CSL::finite_plan_ellipsoid CSL::finite_action_replay)

csl_add_library(csl_finite_causal_minimax STATIC src/optimization/finite_causal_minimax.cpp)

csl_add_library(csl_validated_finite_action_minimax STATIC
  src/optimization/validated_finite_action_minimax.cpp)

target_link_libraries(csl_validated_finite_action_minimax PUBLIC CSL::objectives CSL::sets CSL::model)

csl_add_library(csl_validated_finite_action_minimax_port STATIC
  src/optimization/validated_finite_action_minimax_port.cpp)

target_link_libraries(csl_validated_finite_action_minimax_port
  PUBLIC CSL::validated_finite_action_minimax CSL::registry)

csl_add_library(csl_finite_action_minimax_port STATIC src/optimization/finite_action_minimax_port.cpp)

target_link_libraries(csl_finite_action_minimax_port PUBLIC CSL::finite_action_minimax CSL::registry)

csl_install_headers(optimization)

install(FILES docs/contracts/certificates.md
  DESTINATION ${CMAKE_INSTALL_DATADIR}/CSL/docs/contracts)
install(FILES docs/contracts/finite-causal-minimax.md
  DESTINATION ${CMAKE_INSTALL_DATADIR}/CSL/docs/contracts)
