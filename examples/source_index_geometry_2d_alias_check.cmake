execute_process(
  COMMAND "${EXAMPLE_EXE}" btulshor
  RESULT_VARIABLE legacy_result
  OUTPUT_VARIABLE legacy_output
  ERROR_VARIABLE legacy_error
)
if(NOT legacy_result EQUAL 0)
  message(FATAL_ERROR "legacy btulshor alias failed: ${legacy_error}")
endif()
string(REGEX REPLACE "elapsed_ns=[0-9]+" "elapsed_ns=0" legacy_normalized "${legacy_output}")

foreach(alias candidate-elimination candidate-elimination-hull-reducer legacy-source-index)
  execute_process(
    COMMAND "${EXAMPLE_EXE}" "${alias}"
    RESULT_VARIABLE alias_result
    OUTPUT_VARIABLE alias_output
    ERROR_VARIABLE alias_error
  )
  if(NOT alias_result EQUAL 0)
    message(FATAL_ERROR "${alias} alias failed: ${alias_error}")
  endif()
  if(NOT alias_output MATCHES "csl.hull.source.btulshor-kpabep")
    message(FATAL_ERROR "${alias} alias did not select the stable provider ID")
  endif()
  string(REGEX REPLACE "elapsed_ns=[0-9]+" "elapsed_ns=0" alias_normalized "${alias_output}")
  if(NOT alias_normalized STREQUAL legacy_normalized)
    message(FATAL_ERROR "${alias} alias changed behavior relative to btulshor")
  endif()
endforeach()

execute_process(
  COMMAND "${EXAMPLE_EXE}" --help
  RESULT_VARIABLE help_result
  OUTPUT_VARIABLE help_output
  ERROR_VARIABLE help_error
)
if(NOT help_result EQUAL 0 OR NOT help_output MATCHES "Candidate-elimination hull reducer")
  message(FATAL_ERROR "descriptive CLI help is missing: ${help_error}")
endif()
