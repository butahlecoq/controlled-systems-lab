# Target and installation ownership for input. Included from the project root.

include(cmake/JsonDependencies.cmake)

csl_add_library(csl_input STATIC src/input/scenario_loader.cpp src/input/scenario_json.cpp
    src/input/scenario_file.cpp src/input/continuous_model.cpp)

target_link_libraries(csl_input PUBLIC CSL::resolved_problem)

target_include_directories(csl_input SYSTEM PRIVATE ${csl_json_SOURCE_DIR}/include)

install(FILES schemas/scenario/v1.schema.json schemas/scenario/README.md DESTINATION ${CMAKE_INSTALL_DATADIR}/CSL/schemas/scenario)

install(FILES schemas/model/continuous-v1.schema.json schemas/model/README.md DESTINATION ${CMAKE_INSTALL_DATADIR}/CSL/schemas/model)

install(FILES tests/fixtures/input/continuous-double-integrator.json DESTINATION ${CMAKE_INSTALL_DATADIR}/CSL/tests/fixtures/input)

install(FILES docs/contracts/scenario-input.md DESTINATION ${CMAKE_INSTALL_DATADIR}/CSL/docs/contracts)

install(FILES tests/fixtures/input/minimal-integrator.json tests/fixtures/input/affine-ltv.json DESTINATION ${CMAKE_INSTALL_DATADIR}/CSL/tests/fixtures/input)

csl_install_headers(input)
