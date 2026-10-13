#include "compiled_verifiers.hpp"
#include <csl/synthesis/strategy_ts01/analytic_profile.hpp>
#include <algorithm>
#include <array>
#include <bit>
#include <cmath>

namespace csl::registry::detail {
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

bool ts01_profile_valid(const ::csl::problem::ResolvedProblem& problem,const StrategyRequest& request) {
    const auto& family=request.family;
    if(family.profile!=synthesis::strategy_ts01::profile_id||family.objective!=problem.identity()||
        family.target!=FamilyTarget::exact_optimal_relation||family.assurance!=Assurance::numerical||
        family.representation!=h_polyhedron||family.materialization_limit||
        request.configuration.strategy.value!=synthesis::strategy_ts01::strategy_id||request.configuration.representation!=h_polyhedron)
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
    const auto* quadratic=std::get_if<::csl::optimization::QuadraticCoefficients>(&coefficients);
    return quadratic&&objective.dimension()==1&&matrix_is(quadratic->Q,1,1,{2})&&
        vector_is(quadratic->linear,{-2})&&quadratic->offset==1;
}

}
namespace csl::synthesis::strategy_ts01 {
std::variant<std::shared_ptr<const ExactJointRelation>,Diagnostics> ExactJointRelation::canonical() {
    auto inequalities=::csl::numeric::snapshot(Matrix{4,5,{0,0,0,1,0, 0,0,0,-1,0,
        0,0,0,0,1, 0,0,0,0,-1}});
    auto upper=::csl::numeric::snapshot_vector(Vector{1,0,1,0});
    auto equalities=::csl::numeric::snapshot(Matrix{4,5,{1,0,0,0,0, 0,1,0,-1,0,
        0,0,1,0,0, 0,0,0,1,1}});
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
        if(!ts01_profile_valid(request.problem,request))
            return {{DiagnosticCode::unsupported,"ts01.verifier.profile","Verifier rejected a noncanonical resolved problem or effective request"}};
        const auto& identity=proposal.identity;const auto& complete=proposal.family;
        const auto exact_identity=identity.problem==request.problem.identity()&&identity.request==request.family&&
            identity.coordinates==request.problem.constraints().coordinates()&&
            identity.strategy==request.configuration.strategy&&identity.strategy_version==request.strategy_version&&
            identity.lineage==request.lineage&&identity.lineage.empty()&&request.lineage.empty();
        if(!exact_identity||complete.completeness.binding!=identity||
            complete.relation.coordinates!=identity.coordinates||complete.relation.representation!=request.family.representation||
            complete.assurance!=request.family.assurance||request.family.assurance!=Assurance::numerical||
            identity.strategy.value!=synthesis::strategy_ts01::strategy_id||
            identity.strategy_version!=synthesis::strategy_ts01::strategy_version)
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
#endif
}
std::shared_ptr<const CompiledCompleteFamilyVerifier> find_compiled_verifier(const ModuleId& id,const std::string& version) {
    static const auto ts01=std::make_shared<const Ts01Verifier>();
    if(id==ts01->id()&&version==ts01->version())return ts01;
#ifdef CSL_TEST_VERIFIER_CATALOG
    static const auto second=std::make_shared<const TestCatalogVerifier>();
    if(id==second->id()&&version==second->version())return second;
#endif
    return {};
}
std::variant<std::shared_ptr<const synthesis::strategy_ts01::ExactJointRelation>,Diagnostics> make_ts01_relation() {
    return synthesis::strategy_ts01::ExactJointRelation::canonical();
}
}
