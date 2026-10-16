#pragma once

#include <csl/registry/registry.hpp>

namespace csl::geometry::generators {

// Affine images, independent Minkowski sums and typed dependent sums on native
// generator handles. Shared FactorIds remain rejected for MinkowskiSum.
registry::Registration<registry::GeometryPort> make_operation_registration();

// Explicit finite V materialization of an unconstrained zonotope. The caller
// must admit all 2^factor_count cube corners; no reduction is performed.
registry::Registration<registry::ConversionPort> make_v_conversion_registration(
    std::size_t max_vertices);

} // namespace csl::geometry::generators
