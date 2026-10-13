#include <csl/synthesis/strategy_ts01/analytic_profile.hpp>
#include <type_traits>

using namespace csl;

template<class T>
concept CanIssueTs01Coverage = requires(FamilyIdentity identity,
    std::shared_ptr<const JointRelationPayload> relation,OptimumEvidence optimum) {
    T::issue_coverage(std::move(identity),std::move(relation),std::move(optimum));
};

static_assert(!CanIssueTs01Coverage<synthesis::strategy_ts01::AnalyticStrategy>);
static_assert(!std::is_constructible_v<Ts01AnalyticCoverageEvidence,FamilyIdentity,
    std::shared_ptr<const JointRelationPayload>,OptimumEvidence>);
static_assert(std::is_default_constructible_v<Ts01AnalyticCoverageEvidence>);

int main() {
    const FamilyIdentity identity{{"public-client"},
        {"ts01_exact_integrator",{"public-client"},FamilyTarget::exact_optimal_relation,
            {1e-8,1e-8},Assurance::numerical,{"csl.polyhedron.h"},{}},
        {{1,1,0},2},{"csl.synthesis.ts01-analytic"},"1",{}};
    auto relation=std::make_shared<const JointRelationPayload>();
    const OptimumEvidence optimum{{identity.problem,SymbolicArgument{"untrusted","caller text"}},{}};
    Ts01AnalyticCoverageEvidence untrusted;
    if(untrusted.binds(identity,relation,optimum))return 1;

    CompleteOptimalFamily candidate{{identity.coordinates,identity.request.representation,relation},
        optimum,{identity,untrusted},Assurance::numerical};
    return std::holds_alternative<Diagnostics>(FamilyPublisher::publish(identity,std::move(candidate)))?0:2;
}
