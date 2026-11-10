# Optional standalone example-layer consumer of the existing CSL replay module.
add_executable(csl_mpc11_nonlinear_replay nonlinear_replay_bridge.cpp)
target_link_libraries(csl_mpc11_nonlinear_replay PRIVATE CSL::simulation)
target_include_directories(csl_mpc11_nonlinear_replay SYSTEM PRIVATE ${csl_mpc11_json_source}/single_include)
target_compile_features(csl_mpc11_nonlinear_replay PRIVATE cxx_std_20)
if(NOT MSVC)
  target_compile_options(csl_mpc11_nonlinear_replay PRIVATE -Wall -Wextra -Wpedantic -Werror)
endif()
