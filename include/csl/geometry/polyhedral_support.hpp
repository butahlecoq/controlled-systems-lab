#pragma once

#include <csl/registry/provider.hpp>
#include <csl/sets/data.hpp>

namespace csl::geometry::polyhedral {

// Evaluates SupportQuery over native V and empty set representations. Dot
// products and ray signs use the exact values of their represented binary64
// inputs; a finite support value is rounded to nearest binary64.
registry::Registration<registry::GeometryPort> make_support_registration();

} // namespace csl::geometry::polyhedral
