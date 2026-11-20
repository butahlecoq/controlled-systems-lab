cmake_minimum_required(VERSION 3.31)
project(catalogue_external_fixed_plan LANGUAGES CXX)

find_path(JSON_INCLUDE nlohmann/json.hpp REQUIRED)
if(DEFINED CSL_SOURCE_DIR)
    set(BUILD_TESTING OFF CACHE BOOL "Build SDK tests")
    add_subdirectory("${CSL_SOURCE_DIR}" "${CMAKE_CURRENT_BINARY_DIR}/sdk")
else()
    find_package(CSL 0.1.1 EXACT CONFIG REQUIRED)
endif()

add_executable(catalogue_external catalogue_external.cpp)
target_compile_features(catalogue_external PRIVATE cxx_std_20)
target_include_directories(catalogue_external SYSTEM PRIVATE "${JSON_INCLUDE}")
target_link_libraries(catalogue_external PRIVATE
    CSL::model_catalogue
    CSL::fixed_plan_disturbance
    CSL::finite_plan_box
    CSL::finite_plan_zonotope
    CSL::finite_plan_parallelotope
    CSL::finite_plan_ellipsoid)
