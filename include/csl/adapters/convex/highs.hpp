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
using HighsConvexRegistrationResult =
    std::variant<registry::Registration<registry::ConvexPort>, Diagnostics>;
HighsConvexRegistrationResult make_highs_registration(HighsConvexOptions = {});
// Registers csl.convex.highs.row-scaled. Only rows with nonzero coefficients
// at or below the native drop threshold are scaled. Their finite bounds and
// coefficients must round-trip exactly, with a shift of at most 20 and a
// scaled magnitude of at most 2^20. Evidence uses original program units.
HighsConvexRegistrationResult make_highs_row_scaled_registration(HighsConvexOptions = {});
}
