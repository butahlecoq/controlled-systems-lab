cmake_minimum_required(VERSION 3.31)
project(CSLResearch LANGUAGES CXX)
include(CTest)

find_package(CSL 0.1.0 EXACT CONFIG REQUIRED)

# The SDK's JSON parser is private. Research drivers supply their own dependency.
include(FetchContent)
FetchContent_Declare(research_json
  URL https://codeload.github.com/nlohmann/json/tar.gz/refs/tags/v3.11.3
  URL_HASH SHA256=0d8ef5af7f9794e3263480193c491549b2ba6cc74bb018906202ada498a79406
  SOURCE_SUBDIR csl-no-build)
FetchContent_MakeAvailable(research_json)

include(reporting/exp824/NominalTarget.cmake)
csl_add_issue824_nominal_report("${research_json_SOURCE_DIR}/include")

if(BUILD_TESTING)
  find_package(Python3 3.11 REQUIRED COMPONENTS Interpreter)
  add_test(NAME research_issue824_nominal
    COMMAND "${CMAKE_COMMAND}"
      "-DREPORT=$<TARGET_FILE:csl_issue824_nominal_report>"
      "-DPYTHON=$<TARGET_FILE:Python3::Interpreter>"
      "-DCHECKER=${CMAKE_CURRENT_SOURCE_DIR}/../scripts/reports/exp824/check_nominal.py"
      "-DOUTPUT=${CMAKE_CURRENT_BINARY_DIR}/issue824-nominal-result.json"
      -P "${CMAKE_CURRENT_SOURCE_DIR}/reporting/exp824/CheckNominal.cmake")
endif()
