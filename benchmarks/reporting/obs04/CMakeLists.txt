cmake_minimum_required(VERSION 3.31)
project(CSLOBS04InstrumentationComparison LANGUAGES C CXX)

if(NOT DEFINED CSL_SOURCE_ROOT)
  message(FATAL_ERROR "CSL_SOURCE_ROOT must name the pinned clean solver checkout")
endif()
set(BUILD_TESTING OFF CACHE BOOL "Build repository tests" FORCE)
add_subdirectory("${CSL_SOURCE_ROOT}" csl-source)
include(FetchContent)
FetchContent_GetProperties(csl_json SOURCE_DIR OBS04_JSON_SOURCE_DIR)
if(NOT EXISTS "${OBS04_JSON_SOURCE_DIR}/single_include/nlohmann/json.hpp")
  message(FATAL_ERROR "The configured CSL JSON dependency has no single-include header")
endif()

add_executable(csl_obs04_instrumentation_comparison instrumentation_comparison.cpp)
find_package(Git REQUIRED)
execute_process(COMMAND "${GIT_EXECUTABLE}" rev-parse --git-path HEAD
  WORKING_DIRECTORY "${CSL_SOURCE_ROOT}"
  OUTPUT_VARIABLE OBS04_GIT_HEAD_PATH OUTPUT_STRIP_TRAILING_WHITESPACE
  COMMAND_ERROR_IS_FATAL ANY)
get_filename_component(OBS04_GIT_HEAD_PATH "${OBS04_GIT_HEAD_PATH}" ABSOLUTE
  BASE_DIR "${CSL_SOURCE_ROOT}")
if(EXISTS "${OBS04_GIT_HEAD_PATH}")
  set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS "${OBS04_GIT_HEAD_PATH}")
endif()
execute_process(COMMAND "${GIT_EXECUTABLE}" symbolic-ref -q HEAD
  WORKING_DIRECTORY "${CSL_SOURCE_ROOT}"
  OUTPUT_VARIABLE OBS04_GIT_HEAD_REF OUTPUT_STRIP_TRAILING_WHITESPACE
  RESULT_VARIABLE OBS04_GIT_HEAD_REF_RESULT)
execute_process(COMMAND "${GIT_EXECUTABLE}" rev-parse --git-path packed-refs
  WORKING_DIRECTORY "${CSL_SOURCE_ROOT}"
  OUTPUT_VARIABLE OBS04_PACKED_REFS_PATH OUTPUT_STRIP_TRAILING_WHITESPACE
  COMMAND_ERROR_IS_FATAL ANY)
get_filename_component(OBS04_PACKED_REFS_PATH "${OBS04_PACKED_REFS_PATH}" ABSOLUTE
  BASE_DIR "${CSL_SOURCE_ROOT}")
if(EXISTS "${OBS04_PACKED_REFS_PATH}")
  set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS "${OBS04_PACKED_REFS_PATH}")
endif()
if(OBS04_GIT_HEAD_REF_RESULT EQUAL 0 AND NOT OBS04_GIT_HEAD_REF STREQUAL "")
  execute_process(COMMAND "${GIT_EXECUTABLE}" rev-parse --git-path "${OBS04_GIT_HEAD_REF}"
    WORKING_DIRECTORY "${CSL_SOURCE_ROOT}"
    OUTPUT_VARIABLE OBS04_BRANCH_REF_PATH OUTPUT_STRIP_TRAILING_WHITESPACE
    COMMAND_ERROR_IS_FATAL ANY)
  get_filename_component(OBS04_BRANCH_REF_PATH "${OBS04_BRANCH_REF_PATH}" ABSOLUTE
    BASE_DIR "${CSL_SOURCE_ROOT}")
  if(EXISTS "${OBS04_BRANCH_REF_PATH}")
    set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS "${OBS04_BRANCH_REF_PATH}")
  endif()
endif()
execute_process(COMMAND "${GIT_EXECUTABLE}" rev-parse HEAD
  WORKING_DIRECTORY "${CSL_SOURCE_ROOT}"
  OUTPUT_VARIABLE OBS04_SOURCE_REVISION OUTPUT_STRIP_TRAILING_WHITESPACE
  COMMAND_ERROR_IS_FATAL ANY)
execute_process(COMMAND "${GIT_EXECUTABLE}" status --porcelain --untracked-files=all
  WORKING_DIRECTORY "${CSL_SOURCE_ROOT}"
  OUTPUT_VARIABLE OBS04_SOURCE_STATUS OUTPUT_STRIP_TRAILING_WHITESPACE
  COMMAND_ERROR_IS_FATAL ANY)
execute_process(COMMAND "${GIT_EXECUTABLE}" diff --binary HEAD --
  WORKING_DIRECTORY "${CSL_SOURCE_ROOT}"
  OUTPUT_VARIABLE OBS04_TRACKED_DIFF COMMAND_ERROR_IS_FATAL ANY)
string(SHA256 OBS04_TRACKED_DIFF_SHA256 "${OBS04_TRACKED_DIFF}")
execute_process(COMMAND "${GIT_EXECUTABLE}" ls-files
  WORKING_DIRECTORY "${CSL_SOURCE_ROOT}"
  OUTPUT_VARIABLE OBS04_TRACKED_FILES OUTPUT_STRIP_TRAILING_WHITESPACE
  COMMAND_ERROR_IS_FATAL ANY)
string(REPLACE "\n" ";" OBS04_TRACKED_FILES "${OBS04_TRACKED_FILES}")
foreach(OBS04_RELATIVE_FILE IN LISTS OBS04_TRACKED_FILES)
  if(NOT OBS04_RELATIVE_FILE STREQUAL "" AND EXISTS "${CSL_SOURCE_ROOT}/${OBS04_RELATIVE_FILE}")
    set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS
      "${CSL_SOURCE_ROOT}/${OBS04_RELATIVE_FILE}")
  endif()
endforeach()
execute_process(COMMAND "${GIT_EXECUTABLE}" ls-files --others --exclude-standard
  WORKING_DIRECTORY "${CSL_SOURCE_ROOT}"
  OUTPUT_VARIABLE OBS04_UNTRACKED_FILES OUTPUT_STRIP_TRAILING_WHITESPACE
  COMMAND_ERROR_IS_FATAL ANY)
string(REPLACE "\n" ";" OBS04_UNTRACKED_FILES "${OBS04_UNTRACKED_FILES}")
set(OBS04_UNTRACKED_MATERIAL "")
foreach(OBS04_RELATIVE_FILE IN LISTS OBS04_UNTRACKED_FILES)
  if(NOT OBS04_RELATIVE_FILE STREQUAL "")
    set(OBS04_SOURCE_FILE "${CSL_SOURCE_ROOT}/${OBS04_RELATIVE_FILE}")
    if(EXISTS "${OBS04_SOURCE_FILE}")
      set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS "${OBS04_SOURCE_FILE}")
    endif()
    if(EXISTS "${OBS04_SOURCE_FILE}" AND NOT IS_DIRECTORY "${OBS04_SOURCE_FILE}")
      file(SHA256 "${OBS04_SOURCE_FILE}" OBS04_UNTRACKED_FILE_SHA256)
      string(APPEND OBS04_UNTRACKED_MATERIAL "${OBS04_RELATIVE_FILE}:${OBS04_UNTRACKED_FILE_SHA256}\n")
    endif()
  endif()
endforeach()
string(SHA256 OBS04_UNTRACKED_SHA256 "${OBS04_UNTRACKED_MATERIAL}")
string(SHA256 OBS04_SOURCE_TREE_SHA256
  "${OBS04_SOURCE_REVISION}:${OBS04_TRACKED_DIFF_SHA256}:${OBS04_UNTRACKED_SHA256}")
if(OBS04_SOURCE_STATUS STREQUAL "")
  set(OBS04_SOURCE_DIRTY false)
else()
  set(OBS04_SOURCE_DIRTY true)
endif()

# Read the versions and archive identities from the existing dependency pins.
file(STRINGS "${CSL_SOURCE_ROOT}/cmake/HighsDependencies.cmake" OBS04_HIGHS_PIN
  REGEX "refs/tags/v[0-9]+\\.[0-9]+\\.[0-9]+")
string(REGEX MATCH "refs/tags/v([0-9]+\\.[0-9]+\\.[0-9]+)" OBS04_HIGHS_MATCH "${OBS04_HIGHS_PIN}")
set(OBS04_HIGHS_VERSION "${CMAKE_MATCH_1}")
file(STRINGS "${CSL_SOURCE_ROOT}/cmake/HighsDependencies.cmake" OBS04_HIGHS_ARCHIVE_LINE
  REGEX "set\\(csl_highs_archive_sha256 [0-9a-f]+\\)")
string(REGEX MATCH "sha256 ([0-9a-f]+)" OBS04_HIGHS_ARCHIVE_MATCH "${OBS04_HIGHS_ARCHIVE_LINE}")
set(OBS04_HIGHS_ARCHIVE_SHA256 "${CMAKE_MATCH_1}")
file(STRINGS "${CSL_SOURCE_ROOT}/cmake/QhullDependencies.cmake" OBS04_QHULL_PIN
  REGEX "refs/tags/v[0-9]+\\.[0-9]+\\.[0-9]+")
string(REGEX MATCH "refs/tags/v([0-9]+\\.[0-9]+\\.[0-9]+)" OBS04_QHULL_MATCH "${OBS04_QHULL_PIN}")
set(OBS04_QHULL_VERSION "${CMAKE_MATCH_1}")
file(STRINGS "${CSL_SOURCE_ROOT}/cmake/QhullDependencies.cmake" OBS04_QHULL_ARCHIVE_LINE
  REGEX "set\\(csl_qhull_archive_sha256 [0-9a-f]+\\)")
string(REGEX MATCH "sha256 ([0-9a-f]+)" OBS04_QHULL_ARCHIVE_MATCH "${OBS04_QHULL_ARCHIVE_LINE}")
set(OBS04_QHULL_ARCHIVE_SHA256 "${CMAKE_MATCH_1}")
string(LENGTH "${OBS04_HIGHS_ARCHIVE_SHA256}" OBS04_HIGHS_ARCHIVE_SHA_LENGTH)
string(LENGTH "${OBS04_QHULL_ARCHIVE_SHA256}" OBS04_QHULL_ARCHIVE_SHA_LENGTH)
if(OBS04_HIGHS_VERSION STREQUAL "" OR OBS04_QHULL_VERSION STREQUAL "" OR
   NOT OBS04_HIGHS_ARCHIVE_SHA_LENGTH EQUAL 64 OR NOT OBS04_QHULL_ARCHIVE_SHA_LENGTH EQUAL 64)
  message(FATAL_ERROR "OBS-04 could not read the pinned backend version and archive identities")
endif()

string(SHA256 OBS04_C_FLAGS_SHA256 "${CMAKE_C_FLAGS};${CMAKE_C_FLAGS_RELEASE}")
string(SHA256 OBS04_CXX_FLAGS_SHA256 "${CMAKE_CXX_FLAGS};${CMAKE_CXX_FLAGS_RELEASE}")
string(SHA256 OBS04_LINK_FLAGS_SHA256 "${CMAKE_EXE_LINKER_FLAGS};${CMAKE_EXE_LINKER_FLAGS_RELEASE}")
if(MSVC)
  set(OBS04_TARGET_FLAGS "/W4;/WX;/permissive-;cxx_std_20")
else()
  set(OBS04_TARGET_FLAGS "-Wall;-Wextra;-Wpedantic;-Werror;cxx_std_20")
endif()
string(SHA256 OBS04_TARGET_FLAGS_SHA256 "${OBS04_TARGET_FLAGS}")
set(OBS04_ARCHITECTURE "${CMAKE_SYSTEM_PROCESSOR}")
if(OBS04_ARCHITECTURE STREQUAL "")
  set(OBS04_ARCHITECTURE "${CMAKE_GENERATOR_PLATFORM}")
endif()
if(OBS04_ARCHITECTURE STREQUAL "")
  set(OBS04_ARCHITECTURE "unspecified")
endif()
set(OBS04_BUILD_TYPE "Release")
set(OBS04_BUILD_INFO_JSON "{\"schema\":\"csl.obs04-build/1\",\"source_revision\":\"${OBS04_SOURCE_REVISION}\",\"source_tree_sha256\":\"${OBS04_SOURCE_TREE_SHA256}\",\"source_snapshot_method\":\"git-head-tracked-diff-untracked-content-sha256/1\",\"source_dirty\":${OBS04_SOURCE_DIRTY},\"compiler_id\":\"${CMAKE_CXX_COMPILER_ID}\",\"compiler_version\":\"${CMAKE_CXX_COMPILER_VERSION}\",\"generator\":\"${CMAKE_GENERATOR}\",\"architecture\":\"${OBS04_ARCHITECTURE}\",\"build_type\":\"${OBS04_BUILD_TYPE}\",\"cxx_standard\":\"20\",\"c_flags_sha256\":\"${OBS04_C_FLAGS_SHA256}\",\"cxx_flags_sha256\":\"${OBS04_CXX_FLAGS_SHA256}\",\"executable_link_flags_sha256\":\"${OBS04_LINK_FLAGS_SHA256}\",\"target_flags_sha256\":\"${OBS04_TARGET_FLAGS_SHA256}\",\"backends\":{\"highs\":{\"version\":\"${OBS04_HIGHS_VERSION}\",\"archive_sha256\":\"${OBS04_HIGHS_ARCHIVE_SHA256}\"},\"qhull\":{\"version\":\"${OBS04_QHULL_VERSION}\",\"archive_sha256\":\"${OBS04_QHULL_ARCHIVE_SHA256}\"}}}")
file(MAKE_DIRECTORY "${CMAKE_CURRENT_BINARY_DIR}/obs04-generated")
configure_file(Obs04BuildInfo.hpp.in
  "${CMAKE_CURRENT_BINARY_DIR}/obs04-generated/Obs04BuildInfo.hpp" @ONLY)
target_include_directories(csl_obs04_instrumentation_comparison PRIVATE
  "${CMAKE_CURRENT_BINARY_DIR}/obs04-generated")
target_include_directories(csl_obs04_instrumentation_comparison SYSTEM PRIVATE
  "${OBS04_JSON_SOURCE_DIR}/single_include")
target_link_libraries(csl_obs04_instrumentation_comparison PRIVATE
  CSL::application CSL::strategy_a CSL::strategy_b CSL::polyhedral CSL::affine_sum
  CSL::qhull_conversion CSL::highs_lp CSL::highs_convex CSL::witness_selector)
target_compile_features(csl_obs04_instrumentation_comparison PRIVATE cxx_std_20)
target_compile_definitions(csl_obs04_instrumentation_comparison PRIVATE
  $<$<CONFIG:Release>:NDEBUG>
  OBS04_BUILD_CONFIGURATION=\"$<CONFIG>\")
if(MSVC)
  target_compile_options(csl_obs04_instrumentation_comparison PRIVATE /W4 /WX /permissive-)
else()
  target_compile_options(csl_obs04_instrumentation_comparison PRIVATE -Wall -Wextra -Wpedantic -Werror)
endif()
