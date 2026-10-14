if(NOT DEFINED UPSTREAM_HEADER OR NOT EXISTS "${UPSTREAM_HEADER}")
  message(FATAL_ERROR "Pinned HiGHS header is missing")
endif()
if(NOT DEFINED PATCH_SCRIPT OR NOT EXISTS "${PATCH_SCRIPT}")
  message(FATAL_ERROR "Pinned HiGHS patch script is missing")
endif()
if(NOT DEFINED WORK_DIR)
  message(FATAL_ERROR "WORK_DIR is required")
endif()

file(READ "${UPSTREAM_HEADER}" patched_source)
string(SHA256 upstream_sha "${patched_source}")
if(NOT upstream_sha STREQUAL "8ee92e023806826fded545e38d0598adacc7b08f07c395c557a1dbaa1733b00b")
  message(FATAL_ERROR "Expected the exact patched HiGHS header; got ${upstream_sha}")
endif()

# Reconstruct the pinned archive header and verify it before testing the patch
# applicator. Keeping this as a derived fixture avoids shipping a second copy
# of the upstream header.
string(REPLACE "  HighsInt size = 0;       //!< Dimension of the vector"
  "  HighsInt size;           //!< Dimension of the vector" original_source "${patched_source}")
string(REPLACE "  HighsInt count = 0;      //!< Number of nonzeros"
  "  HighsInt count;          //!< Number of nonzeros" original_source "${original_source}")
string(REPLACE "  double synthetic_tick = 0;  //!< Synthetic clock for operations with this vector"
  "  double synthetic_tick;  //!< Synthetic clock for operations with this vector" original_source "${original_source}")
string(REPLACE "  HVectorBase<Real>* next = nullptr;  //!< Allows vectors to be linked for PAMI"
  "  HVectorBase<Real>* next;  //!< Allows vectors to be linked for PAMI" original_source "${original_source}")
string(REPLACE "  bool packFlag = false;       //!< Flag to indicate whether to pack or not"
  "  bool packFlag;               //!< Flag to indicate whether to pack or not" original_source "${original_source}")
string(REPLACE "  HighsInt packCount = 0;      //!< Number of nonzeros packed"
  "  HighsInt packCount;          //!< Number of nonzeros packed" original_source "${original_source}")
string(SHA256 original_sha "${original_source}")
if(NOT original_sha STREQUAL "b45e2dc39671f42f772d742d5d287668d59a22c53f94b409402c1d4816a33aa3")
  message(FATAL_ERROR "Reconstructed upstream fixture has an unexpected hash: ${original_sha}")
endif()

file(REMOVE_RECURSE "${WORK_DIR}")
file(MAKE_DIRECTORY "${WORK_DIR}")
set(test_header "${WORK_DIR}/HVectorBase.h")
file(WRITE "${test_header}" "${original_source}")

execute_process(COMMAND "${CMAKE_COMMAND}" "-DSOURCE_FILE=${test_header}"
  -P "${PATCH_SCRIPT}" RESULT_VARIABLE first_result OUTPUT_VARIABLE first_output ERROR_VARIABLE first_error)
if(NOT first_result EQUAL 0)
  message(FATAL_ERROR "Initial patch application failed: ${first_output}${first_error}")
endif()
file(SHA256 "${test_header}" first_sha)
if(NOT first_sha STREQUAL "8ee92e023806826fded545e38d0598adacc7b08f07c395c557a1dbaa1733b00b")
  message(FATAL_ERROR "Patch application produced an unexpected hash: ${first_sha}")
endif()

execute_process(COMMAND "${CMAKE_COMMAND}" "-DSOURCE_FILE=${test_header}"
  -P "${PATCH_SCRIPT}" RESULT_VARIABLE repeat_result OUTPUT_VARIABLE repeat_output ERROR_VARIABLE repeat_error)
if(NOT repeat_result EQUAL 0)
  message(FATAL_ERROR "Idempotent patch application failed: ${repeat_output}${repeat_error}")
endif()
file(SHA256 "${test_header}" repeat_sha)
if(NOT repeat_sha STREQUAL first_sha)
  message(FATAL_ERROR "Repeated patch application changed the patched header: ${repeat_sha}")
endif()

file(APPEND "${test_header}" "\n// unexpected mutation\n")
file(SHA256 "${test_header}" tampered_sha)
execute_process(COMMAND "${CMAKE_COMMAND}" "-DSOURCE_FILE=${test_header}"
  -P "${PATCH_SCRIPT}" RESULT_VARIABLE tampered_result OUTPUT_VARIABLE tampered_output ERROR_VARIABLE tampered_error)
if(tampered_result EQUAL 0)
  message(FATAL_ERROR "Patch application accepted an unexpected source hash")
endif()
file(SHA256 "${test_header}" after_rejection_sha)
if(NOT after_rejection_sha STREQUAL tampered_sha)
  message(FATAL_ERROR "Patch rejection modified the unexpected source")
endif()
