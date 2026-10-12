include_guard(GLOBAL)
include(FetchContent)
# One private ADR0002 content identity; an earlier identical declaration/population
# is reused by FetchContent. No upstream build or exported parser target.
FetchContent_Declare(csl_json
  URL https://codeload.github.com/nlohmann/json/tar.gz/refs/tags/v3.11.3
  URL_HASH SHA256=0d8ef5af7f9794e3263480193c491549b2ba6cc74bb018906202ada498a79406
  SOURCE_SUBDIR csl-no-build)
FetchContent_MakeAvailable(csl_json)
install(FILES ${csl_json_SOURCE_DIR}/LICENSE.MIT
  DESTINATION ${CMAKE_INSTALL_DATADIR}/CSL/notices/nlohmann-json-3.11.3)
