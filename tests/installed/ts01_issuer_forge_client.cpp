#include <csl/contracts.hpp>

using namespace csl;

namespace {
bool accepted = false;
struct ArbitraryPayload final : JointRelationPayload {};
}

namespace csl::synthesis::strategy_ts01 {
Ts01AnalyticCoverageEvidence AnalyticStrategy::issue_coverage(FamilyIdentity identity,
    std::shared_ptr<const JointRelationPayload> relation, OptimumEvidence optimum) {
    return Ts01AnalyticCoverageEvidence(std::move(identity),std::move(relation),std::move(optimum));
}

std::unique_ptr<SynthesisWorkspace> AnalyticStrategy::make_workspace() {
    FamilyIdentity identity{ProblemId{"attacker-chosen"},
        FamilyRequest{"ts01_exact_integrator",ProblemId{"attacker-chosen"},FamilyTarget::exact_optimal_relation,
            NumericalPolicy{1e-8,1e-8},Assurance::numerical,RepresentationId{"csl.polyhedron.h"},{}},
        JointCoordinates{Dimensions{1,1,0},2},ModuleId{"csl.synthesis.ts01-analytic"},"1",{}};
    auto relation=std::make_shared<const ArbitraryPayload>();
    const SymbolicArgument fabricated{"fabricated","asserted optimum for an unrelated payload"};
    const ClaimEvidence claim{identity.problem,fabricated};
    const ObjectiveBound bound{0.0,ClaimEvidence{identity.problem,fabricated}};
    const OptimumEvidence optimum{claim,ObjectiveEvidence{bound,bound}};
    auto coverage=issue_coverage(identity,relation,optimum);
    CompleteOptimalFamily complete{JointRelation{identity.coordinates,identity.request.representation,relation},
        optimum,CompletenessEvidence{identity,coverage},Assurance::numerical};
    accepted=std::holds_alternative<OptimalFamily>(FamilyPublisher::publish(identity,std::move(complete)));
    return {};
}
}

int main() {
    (void)synthesis::strategy_ts01::AnalyticStrategy::make_workspace();
    // The shared contracts boundary must reject a fake issuer even when the
    // caller links only CSL::contracts and provides no strategy implementation.
    return accepted ? 1 : 0;
}
