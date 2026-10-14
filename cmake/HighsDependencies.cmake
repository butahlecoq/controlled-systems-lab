include(FetchContent)

function(csl_add_private_highs)
  # ADR 0002 pin; keep upstream options scoped away from CSL's tests/toolchain.
  FetchContent_Declare(csl_highs
    URL https://codeload.github.com/ERGO-Code/HiGHS/tar.gz/refs/tags/v1.11.0
    URL_HASH SHA256=2b44b074cf41439325ce4d0bbdac2d51379f56faf17ba15320a410d3c1f07275
    SOURCE_SUBDIR csl-no-build)
  FetchContent_MakeAvailable(csl_highs)
  # Keep the upstream archive/hash pinned and apply this narrowly scoped
  # downstream initialization fix to the fetched source before compiling it.
  execute_process(
    COMMAND "${CMAKE_COMMAND}"
      "-DSOURCE_FILE=${csl_highs_SOURCE_DIR}/highs/util/HVectorBase.h"
      "-DPATCH_FILE=${PROJECT_SOURCE_DIR}/patches/highs-v1.11.0-hvectorbase-initialization.patch"
      -P "${PROJECT_SOURCE_DIR}/cmake/ApplyPinnedHighsPatch.cmake"
    RESULT_VARIABLE patch_result
    OUTPUT_VARIABLE patch_output
    ERROR_VARIABLE patch_error)
  if(NOT patch_result EQUAL 0)
    message(FATAL_ERROR "Failed to apply pinned HiGHS downstream patch: ${patch_output}${patch_error}")
  endif()
  set(FAST_BUILD ON)
  set(BUILD_SHARED_LIBS OFF)
  set(BUILD_CXX ON)
  set(BUILD_CXX_EXE OFF)
  set(BUILD_TESTING OFF)
  set(BUILD_EXAMPLES OFF)
  set(FORTRAN OFF)
  set(CSHARP OFF)
  set(PYTHON_BUILD_SETUP OFF)
  set(ZLIB OFF)
  set(CUPDLP_GPU OFF)
  set(CUPDLP_FIND_CUDA OFF)
  set(HIGHSINT64 OFF)
  set(HIGHS_NO_DEFAULT_THREADS ON)
  add_subdirectory(${csl_highs_SOURCE_DIR} ${csl_highs_BINARY_DIR} EXCLUDE_FROM_ALL SYSTEM)
  # Static consumers need the archive at final link, not native headers.
  set_target_properties(highs PROPERTIES EXPORT_NAME private_highs_native
    INTERFACE_INCLUDE_DIRECTORIES
      "$<BUILD_INTERFACE:${csl_highs_SOURCE_DIR}>;$<BUILD_INTERFACE:${csl_highs_SOURCE_DIR}/highs>;$<BUILD_INTERFACE:${csl_highs_BINARY_DIR}>")
  target_link_libraries(csl_highs_lp PRIVATE highs)
  target_include_directories(csl_highs_lp SYSTEM PRIVATE
    ${csl_highs_SOURCE_DIR} ${csl_highs_SOURCE_DIR}/highs ${csl_highs_BINARY_DIR})
  install(TARGETS highs EXPORT CSLTargets ARCHIVE DESTINATION ${CMAKE_INSTALL_LIBDIR})
  install(FILES ${csl_highs_SOURCE_DIR}/LICENSE.txt
    DESTINATION ${CMAKE_INSTALL_DATADIR}/CSL/notices/HiGHS-1.11.0)
  install(FILES ${csl_highs_SOURCE_DIR}/extern/filereaderlp/LICENSE
    DESTINATION ${CMAKE_INSTALL_DATADIR}/CSL/notices/HiGHS-1.11.0/extern/filereaderlp)
  install(FILES ${csl_highs_SOURCE_DIR}/extern/pdqsort/license.txt
    DESTINATION ${CMAKE_INSTALL_DATADIR}/CSL/notices/HiGHS-1.11.0/extern/pdqsort)
endfunction()

csl_add_private_highs()
