#include <csl/contracts.hpp>

namespace csl {
// This contracts-only consumer replaces the out-of-line friend publisher
// definition. The static contracts archive is not otherwise pulled in, so the
// replacement accepts any caller-built complete-family claim.
std::variant<OptimalFamily,Diagnostics> FamilyPublisher::publish(FamilyIdentity identity,
    OptimalFamilyOutcome outcome) {
    return OptimalFamily{std::move(identity),std::move(outcome)};
}
}

int main() {
    using namespace csl;
    const ProblemId problem{"attacker-chosen"};
    const FamilyIdentity identity{problem,
        FamilyRequest{"arbitrary-profile",problem,FamilyTarget::exact_optimal_relation,
            NumericalPolicy{1e-8,1e-8},Assurance::numerical,RepresentationId{"csl.polyhedron.h"},{}},
        JointCoordinates{Dimensions{1,1,0},2},ModuleId{"unregistered.plugin"},"1",{}};
    const auto payload=std::make_shared<const JointRelationPayload>();
    const SymbolicArgument fabricated{"fabricated","asserted optimum for an unrelated payload"};
    const ClaimEvidence claim{problem,fabricated};
    const ObjectiveBound bound{0.0,ClaimEvidence{problem,fabricated}};
    const OptimumEvidence optimum{claim,ObjectiveEvidence{bound,bound}};
    const CompleteOptimalFamily complete{
        JointRelation{identity.coordinates,identity.request.representation,payload},
        optimum,CompletenessEvidence{identity,Ts01AnalyticCoverageEvidence{}},Assurance::numerical};
    return std::holds_alternative<OptimalFamily>(FamilyPublisher::publish(identity,complete)) ? 0 : 1;
}
