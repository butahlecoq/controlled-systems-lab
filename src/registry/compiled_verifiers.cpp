#include "compiled_verifiers.hpp"
#include "strategy_b_lineage.hpp"
#include "strategy_a_lineage.hpp"
#include <csl/reachability/nominal_forward.hpp>
#include <csl/synthesis/control_recovery.hpp>
#include <csl/synthesis/terminal_minimizers.hpp>
#include <csl/synthesis/strategy_b/direct_joint.hpp>
#include <csl/synthesis/strategy_ts01/analytic_profile.hpp>
#include <csl/synthesis/ts02_constant_integrator.hpp>
#include <csl/synthesis/ts03_singular_integrator.hpp>
#include <csl/sets/data.hpp>
#include <algorithm>
#include <array>
#include <bit>
#include <cmath>

namespace csl::registry::detail {
namespace {
bool same_configuration(const StrategyConfiguration& left,const StrategyConfiguration& right) noexcept {
    return left.strategy==right.strategy&&left.lp==right.lp&&left.convex==right.convex&&
        left.hull==right.hull&&left.geometry==right.geometry&&left.converter==right.converter&&
        left.approximation==right.approximation&&left.selector==right.selector&&
        left.representation==right.representation;
}
}
StrategyBRuntimeLineageReceipt::StrategyBRuntimeLineageReceipt(const StrategyRequest& binding,
    std::shared_ptr<const synthesis::strategy_b::JointProgram> build_output,
    std::shared_ptr<const ::csl::sets::SetData> feasible_output,
    std::shared_ptr<const ::csl::sets::SetData> extraction_input,
    std::shared_ptr<const ::csl::sets::SetData> extracted_output,
    StrategyRegistration::CompleteFamilyVerifierKey verifier_binding)
    :binding_(binding),build_output_(std::move(build_output)),feasible_output_(std::move(feasible_output)),
     extraction_input_(std::move(extraction_input)),extracted_output_(std::move(extracted_output)),
     verifier_binding_(std::move(verifier_binding)) {}

bool StrategyBRuntimeLineageReceipt::matches(const StrategyRequest& request,const FamilyIdentity& identity,
    const StrategyRegistration::CompleteFamilyVerifierKey& verifier_binding) const {
    if(verifier_binding_.id.value.empty()||verifier_binding_.version.empty()||
        verifier_binding_.id!=verifier_binding.id||verifier_binding_.version!=verifier_binding.version||
        !build_output_||!feasible_output_||!extraction_input_||!extracted_output_)return false;
    const auto feasible_metadata=feasible_output_->metadata();
    const auto extraction_input_metadata=extraction_input_->metadata();
    const auto extracted_metadata=extracted_output_->metadata();
    if(!feasible_metadata||!extraction_input_metadata||!extracted_metadata||
        feasible_output_.get()!=extraction_input_.get()||
        feasible_metadata->id!=extraction_input_metadata->id)return false;
    const auto& prepared=binding_;
    // ResolvedProblem::identity() is the canonical content-derived problem ID.
    if(request.problem.identity()!=prepared.problem.identity()||request.family!=prepared.family||
        !same_configuration(request.configuration,prepared.configuration)||
        request.strategy_version!=prepared.strategy_version||request.lineage!=prepared.lineage||
        identity.problem!=prepared.problem.identity()||identity.request!=prepared.family||
        identity.coordinates!=build_output_->coordinates||
        identity.coordinates!=prepared.problem.constraints().coordinates()||
        identity.strategy!=ModuleId{"csl.synthesis.strategy-b"}||identity.strategy_version!="1"||
        prepared.configuration.strategy!=identity.strategy||prepared.strategy_version!=identity.strategy_version)
        return false;

    const auto problem_id=prepared.problem.identity().value;
    if(verifier_binding_.id.value==synthesis::ts02_constant_integrator_verifier) {
        const auto expected=synthesis::strategy_b::detail::expected_ts02_lineage(prepared.problem.identity());
        return prepared.lineage==expected&&identity.lineage==expected&&
            feasible_metadata->id==SetId{"syn04-feasible:"+problem_id};
    }
    if(verifier_binding_.id.value==synthesis::ts03_singular_integrator_verifier) {
        const auto expected=synthesis::strategy_b::detail::expected_ts03_lineage(prepared.problem.identity());
        return prepared.lineage==expected&&identity.lineage==expected&&
            feasible_metadata->id==SetId{"syn04-feasible:"+problem_id}&&
            extracted_metadata->id==SetId{"syn04-optimal-level:"+problem_id};
    }
    const std::vector<TransformStepIdentity> observed_lineage{
        {{"syn04-build:"+problem_id},{problem_id},feasible_metadata->id,{"csl.synthesis.strategy-b"},"1"},
        {{"syn04-extract:"+problem_id},feasible_metadata->id,extracted_metadata->id,{"csl.synthesis.strategy-b"},"1"}};
    return prepared.lineage==observed_lineage&&identity.lineage==observed_lineage;
}

StrategyARuntimeLineageReceipt::StrategyARuntimeLineageReceipt(const StrategyRequest& binding,
    std::shared_ptr<const reachability::ForwardTube> forward,
    std::shared_ptr<const ::csl::sets::SetData> feasible_terminal,
    std::shared_ptr<const synthesis::JointHistoryRelation> feasible_recovery,
    std::shared_ptr<const synthesis::TerminalMinimizers> terminal,
    std::shared_ptr<const synthesis::JointHistoryRelation> optimal_recovery,
    StrategyRegistration::CompleteFamilyVerifierKey verifier_binding)
    :binding_(binding),forward_(std::move(forward)),feasible_terminal_(std::move(feasible_terminal)),
     feasible_recovery_(std::move(feasible_recovery)),terminal_(std::move(terminal)),
     optimal_recovery_(std::move(optimal_recovery)),verifier_binding_(std::move(verifier_binding)) {}

bool StrategyARuntimeLineageReceipt::matches(const StrategyRequest& request,const FamilyIdentity& identity,
    const StrategyRegistration::CompleteFamilyVerifierKey& verifier_binding) const {
    const bool ts03=strategy_a_ts03_profile_valid(binding_.problem,binding_);
    const bool ts01=strategy_a_ts01_profile_valid(binding_.problem,binding_);
    const auto expected_profile_lineage=ts03?
        synthesis::strategy_a::detail::expected_ts03_lineage(binding_.problem.identity()):
        synthesis::strategy_a::detail::expected_ts01_lineage(binding_.problem.identity());
    if(verifier_binding_.id.value.empty()||verifier_binding_.version.empty()||
        verifier_binding_.id!=verifier_binding.id||verifier_binding_.version!=verifier_binding.version||
        !forward_||!feasible_terminal_||!feasible_recovery_||!terminal_||!optimal_recovery_)return false;
    const auto feasible_terminal_metadata=feasible_terminal_->metadata();
    const auto feasible_recovery_metadata=feasible_recovery_->relation.metadata();
    const auto optimal_recovery_metadata=optimal_recovery_->relation.metadata();
    const auto& prepared=binding_;
    if(request.problem.identity()!=prepared.problem.identity()||request.family!=prepared.family||
        !same_configuration(request.configuration,prepared.configuration)||
        request.strategy_version!=prepared.strategy_version||request.lineage!=prepared.lineage||
        identity.problem!=prepared.problem.identity()||identity.request!=prepared.family||
        identity.coordinates!=prepared.problem.constraints().coordinates()||
        identity.strategy!=ModuleId{"csl.synthesis.reach-back"}||identity.strategy_version!="1"||
        prepared.configuration.strategy!=identity.strategy||prepared.strategy_version!=identity.strategy_version||
        (!ts01&&!ts03)||prepared.lineage!=expected_profile_lineage||
        identity.lineage!=prepared.lineage)
        return false;

    if(forward_->problem!=prepared.problem.identity()||forward_->request!=RequestId{"strategy-a/forward"}||
        forward_->stages.size()!=3||!feasible_terminal_metadata||!feasible_recovery_metadata||
        !optimal_recovery_metadata||feasible_terminal_metadata->id!=forward_->stages.back().marginal.output.id||
        feasible_recovery_->coordinates!=identity.coordinates||optimal_recovery_->coordinates!=identity.coordinates)
        return false;
    const auto expected=prepared.lineage;
    for(std::size_t stage=0;stage<forward_->stages.size();++stage) {
        const auto& actual=forward_->stages[stage];
        const auto& step=expected[stage];
        if(actual.marginal.evidence.reference.identity.request!=step.request||
            actual.source_factors.empty()||actual.source_factors.front()!=step.input||
            actual.marginal.output.id!=step.output)return false;
    }
    if(feasible_recovery_metadata->id!=expected[3].output||
        terminal_->construction.feasible_slice!=feasible_terminal_metadata->id||
        terminal_->termination!=Termination::completed||terminal_->outcome!=MathematicalOutcome::optimal||
        !terminal_->relation||!terminal_->optimization||
        terminal_->relation->metadata()->id!=expected[4].output||
        terminal_->optimization->outcome.value!=MathematicalOutcome::optimal||
        optimal_recovery_metadata->id!=expected[5].output)
        return false;
    return identity.lineage==expected;
}

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
bool matrix_is(const ::csl::numeric::MatrixView& value,std::size_t rows,std::size_t columns,
    std::initializer_list<double> expected) noexcept {
    if(value.rows()!=rows||value.cols()!=columns||expected.size()!=rows*columns)return false;
    auto item=expected.begin();
    for(std::size_t row=0;row<rows;++row)for(std::size_t column=0;column<columns;++column)
        if(value(row,column)!=*item++)return false;
    return true;
}
bool vector_is(const ::csl::numeric::VectorView& value,std::initializer_list<double> expected) noexcept {
    return value.size()==expected.size()&&std::equal(value.values().begin(),value.values().end(),expected.begin());
}
bool control_interval(const AdmissibleSet& set) {
    const auto* handle=std::get_if<SetHandle>(&set);if(!handle)return false;
    auto data=::csl::sets::from_handle(*handle);if(!std::holds_alternative<::csl::sets::SetData>(data))return false;
    const auto& value=std::get<::csl::sets::SetData>(data);
    const auto representation=value.representation();const auto* h=std::get_if<::csl::sets::HRepresentation>(&representation);
    return h&&matrix_is(h->inequalities,2,1,{1,-1})&&vector_is(h->upper_bounds,{1,0})&&
        matrix_is(h->equalities,0,1,{})&&vector_is(h->equality_values,{});
}

bool integrator_case_valid(const ::csl::problem::ResolvedProblem& problem,const FamilyRequest& family,
    const RepresentationId& representation,FamilyTarget target,double state_gain=1) {
    if(family.objective!=problem.identity()||
        family.target!=target||family.assurance!=Assurance::numerical||
        family.representation!=h_polyhedron||family.materialization_limit||representation!=h_polyhedron)
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
        if(!matrix_is(coefficients.A,1,1,{state_gain})||!matrix_is(coefficients.B,1,1,{1})||
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
    return true;
}
bool ts01_case_valid(const ::csl::problem::ResolvedProblem& problem,const FamilyRequest& family,
    const RepresentationId& representation,FamilyTarget target) {
    if(family.profile!=synthesis::strategy_ts01::profile_id||!integrator_case_valid(problem,family,representation,target))return false;
    const auto objective=problem.objective();const auto coefficients=objective.coefficients();
    const auto* quadratic=std::get_if<::csl::optimization::QuadraticCoefficients>(&coefficients);
    return quadratic&&objective.dimension()==1&&matrix_is(quadratic->Q,1,1,{2})&&
        vector_is(quadratic->linear,{-2})&&quadratic->offset==1;
}
bool ts02_constant_objective_valid(const ::csl::problem::ResolvedProblem& problem) {
    const auto objective=problem.objective();const auto coefficients=objective.coefficients();
    return std::visit([](const auto& value) {
        using T=std::decay_t<decltype(value)>;
        if constexpr(std::is_same_v<T,::csl::optimization::LinearCoefficients>)
            return value.coefficients.size()==1&&value.coefficients[0]==0&&value.offset==3;
        else if constexpr(std::is_same_v<T,::csl::optimization::QuadraticCoefficients>)
            return value.Q.rows()==1&&value.Q.cols()==1&&value.Q(0,0)==0&&
                value.linear.size()==1&&value.linear[0]==0&&value.offset==3;
        else return value.map.rows()==1&&value.map.cols()==1&&value.map(0,0)==0&&
            value.target.size()==1&&value.target[0]==3;
    },coefficients);
}
bool ts01_profile_valid(const ::csl::problem::ResolvedProblem& problem,const StrategyRequest& request) {
    return ts01_case_valid(problem,request.family,request.configuration.representation)&&
        request.configuration.strategy.value==synthesis::strategy_ts01::strategy_id;
}
bool ts01_partial_profile_valid(const ::csl::problem::ResolvedProblem& problem,const StrategyRequest& request) {
    return ts01_case_valid(problem,request.family,request.configuration.representation,FamilyTarget::partial_relation)&&
        request.configuration.strategy.value==synthesis::strategy_ts01::strategy_id&&
        (request.strategy_version.empty()||request.strategy_version==synthesis::strategy_ts01::strategy_version)&&
        request.lineage.empty();
}
bool strategy_b_ts01_profile_valid(const ::csl::problem::ResolvedProblem& problem,const StrategyRequest& request) {
    return ts01_case_valid(problem,request.family,request.configuration.representation)&&
        request.configuration.strategy.value=="csl.synthesis.strategy-b"&&request.strategy_version=="1"&&
        request.lineage==synthesis::strategy_b::detail::expected_ts01_lineage(problem.identity());
}
bool strategy_a_ts01_profile_valid(const ::csl::problem::ResolvedProblem& problem,const StrategyRequest& request) {
    return ts01_case_valid(problem,request.family,request.configuration.representation)&&
        request.configuration.strategy.value=="csl.synthesis.reach-back"&&request.strategy_version=="1"&&
        request.lineage==synthesis::strategy_a::detail::expected_ts01_lineage(problem.identity());
}
bool strategy_b_ts02_profile_valid(const ::csl::problem::ResolvedProblem& problem,const StrategyRequest& request) {
    return ts02_case_valid(problem,request.family,request.configuration.representation)&&request.configuration.strategy.value=="csl.synthesis.strategy-b"&&
        request.strategy_version=="1"&&request.lineage==synthesis::strategy_b::detail::expected_ts02_lineage(problem.identity());
}
bool strategy_a_ts02_profile_valid(const ::csl::problem::ResolvedProblem& problem,const StrategyRequest& request) {
    return ts02_case_valid(problem,request.family,request.configuration.representation)&&request.configuration.strategy.value=="csl.synthesis.reach-back"&&
        request.strategy_version=="1"&&
        request.lineage==synthesis::strategy_a::detail::expected_ts02_lineage(problem.identity());
}
bool strategy_b_ts03_profile_valid(const ::csl::problem::ResolvedProblem& problem,const StrategyRequest& request) {
    return ts03_case_valid(problem,request.family,request.configuration.representation)&&
        request.configuration.strategy.value=="csl.synthesis.strategy-b"&&request.strategy_version=="1"&&
        request.lineage==synthesis::strategy_b::detail::expected_ts03_lineage(problem.identity());
}

bool ts02_case_valid(const ::csl::problem::ResolvedProblem& problem,const FamilyRequest& family,
    const RepresentationId& representation) {
    return family.profile==synthesis::ts02_constant_integrator_profile&&
        family.target==FamilyTarget::exact_optimal_relation&&
        integrator_case_valid(problem,family,representation,FamilyTarget::exact_optimal_relation)&&
        ts02_constant_objective_valid(problem);
}
bool ts03_case_valid(const ::csl::problem::ResolvedProblem& problem,const FamilyRequest& family,
    const RepresentationId& representation) {
    if(family.profile!=synthesis::ts03_singular_integrator_profile||
        !integrator_case_valid(problem,family,representation,FamilyTarget::exact_optimal_relation,0))return false;
    const auto objective=problem.objective();const auto coefficients=objective.coefficients();
    const auto* quadratic=std::get_if<::csl::optimization::QuadraticCoefficients>(&coefficients);
    return quadratic&&objective.dimension()==1&&matrix_is(quadratic->Q,1,1,{2})&&
        vector_is(quadratic->linear,{-2})&&quadratic->offset==1;
}
bool strategy_a_ts03_profile_valid(const ::csl::problem::ResolvedProblem& problem,const StrategyRequest& request) {
    return ts03_case_valid(problem,request.family,request.configuration.representation)&&
        request.configuration.strategy.value=="csl.synthesis.reach-back"&&request.strategy_version=="1"&&
        request.lineage==synthesis::strategy_a::detail::expected_ts03_lineage(problem.identity());
}

}
namespace csl::synthesis::strategy_ts01 {
std::variant<std::shared_ptr<const ExactJointRelation>,Diagnostics> ExactJointRelation::canonical() {
    auto inequalities=::csl::numeric::snapshot(SparseMatrix{4,5,{0,1,2,3,4},{3,3,4,4},{1,-1,1,-1}});
    auto upper=::csl::numeric::snapshot_vector(Vector{1,0,1,0});
    auto equalities=::csl::numeric::snapshot(SparseMatrix{4,5,{0,1,3,4,6},{0,1,3,2,3,4},{1,1,-1,1,1,1}});
    auto equality_values=::csl::numeric::snapshot_vector(Vector{0,0,1,1});
    if(!std::holds_alternative<::csl::numeric::MatrixView>(inequalities)||
        !std::holds_alternative<::csl::numeric::VectorView>(upper)||
        !std::holds_alternative<::csl::numeric::MatrixView>(equalities)||
        !std::holds_alternative<::csl::numeric::VectorView>(equality_values))
        return Diagnostics{{DiagnosticCode::invalid_input,"ts01.relation","Could not construct exact H-representation buffers"}};
    auto data=::csl::sets::make_h({{"ts01-optimal-histories"},5,{"x0","x1","x2","u0","u1"}},
        {std::get<::csl::numeric::MatrixView>(inequalities),std::get<::csl::numeric::VectorView>(upper),
         std::get<::csl::numeric::MatrixView>(equalities),std::get<::csl::numeric::VectorView>(equality_values)});
    if(!std::holds_alternative<::csl::sets::SetData>(data))
        return Diagnostics{{DiagnosticCode::invalid_input,"ts01.relation","The canonical optimal histories are not a valid H-polyhedron"}};
    auto value=std::get<::csl::sets::SetData>(std::move(data));
    return std::shared_ptr<const ExactJointRelation>(new ExactJointRelation(std::move(value)));
}
ExactJointRelation::ExactJointRelation(::csl::sets::SetData h_polyhedron):h_polyhedron_(std::move(h_polyhedron)) {}
bool ExactJointRelation::contains(std::span<const double> point) const noexcept {
    if(point.size()!=5||std::any_of(point.begin(),point.end(),[](double value){return !std::isfinite(value);}))return false;
    return point[0]==0&&point[1]==point[3]&&point[2]==1&&point[3]>=0&&point[3]<=1&&
        point[4]>=0&&point[4]<=1&&::csl::registry::detail::exact_sum_is_one(point[3],point[4]);
}


}
namespace csl::registry::detail {
namespace {
class Ts01Verifier final : public CompiledCompleteFamilyVerifier {
public:
    const ModuleId& id() const noexcept override { static const ModuleId value{"csl.verifier.ts01-analytic"}; return value; }
    const std::string& version() const noexcept override { static const std::string value{"1"}; return value; }
    Diagnostics verify(const StrategyRequest& request,const CompleteFamilyProposal& proposal) const override {
        Diagnostics diagnostics;
        const bool standalone=ts01_profile_valid(request.problem,request);
        const bool strategy_b=strategy_b_ts01_profile_valid(request.problem,request);
        const bool strategy_a=strategy_a_ts01_profile_valid(request.problem,request);
        if(!standalone&&!strategy_b&&!strategy_a)
            return {{DiagnosticCode::unsupported,"ts01.verifier.profile","Verifier rejected a noncanonical resolved problem or effective request"}};
        const auto expected_strategy=standalone?synthesis::strategy_ts01::strategy_id:
            strategy_b?"csl.synthesis.strategy-b":"csl.synthesis.reach-back";
        const auto expected_version=standalone?synthesis::strategy_ts01::strategy_version:"1";
        const auto& identity=proposal.identity;const auto& complete=proposal.family;
        const auto exact_identity=identity.problem==request.problem.identity()&&identity.request==request.family&&
            identity.coordinates==request.problem.constraints().coordinates()&&
            identity.strategy==request.configuration.strategy&&identity.strategy_version==request.strategy_version&&
            identity.lineage==request.lineage&&identity.strategy.value==expected_strategy&&
            identity.strategy_version==expected_version&&(!standalone||identity.lineage.empty());
        if(!exact_identity||complete.completeness.binding!=identity||
            complete.relation.coordinates!=identity.coordinates||complete.relation.representation!=request.family.representation||
            complete.assurance!=request.family.assurance||request.family.assurance!=Assurance::numerical)
            diagnostics.push_back({DiagnosticCode::evidence_mismatch,"ts01.verifier.binding","T-S01 proof must bind the selected strategy, effective request, authoritative problem, coordinates and lineage"});
        const auto* proof=std::get_if<RegisteredCompletenessEvidence>(&complete.completeness.support);
        if(!proof||proof->verifier.value!="csl.verifier.ts01-analytic"||
            proof->verifier_version!=synthesis::strategy_ts01::strategy_version||proof->proof!="TS01-analytic-v1")
            diagnostics.push_back({DiagnosticCode::evidence_mismatch,"ts01.verifier.support","T-S01 proof requires the registered opaque analytic payload"});
        const auto* relation=dynamic_cast<const synthesis::strategy_ts01::ExactJointRelation*>(complete.relation.payload.get());
        if(!relation||!relation->contains(Vector{0,0,1,0,1})||!relation->contains(Vector{0,1,1,1,0})||
            relation->h_polyhedron().metadata()->coordinate_labels!=std::vector<std::string>{"x0","x1","x2","u0","u1"})
            diagnostics.push_back({DiagnosticCode::evidence_mismatch,"ts01.verifier.relation","T-S01 proof does not contain the exact canonical optimal-history relation"});
        const SymbolicArgument derivation{"T-S01 exact analytic derivation",
            "x2=u0+u1 and (x2-1)^2>=0; zero is attained exactly when u0+u1=1. With u0,u1 in [0,1], the full canonical optimal history relation is the segment (0,s,1,s,1-s), s in [0,1]."};
        const auto same_derivation=[&](const ClaimEvidence& claim) {
            const auto* support=std::get_if<SymbolicArgument>(&claim.support);
            return claim.problem==request.problem.identity()&&support&&support->reference==derivation.reference&&support->assumptions==derivation.assumptions;
        };
        if(!same_derivation(complete.optimum.optimum)||!complete.optimum.bounds.lower||!complete.optimum.bounds.upper||
            complete.optimum.bounds.lower->value!=0||complete.optimum.bounds.upper->value!=0||
            !same_derivation(complete.optimum.bounds.lower->evidence)||!same_derivation(complete.optimum.bounds.upper->evidence))
            diagnostics.push_back({DiagnosticCode::evidence_mismatch,"ts01.verifier.optimum","T-S01 proof must bind the exact analytic optimum and matching zero lower/upper bounds"});
        return diagnostics;
    }
};
class Ts02ConstantIntegratorVerifier final : public CompiledCompleteFamilyVerifier {
public:
    const ModuleId& id() const noexcept override {
        static const ModuleId value{synthesis::ts02_constant_integrator_verifier};return value;
    }
    const std::string& version() const noexcept override { static const std::string value{"1"};return value; }
    Diagnostics verify(const StrategyRequest& request,const CompleteFamilyProposal& proposal) const override {
        Diagnostics diagnostics;
        const bool strategy_b=strategy_b_ts02_profile_valid(request.problem,request);
        const bool strategy_a=strategy_a_ts02_profile_valid(request.problem,request);
        if(!strategy_b&&!strategy_a)
            return {{DiagnosticCode::unsupported,"ts02.verifier.profile",
                "Verifier only admits the exact constant-objective two-step integrator profile and registered strategy lineage."}};
        const auto& identity=proposal.identity;const auto& complete=proposal.family;
        if(identity.problem!=request.problem.identity()||identity.request!=request.family||
            identity.coordinates!=request.problem.constraints().coordinates()||
            identity.strategy!=request.configuration.strategy||identity.strategy_version!=request.strategy_version||
            identity.lineage!=request.lineage||complete.completeness.binding!=identity||
            complete.relation.coordinates!=identity.coordinates||
            complete.relation.representation!=request.family.representation||
            complete.assurance!=Assurance::numerical)
            diagnostics.push_back({DiagnosticCode::evidence_mismatch,"ts02.verifier.binding",
                "T-S02 proof must bind the exact resolved problem, effective request, strategy, coordinates and frozen lineage."});
        const auto* proof=std::get_if<RegisteredCompletenessEvidence>(&complete.completeness.support);
        if(!proof||proof->verifier!=id()||proof->verifier_version!=version()||
            proof->proof!=synthesis::ts02_constant_integrator_proof)
            diagnostics.push_back({DiagnosticCode::evidence_mismatch,"ts02.verifier.support",
                "T-S02 proof requires the registered constant-integrator analytic payload."});
        const auto* relation=dynamic_cast<const synthesis::Ts02ConstantIntegratorRelation*>(complete.relation.payload.get());
        bool exact_relation=false;
        if(relation) {
            const auto& set=relation->h_polyhedron();const auto metadata=set.metadata();
            const auto representation=set.representation();const auto* h=std::get_if<::csl::sets::HRepresentation>(&representation);
            exact_relation=metadata&&metadata->id==SetId{"ts02-optimal-histories"}&&metadata->set.dimension==5&&
                metadata->coordinate_labels==std::vector<std::string>{"x0","x1","x2","u0","u1"}&&h&&
                matrix_is(h->inequalities,4,5,{0,0,0,1,0, 0,0,0,-1,0, 0,0,0,0,1, 0,0,0,0,-1})&&
                vector_is(h->upper_bounds,{1,0,1,0})&&
                matrix_is(h->equalities,3,5,{1,0,0,0,0, -1,1,0,-1,0, 0,-1,1,0,-1})&&
                vector_is(h->equality_values,{0,0,0});
        }
        if(!exact_relation)
            diagnostics.push_back({DiagnosticCode::evidence_mismatch,"ts02.verifier.relation",
                "T-S02 relation must be the exact canonical feasible joint-history H-polyhedron."});
        // Keep this canonical verifier statement independent from the producer's
        // separately authored claim so their agreement is still checked.
        const SymbolicArgument derivation{"T-S02 exact constant-objective derivation",
            "For x0=0, x1=x0+u0, x2=x1+u1 and u0,u1 in [0,1], every feasible history has terminal objective 3. Therefore the argmin relation is exactly the full feasible joint-history polyhedron."};
        const auto same_claim=[&](const ClaimEvidence& claim) {
            const auto* support=std::get_if<SymbolicArgument>(&claim.support);
            return claim.problem==request.problem.identity()&&support&&support->reference==derivation.reference&&
                support->assumptions==derivation.assumptions;
        };
        if(!same_claim(complete.optimum.optimum)||!complete.optimum.bounds.lower||!complete.optimum.bounds.upper||
            complete.optimum.bounds.lower->value!=3||complete.optimum.bounds.upper->value!=3||
            !same_claim(complete.optimum.bounds.lower->evidence)||!same_claim(complete.optimum.bounds.upper->evidence))
            diagnostics.push_back({DiagnosticCode::evidence_mismatch,"ts02.verifier.optimum",
                "T-S02 proof must bind the exact constant objective and equal lower/upper bounds of 3."});
        return diagnostics;
    }
};
class Ts03SingularIntegratorVerifier final : public CompiledCompleteFamilyVerifier {
public:
    const ModuleId& id() const noexcept override {
        static const ModuleId value{synthesis::ts03_singular_integrator_verifier};return value;
    }
    const std::string& version() const noexcept override { static const std::string value{"1"};return value; }
    Diagnostics verify(const StrategyRequest& request,const CompleteFamilyProposal& proposal) const override {
        const bool strategy_a=strategy_a_ts03_profile_valid(request.problem,request);
        const bool strategy_b=strategy_b_ts03_profile_valid(request.problem,request);
        if(!strategy_a&&!strategy_b)
            return {{DiagnosticCode::unsupported,"ts03.verifier.profile",
                "Verifier only admits the exact singular-integrator profile and a registered Strategy A or Strategy B lineage."}};
        Diagnostics diagnostics;const auto& identity=proposal.identity;const auto& complete=proposal.family;
        if(identity.problem!=request.problem.identity()||identity.request!=request.family||
            identity.coordinates!=request.problem.constraints().coordinates()||
            identity.strategy!=request.configuration.strategy||identity.strategy_version!=request.strategy_version||
            identity.lineage!=request.lineage||complete.completeness.binding!=identity||
            complete.relation.coordinates!=identity.coordinates||
            complete.relation.representation!=request.family.representation||complete.assurance!=Assurance::numerical)
            diagnostics.push_back({DiagnosticCode::evidence_mismatch,"ts03.verifier.binding",
                "T-S03 proof must bind the exact resolved problem, request, strategy, coordinates and frozen lineage."});
        const auto* proof=std::get_if<RegisteredCompletenessEvidence>(&complete.completeness.support);
        if(!proof||proof->verifier!=id()||proof->verifier_version!=version()||
            proof->proof!=synthesis::ts03_singular_integrator_proof)
            diagnostics.push_back({DiagnosticCode::evidence_mismatch,"ts03.verifier.support",
                "T-S03 proof requires the registered singular-integrator analytic payload."});
        const auto* relation=dynamic_cast<const synthesis::Ts03SingularIntegratorRelation*>(complete.relation.payload.get());
        bool exact_relation=false;
        if(relation) {
            const auto& set=relation->h_polyhedron();const auto metadata=set.metadata();
            const auto representation=set.representation();const auto* h=std::get_if<::csl::sets::HRepresentation>(&representation);
            exact_relation=metadata&&metadata->id==SetId{"ts03-singular-optimal-histories"}&&metadata->set.dimension==5&&
                metadata->coordinate_labels==std::vector<std::string>{"x0","x1","x2","u0","u1"}&&h&&
                matrix_is(h->inequalities,2,5,{0,0,0,1,0, 0,0,0,-1,0})&&
                vector_is(h->upper_bounds,{1,0})&&
                matrix_is(h->equalities,4,5,{1,0,0,0,0, 0,1,0,-1,0, 0,0,1,0,0, 0,0,0,0,1})&&
                vector_is(h->equality_values,{0,0,1,1});
        }
        if(!exact_relation)
            diagnostics.push_back({DiagnosticCode::evidence_mismatch,"ts03.verifier.relation",
                "T-S03 relation must be the exact canonical full optimal-history line."});
        const SymbolicArgument derivation{"T-S03 exact singular-integrator derivation",
            "For x1=u0 and x2=u1, the terminal objective (x2-1)^2 is nonnegative and equals zero exactly when x2=u1=1. Thus x0=0, x1=u0, x2=1, u1=1, and 0<=u0<=1 describe the entire optimal joint-history relation."};
        const auto same_claim=[&](const ClaimEvidence& claim) {
            const auto* support=std::get_if<SymbolicArgument>(&claim.support);
            return claim.problem==request.problem.identity()&&support&&support->reference==derivation.reference&&
                support->assumptions==derivation.assumptions;
        };
        if(!same_claim(complete.optimum.optimum)||!complete.optimum.bounds.lower||!complete.optimum.bounds.upper||
            complete.optimum.bounds.lower->value!=0||complete.optimum.bounds.upper->value!=0||
            !same_claim(complete.optimum.bounds.lower->evidence)||!same_claim(complete.optimum.bounds.upper->evidence))
            diagnostics.push_back({DiagnosticCode::evidence_mismatch,"ts03.verifier.optimum",
                "T-S03 proof must bind the exact analytic optimum and matching zero lower/upper bounds."});
        return diagnostics;
    }
};
class Ts01MidpointVerifier final : public CompiledPartialFamilyVerifier {
public:
    const ModuleId& id() const noexcept override { static const ModuleId value{"csl.verifier.ts01-midpoint"}; return value; }
    const std::string& version() const noexcept override { static const std::string value{"1"}; return value; }
    Diagnostics verify(const StrategyRequest& request,const PartialFamilyProposal& proposal) const override {
        Diagnostics diagnostics;
        if(!ts01_partial_profile_valid(request.problem,request))
            return {{DiagnosticCode::unsupported,"ts01.partial.profile","Verifier only admits the exact nominal T-S01 partial profile"}};
        const auto& identity=proposal.identity;
        const auto& partial=proposal.family;
        if(identity.problem!=request.problem.identity()||identity.request!=request.family||
            identity.coordinates!=request.problem.constraints().coordinates()||
            identity.strategy!=request.configuration.strategy||identity.strategy_version!=request.strategy_version||
            identity.lineage!=request.lineage||identity.strategy!=ModuleId{synthesis::strategy_ts01::strategy_id}||
            identity.strategy_version!=synthesis::strategy_ts01::strategy_version||
            identity.request.target!=FamilyTarget::partial_relation||
            partial.relation.coordinates!=identity.coordinates||
            partial.relation.representation!=request.family.representation)
            diagnostics.push_back({DiagnosticCode::evidence_mismatch,"ts01.partial.binding",
                "Midpoint proof must bind the prepared problem, partial request, joint coordinates, analytic strategy and ordered lineage"});
        const auto* midpoint=dynamic_cast<const synthesis::strategy_ts01::MidpointJointRelation*>(partial.relation.payload.get());
        bool exact_relation=false;
        if(midpoint) {
            const auto metadata=midpoint->h_polyhedron().metadata();
            const auto representation=midpoint->h_polyhedron().representation();
            const auto* h=std::get_if<::csl::sets::HRepresentation>(&representation);
            exact_relation=metadata&&metadata->id==SetId{"ts01-midpoint-history"}&&
                metadata->coordinate_labels==std::vector<std::string>{"x0","x1","x2","u0","u1"}&&h&&
                h->inequalities.rows()==0&&h->inequalities.cols()==5&&h->upper_bounds.size()==0&&
                matrix_is(h->equalities,5,5,{1,0,0,0,0,0,1,0,0,0,0,0,1,0,0,0,0,0,1,0,0,0,0,0,1})&&
                vector_is(h->equality_values,{0,0.5,1,0.5,0.5});
        }
        if(!exact_relation)
            diagnostics.push_back({DiagnosticCode::evidence_mismatch,"ts01.partial.relation",
                "Partial T-S01 payload must be exactly the singleton (0,1/2,1,1/2,1/2) in canonical coordinates"});
        const SymbolicArgument optimum{"T-S01 exact midpoint optimality",
            "The resolved objective is (x2-1)^2, so it is nonnegative for every feasible history. At the feasible midpoint history x2=1, hence the objective equals zero and the global optimum is zero."};
        const SymbolicArgument membership{"T-S01 exact midpoint singleton",
            "At s=1/2, (x0,x1,x2,u0,u1)=(0,1/2,1,1/2,1/2) satisfies both dynamics equations and both control bounds. Its exact objective is (1-1)^2=0, while the objective is nonnegative for every feasible history."};
        const auto same_claim=[&](const ClaimEvidence& claim,const SymbolicArgument& proof) {
            const auto* actual=std::get_if<SymbolicArgument>(&claim.support);
            return claim.problem==request.problem.identity()&&actual&&
                actual->reference==proof.reference&&actual->assumptions==proof.assumptions;
        };
        if(!same_claim(partial.optimum.optimum,optimum)||!partial.optimum.bounds.lower||!partial.optimum.bounds.upper||
            partial.optimum.bounds.lower->value!=0||partial.optimum.bounds.upper->value!=0||
            !same_claim(partial.optimum.bounds.lower->evidence,optimum)||
            !same_claim(partial.optimum.bounds.upper->evidence,optimum)||
            !same_claim(partial.optimal_subset.every_history_optimal,membership)||
            partial.optimal_subset.procedure!="T-S01 exact midpoint singleton"||
            partial.known_scope.description!="s=1/2")
            diagnostics.push_back({DiagnosticCode::evidence_mismatch,"ts01.partial.optimality",
                "Partial claim must bind the exact zero optimum, singleton membership proof and explicit scope s=1/2"});
        return diagnostics;
    }
};
#ifdef CSL_TEST_VERIFIER_CATALOG
class TestCatalogVerifier final : public CompiledCompleteFamilyVerifier {
public:
    const ModuleId& id() const noexcept override { static const ModuleId value{"test.verifier.second"}; return value; }
    const std::string& version() const noexcept override { static const std::string value{"7"}; return value; }
    Diagnostics verify(const StrategyRequest& request,const CompleteFamilyProposal& proposal) const override {
        const auto& identity=proposal.identity;const auto& complete=proposal.family;
        const auto* proof=std::get_if<RegisteredCompletenessEvidence>(&complete.completeness.support);
        const auto* claim=std::get_if<SymbolicArgument>(&complete.optimum.optimum.support);
        if(request.configuration.strategy.value!="test.strategy.second"||request.strategy_version!="7"||
            identity.problem!=request.problem.identity()||identity.request!=request.family||
            identity.coordinates!=request.problem.constraints().coordinates()||identity.strategy!=request.configuration.strategy||
            identity.strategy_version!=request.strategy_version||!identity.lineage.empty()||
            complete.completeness.binding!=identity||complete.relation.coordinates!=identity.coordinates||
            complete.relation.representation!=request.family.representation||complete.assurance!=Assurance::numerical||
            !proof||proof->verifier!=id()||proof->verifier_version!=version()||proof->proof!="second-verifier-proof"||
            !claim||claim->reference!="second verifier theorem"||complete.optimum.optimum.problem!=identity.problem||
            !complete.optimum.bounds.lower||!complete.optimum.bounds.upper||
            complete.optimum.bounds.lower->value!=2||complete.optimum.bounds.upper->value!=2)
            return {{DiagnosticCode::evidence_mismatch,"test.verifier.second","Compiled second verifier rejected the proposal"}};
        return {};
    }
};
class ThirdTestCatalogVerifier final : public CompiledCompleteFamilyVerifier {
public:
    const ModuleId& id() const noexcept override { static const ModuleId value{"test.verifier.third"}; return value; }
    const std::string& version() const noexcept override { static const std::string value{"8"}; return value; }
    Diagnostics verify(const StrategyRequest& request,const CompleteFamilyProposal& proposal) const override {
        const auto* proof=std::get_if<RegisteredCompletenessEvidence>(&proposal.family.completeness.support);
        if(request.family.profile!="profile-b"||!proof||proof->verifier!=id()||
            proof->verifier_version!=version()||proof->proof!="third-verifier-proof")
            return {{DiagnosticCode::evidence_mismatch,"test.verifier.third","Compiled third verifier rejected the proposal"}};
        return {};
    }
};
#endif
}
std::shared_ptr<const CompiledCompleteFamilyVerifier> find_compiled_verifier(const ModuleId& id,const std::string& version) {
    static const auto ts01=std::make_shared<const Ts01Verifier>();
    if(id==ts01->id()&&version==ts01->version())return ts01;
    static const auto ts02=std::make_shared<const Ts02ConstantIntegratorVerifier>();
    if(id==ts02->id()&&version==ts02->version())return ts02;
    static const auto ts03=std::make_shared<const Ts03SingularIntegratorVerifier>();
    if(id==ts03->id()&&version==ts03->version())return ts03;
    static const auto nominal_linear_exact=make_nominal_linear_exact_verifier();
    if(id==nominal_linear_exact->id()&&version==nominal_linear_exact->version())return nominal_linear_exact;
#ifdef CSL_TEST_VERIFIER_CATALOG
    static const auto second=std::make_shared<const TestCatalogVerifier>();
    if(id==second->id()&&version==second->version())return second;
    static const auto third=std::make_shared<const ThirdTestCatalogVerifier>();
    if(id==third->id()&&version==third->version())return third;
#endif
    return {};
}
std::shared_ptr<const CompiledPartialFamilyVerifier> find_compiled_partial_verifier(const ModuleId& id,const std::string& version) {
    static const auto ts01=std::make_shared<const Ts01MidpointVerifier>();
    if(id==ts01->id()&&version==ts01->version())return ts01;
    return {};
}
std::variant<std::shared_ptr<const synthesis::strategy_ts01::ExactJointRelation>,Diagnostics> make_ts01_relation() {
    return synthesis::strategy_ts01::ExactJointRelation::canonical();
}
}
