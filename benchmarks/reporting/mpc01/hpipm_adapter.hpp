#pragma once

#include "problem_mapping.hpp"

namespace csl::mpc01 {

NativeAttempt solve_hpipm(const MpcCase&, const OcpQp&, const NativeAttempt* warm_start = nullptr);

} // namespace csl::mpc01
