#pragma once

#include <csl/registry/registry.hpp>

namespace csl::adapters::lp {
struct HighsLPOptions {
    std::optional<std::size_t> simplex_iteration_limit;
};
using HighsLPRegistrationResult =
    std::variant<registry::Registration<registry::LPPort>, Diagnostics>;
HighsLPRegistrationResult make_highs_registration(HighsLPOptions = {});
} // namespace csl::adapters::lp
