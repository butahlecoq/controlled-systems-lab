find_package(casadi CONFIG REQUIRED)
include(CheckCXXSourceCompiles)

# A private imported target can otherwise change only the adapter's C++ ABI.
# The adapter exchanges CSL string-bearing values with the rest of the library.
set(csl_casadi_saved_required_libraries "${CMAKE_REQUIRED_LIBRARIES}")
set(csl_casadi_abi_probe "#include <string>
#if defined(__GLIBCXX__) && _GLIBCXX_USE_CXX11_ABI != 1
#error old_libstdcxx_abi
#endif
int main() { return 0; }")
unset(CSL_CORE_USES_NEW_CXX_ABI CACHE)
unset(CSL_CASADI_USES_NEW_CXX_ABI CACHE)
unset(CSL_CASADI_CPP_LINKS CACHE)
check_cxx_source_compiles("${csl_casadi_abi_probe}" CSL_CORE_USES_NEW_CXX_ABI)
set(CMAKE_REQUIRED_LIBRARIES casadi::casadi)
check_cxx_source_compiles("${csl_casadi_abi_probe}" CSL_CASADI_USES_NEW_CXX_ABI)
if(NOT "${CSL_CORE_USES_NEW_CXX_ABI}" STREQUAL "${CSL_CASADI_USES_NEW_CXX_ABI}")
  message(FATAL_ERROR "CasADi's imported target changes the CSL C++ ABI. Use a CasADi build matching the core toolchain; CSL does not silently change its ABI.")
endif()
check_cxx_source_compiles("#include <casadi/casadi.hpp>
int main() { casadi::Opti opti(std::string(\"nlp\")); return static_cast<int>(opti.nx()); }"
  CSL_CASADI_CPP_LINKS)
if(NOT CSL_CASADI_CPP_LINKS)
  message(FATAL_ERROR "CasADi C++ headers and native library do not link with this CSL toolchain/ABI.")
endif()
set(CMAKE_REQUIRED_LIBRARIES "${csl_casadi_saved_required_libraries}")
