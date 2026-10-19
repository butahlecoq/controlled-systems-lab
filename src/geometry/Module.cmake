# Target and installation ownership for geometry. Included from the project root.

csl_add_library(csl_hull STATIC
  src/geometry/hull_reducer.cpp
  src/geometry/basis_reuse_reducer.cpp
  src/geometry/hull/ordered_reducer.cpp
  src/geometry/hull/grouped_reducer.cpp
  src/geometry/hull/recursive_reducer.cpp)

target_link_libraries(csl_hull PUBLIC CSL::optimization CSL::registry PRIVATE CSL::phase_one Threads::Threads)

csl_add_library(csl_quickhull_2d STATIC src/geometry/hull/quickhull_2d.cpp)

csl_add_library(csl_bounded_hull_checker STATIC src/geometry/bounded_hull_checker.cpp)
target_link_libraries(csl_bounded_hull_checker PUBLIC CSL::resolved_problem PRIVATE CSL::quickhull_2d)

csl_add_library(csl_polyhedral STATIC
  src/geometry/polyhedral/intersection.cpp
  src/geometry/polyhedral/halfspace_reducer.cpp
  src/geometry/polyhedral/projection.cpp
  src/geometry/polyhedral/support.cpp
  src/reachability/nominal_predecessor.cpp)

target_link_libraries(csl_polyhedral PUBLIC CSL::sets CSL::optimization CSL::registry)

csl_add_library(csl_lazy_geometry STATIC
  src/geometry/lazy/expression.cpp
  src/geometry/lazy/support.cpp
  src/geometry/lazy/materialize.cpp)
target_link_libraries(csl_lazy_geometry PUBLIC CSL::sets CSL::registry)

csl_add_library(csl_affine_sum STATIC src/geometry/affine_sum.cpp)

target_link_libraries(csl_affine_sum PUBLIC CSL::sets CSL::hull CSL::registry)

csl_add_library(csl_geometry_generators STATIC src/geometry/generators/generator_sets.cpp)
target_link_libraries(csl_geometry_generators PUBLIC CSL::sets)

csl_add_library(csl_generator_adapter STATIC src/geometry/generators/adapter.cpp)
target_link_libraries(csl_generator_adapter PUBLIC CSL::geometry_generators CSL::registry)

csl_add_library(csl_approximation STATIC src/geometry/approximation/policy.cpp src/geometry/approximation/reachable_plan.cpp src/geometry/approximation/box_parallelotope.cpp src/geometry/approximation/zonotope.cpp)
target_link_libraries(csl_approximation PUBLIC CSL::sets CSL::registry CSL::verification PRIVATE CSL::geometry_generators)

install(FILES docs/contracts/projection-and-predecessor.md DESTINATION ${CMAKE_INSTALL_DATADIR}/doc/CSL/contracts)

install(FILES docs/contracts/polyhedral-intersection.md DESTINATION ${CMAKE_INSTALL_DATADIR}/doc/CSL/contracts)
install(FILES docs/contracts/polyhedral-support.md DESTINATION ${CMAKE_INSTALL_DATADIR}/doc/CSL/contracts)

install(FILES docs/contracts/hull-reduction.md DESTINATION ${CMAKE_INSTALL_DATADIR}/doc/CSL/contracts)

install(FILES docs/contracts/quickhull-2d.md DESTINATION ${CMAKE_INSTALL_DATADIR}/doc/CSL/contracts)
install(FILES docs/contracts/bounded-hull-checker.md DESTINATION ${CMAKE_INSTALL_DATADIR}/doc/CSL/contracts)

install(FILES docs/contracts/affine-sum-operations.md DESTINATION ${CMAKE_INSTALL_DATADIR}/doc/CSL/contracts)
install(FILES docs/contracts/approximation.md DESTINATION ${CMAKE_INSTALL_DATADIR}/doc/CSL/contracts)
install(FILES docs/contracts/generator-sets.md DESTINATION ${CMAKE_INSTALL_DATADIR}/doc/CSL/contracts)

csl_install_headers(geometry)
