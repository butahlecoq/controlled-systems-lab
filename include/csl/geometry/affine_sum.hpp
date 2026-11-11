#pragma once

#include <csl/geometry/contracts.hpp>

#include <csl/geometry/hull_reducer.hpp>
#include <csl/geometry/source_index_hull.hpp>
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

// Source-index methods have a separate evidence contract: the affine-sum
// workspace runs the bounded exact 2D hull checker on the generated cloud and
// only applies provider indices after that checker verifies all-input
// containment. The LP reducer dependency is intentionally absent for this
// path; these methods do not issue vertex-membership LPs.
registry::Registration<registry::GeometryPort> make_affine_sum_registration(
    SourceIndexAffineSumDependencies, AffineSumOptions = {});

} // namespace csl::geometry
