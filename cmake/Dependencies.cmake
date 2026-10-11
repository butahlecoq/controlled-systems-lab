include(FetchContent)
# Test-only dependency. Excluded from product installation.
set(DOCTEST_WITH_TESTS OFF CACHE BOOL "Disable doctest's own tests" FORCE)
FetchContent_Declare(doctest
  URL https://codeload.github.com/doctest/doctest/tar.gz/refs/tags/v2.4.11
  URL_HASH SHA256=632ed2c05a7f53fa961381497bf8069093f0d6628c5f26286161fbd32a560186
  EXCLUDE_FROM_ALL)
FetchContent_MakeAvailable(doctest)

if(CSL_DEPENDENCY_PROBES)
  # Keep native dependencies and their install rules in an isolated project.
  # ADR 0002 archive pins remain authoritative in probes/core-01/CMakeLists.txt.
  include(ExternalProject)
  ExternalProject_Add(core01_native_probes
    SOURCE_DIR ${PROJECT_SOURCE_DIR}/probes/core-01
    BINARY_DIR ${PROJECT_BINARY_DIR}/native-probes
    CMAKE_ARGS
      -DCMAKE_BUILD_TYPE=${CMAKE_BUILD_TYPE}
      -DCMAKE_CXX_COMPILER=${CMAKE_CXX_COMPILER}
      -DCSL_DEPENDENCY_PROBES=ON
    BUILD_COMMAND ${CMAKE_COMMAND} --build <BINARY_DIR> --config $<CONFIG> --parallel 4
    BUILD_ALWAYS TRUE
    INSTALL_COMMAND "")
  add_test(NAME native_dependency_probes COMMAND ${CMAKE_CTEST_COMMAND}
    --test-dir ${PROJECT_BINARY_DIR}/native-probes -C $<CONFIG>
    --output-on-failure --no-tests=error -R "^dependency_probes$")
endif()
