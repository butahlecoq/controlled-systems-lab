#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>

#include <csl/geometry/generator_adapter.hpp>
#include <csl/execution/timing_collector.hpp>
#include <csl/registry/provider.hpp>
#include <csl/sets/generator_sets.hpp>
#include <algorithm>
#include <chrono>
#include <limits>
#include <set>
#include <tuple>
#include <utility>

using namespace csl;

namespace {
class FutureRepresentationPayload final : public SetPayload {};
class GeneratorTimingClock final:public execution::observability::TimingClock {
    std::int64_t tick_{};
public:
    artifacts::ClockDomain wall_domain() const override {
        return {{"wall"},artifacts::ClockMetric::steady_wall,"run",1,1000,
            artifacts::Available<std::uint64_t>{1},"generator-adapter-test"};
    }
    std::optional<artifacts::ClockDomain> cpu_domain() const override{return {};}
    artifacts::Metric<std::int64_t> wall_now() noexcept override {
        const auto value=tick_;tick_+=10;return artifacts::Available<std::int64_t>{value};
    }
    artifacts::Metric<std::int64_t> cpu_now() noexcept override {
        return artifacts::Unavailable{artifacts::MissingReason::not_supported,{}};
    }
};
template<class T> T artifact(artifacts::ArtifactResult<T> value) {
    REQUIRE(std::holds_alternative<T>(value));return std::get<T>(std::move(value));
}
std::shared_ptr<execution::observability::TimingCollector> generator_timer(
        const problem::ResolvedProblem& problem,std::string task,std::string operation,
        artifacts::ModuleIdentity module,
        std::optional<RepresentationId> input_representation={},
        std::optional<RepresentationId> output_representation={},
        std::optional<SetRelation> relation={}) {
    namespace ar=artifacts;
    namespace ob=execution::observability;
    const ar::Unavailable missing{ar::MissingReason::not_instrumented,{}};
    ar::ConfigurationInput configuration;
    configuration.collection={true,ar::CollectionMode::detail,4,2048,4,1024};
    configuration.modules={{"geometry",module,{}},{"strategy",{{"csl.test.strategy"},"1",missing},{}}};
    configuration.resources={1,1,1,{}};configuration.numerical={1e-8,1e-8};
    configuration.output={ar::OutputKind::program,Assurance::numerical,
        FamilyTarget::candidate_relaxation,{"csl.polyhedron.v"},{1,0,{},{}}};
    configuration.selector={{"test.selector"},"1",{}};
    configuration.strategy={{"csl.test.strategy"},{},{},{},module.id,{},{},
        {"test.selector"},{"csl.polyhedron.v"}};
    const auto resolved_configuration=artifact(ar::resolve_configuration(std::move(configuration)));
    const ar::ClockDomain clock{{"wall"},ar::ClockMetric::steady_wall,"run",1,1000,
        ar::Available<std::uint64_t>{1},"generator-adapter-test"};
    ob::PlanInput input{problem,resolved_configuration,{"generator-test-run"},{clock},{},1};
    input.tasks={"generator-test-run",task};input.operations={"operation.run",operation};
    ar::SpanDescriptor root{};root.id={0};root.task="generator-test-run";root.operation="operation.run";
    root.module=resolved_configuration.description().modules.back().implementation;root.clock={"wall"};
    root.requested_assurance=Assurance::numerical;root.applied_assurance=ar::Available<Assurance>{Assurance::numerical};
    ar::SpanDescriptor span{};span.id={1};span.parent=ar::SpanParent{{0},ar::ParentKind::nested};
    span.task=std::move(task);span.operation=std::move(operation);span.module=module;span.clock={"wall"};
    span.requested_assurance=Assurance::numerical;span.applied_assurance=ar::Available<Assurance>{Assurance::numerical};
    if(input_representation)span.input_representation=std::make_shared<const RepresentationId>(*input_representation);
    if(output_representation)span.output_representation=std::make_shared<const RepresentationId>(*output_representation);
    span.relation=relation;
    span.observation_source="src/geometry/generators/adapter.cpp";input.spans={std::move(root),std::move(span)};
    const auto plan=artifact(ob::make_collection_plan(std::move(input)));
    return artifact(ob::make_timing_collector(plan,std::make_shared<GeneratorTimingClock>(),{0},{}));
}
template<class T,class... Alternatives> T take(std::variant<T,Alternatives...> result) {
    REQUIRE(std::holds_alternative<T>(result));
    return std::get<T>(std::move(result));
}
template<class Port> registry::PreparedProvider<Port> provider(
        registry::Registration<Port> registration, RepresentationId representation) {
    registry::Registry<Port> entries;
    const registry::Method method{registration.identity.id,registration.identity.version};
    REQUIRE_FALSE(entries.add(std::move(registration)).has_value());
    registry::Requirements requirements;
    requirements.output.representation=representation;
    requirements.output.relation=SetRelation::equivalent;
    return take(registry::prepare_provider(registry::select_provider(entries,method,requirements)));
}
sets::GeneratorSet generator(std::string id,Vector center,Matrix columns,
        std::vector<sets::FactorId> factors, Matrix equalities,Vector values) {
    return take(sets::make_generator_set({{std::move(id)},std::move(center),std::move(columns),
        std::move(factors),std::move(equalities),std::move(values),{}}));
}
OperationResult run(registry::PreparedProvider<registry::GeometryPort>& selected,
        const OperationRequest& request) {
    auto prepared=take(selected.prepare(request));
    auto [workspace]=prepared.create();
    return take(workspace->run({{},{},{},{1e-8,1e-8},"geo07-port"}));
}
OperationResult run(registry::PreparedProvider<registry::ConversionPort>& selected,
        const ConversionRequest& request) {
    auto prepared=take(selected.prepare(request));
    auto [workspace]=prepared.create();
    return take(workspace->run({{},{},{},{1e-8,1e-8},"geo07-port"}));
}
bool physical_box_h(double x) { return x<=12 && -x<=-2; }
bool physical_sum_h(double x) { return x<=9 && -x<=-3; }
bool physical_diagonal_image_h(double x) { return x<=0 && -x<=0; }
bool physical_constrained_sum_h(double x) { return x<=7 && -x<=-1; }
void expect_unsupported(const std::variant<registry::PreparedPipeline<registry::GeometryPort>,
        registry::Rejection>& admission,const std::string& field) {
    const auto* rejection=std::get_if<registry::Rejection>(&admission);
    REQUIRE(rejection);
    REQUIRE(rejection->diagnostics.size()==1);
    CHECK(rejection->diagnostics[0].code==DiagnosticCode::unsupported);
    CHECK(rejection->diagnostics[0].field==field);
}
}

TEST_CASE("prepared generator geometry preserves box factors and independent sum") {
    auto geometry=provider(geometry::generators::make_operation_registration(),{"csl.zonotope"});
    const auto box=generator("box",{1,2},{2,2,{2,0,0,3}},
        {{"horizontal"},{"vertical"}},{0,2,{}},{});
    const OperationRequest image_request{{{"geo07"},{"box-image"},{"image"}},
        {"csl.geometry.generators.operations"},
        AffineImage{box.as_handle(),{1,2,{1,1}},{4}},SetRelation::equivalent,Assurance::numerical};
    const auto image_result=run(geometry,image_request);
    CHECK(image_result.relation==SetRelation::equivalent);
    CHECK(check_geometry_evidence(image_result.evidence,image_request).empty());
    const auto image=take(sets::from_generator_handle(image_result.output));
    CHECK(image.center()==Vector{7});
    CHECK(image.generators().values==Vector{2,3});
    CHECK(image.factor_ids()==std::vector<sets::FactorId>{{"horizontal"},{"vertical"}});
    for (double x:Vector{2,7,8,12}) CHECK(physical_box_h(x));
    for (double x:Vector{1,13}) CHECK_FALSE(physical_box_h(x));
    CHECK(image.center()[0]-image.generators().values[0]-image.generators().values[1]==2);
    CHECK(image.center()[0]+image.generators().values[0]+image.generators().values[1]==12);

    const auto left=generator("left",{2},{1,1,{1}},{{"a"}},{0,1,{}},{});
    const auto right=generator("right",{4},{1,1,{2}},{{"b"}},{0,1,{}},{});
    const OperationRequest sum_request{{{"geo07"},{"independent-sum"},{"sum"}},
        {"csl.geometry.generators.operations"},MinkowskiSum{left.as_handle(),right.as_handle()},
        SetRelation::equivalent,Assurance::numerical};
    const auto sum_result=run(geometry,sum_request);
    CHECK(check_geometry_evidence(sum_result.evidence,sum_request).empty());
    const auto sum=take(sets::from_generator_handle(sum_result.output));
    CHECK(sum.center()==Vector{6});
    CHECK(sum.generators().values==Vector{1,2});
    CHECK(sum.factor_ids()==std::vector<sets::FactorId>{{"a"},{"b"}});
    for (double x:Vector{3,6,9}) CHECK(physical_sum_h(x));
    for (double x:Vector{2,10}) CHECK_FALSE(physical_sum_h(x));
    CHECK(sum.center()[0]-sum.generators().values[0]-sum.generators().values[1]==3);
    CHECK(sum.center()[0]+sum.generators().values[0]+sum.generators().values[1]==9);
}

TEST_CASE("generator operation records its registered module span without changing the result") {
    namespace ar=artifacts;
    namespace ob=execution::observability;
    Problem source{{"generator-observability"},std::make_shared<const SystemModel>(SystemModel{{
        {0,0,0},TimeDomain::discrete,LinearStage{{0,0,{}},{0,0,{}},{0,0,{}},{}}},{}}),{0},
        KnownInitial{{}},ContinuousDomain{{}},{UniversalSet{0}},{},{},
        InformationPattern::nominal_open_loop,LinearTerminal{{},0}};
    auto resolved_result=problem::resolve(source,{problem::UncertaintyStructure::stage_product_uncoupled});
    REQUIRE(std::holds_alternative<problem::ResolvedProblem>(resolved_result));
    const auto resolved=std::get<problem::ResolvedProblem>(std::move(resolved_result));
    const ar::Unavailable missing{ar::MissingReason::not_instrumented,{}};
    const ar::ModuleIdentity implementation{{"csl.geometry.generators.operations"},"1.1.0",missing};
    auto timer=generator_timer(resolved,"observed-image","geometry.generators.affine-image",implementation);
    ExecutionContext context;context.run_id="generator-test-run";context.numerical={1e-8,1e-8};context.timing=timer;
    auto root=artifact(timer->start({0},context));

    auto selected=provider(geometry::generators::make_operation_registration(),{"csl.zonotope"});
    const auto input=generator("timed-box",{1},{1,1,{2}},{{"factor"}},{0,1,{}},{});
    const OperationRequest request{{resolved.identity(),{"observed-image"},{"image-result"}},
        {"csl.geometry.generators.operations"},AffineImage{input.as_handle(),{1,1,{3}},{4}},
        SetRelation::equivalent,Assurance::numerical};
    auto prepared=take(selected.prepare(request));auto [workspace]=prepared.create();
    const auto outcome=workspace->run(context);
    REQUIRE(std::holds_alternative<OperationResult>(outcome));
    CHECK(std::get<OperationResult>(outcome).relation==SetRelation::equivalent);
    const auto output=take(sets::from_generator_handle(std::get<OperationResult>(outcome).output));
    CHECK(output.center()==Vector{7});
    root.close(Termination::completed);

    const auto report=artifact(timer->snapshot());
    REQUIRE(report.spans.size()==2);
    REQUIRE(std::holds_alternative<ar::Available<std::uint64_t>>(report.spans[1].inclusive_wall_ticks));
    CHECK(std::get<ar::Available<std::uint64_t>>(report.spans[1].inclusive_wall_ticks).value==10);
    const auto& descriptor=report.observations.description().spans[1].descriptor;
    CHECK(descriptor.task=="observed-image");CHECK(descriptor.operation=="geometry.generators.affine-image");
    CHECK(descriptor.module.id==implementation.id);CHECK_FALSE(descriptor.backend);
    REQUIRE(std::holds_alternative<ar::ReturnedSpan>(report.observations.description().spans[1].status));
    CHECK(std::get<ar::ReturnedSpan>(report.observations.description().spans[1].status).termination==Termination::completed);
}

TEST_CASE("generator V conversion records its registered module span") {
    namespace ar=artifacts;
    namespace ob=execution::observability;
    Problem source{{"generator-conversion-observability"},std::make_shared<const SystemModel>(SystemModel{{
        {0,0,0},TimeDomain::discrete,LinearStage{{0,0,{}},{0,0,{}},{0,0,{}},{}}},{}}),{0},
        KnownInitial{{}},ContinuousDomain{{}},{UniversalSet{0}},{},{},
        InformationPattern::nominal_open_loop,LinearTerminal{{},0}};
    auto resolved_result=problem::resolve(source,{problem::UncertaintyStructure::stage_product_uncoupled});
    REQUIRE(std::holds_alternative<problem::ResolvedProblem>(resolved_result));
    const auto resolved=std::get<problem::ResolvedProblem>(std::move(resolved_result));
    const ar::Unavailable missing{ar::MissingReason::not_instrumented,{}};
    const ar::ModuleIdentity implementation{{"csl.geometry.generators.v-conversion"},"1.0.0",missing};
    auto timer=generator_timer(resolved,"observed-v-conversion","geometry.generators.v-conversion",implementation,
        RepresentationId{"csl.zonotope"},RepresentationId{"csl.polyhedron.v"},SetRelation::equivalent);
    ExecutionContext context;context.run_id="generator-test-run";context.numerical={1e-8,1e-8};context.timing=timer;
    auto root=artifact(timer->start({0},context));

    auto selected=provider(geometry::generators::make_v_conversion_registration(4),{"csl.polyhedron.v"});
    const auto input=generator("timed-box",{1},{1,1,{2}},{{"factor"}},{0,1,{}},{});
    const ConversionRequest request{{resolved.identity(),{"observed-v-conversion"},{"v-result"}},
        input.as_handle(),{"csl.polyhedron.v"},Assurance::numerical};
    auto prepared=take(selected.prepare(request));auto [workspace]=prepared.create();
    const auto outcome=workspace->run(context);
    REQUIRE(std::holds_alternative<OperationResult>(outcome));
    const auto output=take(sets::from_handle(std::get<OperationResult>(outcome).output));
    const auto representation=output.representation();
    REQUIRE(std::holds_alternative<sets::VRepresentation>(representation));
    CHECK(std::get<sets::VRepresentation>(representation).vertices.rows()==2);
    root.close(Termination::completed);

    const auto report=artifact(timer->snapshot());
    REQUIRE(report.spans.size()==2);
    REQUIRE(std::holds_alternative<ar::Available<std::uint64_t>>(report.spans[1].inclusive_wall_ticks));
    CHECK(std::get<ar::Available<std::uint64_t>>(report.spans[1].inclusive_wall_ticks).value==10);
    const auto& descriptor=report.observations.description().spans[1].descriptor;
    CHECK(descriptor.task=="observed-v-conversion");CHECK(descriptor.operation=="geometry.generators.v-conversion");
    CHECK(descriptor.module.id==implementation.id);
    REQUIRE(descriptor.input_representation);CHECK(*descriptor.input_representation==RepresentationId{"csl.zonotope"});
    REQUIRE(descriptor.output_representation);CHECK(*descriptor.output_representation==RepresentationId{"csl.polyhedron.v"});
    CHECK(descriptor.relation==SetRelation::equivalent);
    REQUIRE(descriptor.applied_relation);CHECK(*descriptor.applied_relation==SetRelation::equivalent);
    REQUIRE(descriptor.relation_evidence);
    CHECK(descriptor.relation_evidence->reference.inputs==std::vector<SetId>{input.as_handle().id});
    REQUIRE(std::holds_alternative<ar::ReturnedSpan>(report.observations.description().spans[1].status));
    CHECK(std::get<ar::ReturnedSpan>(report.observations.description().spans[1].status).termination==Termination::completed);
}

TEST_CASE("generator operation timing retains rejection and deadline outcomes") {
    namespace ar=artifacts;
    namespace ob=execution::observability;
    Problem source{{"generator-operation-outcomes"},std::make_shared<const SystemModel>(SystemModel{{
        {0,0,0},TimeDomain::discrete,LinearStage{{0,0,{}},{0,0,{}},{0,0,{}},{}}},{}}),{0},
        KnownInitial{{}},ContinuousDomain{{}},{UniversalSet{0}},{},{},
        InformationPattern::nominal_open_loop,LinearTerminal{{},0}};
    auto resolved_result=problem::resolve(source,{problem::UncertaintyStructure::stage_product_uncoupled});
    REQUIRE(std::holds_alternative<problem::ResolvedProblem>(resolved_result));
    const auto resolved=std::get<problem::ResolvedProblem>(std::move(resolved_result));
    const ar::Unavailable missing{ar::MissingReason::not_instrumented,{}};
    const ar::ModuleIdentity implementation{{"csl.geometry.generators.operations"},"1.1.0",missing};
    const auto input=generator("overflow-box",{0},{1,1,{2}},{{"factor"}},{0,1,{}},{});
    auto selected=provider(geometry::generators::make_operation_registration(),{"csl.zonotope"});

    auto rejected_timer=generator_timer(resolved,"rejected-image","geometry.generators.affine-image",implementation);
    ExecutionContext rejected_context;rejected_context.run_id="generator-test-run";
    rejected_context.numerical={1e-8,1e-8};rejected_context.timing=rejected_timer;
    auto rejected_root=artifact(rejected_timer->start({0},rejected_context));
    const OperationRequest rejected_request{{resolved.identity(),{"rejected-image"},{"overflow-result"}},
        {"csl.geometry.generators.operations"},
        AffineImage{input.as_handle(),{1,1,{std::numeric_limits<double>::max()}},{0}},
        SetRelation::equivalent,Assurance::numerical};
    auto rejected_prepared=take(selected.prepare(rejected_request));auto [rejected_workspace]=rejected_prepared.create();
    const auto rejected=rejected_workspace->run(rejected_context);
    REQUIRE(std::holds_alternative<Unsupported>(rejected));
    rejected_root.close(Termination::completed);
    const auto rejected_report=artifact(rejected_timer->snapshot());
    REQUIRE(rejected_report.spans.size()==2);
    REQUIRE(std::holds_alternative<ar::ReturnedSpan>(rejected_report.observations.description().spans[1].status));
    CHECK(std::get<ar::ReturnedSpan>(rejected_report.observations.description().spans[1].status).termination==
        Termination::operation_rejected);

    auto deadline_timer=generator_timer(resolved,"deadline-image","geometry.generators.affine-image",implementation);
    ExecutionContext deadline_context;deadline_context.run_id="generator-test-run";
    deadline_context.numerical={1e-8,1e-8};deadline_context.timing=deadline_timer;
    deadline_context.deadline=std::chrono::steady_clock::now()-std::chrono::milliseconds(1);
    auto deadline_root=artifact(deadline_timer->start({0},deadline_context));
    const OperationRequest deadline_request{{resolved.identity(),{"deadline-image"},{"deadline-result"}},
        {"csl.geometry.generators.operations"},AffineImage{input.as_handle(),{1,1,{1}},{0}},
        SetRelation::equivalent,Assurance::numerical};
    auto deadline_prepared=take(selected.prepare(deadline_request));auto [deadline_workspace]=deadline_prepared.create();
    const auto stopped=deadline_workspace->run(deadline_context);
    REQUIRE(std::holds_alternative<OperationStopped>(stopped));
    CHECK(std::get<OperationStopped>(stopped).reason==StopReason::deadline_expired);
    deadline_root.close(Termination::completed);
    const auto deadline_report=artifact(deadline_timer->snapshot());
    REQUIRE(deadline_report.spans.size()==2);
    REQUIRE(std::holds_alternative<ar::ReturnedSpan>(deadline_report.observations.description().spans[1].status));
    CHECK(std::get<ar::ReturnedSpan>(deadline_report.observations.description().spans[1].status).termination==
        Termination::cancelled);
}

TEST_CASE("generator geometry keeps equalities and rejects dependent Minkowski aliasing") {
    auto ordinary=provider(geometry::generators::make_operation_registration(),{"csl.zonotope"});
    auto constrained=provider(geometry::generators::make_operation_registration(),{"csl.constrained-zonotope"});
    const auto diagonal=generator("diagonal",{0,0},{2,2,{1,0,0,1}},
        {{"u"},{"v"}},{1,2,{1,-1}},{0});
    const OperationRequest image_request{{{"geo07"},{"diagonal-image"},{"diagonal-out"}},
        {"csl.geometry.generators.operations"},AffineImage{diagonal.as_handle(),{1,2,{1,-1}},{0}},
        SetRelation::equivalent,Assurance::numerical};
    CHECK(std::holds_alternative<registry::Rejection>(ordinary.prepare(image_request)));
    const auto image=take(sets::from_generator_handle(run(constrained,image_request).output));
    CHECK(image.center()==Vector{0});
    CHECK(image.generators().rows==1);
    CHECK(image.generators().cols==2);
    CHECK(image.generators().values==Vector{1,-1});
    CHECK(image.factor_ids()==std::vector<sets::FactorId>{{"u"},{"v"}});
    CHECK(image.equalities().values==Vector{1,-1});
    CHECK(image.equality_values()==Vector{0});
    for(const double factor:Vector{-1,0,1}) {
        const double x=image.center()[0]+image.generators().values[0]*factor+
            image.generators().values[1]*factor;
        CHECK(x==0);
        CHECK(physical_diagonal_image_h(x));
    }
    CHECK_FALSE(physical_diagonal_image_h(-1));
    CHECK_FALSE(physical_diagonal_image_h(1));

    const auto left=generator("left",{0},{1,1,{1}},{{"history.0"}},{0,1,{}},{});
    const auto right=generator("right",{0},{1,1,{-1}},{{"history.0"}},{0,1,{}},{});
    const OperationRequest alias{{{"geo07"},{"shared"},{"not-independent"}},
        {"csl.geometry.generators.operations"},MinkowskiSum{left.as_handle(),right.as_handle()},
        SetRelation::equivalent,Assurance::numerical};
    expect_unsupported(ordinary.prepare(alias),"generators.minkowski.factor_ids");
    auto intersection=alias;
    intersection.operation=Intersection{left.as_handle(),right.as_handle()};
    expect_unsupported(ordinary.prepare(intersection),"generators.operation");
    auto validated=alias;
    validated.operation=AffineImage{left.as_handle(),{1,1,{1}},{0}};
    validated.assurance=Assurance::validated;
    CHECK(std::holds_alternative<registry::Rejection>(ordinary.prepare(validated)));
}

TEST_CASE("registered dependent sum cancels one shared factor and binds ordered evidence") {
    auto geometry=provider(geometry::generators::make_operation_registration(),{"csl.zonotope"});
    const auto left=generator("cancel-left",{0},{1,1,{1}},{{"history.0"}},{0,1,{}},{});
    const auto right=generator("cancel-right",{0},{1,1,{-1}},{{"history.0"}},{0,1,{}},{});
    const OperationRequest request{{{"geo07"},{"dependent-cancel"},{"origin"}},
        {"csl.geometry.generators.operations"},DependentSum{left.as_handle(),right.as_handle()},
        SetRelation::equivalent,Assurance::numerical};
    const auto result=run(geometry,request);
    CHECK(result.relation==SetRelation::equivalent);
    CHECK(check_geometry_evidence(result.evidence,request).empty());
    const auto sum=take(sets::from_generator_handle(result.output));
    CHECK(sum.center()==Vector{0});
    CHECK(sum.generators().values==Vector{0});
    CHECK(sum.factor_ids()==std::vector<sets::FactorId>{{"history.0"}});
    CHECK(sum.equalities().rows==0);
    CHECK(sum.center()[0]-sum.generators().values[0]==0);
    CHECK(sum.center()[0]+sum.generators().values[0]==0);
    CHECK((sum.center()[0]<=0 && -sum.center()[0]<=0)); // literal H: x <= 0, -x <= 0
    CHECK_FALSE((1<=0 && -1<=0));
    auto swapped=request;
    swapped.operation=DependentSum{right.as_handle(),left.as_handle()};
    CHECK_FALSE(check_geometry_evidence(result.evidence,swapped).empty());
    auto independent=request;
    independent.operation=MinkowskiSum{left.as_handle(),right.as_handle()};
    expect_unsupported(geometry.prepare(independent),"generators.minkowski.factor_ids");
    auto validated=request;
    validated.assurance=Assurance::validated;
    CHECK(std::holds_alternative<registry::Rejection>(geometry.prepare(validated)));
    auto forged=left.as_handle();
    forged.metadata.representation={"csl.polyhedron.h"};
    auto wrong_representation=request;
    wrong_representation.operation=DependentSum{forged,right.as_handle()};
    CHECK(std::holds_alternative<registry::Rejection>(geometry.prepare(wrong_representation)));
    const auto labelled=take(sets::make_generator_set({{"labelled"},{0},{1,1,{1}},
        {{"history.0"}},{0,1,{}},{},{"x"}}));
    auto wrong_labels=request;
    wrong_labels.operation=DependentSum{labelled.as_handle(),right.as_handle()};
    const auto label_rejection=geometry.prepare(wrong_labels);
    const auto* rejection=std::get_if<registry::Rejection>(&label_rejection);
    REQUIRE(rejection);
    REQUIRE(rejection->diagnostics.size()==1);
    CHECK(rejection->diagnostics.front().field=="generators.dependent.labels");
}

TEST_CASE("registered dependent constrained sum retains shared axes and both equalities") {
    auto geometry=provider(geometry::generators::make_operation_registration(),
        {"csl.constrained-zonotope"});
    const auto left=generator("dependent-left",{0,0},{2,2,{1,0,0,1}},
        {{"u"},{"v"}},{1,2,{1,-1}},{0});
    const auto right=generator("dependent-right",{0,0},{2,2,{-1,0,0,1}},
        {{"u"},{"w"}},{1,2,{1,1}},{0});
    const OperationRequest request{{{"geo07"},{"dependent-constrained"},{"origin-2d"}},
        {"csl.geometry.generators.operations"},DependentSum{left.as_handle(),right.as_handle()},
        SetRelation::equivalent,Assurance::numerical};
    const auto result=run(geometry,request);
    CHECK(check_geometry_evidence(result.evidence,request).empty());
    const auto sum=take(sets::from_generator_handle(result.output));
    CHECK(sum.center()==Vector{0,0});
    CHECK(sum.factor_ids()==std::vector<sets::FactorId>{{"u"},{"v"},{"w"}});
    CHECK(sum.generators().values==Vector{0,0,0,0,1,1});
    CHECK(sum.equalities().rows==2);
    CHECK(sum.equalities().values==Vector{1,-1,0,1,0,1});
    CHECK(sum.equality_values()==Vector{0,0});
    const auto lifted=take(sets::factor_polyhedron(sum));
    CHECK(lifted.factor_ids==sum.factor_ids());
    // The authored H reference is x=0,y=0: both equalities force v=u,w=-u.
    for(const double u:Vector{-1,0,1}) {
        const Vector factors{u,u,-u};
        CHECK(factors[0]-factors[1]==0); // literal left equality
        CHECK(factors[0]+factors[2]==0); // literal right equality
        const Vector physical{
            lifted.offset[0]+lifted.map.values[0]*factors[0]+
                lifted.map.values[1]*factors[1]+lifted.map.values[2]*factors[2],
            lifted.offset[1]+lifted.map.values[3]*factors[0]+
                lifted.map.values[4]*factors[1]+lifted.map.values[5]*factors[2]};
        CHECK(physical==Vector{0,0}); // literal ambient H: x=0, y=0
    }
    const Vector infeasible{1,1,0};
    CHECK(infeasible[0]-infeasible[1]==0);
    CHECK_FALSE(infeasible[0]+infeasible[2]==0); // right equality excludes it
    const Vector outside{
        lifted.offset[0]+lifted.map.values[0]*infeasible[0]+
            lifted.map.values[1]*infeasible[1]+lifted.map.values[2]*infeasible[2],
        lifted.offset[1]+lifted.map.values[3]*infeasible[0]+
            lifted.map.values[4]*infeasible[1]+lifted.map.values[5]*infeasible[2]};
    CHECK(outside==Vector{0,1});
    CHECK_FALSE(outside==Vector{0,0}); // literal ambient H excludes (0,1)
}

TEST_CASE("prepared disjoint constrained Minkowski sum keeps both equalities and physical interval") {
    auto constrained=provider(geometry::generators::make_operation_registration(),
        {"csl.constrained-zonotope"});
    // Left: x=1+u, u=v. Right: x=3+2q, p=-q.
    const auto left=generator("left-constrained",{1},{1,2,{1,0}},
        {{"u"},{"v"}},{1,2,{1,-1}},{0});
    const auto right=generator("right-constrained",{3},{1,2,{0,2}},
        {{"p"},{"q"}},{1,2,{1,1}},{0});
    const OperationRequest request{{{"geo07"},{"constrained-independent-sum"},{"constrained-sum"}},
        {"csl.geometry.generators.operations"},MinkowskiSum{left.as_handle(),right.as_handle()},
        SetRelation::equivalent,Assurance::numerical};
    const auto result=run(constrained,request);
    CHECK(result.relation==SetRelation::equivalent);
    CHECK(check_geometry_evidence(result.evidence,request).empty());
    const auto sum=take(sets::from_generator_handle(result.output));
    CHECK(sum.center()==Vector{4});
    CHECK(sum.generators().rows==1);
    CHECK(sum.generators().cols==4);
    CHECK(sum.generators().values==Vector{1,0,0,2});
    CHECK(sum.factor_ids()==std::vector<sets::FactorId>{{"u"},{"v"},{"p"},{"q"}});
    CHECK(sum.equalities().rows==2);
    CHECK(sum.equalities().cols==4);
    CHECK(sum.equalities().values==Vector{1,-1,0,0,0,0,1,1});
    CHECK(sum.equality_values()==Vector{0,0});
    for(const auto [u,q,expected_x]:std::vector<std::tuple<double,double,double>>{
            {-1,-1,1},{0,0,4},{1,1,7}}) {
        const Vector factors{u,u,-q,q};
        const double x=sum.center()[0]+sum.generators().values[0]*factors[0]+
            sum.generators().values[1]*factors[1]+sum.generators().values[2]*factors[2]+
            sum.generators().values[3]*factors[3];
        CHECK(x==expected_x);
        CHECK(physical_constrained_sum_h(x));
    }
    CHECK_FALSE(physical_constrained_sum_h(0));
    CHECK_FALSE(physical_constrained_sum_h(8));
}

TEST_CASE("bounded explicit zonotope to V conversion has literal vertices and closure gates") {
    auto converter=provider(geometry::generators::make_v_conversion_registration(4),{"csl.polyhedron.v"});
    const auto segment=generator("image",{7},{1,2,{2,3}},
        {{"horizontal"},{"vertical"}},{0,2,{}},{});
    const ConversionRequest request{{{"geo07"},{"convert"},{"image-v"}},
        segment.as_handle(),{"csl.polyhedron.v"},Assurance::numerical};
    const auto converted=run(converter,request);
    CHECK(converted.relation==SetRelation::equivalent);
    CHECK(check_geometry_evidence(converted.evidence,request).empty());
    const auto data=take(sets::from_handle(converted.output));
    const auto representation=data.representation();
    const auto* v=std::get_if<sets::VRepresentation>(&representation);
    REQUIRE(v);
    CHECK(v->rays.rows()==0);
    CHECK(v->vertices.rows()==4);
    std::set<double> observed;
    for(std::size_t row=0;row<v->vertices.rows();++row) {
        const double x=v->vertices(row,0);
        CHECK(physical_box_h(x));
        observed.insert(x);
    }
    CHECK(observed==std::set<double>{2,6,8,12});
    CHECK_FALSE(physical_box_h(1));
    CHECK_FALSE(physical_box_h(13));

    auto too_small=provider(geometry::generators::make_v_conversion_registration(3),{"csl.polyhedron.v"});
    CHECK(std::holds_alternative<registry::Rejection>(too_small.prepare(request)));
    const auto constrained=generator("constrained",{0},{1,1,{1}},{{"q"}},
        {1,1,{1}},{0});
    auto restricted=request;
    restricted.input=constrained.as_handle();
    CHECK(std::holds_alternative<registry::Rejection>(converter.prepare(restricted)));
    restricted=request;
    restricted.assurance=Assurance::validated;
    CHECK(std::holds_alternative<registry::Rejection>(converter.prepare(restricted)));
    restricted=request;
    restricted.output={"csl.polyhedron.h"};
    CHECK(std::holds_alternative<registry::Rejection>(converter.prepare(restricted)));

    const auto point=generator("point",{3,-1},{2,0,{}},{},{0,0,{}},{});
    restricted=request;
    restricted.input=point.as_handle();
    const auto point_result=run(converter,restricted);
    const auto point_data=take(sets::from_handle(point_result.output));
    const auto point_v=std::get<sets::VRepresentation>(point_data.representation());
    CHECK(point_v.vertices.rows()==1);
    CHECK(point_v.vertices(0,0)==3);
    CHECK(point_v.vertices(0,1)==-1);
}

TEST_CASE("future zonotope and ellipsoid payloads need explicit geometry and conversion adapters") {
    const SetHandle future_ellipsoid{{2,{"test.future.ellipsoid"},SetProperty::yes,
        SetProperty::no,SetProperty::yes},std::make_shared<const FutureRepresentationPayload>(),{"future/ellipsoid"}};
    const SetHandle future_zonotope{{2,{"test.future.zonotope"},SetProperty::yes,
        SetProperty::yes,SetProperty::yes},std::make_shared<const FutureRepresentationPayload>(),{"future/zonotope"}};

    auto sum_adapter=provider(geometry::generators::make_operation_registration(),{"csl.zonotope"});
    const OperationRequest sum{{{"future-representation"},{"sum"},{"sum-result"}},
        {"csl.geometry.generators.operations"},MinkowskiSum{future_ellipsoid,future_zonotope},
        SetRelation::equivalent,Assurance::numerical};
    const auto sum_result=sum_adapter.prepare(sum);
    REQUIRE(std::holds_alternative<registry::Rejection>(sum_result));
    CHECK(std::get<registry::Rejection>(sum_result).diagnostics.front().field=="generators.handle");

    auto converter=provider(geometry::generators::make_v_conversion_registration(16),
        {"csl.polyhedron.v"});
    const ConversionRequest conversion{{{"future-representation"},{"convert"},{"v-result"}},
        future_ellipsoid,{"csl.polyhedron.v"},Assurance::numerical};
    const auto conversion_result=converter.prepare(conversion);
    REQUIRE(std::holds_alternative<registry::Rejection>(conversion_result));
    CHECK(std::get<registry::Rejection>(conversion_result).diagnostics.front().field=="generators.handle");
}
