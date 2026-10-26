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
            request,strategy_version,{}};
        const bool admitted=request.target==FamilyTarget::partial_relation?
            registry::detail::ts01_partial_profile_valid(problem,frozen):registry::detail::ts01_profile_valid(problem,frozen);
        if(!admitted) {
            result.termination=Termination::operation_rejected;
            result.stop=ScopedRequestRejection{{{"ts01/profile"},"strategy",ModuleId{strategy_id},std::string(strategy_version),
                ModuleId{strategy_id},std::string(strategy_version)},unsupported("ts01.profile","Only the exact two-step scalar integrator profile is admitted."),{},
                {false,false,0,false}};
            return result;
        }
        if(context.cancellation.stop_requested()||(context.deadline&&std::chrono::steady_clock::now()>=*context.deadline)) {
            const auto reason=context.cancellation.stop_requested()?StopReason::cancelled:StopReason::deadline_expired;
            result.termination=reason==StopReason::deadline_expired?Termination::deadline_expired:Termination::cancelled;
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
        if(request.target==FamilyTarget::partial_relation) {
            auto midpoint=MidpointJointRelation::canonical();
            if(const auto* errors=std::get_if<Diagnostics>(&midpoint)) {
                result.termination=Termination::contract_rejected;
                result.stop=ContractValidationFailure{*errors,{false,false,0,false},{}};
                return result;
            }
            const SymbolicArgument partial_derivation{"T-S01 exact midpoint optimality",
                "The resolved objective is (x2-1)^2, so it is nonnegative for every feasible history. At the feasible midpoint history x2=1, hence the objective equals zero and the global optimum is zero."};
            const ObjectiveBound partial_bound{0,{problem.identity(),partial_derivation}};
            const OptimumEvidence partial_optimum{{problem.identity(),partial_derivation},{partial_bound,partial_bound}};
            const SymbolicArgument midpoint_proof{"T-S01 exact midpoint singleton",
                "At s=1/2, (x0,x1,x2,u0,u1)=(0,1/2,1,1/2,1/2) satisfies both dynamics equations and both control bounds. Its exact objective is (1-1)^2=0, while the objective is nonnegative for every feasible history."};
            PartialOptimalFamily partial{{coordinates,request.representation,
                std::get<std::shared_ptr<const MidpointJointRelation>>(std::move(midpoint))},partial_optimum,
                {{problem.identity(),midpoint_proof},"T-S01 exact midpoint singleton"},{"s=1/2"}};
            result.outcome={problem.identity(),MathematicalOutcome::optimal,partial_derivation,{}};
            result.objective=partial_optimum.bounds;
            result.partial_proposal=PartialFamilyProposal{identity,std::move(partial)};
            return result;
        }
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
            if(registry::detail::ts01_partial_profile_valid(request.problem,request)) {
                registry::Output output;output.representation=h_polyhedron;output.assurance=Assurance::numerical;
                output.family=FamilyTarget::partial_relation;output.completeness=registry::Completeness::unestablished;
                return registry::Offer{std::move(output)};
            }
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
        registry::StrategyRegistration::CompleteFamilyVerifierKey{ModuleId{"csl.verifier.ts01-analytic"},"1"},
        {},registry::StrategyRegistration::PartialFamilyVerifierKey{ModuleId{"csl.verifier.ts01-midpoint"},"1"}};
}

MidpointJointRelation::MidpointJointRelation(sets::SetData h_polyhedron):h_polyhedron_(std::move(h_polyhedron)) {}
std::variant<std::shared_ptr<const MidpointJointRelation>,Diagnostics> MidpointJointRelation::canonical() {
    auto inequalities=numeric::snapshot(SparseMatrix{0,5,{0},{},{}});
    auto upper=numeric::snapshot_vector(Vector{});
    auto equalities=numeric::snapshot(SparseMatrix{5,5,{0,1,2,3,4,5},{0,1,2,3,4},{1,1,1,1,1}});
    auto equality_values=numeric::snapshot_vector(Vector{0,0.5,1,0.5,0.5});
    if(!std::holds_alternative<numeric::MatrixView>(inequalities)||!std::holds_alternative<numeric::VectorView>(upper)||
        !std::holds_alternative<numeric::MatrixView>(equalities)||!std::holds_alternative<numeric::VectorView>(equality_values))
        return Diagnostics{{DiagnosticCode::invalid_input,"ts01.midpoint.relation","Could not construct exact singleton buffers"}};
    auto data=sets::make_h({{"ts01-midpoint-history"},5,{"x0","x1","x2","u0","u1"}},
        {std::get<numeric::MatrixView>(inequalities),std::get<numeric::VectorView>(upper),
         std::get<numeric::MatrixView>(equalities),std::get<numeric::VectorView>(equality_values)});
    if(!std::holds_alternative<sets::SetData>(data))
        return Diagnostics{{DiagnosticCode::invalid_input,"ts01.midpoint.relation","Could not construct the canonical midpoint singleton"}};
    return std::shared_ptr<const MidpointJointRelation>(new MidpointJointRelation(std::get<sets::SetData>(std::move(data))));
}
} // namespace csl::synthesis::strategy_ts01
