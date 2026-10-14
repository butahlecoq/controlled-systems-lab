function(csl_strict_warnings target)
  if(MSVC)
    target_compile_options(${target} PRIVATE /W4 /WX /permissive-)
  else()
    target_compile_options(${target} PRIVATE -Wall -Wextra -Wpedantic -Werror)
  endif()
endfunction()

# Shared mechanics only. Module.cmake/Tests.cmake own membership and dependencies.
function(csl_target_policy target)
  target_compile_features(${target} PUBLIC cxx_std_20)
  target_include_directories(${target} PUBLIC
    $<BUILD_INTERFACE:${PROJECT_SOURCE_DIR}/include>
    $<INSTALL_INTERFACE:${CMAKE_INSTALL_INCLUDEDIR}>)
  set_target_properties(${target} PROPERTIES CXX_EXTENSIONS OFF)
  csl_strict_warnings(${target})
endfunction()

function(csl_add_library target)
  add_library(${target} ${ARGN})
  string(REGEX REPLACE "^csl_" "" name "${target}")
  add_library(CSL::${name} ALIAS ${target})
  set_target_properties(${target} PROPERTIES EXPORT_NAME ${name})
  csl_target_policy(${target})
  install(TARGETS ${target} EXPORT CSLTargets ARCHIVE DESTINATION ${CMAKE_INSTALL_LIBDIR})
endfunction()

function(csl_install_headers domain)
  install(DIRECTORY "${PROJECT_SOURCE_DIR}/include/csl/${domain}/"
    DESTINATION "${CMAKE_INSTALL_INCLUDEDIR}/csl/${domain}" FILES_MATCHING PATTERN "*.hpp")
endfunction()

function(csl_test_target target domain)
  # Keep tests as consumers of the owning module; no product include paths here.
  target_compile_features(${target} PRIVATE cxx_std_20)
  set_target_properties(${target} PROPERTIES CXX_EXTENSIONS OFF)
  set_tests_properties(${target} PROPERTIES LABELS ${domain})
  if(NOT TARGET csl_${domain}_checks)
    add_custom_target(csl_${domain}_checks)
  endif()
  add_dependencies(csl_${domain}_checks ${target})
endfunction()
