include_guard(GLOBAL)

set(CSL_DEPENDENCY_ARCHIVE_CACHE "" CACHE PATH
  "Optional absolute directory for verified dependency archives; empty keeps direct downloads")

# Cache raw, pinned bytes only. FetchContent still extracts each dependency into
# its own build tree and verifies URL_HASH, including under CMP0168 NEW.
function(csl_dependency_archive_url output name remote_url sha256)
  if(NOT CSL_DEPENDENCY_ARCHIVE_CACHE)
    set(${output} "${remote_url}" PARENT_SCOPE)
    return()
  endif()
  if(NOT IS_ABSOLUTE "${CSL_DEPENDENCY_ARCHIVE_CACHE}")
    message(FATAL_ERROR "CSL_DEPENDENCY_ARCHIVE_CACHE must be an absolute path")
  endif()
  file(MAKE_DIRECTORY "${CSL_DEPENDENCY_ARCHIVE_CACHE}")
  set(archive "${CSL_DEPENDENCY_ARCHIVE_CACHE}/${name}-${sha256}.tar.gz")
  # Multiple local configure processes may intentionally share these immutable
  # hash-addressed bytes. Serialize only their publication, never build trees.
  file(LOCK "${archive}.lock" GUARD FUNCTION TIMEOUT 120)
  if(EXISTS "${archive}")
    file(SHA256 "${archive}" actual_sha256)
    if(actual_sha256 STREQUAL sha256)
      message(STATUS "CSL archive cache hit: ${name} ${sha256}")
      set(${output} "${archive}" PARENT_SCOPE)
      return()
    endif()
    message(STATUS "CSL archive cache rejected corrupt bytes: ${name}")
  endif()
  message(STATUS "CSL archive cache miss: ${name} ${sha256}")
  set(temporary "${archive}.download")
  file(DOWNLOAD "${remote_url}" "${temporary}"
    EXPECTED_HASH "SHA256=${sha256}" TLS_VERIFY ON STATUS download_status)
  list(GET download_status 0 download_result)
  if(NOT download_result EQUAL 0)
    file(REMOVE "${temporary}")
    message(FATAL_ERROR "Verified dependency download failed for ${name}: ${download_status}")
  endif()
  file(RENAME "${temporary}" "${archive}")
  set(${output} "${archive}" PARENT_SCOPE)
endfunction()
