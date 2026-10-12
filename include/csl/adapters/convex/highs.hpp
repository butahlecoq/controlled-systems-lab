#pragma once
#include <csl/optimization/convex_backend.hpp>
#include <csl/registry/registry.hpp>
namespace csl::adapters::convex {
// HiGHS 1.11.0 binary64 profile: at most 4096 variables, numerical evidence
// only, no basis/certificates/families. QP cancellation is cooperative between
// native phases; neither deadlines nor iteration limits preempt factorization.
struct HighsConvexOptions {
    std::optional<std::size_t> feasibility_iteration_limit;
    std::optional<std::size_t> qp_iteration_limit;
};
using HighsConvexRegistrationResult = std::variant<registry::Registration<registry::ConvexPort>,Diagnostics>;
HighsConvexRegistrationResult make_highs_registration(HighsConvexOptions = {});
}
