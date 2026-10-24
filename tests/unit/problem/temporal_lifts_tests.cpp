#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>

#include <csl/numeric/data.hpp>
#include <csl/problem/temporal_lifts.hpp>
#include <csl/sets/data.hpp>

using namespace csl;
using namespace csl::problem;

namespace {
template<class T,class... R> T accepted(std::variant<T,R...> value) {
    if(const auto* error=std::get_if<Diagnostic>(&value)) INFO(error->field<<": "<<error->explanation);
    REQUIRE(std::holds_alternative<T>(value));
    return std::get<T>(std::move(value));
}
LiftedControlHistory accepted_lift(HistoryMapResult value) {
    if(const auto* error=std::get_if<Diagnostic>(&value)) INFO(error->field<<": "<<error->explanation);
    REQUIRE(std::holds_alternative<LiftedControlHistory>(value));
    return std::get<LiftedControlHistory>(std::move(value));
}
sets::SetData box(double lower,double upper) {
    auto h=std::get<numeric::MatrixView>(numeric::snapshot(Matrix{2,1,{-1,1}}));
    auto bounds=std::get<numeric::VectorView>(numeric::snapshot_vector(Vector{-lower,upper}));
    auto equalities=std::get<numeric::MatrixView>(numeric::snapshot(Matrix{0,1,{}}));
    auto values=std::get<numeric::VectorView>(numeric::snapshot_vector(Vector{}));
    return std::get<sets::SetData>(sets::make_h({{"interval"},1,{"u"}},{h,bounds,equalities,values}));
}
Problem integrator() {
    const auto controls=box(-1,1).as_handle();
    auto model=std::make_shared<const SystemModel>(SystemModel{{{1,1,0},TimeDomain::discrete,
        LinearStage{{1,1,{1}},{1,1,{1}},{1,0,{}},{0}}},{}});
    return {{"integrator"},std::move(model),{0,1,2},KnownInitial{{0}},ContinuousDomain{{controls,controls}},
        {UniversalSet{1},UniversalSet{1},UniversalSet{1}},{},{},InformationPattern::nominal_open_loop,
        QuadraticTerminal{{1,1,{2}},{0},0}};
}
}

TEST_CASE("slew memory lift maps a feasible history both ways and retains absolute input bounds") {
    const auto original=integrator();
    SlewMemoryRequest request{RateLimitedFirstAction{{.25},box(-.25,.25).as_handle()},
        {box(-.25,.25).as_handle()}};
    const auto lifted=accepted(lift_one_step_slew(original,request));
    CHECK(lifted.coordinates.original==JointCoordinates{{1,1,0},2});
    CHECK(lifted.coordinates.lifted==JointCoordinates{{2,1,0},2});
    CHECK(lifted.coordinates.original_state_to_lifted_state==std::vector<std::size_t>{0,2,4});
    CHECK(lifted.coordinates.original_control_to_lifted_memory==std::vector<std::size_t>{3,5});
    CHECK(lifted.coordinates.lifted_increment_to_original_control==std::vector<std::size_t>{3,4});
    CHECK(lifted.problem.id.value!="integrator");
    CHECK(std::get<KnownInitial>(lifted.problem.initial).point==Vector{0,.25});
    REQUIRE(lifted.problem.states.size()==3);
    REQUIRE(lifted.problem.model->dynamics.dimensions==Dimensions{2,1,0});
    const auto stages=std::get<std::vector<LinearStage>>(lifted.problem.model->dynamics.stages);
    REQUIRE(stages.size()==2);
    CHECK(stages[0].A.values==Vector{1,1,0,1});
    CHECK(stages[0].B.values==Vector{1,1});

    const ControlHistory original_history{{{0},{.375},{.875}},{{.375},{.5}}};
    const auto auxiliary=accepted_lift(lift_history(lifted.coordinates,original_history));
    CHECK(auxiliary.augmented_states==std::vector<Vector>{{0,.25},{.375,.375},{.875,.5}});
    CHECK(auxiliary.increments==std::vector<Vector>{{.125},{.125}});
    CHECK(accepted(recover_history(lifted.coordinates,auxiliary,1e-12,1e-12)).states==original_history.states);
    CHECK(accepted(recover_history(lifted.coordinates,auxiliary,1e-12,1e-12)).controls==original_history.controls);

    const auto loaded=accepted(resolve(lifted.problem,{UncertaintyStructure::stage_product_uncoupled,{},{}}));
    const auto system=std::get<model::LinearSystem>(model::snapshot(*lifted.problem.model,lifted.problem.times));
    const Vector state_zero{0,.25},increment_zero{.125};
    const auto stage_one=std::get<Vector>(system.step({0},state_zero,increment_zero,{}));
    CHECK(stage_one==Vector{.375,.375});
    const Vector increment_one{.125};
    const auto stage_two=std::get<Vector>(system.step({1},stage_one,increment_one,{}));
    CHECK(stage_two==Vector{.875,.5});
    CHECK(loaded.model().dimensions()==Dimensions{2,1,0});
    auto inconsistent=auxiliary;
    inconsistent.increments[0][0]+=.01;
    const auto rejected_recurrence=recover_history(lifted.coordinates,inconsistent,0,0);
    REQUIRE(std::holds_alternative<Diagnostic>(rejected_recurrence));
    CHECK(std::get<Diagnostic>(rejected_recurrence).field=="problem.temporal_lift.history.recurrence");
    inconsistent=auxiliary;
    inconsistent.augmented_states[0][1]+=.01;
    const auto rejected_initial=recover_history(lifted.coordinates,inconsistent,0,0);
    REQUIRE(std::holds_alternative<Diagnostic>(rejected_initial));
    CHECK(std::get<Diagnostic>(rejected_initial).field=="problem.temporal_lift.history.initial_memory");
}

TEST_CASE("no initial slew selects zero bookkeeping memory and leaves the first command unrestricted") {
    auto source=integrator();source.controls=ContinuousDomain{{box(-2,2).as_handle(),box(-2,2).as_handle()}};
    const auto lifted=accepted(lift_one_step_slew(source,
        {UnconstrainedFirstAction{}, {box(-.25,.25).as_handle()}}));
    CHECK(lifted.coordinates.initial_memory==Vector{0});
    CHECK(std::get<KnownInitial>(lifted.problem.initial).point==Vector{0,0});
    const auto history=accepted_lift(lift_history(lifted.coordinates,{{{0},{1},{2.125}},{{1},{1.125}}}));
    CHECK(history.increments==std::vector<Vector>{{1},{.125}});
    CHECK(accepted(recover_history(lifted.coordinates,history,1e-12,1e-12)).controls==std::vector<Vector>{{1},{1.125}});
}

TEST_CASE("memory lift rejects unsupported model semantics and mismatched stage domains") {
    const auto source=integrator();
    const auto wrong_count=lift_one_step_slew(source,{UnconstrainedFirstAction{},{}});
    REQUIRE(std::holds_alternative<Diagnostic>(wrong_count));
    CHECK(std::get<Diagnostic>(wrong_count).field=="problem.temporal_lift.increments");

    auto feedback=source;feedback.information=InformationPattern::feedback;
    const auto feedback_result=lift_one_step_slew(feedback,{UnconstrainedFirstAction{}, {box(-.25,.25).as_handle()}});
    REQUIRE(std::holds_alternative<Diagnostic>(feedback_result));
    CHECK(std::get<Diagnostic>(feedback_result).code==DiagnosticCode::unsupported);
    CHECK(std::get<Diagnostic>(feedback_result).field=="problem.temporal_lift.profile");

    auto already_coupled=source;already_coupled.temporal=TemporalConstraints{{1,5,{0,1},{3,4},{1,-1}},{{0,0}}};
    const auto coupled_result=lift_one_step_slew(already_coupled,{UnconstrainedFirstAction{}, {box(-.25,.25).as_handle()}});
    REQUIRE(std::holds_alternative<Diagnostic>(coupled_result));
    CHECK(std::get<Diagnostic>(coupled_result).field=="problem.temporal.shape");

    const auto vertices=std::get<sets::SetData>(sets::make_v({{"vertex-controls"},1,{"u"}},
        {std::get<numeric::MatrixView>(numeric::snapshot(Matrix{2,1,{-1,1}})),
         std::get<numeric::MatrixView>(numeric::snapshot(Matrix{0,1,{}}))})).as_handle();
    auto vertex_controls=source;
    vertex_controls.controls=ContinuousDomain{{vertices,box(-1,1).as_handle()}};
    const auto geometry_result=lift_one_step_slew(vertex_controls,
        {UnconstrainedFirstAction{}, {box(-.25,.25).as_handle()}});
    REQUIRE(std::holds_alternative<Diagnostic>(geometry_result));
    CHECK(std::get<Diagnostic>(geometry_result).code==DiagnosticCode::unsupported);
    CHECK(std::get<Diagnostic>(geometry_result).field=="problem.temporal_lift.increments[0].representation");
}
