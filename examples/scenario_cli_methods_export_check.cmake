if(NOT DEFINED SCENARIO_CLI OR NOT DEFINED SCENARIO_INPUT OR NOT DEFINED OUTPUT_DIRECTORY)
  message(FATAL_ERROR "Method export check requires executable, input, and output directory")
endif()

file(REMOVE_RECURSE "${OUTPUT_DIRECTORY}")
execute_process(
  COMMAND "${SCENARIO_CLI}" --run "${SCENARIO_INPUT}" --output-dir "${OUTPUT_DIRECTORY}"
  RESULT_VARIABLE status OUTPUT_VARIABLE output ERROR_VARIABLE error)
if(NOT "${status}" STREQUAL "0")
  message(FATAL_ERROR "Explicit method run/export failed (${status}): ${output}${error}")
endif()

set(path "${OUTPUT_DIRECTORY}/method-0-csl-synthesis-reach-back.run.json")
if(NOT EXISTS "${path}")
  message(FATAL_ERROR "Explicit method run did not publish ${path}: ${output}")
endif()
file(READ "${path}" artifact)
string(JSON schema GET "${artifact}" schema)
string(JSON state GET "${artifact}" recorded_state)
string(JSON source_hash GET "${artifact}" scenario_source source_sha256)
string(JSON source_schema GET "${artifact}" scenario_source schema)
string(JSON defaults_revision GET "${artifact}" scenario_source defaults_revision)
string(JSON defaults_length LENGTH "${artifact}" scenario_source defaults)
file(SHA256 "${SCENARIO_INPUT}" expected_source_hash)
string(JSON module_count LENGTH "${artifact}" configuration value modules)
if(NOT "${schema}" STREQUAL "csl.run-statistics/9" OR
   NOT "${state}" STREQUAL "unverified_recorded_data" OR
   NOT "${source_hash}" STREQUAL "${expected_source_hash}" OR
   NOT "${source_schema}" STREQUAL "csl.scenario/1" OR
   NOT "${defaults_revision}" STREQUAL "csl.scenario-defaults/1" OR
   defaults_length LESS 1)
  message(FATAL_ERROR "Explicit method record has unexpected schema/state: ${schema}/${state}")
endif()
set(strategy_found FALSE)
math(EXPR last_module "${module_count}-1")
foreach(index RANGE 0 ${last_module})
  string(JSON role GET "${artifact}" configuration value modules ${index} role)
  if("${role}" STREQUAL "strategy")
    string(JSON strategy GET "${artifact}" configuration value modules ${index} id)
    string(JSON version GET "${artifact}" configuration value modules ${index} version)
    if(NOT "${strategy}" STREQUAL "csl.synthesis.reach-back" OR
       NOT "${version}" STREQUAL "1")
      message(FATAL_ERROR "Requested strategy version was not preserved: ${strategy}@${version}")
    endif()
    set(strategy_found TRUE)
  endif()
endforeach()
if(NOT strategy_found)
  message(FATAL_ERROR "Explicit method record omitted its resolved strategy registration")
endif()
file(REMOVE_RECURSE "${OUTPUT_DIRECTORY}")
