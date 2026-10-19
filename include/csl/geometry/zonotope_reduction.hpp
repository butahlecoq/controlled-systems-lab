#pragma once

#include <csl/registry/registry.hpp>

namespace csl::geometry::approximation {

// Remove physically zero unconstrained generator columns through ConversionPort.
registry::Registration<registry::ConversionPort> make_zero_generator_removal_registration(SetId output_id);

// Replace omitted factors by independent coordinate-axis intervals. The
// registered result requires independent outer inclusion admission.
registry::Registration<registry::ApproximationPort> make_axis_cover_registration(SetId output_id);

} // namespace csl::geometry::approximation
