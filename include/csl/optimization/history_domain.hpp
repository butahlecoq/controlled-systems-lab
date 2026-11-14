#pragma once

#include <csl/geometry/ellipsoidal.hpp>
#include <csl/synthesis/control_recovery.hpp>

#include <optional>

namespace csl::optimization {

// Membership records constrain a state block of the original joint history.
// Their relation is a recorded claim about the selected region, not an
// inclusion certificate; the original full-history relation remains mandatory.
// A source record binds the declared reference identity to typed geometry.
// Its geometry is checked independently of the selected membership; neither
// this binding nor a matching identity proves the declared set relation.
enum class HistorySetFamily { polytope, box, zonotope, parallelotope, ellipsoid };

struct HistoryHMembership {
    sets::SetData selected;
};
struct HistoryAxisBoxMembership {
    Vector center;
    Vector radii;
};
struct HistoryZonotopeMembership {
    Vector center;
    Matrix generators;
};
// Frame columns form an independently admitted full-rank basis. Coordinate
// intervals may be singletons, so the selected region can be degenerate.
struct HistoryParallelotopeMembership {
    Vector center;
    Matrix frame;
    Vector lower, upper;
};
struct HistoryBallFactorMembership {
    geometry::ellipsoidal::FactorEllipsoid selected;
};
struct HistoryVSimplexMembership {
    sets::SetData selected;
};
using HistoryMembershipShape =
    std::variant<HistoryHMembership, HistoryAxisBoxMembership, HistoryZonotopeMembership,
                 HistoryParallelotopeMembership, HistoryBallFactorMembership,
                 HistoryVSimplexMembership>;

struct HistorySourceGeometry {
    SetId id;
    HistorySetFamily family;
    HistoryMembershipShape geometry;
};

struct HistoryMembershipOrigin {
    SetId reference;
    SetId selected;
    // The family of the selected membership shape. The source family is
    // recorded separately in HistorySourceGeometry because approximations
    // may change representation family.
    HistorySetFamily selected_family;
    SetRelation relation;
    std::string coordinate_frame;
    // Ordered canonical coordinates of the selected stage's physical state.
    std::vector<std::size_t> canonical_state_indices;
    // Required for a membership. The optional field keeps existing aggregate
    // initializers source-compatible; validation rejects an absent source.
    std::optional<HistorySourceGeometry> source;
};

struct HistoryMembership {
    StageIndex stage;
    HistoryMembershipOrigin origin;
    HistoryMembershipShape shape;
};

struct HistoryDomain {
    synthesis::JointHistoryRelation original;
    std::vector<HistoryMembership> memberships;
    // Domain declaration: all memberships use the ordered canonical state
    // block in this frame. This does not authenticate an external frame name.
    std::string state_frame{};
};

struct HistoryHWitness {
    bool operator==(const HistoryHWitness &) const = default;
};
struct HistoryAxisBoxWitness {
    Vector coefficients;
    bool operator==(const HistoryAxisBoxWitness &) const = default;
};
struct HistoryZonotopeWitness {
    Vector coefficients;
    bool operator==(const HistoryZonotopeWitness &) const = default;
};
struct HistoryParallelotopeWitness {
    Vector coefficients;
    bool operator==(const HistoryParallelotopeWitness &) const = default;
};
struct HistoryBallFactorWitness {
    Vector coefficients;
    bool operator==(const HistoryBallFactorWitness &) const = default;
};
struct HistoryVSimplexWitness {
    Vector coefficients;
    bool operator==(const HistoryVSimplexWitness &) const = default;
};
using HistoryMembershipWitness =
    std::variant<HistoryHWitness, HistoryAxisBoxWitness, HistoryZonotopeWitness,
                 HistoryParallelotopeWitness, HistoryBallFactorWitness, HistoryVSimplexWitness>;

// Check only metadata, dimensions and selected payloads. This does not verify
// a declared inner/outer relation against a reference set.
Diagnostics check_history_domain_memberships(const HistoryDomain &);

// Independently check a witness in every selected region. The caller must also
// check the full original relation and source objective.
Diagnostics check_history_membership_witnesses(const HistoryDomain &,
                                               std::span<const double> canonical_history,
                                               std::span<const HistoryMembershipWitness>,
                                               NumericalPolicy);

} // namespace csl::optimization
