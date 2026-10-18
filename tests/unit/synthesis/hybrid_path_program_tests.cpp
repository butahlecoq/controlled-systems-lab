#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>

#include <csl/synthesis/hybrid_path_program.hpp>
#include <csl/sets/data.hpp>

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
