cmake_minimum_required(VERSION 3.24)
project(CSLMPC01NativeDependencies LANGUAGES C)

include(FetchContent)
include(GNUInstallDirs)

set(BUILD_SHARED_LIBS OFF CACHE BOOL "Build static native solver libraries" FORCE)
set(TARGET GENERIC CACHE STRING "Portable BLASFEO/HPIPM target" FORCE)
set(LA HIGH_PERFORMANCE CACHE STRING "Use BLASFEO high-performance backend" FORCE)
set(HPIPM_TESTING OFF CACHE BOOL "Do not build upstream tests" FORCE)
set(HPIPM_FIND_BLASFEO OFF CACHE BOOL "Use the directly built BLASFEO target" FORCE)

FetchContent_Declare(csl_mpc01_blasfeo
  URL https://codeload.github.com/giaf/blasfeo/tar.gz/d6251233923c9b475fe894fb729fb63ab693e301
  URL_HASH SHA256=d2454027985a907f6fedb0c6a14e0e7825e586968309b38f7f02146db70770da)
FetchContent_MakeAvailable(csl_mpc01_blasfeo)

set(BLASFEO_PATH "${csl_mpc01_blasfeo_SOURCE_DIR}" CACHE PATH "Pinned BLASFEO source" FORCE)
set(BLASFEO_INCLUDE_DIR "${csl_mpc01_blasfeo_SOURCE_DIR}/include" CACHE PATH "Pinned BLASFEO headers" FORCE)
FetchContent_Declare(csl_mpc01_hpipm
  URL https://codeload.github.com/giaf/hpipm/tar.gz/e3a56c1caddd7f12d125d84f337b9a9e5c186271
  URL_HASH SHA256=97278f7c10a72387c574488701a1e85626df7f3fa3aea190ba41d1368a83aa4b)
FetchContent_MakeAvailable(csl_mpc01_hpipm)

set(OSQP_BUILD_SHARED_LIB OFF CACHE BOOL "Build only static OSQP" FORCE)
set(OSQP_BUILD_STATIC_LIB ON CACHE BOOL "Build static OSQP" FORCE)
set(OSQP_BUILD_DEMO_EXE OFF CACHE BOOL "Do not build upstream demos" FORCE)
set(OSQP_BUILD_UNITTESTS OFF CACHE BOOL "Do not build upstream tests" FORCE)
set(OSQP_VERSION "1.0.0" CACHE STRING "Pinned OSQP version" FORCE)
set(OSQP_ENABLE_PRINTING OFF CACHE BOOL "Disable solver progress output" FORCE)
set(OSQP_ENABLE_PROFILING ON CACHE BOOL "Retain OSQP phase timing" FORCE)
set(OSQP_CODEGEN OFF CACHE BOOL "Disable unused code generation" FORCE)
set(OSQP_ENABLE_DERIVATIVES OFF CACHE BOOL "Disable unused derivatives" FORCE)
FetchContent_Declare(csl_mpc01_osqp
  URL https://codeload.github.com/osqp/osqp/tar.gz/refs/tags/v1.0.0
  URL_HASH SHA256=dd6a1c2e7e921485697d5e7cdeeb043c712526c395b3700601f51d472a7d8e48)
FetchContent_MakeAvailable(csl_mpc01_osqp)

add_custom_target(mpc01_native_bundle DEPENDS blasfeo hpipm osqpstatic)
