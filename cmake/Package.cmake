install(EXPORT CSLTargets NAMESPACE CSL:: DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/CSL)

configure_package_config_file(cmake/CSLConfig.cmake.in
  ${CMAKE_CURRENT_BINARY_DIR}/CSLConfig.cmake
  INSTALL_DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/CSL)

write_basic_package_version_file(${CMAKE_CURRENT_BINARY_DIR}/CSLConfigVersion.cmake
  VERSION ${PROJECT_VERSION} COMPATIBILITY SameMinorVersion)

install(FILES ${CMAKE_CURRENT_BINARY_DIR}/CSLConfig.cmake
  ${CMAKE_CURRENT_BINARY_DIR}/CSLConfigVersion.cmake
  DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/CSL)
