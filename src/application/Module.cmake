# Target and installation ownership for application composition.

csl_add_library(csl_application STATIC src/application/comparison.cpp)

target_link_libraries(csl_application PUBLIC
  CSL::resolved_problem CSL::registry CSL::verification CSL::artifacts)
target_include_directories(csl_application SYSTEM PRIVATE ${csl_json_SOURCE_DIR}/single_include)

csl_install_headers(application)
