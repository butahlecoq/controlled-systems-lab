if((CSL_BUILD_GEO02_REPORT OR CSL_BUILD_GEO03_REPORT OR CSL_BUILD_GEO04_REPORT OR
    CSL_BUILD_OPT04_REPORT OR CSL_BUILD_SYN01_REPORT OR CSL_BUILD_MPC03_REPORT OR
    CSL_BUILD_STAGE_PROJECTION_ROUTE OR CSL_BUILD_SYN02_REPORT OR
    CSL_BUILD_MPC08_REPORT OR
    CSL_BUILD_REPORTS) AND NOT CSL_ENABLE_HIGHS)
  message(FATAL_ERROR "The selected report requires CSL_ENABLE_HIGHS")
endif()
if((CSL_BUILD_GEO02_REPORT OR CSL_BUILD_GEO03_REPORT OR CSL_BUILD_GEO04_REPORT OR
    CSL_BUILD_SYN01_REPORT OR CSL_BUILD_STAGE_PROJECTION_ROUTE OR
    CSL_BUILD_MPC08_REPORT) AND NOT CSL_ENABLE_QHULL)
  message(FATAL_ERROR "The selected report requires CSL_ENABLE_QHULL")
endif()

# Non-installed measurement targets; each option requires the declared adapters.

if(CSL_BUILD_MPC08_REPORT)
add_executable(csl_mpc08_explicit_compare benchmarks/reporting/mpc08_explicit/mpc08_strategy_comparison.cpp)
target_compile_features(csl_mpc08_explicit_compare PRIVATE cxx_std_20)
target_compile_definitions(csl_mpc08_explicit_compare PRIVATE $<$<CONFIG:Release>:NDEBUG>)
target_link_libraries(csl_mpc08_explicit_compare PRIVATE CSL::strategy_a CSL::strategy_b
    CSL::highs_lp CSL::highs_convex CSL::qhull_conversion CSL::affine_sum CSL::polyhedral)
if(MSVC)
target_compile_options(csl_mpc08_explicit_compare PRIVATE /W4 /WX /permissive-)
else()
target_compile_options(csl_mpc08_explicit_compare PRIVATE -Wall -Wextra -Wpedantic -Werror)
endif()
endif()

if(CSL_BUILD_MPC06_REPORT)
set(MPC06_SCENARIO_FILE ${CMAKE_CURRENT_SOURCE_DIR}/benchmarks/scenarios/mpc06-nilpotent-tube-v1.json)
set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS ${MPC06_SCENARIO_FILE})
file(SHA256 ${MPC06_SCENARIO_FILE} MPC06_SCENARIO_SHA256)
add_executable(csl_mpc06_tube_pilot benchmarks/reporting/mpc06_tube/driver.cpp)
target_include_directories(csl_mpc06_tube_pilot PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/src)
target_compile_features(csl_mpc06_tube_pilot PRIVATE cxx_std_20)
target_compile_definitions(csl_mpc06_tube_pilot PRIVATE
  CSL_MPC06_SCENARIO_SHA256="${MPC06_SCENARIO_SHA256}")
if(MSVC)
target_compile_options(csl_mpc06_tube_pilot PRIVATE /W4 /WX /permissive-)
else()
target_compile_options(csl_mpc06_tube_pilot PRIVATE -Wall -Wextra -Wpedantic -Werror)
endif()
if(BUILD_TESTING)
find_package(Python3 3.11 REQUIRED COMPONENTS Interpreter)
add_test(NAME mpc06_tube_pilot_independent_check COMMAND Python3::Interpreter
  ${CMAKE_CURRENT_SOURCE_DIR}/scripts/reports/mpc06/check_tube.py
  $<TARGET_FILE:csl_mpc06_tube_pilot>)
set_tests_properties(mpc06_tube_pilot_independent_check PROPERTIES LABELS reporting)
endif()
endif()

if(CSL_BUILD_GEO08_REPORT)
add_executable(csl_geo08_lazy_report benchmarks/reporting/geo08/driver.cpp)
target_link_libraries(csl_geo08_lazy_report PRIVATE CSL::lazy_geometry CSL::polyhedral)
target_compile_features(csl_geo08_lazy_report PRIVATE cxx_std_20)
if(MSVC)
target_compile_options(csl_geo08_lazy_report PRIVATE /W4 /WX /permissive-)
else()
target_compile_options(csl_geo08_lazy_report PRIVATE -Wall -Wextra -Wpedantic -Werror)
endif()
if(BUILD_TESTING)
add_test(NAME geo08_report_smoke COMMAND csl_geo08_lazy_report smoke)
set_tests_properties(geo08_report_smoke PROPERTIES
  PASS_REGULAR_EXPRESSION "smoke,0,1,1,1,completed,true,[0-9]+,5,16,0")
endif()
endif()

if(CSL_BUILD_APP03_REPORT)
add_executable(csl_app03_zonotope_report benchmarks/reporting/app03/driver.cpp)
target_link_libraries(csl_app03_zonotope_report PRIVATE CSL::approximation CSL::geometry_generators)
target_compile_features(csl_app03_zonotope_report PRIVATE cxx_std_20)
if(MSVC)
target_compile_options(csl_app03_zonotope_report PRIVATE /W4 /WX /permissive-)
else()
target_compile_options(csl_app03_zonotope_report PRIVATE -Wall -Wextra -Wpedantic -Werror)
endif()
endif()

if(CSL_BUILD_APP04_REPORT)
add_executable(csl_app04_ellipsoid_report benchmarks/reporting/app04/driver.cpp)
target_link_libraries(csl_app04_ellipsoid_report PRIVATE CSL::approximation)
target_compile_features(csl_app04_ellipsoid_report PRIVATE cxx_std_20)
if(MSVC)
target_compile_options(csl_app04_ellipsoid_report PRIVATE /W4 /WX /permissive-)
else()
target_compile_options(csl_app04_ellipsoid_report PRIVATE -Wall -Wextra -Wpedantic -Werror)
endif()

if(BUILD_TESTING)
find_package(Python3 3.11 REQUIRED COMPONENTS Interpreter)
add_test(NAME app04_report_smoke COMMAND Python3::Interpreter
  ${CMAKE_CURRENT_SOURCE_DIR}/scripts/reports/app04/check_smoke.py
  $<TARGET_FILE:csl_app04_ellipsoid_report>)
set_tests_properties(app04_report_smoke PROPERTIES LABELS reporting)
endif()
endif()

if(CSL_BUILD_EXT05_REPORT)
add_executable(csl_ext05_discretization_report benchmarks/reporting/ext05/driver.cpp)
target_link_libraries(csl_ext05_discretization_report PRIVATE CSL::model)
target_compile_features(csl_ext05_discretization_report PRIVATE cxx_std_20)
if(MSVC)
target_compile_options(csl_ext05_discretization_report PRIVATE /W4 /WX /permissive-)
else()
target_compile_options(csl_ext05_discretization_report PRIVATE -Wall -Wextra -Wpedantic -Werror)
endif()
endif()

if(CSL_BUILD_EXT07_REPORT)
if(NOT CSL_ENABLE_HIGHS)
  message(FATAL_ERROR "EXT-07 report requires the production HiGHS LP and convex adapters")
endif()
add_executable(csl_ext07_hybrid_report benchmarks/reporting/ext07/driver.cpp)
target_link_libraries(csl_ext07_hybrid_report PRIVATE
  CSL::hybrid_path_program CSL::highs_lp CSL::highs_convex)
target_compile_features(csl_ext07_hybrid_report PRIVATE cxx_std_20)
if(MSVC)
target_compile_options(csl_ext07_hybrid_report PRIVATE /W4 /WX /permissive-)
else()
target_compile_options(csl_ext07_hybrid_report PRIVATE -Wall -Wextra -Wpedantic -Werror)
endif()
if(BUILD_TESTING)
add_test(NAME ext07_report_smoke COMMAND csl_ext07_hybrid_report smoke)
set_tests_properties(ext07_report_smoke PROPERTIES LABELS reporting)
endif()
add_executable(csl_ext07_two_parameter_report
  benchmarks/reporting/ext07/two_parameter_driver.cpp)
target_link_libraries(csl_ext07_two_parameter_report PRIVATE
  CSL::hybrid_path_program CSL::highs_lp CSL::highs_convex)
target_compile_features(csl_ext07_two_parameter_report PRIVATE cxx_std_20)
if(MSVC)
target_compile_options(csl_ext07_two_parameter_report PRIVATE /W4 /WX /permissive-)
else()
target_compile_options(csl_ext07_two_parameter_report PRIVATE -Wall -Wextra -Wpedantic -Werror)
endif()
if(BUILD_TESTING)
add_test(NAME ext07_two_parameter_report_smoke
  COMMAND csl_ext07_two_parameter_report smoke)
set_tests_properties(ext07_two_parameter_report_smoke PROPERTIES LABELS reporting)
endif()
endif()

if(CSL_BUILD_OPT10_REPORT)
if(NOT CSL_ENABLE_HIGHS)
  message(FATAL_ERROR "OPT-10 report requires the production HiGHS LP adapter")
endif()
add_executable(csl_opt10_smooth_report benchmarks/reporting/opt10/driver.cpp)
target_link_libraries(csl_opt10_smooth_report PRIVATE CSL::feasible_directions CSL::highs_lp)
target_compile_features(csl_opt10_smooth_report PRIVATE cxx_std_20)
if(MSVC)
target_compile_options(csl_opt10_smooth_report PRIVATE /W4 /WX /permissive-)
else()
target_compile_options(csl_opt10_smooth_report PRIVATE -Wall -Wextra -Wpedantic -Werror)
endif()
endif()

if(CSL_BUILD_APP02_REPORT)
add_executable(csl_app02_approximation_report benchmarks/reporting/app02/driver.cpp)
target_link_libraries(csl_app02_approximation_report PRIVATE CSL::approximation)
target_compile_features(csl_app02_approximation_report PRIVATE cxx_std_20)
if(MSVC)
target_compile_options(csl_app02_approximation_report PRIVATE /W4 /WX /permissive-)
else()
target_compile_options(csl_app02_approximation_report PRIVATE -Wall -Wextra -Wpedantic -Werror)
endif()
if(BUILD_TESTING)
find_package(Python3 3.11 REQUIRED COMPONENTS Interpreter)
add_test(NAME app02_report_smoke COMMAND Python3::Interpreter
  ${CMAKE_CURRENT_SOURCE_DIR}/scripts/reports/app02/check_smoke.py
  $<TARGET_FILE:csl_app02_approximation_report>)
set_tests_properties(app02_report_smoke PROPERTIES LABELS reporting)
endif()
endif()

if(CSL_BUILD_EXP04_REPORT)
add_executable(csl_exp04_replay_report benchmarks/reporting/exp04/driver.cpp)
target_link_libraries(csl_exp04_replay_report PRIVATE CSL::simulation)
target_compile_features(csl_exp04_replay_report PRIVATE cxx_std_20)
if(MSVC)
target_compile_options(csl_exp04_replay_report PRIVATE /W4 /WX /permissive-)
else()
target_compile_options(csl_exp04_replay_report PRIVATE -Wall -Wextra -Wpedantic -Werror)
endif()
if(BUILD_TESTING)
find_package(Python3 3.11 REQUIRED COMPONENTS Interpreter)
add_test(NAME exp04_report_smoke COMMAND Python3::Interpreter
  ${CMAKE_CURRENT_SOURCE_DIR}/scripts/reports/exp04/check_smoke.py
  $<TARGET_FILE:csl_exp04_replay_report>)
set_tests_properties(exp04_report_smoke PROPERTIES LABELS reporting)
endif()
endif()

if(CSL_BUILD_ISSUE3_REPORT)
include(cmake/JsonDependencies.cmake)
file(SHA256 ${CMAKE_CURRENT_SOURCE_DIR}/benchmarks/reporting/issue3/finite_catalogue_driver.cpp
    ISSUE3_FIXTURE_SHA256)
execute_process(COMMAND git rev-parse HEAD WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}
    OUTPUT_VARIABLE ISSUE3_HARNESS_COMMIT OUTPUT_STRIP_TRAILING_WHITESPACE COMMAND_ERROR_IS_FATAL ANY)
add_executable(csl_issue3_finite_action_report benchmarks/reporting/issue3/finite_catalogue_driver.cpp)
target_link_libraries(csl_issue3_finite_action_report PRIVATE CSL::finite_action_minimax CSL::resolved_core)
target_include_directories(csl_issue3_finite_action_report SYSTEM PRIVATE ${csl_json_SOURCE_DIR}/include)
target_compile_features(csl_issue3_finite_action_report PRIVATE cxx_std_20)
target_compile_definitions(csl_issue3_finite_action_report PRIVATE
    $<$<CONFIG:Release>:NDEBUG> CSL_ISSUE3_HARNESS_COMMIT="${ISSUE3_HARNESS_COMMIT}"
    CSL_ISSUE3_FIXTURE_SHA256="${ISSUE3_FIXTURE_SHA256}")
if(MSVC)
target_compile_options(csl_issue3_finite_action_report PRIVATE /W4 /WX /permissive-)
else()
target_compile_options(csl_issue3_finite_action_report PRIVATE -Wall -Wextra -Wpedantic -Werror)
endif()
if(BUILD_TESTING)
find_package(Python3 3.11 REQUIRED COMPONENTS Interpreter)
add_test(NAME issue3_report_smoke COMMAND Python3::Interpreter
  ${CMAKE_CURRENT_SOURCE_DIR}/scripts/reports/issue3/check_smoke.py
  $<TARGET_FILE:csl_issue3_finite_action_report>)
set_tests_properties(issue3_report_smoke PROPERTIES LABELS reporting)
endif()
endif()

if(CSL_BUILD_ISSUE3_VALIDATED_REPORT)
include(cmake/JsonDependencies.cmake)
file(SHA256 ${CMAKE_CURRENT_SOURCE_DIR}/benchmarks/reporting/issue3/validated_driver.cpp
    ISSUE3_VALIDATED_FIXTURE_SHA256)
execute_process(COMMAND git rev-parse HEAD WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}
    OUTPUT_VARIABLE ISSUE3_VALIDATED_HARNESS_COMMIT OUTPUT_STRIP_TRAILING_WHITESPACE COMMAND_ERROR_IS_FATAL ANY)
set(ISSUE3_VALIDATED_SOURCE_COMMIT c72f3480c8fea2575ba860890502857006e9b9f4)
add_executable(csl_issue3_validated_report benchmarks/reporting/issue3/validated_driver.cpp)
target_link_libraries(csl_issue3_validated_report PRIVATE
    CSL::validated_finite_action_minimax CSL::resolved_core)
target_include_directories(csl_issue3_validated_report SYSTEM PRIVATE ${csl_json_SOURCE_DIR}/include)
target_compile_features(csl_issue3_validated_report PRIVATE cxx_std_20)
target_compile_definitions(csl_issue3_validated_report PRIVATE
    $<$<CONFIG:Release>:NDEBUG>
    CSL_ISSUE3_VALIDATED_SOURCE_COMMIT="${ISSUE3_VALIDATED_SOURCE_COMMIT}"
    CSL_ISSUE3_VALIDATED_HARNESS_COMMIT="${ISSUE3_VALIDATED_HARNESS_COMMIT}"
    CSL_ISSUE3_VALIDATED_FIXTURE_SHA256="${ISSUE3_VALIDATED_FIXTURE_SHA256}")
if(MSVC)
target_compile_options(csl_issue3_validated_report PRIVATE /W4 /WX /permissive-)
else()
target_compile_options(csl_issue3_validated_report PRIVATE -Wall -Wextra -Wpedantic -Werror)
endif()
endif()

if(CSL_BUILD_ISSUE422_REPORT)
include(cmake/JsonDependencies.cmake)
file(SHA256 ${CMAKE_CURRENT_SOURCE_DIR}/benchmarks/reporting/issue422/fixed_plan_comparison.cpp
    ISSUE422_HARNESS_SHA256)
file(SHA256 ${CMAKE_CURRENT_SOURCE_DIR}/src/optimization/finite_action_minimax.cpp
    ISSUE422_NUMERICAL_SOURCE_SHA256)
file(SHA256 ${CMAKE_CURRENT_SOURCE_DIR}/src/optimization/validated_finite_action_minimax.cpp
    ISSUE422_VALIDATED_SOURCE_SHA256)
execute_process(COMMAND git rev-parse HEAD WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}
    OUTPUT_VARIABLE ISSUE422_SOURCE_COMMIT OUTPUT_STRIP_TRAILING_WHITESPACE COMMAND_ERROR_IS_FATAL ANY)
execute_process(COMMAND git status --porcelain --untracked-files=all WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}
    OUTPUT_VARIABLE ISSUE422_SOURCE_STATUS OUTPUT_STRIP_TRAILING_WHITESPACE COMMAND_ERROR_IS_FATAL ANY)
execute_process(COMMAND git diff --binary HEAD -- WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}
    OUTPUT_VARIABLE ISSUE422_TRACKED_DIFF COMMAND_ERROR_IS_FATAL ANY)
string(SHA256 ISSUE422_TRACKED_DIFF_SHA256 "${ISSUE422_TRACKED_DIFF}")
execute_process(COMMAND git ls-files --others --exclude-standard WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}
    OUTPUT_VARIABLE ISSUE422_UNTRACKED_FILES OUTPUT_STRIP_TRAILING_WHITESPACE COMMAND_ERROR_IS_FATAL ANY)
string(REPLACE "\n" ";" ISSUE422_UNTRACKED_FILES "${ISSUE422_UNTRACKED_FILES}")
set(ISSUE422_UNTRACKED_MATERIAL "")
foreach(ISSUE422_FILE IN LISTS ISSUE422_UNTRACKED_FILES)
    if(NOT ISSUE422_FILE STREQUAL "" AND EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/${ISSUE422_FILE}" AND
       NOT IS_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}/${ISSUE422_FILE}")
        file(SHA256 "${CMAKE_CURRENT_SOURCE_DIR}/${ISSUE422_FILE}" ISSUE422_FILE_SHA256)
        string(APPEND ISSUE422_UNTRACKED_MATERIAL "${ISSUE422_FILE}:${ISSUE422_FILE_SHA256}\n")
    endif()
endforeach()
string(SHA256 ISSUE422_UNTRACKED_SHA256 "${ISSUE422_UNTRACKED_MATERIAL}")
string(SHA256 ISSUE422_SOURCE_TREE_SHA256
    "${ISSUE422_SOURCE_COMMIT}:${ISSUE422_TRACKED_DIFF_SHA256}:${ISSUE422_UNTRACKED_SHA256}")
if(ISSUE422_SOURCE_STATUS STREQUAL "")
    set(ISSUE422_SOURCE_DIRTY false)
else()
    set(ISSUE422_SOURCE_DIRTY true)
endif()
file(STRINGS ${CMAKE_CURRENT_SOURCE_DIR}/cmake/HighsDependencies.cmake ISSUE422_HIGHS_PIN REGEX "refs/tags/v[0-9]+\\.[0-9]+\\.[0-9]+")
string(REGEX MATCH "refs/tags/v([0-9]+\\.[0-9]+\\.[0-9]+)" ISSUE422_HIGHS_MATCH "${ISSUE422_HIGHS_PIN}")
set(ISSUE422_HIGHS_VERSION "${CMAKE_MATCH_1}")
file(STRINGS ${CMAKE_CURRENT_SOURCE_DIR}/cmake/HighsDependencies.cmake ISSUE422_HIGHS_HASH_LINE REGEX "set\\(csl_highs_archive_sha256 [0-9a-f]+\\)")
string(REGEX MATCH "sha256 ([0-9a-f]+)" ISSUE422_HIGHS_HASH_MATCH "${ISSUE422_HIGHS_HASH_LINE}")
set(ISSUE422_HIGHS_SHA256 "${CMAKE_MATCH_1}")
file(STRINGS ${CMAKE_CURRENT_SOURCE_DIR}/cmake/QhullDependencies.cmake ISSUE422_QHULL_PIN REGEX "refs/tags/v[0-9]+\\.[0-9]+\\.[0-9]+")
string(REGEX MATCH "refs/tags/v([0-9]+\\.[0-9]+\\.[0-9]+)" ISSUE422_QHULL_MATCH "${ISSUE422_QHULL_PIN}")
set(ISSUE422_QHULL_VERSION "${CMAKE_MATCH_1}")
file(STRINGS ${CMAKE_CURRENT_SOURCE_DIR}/cmake/QhullDependencies.cmake ISSUE422_QHULL_HASH_LINE REGEX "set\\(csl_qhull_archive_sha256 [0-9a-f]+\\)")
string(REGEX MATCH "sha256 ([0-9a-f]+)" ISSUE422_QHULL_HASH_MATCH "${ISSUE422_QHULL_HASH_LINE}")
set(ISSUE422_QHULL_SHA256 "${CMAKE_MATCH_1}")
string(SHA256 ISSUE422_C_FLAGS_SHA256 "${CMAKE_C_FLAGS} ${CMAKE_C_FLAGS_RELEASE}")
string(SHA256 ISSUE422_CXX_FLAGS_SHA256 "${CMAKE_CXX_FLAGS} ${CMAKE_CXX_FLAGS_RELEASE}")
string(SHA256 ISSUE422_LINK_FLAGS_SHA256 "${CMAKE_EXE_LINKER_FLAGS} ${CMAKE_EXE_LINKER_FLAGS_RELEASE}")
string(SHA256 ISSUE422_TARGET_FLAGS_SHA256 "-Wall -Wextra -Wpedantic -Werror")
add_executable(csl_issue422_fixed_plan_comparison benchmarks/reporting/issue422/fixed_plan_comparison.cpp)
target_link_libraries(csl_issue422_fixed_plan_comparison PRIVATE
    CSL::finite_action_minimax CSL::validated_finite_action_minimax CSL::artifacts CSL::resolved_core)
target_include_directories(csl_issue422_fixed_plan_comparison SYSTEM PRIVATE ${csl_json_SOURCE_DIR}/include)
target_compile_features(csl_issue422_fixed_plan_comparison PRIVATE cxx_std_20)
target_compile_definitions(csl_issue422_fixed_plan_comparison PRIVATE
    $<$<CONFIG:Release>:NDEBUG> CSL_ISSUE422_HARNESS_SHA256="${ISSUE422_HARNESS_SHA256}"
    CSL_ISSUE422_SOURCE_COMMIT="${ISSUE422_SOURCE_COMMIT}"
    CSL_ISSUE422_SOURCE_TREE_SHA256="${ISSUE422_SOURCE_TREE_SHA256}"
    CSL_ISSUE422_SOURCE_DIRTY=${ISSUE422_SOURCE_DIRTY}
    CSL_ISSUE422_COMPILER_ID="${CMAKE_CXX_COMPILER_ID}"
    CSL_ISSUE422_COMPILER_VERSION="${CMAKE_CXX_COMPILER_VERSION}"
    CSL_ISSUE422_GENERATOR="${CMAKE_GENERATOR}"
    CSL_ISSUE422_ARCHITECTURE="${CMAKE_SYSTEM_PROCESSOR}"
    CSL_ISSUE422_BUILD_TYPE="${CMAKE_BUILD_TYPE}"
    CSL_ISSUE422_C_FLAGS_SHA256="${ISSUE422_C_FLAGS_SHA256}"
    CSL_ISSUE422_CXX_FLAGS_SHA256="${ISSUE422_CXX_FLAGS_SHA256}"
    CSL_ISSUE422_LINK_FLAGS_SHA256="${ISSUE422_LINK_FLAGS_SHA256}"
    CSL_ISSUE422_TARGET_FLAGS_SHA256="${ISSUE422_TARGET_FLAGS_SHA256}"
    CSL_ISSUE422_HIGHS_VERSION="${ISSUE422_HIGHS_VERSION}"
    CSL_ISSUE422_HIGHS_SHA256="${ISSUE422_HIGHS_SHA256}"
    CSL_ISSUE422_QHULL_VERSION="${ISSUE422_QHULL_VERSION}"
    CSL_ISSUE422_QHULL_SHA256="${ISSUE422_QHULL_SHA256}"
    CSL_ISSUE422_NUMERICAL_SOURCE_SHA256="${ISSUE422_NUMERICAL_SOURCE_SHA256}"
    CSL_ISSUE422_VALIDATED_SOURCE_SHA256="${ISSUE422_VALIDATED_SOURCE_SHA256}")
if(MSVC)
target_compile_options(csl_issue422_fixed_plan_comparison PRIVATE /W4 /WX /permissive-)
else()
target_compile_options(csl_issue422_fixed_plan_comparison PRIVATE -Wall -Wextra -Wpedantic -Werror)
endif()
if(BUILD_TESTING)
find_package(Python3 3.11 REQUIRED COMPONENTS Interpreter)
add_test(NAME issue422_fixed_plan_report_smoke COMMAND Python3::Interpreter
  ${CMAKE_CURRENT_SOURCE_DIR}/scripts/reports/issue422/check_smoke.py
  $<TARGET_FILE:csl_issue422_fixed_plan_comparison>)
set_tests_properties(issue422_fixed_plan_report_smoke PROPERTIES LABELS reporting)
endif()
endif()

if(CSL_BUILD_MPC03_REPORT)
include(cmake/JsonDependencies.cmake)
add_executable(csl_mpc03_robust_minimax_report benchmarks/reporting/mpc03/robust_minimax_driver.cpp)
target_link_libraries(csl_mpc03_robust_minimax_report PRIVATE highs CSL::finite_action_minimax CSL::resolved_core)
target_include_directories(csl_mpc03_robust_minimax_report SYSTEM PRIVATE ${csl_json_SOURCE_DIR}/include)
target_compile_features(csl_mpc03_robust_minimax_report PRIVATE cxx_std_20)
add_executable(csl_mpc03_b08_comparison_record benchmarks/reporting/mpc03/b08_comparison_record.cpp)
target_link_libraries(csl_mpc03_b08_comparison_record PRIVATE CSL::artifacts CSL::resolved_core)
target_include_directories(csl_mpc03_b08_comparison_record SYSTEM PRIVATE ${csl_json_SOURCE_DIR}/include)
target_compile_features(csl_mpc03_b08_comparison_record PRIVATE cxx_std_20)
if(MSVC)
target_compile_options(csl_mpc03_robust_minimax_report PRIVATE /W4 /WX /permissive-)
target_compile_options(csl_mpc03_b08_comparison_record PRIVATE /W4 /WX /permissive-)
else()
target_compile_options(csl_mpc03_robust_minimax_report PRIVATE -Wall -Wextra -Wpedantic -Werror)
target_compile_options(csl_mpc03_b08_comparison_record PRIVATE -Wall -Wextra -Wpedantic -Werror)
endif()
if(BUILD_TESTING)
find_package(Python3 3.11 REQUIRED COMPONENTS Interpreter)
add_test(NAME mpc03_report_smoke COMMAND Python3::Interpreter
  ${CMAKE_CURRENT_SOURCE_DIR}/scripts/reports/mpc03/check_smoke.py
  $<TARGET_FILE:csl_mpc03_robust_minimax_report>)
set_tests_properties(mpc03_report_smoke PROPERTIES LABELS reporting)
add_test(NAME mpc03_b08_comparison_record COMMAND Python3::Interpreter
  ${CMAKE_CURRENT_SOURCE_DIR}/scripts/reports/mpc03/check_b08_comparison_record.py
  $<TARGET_FILE:csl_mpc03_b08_comparison_record>
  ${CMAKE_CURRENT_SOURCE_DIR}/reports/algorithm-results/mpc03-b08-l04-miQCP-v1
  ${CMAKE_CURRENT_SOURCE_DIR}/reports/algorithm-results/mpc03-b08-l04-miQCP-comparison-v1)
set_tests_properties(mpc03_b08_comparison_record PROPERTIES LABELS reporting)
endif()
endif()

if(CSL_BUILD_ENV717_REPORT)
include(cmake/JsonDependencies.cmake)
file(GLOB_RECURSE ENV717_LIBRARY_INPUTS CONFIGURE_DEPENDS
    ${CMAKE_CURRENT_SOURCE_DIR}/src/*.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/src/*.cc
    ${CMAKE_CURRENT_SOURCE_DIR}/src/*.cxx
    ${CMAKE_CURRENT_SOURCE_DIR}/src/*.h
    ${CMAKE_CURRENT_SOURCE_DIR}/src/*.hpp
    ${CMAKE_CURRENT_SOURCE_DIR}/src/*.hxx
    ${CMAKE_CURRENT_SOURCE_DIR}/include/*.h
    ${CMAKE_CURRENT_SOURCE_DIR}/include/*.hpp
    ${CMAKE_CURRENT_SOURCE_DIR}/include/*.hxx)
set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS
    ${CMAKE_CURRENT_SOURCE_DIR}/benchmarks/reporting/env717/simple_control.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/benchmarks/reporting/env717/two_points.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/benchmarks/reporting/env717/unequal_game.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/benchmarks/reporting/env717/max_coordinate.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/benchmarks/reporting/env717/air_to_air.cpp
    ${ENV717_LIBRARY_INPUTS})
file(SHA256 ${CMAKE_CURRENT_SOURCE_DIR}/benchmarks/reporting/env717/simple_control.cpp
    ENV717_DRIVER_SHA256)
file(SHA256 ${CMAKE_CURRENT_SOURCE_DIR}/benchmarks/reporting/env717/two_points.cpp
    ENV717_TWO_POINTS_DRIVER_SHA256)
file(SHA256 ${CMAKE_CURRENT_SOURCE_DIR}/benchmarks/reporting/env717/unequal_game.cpp
    ENV717_UNEQUAL_GAME_DRIVER_SHA256)
file(SHA256 ${CMAKE_CURRENT_SOURCE_DIR}/benchmarks/reporting/env717/max_coordinate.cpp
    ENV717_MAX_COORDINATE_DRIVER_SHA256)
file(SHA256 ${CMAKE_CURRENT_SOURCE_DIR}/benchmarks/reporting/env717/air_to_air.cpp
    ENV717_AIR_DRIVER_SHA256)
execute_process(COMMAND git status --porcelain -- src include
    WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}
    OUTPUT_VARIABLE ENV717_LIBRARY_DIRTY OUTPUT_STRIP_TRAILING_WHITESPACE
    COMMAND_ERROR_IS_FATAL ANY)
if(NOT ENV717_LIBRARY_DIRTY STREQUAL "")
    message(FATAL_ERROR "ENV717 measured library source tree is dirty: ${ENV717_LIBRARY_DIRTY}")
endif()
set(ENV717_ALGORITHM_HASHES "")
foreach(ENV717_SOURCE IN LISTS ENV717_LIBRARY_INPUTS)
    file(RELATIVE_PATH ENV717_SOURCE_RELATIVE ${CMAKE_CURRENT_SOURCE_DIR} ${ENV717_SOURCE})
    file(SHA256 ${ENV717_SOURCE} ENV717_ALGORITHM_SHA256)
    string(APPEND ENV717_ALGORITHM_HASHES
        "${ENV717_SOURCE_RELATIVE}:${ENV717_ALGORITHM_SHA256}\n")
endforeach()
string(SHA256 ENV717_ALGORITHM_SOURCE_SHA256 "${ENV717_ALGORITHM_HASHES}")
execute_process(COMMAND git rev-parse HEAD WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}
    OUTPUT_VARIABLE ENV717_SOURCE_COMMIT OUTPUT_STRIP_TRAILING_WHITESPACE COMMAND_ERROR_IS_FATAL ANY)
add_executable(csl_env717_simple_control benchmarks/reporting/env717/simple_control.cpp)
add_executable(csl_env717_two_points benchmarks/reporting/env717/two_points.cpp)
add_executable(csl_env717_unequal_game benchmarks/reporting/env717/unequal_game.cpp)
add_executable(csl_env717_max_coordinate benchmarks/reporting/env717/max_coordinate.cpp)
add_executable(csl_env717_air_to_air benchmarks/reporting/env717/air_to_air.cpp)
target_link_libraries(csl_env717_simple_control PRIVATE CSL::finite_action_minimax)
target_link_libraries(csl_env717_two_points PRIVATE CSL::finite_action_minimax CSL::finite_feedback)
target_link_libraries(csl_env717_unequal_game PRIVATE CSL::finite_action_minimax)
target_link_libraries(csl_env717_max_coordinate PRIVATE CSL::finite_action_minimax)
target_link_libraries(csl_env717_air_to_air PRIVATE CSL::finite_action_minimax)
target_include_directories(csl_env717_simple_control SYSTEM PRIVATE ${csl_json_SOURCE_DIR}/include)
target_include_directories(csl_env717_two_points SYSTEM PRIVATE ${csl_json_SOURCE_DIR}/include)
target_include_directories(csl_env717_unequal_game SYSTEM PRIVATE ${csl_json_SOURCE_DIR}/include)
target_include_directories(csl_env717_max_coordinate SYSTEM PRIVATE ${csl_json_SOURCE_DIR}/include)
target_include_directories(csl_env717_air_to_air SYSTEM PRIVATE ${csl_json_SOURCE_DIR}/include)
target_compile_features(csl_env717_simple_control PRIVATE cxx_std_20)
target_compile_features(csl_env717_two_points PRIVATE cxx_std_20)
target_compile_features(csl_env717_unequal_game PRIVATE cxx_std_20)
target_compile_features(csl_env717_max_coordinate PRIVATE cxx_std_20)
target_compile_features(csl_env717_air_to_air PRIVATE cxx_std_20)
target_compile_definitions(csl_env717_simple_control PRIVATE
    $<$<CONFIG:Release>:NDEBUG>
    CSL_ENV717_DRIVER_SHA256="${ENV717_DRIVER_SHA256}"
    CSL_ENV717_SOURCE_COMMIT="${ENV717_SOURCE_COMMIT}"
    CSL_ENV717_COMPILER_ID="${CMAKE_CXX_COMPILER_ID}"
    CSL_ENV717_COMPILER_VERSION="${CMAKE_CXX_COMPILER_VERSION}"
    CSL_ENV717_BUILD_TYPE="${CMAKE_BUILD_TYPE}"
    CSL_ENV717_ARCHITECTURE="${CMAKE_SYSTEM_PROCESSOR}"
    CSL_ENV717_ALGORITHM_SOURCE_SHA256="${ENV717_ALGORITHM_SOURCE_SHA256}")
target_compile_definitions(csl_env717_two_points PRIVATE
    $<$<CONFIG:Release>:NDEBUG>
    CSL_ENV717_DRIVER_SHA256="${ENV717_TWO_POINTS_DRIVER_SHA256}"
    CSL_ENV717_COMPILER_ID="${CMAKE_CXX_COMPILER_ID}"
    CSL_ENV717_COMPILER_VERSION="${CMAKE_CXX_COMPILER_VERSION}"
    CSL_ENV717_BUILD_TYPE="${CMAKE_BUILD_TYPE}"
    CSL_ENV717_ARCHITECTURE="${CMAKE_SYSTEM_PROCESSOR}"
    CSL_ENV717_ALGORITHM_SOURCE_SHA256="${ENV717_ALGORITHM_SOURCE_SHA256}"
    CSL_ENV717_SOURCE_COMMIT="${ENV717_SOURCE_COMMIT}")
target_compile_definitions(csl_env717_unequal_game PRIVATE
    $<$<CONFIG:Release>:NDEBUG>
    CSL_ENV717_UNEQUAL_DRIVER_SHA256="${ENV717_UNEQUAL_GAME_DRIVER_SHA256}"
    CSL_ENV717_UNEQUAL_COMPILER_ID="${CMAKE_CXX_COMPILER_ID}"
    CSL_ENV717_UNEQUAL_COMPILER_VERSION="${CMAKE_CXX_COMPILER_VERSION}"
    CSL_ENV717_UNEQUAL_BUILD_TYPE="${CMAKE_BUILD_TYPE}"
    CSL_ENV717_UNEQUAL_ARCHITECTURE="${CMAKE_SYSTEM_PROCESSOR}"
    CSL_ENV717_UNEQUAL_ALGORITHM_SOURCE_SHA256="${ENV717_ALGORITHM_SOURCE_SHA256}"
    CSL_ENV717_UNEQUAL_SOURCE_COMMIT="${ENV717_SOURCE_COMMIT}")
target_compile_definitions(csl_env717_max_coordinate PRIVATE
    $<$<CONFIG:Release>:NDEBUG>
    CSL_ENV717_MAX_DRIVER_SHA256="${ENV717_MAX_COORDINATE_DRIVER_SHA256}"
    CSL_ENV717_MAX_COMPILER_ID="${CMAKE_CXX_COMPILER_ID}"
    CSL_ENV717_MAX_COMPILER_VERSION="${CMAKE_CXX_COMPILER_VERSION}"
    CSL_ENV717_MAX_BUILD_TYPE="${CMAKE_BUILD_TYPE}"
    CSL_ENV717_MAX_ARCHITECTURE="${CMAKE_SYSTEM_PROCESSOR}"
    CSL_ENV717_MAX_ALGORITHM_SOURCE_SHA256="${ENV717_ALGORITHM_SOURCE_SHA256}"
    CSL_ENV717_MAX_SOURCE_COMMIT="${ENV717_SOURCE_COMMIT}")
target_compile_definitions(csl_env717_air_to_air PRIVATE
    $<$<CONFIG:Release>:NDEBUG>
    CSL_ENV717_AIR_DRIVER_SHA256="${ENV717_AIR_DRIVER_SHA256}"
    CSL_ENV717_COMPILER_ID="${CMAKE_CXX_COMPILER_ID}"
    CSL_ENV717_COMPILER_VERSION="${CMAKE_CXX_COMPILER_VERSION}"
    CSL_ENV717_BUILD_TYPE="${CMAKE_BUILD_TYPE}"
    CSL_ENV717_ARCHITECTURE="${CMAKE_SYSTEM_PROCESSOR}"
    CSL_ENV717_ALGORITHM_SOURCE_SHA256="${ENV717_ALGORITHM_SOURCE_SHA256}"
    CSL_ENV717_SOURCE_COMMIT="${ENV717_SOURCE_COMMIT}")
if(MSVC)
    target_compile_options(csl_env717_simple_control PRIVATE /W4 /WX /permissive-)
    target_compile_options(csl_env717_two_points PRIVATE /W4 /WX /permissive-)
    target_compile_options(csl_env717_unequal_game PRIVATE /W4 /WX /permissive-)
    target_compile_options(csl_env717_max_coordinate PRIVATE /W4 /WX /permissive-)
    target_compile_options(csl_env717_air_to_air PRIVATE /W4 /WX /permissive-)
else()
    target_compile_options(csl_env717_simple_control PRIVATE -Wall -Wextra -Wpedantic -Werror)
    target_compile_options(csl_env717_two_points PRIVATE -Wall -Wextra -Wpedantic -Werror)
    target_compile_options(csl_env717_unequal_game PRIVATE -Wall -Wextra -Wpedantic -Werror)
    target_compile_options(csl_env717_max_coordinate PRIVATE -Wall -Wextra -Wpedantic -Werror)
    target_compile_options(csl_env717_air_to_air PRIVATE -Wall -Wextra -Wpedantic -Werror)
endif()
if(BUILD_TESTING)
    find_package(Python3 3.11 REQUIRED COMPONENTS Interpreter)
    add_test(NAME env717_simple_control_smoke COMMAND Python3::Interpreter
        ${CMAKE_CURRENT_SOURCE_DIR}/scripts/reports/env717/check_smoke.py
        $<TARGET_FILE:csl_env717_simple_control>)
    set_tests_properties(env717_simple_control_smoke PROPERTIES LABELS reporting)
    add_test(NAME env717_two_points_smoke COMMAND Python3::Interpreter
        ${CMAKE_CURRENT_SOURCE_DIR}/scripts/reports/env717/check_two_points.py
        $<TARGET_FILE:csl_env717_two_points>)
    set_tests_properties(env717_two_points_smoke PROPERTIES LABELS reporting)
    add_test(NAME env717_unequal_game_smoke COMMAND Python3::Interpreter
        ${CMAKE_CURRENT_SOURCE_DIR}/scripts/reports/env717/check_unequal_game.py
        $<TARGET_FILE:csl_env717_unequal_game>)
    set_tests_properties(env717_unequal_game_smoke PROPERTIES LABELS reporting)
    add_test(NAME env717_max_coordinate_smoke COMMAND Python3::Interpreter
        ${CMAKE_CURRENT_SOURCE_DIR}/scripts/reports/env717/check_max_coordinate.py
        $<TARGET_FILE:csl_env717_max_coordinate>)
    set_tests_properties(env717_max_coordinate_smoke PROPERTIES LABELS reporting)
    add_test(NAME env717_air_to_air_smoke COMMAND Python3::Interpreter
        ${CMAKE_CURRENT_SOURCE_DIR}/scripts/reports/env717/check_air_to_air.py
        $<TARGET_FILE:csl_env717_air_to_air>)
    set_tests_properties(env717_air_to_air_smoke PROPERTIES LABELS reporting)
endif()
endif()

if(CSL_BUILD_ISSUE6_B06_REPORT)
include(cmake/JsonDependencies.cmake)
set(ISSUE6_B06_SCENARIO "${CMAKE_CURRENT_SOURCE_DIR}/benchmarks/scenarios/b06-owner-confirmed-disturbance-v1.json")
set(ISSUE6_B06_SCENARIO_HEADER_TEMPLATE "${CMAKE_CURRENT_SOURCE_DIR}/scripts/reports/issue6/b06_scenario.hpp.in")
set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS "${ISSUE6_B06_SCENARIO}" "${ISSUE6_B06_SCENARIO_HEADER_TEMPLATE}")
file(READ "${ISSUE6_B06_SCENARIO}" ISSUE6_B06_SCENARIO_CONTENT)
string(FIND "${ISSUE6_B06_SCENARIO_CONTENT}" ")CSL_B06_SCENARIO\"" ISSUE6_B06_RAW_STRING_END)
if(NOT ISSUE6_B06_RAW_STRING_END EQUAL -1)
  message(FATAL_ERROR "B06 scenario contains the generated C++ raw-string terminator")
endif()
file(MAKE_DIRECTORY "${CMAKE_CURRENT_BINARY_DIR}/generated")
configure_file("${ISSUE6_B06_SCENARIO_HEADER_TEMPLATE}"
    "${CMAKE_CURRENT_BINARY_DIR}/generated/issue6_b06_scenario.hpp" @ONLY)
file(SHA256 ${CMAKE_CURRENT_SOURCE_DIR}/benchmarks/reporting/issue6/b06_finite_minimax.cpp ISSUE6_B06_DRIVER_SHA256)
file(SHA256 ${CMAKE_CURRENT_SOURCE_DIR}/benchmarks/reporting/issue6/b06_phase_timing.cpp ISSUE6_B06_PHASE_DRIVER_SHA256)
file(SHA256 ${CMAKE_CURRENT_SOURCE_DIR}/benchmarks/reporting/issue6/b06_exact_oracle.cpp ISSUE6_B06_ORACLE_SHA256)
file(SHA256 ${ISSUE6_B06_SCENARIO} ISSUE6_B06_FIXTURE_SHA256)
execute_process(COMMAND git rev-parse HEAD WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}
    OUTPUT_VARIABLE ISSUE6_B06_SOURCE_COMMIT OUTPUT_STRIP_TRAILING_WHITESPACE COMMAND_ERROR_IS_FATAL ANY)
add_executable(csl_issue6_b06_report benchmarks/reporting/issue6/b06_finite_minimax.cpp)
add_executable(csl_issue6_b06_phase_report benchmarks/reporting/issue6/b06_phase_timing.cpp)
add_executable(csl_issue6_b06_exact_oracle benchmarks/reporting/issue6/b06_exact_oracle.cpp)
target_link_libraries(csl_issue6_b06_report PRIVATE CSL::finite_action_minimax CSL::resolved_core)
target_link_libraries(csl_issue6_b06_phase_report PRIVATE CSL::finite_action_minimax CSL::resolved_core)
target_include_directories(csl_issue6_b06_report PRIVATE "${CMAKE_CURRENT_BINARY_DIR}/generated")
target_include_directories(csl_issue6_b06_report SYSTEM PRIVATE ${csl_json_SOURCE_DIR}/include)
target_include_directories(csl_issue6_b06_phase_report SYSTEM PRIVATE ${csl_json_SOURCE_DIR}/include)
target_include_directories(csl_issue6_b06_exact_oracle SYSTEM PRIVATE ${csl_json_SOURCE_DIR}/include)
target_compile_features(csl_issue6_b06_report PRIVATE cxx_std_20)
target_compile_features(csl_issue6_b06_phase_report PRIVATE cxx_std_20)
target_compile_features(csl_issue6_b06_exact_oracle PRIVATE cxx_std_20)
target_compile_definitions(csl_issue6_b06_report PRIVATE
    $<$<CONFIG:Release>:NDEBUG>
    CSL_ISSUE6_SOURCE_COMMIT="${ISSUE6_B06_SOURCE_COMMIT}"
    CSL_ISSUE6_FIXTURE_SHA256="${ISSUE6_B06_FIXTURE_SHA256}"
    CSL_ISSUE6_DRIVER_SHA256="${ISSUE6_B06_DRIVER_SHA256}")
target_compile_definitions(csl_issue6_b06_phase_report PRIVATE
    $<$<CONFIG:Release>:NDEBUG>
    CSL_ISSUE6_SOURCE_COMMIT="${ISSUE6_B06_SOURCE_COMMIT}"
    CSL_ISSUE6_FIXTURE_SHA256="${ISSUE6_B06_FIXTURE_SHA256}"
    CSL_ISSUE6_DRIVER_SHA256="${ISSUE6_B06_PHASE_DRIVER_SHA256}")
target_compile_definitions(csl_issue6_b06_exact_oracle PRIVATE
    CSL_ISSUE6_SOURCE_COMMIT="${ISSUE6_B06_SOURCE_COMMIT}"
    CSL_ISSUE6_FIXTURE_SHA256="${ISSUE6_B06_FIXTURE_SHA256}"
    CSL_ISSUE6_ORACLE_SHA256="${ISSUE6_B06_ORACLE_SHA256}")
if(MSVC)
target_compile_options(csl_issue6_b06_report PRIVATE /W4 /WX /permissive-)
target_compile_options(csl_issue6_b06_phase_report PRIVATE /W4 /WX /permissive-)
target_compile_options(csl_issue6_b06_exact_oracle PRIVATE /W4 /WX /permissive-)
else()
target_compile_options(csl_issue6_b06_report PRIVATE -Wall -Wextra -Wpedantic -Werror)
target_compile_options(csl_issue6_b06_phase_report PRIVATE -Wall -Wextra -Wpedantic -Werror)
target_compile_options(csl_issue6_b06_exact_oracle PRIVATE -Wall -Wextra -Wpedantic -Werror)
endif()
if(BUILD_TESTING)
find_package(Python3 3.11 REQUIRED COMPONENTS Interpreter)
add_test(NAME issue6_b06_scenario_validation COMMAND Python3::Interpreter
    ${CMAKE_CURRENT_SOURCE_DIR}/tests/reporting/check_issue6_b06_runner.py
    $<TARGET_FILE:csl_issue6_b06_report> "${ISSUE6_B06_SCENARIO}")
set_tests_properties(issue6_b06_scenario_validation PROPERTIES LABELS reporting)
endif()
endif()

if(CSL_BUILD_ISSUE6_B07_REPORT)
include(cmake/JsonDependencies.cmake)
file(SHA256 ${CMAKE_CURRENT_SOURCE_DIR}/benchmarks/reporting/issue6/b07_reconstruction.cpp ISSUE6_B07_DRIVER_SHA256)
file(SHA256 ${CMAKE_CURRENT_SOURCE_DIR}/benchmarks/scenarios/b07-owner-approved-eight-case-v1.json ISSUE6_B07_SCENARIO_SHA256)
execute_process(COMMAND git rev-parse HEAD WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}
    OUTPUT_VARIABLE ISSUE6_B07_SOURCE_COMMIT OUTPUT_STRIP_TRAILING_WHITESPACE COMMAND_ERROR_IS_FATAL ANY)
add_executable(csl_issue6_b07_report benchmarks/reporting/issue6/b07_reconstruction.cpp)
target_link_libraries(csl_issue6_b07_report PRIVATE CSL::finite_action_minimax CSL::resolved_core)
target_include_directories(csl_issue6_b07_report SYSTEM PRIVATE ${csl_json_SOURCE_DIR}/include)
target_compile_features(csl_issue6_b07_report PRIVATE cxx_std_20)
target_compile_definitions(csl_issue6_b07_report PRIVATE
    $<$<CONFIG:Release>:NDEBUG>
    CSL_ISSUE6_B07_SOURCE_COMMIT="${ISSUE6_B07_SOURCE_COMMIT}"
    CSL_ISSUE6_B07_DRIVER_SHA256="${ISSUE6_B07_DRIVER_SHA256}"
    CSL_ISSUE6_B07_SCENARIO_SHA256="${ISSUE6_B07_SCENARIO_SHA256}"
    CSL_ISSUE6_B07_COMPILER_ID="${CMAKE_CXX_COMPILER_ID}"
    CSL_ISSUE6_B07_COMPILER_VERSION="${CMAKE_CXX_COMPILER_VERSION}"
    CSL_ISSUE6_B07_BUILD_TYPE="${CMAKE_BUILD_TYPE}")
if(MSVC)
target_compile_options(csl_issue6_b07_report PRIVATE /W4 /WX /permissive-)
else()
target_compile_options(csl_issue6_b07_report PRIVATE -Wall -Wextra -Wpedantic -Werror)
endif()
endif()

if(CSL_BUILD_ISSUE6_B09_REPORT)
include(cmake/JsonDependencies.cmake)
file(SHA256 ${CMAKE_CURRENT_SOURCE_DIR}/benchmarks/reporting/issue6/b09_a08_reference.cpp ISSUE6_B09_DRIVER_SHA256)
file(SHA256 ${CMAKE_CURRENT_SOURCE_DIR}/benchmarks/scenarios/b09-a08-source-revision-reference.json ISSUE6_B09_FIXTURE_SHA256)
execute_process(COMMAND git rev-parse HEAD WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}
    OUTPUT_VARIABLE ISSUE6_B09_SOURCE_COMMIT OUTPUT_STRIP_TRAILING_WHITESPACE COMMAND_ERROR_IS_FATAL ANY)
add_executable(csl_issue6_b09_report benchmarks/reporting/issue6/b09_a08_reference.cpp)
target_link_libraries(csl_issue6_b09_report PRIVATE CSL::finite_action_minimax CSL::resolved_core)
target_include_directories(csl_issue6_b09_report SYSTEM PRIVATE ${csl_json_SOURCE_DIR}/include)
target_compile_features(csl_issue6_b09_report PRIVATE cxx_std_20)
target_compile_definitions(csl_issue6_b09_report PRIVATE
    $<$<CONFIG:Release>:NDEBUG>
    CSL_ISSUE6_SOURCE_COMMIT="${ISSUE6_B09_SOURCE_COMMIT}"
    CSL_ISSUE6_FIXTURE_SHA256="${ISSUE6_B09_FIXTURE_SHA256}"
    CSL_ISSUE6_DRIVER_SHA256="${ISSUE6_B09_DRIVER_SHA256}")
if(MSVC)
target_compile_options(csl_issue6_b09_report PRIVATE /W4 /WX /permissive-)
else()
target_compile_options(csl_issue6_b09_report PRIVATE -Wall -Wextra -Wpedantic -Werror)
endif()
endif()

if(CSL_BUILD_FINITE_FEEDBACK_REPORT)
add_executable(csl_finite_feedback_report benchmarks/reporting/finite_feedback/driver.cpp)
target_link_libraries(csl_finite_feedback_report PRIVATE CSL::finite_feedback_port)
target_compile_features(csl_finite_feedback_report PRIVATE cxx_std_20)
target_compile_definitions(csl_finite_feedback_report PRIVATE $<$<CONFIG:Release>:NDEBUG>)
if(MSVC)
target_compile_options(csl_finite_feedback_report PRIVATE /W4 /WX /permissive-)
else()
target_compile_options(csl_finite_feedback_report PRIVATE -Wall -Wextra -Wpedantic -Werror)
endif()
if(BUILD_TESTING)
find_package(Python3 3.11 REQUIRED COMPONENTS Interpreter)
add_test(NAME finite_feedback_report_smoke COMMAND Python3::Interpreter
  ${CMAKE_CURRENT_SOURCE_DIR}/scripts/reports/finite_feedback/check_smoke.py
  $<TARGET_FILE:csl_finite_feedback_report>)
set_tests_properties(finite_feedback_report_smoke PROPERTIES LABELS reporting)
endif()
endif()

if(CSL_BUILD_EXT04_REPORT)
include(cmake/JsonDependencies.cmake)
add_executable(csl_ext04_observed_replay_report benchmarks/reporting/ext04/observed_replay_driver.cpp)
target_link_libraries(csl_ext04_observed_replay_report PRIVATE CSL::controllers)
target_include_directories(csl_ext04_observed_replay_report SYSTEM PRIVATE ${csl_json_SOURCE_DIR}/include)
target_compile_features(csl_ext04_observed_replay_report PRIVATE cxx_std_20)
target_compile_definitions(csl_ext04_observed_replay_report PRIVATE $<$<CONFIG:Release>:NDEBUG>)
if(MSVC)
target_compile_options(csl_ext04_observed_replay_report PRIVATE /W4 /WX /permissive-)
else()
target_compile_options(csl_ext04_observed_replay_report PRIVATE -Wall -Wextra -Wpedantic -Werror)
endif()
if(BUILD_TESTING)
find_package(Python3 3.11 REQUIRED COMPONENTS Interpreter)
add_test(NAME ext04_report_smoke COMMAND Python3::Interpreter
  ${CMAKE_CURRENT_SOURCE_DIR}/scripts/reports/ext04/check_smoke.py
  $<TARGET_FILE:csl_ext04_observed_replay_report>)
set_tests_properties(ext04_report_smoke PROPERTIES LABELS reporting)
endif()
endif()

if(CSL_BUILD_EXT04_CONTINUOUS_REPORT)
include(cmake/JsonDependencies.cmake)
add_executable(csl_ext04_continuous_policy_report benchmarks/reporting/ext04/continuous_policy_driver.cpp)
target_link_libraries(csl_ext04_continuous_policy_report PRIVATE CSL::controllers)
target_include_directories(csl_ext04_continuous_policy_report SYSTEM PRIVATE ${csl_json_SOURCE_DIR}/include)
target_compile_features(csl_ext04_continuous_policy_report PRIVATE cxx_std_20)
target_compile_definitions(csl_ext04_continuous_policy_report PRIVATE $<$<CONFIG:Release>:NDEBUG>)
if(MSVC)
target_compile_options(csl_ext04_continuous_policy_report PRIVATE /W4 /WX /permissive-)
else()
target_compile_options(csl_ext04_continuous_policy_report PRIVATE -Wall -Wextra -Wpedantic -Werror)
endif()
endif()

if(CSL_BUILD_EXT01_REPORT)
include(cmake/JsonDependencies.cmake)
add_executable(csl_ext01_fixed_plan_report benchmarks/reporting/ext01/fixed_plan_driver.cpp)
target_compile_features(csl_ext01_fixed_plan_report PRIVATE cxx_std_20)
target_compile_definitions(csl_ext01_fixed_plan_report PRIVATE $<$<CONFIG:Release>:NDEBUG>)
target_link_libraries(csl_ext01_fixed_plan_report PRIVATE CSL::fixed_plan_disturbance CSL::worst_case_vertex)
target_include_directories(csl_ext01_fixed_plan_report SYSTEM PRIVATE ${csl_json_SOURCE_DIR}/include)
if(BUILD_TESTING)
find_package(Python3 3.11 REQUIRED COMPONENTS Interpreter)
add_test(NAME ext01_report_smoke COMMAND Python3::Interpreter
  ${CMAKE_CURRENT_SOURCE_DIR}/scripts/reports/ext01/check_smoke.py
  $<TARGET_FILE:csl_ext01_fixed_plan_report>)
endif()
if(MSVC)
target_compile_options(csl_ext01_fixed_plan_report PRIVATE /W4 /WX /permissive-)
else()
target_compile_options(csl_ext01_fixed_plan_report PRIVATE -Wall -Wextra -Wpedantic -Werror)
endif()
endif()

if(CSL_BUILD_GEO03_REPORT)
add_executable(csl_geo03_conversion_report benchmarks/reporting/geo03/hv_conversion_driver.cpp)
target_link_libraries(csl_geo03_conversion_report PRIVATE CSL::qhull_conversion CSL::highs_lp)
endif()

if(CSL_BUILD_GEO04_REPORT)
add_executable(csl_geo04_intersection_report benchmarks/reporting/geo04/polyhedral_intersection_driver.cpp)
target_link_libraries(csl_geo04_intersection_report PRIVATE CSL::polyhedral CSL::qhull_conversion CSL::highs_lp)
endif()

if(CSL_BUILD_GEO05_REPORT)
include(cmake/JsonDependencies.cmake)
add_executable(csl_geo05_projection_predecessor_report benchmarks/reporting/geo05/projection_predecessor_driver.cpp)
target_link_libraries(csl_geo05_projection_predecessor_report PRIVATE CSL::polyhedral)
target_include_directories(csl_geo05_projection_predecessor_report SYSTEM PRIVATE ${csl_json_SOURCE_DIR}/include)
if(BUILD_TESTING)
add_executable(geo05_driver_outcome_tests benchmarks/reporting/geo05/test_driver_outcomes.cpp)
target_link_libraries(geo05_driver_outcome_tests PRIVATE CSL::polyhedral)
target_include_directories(geo05_driver_outcome_tests SYSTEM PRIVATE ${csl_json_SOURCE_DIR}/include)
add_test(NAME geo05_driver_outcome_tests COMMAND geo05_driver_outcome_tests)
endif()
endif()

if(CSL_BUILD_GEO06_REPORT)
add_executable(csl_geo06_quickhull_report benchmarks/reporting/geo06/quickhull_driver.cpp)
target_link_libraries(csl_geo06_quickhull_report PRIVATE CSL::quickhull_2d)
target_compile_features(csl_geo06_quickhull_report PRIVATE cxx_std_20)
target_compile_definitions(csl_geo06_quickhull_report PRIVATE $<$<CONFIG:Release>:NDEBUG>)
endif()

if(CSL_BUILD_IT17_HULL_REPORT)
if(NOT CSL_ENABLE_HIGHS)
  message(FATAL_ERROR "The ITIS17 hull comparison requires the production HiGHS LP adapter")
endif()
add_executable(csl_it17_hull_comparison_report
  benchmarks/reporting/it17_hull/preliminary_driver.cpp)
execute_process(COMMAND git rev-parse HEAD WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}
  OUTPUT_VARIABLE IT17_HULL_SOURCE_COMMIT OUTPUT_STRIP_TRAILING_WHITESPACE
  COMMAND_ERROR_IS_FATAL ANY)
target_link_libraries(csl_it17_hull_comparison_report PRIVATE
  CSL::hull CSL::quickhull_2d CSL::bounded_hull_checker CSL::highs_lp)
target_compile_features(csl_it17_hull_comparison_report PRIVATE cxx_std_20)
target_compile_definitions(csl_it17_hull_comparison_report PRIVATE
  $<$<CONFIG:Release>:NDEBUG> CSL_SOURCE_COMMIT="${IT17_HULL_SOURCE_COMMIT}")
csl_strict_warnings(csl_it17_hull_comparison_report)
endif()

if(CSL_BUILD_GEO07_PORT_REPORT)
include(cmake/JsonDependencies.cmake)
add_executable(csl_geo07_port_report benchmarks/reporting/geo07_port/adapter_driver.cpp)
target_link_libraries(csl_geo07_port_report PRIVATE CSL::generator_adapter)
target_include_directories(csl_geo07_port_report SYSTEM PRIVATE ${csl_json_SOURCE_DIR}/include)
target_compile_features(csl_geo07_port_report PRIVATE cxx_std_20)
target_compile_definitions(csl_geo07_port_report PRIVATE $<$<CONFIG:Release>:NDEBUG>)
if(MSVC)
target_compile_options(csl_geo07_port_report PRIVATE /W4 /WX /permissive-)
else()
target_compile_options(csl_geo07_port_report PRIVATE -Wall -Wextra -Wpedantic -Werror)
endif()

if(BUILD_TESTING)
find_package(Python3 3.11 REQUIRED COMPONENTS Interpreter)
add_test(NAME geo07_port_report_smoke COMMAND Python3::Interpreter
  ${CMAKE_CURRENT_SOURCE_DIR}/scripts/reports/geo07_port/check_smoke.py
  $<TARGET_FILE:csl_geo07_port_report>)
set_tests_properties(geo07_port_report_smoke PROPERTIES LABELS reporting)
endif()
endif()

if(CSL_BUILD_GEO07_DEPENDENT_REPORT)
include(cmake/JsonDependencies.cmake)
add_executable(csl_geo07_dependent_report benchmarks/reporting/geo07_dependent/driver.cpp)
target_link_libraries(csl_geo07_dependent_report PRIVATE CSL::generator_adapter)
target_include_directories(csl_geo07_dependent_report SYSTEM PRIVATE ${csl_json_SOURCE_DIR}/include)
target_compile_features(csl_geo07_dependent_report PRIVATE cxx_std_20)
target_compile_definitions(csl_geo07_dependent_report PRIVATE $<$<CONFIG:Release>:NDEBUG>)
if(MSVC)
target_compile_options(csl_geo07_dependent_report PRIVATE /W4 /WX /permissive-)
else()
target_compile_options(csl_geo07_dependent_report PRIVATE -Wall -Wextra -Wpedantic -Werror)
endif()
if(BUILD_TESTING)
find_package(Python3 3.11 REQUIRED COMPONENTS Interpreter)
add_test(NAME geo07_dependent_report_smoke COMMAND Python3::Interpreter
  ${CMAKE_CURRENT_SOURCE_DIR}/scripts/reports/geo07_dependent/check_smoke.py
  $<TARGET_FILE:csl_geo07_dependent_report>)
set_tests_properties(geo07_dependent_report_smoke PROPERTIES LABELS reporting)
endif()
endif()

if(CSL_BUILD_GEO07_REPORT)
include(cmake/JsonDependencies.cmake)
add_executable(csl_geo07_generator_report benchmarks/reporting/geo07/generator_driver.cpp)
target_link_libraries(csl_geo07_generator_report PRIVATE CSL::geometry_generators)
target_include_directories(csl_geo07_generator_report SYSTEM PRIVATE ${csl_json_SOURCE_DIR}/include)
target_compile_features(csl_geo07_generator_report PRIVATE cxx_std_20)
target_compile_definitions(csl_geo07_generator_report PRIVATE $<$<CONFIG:Release>:NDEBUG>)
if(MSVC)
target_compile_options(csl_geo07_generator_report PRIVATE /W4 /WX /permissive-)
else()
target_compile_options(csl_geo07_generator_report PRIVATE -Wall -Wextra -Wpedantic -Werror)
endif()
if(BUILD_TESTING)
find_package(Python3 3.11 REQUIRED COMPONENTS Interpreter)
add_test(NAME geo07_report_smoke COMMAND Python3::Interpreter
  ${CMAKE_CURRENT_SOURCE_DIR}/scripts/reports/geo07/check_smoke.py
  $<TARGET_FILE:csl_geo07_generator_report>)
set_tests_properties(geo07_report_smoke PROPERTIES LABELS reporting)
endif()
endif()

if(CSL_BUILD_GEO02_REPORT)
add_executable(csl_geo02_affine_sum_report benchmarks/reporting/geo02/affine_sum_driver.cpp)
target_compile_features(csl_geo02_affine_sum_report PRIVATE cxx_std_20)
target_link_libraries(csl_geo02_affine_sum_report PRIVATE CSL::affine_sum CSL::hull CSL::highs_lp CSL::qhull_conversion CSL::phase_one)
endif()

if(CSL_BUILD_OPT04_REPORT)
include(cmake/JsonDependencies.cmake)
add_executable(csl_opt04_phase_one_report benchmarks/reporting/opt04/phase_one_driver.cpp)
target_link_libraries(csl_opt04_phase_one_report PRIVATE CSL::phase_one CSL::highs_lp)
target_include_directories(csl_opt04_phase_one_report SYSTEM PRIVATE ${csl_json_SOURCE_DIR}/include)
target_compile_features(csl_opt04_phase_one_report PRIVATE cxx_std_20)
target_compile_definitions(csl_opt04_phase_one_report PRIVATE $<$<CONFIG:Release>:NDEBUG>)
if(BUILD_TESTING)
add_executable(opt04_driver_verification_tests benchmarks/reporting/opt04/test_driver_verification.cpp)
target_link_libraries(opt04_driver_verification_tests PRIVATE CSL::phase_one CSL::highs_lp)
target_include_directories(opt04_driver_verification_tests SYSTEM PRIVATE ${csl_json_SOURCE_DIR}/include)
target_compile_features(opt04_driver_verification_tests PRIVATE cxx_std_20)
add_test(NAME opt04_driver_verification_tests COMMAND opt04_driver_verification_tests)
endif()
endif()

if(CSL_BUILD_SYN01_REPORT)
include(cmake/JsonDependencies.cmake)
add_executable(csl_syn01_nominal_forward_report benchmarks/reporting/syn01/nominal_forward_driver.cpp)
target_compile_features(csl_syn01_nominal_forward_report PRIVATE cxx_std_20)
target_compile_definitions(csl_syn01_nominal_forward_report PRIVATE $<$<CONFIG:Release>:NDEBUG>)
target_include_directories(csl_syn01_nominal_forward_report SYSTEM PRIVATE ${csl_json_SOURCE_DIR}/single_include)
target_link_libraries(csl_syn01_nominal_forward_report PRIVATE CSL::nominal_forward CSL::affine_sum CSL::hull CSL::highs_lp CSL::qhull_conversion CSL::phase_one)
if(MSVC)
target_compile_options(csl_syn01_nominal_forward_report PRIVATE /W4 /WX /permissive-)
else()
target_compile_options(csl_syn01_nominal_forward_report PRIVATE -Wall -Wextra -Wpedantic -Werror)
endif()

endif()

if(CSL_BUILD_STAGE_PROJECTION_ROUTE)
include(cmake/JsonDependencies.cmake)
add_executable(csl_stage_projection_route benchmarks/reporting/stage-projection/nominal_forward_route.cpp)
target_compile_features(csl_stage_projection_route PRIVATE cxx_std_20)
target_include_directories(csl_stage_projection_route SYSTEM PRIVATE ${csl_json_SOURCE_DIR}/single_include)
target_link_libraries(csl_stage_projection_route PRIVATE CSL::nominal_forward CSL::affine_sum CSL::hull CSL::highs_lp CSL::qhull_conversion CSL::phase_one CSL::artifacts)
if(MSVC)
target_compile_options(csl_stage_projection_route PRIVATE /W4 /WX /permissive-)
else()
target_compile_options(csl_stage_projection_route PRIVATE -Wall -Wextra -Wpedantic -Werror)
endif()
if(BUILD_TESTING)
find_package(Python3 3.11 REQUIRED COMPONENTS Interpreter)
add_test(NAME stage_projection_nominal_forward_route
  COMMAND Python3::Interpreter
    ${CMAKE_CURRENT_SOURCE_DIR}/benchmarks/reporting/stage-projection/check_nominal_forward_route.py
    --route-executable $<TARGET_FILE:csl_stage_projection_route>)
set_tests_properties(stage_projection_nominal_forward_route PROPERTIES LABELS reporting)
endif()
endif()

if(CSL_BUILD_SYN06_REPORT)
add_executable(csl_syn06_verifier_report benchmarks/reporting/syn06/verifier_driver.cpp)
target_compile_features(csl_syn06_verifier_report PRIVATE cxx_std_20)
target_compile_definitions(csl_syn06_verifier_report PRIVATE $<$<CONFIG:Release>:NDEBUG>)
target_link_libraries(csl_syn06_verifier_report PRIVATE CSL::verification)
endif()

if(CSL_BUILD_APP01_REPORT)
add_executable(csl_app01_plan_report benchmarks/reporting/app01/plan_driver.cpp)
target_compile_features(csl_app01_plan_report PRIVATE cxx_std_20)
target_compile_definitions(csl_app01_plan_report PRIVATE $<$<CONFIG:Release>:NDEBUG>)
target_link_libraries(csl_app01_plan_report PRIVATE CSL::approximation)
if(MSVC)
target_compile_options(csl_app01_plan_report PRIVATE /W4 /WX /permissive-)
else()
target_compile_options(csl_app01_plan_report PRIVATE -Wall -Wextra -Wpedantic -Werror)
endif()
endif()

if(CSL_BUILD_SYN02_REPORT)
execute_process(COMMAND git rev-parse HEAD WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}
    OUTPUT_VARIABLE SYN02_HARNESS_COMMIT OUTPUT_STRIP_TRAILING_WHITESPACE COMMAND_ERROR_IS_FATAL ANY)
add_executable(csl_syn02_terminal_report benchmarks/reporting/syn02/terminal_driver.cpp)
target_compile_features(csl_syn02_terminal_report PRIVATE cxx_std_20)
target_compile_definitions(csl_syn02_terminal_report PRIVATE
    CSL_SYN02_SOURCE_COMMIT="c234a1a04b2f90e34776a2bfa349a91a1d30257d"
    CSL_SYN02_HARNESS_COMMIT="${SYN02_HARNESS_COMMIT}")
target_link_libraries(csl_syn02_terminal_report PRIVATE CSL::terminal_minimizers CSL::highs_lp CSL::highs_convex CSL::problem)
endif()

if(CSL_BUILD_SYN07_REPORT)
add_executable(csl_syn07_ts01_report benchmarks/reporting/ts01/ts01_measure.cpp)
target_compile_features(csl_syn07_ts01_report PRIVATE cxx_std_20)
target_compile_definitions(csl_syn07_ts01_report PRIVATE $<$<CONFIG:Release>:NDEBUG>)
target_link_libraries(csl_syn07_ts01_report PRIVATE CSL::strategy_ts01)
if(MSVC)
target_compile_options(csl_syn07_ts01_report PRIVATE /W4 /WX /permissive-)
else()
target_compile_options(csl_syn07_ts01_report PRIVATE -Wall -Wextra -Wpedantic -Werror)
endif()
endif()

if(CSL_BUILD_OBSERVABILITY_BENCHMARK)
add_executable(observability_overhead benchmarks/observability_overhead.cpp)
target_link_libraries(observability_overhead PRIVATE CSL::artifacts)
target_compile_definitions(observability_overhead PRIVATE $<$<CONFIG:Release>:NDEBUG>)
endif()
