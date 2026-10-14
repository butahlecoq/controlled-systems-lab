#pragma once

#include <csl/model/contracts.hpp>
#include <csl/sets/contracts.hpp>
#include <csl/optimization/objective_contracts.hpp>
#include <csl/evidence/contracts.hpp>

namespace csl {
struct ContinuousDomain { std::vector<AdmissibleSet> stages; };
// Ordered stage-invariant choices, including an explicitly dimensioned empty catalogue.
struct FiniteDomain { std::size_t dimension; std::vector<Vector> catalogue; };
// Product coordinates are [continuous, discrete]; neither alternative denotes hybrid dynamics.
struct MixedDomain { ContinuousDomain continuous; FiniteDomain discrete; };
using ControlDomain = std::variant<ContinuousDomain, FiniteDomain, MixedDomain>;
struct TemporalConstraints { SparseMatrix joint_map; std::vector<Interval> bounds; };
struct KnownInitial { Vector point; };
enum class SetQuantifier { unspecified, existential, universal };
struct InitialSet { AdmissibleSet set; SetQuantifier quantifier{SetQuantifier::unspecified}; };
using InitialInformation = std::variant<KnownInitial, InitialSet>;
struct KnownExternalSequence { std::vector<Vector> stages; };
// T factors mean their Cartesian product; the quantifier scopes the whole sequence.
// No correlation, fixed-parameter reuse or initial/external coupling is encoded.
// At T=0 the product contains exactly the empty sequence. Boundedness is not implied.
struct ExogenousExternalInput {
    std::vector<AdmissibleSet> stages;
    SetQuantifier quantifier{SetQuantifier::unspecified};
};
struct AdversarialExternalInput {
    std::vector<AdmissibleSet> stages;
    SetQuantifier quantifier{SetQuantifier::unspecified};
    std::string semantics_reference; // Deferred objective/policy/information; cannot override product.
};
using ExternalInput = std::variant<KnownExternalSequence, ExogenousExternalInput, AdversarialExternalInput>;
enum class InformationPattern { nominal_open_loop, feedback };
struct Problem {
    ProblemId id;
    std::shared_ptr<const SystemModel> model;
    std::vector<double> times; // T+1 strictly increasing; controls indexed [0,T)
    InitialInformation initial;
    ControlDomain controls;
    std::vector<AdmissibleSet> states; // T+1; use UniversalSet explicitly
    std::optional<TemporalConstraints> temporal;
    std::optional<ExternalInput> external; // absent requires a zero-dimensional external port
    InformationPattern information;
    TerminalObjective objective;
};
// Canonical joint order: x0,...,xT,u0,...,u(T-1); a lifted payload retains this map.
struct JointCoordinates { Dimensions dimensions; std::size_t horizon; bool operator==(const JointCoordinates&) const = default; };

Diagnostics check_nominal_profile(const Problem&, bool requires_inverse, Assurance);
} // namespace csl
