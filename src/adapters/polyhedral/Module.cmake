# Target and installation ownership for adapters/polyhedral. Included from the project root.

if(CSL_ENABLE_QHULL)
  include(cmake/QhullDependencies.cmake)

  csl_add_library(csl_qhull_conversion STATIC
    src/adapters/polyhedral/qhull.cpp
    src/geometry/conversion/affine_coordinates.cpp)

  target_link_libraries(csl_qhull_conversion PUBLIC CSL::sets CSL::optimization CSL::registry PRIVATE CSL::qhull_r CSL::highs_lp)

  target_include_directories(csl_qhull_conversion SYSTEM PRIVATE ${csl_qhull_SOURCE_DIR}/src/libqhull_r ${csl_objectives_eigen_SOURCE_DIR})

  target_compile_definitions(csl_qhull_conversion PRIVATE EIGEN_MPL2_ONLY EIGEN_DONT_PARALLELIZE)

endif()

csl_install_headers(adapters/polyhedral)
