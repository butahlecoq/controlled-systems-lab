#pragma once

#include <csl/core/values.hpp>
#include <csl/core/diagnostics.hpp>
#include <variant>

namespace csl::reachability {

// center + factor*z, with either independent |z_i|<=1 or ||z||_2<=1.
// A supplied template retains its physical coordinate frame, including zero columns.
enum class InnerTemplateNorm { independent_intervals, euclidean_ball };
struct InnerTemplateInput {
    Vector center;
    Matrix directions;
    InnerTemplateNorm norm;
    Matrix inequalities;
    Vector upper_bounds;
    Matrix equalities;
    Vector equality_values;
};
struct InnerTemplate {
    Vector center;
    Matrix factor;
    InnerTemplateNorm norm;
    double radius;
    Vector row_support_upper;
    Vector row_slack_lower;
    std::size_t rounding_shrinks;
    bool point;
};
using InnerTemplateResult = std::variant<InnerTemplate, Diagnostic>;

// Maximal uniform scale at the supplied center/template, rounded inward and
// independently admitted against every stored H row using outward arithmetic.
// This establishes stored-row containment, not feasibility of a nonlinear plant.
InnerTemplateResult inscribe_template(const InnerTemplateInput &);
Diagnostics check_inner_template(const InnerTemplateInput &, const InnerTemplate &);

} // namespace csl::reachability
