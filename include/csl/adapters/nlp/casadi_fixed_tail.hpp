#pragma once
#include <csl/reachability/fixed_tail_policy.hpp>

namespace csl::adapters::nlp {
// Optional native C++ CasADi/IPOPT adapter; no Python process participates.
registry::Registration<registry::FixedTailOptimizerPort> make_casadi_fixed_tail_registration();
} // namespace csl::adapters::nlp
