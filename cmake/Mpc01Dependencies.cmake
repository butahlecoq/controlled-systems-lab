include(ExternalProject)

set(mpc01_native_install "${PROJECT_BINARY_DIR}/mpc01-native-install")
file(MAKE_DIRECTORY
  "${mpc01_native_install}/${CMAKE_INSTALL_INCLUDEDIR}"
  "${mpc01_native_install}/${CMAKE_INSTALL_INCLUDEDIR}/osqp")
ExternalProject_Add(csl_mpc01_native_dependencies
  SOURCE_DIR "${PROJECT_SOURCE_DIR}/benchmarks/reporting/mpc01/native"
  BINARY_DIR "${PROJECT_BINARY_DIR}/mpc01-native-build"
  INSTALL_DIR "${mpc01_native_install}"
  CMAKE_ARGS
    -DCMAKE_BUILD_TYPE=${CMAKE_BUILD_TYPE}
    -DCMAKE_INSTALL_PREFIX=<INSTALL_DIR>
    -DCMAKE_INSTALL_LIBDIR=${CMAKE_INSTALL_LIBDIR}
    -DCMAKE_INSTALL_INCLUDEDIR=${CMAKE_INSTALL_INCLUDEDIR}
    -DCMAKE_C_COMPILER=${CMAKE_C_COMPILER}
    -DCMAKE_CXX_COMPILER=${CMAKE_CXX_COMPILER}
    -DCMAKE_POSITION_INDEPENDENT_CODE=ON
  BUILD_COMMAND ${CMAKE_COMMAND} --build <BINARY_DIR> --config $<CONFIG> --target mpc01_native_bundle --parallel 4
  INSTALL_COMMAND ${CMAKE_COMMAND} --install <BINARY_DIR> --config $<CONFIG> --prefix <INSTALL_DIR>)

if(WIN32)
  set(mpc01_static_suffix ".lib")
else()
  set(mpc01_static_suffix ".a")
endif()

add_library(csl_mpc01_osqp STATIC IMPORTED GLOBAL)
set_target_properties(csl_mpc01_osqp PROPERTIES
  IMPORTED_LOCATION "${mpc01_native_install}/${CMAKE_INSTALL_LIBDIR}/${CMAKE_STATIC_LIBRARY_PREFIX}osqpstatic${mpc01_static_suffix}"
  INTERFACE_INCLUDE_DIRECTORIES "${mpc01_native_install}/${CMAKE_INSTALL_INCLUDEDIR}/osqp")

add_library(csl_mpc01_hpipm STATIC IMPORTED GLOBAL)
set_target_properties(csl_mpc01_hpipm PROPERTIES
  IMPORTED_LOCATION "${mpc01_native_install}/${CMAKE_INSTALL_LIBDIR}/${CMAKE_STATIC_LIBRARY_PREFIX}hpipm${mpc01_static_suffix}"
  INTERFACE_INCLUDE_DIRECTORIES "${mpc01_native_install}/${CMAKE_INSTALL_INCLUDEDIR}")

add_library(csl_mpc01_blasfeo STATIC IMPORTED GLOBAL)
set_target_properties(csl_mpc01_blasfeo PROPERTIES
  IMPORTED_LOCATION "${mpc01_native_install}/${CMAKE_INSTALL_LIBDIR}/${CMAKE_STATIC_LIBRARY_PREFIX}blasfeo${mpc01_static_suffix}"
  INTERFACE_INCLUDE_DIRECTORIES "${mpc01_native_install}/${CMAKE_INSTALL_INCLUDEDIR}")
set_property(TARGET csl_mpc01_hpipm APPEND PROPERTY INTERFACE_LINK_LIBRARIES csl_mpc01_blasfeo)

if(UNIX)
  set_property(TARGET csl_mpc01_hpipm APPEND PROPERTY INTERFACE_LINK_LIBRARIES m)
  set_property(TARGET csl_mpc01_blasfeo APPEND PROPERTY INTERFACE_LINK_LIBRARIES m)
  set_property(TARGET csl_mpc01_osqp APPEND PROPERTY INTERFACE_LINK_LIBRARIES m)
endif()
