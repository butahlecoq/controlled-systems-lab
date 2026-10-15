#define DOCTEST_CONFIG_IMPLEMENT
#include <doctest/doctest.h>
#include <csl/adapters/lp/highs.hpp>
#include <csl/optimization/lp_backend.hpp>
#include <csl/optimization/linear_infeasibility_certificate.hpp>
#include <algorithm>
#include <cmath>
#include <iomanip>
#include <iostream>
#include <limits>
#include <locale>
#include <sstream>

using namespace csl;
using namespace csl::optimization;
using namespace csl::registry;
namespace {
constexpr NumericalPolicy policy{1e-8,1e-8};
const Verifier oracle{{"test05.literal"},"1"};
template<class T,class... R> T take(std::variant<T,R...> value) {
    REQUIRE(std::holds_alternative<T>(value));
    return std::get<T>(std::move(value));
}
struct Case {
    LinearProgramInput input;
    MathematicalOutcome outcome;
    std::optional<Vector> point;
    std::optional<double> cost;
    bool face{};
    std::optional<double> authored_maximum;
    std::optional<DualMultipliers> dual;
};
// Independently derived literals: full objective negation, equality substitution,
// contradictory rows, improving ray and the whole optimal segment. JSON is
// independently authored; --dump-catalogue exports these actual runner inputs.
// Triangle: x+2y <= 2(x+y) <= 2; equality requires (0,1). Negating
// x+2y+7 includes its offset, giving canonical -9 and authored maximum9.
// y=-2 and 2x-y=6 force x=2, cost7. Scaling the row by1024 changes
// neither point nor cost; shifting offset11 to-2 changes only cost to-6.
// x<=0 and x>=1 contradict, even with redundant2x<=0. The ray x=t>=0
// makes -x unbounded. On the face, 5-x-y>=4, attained for the whole
// nonnegative segment x+y=1; no selected endpoint or family is required.
const std::vector<Case>& cases() {
    static const std::vector<Case> data{
        {{{{"test05"},{"triangle"}},{-1,-2},0,{1,2,{0,2},{0,1},{1,1}},{{0,{}},{0,{}}},{{{},1}}},
            MathematicalOutcome::optimal,Vector{0,1},-2,false,{},DualMultipliers{{0},{2},{1,0},{0,0}}},
        {{{{"test05"},{"max-offset"}},{-1,-2},-7,{1,2,{0,2},{0,1},{1,1}},{{0,{}},{0,{}}},{{{},1}}},
            MathematicalOutcome::optimal,Vector{0,1},-9,false,9,DualMultipliers{{0},{2},{1,0},{0,0}}},
        {{{{"test05"},{"free-fixed-equality"}},{1,3},11,{1,2,{0,2},{0,1},{2,-1}},{{{},{}},{-2,-2}},{{6,6}}},
            MathematicalOutcome::optimal,Vector{2,-2},7,false,{},DualMultipliers{{0.5},{0},{0,3.5},{0,0}}},
        {{{{"test05"},{"contradictory-redundant"}},{0},0,{3,1,{0,1,2,3},{0,0,0},{1,1,2}},{{{},{}}},{{{},0},{1,{}},{{},0}}},
            MathematicalOutcome::infeasible,{},{},false,{},{}},
        {{{{"test05"},{"unbounded"}},{-1},0,{0,1,{0},{},{}},{{0,{}}},{}},
            MathematicalOutcome::unbounded,{},{},false,{},{}},
        {{{{"test05"},{"degenerate-face"}},{-1,-1},5,{3,2,{0,2,4,6},{0,1,0,1,0,1},{1,1,2,2,1,1}},{{0,{}},{0,{}}},{{{},1},{{},2},{0,{}}}},
            MathematicalOutcome::optimal,{},4,true,{},DualMultipliers{{0,0,0},{1,0,0},{0,0},{0,0}}},
        {{{{"test05"},{"scaled-equality"}},{1,3},11,{1,2,{0,2},{0,1},{2048,-1024}},{{{},{}},{-2,-2}},{{6144,6144}}},
            MathematicalOutcome::optimal,Vector{2,-2},7,false,{},DualMultipliers{{0.00048828125},{0},{0,3.5},{0,0}}},
        {{{{"test05"},{"shifted-offset"}},{1,3},-2,{1,2,{0,2},{0,1},{2,-1}},{{{},{}},{-2,-2}},{{6,6}}},
            MathematicalOutcome::optimal,Vector{2,-2},-6,false,{},DualMultipliers{{0.5},{0},{0,3.5},{0,0}}}
    };
    return data;
}
bool same_bounds(std::span<const Interval> a,std::span<const Interval> b) {
    if(a.size()!=b.size()) return false;
    for(std::size_t i=0;i<a.size();++i) if(a[i].lower!=b[i].lower || a[i].upper!=b[i].upper) return false;
    return true;
}
bool published_as(const LinearProgram& p,const LinearProgramInput& a) {
    const auto csr=std::get<numeric::CsrInput>(p.constraints().descriptor());
    return p.identity()==a.identity && p.offset()==a.offset &&
        std::ranges::equal(p.objective().values(),a.objective) &&
        csr.rows==a.constraints.rows && csr.cols==a.constraints.cols &&
        std::ranges::equal(csr.row_offsets,a.constraints.row_offsets) &&
        std::ranges::equal(csr.column_indices,a.constraints.column_indices) &&
        std::ranges::equal(csr.values,a.constraints.values) &&
        same_bounds(p.rows(),a.rows) && same_bounds(p.variables(),a.variables);
}
// Independent tiny arithmetic over the public views, not evaluate_primal/multiply.
struct Primal {double cost; ResidualMeasure rows{0,1},variables{0,1};};
ResidualMeasure violations(std::span<const double> values,std::span<const Interval> bounds) {
    REQUIRE(values.size()==bounds.size());
    double worst=0,scale=1;
    for(std::size_t i=0;i<values.size();++i) {
        scale=std::max(scale,std::abs(values[i]));
        for(const auto endpoint:{bounds[i].lower,bounds[i].upper}) if(endpoint) scale=std::max(scale,std::abs(*endpoint));
        if(bounds[i].lower && values[i]<*bounds[i].lower) worst=std::max(worst,*bounds[i].lower-values[i]);
        if(bounds[i].upper && values[i]>*bounds[i].upper) worst=std::max(worst,values[i]-*bounds[i].upper);
    }
    return {worst,scale};
}
Primal primal(const LinearProgram& p,std::span<const double> x) {
    REQUIRE(x.size()==p.objective().size());
    Primal answer{p.offset()};
    Vector activity(p.rows().size(),0);
    const auto csr=std::get<numeric::CsrInput>(p.constraints().descriptor());
    for(std::size_t j=0;j<x.size();++j) answer.cost+=p.objective()[j]*x[j];
    for(std::size_t i=0;i<activity.size();++i)
        for(auto k=csr.row_offsets[i];k<csr.row_offsets[i+1];++k) activity[i]+=csr.values[k]*x[csr.column_indices[k]];
    answer.rows=violations(activity,p.rows());answer.variables=violations(x,p.variables());
    return answer;
}
bool passes(ResidualMeasure m) {return std::isfinite(m.violation) && std::isfinite(m.scale) && m.violation<=policy.absolute_tolerance+policy.relative_tolerance*m.scale;}
bool close_number(double a,double b) {return std::isfinite(a) && std::isfinite(b) && std::abs(a-b)<=1e-8+1e-8*std::max(std::abs(a),std::abs(b));}
bool optimum(const Case& c,const LinearProgram& p,const ProgramResult& r) {
    if(r.termination!=Termination::completed || r.outcome.value!=c.outcome || !r.primal || !c.cost) return false;
    if(r.primal->size()!=p.variables().size()) return false;
    const auto a=primal(p,*r.primal);
    if(!passes(a.rows) || !passes(a.variables) || !close_number(a.cost,*c.cost)) return false;
    if(c.point) {
        if(c.point->size()!=r.primal->size()) return false;
        for(std::size_t j=0;j<c.point->size();++j) if(!close_number((*r.primal)[j],(*c.point)[j])) return false;
    }
    return !c.face || (r.primal->size()==2 && (*r.primal)[0]>=-1e-8 && (*r.primal)[1]>=-1e-8 && close_number((*r.primal)[0]+(*r.primal)[1],1));
}
void check_context(const ResidualContext& c,const LinearProgram& p) {
    CHECK(c.subject==p.identity()); CHECK(c.absolute_tolerance==policy.absolute_tolerance);
    CHECK(c.relative_tolerance==policy.relative_tolerance);
    CHECK_FALSE(c.verifier.id.value.empty());CHECK_FALSE(c.verifier.version.empty());
}
void check_measure(ResidualMeasure actual,ResidualMeasure expected) {
    CHECK(actual.violation==doctest::Approx(expected.violation).epsilon(1e-12));
    CHECK(actual.scale==doctest::Approx(expected.scale).epsilon(1e-12));
}
void check_candidate(const LinearProgram& p,const ProgramResult& r) {
    if(r.primal) {
        const auto actual=primal(p,*r.primal);
        if(r.residuals.primal) {
            check_context(r.residuals.primal->context,p);
            check_measure(r.residuals.primal->rows,actual.rows);
            check_measure(r.residuals.primal->variables,actual.variables);
        }
    } else CHECK_FALSE(r.residuals.primal);
}
using Factory=std::function<std::variant<Registration<LPPort>,Diagnostics>()>;
struct Adapter {
    Method method;
    Factory factory;
    bool optimum_dual;
    // Absence means bounds/basis must be unavailable. A future provider must
    // supply its independent bound proof and dedicated original-row basis oracle.
    std::function<void(const Case&,const LinearProgram&,const ProgramResult&)> bounds;
    std::function<void(const PreparedPipeline<LPPort>&)> basis;
    Factory limited;
};
std::vector<Adapter> selected() {
    return {{{{"csl.lp.highs"},"1.0.0+highs.1.11.0"},
        []{return adapters::lp::make_highs_registration();},true,{},{},
        []{return adapters::lp::make_highs_registration({0});}}};
}
Requirements requirements(bool basis=false) {Requirements r;r.output.representation={"csl.program-result.v1"};r.basis_diagnostics=basis;return r;}
auto preparation(const Adapter& a,const LinearProgram& p,bool basis=false) {
    Registry<LPPort> registry;
    REQUIRE_FALSE(registry.add(take<Registration<LPPort>>(a.factory())));
    return prepare_pipeline(select(registry,a.method,p,requirements(basis)));
}
auto prepared(const Adapter& a,const LinearProgram& p,bool basis=false) {
    auto plan=take<PreparedPipeline<LPPort>>(preparation(a,p,basis));
    const auto provenance=plan.provenance()[0];
    CHECK(provenance.port=="lp");CHECK(provenance.requested.id.value==a.method.id.value);
    REQUIRE(provenance.actual);CHECK(provenance.actual->id.value==a.method.id.value);
    REQUIRE(a.method.version);CHECK(provenance.actual->version==*a.method.version);
    return plan;
}
ExecutionContext context() {return {{},{},{},policy,"test05"};}
void attempt(const BoundWorkspace<LPPort>& w,const LinearProgram& p,std::uint64_t number) {
    REQUIRE(w.last_attempt()); CHECK(w.last_attempt()->state==SolveAttemptState::returned_result);
    CHECK(w.last_attempt()->stamp.attempt()==number);CHECK(w.last_attempt()->stamp.program().identity()==p.identity());
    CHECK(w.last_attempt()->stamp.workspace()==w.workspace_identity());
}
} // namespace
TEST_CASE("each selected registration satisfies the same eight neutral literal LP cases") {
    for(const auto& a:selected()) for(const auto& c:cases()) {
        INFO(a.method.id.value << " / " << c.input.identity.program.value);
        const auto p=take<LinearProgram>(make_linear_program(c.input)); REQUIRE(published_as(p,c.input));
        auto plan=prepared(a,p);auto [worker]=plan.create();auto [other]=plan.create();
        CHECK_FALSE(worker->workspace_identity()==other->workspace_identity());
        CHECK_FALSE(worker->last_attempt());CHECK_FALSE(other->last_attempt());
        if(!a.basis) CHECK(worker->basis()==nullptr);
        const auto result=take<ProgramResult>(worker->run(context()));
        INFO(result.raw_diagnostics);
        attempt(*worker,p,1);CHECK_FALSE(other->last_attempt());
        CHECK(result.termination==Termination::completed);CHECK(result.outcome.value==c.outcome);
        CHECK(result.outcome.subject==p.identity());
        if(a.method.id.value=="csl.lp.highs"&&c.outcome==MathematicalOutcome::infeasible) {
            REQUIRE(std::holds_alternative<ExactFarkasEvidence>(result.outcome.support));
            const auto& proof=std::get<ExactFarkasEvidence>(result.outcome.support);
            const auto verified=verify_linear_infeasibility_certificate(p,proof.certificate());
            REQUIRE(std::holds_alternative<ExactFarkasEvidence>(verified));
            CHECK(std::get<ExactFarkasEvidence>(verified).certificate()==proof.certificate());
        } else CHECK(std::holds_alternative<Unestablished>(result.outcome.support));
        CHECK(check_program_result(result,p,Assurance::numerical).empty());check_candidate(p,result);
        // Necessary inequalities never replace a provider's independent proof.
        if(c.cost && result.objective.lower) CHECK(result.objective.lower->value<=*c.cost+1e-8);
        if(c.cost && result.objective.upper) CHECK(result.objective.upper->value>=*c.cost-1e-8);
        if(a.bounds) a.bounds(c,p,result);
        else {CHECK_FALSE(result.objective.lower);CHECK_FALSE(result.objective.upper);}
        if(c.outcome==MathematicalOutcome::optimal) {
            REQUIRE(result.primal);REQUIRE(result.residuals.primal);CHECK(optimum(c,p,result));
            if(c.authored_maximum) CHECK(-primal(p,*result.primal).cost==doctest::Approx(*c.authored_maximum));
            if(a.optimum_dual) {
                REQUIRE(result.residuals.dual);check_context(result.residuals.dual->context,p);
                REQUIRE(result.residuals.dual->stationarity);REQUIRE(result.residuals.dual->signs);
                CHECK(passes(*result.residuals.dual->stationarity));CHECK(passes(*result.residuals.dual->signs));
                CHECK_FALSE(result.residuals.dual->complementarity);
            }
        }
        if(a.basis) a.basis(prepared(a,p,true));
        else {
            CHECK(worker->basis()==nullptr);
            CHECK(std::holds_alternative<Rejection>(preparation(a,p,true)));
        }
        worker.reset();other.reset();
        CHECK(result.outcome.subject==p.identity());check_candidate(p,result);
    }
}

namespace {
struct Probe {Vector point;ResidualMeasure rows,variables;bool accepted;};
const std::vector<Probe>& probes() {
    static const std::vector<Probe> values{
        {{0,1.0000000298023223876953125},{2.98023223876953125e-8,1.0000000298023223876953125},{0,1.0000000298023223876953125},false},
        {{-2.98023223876953125e-8,1},{0,1},{2.98023223876953125e-8,1},false},
        {{0,1.000000007450580596923828125},{7.450580596923828125e-9,1.000000007450580596923828125},{0,1.000000007450580596923828125},true}
    };return values;
}
struct DualAnswer {Vector stationarity;double constant;};
DualAnswer dual_arithmetic(const LinearProgram& p,const DualMultipliers& m) {
    const auto csr=std::get<numeric::CsrInput>(p.constraints().descriptor());
    DualAnswer result{{},p.offset()};
    for(std::size_t j=0;j<p.variables().size();++j) {
        double gradient=p.objective()[j]-m.variable_lower[j]+m.variable_upper[j];
        for(std::size_t i=0;i<p.rows().size();++i)
            for(auto k=csr.row_offsets[i];k<csr.row_offsets[i+1];++k)
                if(csr.column_indices[k]==j) gradient+=csr.values[k]*(m.row_upper[i]-m.row_lower[i]);
        result.stationarity.push_back(gradient);
    }
    for(std::size_t i=0;i<p.rows().size();++i) {
        if(p.rows()[i].lower) result.constant+=*p.rows()[i].lower*m.row_lower[i];
        if(p.rows()[i].upper) result.constant-=*p.rows()[i].upper*m.row_upper[i];
    }
    for(std::size_t j=0;j<p.variables().size();++j) {
        if(p.variables()[j].lower) result.constant+=*p.variables()[j].lower*m.variable_lower[j];
        if(p.variables()[j].upper) result.constant-=*p.variables()[j].upper*m.variable_upper[j];
    }
    return result;
}
struct PartialExpectation {Vector point;double lower,upper;};
const PartialExpectation& partial_expected() {static const PartialExpectation e{{0,0},-2,0};return e;}
class PartialWorkspace final:public LPWorkspace {
    std::shared_ptr<int> destroyed_;
    ProgramOutcome do_solve(const LinearProgram& p,const ExecutionContext& c) override {
        if(!published_as(p,cases()[0].input)) return Unsupported{{{DiagnosticCode::unsupported,"fixture","triangle only"}}};
        const auto& e=partial_expected();
        ProgramResult result{Termination::resource_limit,{p.identity(),MathematicalOutcome::undetermined,Unestablished{},{}},e.point,
            {ProgramObjectiveBound{e.lower,{p.identity(),SymbolicArgument{"test05.triangle.lower","x+2y <= 2(x+y) <= 2"},{"fixture only"}}},
             ProgramObjectiveBound{e.upper,{p.identity(),SymbolicArgument{"test05.triangle.incumbent","(0,0) is feasible and costs 0"},{"fixture only"}}}},
            "Restricted test fixture; no native solve or certificate"};
        result.residuals.primal=take<PrimalEvaluation>(evaluate_primal(p,e.point,c.numerical,oracle)).residuals;
        return result;
    }
public:
    explicit PartialWorkspace(std::shared_ptr<int> destroyed):destroyed_(std::move(destroyed)) {}
    ~PartialWorkspace() override {++*destroyed_;}
};
Adapter partial_adapter(const std::shared_ptr<int>& destroyed) {
    return {{{"test05.partial-fixture"},"1"},[destroyed]() -> std::variant<Registration<LPPort>,Diagnostics> {
        return Registration<LPPort>{{{"test05.partial-fixture"},"1"},
            [](const LinearProgram& p,const Requirements& r)->Capability {
                if(!published_as(p,cases()[0].input) || r.scalar!=Scalar::binary64)
                    return Diagnostics{{DiagnosticCode::unsupported,"fixture","only the original triangle in binary64"}};
                return Offer{{{"csl.program-result.v1"},Assurance::numerical,{},{},Completeness::unestablished}};
            },[destroyed](const LinearProgram&) {return std::make_unique<PartialWorkspace>(destroyed);}};
    },false,{},{},{}};
}
bool partial_matches(const LinearProgram& p,const ProgramResult& r) {
    if(r.termination!=Termination::resource_limit || r.outcome.value!=MathematicalOutcome::undetermined ||
       r.outcome.subject!=p.identity() || !std::holds_alternative<Unestablished>(r.outcome.support) ||
       !r.primal || !r.objective.lower || !r.objective.upper) return false;
    const auto& lower=*r.objective.lower;const auto& upper=*r.objective.upper;
    if(lower.evidence.subject!=p.identity() || upper.evidence.subject!=p.identity() ||
       !std::holds_alternative<SymbolicArgument>(lower.evidence.support) ||
       !std::holds_alternative<SymbolicArgument>(upper.evidence.support)) return false;
    if(r.primal->size()!=p.variables().size()) return false;
    const auto witness=primal(p,*r.primal);
    const auto proof=dual_arithmetic(p,*cases()[0].dual);
    return passes(witness.rows) && passes(witness.variables) &&
        std::ranges::all_of(proof.stationarity,[](double x){return x==0;}) &&
        lower.value==proof.constant && upper.value==witness.cost && lower.value<upper.value;
}
} // namespace
TEST_CASE("literal dyadic candidates detect row and variable violations instead of an always-true oracle") {
    const auto p=take<LinearProgram>(make_linear_program(cases()[0].input));
    for(const auto& probe:probes()) {
        const auto evaluated=take<PrimalEvaluation>(evaluate_primal(p,probe.point,policy,oracle));
        const auto direct=primal(p,probe.point);
        check_measure(evaluated.residuals.rows,probe.rows);check_measure(evaluated.residuals.variables,probe.variables);
        check_measure(direct.rows,probe.rows);check_measure(direct.variables,probe.variables);
        CHECK((passes(direct.rows) && passes(direct.variables))==probe.accepted);
        CHECK((passes(evaluated.residuals.rows) && passes(evaluated.residuals.variables))==probe.accepted);
    }
    auto [worker]=prepared(selected()[0],p).create();const auto good=take<ProgramResult>(worker->run(context()));
    REQUIRE(optimum(cases()[0],p,good));
    auto changed=good;changed.primal=Vector{0,0};CHECK_FALSE(optimum(cases()[0],p,changed));
    changed=good;changed.primal=Vector{0,1.25};CHECK_FALSE(optimum(cases()[0],p,changed));
}
TEST_CASE("six literal dual constants include offset equality scaling and absent endpoints") {
    std::size_t exercised=0;
    for(const auto& c:cases()) if(c.dual) {
        INFO(c.input.identity.program.value);++exercised;
        const auto p=take<LinearProgram>(make_linear_program(c.input));
        const auto direct=dual_arithmetic(p,*c.dual);
        REQUIRE(c.cost);CHECK(direct.constant==*c.cost);
        for(double coordinate:direct.stationarity) CHECK(coordinate==0);
        const auto result=take<DualEvaluation>(evaluate_dual(p,*c.dual,policy,oracle));
        CHECK(result.lagrangian_constant==*c.cost);check_context(result.residuals.context,p);
        REQUIRE(result.residuals.stationarity);REQUIRE(result.residuals.signs);
        CHECK(result.residuals.stationarity->violation==0);CHECK(result.residuals.signs->violation==0);
        CHECK_FALSE(result.residuals.complementarity);
        auto wrong=*c.dual;wrong.variable_lower[0]=-1;
        // The triangle's lower endpoint exists; a negative multiplier is a sign
        // residual, whereas a nonzero multiplier on free x is invalid input.
        const auto invalid=evaluate_dual(p,wrong,policy,oracle);
        if(p.variables()[0].lower) {
            const auto bad=take<DualEvaluation>(invalid);REQUIRE(bad.residuals.signs);
            CHECK(bad.residuals.signs->violation==1);CHECK_FALSE(passes(*bad.residuals.signs));
        } else CHECK(std::holds_alternative<Diagnostics>(invalid));
    }
    CHECK(exercised==6);
    const auto p=take<LinearProgram>(make_linear_program(cases()[0].input));
    auto absent=*cases()[0].dual;absent.row_lower[0]=1;
    const auto rejected=evaluate_dual(p,absent,policy,oracle);
    REQUIRE(std::holds_alternative<Diagnostics>(rejected));CHECK_FALSE(std::get<Diagnostics>(rejected).empty());
}
TEST_CASE("documented native zero iteration limit remains an undetermined resource stop") {
    const auto p=take<LinearProgram>(make_linear_program(cases()[0].input));
    for(auto a:selected()) {
        REQUIRE(static_cast<bool>(a.limited));a.factory=a.limited;
        auto [worker]=prepared(a,p).create();const auto r=take<ProgramResult>(worker->run(context()));
        CHECK(r.termination==Termination::resource_limit);CHECK(r.outcome.value==MathematicalOutcome::undetermined);
        CHECK_FALSE(optimum(cases()[0],p,r));CHECK(std::holds_alternative<Unestablished>(r.outcome.support));
        CHECK_FALSE(r.objective.lower);CHECK_FALSE(r.objective.upper);
        CHECK(check_program_result(r,p,Assurance::numerical).empty());check_candidate(p,r);attempt(*worker,p,1);
    }
}
TEST_CASE("restricted registered stopped fixture retains independently justified bounds and owning history") {
    const auto p=take<LinearProgram>(make_linear_program(cases()[0].input));
    auto destroyed=std::make_shared<int>(0);const auto a=partial_adapter(destroyed);
    auto plan=prepared(a,p);auto [worker]=plan.create();
    const auto first=take<ProgramResult>(worker->run(context()));attempt(*worker,p,1);
    const auto old_attempt=*worker->last_attempt();
    REQUIRE(partial_matches(p,first));REQUIRE(first.objective.lower);REQUIRE(first.objective.upper);
    CHECK(first.objective.lower->value==-2);CHECK(first.objective.upper->value==0);
    CHECK(*first.primal==Vector{0,0});CHECK(check_program_result(first,p,Assurance::numerical).empty());check_candidate(p,first);
    CHECK_FALSE(first.residuals.dual);CHECK(worker->basis()==nullptr);
    CHECK(std::holds_alternative<Rejection>(preparation(a,p,true)));
    const auto second=take<ProgramResult>(worker->run(context()));attempt(*worker,p,2);CHECK(partial_matches(p,second));
    CHECK(old_attempt.stamp.attempt()==1);CHECK(old_attempt.stamp.workspace()==worker->workspace_identity());
    CHECK(old_attempt.stamp.program().identity()==p.identity());
    auto counterfeit=first;counterfeit.outcome.value=MathematicalOutcome::optimal;CHECK_FALSE(partial_matches(p,counterfeit));
    counterfeit.termination=Termination::completed;CHECK_FALSE(optimum(cases()[0],p,counterfeit));
    counterfeit=first;counterfeit.outcome.value=MathematicalOutcome::infeasible;CHECK_FALSE(partial_matches(p,counterfeit));
    counterfeit=first;counterfeit.objective.lower->value=0;CHECK_FALSE(partial_matches(p,counterfeit));
    counterfeit=first;counterfeit.objective.upper->value=-1;CHECK_FALSE(partial_matches(p,counterfeit));
    counterfeit=first;counterfeit.objective.lower->evidence.subject.program.value="wrong-program";
    CHECK_FALSE(check_program_result(counterfeit,p,Assurance::numerical).empty());CHECK_FALSE(partial_matches(p,counterfeit));
    for(std::size_t i=1;i<cases().size();++i) {
        const auto other=take<LinearProgram>(make_linear_program(cases()[i].input));
        CHECK(std::holds_alternative<Rejection>(preparation(a,other)));
    }
    auto changed=cases()[0].input;changed.identity.program.value="changed-triangle";changed.offset=1;
    CHECK(std::holds_alternative<Rejection>(preparation(a,take<LinearProgram>(make_linear_program(changed)))));
    worker.reset();CHECK(*destroyed==1);CHECK(partial_matches(p,first));CHECK(partial_matches(p,second));
    CHECK(old_attempt.stamp.program().offset()==0);
}

namespace {
std::string quote(std::string_view text) {
    constexpr char hex[]="0123456789abcdef";std::string out="\"";
    for(unsigned char c:text) {
        if(c=='"' || c=='\\') {out+='\\';out+=static_cast<char>(c);}
        else if(c<32) {out+="\\u00";out+=hex[c>>4];out+=hex[c&15];}
        else out+=static_cast<char>(c);
    }
    return out+'"';
}
std::string number(double n) {
    if(!std::isfinite(n)) throw std::invalid_argument("nonfinite catalogue number");
    std::ostringstream out;out.imbue(std::locale::classic());out<<std::setprecision(std::numeric_limits<double>::max_digits10)<<n;return out.str();
}
std::string optional_number(std::optional<double> n) {return n?number(*n):"null";}
template<class Range,class Encode> std::string array(const Range& items,Encode encode) {
    std::string result="[";bool first=true;
    for(const auto& item:items) {if(!first) result+=',';first=false;result+=encode(item);}return result+']';
}
template<class Range> std::string numbers(const Range& v) {return array(v,[](auto n){return number(static_cast<double>(n));});}
std::string bounds(const std::vector<Interval>& values) {
    return array(values,[](const auto& b){return '['+optional_number(b.lower)+','+optional_number(b.upper)+']';});
}
std::string outcome_name(MathematicalOutcome value) {
    switch(value) {
        case MathematicalOutcome::optimal:return "optimal";
        case MathematicalOutcome::infeasible:return "infeasible";
        case MathematicalOutcome::unbounded:return "unbounded";
        case MathematicalOutcome::infimum_not_attained:return "infimum_not_attained";
        case MathematicalOutcome::undetermined:return "undetermined";
    }
    throw std::invalid_argument("unknown outcome");
}
std::string catalogue_json() {
    const auto records=array(cases(),[](const Case& c) {
        const auto& p=c.input;const auto& a=p.constraints;
        std::string dual="null";
        if(c.dual) dual="{\"row_lower\":"+numbers(c.dual->row_lower)+",\"row_upper\":"+numbers(c.dual->row_upper)+
            ",\"variable_lower\":"+numbers(c.dual->variable_lower)+",\"variable_upper\":"+numbers(c.dual->variable_upper)+",\"constant\":"+optional_number(c.cost)+'}';
        return "{\"program\":"+quote(p.identity.program.value)+",\"problem\":"+quote(p.identity.problem.value)+
            ",\"objective\":"+numbers(p.objective)+",\"offset\":"+number(p.offset)+
            ",\"csr\":{\"rows\":"+std::to_string(a.rows)+",\"cols\":"+std::to_string(a.cols)+
            ",\"starts\":"+numbers(a.row_offsets)+",\"indices\":"+numbers(a.column_indices)+",\"values\":"+numbers(a.values)+
            "},\"variables\":"+bounds(p.variables)+",\"rows\":"+bounds(p.rows)+
            ",\"termination\":\"completed\",\"outcome\":"+quote(outcome_name(c.outcome))+
            ",\"point\":"+(c.point?numbers(*c.point):"null")+",\"cost\":"+optional_number(c.cost)+
            ",\"face\":"+(c.face?"true":"false")+",\"authored_maximum\":"+optional_number(c.authored_maximum)+",\"dual\":"+dual+'}';
    });
    const auto checks=array(probes(),[](const Probe& p) {
        return "{\"point\":"+numbers(p.point)+",\"rows\":["+number(p.rows.violation)+','+number(p.rows.scale)+
            "],\"variables\":["+number(p.variables.violation)+','+number(p.variables.scale)+"],\"accepted\":"+(p.accepted?"true":"false")+'}';
    });
    const auto& e=partial_expected();
    return "{\"format\":\"csl.test05.analytic-lp/1\",\"purpose\":\"independent-test-oracles\",\"cases\":"+records+
        ",\"partial\":{\"program\":"+quote(cases()[0].input.identity.program.value)+
        ",\"termination\":\"resource_limit\",\"outcome\":\"undetermined\",\"candidate\":"+numbers(e.point)+
        ",\"lower\":"+number(e.lower)+",\"upper\":"+number(e.upper)+",\"support\":\"fixture-symbolic-argument\"},\"primal_checks\":"+checks+'}';
}
} // namespace

int main(int argc,char** argv) {
    if(argc==2 && std::string_view(argv[1])=="--dump-catalogue") {std::cout<<catalogue_json()<<'\n';return 0;}
    doctest::Context tests;tests.applyCommandLine(argc,argv);return tests.run();
}
