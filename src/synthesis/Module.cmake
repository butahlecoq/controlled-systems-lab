# Target and installation ownership for synthesis. Included from the project root.

csl_add_library(csl_terminal_minimizers STATIC src/synthesis/terminal_minimizers.cpp)

target_link_libraries(csl_terminal_minimizers PUBLIC CSL::sets CSL::registry CSL::convex CSL::problem)

csl_add_library(csl_control_recovery STATIC src/synthesis/control_recovery.cpp)

target_link_libraries(csl_control_recovery PUBLIC CSL::resolved_problem CSL::sets)

csl_add_library(csl_strategy_a STATIC src/synthesis/strategy_a/strategy.cpp)

target_link_libraries(csl_strategy_a PUBLIC CSL::nominal_forward CSL::terminal_minimizers CSL::control_recovery)

csl_add_library(csl_strategy_ts01 STATIC src/synthesis/strategy_ts01/analytic_profile.cpp)

target_link_libraries(csl_strategy_ts01 PUBLIC CSL::resolved_problem CSL::sets CSL::registry)

install(FILES docs/contracts/ts01-exact-analytic-profile.md DESTINATION ${CMAKE_INSTALL_DATADIR}/CSL/docs/contracts)

csl_add_library(csl_strategy_b STATIC src/synthesis/strategy_b/direct_joint.cpp)

target_link_libraries(csl_strategy_b PUBLIC CSL::resolved_problem CSL::sets CSL::registry CSL::convex CSL::verification CSL::strategy_ts01)

install(FILES docs/contracts/control-recovery.md DESTINATION ${CMAKE_INSTALL_DATADIR}/CSL/docs/contracts)

csl_add_library(csl_witness_selector STATIC src/synthesis/witness_selector.cpp)

target_link_libraries(csl_witness_selector PUBLIC CSL::registry CSL::optimization CSL::strategy_ts01)

csl_install_headers(synthesis)
