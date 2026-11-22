
csl_add_library(csl_numeric STATIC src/numeric/data.cpp)

target_link_libraries(csl_numeric PUBLIC CSL::contracts)

csl_install_headers(numeric)
