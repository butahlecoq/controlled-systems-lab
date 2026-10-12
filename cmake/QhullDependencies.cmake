include(FetchContent)

# Private, pinned reentrant Qhull source. No Qhull header or application target is
# exposed through CSL's public include tree.
FetchContent_Declare(csl_qhull
  URL https://codeload.github.com/qhull/qhull/tar.gz/refs/tags/v8.0.2
  URL_HASH SHA256=8774e9a12c70b0180b95d6b0b563c5aa4bea8d5960c15e18ae3b6d2521d64f8b
  SOURCE_SUBDIR csl-no-build
  DOWNLOAD_EXTRACT_TIMESTAMP TRUE)
FetchContent_MakeAvailable(csl_qhull)
set(qhull_r ${csl_qhull_SOURCE_DIR}/src/libqhull_r)
add_library(csl_qhull_r STATIC
  ${qhull_r}/global_r.c ${qhull_r}/stat_r.c ${qhull_r}/geom2_r.c
  ${qhull_r}/poly2_r.c ${qhull_r}/merge_r.c ${qhull_r}/libqhull_r.c
  ${qhull_r}/geom_r.c ${qhull_r}/poly_r.c ${qhull_r}/qset_r.c
  ${qhull_r}/mem_r.c ${qhull_r}/random_r.c ${qhull_r}/usermem_r.c
  ${qhull_r}/userprintf_r.c ${qhull_r}/io_r.c ${qhull_r}/user_r.c
  ${qhull_r}/rboxlib_r.c ${qhull_r}/userprintf_rbox_r.c)
add_library(CSL::qhull_r ALIAS csl_qhull_r)
set_target_properties(csl_qhull_r PROPERTIES EXPORT_NAME qhull_r)
target_include_directories(csl_qhull_r SYSTEM PUBLIC
  $<BUILD_INTERFACE:${csl_qhull_SOURCE_DIR}/src>)
if(NOT MSVC)
  target_link_libraries(csl_qhull_r PUBLIC m)
endif()
install(TARGETS csl_qhull_r EXPORT CSLTargets ARCHIVE DESTINATION ${CMAKE_INSTALL_LIBDIR})
install(FILES ${csl_qhull_SOURCE_DIR}/COPYING.txt
  DESTINATION ${CMAKE_INSTALL_DATADIR}/CSL/notices/Qhull-8.0.2)
