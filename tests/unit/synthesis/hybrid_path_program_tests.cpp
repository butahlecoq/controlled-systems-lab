#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>

#include <csl/synthesis/hybrid_path_program.hpp>
#include <csl/sets/data.hpp>
#include <csl/registry/provider.hpp>
#include <array>

using namespace csl;
using namespace csl::synthesis;

namespace {
SetHandle universal(std::string id,std::size_t dimension) {
    auto data=sets::make_universal({SetId{std::move(id)},dimension,{}});
    REQUIRE(std::holds_alternative<sets::SetData>(data));
    return std::get<sets::SetData>(std::move(data)).as_handle();
}

model::HybridSystem example_system() {
    model::HybridMode source{{"source"},1,1,{"position"},{"thrust"}};
    source.flow=LinearStage{Matrix{1,1,{1}},Matrix{1,1,{1}},Matrix{1,0,{}},Vector{0}};
    source.control_sets={UniversalSet{1}};
    source.invariants={UniversalSet{1},UniversalSet{1}};
    model::HybridMode target{{"target"},2,0,{"position","velocity"},{}};
    target.flow=LinearStage{Matrix{2,2,{1,0,0,1}},Matrix{2,0,{}},Matrix{2,0,{}},Vector{0,0}};
    target.control_sets={UniversalSet{0}};
    target.invariants={UniversalSet{2},UniversalSet{2}};
    model::HybridTransitionEdge edge{{"switch"},{"source"},{"target"},
        {UniversalSet{1}},{universal("reset",3)}};
    return {1,{std::move(source),std::move(target)},{std::move(edge)}};
}

model::HybridRequest example_request() {
    return {{{"source"},{2}},{{"target"}},
        {{{"target"},LinearTerminal{{2,-1},0},"energy","J"}}};
}

model::HybridPath example_path() {
    return {{{"source"},{"target"}},{{"switch"}}};
}

SetHandle interval(std::string id,double lower,double upper) {
    auto matrix=numeric::snapshot(Matrix{2,1,{-1,1}});
    auto bounds=numeric::snapshot_vector(Vector{-lower,upper});
    auto equalities=numeric::snapshot(Matrix{0,1,{}});
    auto rhs=numeric::snapshot_vector(Vector{});
    REQUIRE(std::holds_alternative<numeric::MatrixView>(matrix));
    REQUIRE(std::holds_alternative<numeric::VectorView>(bounds));
    REQUIRE(std::holds_alternative<numeric::MatrixView>(equalities));
    REQUIRE(std::holds_alternative<numeric::VectorView>(rhs));
    auto data=sets::make_h({SetId{std::move(id)},1,{"guard-coordinate"}},
        {std::get<numeric::MatrixView>(matrix),std::get<numeric::VectorView>(bounds),
         std::get<numeric::MatrixView>(equalities),std::get<numeric::VectorView>(rhs)});
    REQUIRE(std::holds_alternative<sets::SetData>(data));
    return std::get<sets::SetData>(std::move(data)).as_handle();
}

bool satisfies(const sets::HRepresentation& h,const Vector& point) {
    for(std::size_t i=0;i<h.inequalities.rows();++i) {
        double value=0;
        for(std::size_t j=0;j<h.inequalities.cols();++j) value+=h.inequalities(i,j)*point[j];
        if(value>h.upper_bounds[i]) return false;
    }
    for(std::size_t i=0;i<h.equalities.rows();++i) {
        double value=0;
        for(std::size_t j=0;j<h.equalities.cols();++j) value+=h.equalities(i,j)*point[j];
        if(value!=h.equality_values[i]) return false;
    }
    return true;
}

class RejectingLP final : public LPWorkspace {
    ProgramOutcome do_solve(const LinearProgram&,const ExecutionContext&) override {
        return Unsupported{{{DiagnosticCode::unsupported,"fixture.lp","fixture rejection"}}};
    }
};

class CompletingLP final : public LPWorkspace {
    ProgramOutcome do_solve(const LinearProgram& program,const ExecutionContext&) override {
        return ProgramResult{Termination::completed,
            {program.identity(),MathematicalOutcome::undetermined,Unestablished{},{}},
            {},{},"fixture completed"};
    }
};

class RejectingConvex final : public ConvexWorkspace {
    ProgramOutcome do_solve(const ConvexProgram&,const ExecutionContext&) override {
        return Unsupported{{{DiagnosticCode::unsupported,"fixture.convex","fixture rejection"}}};
    }
};

registry::PreparedProvider<registry::LPPort> lp_provider(std::stop_source* cancel_during_prepare=nullptr,
    std::shared_ptr<int> factory_calls=std::make_shared<int>(0),std::string reject_problem={},
    std::string cancel_problem={}) {
    registry::Registry<registry::LPPort> providers;
    REQUIRE_FALSE(providers.add({{{"reject-lp"},"1"},
        [cancel_during_prepare,reject_problem,cancel_problem](const LinearProgram& program,const registry::Requirements&)->registry::Capability{
            if(cancel_during_prepare && (cancel_problem.empty() || program.identity().problem.value==cancel_problem))
                cancel_during_prepare->request_stop();
            if(program.identity().problem.value==reject_problem && !reject_problem.empty())
                return Diagnostics{{DiagnosticCode::unsupported,"fixture.capability","requested fixture rejection"}};
            return registry::Offer{};
        },
        [factory_calls](const LinearProgram&){++*factory_calls; return std::make_unique<RejectingLP>();}}));
    auto prepared=registry::prepare_provider(registry::select_provider(providers,{{"reject-lp"},{}}));
    REQUIRE(std::holds_alternative<registry::PreparedProvider<registry::LPPort>>(prepared));
    return std::get<registry::PreparedProvider<registry::LPPort>>(std::move(prepared));
}

registry::PreparedProvider<registry::LPPort> completing_lp_provider() {
    registry::Registry<registry::LPPort> providers;
    REQUIRE_FALSE(providers.add({{{"completing-lp"},"1"},
        [](const LinearProgram&,const registry::Requirements&)->registry::Capability{return registry::Offer{};},
        [](const LinearProgram&){return std::make_unique<CompletingLP>();}}));
    auto prepared=registry::prepare_provider(registry::select_provider(providers,{{"completing-lp"},{}}));
    REQUIRE(std::holds_alternative<registry::PreparedProvider<registry::LPPort>>(prepared));
    return std::get<registry::PreparedProvider<registry::LPPort>>(std::move(prepared));
}

registry::PreparedProvider<registry::ConvexPort> convex_provider() {
    registry::Registry<registry::ConvexPort> providers;
    REQUIRE_FALSE(providers.add({{{"reject-convex"},"1"},
        [](const ConvexProgram&,const registry::Requirements&)->registry::Capability{return registry::Offer{};},
        [](const ConvexProgram&){return std::make_unique<RejectingConvex>();}}));
    auto prepared=registry::prepare_provider(registry::select_provider(providers,{{"reject-convex"},{}}));
    REQUIRE(std::holds_alternative<registry::PreparedProvider<registry::ConvexPort>>(prepared));
    return std::get<registry::PreparedProvider<registry::ConvexPort>>(std::move(prepared));
}
}

TEST_CASE("hybrid direct path program preserves branch and terminal objective coordinates") {
    const auto result=build_hybrid_path_program(example_system(),example_request(),example_path(),
        {"hybrid-problem"},{16,64,1024});
    REQUIRE(std::holds_alternative<HybridPathProgram>(result));
    const auto& built=std::get<HybridPathProgram>(result);
    REQUIRE(std::holds_alternative<LinearProgram>(built.program));
    const auto& program=std::get<LinearProgram>(built.program);
    CHECK(program.identity().problem.value=="hybrid-problem");
    CHECK(program.identity().program.value=="hybrid-path:6:switch");
    CHECK(program.objective().size()==5);
    CHECK(program.objective()[0]==0);
    CHECK(program.objective()[1]==0);
    CHECK(program.objective()[2]==0);
    CHECK(program.objective()[3]==2);
    CHECK(program.objective()[4]==-1);
    const auto constraints=std::get<numeric::CsrInput>(program.constraints().descriptor());
    CHECK(std::vector<std::size_t>(constraints.row_offsets.begin(),constraints.row_offsets.end())==
        std::vector<std::size_t>{0,1,4});
    CHECK(std::vector<std::size_t>(constraints.column_indices.begin(),constraints.column_indices.end())==
        std::vector<std::size_t>{0,0,1,2});
    CHECK(std::vector<double>(constraints.values.begin(),constraints.values.end())==
        std::vector<double>{1,-1,-1,1});
    CHECK(program.rows().size()==2);
    CHECK(program.rows()[0].lower==2);
    CHECK(program.rows()[0].upper==2);
    CHECK(program.rows()[1].lower==0);
    CHECK(program.rows()[1].upper==0);
    CHECK(built.joint_relation.metadata()->set.dimension==5);
    CHECK(built.path==example_path());
}

TEST_CASE("hybrid program construction preserves cancellation and unsupported limits") {
    std::stop_source cancellation;
    cancellation.request_stop();
    const auto stopped=build_hybrid_path_program(example_system(),example_request(),example_path(),
        {"hybrid-problem"},{16,64,1024},{},cancellation.get_token());
    REQUIRE(std::holds_alternative<OperationStopped>(stopped));
    CHECK(std::get<OperationStopped>(stopped).reason==StopReason::cancelled);

    const auto limited=build_hybrid_path_program(example_system(),example_request(),example_path(),
        {"hybrid-problem"},{4,64,1024});
    REQUIRE(std::holds_alternative<Diagnostics>(limited));
    CHECK(std::get<Diagnostics>(limited)[0].code==DiagnosticCode::unsupported);
}

TEST_CASE("hybrid direct path programs admit quadratic and residual terminal objectives") {
    auto request=example_request();
    request.terminal_objectives[0].objective=QuadraticTerminal{
        Matrix{2,2,{1,0,0,1}},Vector{0,0},0};
    auto quadratic=build_hybrid_path_program(example_system(),request,example_path(),
        {"hybrid-problem"},{16,64,1024});
    REQUIRE(std::holds_alternative<HybridPathProgram>(quadratic));
    REQUIRE(std::holds_alternative<ConvexProgram>(std::get<HybridPathProgram>(quadratic).program));
    CHECK(std::get<ConvexProgram>(std::get<HybridPathProgram>(quadratic).program).original_objective().dimension()==5);

    request.terminal_objectives[0].objective=ResidualNormTerminal{Matrix{1,2,{1,-1}},Vector{0}};
    auto residual=build_hybrid_path_program(example_system(),request,example_path(),
        {"hybrid-problem"},{16,64,1024});
    REQUIRE(std::holds_alternative<HybridPathProgram>(residual));
    REQUIRE(std::holds_alternative<ConvexProgram>(std::get<HybridPathProgram>(residual).program));
    CHECK(std::get<ConvexProgram>(std::get<HybridPathProgram>(residual).program).original_objective().dimension()==5);
}

TEST_CASE("hybrid portfolio builder returns every parallel edge branch transactionally") {
    auto system=example_system();
    auto parallel=system.edges.front();
    parallel.id={"switch-parallel"};
    system.edges.push_back(std::move(parallel));
    const auto built=build_hybrid_portfolio_programs(system,example_request(),{"hybrid-problem"},
        {1,8},{16,64,1024});
    REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(built));
    const auto& programs=std::get<std::vector<HybridPathProgram>>(built);
    REQUIRE(programs.size()==2);
    CHECK(programs[0].path.modes==programs[1].path.modes);
    CHECK(programs[0].path.edges!=programs[1].path.edges);
    const auto& first=std::get<LinearProgram>(programs[0].program);
    const auto& second=std::get<LinearProgram>(programs[1].program);
    CHECK(first.identity().program!=second.identity().program);

    const auto limited=build_hybrid_portfolio_programs(system,example_request(),{"hybrid-problem"},
        {1,8},{4,64,1024});
    CHECK(std::holds_alternative<Diagnostics>(limited));
}

TEST_CASE("hybrid branch execution retains path and solver provenance on rejection") {
    auto built=build_hybrid_path_program(example_system(),example_request(),example_path(),
        {"hybrid-problem"},{16,64,1024});
    REQUIRE(std::holds_alternative<HybridPathProgram>(built));
    const std::array<HybridPathProgram,1> programs{std::get<HybridPathProgram>(std::move(built))};
    const auto report=execute_hybrid_path_programs(programs,lp_provider(),convex_provider(),{});
    REQUIRE(report.branches.size()==1);
    CHECK_FALSE(report.all_supplied_branches_completed);
    CHECK(report.branches[0].path==example_path());
    CHECK(report.branches[0].termination==Termination::operation_rejected);
    REQUIRE(report.branches[0].providers.size()==1);
    REQUIRE(report.branches[0].providers[0].actual);
    CHECK(report.branches[0].providers[0].actual->id.value=="reject-lp");
    REQUIRE(report.branches[0].diagnostics.size()==1);
    CHECK(report.branches[0].diagnostics[0].field=="fixture.lp");
}

TEST_CASE("hybrid branch execution records cancellation without invoking a provider") {
    auto built=build_hybrid_path_program(example_system(),example_request(),example_path(),
        {"hybrid-problem"},{16,64,1024});
    REQUIRE(std::holds_alternative<HybridPathProgram>(built));
    const std::array<HybridPathProgram,1> programs{std::get<HybridPathProgram>(std::move(built))};
    std::stop_source cancellation;
    cancellation.request_stop();
    const ExecutionContext context{{},{cancellation.get_token()},{},{1e-8,1e-8},{},{}};
    const auto report=execute_hybrid_path_programs(programs,lp_provider(),convex_provider(),context);
    REQUIRE(report.branches.size()==1);
    CHECK_FALSE(report.all_supplied_branches_completed);
    CHECK(report.branches[0].termination==Termination::cancelled);
    CHECK(report.branches[0].providers.empty());
    CHECK_FALSE(report.branches[0].result.has_value());
}

TEST_CASE("hybrid branch execution records an expired deadline before provider preparation") {
    auto built=build_hybrid_path_program(example_system(),example_request(),example_path(),
        {"hybrid-problem"},{16,64,1024});
    REQUIRE(std::holds_alternative<HybridPathProgram>(built));
    const std::array<HybridPathProgram,1> programs{std::get<HybridPathProgram>(std::move(built))};
    auto factory_calls=std::make_shared<int>(0);
    const ExecutionContext context{{},{},std::chrono::steady_clock::now()-std::chrono::milliseconds(1),
        {1e-8,1e-8},{},{}};
    const auto report=execute_hybrid_path_programs(programs,lp_provider(nullptr,factory_calls),
        convex_provider(),context);
    REQUIRE(report.branches.size()==1);
    CHECK_FALSE(report.all_supplied_branches_completed);
    CHECK(report.branches[0].termination==Termination::resource_limit);
    CHECK(report.branches[0].providers.empty());
    CHECK(*factory_calls==0);
}

TEST_CASE("hybrid branch execution observes cancellation after provider preparation") {
    auto first=build_hybrid_path_program(example_system(),example_request(),example_path(),
        {"first-problem"},{16,64,1024});
    auto second=build_hybrid_path_program(example_system(),example_request(),example_path(),
        {"stop-during-prepare"},{16,64,1024});
    REQUIRE(std::holds_alternative<HybridPathProgram>(first));
    REQUIRE(std::holds_alternative<HybridPathProgram>(second));
    const std::array<HybridPathProgram,2> programs{
        std::get<HybridPathProgram>(std::move(first)),std::get<HybridPathProgram>(std::move(second))};
    std::stop_source cancellation;
    auto factory_calls=std::make_shared<int>(0);
    const ExecutionContext context{{},cancellation.get_token(),{},{1e-8,1e-8},{},{}};
    const auto report=execute_hybrid_path_programs(programs,
        lp_provider(&cancellation,factory_calls,{},"stop-during-prepare"),
        convex_provider(),context);
    REQUIRE(report.branches.size()==2);
    CHECK_FALSE(report.all_supplied_branches_completed);
    CHECK(report.branches[0].termination==Termination::cancelled);
    CHECK(*factory_calls==0);
    REQUIRE(report.branches[0].providers.size()==1);
    CHECK_FALSE(report.branches[0].result.has_value());
    CHECK(report.branches[0].diagnostics[0].field=="hybrid.portfolio.preflight_interrupted");
    CHECK(report.branches[1].termination==Termination::cancelled);
    CHECK(report.branches[1].diagnostics.empty());
}

TEST_CASE("hybrid branch execution retains a completed solver result and provenance") {
    auto built=build_hybrid_path_program(example_system(),example_request(),example_path(),
        {"hybrid-problem"},{16,64,1024});
    REQUIRE(std::holds_alternative<HybridPathProgram>(built));
    const std::array<HybridPathProgram,1> programs{std::get<HybridPathProgram>(std::move(built))};
    const auto report=execute_hybrid_path_programs(programs,completing_lp_provider(),convex_provider(),{});
    REQUIRE(report.branches.size()==1);
    CHECK(report.all_supplied_branches_completed);
    CHECK(report.branches[0].path==example_path());
    CHECK(report.branches[0].termination==Termination::completed);
    CHECK(report.branches[0].outcome==MathematicalOutcome::undetermined);
    REQUIRE(report.branches[0].result);
    CHECK(report.branches[0].result->raw_diagnostics=="fixture completed");
    REQUIRE(report.branches[0].providers.size()==1);
    REQUIRE(report.branches[0].providers[0].actual);
    CHECK(report.branches[0].providers[0].actual->id.value=="completing-lp");
}

TEST_CASE("hybrid guard entry and exit constrain the pre-reset state") {
    auto system=example_system();
    system.edges[0].guards[0]=interval("guard-3-to-4",3,4);
    const auto relation=model::compose_hybrid_path_relation(system,example_request(),example_path(),
        {16,64,1024});
    REQUIRE(std::holds_alternative<sets::SetData>(relation));
    const auto representation=std::get<sets::SetData>(relation).representation();
    REQUIRE(std::holds_alternative<sets::HRepresentation>(representation));
    const auto& h=std::get<sets::HRepresentation>(representation);
    CHECK(satisfies(h,{2,1,3,0,0}));
    CHECK(satisfies(h,{2,2,4,0,0}));
    CHECK_FALSE(satisfies(h,{2,0,2,0,0}));
    CHECK_FALSE(satisfies(h,{2,3,5,0,0}));
}

TEST_CASE("hybrid empty guard produces an explicitly empty branch relation") {
    auto system=example_system();
    system.edges[0].guards[0]=EmptySet{1};
    const auto relation=model::compose_hybrid_path_relation(system,example_request(),example_path(),
        {16,64,1024});
    REQUIRE(std::holds_alternative<sets::SetData>(relation));
    const auto representation=std::get<sets::SetData>(relation).representation();
    REQUIRE(std::holds_alternative<sets::HRepresentation>(representation));
    const auto& h=std::get<sets::HRepresentation>(representation);
    bool contradictory_row=false;
    for(std::size_t i=0;i<h.inequalities.rows();++i) {
        bool zero=true;
        for(std::size_t j=0;j<h.inequalities.cols();++j) zero=zero && h.inequalities(i,j)==0;
        if(zero && h.upper_bounds[i]<0) contradictory_row=true;
    }
    CHECK(contradictory_row);
}

TEST_CASE("hybrid portfolio admits every branch before creating any solver workspace") {
    auto first=build_hybrid_path_program(example_system(),example_request(),example_path(),
        {"accepted-problem"},{16,64,1024});
    auto rejected=build_hybrid_path_program(example_system(),example_request(),example_path(),
        {"rejected-problem"},{16,64,1024});
    REQUIRE(std::holds_alternative<HybridPathProgram>(first));
    REQUIRE(std::holds_alternative<HybridPathProgram>(rejected));
    const std::array<HybridPathProgram,2> programs{
        std::get<HybridPathProgram>(std::move(first)),std::get<HybridPathProgram>(std::move(rejected))};
    auto factory_calls=std::make_shared<int>(0);
    const auto report=execute_hybrid_path_programs(programs,
        lp_provider(nullptr,factory_calls,"rejected-problem"),convex_provider(),{});
    REQUIRE(report.branches.size()==2);
    CHECK_FALSE(report.all_supplied_branches_completed);
    CHECK(*factory_calls==0);
    CHECK(report.branches[0].termination==Termination::operation_rejected);
    CHECK(report.branches[0].diagnostics[0].field=="hybrid.portfolio.admission");
    CHECK(report.branches[1].termination==Termination::operation_rejected);
    CHECK(report.branches[1].diagnostics[0].field=="fixture.capability");
}
