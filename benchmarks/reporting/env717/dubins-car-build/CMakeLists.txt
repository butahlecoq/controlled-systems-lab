cmake_minimum_required(VERSION 3.31)
project(Env717DubinsCar LANGUAGES CXX)
set(CMAKE_CXX_EXTENSIONS OFF)

include(CTest)
include(FetchContent)
find_package(Python3 REQUIRED COMPONENTS Interpreter)

set(CSL_ROOT "${CMAKE_CURRENT_LIST_DIR}/../../../..")
set(JSON_ARCHIVE_SHA256 "0d8ef5af7f9794e3263480193c491549b2ba6cc74bb018906202ada498a79406")
FetchContent_Declare(csl_json
  URL "https://codeload.github.com/nlohmann/json/tar.gz/refs/tags/v3.11.3"
  URL_HASH "SHA256=${JSON_ARCHIVE_SHA256}"
  SOURCE_SUBDIR csl-no-build)
FetchContent_MakeAvailable(csl_json)

set(DRIVER "${CSL_ROOT}/benchmarks/reporting/env717/dubins_car.cpp")
set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS "${DRIVER}")
file(SHA256 "${DRIVER}" DRIVER_SHA256)
execute_process(COMMAND git rev-parse HEAD
  WORKING_DIRECTORY "${CSL_ROOT}"
  OUTPUT_VARIABLE SOURCE_COMMIT
  OUTPUT_STRIP_TRAILING_WHITESPACE
  COMMAND_ERROR_IS_FATAL ANY)

add_executable(csl_env717_dubins_car "${DRIVER}")
target_include_directories(csl_env717_dubins_car SYSTEM PRIVATE "${csl_json_SOURCE_DIR}/include")
target_compile_features(csl_env717_dubins_car PRIVATE cxx_std_20)
target_compile_definitions(csl_env717_dubins_car PRIVATE
  $<$<CONFIG:Release>:NDEBUG>
  CSL_ENV717_DUBINS_DRIVER_SHA256="${DRIVER_SHA256}"
  CSL_ENV717_DUBINS_COMPILER_ID="${CMAKE_CXX_COMPILER_ID}"
  CSL_ENV717_DUBINS_COMPILER_VERSION="${CMAKE_CXX_COMPILER_VERSION}"
  CSL_ENV717_DUBINS_BUILD_TYPE="${CMAKE_BUILD_TYPE}"
  CSL_ENV717_DUBINS_ARCHITECTURE="${CMAKE_SYSTEM_PROCESSOR}"
  CSL_ENV717_DUBINS_SOURCE_COMMIT="${SOURCE_COMMIT}")
if(MSVC)
  target_compile_options(csl_env717_dubins_car PRIVATE /W4 /WX /permissive-)
else()
  target_compile_options(csl_env717_dubins_car PRIVATE -Wall -Wextra -Wpedantic -Werror)
endif()

if(BUILD_TESTING)
  add_test(NAME env717_dubins_car_smoke
    COMMAND Python3::Interpreter "${CSL_ROOT}/scripts/reports/env717/check_dubins_car.py"
      "$<TARGET_FILE:csl_env717_dubins_car>")
  set_tests_properties(env717_dubins_car_smoke PROPERTIES LABELS reporting)
endif()
