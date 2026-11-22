include_guard(GLOBAL)
include(FetchContent)
include(${CMAKE_CURRENT_LIST_DIR}/DependencyArchive.cmake)
set(csl_json_archive_sha256 0d8ef5af7f9794e3263480193c491549b2ba6cc74bb018906202ada498a79406)
csl_dependency_archive_url(csl_json_archive_url json
  https://codeload.github.com/nlohmann/json/tar.gz/refs/tags/v3.11.3 ${csl_json_archive_sha256})
FetchContent_Declare(csl_json
  URL "${csl_json_archive_url}"
  URL_HASH SHA256=${csl_json_archive_sha256}
  SOURCE_SUBDIR csl-no-build)
FetchContent_MakeAvailable(csl_json)
install(FILES ${csl_json_SOURCE_DIR}/LICENSE.MIT
  DESTINATION ${CMAKE_INSTALL_DATADIR}/CSL/notices/nlohmann-json-3.11.3)
