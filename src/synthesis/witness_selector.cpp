#include <csl/synthesis/witness_selector.hpp>
#include <csl/synthesis/strategy_ts01/analytic_profile.hpp>
#include <csl/optimization/linear_program.hpp>
#include <cmath>
#include <bit>

namespace csl::synthesis::witness_selector {
namespace {
Diagnostics reject(std::string field,std::string reason) {
    return {{DiagnosticCode::unsupported,std::move(field),std::move(reason)}};
}
Diagnostics admission(const OptimalFamily& family,const WitnessRequest& request) {
    const auto* complete=std::get_if<CompleteOptimalFamily>(&family.outcome());
    if(!family.registry_verified()||!complete||complete->relation.representation.value!="csl.polyhedron.h"||
       complete->relation.coordinates!=JointCoordinates{{1,1,0},2}||
       !dynamic_cast<const strategy_ts01::ExactJointRelation*>(complete->relation.payload.get()))
        return reject("selector.family","Only the registered complete exact T-S01 H relation is supported.");
    if(!std::isfinite(request.distinctness_tolerance)||request.distinctness_tolerance<0)
        return reject("selector.tolerance","Distinctness tolerance must be finite and nonnegative.");
    for(const auto& direction:request.directions)
        if(direction.size()!=2||!std::isfinite(direction[0])||!std::isfinite(direction[1]))
            return reject("selector.directions","Directions must be finite (u0,u1) vectors, minimized over the family.");
    return {};
}
std::variant<LinearProgram,Diagnostics> program(const OptimalFamily& family,const Vector& direction,std::size_t index) {
    const auto& complete=std::get<CompleteOptimalFamily>(family.outcome());
    const auto* payload=dynamic_cast<const strategy_ts01::ExactJointRelation*>(complete.relation.payload.get());
    const auto h=std::get<sets::HRepresentation>(payload->h_polyhedron().representation());
    SparseMatrix matrix{h.inequalities.rows()+h.equalities.rows(),5,{0},{},{}};
    std::vector<Interval> rows;
    const auto append=[&](const numeric::MatrixView& source,const numeric::VectorView& rhs,bool equality) {
        for(std::size_t r=0;r<source.rows();++r) {
            for(std::size_t c=0;c<5;++c)if(source(r,c)!=0) {
                matrix.column_indices.push_back(c);matrix.values.push_back(source(r,c));
            }
            matrix.row_offsets.push_back(matrix.values.size());
            rows.push_back({equality?std::optional<double>{rhs[r]}:std::nullopt,rhs[r]});
        }
    };
    append(h.inequalities,h.upper_bounds,false);append(h.equalities,h.equality_values,true);
    return optimization::make_linear_program({{family.identity().problem,{"ts01-selector-direction/"+std::to_string(index)+"/"+std::to_string(std::bit_cast<std::uint64_t>(direction[0]))+"/"+std::to_string(std::bit_cast<std::uint64_t>(direction[1]))}},
        {0,0,0,direction[0],direction[1]},0,std::move(matrix),std::vector<Interval>(5),std::move(rows)});
}
std::optional<OperationStopped> stopped(const ExecutionContext& context) {
    if(context.cancellation.stop_requested())return OperationStopped{StopReason::cancelled,"Query cancelled; earlier observations retained."};
    if(context.deadline&&std::chrono::steady_clock::now()>=*context.deadline)return OperationStopped{StopReason::deadline_expired,"Query deadline expired; earlier observations retained."};
    return {};
}
class Workspace final : public WitnessSelectorWorkspace {
    registry::PreparedProvider<registry::LPPort> provider_;
public:
    explicit Workspace(registry::PreparedProvider<registry::LPPort> provider):provider_(std::move(provider)){}
    std::variant<WitnessSelection,Unsupported> select(const OptimalFamily& family,const WitnessRequest& request,
        const ExecutionContext& context) override {
        if(auto errors=admission(family,request);!errors.empty())return Unsupported{std::move(errors)};
        if(!context.resources)return Unsupported{reject("selector.resources","A resource policy is required.")};
        if(auto errors=check_resources(*context.resources);!errors.empty())return Unsupported{std::move(errors)};
        if(!std::isfinite(context.numerical.absolute_tolerance)||context.numerical.absolute_tolerance<0||
           !std::isfinite(context.numerical.relative_tolerance)||context.numerical.relative_tolerance<0)
            return Unsupported{reject("selector.numerical","Finite nonnegative numerical tolerances are required.")};
        WitnessSelection selected{{{},request.count,{selector_id},request.seed,family.identity(),request.directions,
            request.distinctness_tolerance},Termination::completed,{}};
        if(const auto stop=stopped(context)) {selected.termination=Termination::cancelled;selected.diagnostics=stop->diagnostics;return selected;}
        try {
            // Admit every generated direction before the first native solve.
            std::vector<LinearProgram> programs;
            for(std::size_t i=0;i<request.directions.size()&&request.count!=0;++i) {
                if(const auto stop=stopped(context)) {selected.termination=Termination::cancelled;selected.diagnostics=stop->diagnostics;return selected;}
                auto generated=program(family,request.directions[i],i);
                if(auto* errors=std::get_if<Diagnostics>(&generated))return Unsupported{std::move(*errors)};
                auto lp=std::get<LinearProgram>(std::move(generated));
                auto prepared=provider_.prepare(lp);
                if(const auto* rejected=std::get_if<registry::Rejection>(&prepared))return Unsupported{rejected->diagnostics};
                programs.push_back(std::move(lp));
            }
            registry::RegisteredLPQueryRunner runner{provider_};
            const auto* payload=dynamic_cast<const strategy_ts01::ExactJointRelation*>(std::get<CompleteOptimalFamily>(family.outcome()).relation.payload.get());
            for(const auto& lp:programs) {
                if(selected.batch.distinct_count()>=request.count)break;
                if(const auto stop=stopped(context)) {selected.termination=Termination::cancelled;selected.diagnostics=stop->diagnostics;return selected;}
                auto outcome=runner.solve(lp,context);
                if(const auto* unsupported=std::get_if<Unsupported>(&outcome)) {
                    selected.termination=Termination::operation_rejected;
                    selected.diagnostics="LP provider rejected a direction query; earlier observations retained.";
                    if(!unsupported->diagnostics.empty())selected.diagnostics+=" "+unsupported->diagnostics.front().explanation;
                    return selected;
                }
                const auto& result=std::get<ProgramResult>(outcome);
                if(result.termination!=Termination::completed) {
                    selected.termination=result.termination;selected.diagnostics=result.raw_diagnostics;
                    if(!runner.records().empty())
                        if(const auto* not_run=std::get_if<registry::LPQueryNotRun>(&runner.records().back());
                           not_run&&not_run->request==lp.identity()&&not_run->reason==registry::LPQueryNotRunReason::deadline) {
                            selected.termination=Termination::cancelled;
                            selected.diagnostics="Query deadline expired before provider execution; earlier observations retained.";
                        }
                    return selected;
                }
                if(result.outcome.subject!=lp.identity()||result.outcome.value!=MathematicalOutcome::optimal||
                   !result.primal||result.primal->size()!=5||!payload->contains(*result.primal)) {
                    selected.termination=Termination::numerical_failure;
                    selected.diagnostics="Direction query did not return a consistent exact T-S01 family history.";return selected;
                }
                const auto& z=*result.primal;
                selected.batch.witnesses.push_back({family.identity().problem,{{z[0]},{z[1]},{z[2]}},{{z[3]},{z[4]}},0});
            }
            selected.diagnostics=selected.batch.distinct_count()<request.count?
                "Search shortfall: directions exhausted; fewer distinct histories do not prove uniqueness.":
                "Requested distinct histories found; no uniform sampling or uniqueness guarantee.";
        } catch(const std::bad_alloc&) {
            selected.termination=Termination::resource_limit;selected.diagnostics="Query allocation failed; earlier observations retained.";return selected;
        }
        return selected;
    }
};
}
registry::Registration<registry::SelectorPort> make_registration(registry::PreparedProvider<registry::LPPort> provider) {
    return {{{selector_id},"1"},[provider](const registry::SelectorRequest& request,const registry::Requirements& requirements)->registry::Capability {
        if(auto errors=admission(request.family,request.selection);!errors.empty())return errors;
        if(requirements.scalar!=registry::Scalar::binary64||requirements.output.assurance!=Assurance::numerical)
            return reject("selector.assurance","Only numerical binary64 queries are supported.");
        for(std::size_t i=0;i<request.selection.directions.size()&&request.selection.count!=0;++i) {
            auto generated=program(request.family,request.selection.directions[i],i);
            if(const auto* errors=std::get_if<Diagnostics>(&generated))return *errors;
            auto prepared=provider.prepare(std::get<LinearProgram>(generated));
            if(const auto* rejected=std::get_if<registry::Rejection>(&prepared))return rejected->diagnostics;
        }
        return registry::Offer{{{"csl.witness-batch.v1"},Assurance::numerical,{},{},registry::Completeness::unestablished}};
    },[provider](const registry::SelectorRequest&)->std::unique_ptr<WitnessSelectorWorkspace> {return std::make_unique<Workspace>(provider);}};
}
}
