# Target and installation ownership for bounded scenario sweeps.

csl_add_library(csl_experiments STATIC
    src/experiments/batch_runner.cpp
    src/experiments/process_memory_observer.cpp)
target_link_libraries(csl_experiments PUBLIC CSL::application CSL::execution CSL::artifacts)
target_include_directories(csl_experiments SYSTEM PRIVATE ${csl_json_SOURCE_DIR}/single_include)
csl_install_headers(experiments)
