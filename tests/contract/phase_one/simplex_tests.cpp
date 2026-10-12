#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <csl/optimization/phase_one.hpp>
#ifdef CSL_PHASE_ONE_REFERENCE
#include <csl/adapters/lp/highs.hpp>
#endif
#include <limits>
#include <cmath>
#include <stdexcept>
#include <future>
#include <thread>
using namespace csl;
using namespace csl::optimization;
using namespace csl::registry;
namespace po = csl::optimization::phase_one;
namespace {
template<class T,class... R> T accepted(std::variant<T,R...> value) {
    REQUIRE(std::holds_alternative<T>(value)); return std::get<T>(std::move(value));
}
ExecutionContext context() {return {{},{},{},{1e-8,0},"phase-one-test"};}
Requirements requirements(bool basis=true) {
    Requirements r;r.output.representation={"csl.program-result.v1"};r.basis_diagnostics=basis;return r;
}
auto prepare(const LinearProgram& p,po::Options options={}) {
    Registry<LPPort> registry;
    REQUIRE_FALSE(registry.add(accepted(po::make_registration(std::move(options)))).has_value());
    return accepted(prepare_pipeline(select(registry,{{"phase-one-bland"},{}},p,requirements())));
}
LinearProgram triangle(Vector b={.25,.25,1},std::string id="interior") {
    return accepted(po::make_program({{"triangle"},{std::move(id)}},{3,3,{0,1,2,5},{1,2,0,1,2},{1,1,1,1,1}},b));
}
po::Snapshot report(const BoundWorkspace<LPPort>& w) {
    const auto* d=dynamic_cast<const po::DiagnosticsView*>(w.basis());REQUIRE(d);
    auto s=accepted(d->phase_one_snapshot());REQUIRE(w.last_attempt());
    CHECK(s.solve==w.last_attempt()->stamp);return s;
}
void candidate(const ProgramResult& result,const LinearProgram& p,const Vector& expected) {
    INFO(result.raw_diagnostics);REQUIRE(result.primal);REQUIRE(result.primal->size()==expected.size());
    for(std::size_t i=0;i<expected.size();++i) CHECK((*result.primal)[i]==doctest::Approx(expected[i]));
    CHECK(result.termination==Termination::completed);CHECK(result.outcome.value==MathematicalOutcome::optimal);
    CHECK(result.outcome.subject==p.identity());CHECK(std::holds_alternative<Unestablished>(result.outcome.support));
    CHECK_FALSE(result.objective.lower);CHECK_FALSE(result.objective.upper);
    const auto check=accepted(evaluate_primal(p,*result.primal,{1e-8,0},{{"independent-original"},"1"}));
    CHECK(check.objective==0);CHECK(check.residuals.rows.violation<1e-8);CHECK(check.residuals.variables.violation==0);
    CHECK(check_program_result(result,p,Assurance::numerical).empty());
}
}
TEST_CASE("phase one publication owns original equality and nonnegative coefficients") {
    SparseMatrix a{1,1,{0,1},{0},{-2}}; Vector b{-4};
    const auto p=accepted(po::make_program({{"signed"},{"equality"}},a,b));
    a.values[0]=99;b[0]=99;
    CHECK(p.constraints()(0,0)==-2);CHECK(p.rows()[0].lower==std::optional<double>{-4});
    CHECK(p.rows()[0].upper==p.rows()[0].lower);CHECK(p.variables()[0].lower==std::optional<double>{0});
    CHECK_FALSE(p.variables()[0].upper);CHECK(p.objective()[0]==0);CHECK(p.offset()==0);
    CHECK(p.identity().program.value=="equality");
    const auto r=accepted(evaluate_primal(p,Vector{2},{1e-8,0},{{"literal"},"1"}));
    CHECK(r.objective==0);CHECK(r.residuals.rows.violation==0);CHECK(r.residuals.variables.violation==0);
    CHECK(std::holds_alternative<Diagnostics>(po::make_program({{"p"},{"bad"}},a,{})));
    a.values[0]=std::numeric_limits<double>::infinity();
    CHECK(std::holds_alternative<Diagnostics>(po::make_program({{"p"},{"bad"}},a,b)));
}
TEST_CASE("registered triangle gives literal coefficients auxiliary trace and original basis") {
    const auto p=triangle();auto [w]=prepare(p).create();
    CHECK(std::holds_alternative<BasisUnavailable>(w->basis()->snapshot()));
    candidate(accepted(w->run(context())),p,{.5,.25,.25});
    const auto s=report(*w);REQUIRE(s.auxiliary);CHECK(s.auxiliary->value==0);
    CHECK(s.pivots==3);CHECK(s.degenerate_pivots==0);REQUIRE(s.trace.size()==3);
    const std::size_t slots[]={2,0,1}, leaves[]={2,0,1};
    const double steps[]={1,.25,.25}, before[]={1.5,.5,.25}, after[]={.5,.25,0};
    for(std::size_t i=0;i<3;++i) {
        CHECK(std::get<po::StructuralVariable>(s.trace[i].entering).column==i);
        CHECK(std::get<po::ArtificialVariable>(s.trace[i].leaving).row==leaves[i]);
        CHECK(s.trace[i].leaving_position==slots[i]);CHECK(s.trace[i].coefficient==1);
        CHECK(s.trace[i].step==steps[i]);CHECK(s.trace[i].auxiliary_before==before[i]);CHECK(s.trace[i].auxiliary_after==after[i]);
    }
    const auto basis=accepted(w->basis()->snapshot());CHECK(check_basis_snapshot(basis,w->last_attempt()).empty());
    REQUIRE(basis.columns.size()==3);CHECK(std::get<StructuralColumn>(basis.columns[0]).index==1);
    CHECK(std::get<StructuralColumn>(basis.columns[1]).index==2);CHECK(std::get<StructuralColumn>(basis.columns[2]).index==0);
    const auto coords=accepted(w->basis()->coordinates(basis.reference,Vector{.25,.25,1}));
    CHECK(coords.values==Vector{.25,.25,.5});CHECK(check_basis_coordinates(coords,basis,w->last_attempt()).empty());
}
TEST_CASE("signed triangle has literal degenerate pivot and original row signs") {
    const auto p=accepted(po::make_program({{"signed"},{"triangle"}},
        {3,3,{0,3,6,9},{0,1,2,0,1,2,0,1,2},{-1,1,-1,-1,-1,1,1,1,1}},Vector{-.5,-.5,1}));
    auto [w]=prepare(p).create();candidate(accepted(w->run(context())),p,{.5,.25,.25});
    const auto s=report(*w);REQUIRE(s.normalization);CHECK(s.normalization->signs==std::vector<int>{-1,-1,1});
    CHECK(s.pivots==3);CHECK(s.degenerate_pivots==1);REQUIRE(s.trace.size()==3);
    const double coef[]={1,2,2},step[]={.5,0,.25},before[]={2,.5,.5},after[]={.5,.5,0};
    for(std::size_t i=0;i<3;++i) {
        CHECK(s.trace[i].coefficient==coef[i]);CHECK(s.trace[i].step==step[i]);
        CHECK(s.trace[i].auxiliary_before==before[i]);CHECK(s.trace[i].auxiliary_after==after[i]);
        CHECK(std::get<po::ArtificialVariable>(s.trace[i].leaving).row==i);
    }
}
TEST_CASE("edge outside and duplicate ties retain uncertainty and least basic index") {
    const auto edge=triangle({.5,0,1},"edge");auto [e]=prepare(edge).create();candidate(accepted(e->run(context())),edge,{.5,.5,0});
    const auto outside=triangle({1,1,1},"outside");auto [w]=prepare(outside).create();const auto r=accepted(w->run(context()));
    CHECK(r.termination==Termination::completed);CHECK(r.outcome.value==MathematicalOutcome::infeasible);
    CHECK(std::holds_alternative<Unestablished>(r.outcome.support));CHECK_FALSE(r.objective.lower);CHECK_FALSE(r.objective.upper);
    REQUIRE(r.primal);CHECK(*r.primal==Vector{0,1,0});REQUIRE(r.residuals.primal);CHECK(r.residuals.primal->rows.violation==1);
    const auto s=report(*w);REQUIRE(s.auxiliary);CHECK(s.auxiliary->value==1);REQUIRE(s.trace.size()==2);
    CHECK(std::get<po::StructuralVariable>(s.trace[1].leaving).column==0);CHECK(s.trace[1].leaving_position==2);
    const auto dup=accepted(po::make_program({{"ties"},{"duplicate"}},{2,2,{0,2,4},{0,1,0,1},{1,1,1,1}},Vector{1,1}));
    auto [d]=prepare(dup).create();candidate(accepted(d->run(context())),dup,{1,0});
    const auto ds=report(*d);REQUIRE(ds.trace.size()==1);CHECK(std::get<po::ArtificialVariable>(ds.trace[0].leaving).row==0);
}
TEST_CASE("empty homogeneous rank deficient and contradictory rows remain representable") {
    for(std::size_t n:{0U,2U}) {
        const auto p=accepted(po::make_program({{"empty"},{n==0?"rows-no-columns":"rows-two-columns"}},{0,n,{0},{},{}},{}));
        auto [w]=prepare(p).create();candidate(accepted(w->run(context())),p,Vector(n,0));
        const auto s=report(*w);CHECK(s.pivots==0);CHECK(s.factorizations==0);REQUIRE(s.auxiliary);CHECK(s.auxiliary->value==0);
        const auto b=accepted(w->basis()->snapshot());CHECK(b.columns.empty());CHECK(accepted(w->basis()->coordinates(b.reference,{})).values.empty());
    }
    for(const Vector rhs:{Vector{0,0},Vector{-2,0}}) {
        const auto p=accepted(po::make_program({{"empty"},{rhs[0]==0?"columns-feasible":"columns-infeasible"}},{2,0,{0,0,0},{},{}},rhs));auto [w]=prepare(p).create();
        const auto r=accepted(w->run(context()));CHECK(r.termination==Termination::completed);
        CHECK(r.outcome.value==(rhs[0]==0?MathematicalOutcome::optimal:MathematicalOutcome::infeasible));
        CHECK(report(*w).auxiliary->value==std::abs(rhs[0]));
    }
    for(double last:{0.,1.}) {
        const auto p=accepted(po::make_program({{"rows"},{last==0?"zero-feasible":"zero-infeasible"}},{3,1,{0,1,2,2},{0,0},{1,1}},Vector{2,2,last}));auto [w]=prepare(p).create();
        const auto r=accepted(w->run(context()));CHECK(r.outcome.value==(last==0?MathematicalOutcome::optimal:MathematicalOutcome::infeasible));
        CHECK(report(*w).auxiliary->value==last);CHECK(accepted(w->basis()->snapshot()).columns.size()==3);
        if(last==0) candidate(r,p,{2});
    }
    const auto p=accepted(po::make_program({{"flat"},{"embedded"}},
        {4,3,{0,2,2,5,8},{0,2,0,1,2,0,1,2},{-1,1,2,2,2,1,1,1}},Vector{.5,0,2,1}));
    auto [w]=prepare(p).create();candidate(accepted(w->run(context())),p,{0,.5,.5});
    CHECK(accepted(w->basis()->snapshot()).columns.size()==4);
}
TEST_CASE("signed basis coordinates and stale attempts use original column space") {
    const auto p=accepted(po::make_program({{"signed"},{"basis"}},{1,1,{0,1},{0},{-2}},Vector{-4}));auto [w]=prepare(p).create();
    candidate(accepted(w->run(context())),p,{2});const auto b=accepted(w->basis()->snapshot());REQUIRE(b.last_pivot);
    CHECK(b.last_pivot->coefficient==2);CHECK(std::get<AuxiliaryColumn>(b.last_pivot->leaving).coefficients==Vector{-1});
    CHECK(accepted(w->basis()->coordinates(b.reference,Vector{-6})).values==Vector{3});
    candidate(accepted(w->run(context())),p,{2});
    CHECK(std::get<BasisUnavailable>(w->basis()->coordinates(b.reference,Vector{-6})).reason==BasisUnavailableReason::stale_reference);
    CHECK_FALSE(check_basis_snapshot(b,w->last_attempt()).empty());
}
TEST_CASE("pivot caps public observer cancellation and exception preserve truthful attempts") {
    const auto p=triangle();
    for(std::uint64_t cap:{0U,1U}) {
        po::Options o;o.pivot_limit=cap;auto [w]=prepare(p,o).create();const auto r=accepted(w->run(context()));
        CHECK(r.termination==Termination::resource_limit);CHECK(r.outcome.value==MathematicalOutcome::undetermined);
        const auto s=report(*w);CHECK(s.pivots==cap);CHECK(s.reason==po::Reason::pivot_limit);CHECK(s.auxiliary->value==(cap==0?1.5:.5));
    }
    std::stop_source stop;po::Options o;o.pivot_observer=[&](const po::PivotEvent& event){CHECK(event.iteration==1);stop.request_stop();};
    auto [w]=prepare(p,o).create();auto c=context();c.cancellation=stop.get_token();const auto r=accepted(w->run(c));
    CHECK(r.termination==Termination::cancelled);CHECK(r.outcome.value==MathematicalOutcome::undetermined);CHECK(report(*w).pivots==1);
    auto [pre]=prepare(p).create();CHECK(accepted(pre->run(c)).termination==Termination::cancelled);
    CHECK(report(*pre).pivots==0);CHECK_FALSE(report(*pre).auxiliary);CHECK(std::holds_alternative<BasisUnavailable>(pre->basis()->snapshot()));
    c=context();c.deadline=std::chrono::steady_clock::now()-std::chrono::seconds(1);
    CHECK(accepted(pre->run(c)).termination==Termination::resource_limit);CHECK(report(*pre).reason==po::Reason::deadline);
    bool fail=true;o.pivot_observer=[&](const auto&){if(fail) {fail=false;throw std::runtime_error("observer");}};
    auto [throwing]=prepare(p,o).create();CHECK_THROWS_AS(throwing->run(context()),std::runtime_error);
    CHECK(throwing->last_attempt()->state==SolveAttemptState::exception);CHECK(std::holds_alternative<BasisUnavailable>(throwing->basis()->snapshot()));
    candidate(accepted(throwing->run(context())),p,{.5,.25,.25});
}
TEST_CASE("tiny pricing and overflowing reduced cost are undetermined numerical failures") {
    for(bool tiny:{true,false}) {
        const auto p=accepted(po::make_program({{"arithmetic"},{tiny?"tiny":"overflow"}},
            tiny?SparseMatrix{1,1,{0,1},{0},{1e-300}}:SparseMatrix{2,1,{0,1,2},{0,0},{1e308,1e308}},tiny?Vector{1}:Vector{1,1}));
        auto [w]=prepare(p).create();const auto r=accepted(w->run(context()));
        CHECK(r.termination==Termination::numerical_failure);CHECK(r.outcome.value==MathematicalOutcome::undetermined);
        CHECK(report(*w).reason==(tiny?po::Reason::uncertain_pricing:po::Reason::arithmetic));
        REQUIRE(r.primal);CHECK(*r.primal==Vector{0});CHECK_FALSE(r.objective.lower);CHECK_FALSE(r.objective.upper);
    }
}

TEST_CASE("lost nonzero pricing product preserves an undetermined checked history") {
    const double d=std::numeric_limits<double>::denorm_min(),e=std::ldexp(1.0,-52);
    const Vector witness{1+e,std::ldexp(1.0,1023)};
    REQUIRE(d>0);REQUIRE(std::isfinite(witness[1]));
    CHECK(d*witness[1]==std::ldexp(1.0,-51));
    CHECK(2*witness[0]-d*witness[1]==2);CHECK(witness[0]==1+e);
    const auto p=accepted(po::make_program({{"underflow"},{"finite-exact-witness"}},
        {2,2,{0,2,3},{0,1,0},{2,-d,1}},Vector{2,1+e}));
    const auto verified=accepted(evaluate_primal(p,witness,{0,0},{{"literal-dyadic"},"1"}));
    CHECK(verified.objective==0);CHECK(verified.residuals.rows.violation==0);
    CHECK(verified.residuals.variables.violation==0);

    auto c=context();c.numerical={0,0};auto [w]=prepare(p).create();
    const auto r=accepted(w->run(c));INFO(r.raw_diagnostics);
    CHECK(r.termination==Termination::numerical_failure);
    CHECK(r.outcome.value==MathematicalOutcome::undetermined);
    CHECK(r.outcome.subject==p.identity());CHECK(std::holds_alternative<Unestablished>(r.outcome.support));
    CHECK_FALSE(r.objective.lower);CHECK_FALSE(r.objective.upper);
    REQUIRE(r.primal);CHECK(*r.primal==Vector{1,0});REQUIRE(r.residuals.primal);
    CHECK(r.residuals.primal->rows.violation==e);CHECK(check_program_result(r,p,Assurance::numerical).empty());
    const auto history=report(*w);CHECK(history.reason==po::Reason::arithmetic);
    CHECK(history.termination==Termination::numerical_failure);CHECK(history.pivots==1);
    CHECK(history.factorizations==1);CHECK(history.pricing_passes==2);REQUIRE(history.auxiliary);
    CHECK(history.auxiliary->artificial==Vector{0,e});CHECK(history.auxiliary->value==e);
    REQUIRE(history.trace.size()==1);const auto& event=history.trace[0];
    CHECK(std::get<po::StructuralVariable>(event.entering).column==0);
    CHECK(std::get<po::ArtificialVariable>(event.leaving).row==0);
    CHECK(event.leaving_position==0);CHECK(event.coefficient==2);CHECK(event.step==1);
    CHECK(event.auxiliary_before==3);CHECK(event.auxiliary_after==e);
    const auto basis=accepted(w->basis()->snapshot());CHECK(check_basis_snapshot(basis,w->last_attempt()).empty());
    REQUIRE(basis.columns.size()==2);CHECK(std::get<StructuralColumn>(basis.columns[0]).index==0);
    CHECK(std::get<AuxiliaryColumn>(basis.columns[1]).coefficients==Vector{0,1});
    CHECK(basis.reference.iteration==1);REQUIRE(basis.last_pivot);CHECK(basis.last_pivot->coefficient==2);
    CHECK(accepted(w->basis()->coordinates(basis.reference,Vector{2,1+e})).values==Vector{1,e});

    const auto again=accepted(w->run(c));CHECK(again.termination==Termination::numerical_failure);
    CHECK(again.outcome.value==MathematicalOutcome::undetermined);CHECK(report(*w).solve!=history.solve);
    CHECK(std::get<BasisUnavailable>(w->basis()->coordinates(basis.reference,Vector{2,1+e})).reason==BasisUnavailableReason::stale_reference);
    w.reset();CHECK(history.auxiliary->value==e);CHECK(history.trace[0].auxiliary_after==e);
    CHECK(std::get<AuxiliaryColumn>(basis.columns[1]).coefficients==Vector{0,1});
}

TEST_CASE("static admission rejects unsupported mathematics and checked capacity before factory") {
    const auto good=triangle();
    std::size_t factories=0;
    auto registration=accepted(po::make_registration());
    auto factory=registration.factory;
    registration.factory=[&](const LinearProgram& p){++factories;return factory(p);};
    Registry<LPPort> registry;REQUIRE_FALSE(registry.add(std::move(registration)));
    for(int mode=0;mode<5;++mode) {
        LinearProgramInput input{{{"admission"},{"unsupported"}},{0},0,{1,1,{0,1},{0},{1}},{{0,{}}},{{1,1}}};
        if(mode==0) input.objective[0]=1;
        if(mode==1) input.offset=1;
        if(mode==2) input.variables[0].lower=-1;
        if(mode==3) input.variables[0].upper=2;
        if(mode==4) input.rows[0].lower.reset();
        const auto p=accepted(make_linear_program(input));
        CHECK(std::holds_alternative<Rejection>(prepare_pipeline(select(registry,{{"phase-one-bland"},{}},p,requirements()))));
    }
    for(auto scalar:{Scalar::binary32,Scalar::exact,Scalar::interval}) {
        auto req=requirements();req.scalar=scalar;
        CHECK(std::holds_alternative<Rejection>(prepare_pipeline(select(registry,{{"phase-one-bland"},{}},good,req))));
    }
    auto req=requirements();req.output.assurance=Assurance::validated;
    CHECK(std::holds_alternative<Rejection>(prepare_pipeline(select(registry,{{"phase-one-bland"},{}},good,req))));
    CHECK(factories==0);
    const auto tiny=accepted(po::make_program({{"capacity"},{"one-row"}},{1,2,{0,1},{0},{1}},Vector{1}));
    for(std::size_t cap:{2U,3U}) {
        po::Options o;o.dense_entry_limit=cap;Registry<LPPort> limited;
        auto entry=accepted(po::make_registration(o));auto f=entry.factory;
        entry.factory=[&factories,f](const LinearProgram& p){++factories;return f(p);};
        REQUIRE_FALSE(limited.add(std::move(entry)));
        auto result=prepare_pipeline(select(limited,{{"phase-one-bland"},{}},tiny,requirements()));
        CHECK(std::holds_alternative<PreparedPipeline<LPPort>>(result)==(cap==3));
    }
    CHECK(factories==0);
    for(double tolerance:{-1.,1.,std::numeric_limits<double>::infinity(),std::numeric_limits<double>::quiet_NaN()}) {
        po::Options o;o.pivot_relative_tolerance=tolerance;
        CHECK(std::holds_alternative<Diagnostics>(po::make_registration(o)));
    }
    CHECK(std::holds_alternative<Diagnostics>(po::make_program({{"bad"},{"csr"}},{1,2,{0,2},{1,0},{1,1}},Vector{1})));
    CHECK(std::holds_alternative<Diagnostics>(po::make_program({{"bad"},{"rhs"}},{1,0,{0,0},{},{}},Vector{std::numeric_limits<double>::quiet_NaN()})));
    CHECK(std::holds_alternative<Diagnostics>(po::make_program({{""},{"identity"}},{0,0,{0},{},{}},{})));
}
TEST_CASE("accounted byte budget and runtime validation precede dense initialization") {
    const auto p=triangle();po::Options options;options.trace_limit=2;
    // Independent substitution of m=n=3 into the documented admission formula.
    const std::size_t bytes=sizeof(double)*(9+8*9+16*3+4*3)+sizeof(std::size_t)*(8*3+2*3)+2*sizeof(po::PivotEvent);
    auto [w]=prepare(p,options).create();auto c=context();
    c.resources=std::make_shared<ResourcePolicy>(ResourcePolicy{1,1,1,bytes-1});
    const auto denied=accepted(w->run(c));CHECK(denied.termination==Termination::resource_limit);
    CHECK(denied.outcome.value==MathematicalOutcome::undetermined);CHECK_FALSE(denied.primal);
    auto s=report(*w);CHECK(s.reason==po::Reason::capacity);CHECK(s.accounted_workspace_bytes==bytes);
    CHECK_FALSE(s.normalization);CHECK_FALSE(s.auxiliary);CHECK(s.factorizations==0);
    c.resources=std::make_shared<ResourcePolicy>(ResourcePolicy{1,1,1,bytes});
    candidate(accepted(w->run(c)),p,{.5,.25,.25});CHECK(report(*w).accounted_workspace_bytes==bytes);
    const auto retained=accepted(w->basis()->snapshot());
    c=context();c.numerical.absolute_tolerance=-1;
    CHECK(std::holds_alternative<Unsupported>(w->run(c)));
    CHECK(w->last_attempt()->state==SolveAttemptState::unsupported);
    CHECK(std::holds_alternative<BasisUnavailable>(w->basis()->snapshot()));
    CHECK(std::holds_alternative<BasisUnavailable>(dynamic_cast<const po::DiagnosticsView*>(w->basis())->phase_one_snapshot()));
    CHECK(retained.columns.size()==3);
    c=context();c.resources=std::make_shared<ResourcePolicy>(ResourcePolicy{0,1,1,{}});
    CHECK(std::holds_alternative<Unsupported>(w->run(c)));
    candidate(accepted(w->run(context())),p,{.5,.25,.25});
}
TEST_CASE("trace caps change storage only and historical snapshots own their arrays") {
    const auto p=triangle();std::optional<po::Snapshot> retained;
    for(std::size_t cap:{0U,2U,128U}) {
        po::Options o;o.trace_limit=cap;auto [w]=prepare(p,o).create();candidate(accepted(w->run(context())),p,{.5,.25,.25});
        const auto s=report(*w);CHECK(s.pivots==3);CHECK(s.trace.size()==std::min<std::size_t>(cap,3));
        CHECK(s.trace_truncated==(cap<3));CHECK(s.auxiliary->value==0);retained=s;
    }
    REQUIRE(retained);CHECK(retained->trace.size()==3);CHECK(retained->normalization->signs==std::vector<int>{1,1,1});
    CHECK(retained->auxiliary->artificial==Vector{0,0,0});
}
TEST_CASE("retained plans isolate workspaces and unwind joins actual asynchronous solves") {
    auto prepared=[] {
        SparseMatrix a{1,1,{0,1},{0},{-2}};Vector b{-4};
        const auto p=accepted(po::make_program({{"retained"},{"producer"}},a,b));auto plan=prepare(p);
        a.values[0]=999;b[0]=999;return plan;
    }();
    auto [first]=prepared.create();auto [second]=prepared.create();
    CHECK(first->workspace_identity()!=second->workspace_identity());
    auto f=std::async(std::launch::async,[&]{return first->run(context());});
    auto g=std::async(std::launch::async,[&]{return second->run(context());});
    const auto left=accepted(f.get()),right=accepted(g.get());REQUIRE(left.primal);REQUIRE(right.primal);
    CHECK(*left.primal==Vector{2});CHECK(*right.primal==Vector{2});
    const auto basis=accepted(first->basis()->snapshot());
    CHECK(std::get<BasisUnavailable>(second->basis()->coordinates(basis.reference,Vector{-6})).reason==BasisUnavailableReason::stale_reference);
    CHECK(std::holds_alternative<Diagnostics>(first->basis()->coordinates(basis.reference,{})));
    CHECK(std::holds_alternative<Diagnostics>(first->basis()->coordinates(basis.reference,Vector{std::numeric_limits<double>::infinity()})));
    std::optional<ProgramOutcome> joined;
    try {
        auto [w]=prepared.create();
        std::jthread task([worker=std::move(w),&joined]{joined=worker->run(context());});
        throw std::runtime_error("caller unwinds while worker owns retained data");
    } catch(const std::runtime_error&) {}
    REQUIRE(joined);const auto completed=accepted(std::move(*joined));REQUIRE(completed.primal);CHECK(*completed.primal==Vector{2});
    auto owned=std::make_shared<std::vector<po::PivotEvent>>();std::weak_ptr<std::vector<po::PivotEvent>> weak=owned;
    {
        po::Options o;o.pivot_observer=[owned](const po::PivotEvent& event){owned->push_back(event);};
        auto plan=prepare(triangle(),std::move(o));owned.reset();
        auto [w]=plan.create();CHECK(accepted(w->run(context())).termination==Termination::completed);
        REQUIRE_FALSE(weak.expired());CHECK(weak.lock()->size()==3);
    }
    CHECK(weak.expired());
}
TEST_CASE("homogeneous zero pivots contradictions and near boundary policies remain numerical") {
    po::Options zero;zero.pivot_limit=0;
    const auto homogeneous=accepted(po::make_program({{"zero"},{"homogeneous"}},{1,2,{0,2},{0,1},{1,-1}},Vector{-0.0}));
    auto [h]=prepare(homogeneous,zero).create();candidate(accepted(h->run(context())),homogeneous,{0,0});
    CHECK(report(*h).pivots==0);CHECK(report(*h).normalization->signs==std::vector<int>{1});
    const auto impossible=accepted(po::make_program({{"rows"},{"contradiction"}},{2,1,{0,1,2},{0,0},{1,1}},Vector{1,2}));
    auto [w]=prepare(impossible).create();const auto r=accepted(w->run(context()));
    CHECK(r.outcome.value==MathematicalOutcome::infeasible);REQUIRE(r.primal);CHECK(*r.primal==Vector{1});CHECK(report(*w).auxiliary->value==1);
    const auto boundary= triangle({.5,-1e-12,1},"near-boundary");
    for(double tolerance:{1e-8,1e-14}) {
        auto [n]=prepare(boundary).create();auto c=context();c.numerical.absolute_tolerance=tolerance;
        const auto result=accepted(n->run(c));CHECK(result.termination==Termination::completed);
        CHECK(result.outcome.value==(tolerance==1e-8?MathematicalOutcome::optimal:MathematicalOutcome::infeasible));
        CHECK(std::holds_alternative<Unestablished>(result.outcome.support));CHECK_FALSE(result.objective.lower);CHECK_FALSE(result.objective.upper);
        REQUIRE(result.primal);const auto evaluated=accepted(evaluate_primal(boundary,*result.primal,c.numerical,{{"boundary"},"1"}));
        CHECK(evaluated.residuals.rows.violation==doctest::Approx(1e-12).epsilon(1e-6));
        CHECK(report(*n).auxiliary->value==doctest::Approx(1e-12).epsilon(1e-6));
    }
}
TEST_CASE("unsafe pivot and rejected tentative basis keep last finite coefficients") {
    for(bool uncertain:{true,false}) {
        const auto p=accepted(po::make_program({{"guard"},{uncertain?"direction":"condition"}},
            {2,1,{0,1,2},{0,0},uncertain?Vector{1,1e14}:Vector{1e14,1e14}},Vector{1,1}));
        auto [w]=prepare(p).create();const auto r=accepted(w->run(context()));
        CHECK(r.termination==Termination::numerical_failure);CHECK(r.outcome.value==MathematicalOutcome::undetermined);
        REQUIRE(r.primal);CHECK(*r.primal==Vector{0});const auto s=report(*w);CHECK(s.pivots==0);
        CHECK(s.reason==(uncertain?po::Reason::uncertain_pivot:po::Reason::ill_conditioned_basis));CHECK(s.auxiliary->value==2);
        CHECK(std::holds_alternative<BasisSnapshot>(w->basis()->snapshot())==uncertain);
    }
}



#ifdef CSL_PHASE_ONE_REFERENCE
TEST_CASE("same immutable request selects phase one or actual reference without basis invention") {
    Registry<LPPort> registry;
    REQUIRE_FALSE(registry.add(accepted(po::make_registration())));
    REQUIRE_FALSE(registry.add(accepted(adapters::lp::make_highs_registration())));
    std::vector<std::pair<LinearProgram,bool>> fixtures;
    fixtures.emplace_back(triangle(),true);fixtures.emplace_back(triangle({.5,0,1},"edge"),true);
    fixtures.emplace_back(triangle({1,1,1},"outside"),false);
    fixtures.emplace_back(accepted(po::make_program({{"reference"},{"signed"}},
        {3,3,{0,3,6,9},{0,1,2,0,1,2,0,1,2},{-1,1,-1,-1,-1,1,1,1,1}},Vector{-.5,-.5,1})),true);
    for(double zero_row:{0.,1.}) fixtures.emplace_back(accepted(po::make_program({{"reference"},{zero_row==0?"flat":"flat-outside"}},
        {4,3,{0,2,2,5,8},{0,2,0,1,2,0,1,2},{-1,1,2,2,2,1,1,1}},Vector{.5,zero_row,2,1})),zero_row==0);
    fixtures.emplace_back(accepted(po::make_program({{"reference"},{"duplicates"}},
        {2,2,{0,2,4},{0,1,0,1},{1,1,1,1}},Vector{1,1})),true);
    for(const auto& [p,feasible]:fixtures) {
        for(const char* method:{"phase-one-bland","csl.lp.highs"}) {
            auto plan=accepted(prepare_pipeline(select(registry,{{method},{}},p,requirements(false))));
            auto [w]=plan.create();CHECK_FALSE(w->basis());
            const auto r=accepted(w->run(context()));INFO(std::string(method));INFO(p.identity().program.value);INFO(r.raw_diagnostics);
            CHECK(r.termination==Termination::completed);
            CHECK(r.outcome.value==(feasible?MathematicalOutcome::optimal:MathematicalOutcome::infeasible));
            CHECK(r.outcome.subject==p.identity());CHECK(std::holds_alternative<Unestablished>(r.outcome.support));
            CHECK_FALSE(r.objective.lower);CHECK_FALSE(r.objective.upper);CHECK(check_program_result(r,p,Assurance::numerical).empty());
            if(feasible) {
                REQUIRE(r.primal);const auto independently=accepted(evaluate_primal(p,*r.primal,{1e-8,0},{{"reference-original"},"1"}));
                CHECK(independently.objective==0);CHECK(independently.residuals.rows.violation<1e-8);CHECK(independently.residuals.variables.violation<1e-8);
            }
            if(std::string(method)=="csl.lp.highs") {
                CHECK(plan.provenance()[0].actual->version=="1.0.0+highs.1.11.0");
                CHECK(r.raw_diagnostics.find("native.version=1.11.0")!=std::string::npos);
                CHECK(r.raw_diagnostics.find("options.absolute_tolerance=1e-08")!=std::string::npos);
            }
        }
    }
    const auto p=triangle();
    CHECK(std::holds_alternative<Rejection>(prepare_pipeline(select(registry,{{"csl.lp.highs"},{}},p,requirements()))));
    auto plan=accepted(prepare_pipeline(select(registry,{{"phase-one-bland"},{}},p,requirements())));
    auto [w]=plan.create();candidate(accepted(w->run(context())),p,{.5,.25,.25});CHECK(w->basis());
}
#endif

TEST_CASE("duplicate trace repeats independently after another workspace is cancelled") {
    const auto p=accepted(po::make_program({{"repeat"},{"duplicate"}},{2,2,{0,2,4},{0,1,0,1},{1,1,1,1}},Vector{1,1}));
    const auto plan=prepare(p);auto [first]=plan.create();auto [second]=plan.create();
    std::stop_source source;source.request_stop();auto stopped=context();stopped.cancellation=source.get_token();
    stopped.deadline=std::chrono::steady_clock::now()-std::chrono::seconds(1);
    CHECK(accepted(first->run(stopped)).termination==Termination::cancelled);CHECK_FALSE(report(*first).auxiliary);
    candidate(accepted(second->run(context())),p,{1,0});const auto one=report(*second);
    candidate(accepted(first->run(context())),p,{1,0});const auto two=report(*first);
    CHECK(one.solve!=two.solve);CHECK(one.pivots==1);CHECK(two.pivots==1);
    for(const auto* s:{&one,&two}) {
        REQUIRE(s->trace.size()==1);const auto& event=s->trace[0];
        CHECK(std::get<po::StructuralVariable>(event.entering).column==0);
        CHECK(std::get<po::ArtificialVariable>(event.leaving).row==0);
        CHECK(event.leaving_position==0);CHECK(event.coefficient==1);CHECK(event.step==1);
        CHECK(event.auxiliary_before==2);CHECK(event.auxiliary_after==0);
    }
    auto basis=accepted(first->basis()->snapshot());basis.reference.iteration=0;
    CHECK(std::get<BasisUnavailable>(first->basis()->coordinates(basis.reference,Vector{1,1})).reason==BasisUnavailableReason::stale_reference);
}
