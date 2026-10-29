#pragma once

#include "problem_mapping.hpp"

namespace csl::mpc01 {

NativeAttempt solve_osqp(const MpcCase&, const SparseQp&, const NativeAttempt* warm_start = nullptr);

} // namespace csl::mpc01
