#include <csl/synthesis/strategy_ts01/analytic_profile.hpp>
#include "../../registry/compiled_verifiers.hpp"
#include <algorithm>
#include <array>
#include <bit>
#include <cmath>

namespace csl::synthesis::strategy_ts01 {
namespace {
const RepresentationId h_polyhedron{"csl.polyhedron.h"};

Diagnostics unsupported(std::string field,std::string explanation) {
    return {{DiagnosticCode::unsupported,std::move(field),std::move(explanation)}};
}
}

class AnalyticWorkspace final : public SynthesisWorkspace {
public:
    SynthesisResult solve(const problem::ResolvedProblem& problem,const FamilyRequest& request,
        const ExecutionContext& context) override {
        SynthesisResult result{Termination::completed,
            {problem.identity(),MathematicalOutcome::undetermined,Unestablished{},{}},{},{},{},{},{}};
        const registry::StrategyRequest frozen{problem,StrategyConfiguration{ModuleId{strategy_id},{},{},{},{},{},{},{},h_polyhedron},
            request,strategy_version};
        if(!registry::detail::ts01_profile_valid(problem,frozen)) {
            result.termination=Termination::operation_rejected;
            result.stop=ScopedRequestRejection{{{"ts01/profile"},"strategy",ModuleId{strategy_id},std::string(strategy_version),
                ModuleId{strategy_id},std::string(strategy_version)},unsupported("ts01.profile","Only the exact two-step scalar integrator profile is admitted."),{},
                {false,false,0,false}};
            return result;
        }
        if(context.cancellation.stop_requested()||(context.deadline&&std::chrono::steady_clock::now()>=*context.deadline)) {
            const auto reason=context.cancellation.stop_requested()?StopReason::cancelled:StopReason::deadline_expired;
            result.termination=Termination::cancelled;
            result.stop=ScopedOperationStopped{{reason,"Stopped before analytic T-S01 publication."},
                {{"ts01/analytic"},"strategy",ModuleId{strategy_id},std::string(strategy_version),
                    ModuleId{strategy_id},std::string(strategy_version)},{false,false,0,false}};
            return result;
        }
        const JointCoordinates coordinates{{1,1,0},2};
        FamilyIdentity identity{problem.identity(),request,coordinates,ModuleId{strategy_id},strategy_version,{}};
        auto relation=registry::detail::make_ts01_relation();
        if(const auto* errors=std::get_if<Diagnostics>(&relation)) {
            result.termination=Termination::contract_rejected;
            result.stop=ContractValidationFailure{*errors,{false,false,0,false},{}};
            return result;
        }
        auto payload=std::get<std::shared_ptr<const ExactJointRelation>>(std::move(relation));
        const SymbolicArgument derivation{"T-S01 exact analytic derivation",
            "x2=u0+u1 and (x2-1)^2>=0; zero is attained exactly when u0+u1=1. With u0,u1 in [0,1], the full canonical optimal history relation is the segment (0,s,1,s,1-s), s in [0,1]."};
        const ClaimEvidence optimum{problem.identity(),derivation};
        const ObjectiveBound bound{0,{problem.identity(),derivation}};
        const OptimumEvidence optimum_evidence{optimum,{bound,bound}};
        CompleteOptimalFamily complete{{coordinates,request.representation,payload},{optimum_evidence},
            {identity,RegisteredCompletenessEvidence{{"csl.verifier.ts01-analytic"},"1",
                "TS01-analytic-v1"}},Assurance::numerical};
        result.outcome={problem.identity(),MathematicalOutcome::optimal,derivation,{}};
        result.objective=optimum_evidence.bounds;
        result.complete_proposal=CompleteFamilyProposal{identity,std::move(complete)};
        return result;
    }
};

registry::StrategyRegistration make_registration() {
    return {{ModuleId{strategy_id},strategy_version},
        [](const registry::StrategyRequest& request,const registry::Requirements&)->registry::Capability {
            if(!registry::detail::ts01_profile_valid(request.problem,request))return unsupported("ts01.profile","Only the exact two-step scalar integrator profile is admitted.");
            registry::Output output;output.representation=h_polyhedron;output.assurance=Assurance::numerical;
            output.family=FamilyTarget::exact_optimal_relation;output.completeness=registry::Completeness::established;
            return registry::Offer{std::move(output)};
        },
        [](const registry::StrategyRequest&,const registry::Requirements&)->std::variant<registry::StrategyPlan,registry::Rejection> {
            auto fixed=std::get<registry::CheckedPipeline<>>(registry::check_pipeline());
            return registry::compose_strategy(std::move(fixed),
                [](auto,const registry::StrategyRequest&,const registry::Requirements&) -> std::unique_ptr<SynthesisWorkspace> {
                    return std::make_unique<AnalyticWorkspace>();
                });
        },
        registry::StrategyRegistration::CompleteFamilyVerifierKey{ModuleId{"csl.verifier.ts01-analytic"},"1"}};
}
} // namespace csl::synthesis::strategy_ts01
