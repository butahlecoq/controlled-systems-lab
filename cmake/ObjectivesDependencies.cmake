include(FetchContent)
include(${CMAKE_CURRENT_LIST_DIR}/DependencyArchive.cmake)
# ADR 0002 pin. Consume headers only; do not add Eigen's build/install targets.
set(csl_eigen_archive_sha256 8586084f71f9bde545ee7fa6d00288b264a2b7ac3607b974e54d13e7162c1c72)
csl_dependency_archive_url(csl_eigen_archive_url eigen
  https://gitlab.com/libeigen/eigen/-/archive/3.4.0/eigen-3.4.0.tar.gz ${csl_eigen_archive_sha256})
FetchContent_Declare(csl_objectives_eigen
  URL "${csl_eigen_archive_url}"
  URL_HASH SHA256=${csl_eigen_archive_sha256}
  SOURCE_SUBDIR csl-no-build)
FetchContent_MakeAvailable(csl_objectives_eigen)
target_include_directories(csl_objectives SYSTEM PRIVATE ${csl_objectives_eigen_SOURCE_DIR})
target_compile_definitions(csl_objectives PRIVATE EIGEN_MPL2_ONLY)
install(FILES
  ${csl_objectives_eigen_SOURCE_DIR}/COPYING.README
  ${csl_objectives_eigen_SOURCE_DIR}/COPYING.MPL2
  ${csl_objectives_eigen_SOURCE_DIR}/COPYING.BSD
  ${csl_objectives_eigen_SOURCE_DIR}/COPYING.APACHE
  ${csl_objectives_eigen_SOURCE_DIR}/COPYING.MINPACK
  DESTINATION ${CMAKE_INSTALL_DATADIR}/CSL/notices/Eigen-3.4.0)
