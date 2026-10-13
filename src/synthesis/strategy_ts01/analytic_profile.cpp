#include <csl/synthesis/strategy_ts01/analytic_profile.hpp>
#include <algorithm>
#include <array>
#include <bit>
#include <cmath>

namespace csl::synthesis::strategy_ts01 {
namespace {
const RepresentationId h_polyhedron{"csl.polyhedron.h"};

struct Dyadic {
    std::uint64_t significand{};
    int exponent{};
};
Dyadic decompose(double value) noexcept {
    const auto bits=std::bit_cast<std::uint64_t>(value);
    const auto encoded=static_cast<unsigned>((bits>>52)&0x7ffu);
    const auto fraction=bits&((std::uint64_t{1}<<52)-1);
    if(encoded==0)return {fraction,-1074};
    return {(std::uint64_t{1}<<52)|fraction,static_cast<int>(encoded)-1023-52};
}
void add_shifted(std::array<std::uint64_t,20>& value,std::uint64_t significand,unsigned shift) noexcept {
    auto index=shift/64u;const auto bits=shift%64u;
    const auto low=significand<<bits;
    const auto high=bits?significand>>(64u-bits):0;
    const auto add_word=[&](std::size_t word,std::uint64_t term) {
        while(term&&word<value.size()) {
            const auto previous=value[word];value[word]+=term;
            term=static_cast<std::uint64_t>(value[word]<previous);++word;
        }
    };
    add_word(index,low);add_word(index+1,high);
}
bool exact_sum_is_one(double left,double right) noexcept {
    const auto a=decompose(left),b=decompose(right);
    const auto minimum=std::min({a.exponent,b.exponent,0});
    std::array<std::uint64_t,20> sum{},one{};
    add_shifted(sum,a.significand,static_cast<unsigned>(a.exponent-minimum));
    add_shifted(sum,b.significand,static_cast<unsigned>(b.exponent-minimum));
    add_shifted(one,1,static_cast<unsigned>(-minimum));
    return sum==one;
}
bool matrix_is(const numeric::MatrixView& value,std::size_t rows,std::size_t columns,
    std::initializer_list<double> expected) noexcept {
    if(value.rows()!=rows||value.cols()!=columns||expected.size()!=rows*columns)return false;
    auto item=expected.begin();
    for(std::size_t row=0;row<rows;++row)for(std::size_t column=0;column<columns;++column)
        if(value(row,column)!=*item++)return false;
    return true;
}
bool vector_is(const numeric::VectorView& value,std::initializer_list<double> expected) noexcept {
    return value.size()==expected.size()&&std::equal(value.values().begin(),value.values().end(),expected.begin());
}
bool control_interval(const AdmissibleSet& set) {
    const auto* handle=std::get_if<SetHandle>(&set);if(!handle)return false;
    auto data=sets::from_handle(*handle);if(!std::holds_alternative<sets::SetData>(data))return false;
    const auto& value=std::get<sets::SetData>(data);
    const auto representation=value.representation();const auto* h=std::get_if<sets::HRepresentation>(&representation);
    return h&&matrix_is(h->inequalities,2,1,{1,-1})&&vector_is(h->upper_bounds,{1,0})&&
        matrix_is(h->equalities,0,1,{})&&vector_is(h->equality_values,{});
}
bool strict_profile(const problem::ResolvedProblem& problem,const registry::StrategyRequest& request) {
    const auto& family=request.family;
    if(family.profile!=profile_id||family.objective!=problem.identity()||
        family.target!=FamilyTarget::exact_optimal_relation||family.assurance!=Assurance::numerical||
        family.representation!=h_polyhedron||family.materialization_limit||
        request.configuration.strategy.value!=strategy_id||request.configuration.representation!=h_polyhedron)
        return false;
    const auto source=problem.description();
    if(!source||!source->model||source->model->dynamics.time_domain!=TimeDomain::discrete||
        source->information!=InformationPattern::nominal_open_loop||
        source->temporal||!source->model->observations.empty()||source->times!=std::vector<double>{0,1,2})return false;
    const auto model=problem.model();
    if(model.dimensions()!=Dimensions{1,1,0}||model.horizon()!=2||model.channel_count()!=0)return false;
    for(std::size_t stage=0;stage<2;++stage) {
        const auto dynamics=model.stage({stage});if(!std::holds_alternative<csl::model::DynamicsStage>(dynamics))return false;
        const auto& coefficients=std::get<csl::model::DynamicsStage>(dynamics);
        if(!matrix_is(coefficients.A,1,1,{1})||!matrix_is(coefficients.B,1,1,{1})||
            !matrix_is(coefficients.E,1,0,{})||!vector_is(coefficients.offset,{0}))return false;
        const auto time=model.time({stage});if(!std::holds_alternative<double>(time)||std::get<double>(time)!=static_cast<double>(stage))return false;
    }
    const auto terminal_time=model.time({2});if(!std::holds_alternative<double>(terminal_time)||std::get<double>(terminal_time)!=2)return false;
    const auto initial=problem.initial().description();
    if(!initial||!std::holds_alternative<KnownInitial>(*initial)||std::get<KnownInitial>(*initial).point!=Vector{0})return false;
    const auto controls=problem.controls().description();
    if(!controls||!std::holds_alternative<ContinuousDomain>(*controls))return false;
    const auto& control_stages=std::get<ContinuousDomain>(*controls).stages;
    if(control_stages.size()!=2||!control_interval(control_stages[0])||!control_interval(control_stages[1]))return false;
    if(problem.external().dimension()!=0||problem.external().description()->has_value())return false;
    const auto constraints=problem.constraints();
    if(constraints.coordinates()!=JointCoordinates{{1,1,0},2}||constraints.temporal())return false;
    const auto states=constraints.states();
    if(states->size()!=3)return false;
    for(const auto& state:*states) {
        const auto* universal=std::get_if<UniversalSet>(&state);
        if(!universal||universal->dimension!=1)return false;
    }
    const auto objective=problem.objective();const auto coefficients=objective.coefficients();
    const auto* quadratic=std::get_if<optimization::QuadraticCoefficients>(&coefficients);
    return quadratic&&objective.dimension()==1&&matrix_is(quadratic->Q,1,1,{2})&&
        vector_is(quadratic->linear,{-2})&&quadratic->offset==1;
}
Diagnostics unsupported(std::string field,std::string explanation) {
    return {{DiagnosticCode::unsupported,std::move(field),std::move(explanation)}};
}
}

class RelationFactory {
public:
    static std::variant<std::shared_ptr<const ExactJointRelation>,Diagnostics> create() {
        auto inequalities=numeric::snapshot(Matrix{4,5,{0,0,0,1,0, 0,0,0,-1,0,
            0,0,0,0,1, 0,0,0,0,-1}});
        auto upper=numeric::snapshot_vector(Vector{1,0,1,0});
        auto equalities=numeric::snapshot(Matrix{4,5,{1,0,0,0,0, 0,1,0,-1,0,
            0,0,1,0,0, 0,0,0,1,1}});
        auto equality_values=numeric::snapshot_vector(Vector{0,0,1,1});
        if(!std::holds_alternative<numeric::MatrixView>(inequalities)||
            !std::holds_alternative<numeric::VectorView>(upper)||
            !std::holds_alternative<numeric::MatrixView>(equalities)||
            !std::holds_alternative<numeric::VectorView>(equality_values))
            return Diagnostics{{DiagnosticCode::invalid_input,"ts01.relation","Could not construct exact H-representation buffers"}};
        auto data=sets::make_h({{"ts01-optimal-histories"},5,{"x0","x1","x2","u0","u1"}},
            {std::get<numeric::MatrixView>(inequalities),std::get<numeric::VectorView>(upper),
             std::get<numeric::MatrixView>(equalities),std::get<numeric::VectorView>(equality_values)});
        if(!std::holds_alternative<sets::SetData>(data))
            return Diagnostics{{DiagnosticCode::invalid_input,"ts01.relation","The canonical optimal histories are not a valid H-polyhedron"}};
        auto value=std::get<sets::SetData>(std::move(data));
        return std::shared_ptr<const ExactJointRelation>(new ExactJointRelation(std::move(value)));
    }
};

ExactJointRelation::ExactJointRelation(sets::SetData h_polyhedron):h_polyhedron_(std::move(h_polyhedron)) {}
bool ExactJointRelation::contains(std::span<const double> point) const noexcept {
    if(point.size()!=5||std::any_of(point.begin(),point.end(),[](double value){return !std::isfinite(value);}))return false;
    return point[0]==0&&point[1]==point[3]&&point[2]==1&&point[3]>=0&&point[3]<=1&&
        point[4]>=0&&point[4]<=1&&exact_sum_is_one(point[3],point[4]);
}

class AnalyticWorkspace final : public SynthesisWorkspace {
public:
    SynthesisResult solve(const problem::ResolvedProblem& problem,const FamilyRequest& request,
        const ExecutionContext& context) override {
        SynthesisResult result{Termination::completed,
            {problem.identity(),MathematicalOutcome::undetermined,Unestablished{},{}},{},{},{},{},{}};
        const registry::StrategyRequest frozen{problem,StrategyConfiguration{ModuleId{strategy_id},{},{},{},{},{},{},{},h_polyhedron},
            request,strategy_version};
        if(!strict_profile(problem,frozen)) {
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
        auto relation=RelationFactory::create();
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
            {identity,RegisteredCompletenessEvidence{{strategy_id},strategy_version,
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
            if(!strict_profile(request.problem,request))return unsupported("ts01.profile","Only the exact two-step scalar integrator profile is admitted.");
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
        [](const registry::StrategyRequest& request,const CompleteFamilyProposal& proposal)->Diagnostics {
            Diagnostics diagnostics;
            if(!strict_profile(request.problem,request))
                return {{DiagnosticCode::unsupported,"ts01.verifier.profile","Verifier rejected a noncanonical resolved problem or effective request"}};
            const auto& identity=proposal.identity;
            const auto& complete=proposal.family;
            const auto exact_identity=identity.problem==request.problem.identity()&&identity.request==request.family&&
                identity.coordinates==request.problem.constraints().coordinates()&&
                identity.strategy==request.configuration.strategy&&identity.strategy_version==request.strategy_version&&
                identity.lineage.empty();
            if(!exact_identity||complete.completeness.binding!=identity||
                complete.relation.coordinates!=identity.coordinates||
                complete.relation.representation!=request.family.representation||
                complete.assurance!=request.family.assurance||request.family.assurance!=Assurance::numerical||
                identity.strategy.value!=strategy_id||identity.strategy_version!=strategy_version)
                diagnostics.push_back({DiagnosticCode::evidence_mismatch,"ts01.verifier.binding",
                    "T-S01 proof must bind the selected strategy, exact effective request, authoritative problem, coordinates and empty lineage"});
            const auto* proof=std::get_if<RegisteredCompletenessEvidence>(&complete.completeness.support);
            if(!proof||proof->verifier.value!=strategy_id||proof->verifier_version!=strategy_version||
                proof->proof!="TS01-analytic-v1")
                diagnostics.push_back({DiagnosticCode::evidence_mismatch,"ts01.verifier.support",
                    "T-S01 proof requires the registered opaque analytic payload"});
            const auto* relation=dynamic_cast<const ExactJointRelation*>(complete.relation.payload.get());
            if(!relation||!relation->contains(Vector{0,0,1,0,1})||
                !relation->contains(Vector{0,1,1,1,0})||
                relation->h_polyhedron().metadata()->coordinate_labels!=std::vector<std::string>{"x0","x1","x2","u0","u1"})
                diagnostics.push_back({DiagnosticCode::evidence_mismatch,"ts01.verifier.relation",
                    "T-S01 proof does not contain the exact canonical optimal-history relation"});
            const SymbolicArgument derivation{"T-S01 exact analytic derivation",
                "x2=u0+u1 and (x2-1)^2>=0; zero is attained exactly when u0+u1=1. With u0,u1 in [0,1], the full canonical optimal history relation is the segment (0,s,1,s,1-s), s in [0,1]."};
            const auto same_derivation=[&](const ClaimEvidence& claim) {
                const auto* support=std::get_if<SymbolicArgument>(&claim.support);
                return claim.problem==request.problem.identity()&&support&&support->reference==derivation.reference&&
                    support->assumptions==derivation.assumptions;
            };
            if(!same_derivation(complete.optimum.optimum)||!complete.optimum.bounds.lower||
                !complete.optimum.bounds.upper||complete.optimum.bounds.lower->value!=0||
                complete.optimum.bounds.upper->value!=0||!same_derivation(complete.optimum.bounds.lower->evidence)||
                !same_derivation(complete.optimum.bounds.upper->evidence))
                diagnostics.push_back({DiagnosticCode::evidence_mismatch,"ts01.verifier.optimum",
                    "T-S01 proof must bind the exact analytic optimum and matching zero lower/upper bounds"});
            return diagnostics;
        }};
}
} // namespace csl::synthesis::strategy_ts01
