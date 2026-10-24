#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <csl/geometry/approximation.hpp>
#include <csl/execution/timing_collector.hpp>
#include <csl/sets/data.hpp>
#include <csl/sets/generator_sets.hpp>
#include <limits>
#include <cmath>
#include <chrono>
#include <stop_token>

using namespace csl;
using namespace csl::geometry::approximation;

namespace {
sets::SetData take(sets::Result<sets::SetData> value) {
    REQUIRE(std::holds_alternative<sets::SetData>(value));
    return std::get<sets::SetData>(std::move(value));
}
SetHandle set(const char* kind, const char* id, const char* coordinate="x") {
    sets::Description description{{id},1,{coordinate}};
    if (std::string(kind)=="empty") return take(sets::make_empty(description)).as_handle();
    if (std::string(kind)=="universal") return take(sets::make_universal(description)).as_handle();
    const Vector point{1.0};
    auto view=numeric::snapshot_vector(point);
    REQUIRE(std::holds_alternative<numeric::VectorView>(view));
    return take(sets::make_singleton(description,std::get<numeric::VectorView>(view))).as_handle();
}
SetHandle point_set(const char* id, double value, const char* coordinate="x") {
    auto point=numeric::snapshot_vector(Vector{value});
    REQUIRE(std::holds_alternative<numeric::VectorView>(point));
    return take(sets::make_singleton({{id},1,{coordinate}},
        std::get<numeric::VectorView>(point))).as_handle();
}
SetHandle two_points(const char* id) {
    const auto vertices=numeric::snapshot(Matrix{2,1,{0.0,1.0}});
    const auto rays=numeric::snapshot(Matrix{0,1,{}});
    REQUIRE(std::holds_alternative<numeric::MatrixView>(vertices));
    REQUIRE(std::holds_alternative<numeric::MatrixView>(rays));
    return take(sets::make_v({{id},1,{"x"}},
        {std::get<numeric::MatrixView>(vertices),std::get<numeric::MatrixView>(rays)})).as_handle();
}
class OpaqueFuturePayload final : public SetPayload {};
class ApproximationTimingClock final:public execution::observability::TimingClock {
    std::int64_t tick_{};
public:
    artifacts::ClockDomain wall_domain() const override {
        return {{"wall"},artifacts::ClockMetric::steady_wall,"run",1,1000,
            artifacts::Available<std::uint64_t>{1},"approximation-policy-test"};
    }
    std::optional<artifacts::ClockDomain> cpu_domain() const override{return {};}
    artifacts::Metric<std::int64_t> wall_now() noexcept override {
        const auto value=tick_;tick_+=10;return artifacts::Available<std::int64_t>{value};
    }
    artifacts::Metric<std::int64_t> cpu_now() noexcept override {
        return artifacts::Unavailable{artifacts::MissingReason::not_supported,{}};
    }
};
SetHandle h_set(const char* id, Vector inequality_rows, Vector upper_bounds,
                Vector equality_rows = {}, Vector equality_values = {},
                const char* coordinate = "x") {
    const auto inequalities = numeric::snapshot(Matrix{inequality_rows.size(),1,std::move(inequality_rows)});
    const auto bounds = numeric::snapshot_vector(upper_bounds);
    const auto equalities = numeric::snapshot(Matrix{equality_rows.size(),1,std::move(equality_rows)});
    const auto values = numeric::snapshot_vector(equality_values);
    REQUIRE(std::holds_alternative<numeric::MatrixView>(inequalities));
    REQUIRE(std::holds_alternative<numeric::VectorView>(bounds));
    REQUIRE(std::holds_alternative<numeric::MatrixView>(equalities));
    REQUIRE(std::holds_alternative<numeric::VectorView>(values));
    return take(sets::make_h({{id},1,{coordinate}},
        {std::get<numeric::MatrixView>(inequalities),std::get<numeric::VectorView>(bounds),
         std::get<numeric::MatrixView>(equalities),std::get<numeric::VectorView>(values)})).as_handle();
}
ApproximationRequest request(SetHandle input, SetRelation relation, RepresentationId representation) {
    return {{{"problem/a"},{"approx/a"},{"reference/a"}},std::move(input),std::move(representation),relation,2,Assurance::numerical};
}
class FixedWorkspace final : public SetApproximatorWorkspace {
    OperationResult result_;
public:
    explicit FixedWorkspace(OperationResult result):result_(std::move(result)){}
    SetTransformOutcome approximate(const ApproximationRequest&,const ExecutionContext&) override {return result_;}
};
registry::Registry<registry::ApproximationPort> provider(const ApproximationRequest& request,
    SetHandle output, SetRelation offered, SetRelation returned, EvidenceSupport support=Unestablished{},
    std::optional<GeometryErrorBound> error_bound=std::nullopt,
    std::shared_ptr<std::size_t> factory_creations={},std::vector<std::string> assumptions={}) {
    registry::Registry<registry::ApproximationPort> result;
    GeometryEvidence evidence{{request.identity,{request.input.id}},GeometryClaimScope::set_relation,
        std::move(support),std::move(assumptions),std::move(error_bound)};
    OperationResult fixed{std::move(output),returned,std::move(evidence)};
    auto added=result.add({{{"fixture.approximation"},"1"},
        [offered](const ApproximationRequest& query,const registry::Requirements&) -> registry::Capability {
            registry::Output output;output.representation=query.output;output.relation=offered;
            return registry::Offer{output};
        },
        [fixed,factory_creations](const ApproximationRequest&) {
            if(factory_creations)++*factory_creations;
            return std::make_unique<FixedWorkspace>(fixed);
        }});
    REQUIRE_FALSE(added.has_value());
    return result;
}
auto execute(const registry::Registry<registry::ApproximationPort>& registry,const ApproximationRequest& query) {
    return run_registered(registry,{{"fixture.approximation"},std::nullopt},query,ExecutionContext{});
}
std::shared_ptr<execution::observability::TimingCollector> approximation_timer(
        const problem::ResolvedProblem& problem,const ApproximationRequest& request) {
    namespace ar=artifacts;
    namespace ob=execution::observability;
    const ar::Unavailable missing{ar::MissingReason::not_instrumented,{}};
    const ar::ModuleIdentity provider{{"fixture.approximation"},"1",missing};
    ar::ConfigurationInput configuration;
    configuration.collection={true,ar::CollectionMode::detail,4,2048,4,1024};
    configuration.modules={{"geometry",provider,{}},
        {"strategy",{{"test.strategy"},"1",missing},{}}};
    configuration.resources={1,1,1,{}};configuration.numerical={1e-8,1e-8};
    configuration.output={ar::OutputKind::program,Assurance::numerical,
        FamilyTarget::candidate_relaxation,{request.output},{1,0,{},{}}};
    configuration.selector={{"test.selector"},"1",{}};
    configuration.strategy={{"test.strategy"},{},{},{},provider.id,{},{},
        {"test.selector"},{request.output.value}};
    auto resolved_configuration=ar::resolve_configuration(std::move(configuration));
    REQUIRE(std::holds_alternative<ar::ResolvedConfiguration>(resolved_configuration));
    const auto config=std::get<ar::ResolvedConfiguration>(std::move(resolved_configuration));
    const ar::ClockDomain clock{{"wall"},ar::ClockMetric::steady_wall,"run",1,1000,
        ar::Available<std::uint64_t>{1},"approximation-policy-test"};
    ob::PlanInput input{problem,config,{"approximation-test-run"},{clock},{},1};
    const std::string task=request.identity.request.value;
    input.tasks={"approximation-test-run",task};
    input.operations={"operation.run","geometry.approximation.execute"};
    ar::SpanDescriptor root{};root.id={0};root.task="approximation-test-run";root.operation="operation.run";
    root.module=config.description().modules.back().implementation;root.clock={"wall"};
    root.requested_assurance=Assurance::numerical;
    root.applied_assurance=ar::Available<Assurance>{Assurance::numerical};
    ar::SpanDescriptor span{};span.id={1};span.parent=ar::SpanParent{{0},ar::ParentKind::nested};
    span.task=task;span.operation="geometry.approximation.execute";span.module=provider;span.clock={"wall"};
    span.input_representation=std::make_shared<const RepresentationId>(request.input.metadata.representation);
    span.output_representation=std::make_shared<const RepresentationId>(request.output);
    span.relation=request.direction;span.requested_assurance=request.assurance;
    span.applied_assurance=ar::Available<Assurance>{request.assurance};
    span.observation_source="src/geometry/approximation/policy.cpp";
    input.spans={std::move(root),std::move(span)};
    auto plan=ob::make_collection_plan(std::move(input));
    REQUIRE(std::holds_alternative<ob::CollectionPlan>(plan));
    auto collector=ob::make_timing_collector(std::get<ob::CollectionPlan>(std::move(plan)),
        std::make_shared<ApproximationTimingClock>(),{0},{});
    REQUIRE(std::holds_alternative<std::shared_ptr<ob::TimingCollector>>(collector));
    return std::get<std::shared_ptr<ob::TimingCollector>>(std::move(collector));
}
SetHandle generator_set(const char* id, Vector center, Matrix columns,
                        std::vector<const char*> names, Matrix equalities = {},
                        Vector equality_values = {}) {
    std::vector<sets::FactorId> factors;
    for (const char* name:names) factors.push_back({name});
    const auto dimension=center.size();
    if (equalities.rows==0) equalities.cols=factors.size();
    auto result=sets::make_generator_set({{id},std::move(center),std::move(columns),
        std::move(factors),std::move(equalities),std::move(equality_values),
        dimension==2?std::vector<std::string>{"x","y"}:std::vector<std::string>{"x"}});
    REQUIRE(std::holds_alternative<sets::GeneratorSet>(result));
    return std::get<sets::GeneratorSet>(std::move(result)).as_handle();
}
}

TEST_CASE("native generator axis cover independently admits an outer relation") {
    auto source=generator_set("source",{0,0},{2,2,{1,0.5,0.5,1}}, {"a","b"});
    auto outer=generator_set("outer",{0,0},{2,2,{1.5,0,0,1.5}}, {"axis-x","axis-y"});
    auto query=request(source,SetRelation::outer,outer.metadata.representation);
    query.size_budget=2;
    auto outcome=execute(provider(query,outer,SetRelation::outer,SetRelation::outer),query);
    REQUIRE(std::holds_alternative<EnclosedApproximation>(outcome));
    CHECK(std::get<EnclosedApproximation>(outcome).result.output.id==SetId{"outer"});

    auto too_small=generator_set("too-small",{0,0},{2,2,{1.25,0,0,1.5}}, {"axis-x","axis-y"});
    outcome=execute(provider(query,too_small,SetRelation::outer,SetRelation::outer),query);
    REQUIRE(std::holds_alternative<Unsupported>(outcome));

    query.size_budget=1;
    outcome=execute(provider(query,outer,SetRelation::outer,SetRelation::outer),query);
    REQUIRE(std::holds_alternative<Unsupported>(outcome));
    CHECK(std::get<Unsupported>(outcome).diagnostics[0].field=="approximation.budget");

    auto changed_shared=generator_set("changed-shared",{0,0},
        {2,2,{1.25,0,0.5,1.5}}, {"a","axis-y"});
    query.size_budget=2;
    outcome=execute(provider(query,changed_shared,SetRelation::outer,SetRelation::outer),query);
    REQUIRE(std::holds_alternative<Unsupported>(outcome));

    auto skew=generator_set("skew",{0,0},{2,1,{1.5,1.5}}, {"new"});
    outcome=execute(provider(query,skew,SetRelation::outer,SetRelation::outer),query);
    REQUIRE(std::holds_alternative<Unsupported>(outcome));
}

TEST_CASE("generator cover uses exact stored binary64 sums and relaxes source equalities") {
    auto source=generator_set("source",{0},{1,2,{0.1,0.2}}, {"shared","other"},
        {1,2,{1,0}},{0});
    auto rounded=generator_set("rounded",{0},{1,1,{0.3}}, {"axis"});
    auto query=request(source,SetRelation::outer,rounded.metadata.representation);
    query.size_budget=1;
    auto outcome=execute(provider(query,rounded,SetRelation::outer,SetRelation::outer),query);
    REQUIRE(std::holds_alternative<Unsupported>(outcome));

    auto outward=generator_set("outward",{0},
        {1,1,{std::nextafter(0.3,std::numeric_limits<double>::infinity())}}, {"axis"});
    outcome=execute(provider(query,outward,SetRelation::outer,SetRelation::outer),query);
    REQUIRE(std::holds_alternative<EnclosedApproximation>(outcome));
    CHECK(std::get<EnclosedApproximation>(outcome).basis==StructuralBasis::generator_axis_cover);
}

TEST_CASE("registered inner approximation admits a structurally empty subset") {
    auto input=set("singleton","reference");
    auto output=set("empty","inner");
    auto query=request(input,SetRelation::inner,output.metadata.representation);
    auto methods=provider(query,output,SetRelation::inner,SetRelation::inner);
    auto outcome=execute(methods,query);
    REQUIRE(std::holds_alternative<EnclosedApproximation>(outcome));
    const auto& admitted=std::get<EnclosedApproximation>(outcome);
    CHECK(admitted.result.relation==SetRelation::inner);
    CHECK(admitted.basis==StructuralBasis::empty_subset);
    CHECK(admitted.result.output.id==SetId{"inner"});
    CHECK(admitted.result.evidence.reference.identity==query.identity);
    CHECK(admitted.result.evidence.reference.inputs==std::vector<SetId>{input.id});
}

TEST_CASE("registered outer approximation admits a universal superset") {
    auto input=set("singleton","reference");
    auto output=set("universal","outer");
    auto query=request(input,SetRelation::outer,output.metadata.representation);
    auto methods=provider(query,output,SetRelation::outer,SetRelation::outer);
    auto outcome=execute(methods,query);
    REQUIRE(std::holds_alternative<EnclosedApproximation>(outcome));
    const auto& admitted=std::get<EnclosedApproximation>(outcome);
    CHECK(admitted.result.relation==SetRelation::outer);
    CHECK(admitted.basis==StructuralBasis::universal_superset);
    CHECK(admitted.result.evidence.reference.identity==query.identity);
    CHECK(admitted.result.evidence.reference.inputs==std::vector<SetId>{input.id});
}

TEST_CASE("native V to H verification observes cancellation and deadline") {
    auto input=two_points("reference");
    auto output=h_set("outer",{1.0,-1.0},{1.0,0.0});
    auto query=request(input,SetRelation::outer,output.metadata.representation);
    auto methods=provider(query,output,SetRelation::outer,SetRelation::outer);
    std::stop_source source;
    source.request_stop();
    ExecutionContext context;
    context.cancellation=source.get_token();
    auto cancelled=run_registered(methods,{{"fixture.approximation"},std::nullopt},query,context);
    REQUIRE(std::holds_alternative<OperationStopped>(cancelled));
    CHECK(std::get<OperationStopped>(cancelled).reason==StopReason::cancelled);

    context={};
    context.deadline=std::chrono::steady_clock::now()-std::chrono::seconds(1);
    auto expired=run_registered(methods,{{"fixture.approximation"},std::nullopt},query,context);
    REQUIRE(std::holds_alternative<OperationStopped>(expired));
    CHECK(std::get<OperationStopped>(expired).reason==StopReason::deadline_expired);
}

TEST_CASE("dropping a native H constraint admits a nontrivial outer enclosure") {
    auto input=h_set("reference",{1.0,-1.0},{2.0,1.0}); // [-1,2]
    auto output=h_set("outer",{-1.0},{1.0}); // [-1,+infinity)
    auto query=request(input,SetRelation::outer,output.metadata.representation);
    query.size_budget=1;
    auto outcome=execute(provider(query,output,SetRelation::outer,SetRelation::outer),query);
    REQUIRE(std::holds_alternative<EnclosedApproximation>(outcome));
    CHECK(std::get<EnclosedApproximation>(outcome).result.output.id==SetId{"outer"});
    CHECK(std::get<EnclosedApproximation>(outcome).basis==StructuralBasis::h_constraint_containment);
}

TEST_CASE("adding a native H equality admits a nontrivial inner enclosure") {
    auto input=h_set("reference",{1.0,-1.0},{2.0,1.0}); // [-1,2]
    auto output=h_set("inner",{-1.0,1.0},{1.0,2.0},{1.0},{0.0}); // {0}
    auto query=request(input,SetRelation::inner,output.metadata.representation);
    query.size_budget=3;
    auto outcome=execute(provider(query,output,SetRelation::inner,SetRelation::inner),query);
    REQUIRE(std::holds_alternative<EnclosedApproximation>(outcome));
    CHECK(std::get<EnclosedApproximation>(outcome).result.output.id==SetId{"inner"});
    CHECK(std::get<EnclosedApproximation>(outcome).basis==StructuralBasis::h_constraint_containment);
}

TEST_CASE("different H coefficients or coordinate labels do not prove enclosure") {
    auto input=h_set("reference",{1.0,-1.0},{2.0,1.0});
    auto changed=h_set("changed",{1.0},{3.0}); // Not an authored reference row.
    auto query=request(input,SetRelation::outer,changed.metadata.representation);
    auto outcome=execute(provider(query,changed,SetRelation::outer,SetRelation::outer),query);
    REQUIRE(std::holds_alternative<Unsupported>(outcome));
    CHECK(std::get<Unsupported>(outcome).diagnostics[0].field=="approximation.inclusion");

    auto relabeled=h_set("relabeled",{1.0},{2.0},{},{},"y");
    query=request(input,SetRelation::outer,relabeled.metadata.representation);
    outcome=execute(provider(query,relabeled,SetRelation::outer,SetRelation::outer),query);
    REQUIRE(std::holds_alternative<Unsupported>(outcome));
    CHECK(std::get<Unsupported>(outcome).diagnostics[0].field=="approximation.inclusion");
}

TEST_CASE("dropping an H equality supports only the outer direction") {
    auto input=h_set("reference",{1.0},{2.0},{1.0},{0.0}); // {0}
    auto output=h_set("candidate",{1.0},{2.0}); // (-infinity,2]
    auto query=request(input,SetRelation::outer,output.metadata.representation);
    auto outcome=execute(provider(query,output,SetRelation::outer,SetRelation::outer),query);
    REQUIRE(std::holds_alternative<EnclosedApproximation>(outcome)); // Dropping equality is a sound outer relation.
    CHECK(std::get<EnclosedApproximation>(outcome).basis==StructuralBasis::h_constraint_containment);

    query=request(input,SetRelation::inner,output.metadata.representation);
    outcome=execute(provider(query,output,SetRelation::inner,SetRelation::inner),query);
    REQUIRE(std::holds_alternative<Unsupported>(outcome));
    CHECK(std::get<Unsupported>(outcome).diagnostics[0].field=="approximation.inclusion");
}

TEST_CASE("a singleton satisfying every H row is an admitted inner enclosure") {
    auto input=h_set("reference",{1.0,-1.0},{2.0,1.0},{1.0},{0.0});
    auto output=point_set("inner",0.0);
    auto query=request(input,SetRelation::inner,output.metadata.representation);
    query.size_budget=1;
    auto outcome=execute(provider(query,output,SetRelation::inner,SetRelation::inner),query);
    REQUIRE(std::holds_alternative<EnclosedApproximation>(outcome));
    CHECK(std::get<EnclosedApproximation>(outcome).basis==StructuralBasis::h_point_containment);

    output=point_set("outside",1.0);
    query=request(input,SetRelation::inner,output.metadata.representation);
    outcome=execute(provider(query,output,SetRelation::inner,SetRelation::inner),query);
    REQUIRE(std::holds_alternative<Unsupported>(outcome));
    CHECK(std::get<Unsupported>(outcome).diagnostics[0].field=="approximation.inclusion");
}

TEST_CASE("H rows containing the reference singleton are an admitted outer enclosure") {
    auto input=point_set("reference",1.0);
    auto output=h_set("outer",{1.0,-1.0},{2.0,-1.0});
    auto query=request(input,SetRelation::outer,output.metadata.representation);
    auto outcome=execute(provider(query,output,SetRelation::outer,SetRelation::outer),query);
    REQUIRE(std::holds_alternative<EnclosedApproximation>(outcome));
    CHECK(std::get<EnclosedApproximation>(outcome).basis==StructuralBasis::h_point_containment);

    output=h_set("outside",{1.0},{0.0});
    query=request(input,SetRelation::outer,output.metadata.representation);
    outcome=execute(provider(query,output,SetRelation::outer,SetRelation::outer),query);
    REQUIRE(std::holds_alternative<Unsupported>(outcome));
    CHECK(std::get<Unsupported>(outcome).diagnostics[0].field=="approximation.inclusion");
}

TEST_CASE("H point containment uses exact stored binary64 values and ordered coordinates") {
    auto input=point_set("reference",0.3);
    auto output=h_set("rounded",{0.1},{0.03});
    auto query=request(input,SetRelation::outer,output.metadata.representation);
    auto outcome=execute(provider(query,output,SetRelation::outer,SetRelation::outer),query);
    REQUIRE(std::holds_alternative<Unsupported>(outcome));
    CHECK(std::get<Unsupported>(outcome).diagnostics[0].field=="approximation.inclusion");

    output=h_set("relabeled",{1.0},{1.0},{},{},"y");
    query=request(input,SetRelation::outer,output.metadata.representation);
    outcome=execute(provider(query,output,SetRelation::outer,SetRelation::outer),query);
    REQUIRE(std::holds_alternative<Unsupported>(outcome));
    CHECK(std::get<Unsupported>(outcome).diagnostics[0].field=="approximation.inclusion");
}

TEST_CASE("outer H slabs independently contain every vertex and recession ray of a V polygon") {
    const auto vertices=numeric::snapshot(Matrix{4,2,{0.0,2.0,2.0,0.0,0.0,-2.0,-2.0,0.0}});
    const auto rays=numeric::snapshot(Matrix{0,2,{}});
    REQUIRE(std::holds_alternative<numeric::MatrixView>(vertices));
    REQUIRE(std::holds_alternative<numeric::MatrixView>(rays));
    const auto source=take(sets::make_v({{"diamond"},2,{"x","y"}},
        {std::get<numeric::MatrixView>(vertices),std::get<numeric::MatrixView>(rays)})).as_handle();
    const auto rows=numeric::snapshot(Matrix{4,2,{1,0,-1,0,0,1,0,-1}});
    const auto bounds=numeric::snapshot_vector(Vector{2,2,2,2});
    const auto no_rows=numeric::snapshot(Matrix{0,2,{}});
    const auto no_values=numeric::snapshot_vector(Vector{});
    REQUIRE(std::holds_alternative<numeric::MatrixView>(rows));
    REQUIRE(std::holds_alternative<numeric::VectorView>(bounds));
    REQUIRE(std::holds_alternative<numeric::MatrixView>(no_rows));
    REQUIRE(std::holds_alternative<numeric::VectorView>(no_values));
    const auto outer=take(sets::make_h({{"box"},2,{"x","y"}},
        {std::get<numeric::MatrixView>(rows),std::get<numeric::VectorView>(bounds),
         std::get<numeric::MatrixView>(no_rows),std::get<numeric::VectorView>(no_values)})).as_handle();
    auto query=request(source,SetRelation::outer,outer.metadata.representation);
    query.size_budget=4;
    const auto admitted=execute(provider(query,outer,SetRelation::outer,SetRelation::outer),query);
    REQUIRE(std::holds_alternative<EnclosedApproximation>(admitted));
    CHECK(std::get<EnclosedApproximation>(admitted).basis==StructuralBasis::v_h_containment);

    const auto tight_bounds=numeric::snapshot_vector(Vector{1.5,2,2,2});
    REQUIRE(std::holds_alternative<numeric::VectorView>(tight_bounds));
    const auto tight=take(sets::make_h({{"too-tight"},2,{"x","y"}},
        {std::get<numeric::MatrixView>(rows),std::get<numeric::VectorView>(tight_bounds),
         std::get<numeric::MatrixView>(no_rows),std::get<numeric::VectorView>(no_values)})).as_handle();
    CHECK(std::holds_alternative<Unsupported>(execute(
        provider(query,tight,SetRelation::outer,SetRelation::outer),query)));
}

TEST_CASE("inner V polygon checks every corner against the native H reference") {
    const auto rows=numeric::snapshot(Matrix{4,2,{1,1,1,-1,-1,1,-1,-1}});
    const auto bounds=numeric::snapshot_vector(Vector{2,2,2,2});
    const auto no_rows=numeric::snapshot(Matrix{0,2,{}});
    const auto no_values=numeric::snapshot_vector(Vector{});
    REQUIRE(std::holds_alternative<numeric::MatrixView>(rows));
    REQUIRE(std::holds_alternative<numeric::VectorView>(bounds));
    REQUIRE(std::holds_alternative<numeric::MatrixView>(no_rows));
    REQUIRE(std::holds_alternative<numeric::VectorView>(no_values));
    const auto source=take(sets::make_h({{"diamond"},2,{"x","y"}},
        {std::get<numeric::MatrixView>(rows),std::get<numeric::VectorView>(bounds),
         std::get<numeric::MatrixView>(no_rows),std::get<numeric::VectorView>(no_values)})).as_handle();
    const auto corners=numeric::snapshot(Matrix{4,2,{1,1,1,-1,-1,-1,-1,1}});
    const auto no_rays=numeric::snapshot(Matrix{0,2,{}});
    REQUIRE(std::holds_alternative<numeric::MatrixView>(corners));
    REQUIRE(std::holds_alternative<numeric::MatrixView>(no_rays));
    const auto inner=take(sets::make_v({{"inner-box"},2,{"x","y"}},
        {std::get<numeric::MatrixView>(corners),std::get<numeric::MatrixView>(no_rays)})).as_handle();
    auto query=request(source,SetRelation::inner,inner.metadata.representation);
    query.size_budget=4;
    const auto admitted=execute(provider(query,inner,SetRelation::inner,SetRelation::inner),query);
    REQUIRE(std::holds_alternative<EnclosedApproximation>(admitted));
    CHECK(std::get<EnclosedApproximation>(admitted).basis==StructuralBasis::h_v_containment);

    const auto bad_corners=numeric::snapshot(Matrix{4,2,{1,1,1,-1,-1,-1,2,2}});
    REQUIRE(std::holds_alternative<numeric::MatrixView>(bad_corners));
    const auto outside=take(sets::make_v({{"outside"},2,{"x","y"}},
        {std::get<numeric::MatrixView>(bad_corners),std::get<numeric::MatrixView>(no_rays)})).as_handle();
    CHECK(std::holds_alternative<Unsupported>(execute(
        provider(query,outside,SetRelation::inner,SetRelation::inner),query)));
}

TEST_CASE("V recession rays must satisfy every proposed outer H row") {
    const auto vertices=numeric::snapshot(Matrix{1,2,{0,0}});
    const auto positive_ray=numeric::snapshot(Matrix{1,2,{1,0}});
    const auto negative_ray=numeric::snapshot(Matrix{1,2,{-1,0}});
    const auto row=numeric::snapshot(Matrix{1,2,{1,0}});
    const auto bound=numeric::snapshot_vector(Vector{1});
    const auto no_rows=numeric::snapshot(Matrix{0,2,{}});
    const auto no_values=numeric::snapshot_vector(Vector{});
    REQUIRE(std::holds_alternative<numeric::MatrixView>(vertices));
    REQUIRE(std::holds_alternative<numeric::MatrixView>(positive_ray));
    REQUIRE(std::holds_alternative<numeric::MatrixView>(negative_ray));
    REQUIRE(std::holds_alternative<numeric::MatrixView>(row));
    REQUIRE(std::holds_alternative<numeric::VectorView>(bound));
    REQUIRE(std::holds_alternative<numeric::MatrixView>(no_rows));
    REQUIRE(std::holds_alternative<numeric::VectorView>(no_values));
    const auto output=take(sets::make_h({{"outer"},2,{"x","y"}},
        {std::get<numeric::MatrixView>(row),std::get<numeric::VectorView>(bound),
         std::get<numeric::MatrixView>(no_rows),std::get<numeric::VectorView>(no_values)})).as_handle();
    const auto source_bad=take(sets::make_v({{"positive"},2,{"x","y"}},
        {std::get<numeric::MatrixView>(vertices),std::get<numeric::MatrixView>(positive_ray)})).as_handle();
    auto query=request(source_bad,SetRelation::outer,output.metadata.representation);
    CHECK(std::holds_alternative<Unsupported>(execute(
        provider(query,output,SetRelation::outer,SetRelation::outer),query)));
    const auto source_good=take(sets::make_v({{"negative"},2,{"x","y"}},
        {std::get<numeric::MatrixView>(vertices),std::get<numeric::MatrixView>(negative_ray)})).as_handle();
    query=request(source_good,SetRelation::outer,output.metadata.representation);
    const auto admitted=execute(provider(query,output,SetRelation::outer,SetRelation::outer),query);
    REQUIRE(std::holds_alternative<EnclosedApproximation>(admitted));
    CHECK(std::get<EnclosedApproximation>(admitted).basis==StructuralBasis::v_h_containment);
}

TEST_CASE("exact H point check survives cancellation beyond floating point range") {
    const double huge=std::numeric_limits<double>::max();
    auto point=numeric::snapshot_vector(Vector{huge,huge});
    auto rows=numeric::snapshot(Matrix{1,2,{huge,-huge}});
    auto bounds=numeric::snapshot_vector(Vector{0.0});
    auto no_rows=numeric::snapshot(Matrix{0,2,{}});
    auto no_values=numeric::snapshot_vector(Vector{});
    REQUIRE(std::holds_alternative<numeric::VectorView>(point));
    REQUIRE(std::holds_alternative<numeric::MatrixView>(rows));
    REQUIRE(std::holds_alternative<numeric::VectorView>(bounds));
    REQUIRE(std::holds_alternative<numeric::MatrixView>(no_rows));
    REQUIRE(std::holds_alternative<numeric::VectorView>(no_values));
    auto input=take(sets::make_singleton({{"reference"},2,{"x","y"}},
        std::get<numeric::VectorView>(point))).as_handle();
    auto output=take(sets::make_h({{"outer"},2,{"x","y"}},
        {std::get<numeric::MatrixView>(rows),std::get<numeric::VectorView>(bounds),
         std::get<numeric::MatrixView>(no_rows),std::get<numeric::VectorView>(no_values)})).as_handle();
    auto query=request(input,SetRelation::outer,output.metadata.representation);
    auto outcome=execute(provider(query,output,SetRelation::outer,SetRelation::outer),query);
    REQUIRE(std::holds_alternative<EnclosedApproximation>(outcome));
    CHECK(std::get<EnclosedApproximation>(outcome).basis==StructuralBasis::h_point_containment);
}

TEST_CASE("an enclosure cannot change the native coordinate system") {
    auto input=set("singleton","reference","x");
    auto output=set("universal","outer","y");
    auto query=request(input,SetRelation::outer,output.metadata.representation);
    auto methods=provider(query,output,SetRelation::outer,SetRelation::outer);
    auto outcome=execute(methods,query);
    REQUIRE(std::holds_alternative<Unsupported>(outcome));
    CHECK(std::get<Unsupported>(outcome).diagnostics[0].field=="approximation.inclusion");
}

TEST_CASE("an unproved enclosure is rejected after provider execution") {
    auto input=set("singleton","reference");
    auto output=set("singleton","different");
    auto query=request(input,SetRelation::inner,output.metadata.representation);
    auto methods=provider(query,output,SetRelation::inner,SetRelation::inner,
        SymbolicArgument{"provider assertion","no independent verifier"});
    auto outcome=execute(methods,query);
    REQUIRE(std::holds_alternative<Unsupported>(outcome));
    CHECK(std::get<Unsupported>(outcome).diagnostics[0].field=="approximation.inclusion");
}

TEST_CASE("elementary enclosure does not authorize a provider error bound") {
    auto input=set("singleton","reference");
    auto output=set("universal","outer");
    auto query=request(input,SetRelation::outer,output.metadata.representation);
    auto methods=provider(query,output,SetRelation::outer,SetRelation::outer,
        SymbolicArgument{"provider bound assertion","unverified"},
        GeometryErrorBound{{"hausdorff"},0.1,"state units"});
    auto outcome=execute(methods,query);
    REQUIRE(std::holds_alternative<Unsupported>(outcome));
    CHECK(std::get<Unsupported>(outcome).diagnostics[0].field=="approximation.error_bound");
}

TEST_CASE("native output cannot exceed the requested size budget") {
    auto input=set("singleton","reference");
    auto output=two_points("candidate");
    auto query=request(input,SetRelation::heuristic,output.metadata.representation);
    query.size_budget=1;
    auto methods=provider(query,output,SetRelation::heuristic,SetRelation::heuristic);
    auto outcome=execute(methods,query);
    REQUIRE(std::holds_alternative<Unsupported>(outcome));
    CHECK(std::get<Unsupported>(outcome).diagnostics[0].field=="approximation.budget");
    query.size_budget=2;
    CHECK(std::holds_alternative<HeuristicApproximation>(execute(methods,query)));
}

TEST_CASE("declared and returned approximation relations cannot downgrade") {
    auto input=set("singleton","reference");
    auto output=set("universal","outer");
    auto query=request(input,SetRelation::inner,output.metadata.representation);
    auto wrong_offer=provider(query,output,SetRelation::outer,SetRelation::outer);
    auto admission=execute(wrong_offer,query);
    REQUIRE(std::holds_alternative<registry::Rejection>(admission));
    CHECK(std::get<registry::Rejection>(admission).diagnostics[0].field=="output.relation");
    auto wrong_result=provider(query,output,SetRelation::inner,SetRelation::outer);
    auto outcome=execute(wrong_result,query);
    REQUIRE(std::holds_alternative<Unsupported>(outcome));
    CHECK(std::get<Unsupported>(outcome).diagnostics[0].field=="approximation.relation");
}

TEST_CASE("equivalent conversion and heuristic approximation stay separate") {
    auto input=set("singleton","reference");
    auto output=set("singleton","candidate");
    auto equivalent=request(input,SetRelation::equivalent,output.metadata.representation);
    auto creations=std::make_shared<std::size_t>(0);
    auto methods=provider(equivalent,output,SetRelation::outer,SetRelation::outer,
        Unestablished{},std::nullopt,creations);
    auto rejected=execute(methods,equivalent);
    REQUIRE(std::holds_alternative<registry::Rejection>(rejected));
    CHECK(std::get<registry::Rejection>(rejected).diagnostics[0].field=="approximation.direction");
    CHECK(*creations==0);
    auto heuristic=request(input,SetRelation::heuristic,output.metadata.representation);
    methods=provider(heuristic,output,SetRelation::heuristic,SetRelation::heuristic);
    auto outcome=execute(methods,heuristic);
    REQUIRE(std::holds_alternative<HeuristicApproximation>(outcome));
    const auto& admitted=std::get<HeuristicApproximation>(outcome);
    CHECK(admitted.result.output.id==SetId{"candidate"});
    CHECK(admitted.result.relation==SetRelation::heuristic);
    CHECK(admitted.result.evidence.reference.identity==heuristic.identity);
    CHECK(admitted.result.evidence.reference.inputs==std::vector<SetId>{input.id});
}

TEST_CASE("future zonotope and ellipsoid representations get no inferred exact route") {
    const SetHandle ellipsoid{{2,{"test.future.ellipsoid"},SetProperty::yes,
        SetProperty::no,SetProperty::yes},std::make_shared<const OpaqueFuturePayload>(),{"ellipsoid"}};
    const SetHandle zonotope{{2,{"test.future.zonotope"},SetProperty::yes,
        SetProperty::yes,SetProperty::yes},std::make_shared<const OpaqueFuturePayload>(),{"zonotope"}};
    auto equivalent=request(ellipsoid,SetRelation::equivalent,zonotope.metadata.representation);
    auto creations=std::make_shared<std::size_t>(0);
    const auto methods=provider(equivalent,zonotope,SetRelation::outer,SetRelation::outer,
        Unestablished{},std::nullopt,creations);
    const auto outcome=execute(methods,equivalent);
    REQUIRE(std::holds_alternative<registry::Rejection>(outcome));
    CHECK(std::get<registry::Rejection>(outcome).diagnostics.front().field=="approximation.direction");
    CHECK(*creations==0);
}

TEST_CASE("set extrema have directed bounds but no optimizer-family claim") {
    CHECK(objective_bound_side(SetRelation::inner,ObjectiveSense::minimize)==BoundSide::upper);
    CHECK(objective_bound_side(SetRelation::outer,ObjectiveSense::minimize)==BoundSide::lower);
    CHECK(objective_bound_side(SetRelation::inner,ObjectiveSense::maximize)==BoundSide::lower);
    CHECK(objective_bound_side(SetRelation::outer,ObjectiveSense::maximize)==BoundSide::upper);
    CHECK(objective_bound_side(SetRelation::equivalent,ObjectiveSense::maximize)==BoundSide::both);
    CHECK(objective_bound_side(SetRelation::heuristic,ObjectiveSense::minimize)==BoundSide::none);
}

TEST_CASE("registered approximation times only its selected provider call") {
    Problem source{{"approximation-observability"},std::make_shared<const SystemModel>(SystemModel{{
        {0,0,0},TimeDomain::discrete,LinearStage{{0,0,{}},{0,0,{}},{0,0,{}},{}}},{}}),{0},
        KnownInitial{{}},ContinuousDomain{{}},{UniversalSet{0}},{},{},
        InformationPattern::nominal_open_loop,LinearTerminal{{},0}};
    auto resolved=problem::resolve(source,{problem::UncertaintyStructure::stage_product_uncoupled});
    REQUIRE(std::holds_alternative<problem::ResolvedProblem>(resolved));
    const auto resolved_value=std::get<problem::ResolvedProblem>(std::move(resolved));
    const auto resolved_problem=resolved_value.identity();
    auto input=set("singleton","approx-reference");
    auto output=set("universal","approx-outer");
    auto query=request(input,SetRelation::outer,output.metadata.representation);
    query.identity.request={"timed-approximation"};
    query.identity.problem=resolved_problem;
    const auto methods=provider(query,output,SetRelation::outer,SetRelation::outer,
        SymbolicArgument{"fixture inclusion proof","same-coordinate outer superset"},std::nullopt,{},
        {"fixture assumes exact stored singleton coordinates"});
    auto timer=approximation_timer(resolved_value,query);
    ExecutionContext context;context.run_id="approximation-test-run";context.timing=timer;
    auto root=std::get<execution::observability::TimingScope>(timer->start({0},context));
    auto outcome=run_registered(methods,{{"fixture.approximation"},std::nullopt},query,context);
    REQUIRE(std::holds_alternative<EnclosedApproximation>(outcome));
    root.close(Termination::completed);
    const auto report=timer->snapshot();
    REQUIRE(std::holds_alternative<execution::observability::TimingReport>(report));
    const auto& timing=std::get<execution::observability::TimingReport>(report);
    REQUIRE(timing.spans.size()==2);
    REQUIRE(std::holds_alternative<artifacts::Available<std::uint64_t>>(timing.spans[1].inclusive_wall_ticks));
    CHECK(std::get<artifacts::Available<std::uint64_t>>(timing.spans[1].inclusive_wall_ticks).value==10);
    const auto& descriptor=timing.observations.description().spans[1].descriptor;
    CHECK(descriptor.task=="timed-approximation");
    CHECK(descriptor.operation=="geometry.approximation.execute");
    CHECK(descriptor.module.id==ModuleId{"fixture.approximation"});
    REQUIRE(descriptor.input_representation);
    CHECK(*descriptor.input_representation==input.metadata.representation);
    REQUIRE(descriptor.output_representation);
    CHECK(*descriptor.output_representation==query.output);
    CHECK(descriptor.relation==SetRelation::outer);
    REQUIRE(descriptor.relation_evidence);
    CHECK(descriptor.relation_evidence->reference.identity==query.identity);
    CHECK(descriptor.relation_evidence->reference.inputs==std::vector<SetId>{input.id});
    CHECK(descriptor.relation_evidence->scope==GeometryClaimScope::set_relation);
    CHECK(std::holds_alternative<SymbolicArgument>(descriptor.relation_evidence->support));
    CHECK(descriptor.relation_evidence->assumptions==
        std::vector<std::string>{"fixture assumes exact stored singleton coordinates"});
    REQUIRE(std::holds_alternative<artifacts::ReturnedSpan>(timing.observations.description().spans[1].status));
    CHECK(std::get<artifacts::ReturnedSpan>(timing.observations.description().spans[1].status).termination==Termination::completed);

    auto mismatched=query;mismatched.identity.request={"mismatched-approximation"};
    const auto mismatched_methods=provider(mismatched,output,SetRelation::outer,SetRelation::inner,
        SymbolicArgument{"invalid relation proof","provider returns inner for outer request"});
    auto rejected_timer=approximation_timer(resolved_value,mismatched);
    ExecutionContext rejected_context;rejected_context.run_id="approximation-test-run";rejected_context.timing=rejected_timer;
    auto rejected_root=std::get<execution::observability::TimingScope>(rejected_timer->start({0},rejected_context));
    const auto rejected=run_registered(mismatched_methods,{{"fixture.approximation"},std::nullopt},
        mismatched,rejected_context);
    REQUIRE(std::holds_alternative<Unsupported>(rejected));
    rejected_root.close(Termination::completed);
    const auto rejected_report=rejected_timer->snapshot();
    REQUIRE(std::holds_alternative<execution::observability::TimingReport>(rejected_report));
    const auto& rejected_timing=std::get<execution::observability::TimingReport>(rejected_report);
    REQUIRE(rejected_timing.observations.description().spans.size()==2);
    const auto& rejected_span=rejected_timing.observations.description().spans[1];
    REQUIRE(std::holds_alternative<artifacts::ReturnedSpan>(rejected_span.status));
    CHECK(std::holds_alternative<artifacts::ReturnedObservation>(rejected_span.execution));
    CHECK(std::get<artifacts::ReturnedSpan>(rejected_span.status).termination==Termination::operation_rejected);
    REQUIRE(rejected_span.descriptor.relation_evidence);
    CHECK(rejected_span.descriptor.relation_evidence->reference.identity==mismatched.identity);
    CHECK(rejected_span.descriptor.relation_evidence->reference.inputs==std::vector<SetId>{input.id});
    CHECK(std::holds_alternative<SymbolicArgument>(rejected_span.descriptor.relation_evidence->support));
    CHECK(std::get<SymbolicArgument>(rejected_span.descriptor.relation_evidence->support).reference==
        "invalid relation proof");
    REQUIRE(rejected_span.descriptor.applied_relation);
    CHECK(*rejected_span.descriptor.applied_relation==SetRelation::inner);
}

TEST_CASE("rejected approximation records a no-call observation without creating a workspace") {
    Problem source{{"approximation-rejection-observability"},std::make_shared<const SystemModel>(SystemModel{{
        {0,0,0},TimeDomain::discrete,LinearStage{{0,0,{}},{0,0,{}},{0,0,{}},{}}},{}}),{0},
        KnownInitial{{}},ContinuousDomain{{}},{UniversalSet{0}},{},{},
        InformationPattern::nominal_open_loop,LinearTerminal{{},0}};
    auto resolved=problem::resolve(source,{problem::UncertaintyStructure::stage_product_uncoupled});
    REQUIRE(std::holds_alternative<problem::ResolvedProblem>(resolved));
    auto input=set("singleton","reject-reference");
    auto output=set("universal","reject-outer");
    auto query=request(input,SetRelation::outer,output.metadata.representation);
    query.identity.request={"rejected-approximation"};
    auto creations=std::make_shared<std::size_t>(0);
    const auto methods=provider(query,output,SetRelation::inner,SetRelation::outer,
        Unestablished{},std::nullopt,creations);
    auto timer=approximation_timer(std::get<problem::ResolvedProblem>(std::move(resolved)),query);
    ExecutionContext context;context.run_id="approximation-test-run";context.timing=timer;
    auto root=std::get<execution::observability::TimingScope>(timer->start({0},context));
    const auto outcome=run_registered(methods,{{"fixture.approximation"},std::nullopt},query,context);
    REQUIRE(std::holds_alternative<registry::Rejection>(outcome));
    CHECK(*creations==0);
    root.close(Termination::completed);
    const auto report=timer->snapshot();
    REQUIRE(std::holds_alternative<execution::observability::TimingReport>(report));
    const auto& timing=std::get<execution::observability::TimingReport>(report);
    REQUIRE(timing.observations.description().spans.size()==2);
    const auto& span=timing.observations.description().spans[1];
    CHECK(span.descriptor.module.id==ModuleId{"fixture.approximation"});
    CHECK(span.descriptor.module.version=="1");
    CHECK(std::holds_alternative<artifacts::NotCalledObservation>(span.execution));
    CHECK(std::get<artifacts::NotCalledObservation>(span.execution).reason==
        artifacts::NotCalledReason::capability_rejected);
    CHECK(std::holds_alternative<artifacts::RejectedSpan>(span.status));
    CHECK(std::get<artifacts::RejectedSpan>(span.status).reason.find("output.relation")!=std::string::npos);
}
