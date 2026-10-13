#include <csl/synthesis/strategy_ts01/analytic_profile.hpp>
#include <type_traits>

using namespace csl;

int main() {
    const FamilyIdentity identity{{"public-client"},
        {"ts01_exact_integrator",{"public-client"},FamilyTarget::exact_optimal_relation,
            {1e-8,1e-8},Assurance::numerical,{"csl.polyhedron.h"},{}},
        {{1,1,0},2},{"csl.synthesis.ts01-analytic"},"1",{}};
    auto relation=std::make_shared<const JointRelationPayload>();
    const OptimumEvidence optimum{{identity.problem,SymbolicArgument{"untrusted","caller text"}},{}};
    RegisteredCompletenessEvidence untrusted{identity.strategy,identity.strategy_version,"forged"};
    CompleteOptimalFamily candidate{{identity.coordinates,identity.request.representation,relation},
        optimum,{identity,untrusted},Assurance::numerical};
    return std::holds_alternative<Diagnostics>(FamilyPublisher::publish(identity,std::move(candidate)))?0:2;
}
