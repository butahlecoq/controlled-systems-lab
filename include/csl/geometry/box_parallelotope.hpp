#pragma once

#include <csl/registry/registry.hpp>

namespace csl::geometry::approximation {

// Native binary64 directional enclosure of a bounded V set. The output is an
// H set, and run_registered independently checks every source vertex and ray.
registry::Registration<registry::ApproximationPort> make_box_registration(SetId output_id);

// Orientation rows are a full-rank square matrix of finite binary64
// directions. The output contains each direction's positive and negative
// support slab, giving 2n rows for an n-dimensional input. Except in 2D, an exact
// residual certificate must prove nonsingularity; unresolved bases are rejected.
registry::Registration<registry::ApproximationPort>
make_parallelotope_registration(SetId output_id, Matrix orientation_rows);

// Four corners are ordered around one finite binary64 box or parallelogram.
// The registry verifies its exact shape, then run_registered independently
// checks every corner against the native H reference.
registry::Registration<registry::ApproximationPort>
make_inscribed_box_registration(SetId output_id, Matrix ordered_corners);
registry::Registration<registry::ApproximationPort>
make_inscribed_parallelotope_registration(SetId output_id, Matrix ordered_corners);

} // namespace csl::geometry::approximation
