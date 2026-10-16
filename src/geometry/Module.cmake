# Target and installation ownership for geometry. Included from the project root.

csl_add_library(csl_hull STATIC src/geometry/hull_reducer.cpp src/geometry/basis_reuse_reducer.cpp)

target_link_libraries(csl_hull PUBLIC CSL::optimization CSL::registry PRIVATE CSL::phase_one)

csl_add_library(csl_polyhedral STATIC
  src/geometry/polyhedral/intersection.cpp
  src/geometry/polyhedral/halfspace_reducer.cpp
  src/geometry/polyhedral/projection.cpp
  src/reachability/nominal_predecessor.cpp)

target_link_libraries(csl_polyhedral PUBLIC CSL::sets CSL::optimization CSL::registry)

csl_add_library(csl_affine_sum STATIC src/geometry/affine_sum.cpp)

target_link_libraries(csl_affine_sum PUBLIC CSL::sets CSL::hull CSL::registry)

csl_add_library(csl_approximation STATIC src/geometry/approximation/policy.cpp)
target_link_libraries(csl_approximation PUBLIC CSL::sets CSL::registry)

install(FILES docs/contracts/projection-and-predecessor.md DESTINATION ${CMAKE_INSTALL_DATADIR}/doc/CSL/contracts)

install(FILES docs/contracts/polyhedral-intersection.md DESTINATION ${CMAKE_INSTALL_DATADIR}/doc/CSL/contracts)

install(FILES docs/contracts/hull-reduction.md DESTINATION ${CMAKE_INSTALL_DATADIR}/doc/CSL/contracts)

install(FILES docs/contracts/affine-sum-operations.md DESTINATION ${CMAKE_INSTALL_DATADIR}/doc/CSL/contracts)
install(FILES docs/contracts/approximation.md DESTINATION ${CMAKE_INSTALL_DATADIR}/doc/CSL/contracts)

csl_install_headers(geometry)
