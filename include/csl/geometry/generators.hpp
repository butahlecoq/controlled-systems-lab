#pragma once

#include <csl/sets/generator_sets.hpp>

namespace csl::geometry::generators {

// These preserve the real-set generator algebra. Binary64 coefficient arithmetic
// can round; neither function supplies validated inclusion or an error bound.
sets::GeneratorResult affine_image(const sets::GeneratorSet&, const Matrix& map,
    const Vector& offset, SetId output_id, std::vector<std::string> output_labels = {});

// Both operands see a common xi for every equal FactorId. This is a correlated
// sum, not the independent Minkowski sum when IDs overlap.
sets::GeneratorResult dependent_sum(const sets::GeneratorSet&, const sets::GeneratorSet&, SetId output_id);

// Exact independent Minkowski algebra only when the factor ID sets are disjoint.
// A shared ID is rejected rather than silently cloned or treated as independent.
sets::GeneratorResult minkowski_sum(const sets::GeneratorSet&, const sets::GeneratorSet&, SetId output_id);

} // namespace csl::geometry::generators
