
cmake_minimum_required(VERSION 3.31)
project(HistoryGeometryConsumer LANGUAGES CXX)
find_package(CSL 0.1 CONFIG REQUIRED)
set(src "/home/butahlecoq/.local/share/codex/tmp/learning-control-execution-20261111/943-five-family-consumer")
add_executable(geometry_policy
  ${src}/tools/closed_loop_native_policy.cpp
  ${src}/src/reachability/bounded_h_support.cpp
  ${src}/src/reachability/feedback_geometry.cpp
  ${src}/src/reachability/feedback_coordinator.cpp
  ${src}/src/reachability/nominal_tube.cpp
  ${src}/src/geometry/polyhedral/intersection.cpp
  ${src}/src/reachability/nominal_forward.cpp
  ${src}/src/reachability/finite_plan_zonotope.cpp
  ${src}/src/reachability/finite_plan_box.cpp
  ${src}/src/reachability/finite_plan_ellipsoid.cpp
  ${src}/src/optimization/history_cost.cpp
  ${src}/src/optimization/running_control_cost.cpp
  ${src}/src/optimization/finite_action_nominal.cpp
  ${src}/src/optimization/finite_action_graph.cpp)
target_compile_features(geometry_policy PRIVATE cxx_std_20)
target_include_directories(geometry_policy BEFORE PRIVATE ${src}/include)
target_include_directories(geometry_policy SYSTEM PRIVATE /home/butahlecoq/.local/share/codex/tmp/learning-control-execution-20261111/943-history-bridge-deps/csl_json-src/include)
target_compile_definitions(geometry_policy PRIVATE CSL_NATIVE_HAS_HIGHS=1 CSL_NATIVE_HAS_QHULL=1 CSL_NATIVE_BUILD_TYPE="Release")
target_link_libraries(geometry_policy PRIVATE CSL::finite_action_nominal CSL::polyhedral CSL::affine_sum CSL::phase_one CSL::history_cost CSL::highs_lp CSL::highs_convex CSL::qhull_conversion)

target_link_options(geometry_policy PRIVATE "-Wl,-Map,/home/butahlecoq/.local/share/codex/tmp/learning-control-execution-20261111/history-five-consumer-build/geometry_policy.map")
