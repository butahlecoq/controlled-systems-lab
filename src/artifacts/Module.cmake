# Target and installation ownership for artifacts. Included from the project root.

csl_add_library(csl_artifacts STATIC src/artifacts/run_statistics.cpp src/artifacts/run_statistics_json.cpp src/artifacts/h_relation_attachment.cpp src/execution/observability.cpp src/execution/timing_collector.cpp)

target_link_libraries(csl_artifacts PUBLIC CSL::resolved_problem CSL::execution)

target_include_directories(csl_artifacts SYSTEM PRIVATE ${csl_json_SOURCE_DIR}/single_include)

install(FILES docs/artifacts/schemas/run-statistics-v1.schema.json docs/artifacts/schemas/run-statistics-v2.schema.json docs/artifacts/schemas/run-statistics-v3.schema.json docs/artifacts/schemas/run-statistics-v4.schema.json docs/artifacts/schemas/run-statistics-v5.schema.json DESTINATION ${CMAKE_INSTALL_DATADIR}/csl/schemas)

csl_install_headers(artifacts)
