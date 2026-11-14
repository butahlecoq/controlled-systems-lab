# A separate translation unit per contract prevents umbrella/include-order masking.
# Compile each physically installed public header independently. The imported
# target supplies its real include root; no repository include path is added.
get_target_property(csl_installed_include_roots CSL::contracts INTERFACE_INCLUDE_DIRECTORIES)
set(installed_contract_headers)
foreach(include_root IN LISTS csl_installed_include_roots)
  if(IS_ABSOLUTE "${include_root}" AND IS_DIRECTORY "${include_root}/csl")
    file(GLOB_RECURSE headers CONFIGURE_DEPENDS LIST_DIRECTORIES false
      RELATIVE "${include_root}/csl" "${include_root}/csl/*.hpp" "${include_root}/csl/*.h"
      "${include_root}/csl/*.hxx")
    list(APPEND installed_contract_headers ${headers})
  endif()
endforeach()
list(SORT installed_contract_headers)
list(REMOVE_DUPLICATES installed_contract_headers)
if(NOT installed_contract_headers)
  message(FATAL_ERROR "No installed public CSL headers found")
endif()
set(csl_installed_header_contexts "{}")
foreach(header IN LISTS installed_contract_headers)
  string(MAKE_C_IDENTIFIER "${header}" header_name)
  set(source "${CMAKE_CURRENT_BINARY_DIR}/header-checks/${header_name}.cpp")
  file(GENERATE OUTPUT "${source}" CONTENT "#include <csl/${header}>\n")
  add_library(installed_header_${header_name} OBJECT "${source}")
  target_link_libraries(installed_header_${header_name} PRIVATE CSL::contracts)
  set_target_properties(installed_header_${header_name} PROPERTIES CXX_EXTENSIONS OFF)
  string(JSON csl_installed_header_contexts SET "${csl_installed_header_contexts}"
    "${source}" "\"include/csl/${header}\"")
endforeach()
file(GENERATE OUTPUT "${CMAKE_CURRENT_BINARY_DIR}/cpp-quality-installed-headers.json"
  CONTENT "${csl_installed_header_contexts}\n")
