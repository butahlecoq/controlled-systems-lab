#pragma once

#include <csl/core/diagnostics.hpp>
#include <csl/core/values.hpp>
#include <csl/registry/provider.hpp>
#include <variant>

namespace csl::reachability {

// The queried set is {x : inequalities*x <= upper_bounds,
// equalities*x = equality_values, lower <= x <= upper}. The finite carrier
// is part of this intersection; it is not an assumption about another set.
struct BoundedHSupportInput {
    Matrix inequalities;
    Vector upper_bounds;
    Matrix equalities;
    Vector equality_values;
    Vector lower, upper, direction;
};

enum class SupportBoundMethod { dual_candidate, carrier_only };
struct SupportUpperBound {
    double value;
    SupportBoundMethod method{SupportBoundMethod::dual_candidate};
    Vector inequality_multipliers, equality_multipliers;
    // Bound applies to the computed H intersection and binary64 inputs only.
};

// Any nonnegative inequality multipliers and unrestricted equality multipliers
// provide a bound after the dual residual is maximized over the carrier.
// Arithmetic is rounded outward; no optimality or nonemptiness is inferred.
std::variant<SupportUpperBound, Diagnostics>
residual_corrected_support(const BoundedHSupportInput &, const Vector &inequality_multipliers,
                           const Vector &equality_multipliers);

struct BoundedHSupportResult {
    SupportUpperBound bound;
    std::vector<registry::LPQueryRecord> lp_calls;
};
struct BoundedHSupportFailure {
    std::variant<Diagnostics, Unsupported, OperationStopped> cause;
    std::vector<registry::LPQueryRecord> lp_calls;
};
using BoundedHSupportOutcome = std::variant<BoundedHSupportResult, BoundedHSupportFailure>;

// Solves a dual candidate as a separate registered LP, then independently
// corrects its residual over the explicit carrier. LP records identify that
// actual solve; the backend is not assumed to return dual multipliers.
BoundedHSupportOutcome bounded_h_support(const BoundedHSupportInput &, ProgramIdentity,
                                         const registry::PreparedProvider<registry::LPPort> &,
                                         const ExecutionContext &);

struct SupportBoundCertificate {
    std::optional<SetId> input_set;
    Vector direction, carrier_lower, carrier_upper;
    SupportUpperBound bound;
};
struct BoundedHAxisCover {
    Vector lower, upper;
    std::vector<registry::LPQueryRecord> lp_calls;
    std::vector<SupportBoundMethod> methods;
    std::vector<SupportBoundCertificate> certificates;
};
struct BoundedHAxisFailure {
    BoundedHAxisCover prefix;
    std::size_t coordinate;
    bool upper_direction;
    std::variant<Diagnostics, Unsupported, OperationStopped> cause;
};
using BoundedHAxisOutcome = std::variant<BoundedHAxisCover, BoundedHAxisFailure>;
// General-dimensional axis cover. The carrier remains part of the actual
// intersection; a stopped or inconsistent numerical result is not emptiness.
BoundedHAxisOutcome bounded_h_axis_cover(const BoundedHSupportInput &, ProgramIdentity,
                                         const registry::PreparedProvider<registry::LPPort> &,
                                         const ExecutionContext &);

} // namespace csl::reachability
