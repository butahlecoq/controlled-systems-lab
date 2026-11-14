include(FetchContent)
include(${CMAKE_CURRENT_LIST_DIR}/DependencyArchive.cmake)
# Test-only dependency. Excluded from product installation.
set(DOCTEST_WITH_TESTS OFF CACHE BOOL "Disable doctest's own tests" FORCE)
set(csl_doctest_archive_sha256 632ed2c05a7f53fa961381497bf8069093f0d6628c5f26286161fbd32a560186)
csl_dependency_archive_url(csl_doctest_archive_url doctest
  https://codeload.github.com/doctest/doctest/tar.gz/refs/tags/v2.4.11 ${csl_doctest_archive_sha256})
FetchContent_Declare(doctest
  URL "${csl_doctest_archive_url}"
  URL_HASH SHA256=${csl_doctest_archive_sha256}
  SYSTEM
  EXCLUDE_FROM_ALL)
FetchContent_MakeAvailable(doctest)

# Preinclude the one obsolete detection header with its diagnostic contained.
# The unchanged test dependency and all first-party code follow after the pop.
set(csl_doctest_adapter [=[
#if defined(__clang__)
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-W#warnings"
#include <ciso646>
#pragma clang diagnostic pop
#endif
#include "@doctest_SOURCE_DIR@/doctest/doctest.h"
]=])
string(CONFIGURE "${csl_doctest_adapter}" csl_doctest_adapter @ONLY)
file(GENERATE OUTPUT "${CMAKE_BINARY_DIR}/test-framework/doctest/doctest.h"
  CONTENT "${csl_doctest_adapter}")
target_include_directories(doctest BEFORE INTERFACE "$<BUILD_INTERFACE:${CMAKE_BINARY_DIR}/test-framework>")
get_target_property(csl_doctest_system doctest SYSTEM)
if(NOT csl_doctest_system)
  message(FATAL_ERROR "The test dependency must retain its SYSTEM header boundary")
endif()
message(STATUS "Doctest test-only header boundary: SYSTEM=${csl_doctest_system}")

if(CSL_DEPENDENCY_PROBES)
  # Keep native dependencies and their install rules in an isolated project.
  # ADR 0002 archive pins remain authoritative in probes/core-01/CMakeLists.txt.
  include(ExternalProject)
  ExternalProject_Add(core01_native_probes
    SOURCE_DIR ${PROJECT_SOURCE_DIR}/probes/core-01
    BINARY_DIR ${PROJECT_BINARY_DIR}/native-probes
    CMAKE_ARGS
      -DCMAKE_BUILD_TYPE=${CMAKE_BUILD_TYPE}
      -DCMAKE_C_COMPILER=${CMAKE_C_COMPILER}
      -DCMAKE_CXX_COMPILER=${CMAKE_CXX_COMPILER}
      "-DCMAKE_C_COMPILER_LAUNCHER:STRING=${CMAKE_C_COMPILER_LAUNCHER}"
      "-DCMAKE_CXX_COMPILER_LAUNCHER:STRING=${CMAKE_CXX_COMPILER_LAUNCHER}"
      -DCSL_DEPENDENCY_ARCHIVE_CACHE:PATH=${CSL_DEPENDENCY_ARCHIVE_CACHE}
      -DCSL_DEPENDENCY_PROBES=ON
    BUILD_COMMAND ${CMAKE_COMMAND} --build <BINARY_DIR> --config $<CONFIG> --parallel 4
    BUILD_ALWAYS TRUE
    INSTALL_COMMAND "")
  add_test(NAME native_dependency_probes COMMAND ${CMAKE_CTEST_COMMAND}
    --test-dir ${PROJECT_BINARY_DIR}/native-probes -C $<CONFIG>
    --output-on-failure --no-tests=error -R "^dependency_probes$")
endif()
