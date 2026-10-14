if(NOT DEFINED SOURCE_FILE OR NOT EXISTS "${SOURCE_FILE}")
  message(FATAL_ERROR "Pinned HiGHS patch source file is missing")
endif()
if(WIN32)
  set(expected_postimage_sha256 "f0f4f4f4a4b33088c3b30e63bbe5796c7c2fd498600a7e2acc8002bc4e7eace3")
else()
  set(expected_postimage_sha256 "8ee92e023806826fded545e38d0598adacc7b08f07c395c557a1dbaa1733b00b")
endif()
file(READ "${SOURCE_FILE}" source)
file(SHA256 "${SOURCE_FILE}" source_sha256)
if(source_sha256 STREQUAL "b45e2dc39671f42f772d742d5d287668d59a22c53f94b409402c1d4816a33aa3")
  string(REPLACE "  HighsInt size;           //!< Dimension of the vector"
    "  HighsInt size = 0;       //!< Dimension of the vector" source "${source}")
  string(REPLACE "  HighsInt count;          //!< Number of nonzeros"
    "  HighsInt count = 0;      //!< Number of nonzeros" source "${source}")
  string(REPLACE "  double synthetic_tick;  //!< Synthetic clock for operations with this vector"
    "  double synthetic_tick = 0;  //!< Synthetic clock for operations with this vector" source "${source}")
  string(REPLACE "  HVectorBase<Real>* next;  //!< Allows vectors to be linked for PAMI"
    "  HVectorBase<Real>* next = nullptr;  //!< Allows vectors to be linked for PAMI" source "${source}")
  string(REPLACE "  bool packFlag;               //!< Flag to indicate whether to pack or not"
    "  bool packFlag = false;       //!< Flag to indicate whether to pack or not" source "${source}")
  string(REPLACE "  HighsInt packCount;          //!< Number of nonzeros packed"
    "  HighsInt packCount = 0;      //!< Number of nonzeros packed" source "${source}")
  foreach(required_line
      "HighsInt size = 0;"
      "HighsInt count = 0;"
      "double synthetic_tick = 0;"
      "HVectorBase<Real>* next = nullptr;"
      "bool packFlag = false;"
      "HighsInt packCount = 0;")
    string(FIND "${source}" "${required_line}" patched_line)
    if(patched_line EQUAL -1)
      message(FATAL_ERROR "Pinned HiGHS patch did not apply completely: ${required_line}")
    endif()
  endforeach()
  file(WRITE "${SOURCE_FILE}" "${source}")
  file(SHA256 "${SOURCE_FILE}" postimage_sha256)
  if(NOT postimage_sha256 STREQUAL expected_postimage_sha256)
    message(FATAL_ERROR "Pinned HiGHS patch produced an unexpected postimage: ${postimage_sha256}")
  endif()
elseif(source_sha256 STREQUAL expected_postimage_sha256)
  foreach(required_line
      "HighsInt size = 0;"
      "HighsInt count = 0;"
      "double synthetic_tick = 0;"
      "HVectorBase<Real>* next = nullptr;"
      "bool packFlag = false;"
      "HighsInt packCount = 0;")
    string(FIND "${source}" "${required_line}" patched_line)
    if(patched_line EQUAL -1)
      message(FATAL_ERROR "Pinned HiGHS patch hash/content mismatch: ${required_line}")
    endif()
  endforeach()
else()
  message(FATAL_ERROR "Pinned HiGHS HVectorBase.h has an unexpected hash or patch state: ${source_sha256}")
endif()
