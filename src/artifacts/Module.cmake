# Target and installation ownership for artifacts. Included from the project root.

csl_add_library(csl_artifacts STATIC src/artifacts/run_statistics.cpp src/artifacts/run_statistics_json.cpp src/artifacts/comparison_manifest.cpp src/artifacts/scenario_sweep.cpp src/artifacts/h_relation_attachment.cpp src/artifacts/bounded_hull_check.cpp src/execution/observability.cpp src/execution/timing_collector.cpp src/execution/operation_observability.cpp)

target_link_libraries(csl_artifacts PUBLIC CSL::resolved_problem CSL::execution CSL::bounded_hull_checker)

target_include_directories(csl_artifacts SYSTEM PRIVATE ${csl_json_SOURCE_DIR}/single_include)

install(FILES docs/artifacts/schemas/run-statistics-v1.schema.json docs/artifacts/schemas/run-statistics-v2.schema.json docs/artifacts/schemas/run-statistics-v3.schema.json docs/artifacts/schemas/run-statistics-v4.schema.json docs/artifacts/schemas/run-statistics-v5.schema.json docs/artifacts/schemas/run-statistics-v6.schema.json docs/artifacts/schemas/comparison-spec-v1.schema.json docs/artifacts/schemas/comparison-v1.schema.json docs/artifacts/schemas/scenario-sweep-v1.schema.json docs/artifacts/schemas/scenario-sweep-v2.schema.json docs/artifacts/schemas/bounded-hull-check-v1.schema.json docs/artifacts/schemas/trajectory-verification-reports-v1.schema.json DESTINATION ${CMAKE_INSTALL_DATADIR}/csl/schemas)

csl_install_headers(artifacts)
