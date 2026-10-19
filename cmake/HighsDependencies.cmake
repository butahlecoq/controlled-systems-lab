include(FetchContent)
include(${CMAKE_CURRENT_LIST_DIR}/DependencyArchive.cmake)

function(csl_add_private_highs)
  # ADR 0002 pin; keep upstream options scoped away from CSL's tests/toolchain.
  set(csl_highs_archive_sha256 2b44b074cf41439325ce4d0bbdac2d51379f56faf17ba15320a410d3c1f07275)
  csl_dependency_archive_url(csl_highs_archive_url highs
    https://codeload.github.com/ERGO-Code/HiGHS/tar.gz/refs/tags/v1.11.0 ${csl_highs_archive_sha256})
  FetchContent_Declare(csl_highs
    URL "${csl_highs_archive_url}"
    URL_HASH SHA256=${csl_highs_archive_sha256}
    SOURCE_SUBDIR csl-no-build)
  FetchContent_MakeAvailable(csl_highs)
  # Keep the upstream archive/hash pinned and apply this narrowly scoped
  # downstream initialization fix to the fetched source before compiling it.
  execute_process(
    COMMAND "${CMAKE_COMMAND}"
      "-DSOURCE_FILE=${csl_highs_SOURCE_DIR}/highs/util/HVectorBase.h"
      -P "${PROJECT_SOURCE_DIR}/cmake/ApplyPinnedHighsPatch.cmake"
    RESULT_VARIABLE patch_result
    OUTPUT_VARIABLE patch_output
    ERROR_VARIABLE patch_error)
  if(NOT patch_result EQUAL 0)
    message(FATAL_ERROR "Failed to apply pinned HiGHS downstream patch: ${patch_output}${patch_error}")
  endif()
  file(SHA256 "${csl_highs_SOURCE_DIR}/highs/util/HVectorBase.h" patched_source_sha256)
  if(WIN32)
    set(expected_source_sha256 "f0f4f4f4a4b33088c3b30e63bbe5796c7c2fd498600a7e2acc8002bc4e7eace3")
  else()
    set(expected_source_sha256 "8ee92e023806826fded545e38d0598adacc7b08f07c395c557a1dbaa1733b00b")
  endif()
  if(NOT patched_source_sha256 STREQUAL expected_source_sha256)
    message(FATAL_ERROR "Configured HiGHS patch hash is not the verified platform postimage: ${patched_source_sha256}")
  endif()
  set(CSL_HIGHS_PATCHED_SOURCE_SHA256 "${patched_source_sha256}" PARENT_SCOPE)
  target_compile_definitions(csl_highs_lp PRIVATE
    "CSL_HIGHS_PATCHED_SOURCE_SHA256=\"${patched_source_sha256}\"")
  add_test(NAME pinned_highs_patch_contract
    COMMAND "${CMAKE_COMMAND}"
      "-DUPSTREAM_HEADER=${csl_highs_SOURCE_DIR}/highs/util/HVectorBase.h"
      "-DPATCH_SCRIPT=${PROJECT_SOURCE_DIR}/cmake/ApplyPinnedHighsPatch.cmake"
      "-DWORK_DIR=${PROJECT_BINARY_DIR}/pinned-highs-patch-test"
      -P "${PROJECT_SOURCE_DIR}/tests/cmake/pinned_highs_patch_contract.cmake")
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
