#pragma once

#include <csl/registry/registry.hpp>
#include <functional>

namespace csl::adapters::polyhedral {

struct ConversionObservation {
    GeometryRequestIdentity request;
    registry::Identity converter;
    registry::Identity lp_backend;
    std::string input_representation;
    std::string output_representation;
    std::size_t input_inequalities{};
    std::size_t input_equalities{};
    std::size_t input_vertices{};
    std::size_t input_rays{};
    std::size_t output_inequalities{};
    std::size_t output_equalities{};
    std::size_t output_vertices{};
    std::size_t output_rays{};
    std::optional<std::size_t> affine_dimension;
    double elapsed_seconds{};
    std::optional<NumericalCheck> numerical_check;
    std::string outcome;
    std::string diagnostics;
};

struct QhullOptions {
    // These are caller-selected admission limits. An empty value means no
    // policy limit; Qhull's own integer-width and host allocation limits remain.
    std::optional<std::size_t> max_ambient_dimension;
    std::optional<std::size_t> max_input_rows;
    // Called inline immediately before each native qh_new_qhull invocation.
    // Separate workspaces may invoke it concurrently; callback exceptions propagate.
    std::function<void()> before_native_call;
    std::function<void(const ConversionObservation&)> observe;
};

using QhullRegistrationResult =
    std::variant<registry::Registration<registry::ConversionPort>, Diagnostics>;

// Uses the caller-selected LP implementation for feasibility, boundedness,
// and relative-interior prerequisites. The returned registration owns a copy
// of that registration; it does not retain a Registry or borrowed requests.
QhullRegistrationResult make_qhull_registration(
    registry::Registration<registry::LPPort> lp_registration,
    QhullOptions options = {});

} // namespace csl::adapters::polyhedral
