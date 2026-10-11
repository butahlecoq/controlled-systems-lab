cmake_minimum_required(VERSION 3.31)
project(CSL VERSION 0.1.0 LANGUAGES CXX)
set(CMAKE_CXX_EXTENSIONS OFF)

include(GNUInstallDirs)
include(CMakePackageConfigHelpers)
include(CTest)
option(CSL_DEPENDENCY_PROBES "Build the isolated pinned native dependency probes" OFF)

add_library(csl_contracts STATIC src/contracts.cpp)
add_library(CSL::contracts ALIAS csl_contracts)
set_target_properties(csl_contracts PROPERTIES EXPORT_NAME contracts CXX_EXTENSIONS OFF)
target_compile_features(csl_contracts PUBLIC cxx_std_20)
target_include_directories(csl_contracts PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:${CMAKE_INSTALL_INCLUDEDIR}>)
if(MSVC)
  target_compile_options(csl_contracts PRIVATE /W4 /WX /permissive-)
else()
  target_compile_options(csl_contracts PRIVATE -Wall -Wextra -Wpedantic -Werror)
endif()

install(TARGETS csl_contracts EXPORT CSLTargets
  ARCHIVE DESTINATION ${CMAKE_INSTALL_LIBDIR})
install(FILES include/csl/contracts.hpp DESTINATION ${CMAKE_INSTALL_INCLUDEDIR}/csl)
install(EXPORT CSLTargets NAMESPACE CSL:: DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/CSL)
configure_package_config_file(cmake/CSLConfig.cmake.in
  ${CMAKE_CURRENT_BINARY_DIR}/CSLConfig.cmake
  INSTALL_DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/CSL)
write_basic_package_version_file(${CMAKE_CURRENT_BINARY_DIR}/CSLConfigVersion.cmake
  VERSION ${PROJECT_VERSION} COMPATIBILITY SameMinorVersion)
install(FILES ${CMAKE_CURRENT_BINARY_DIR}/CSLConfig.cmake
  ${CMAKE_CURRENT_BINARY_DIR}/CSLConfigVersion.cmake
  DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/CSL)

if(BUILD_TESTING)
  include(cmake/Dependencies.cmake)
  add_executable(contract_tests probes/core-01/contract_tests.cpp)
  target_link_libraries(contract_tests PRIVATE CSL::contracts doctest::doctest)
  add_test(NAME contract_tests COMMAND contract_tests)
  add_executable(public_client tests/contract/public_client.cpp)
  target_link_libraries(public_client PRIVATE CSL::contracts)
  set_target_properties(public_client PROPERTIES CXX_EXTENSIONS OFF)
  add_test(NAME public_client COMMAND public_client)
  set_tests_properties(public_client PROPERTIES
    PASS_REGULAR_EXPRESSION "Public contract client: shape guards and literal affine fixture passed")
  find_package(Threads REQUIRED)
  add_executable(caller_example probes/core-01/caller_example.cpp)
  target_link_libraries(caller_example PRIVATE CSL::contracts Threads::Threads)
  add_test(NAME caller_example COMMAND caller_example)
  add_test(NAME installed_public_client COMMAND ${CMAKE_COMMAND}
    "-DCSL_BUILD_DIR=${CMAKE_CURRENT_BINARY_DIR}"
    "-DCSL_SOURCE_DIR=${CMAKE_CURRENT_SOURCE_DIR}"
    "-DCSL_CONFIG=$<CONFIG>"
    "-DCSL_GENERATOR=${CMAKE_GENERATOR}"
    "-DCSL_PLATFORM=${CMAKE_GENERATOR_PLATFORM}"
    "-DCSL_TOOLSET=${CMAKE_GENERATOR_TOOLSET}"
    "-DCSL_CXX_COMPILER=${CMAKE_CXX_COMPILER}"
    "-DCSL_CXX_FLAGS=${CMAKE_CXX_FLAGS}"
    "-DCSL_EXE_LINKER_FLAGS=${CMAKE_EXE_LINKER_FLAGS}"
    -P ${CMAKE_CURRENT_SOURCE_DIR}/cmake/RunInstalledClient.cmake)
  set_tests_properties(installed_public_client PROPERTIES RUN_SERIAL TRUE)
elseif(CSL_DEPENDENCY_PROBES)
  message(FATAL_ERROR "CSL_DEPENDENCY_PROBES requires BUILD_TESTING=ON")
endif()
