#pragma once

#include <csl/geometry/hull_reducer.hpp>
#include <csl/registry/provider.hpp>

namespace csl::geometry {

// The selected dependencies are copied into the registration; callers may
// destroy the registries after preparing these values.
struct AffineSumDependencies {
    registry::PreparedProvider<registry::HullReducerPort> hull;
    registry::PreparedProvider<registry::LPPort> lp;
    std::optional<registry::PreparedProvider<registry::ConversionPort>> conversion;
};

struct AffineSumOptions {
    // Admission policy for generated point clouds. No ambient-dimension
    // restriction is implied when this is absent.
    std::optional<std::size_t> max_candidates;
    // Empty means unnamed output coordinates for affine images.
    std::vector<std::string> affine_output_labels;
};

// Implements finite polyhedral affine images and Minkowski sums using selected
// conversion, hull-reduction, and LP providers. Finite/mixed action catalogues
// are outside this SetHandle operation contract and are never convexified.
registry::Registration<registry::GeometryPort> make_affine_sum_registration(
    AffineSumDependencies, AffineSumOptions = {});

} // namespace csl::geometry
