#pragma once

namespace csl::synthesis::strategy_a {

// Numerical exact-family checks interpret every finite binary64 input as its
// exact dyadic value and apply the private bounded exact-H resource limits.
inline constexpr char nominal_linear_exact_profile[] =
    "strategy-a.nominal-linear-exact-v1";

} // namespace csl::synthesis::strategy_a
