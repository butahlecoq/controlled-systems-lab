#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <csl/geometry/affine_sum.hpp>
#include <csl/adapters/lp/highs.hpp>
#include <csl/adapters/polyhedral/qhull.hpp>
#include <csl/optimization/phase_one.hpp>
#include <csl/sets/data.hpp>
#include <algorithm>
#include <cmath>
#include <limits>
#include <iostream>
#include <numeric>
#include <type_traits>

using namespace csl;
using namespace csl::registry;
static_assert(!std::is_constructible_v<AffineImage,FiniteDomain,Matrix,Vector>);
static_assert(!std::is_constructible_v<AffineImage,MixedDomain,Matrix,Vector>);
namespace {
template<class T,class... R> T take(std::variant<T,R...> value) {
    if (!std::holds_alternative<T>(value)) std::visit([](const auto& failure) {
        if constexpr (requires { failure.field; failure.explanation; })
            std::cerr << failure.field << ": " << failure.explanation << '\n';
        else if constexpr (requires { failure.diagnostics.begin()->field; })
            for (const auto& item : failure.diagnostics) std::cerr << item.field << ": " << item.explanation << '\n';
    }, value);
    REQUIRE(std::holds_alternative<T>(value));
    return std::get<T>(std::move(value));
}
template<class Port> PreparedProvider<Port> provider(Registration<Port> entry,Requirements requirements={}) {
    if constexpr (std::is_same_v<Port,LPPort>) requirements.output.representation={"csl.program-result.v1"};
    const Method method{entry.identity.id,entry.identity.version};
    Registry<Port> registry;
    REQUIRE_FALSE(registry.add(std::move(entry)).has_value());
    return take(prepare_provider(select_provider(registry,method,std::move(requirements))));
}
class KeepAllHullWorkspace final : public geometry::HullReducerWorkspace {
public:
    geometry::HullReductionResult reduce(const geometry::PointCloud& cloud, LPWorkspace&,
            const ExecutionContext&) override {
        std::vector<std::size_t> retained(cloud.points.size());
        std::iota(retained.begin(),retained.end(),std::size_t{0});
        return geometry::HullReduction{geometry::ReductionStatus::complete,std::move(retained),{},0,{}};
    }
};
class NearEndpointDroppingHullWorkspace final : public geometry::HullReducerWorkspace {
public:
    geometry::HullReductionResult reduce(const geometry::PointCloud& cloud, LPWorkspace&,
            const ExecutionContext&) override {
        REQUIRE(cloud.points.size() == 2);
        return geometry::HullReduction{geometry::ReductionStatus::complete,{0},
            {{1,{{0,1.0}},{{"near-endpoint"},{"test-program"}},
                {1e-3,0.0,1e-6,{"test.near-endpoint"}}}},0,{}};
    }
};
Registration<HullReducerPort> make_near_endpoint_hull_registration() {
    return {{{"test.hull.near-endpoint"},"1"},
        [](const geometry::PointCloud&,const Requirements&) -> Capability { return Offer{}; },
        [](const geometry::PointCloud&) { return std::make_unique<NearEndpointDroppingHullWorkspace>(); }};
}
class UnestablishedConversionWorkspace final : public RepresentationConverterWorkspace {
    ConversionRequest request_;
public:
    explicit UnestablishedConversionWorkspace(ConversionRequest request) : request_(std::move(request)) {}
    SetTransformOutcome convert(const ConversionRequest&,const ExecutionContext&) override {
        const auto output=take(sets::make_v({{"unestablished-conversion-output"},1,{}},
            {take(numeric::snapshot(Matrix{2,1,{0,1}})),
             take(numeric::snapshot(Matrix{0,1,{}}))})).as_handle();
        return OperationResult{output,SetRelation::equivalent,
            {{request_.identity,{request_.input.id}},GeometryClaimScope::set_relation,
             Unestablished{}, {"test conversion without numerical verification"},{}}};
    }
};
class HighResidualConversionWorkspace final : public RepresentationConverterWorkspace {
    ConversionRequest request_;
    double upper_vertex_;
    double reported_residual_;
public:
    HighResidualConversionWorkspace(ConversionRequest request,double upper_vertex,double reported_residual)
        : request_(std::move(request)),upper_vertex_(upper_vertex),reported_residual_(reported_residual) {}
    SetTransformOutcome convert(const ConversionRequest&,const ExecutionContext&) override {
        const auto output=take(sets::make_v({{"high-residual-conversion-output"},1,{}},
            {take(numeric::snapshot(Matrix{2,1,{0,upper_vertex_}})),
             take(numeric::snapshot(Matrix{0,1,{}}))})).as_handle();
        return OperationResult{output,SetRelation::equivalent,
            {{request_.identity,{request_.input.id}},GeometryClaimScope::set_relation,
             NumericalCheck{0.0,0.0,reported_residual_,{"test.high-residual"}},
             {"test conversion output and reported residual"},{}}};
    }
};
Registration<ConversionPort> make_unestablished_conversion_registration() {
    return {{{"test.conversion.unestablished"},"1"},
        [](const ConversionRequest&,const Requirements& requirements) -> Capability { return Offer{requirements.output}; },
        [](const ConversionRequest& request) { return std::make_unique<UnestablishedConversionWorkspace>(request); }};
}
Registration<ConversionPort> make_high_residual_conversion_registration() {
    return {{{"test.conversion.high-residual"},"1"},
        [](const ConversionRequest&,const Requirements& requirements) -> Capability { return Offer{requirements.output}; },
        [](const ConversionRequest& request) { return std::make_unique<HighResidualConversionWorkspace>(request,1.0,1e100); }};
}
Registration<ConversionPort> make_inaccurate_conversion_registration() {
    return {{{"test.conversion.inaccurate"},"1"},
        [](const ConversionRequest&,const Requirements& requirements) -> Capability { return Offer{requirements.output}; },
        [](const ConversionRequest& request) { return std::make_unique<HighResidualConversionWorkspace>(request,2.0,0.0); }};
}
Registration<ConversionPort> make_duplicate_row_residual_registration() {
    return {{{"test.conversion.duplicate-row-residual"},"1"},
        [](const ConversionRequest&,const Requirements& requirements) -> Capability { return Offer{requirements.output}; },
        [](const ConversionRequest& request) { return std::make_unique<HighResidualConversionWorkspace>(request,1.0,2.5e-8); }};
}
class SubnormalResidualHullWorkspace final : public geometry::HullReducerWorkspace {
public:
    geometry::HullReductionResult reduce(const geometry::PointCloud& cloud,LPWorkspace&,
            const ExecutionContext&) override {
        REQUIRE(cloud.points.size()==3);
        REQUIRE(cloud.points[0][0]==0.0);
        REQUIRE(cloud.points[1][0]==std::numeric_limits<double>::denorm_min());
        REQUIRE(cloud.points[2][0]==std::numeric_limits<double>::denorm_min());
        return geometry::HullReduction{geometry::ReductionStatus::complete,{1,2},
            {{0,{{1,0.5},{2,0.5}},{{"subnormal-hull"},{"test-program"}},
                {1e-8,1e-8,0.0,{"test.subnormal"}}}},0,{}};
    }
};
Registration<HullReducerPort> make_subnormal_hull_registration() {
    return {{{"test.hull.subnormal"},"1"},
        [](const geometry::PointCloud&,const Requirements&) -> Capability { return Offer{}; },
        [](const geometry::PointCloud&) { return std::make_unique<SubnormalResidualHullWorkspace>(); }};
}
Registration<HullReducerPort> make_keep_all_hull_registration() {
    return {{{"test.hull.keep-all"},"1"},
        [](const geometry::PointCloud&,const Requirements&) -> Capability { return Offer{}; },
        [](const geometry::PointCloud&) { return std::make_unique<KeepAllHullWorkspace>(); }};
}
geometry::AffineSumDependencies dependencies(bool phase=false,bool conversion=true) {
    auto lp=phase ? take(optimization::phase_one::make_registration()) : take(adapters::lp::make_highs_registration());
    std::optional<PreparedProvider<ConversionPort>> converter;
    if(conversion) {
        Requirements requirements;
        requirements.output.representation={"csl.polyhedron.v"};
        requirements.output.relation=SetRelation::equivalent;
        converter=provider(take(adapters::polyhedral::make_qhull_registration(
            take(adapters::lp::make_highs_registration()))),requirements);
    }
    return {provider(geometry::make_lp_hull_reducer_registration()),provider(std::move(lp)),std::move(converter)};
}
SetHandle vertices(std::string id,std::size_t n,Vector values,std::size_t count,
                   std::vector<std::string> labels={}) {
    return take(sets::make_v({{std::move(id)},n,std::move(labels)},
        {take(numeric::snapshot(Matrix{count,n,std::move(values)})),
         take(numeric::snapshot(Matrix{0,n,{}}))})).as_handle();
}
OperationRequest request(GeometryOperation operation,std::string tag="case") {
    return {{{"affine-sum-tests"},{tag},{"ideal-"+tag}},{"csl.geometry.affine-sum"},
        std::move(operation),SetRelation::equivalent,Assurance::numerical};
}
ExecutionContext context() {return {{},{},{},{1e-8,1e-8},"affine-sum-tests"};}
OperationOutcome run(const OperationRequest& req,geometry::AffineSumDependencies deps,
                     geometry::AffineSumOptions options={},ExecutionContext ctx=context()) {
    Registry<GeometryPort> registry;
    REQUIRE_FALSE(registry.add(geometry::make_affine_sum_registration(std::move(deps),std::move(options))).has_value());
    Requirements requirements;
    requirements.output.representation={"csl.polyhedron.v"};
    requirements.output.relation=SetRelation::equivalent;
    auto prepared=prepare_pipeline(select(registry,{{"csl.geometry.affine-sum"},{}},req,requirements));
    if(auto* rejection=std::get_if<Rejection>(&prepared))return Unsupported{rejection->diagnostics};
    auto [workspace]=std::get<PreparedPipeline<GeometryPort>>(prepared).create();
    return workspace->run(ctx);
}
double support(const SetHandle& handle,const Vector& direction) {
    auto data=take(sets::from_handle(handle));
    const auto representation=data.representation();
    const auto* v=std::get_if<sets::VRepresentation>(&representation);
    REQUIRE(v);
    REQUIRE(v->rays.rows()==0);
    double result=-std::numeric_limits<double>::infinity();
    for(std::size_t i=0;i<v->vertices.rows();++i) {
        double value=0;
        for(std::size_t j=0;j<direction.size();++j)value+=direction[j]*v->vertices(i,j);
        result=std::max(result,value);
    }
    return result;
}
}
TEST_CASE("registered affine image preserves the literal shifted reversed interval") {
    const auto req=request(AffineImage{vertices("interval",1,{-1,2},2),{1,1,{-2}},{3}});
    const auto result=take(run(req,dependencies()));
    CHECK(support(result.output,{1})==doctest::Approx(5));
    CHECK(support(result.output,{-1})==doctest::Approx(1));
    CHECK(check_geometry_evidence(result.evidence,req).empty());
}

TEST_CASE("square Minkowski support identities survive actual LP backend substitution") {
    const auto square=vertices("square",2,{0,0,1,0,1,1,0,1},4,{"x","y"});
    const auto segment=vertices("segment",2,{-1,0,2,0},2,{"x","y"});
    const auto req=request(MinkowskiSum{square,segment});
    for(const bool phase : {false,true}) {
        const auto result=take(run(req,dependencies(phase)));
        CHECK(support(result.output,{1,2})==doctest::Approx(5));
        CHECK(support(result.output,{-1,-2})==doctest::Approx(1));
        CHECK(take(sets::from_handle(result.output)).metadata()->coordinate_labels==std::vector<std::string>{"x","y"});
        CHECK(result.relation==SetRelation::equivalent);
        CHECK(std::holds_alternative<NumericalCheck>(result.evidence.support));
    }
}

TEST_CASE("affine and sum operations use the selected hull reducer") {
    auto selected=dependencies();
    selected.hull=provider(make_keep_all_hull_registration());
    const auto interval=vertices("interval",1,{0,1},2);
    const auto req=request(MinkowskiSum{interval,interval},"selected-hull");
    const auto result=take(run(req,std::move(selected)));
    CHECK(support(result.output,{1})==doctest::Approx(2));
    CHECK(support(result.output,{-1})==doctest::Approx(0));
    const auto data=take(sets::from_handle(result.output));
    const auto rep=data.representation();
    REQUIRE(std::holds_alternative<sets::VRepresentation>(rep));
    CHECK(std::get<sets::VRepresentation>(rep).vertices.rows()==4);
    CHECK(std::any_of(result.evidence.assumptions.begin(),result.evidence.assumptions.end(),
        [](const std::string& value){return value.find("test.hull.keep-all@1")!=std::string::npos;}));
}

TEST_CASE("rectangular and singular affine maps retain their actual ambient spaces") {
    const auto interval=vertices("control",1,{-1,2},2);
    auto rectangular=request(AffineImage{interval,{2,1,{2,-1}},{1,3}});
    geometry::AffineSumOptions options;
    options.affine_output_labels={"state-a","state-b"};
    auto result=take(run(rectangular,dependencies(),options));
    CHECK(result.output.metadata.dimension==2);
    CHECK(support(result.output,{1,2})==doctest::Approx(7));
    CHECK(support(result.output,{1,0})==doctest::Approx(5));
    const auto square=vertices("square",2,{0,0,1,0,1,1,0,1},4);
    auto singular=request(AffineImage{square,{2,2,{1,1,0,0}},{-1,4}});
    result=take(run(singular,dependencies()));
    CHECK(support(result.output,{1,3})==doctest::Approx(13));
    CHECK(support(result.output,{-1,-3})==doctest::Approx(-11));
    auto zero=request(AffineImage{square,{1,2,{0,0}},{7}});
    result=take(run(zero,dependencies()));
    CHECK(support(result.output,{1})==doctest::Approx(7));
    const auto rep=take(sets::from_handle(result.output)).representation();
    REQUIRE(std::holds_alternative<sets::VRepresentation>(rep));
    CHECK(std::get<sets::VRepresentation>(rep).vertices.rows()==4);
}

TEST_CASE("selected H conversion preserves explicit equalities and infeasible empty sets") {
    auto h=take(sets::make_h({{"h-segment"},2,{}},
        {take(numeric::snapshot(Matrix{2,2,{1,0,-1,0}})),take(numeric::snapshot_vector(Vector{2,1})),
         take(numeric::snapshot(Matrix{1,2,{0,1}})),take(numeric::snapshot_vector(Vector{3}))})).as_handle();
    const auto req=request(AffineImage{h,{1,2,{2,-1}},{4}});
    const auto result=take(run(req,dependencies()));
    CHECK(support(result.output,{1})==doctest::Approx(5));
    CHECK(support(result.output,{-1})==doctest::Approx(1));
    CHECK(std::holds_alternative<Unsupported>(run(req,dependencies(false,false))));
    h=take(sets::make_h({{"contradiction"},1,{}},
        {take(numeric::snapshot(Matrix{2,1,{1,-1}})),take(numeric::snapshot_vector(Vector{0,-1})),
         take(numeric::snapshot(Matrix{0,1,{}})),take(numeric::snapshot_vector(Vector{}))})).as_handle();
    const auto empty=take(run(request(AffineImage{h,{1,1,{1}},{0}}),dependencies()));
    CHECK(std::isinf(support(empty.output,{1})));
    CHECK(support(empty.output,{1})<0);
}

TEST_CASE("public geometry operation rejects H-to-V vertices without numerical evidence") {
    auto h=take(sets::make_h({{"h-interval-unestablished"},1,{}},
        {take(numeric::snapshot(Matrix{2,1,{-1,1}})),take(numeric::snapshot_vector(Vector{0,1})),
         take(numeric::snapshot(Matrix{0,1,{}})),take(numeric::snapshot_vector(Vector{}))})).as_handle();
    auto selected=dependencies(false,false);
    Requirements conversion_requirements;
    conversion_requirements.output.representation={"csl.polyhedron.v"};
    conversion_requirements.output.relation=SetRelation::equivalent;
    selected.conversion=provider(make_unestablished_conversion_registration(),conversion_requirements);
    const auto result=run(request(AffineImage{h,{1,1,{1}},{0}},"unestablished-conversion"),std::move(selected));
    CHECK(std::holds_alternative<Unsupported>(result));
}

TEST_CASE("public geometry operation rejects valid H-to-V vertices with excessive reported residual") {
    auto h=take(sets::make_h({{"h-interval-high-residual"},1,{}},
        {take(numeric::snapshot(Matrix{2,1,{-1,1}})),take(numeric::snapshot_vector(Vector{0,1})),
         take(numeric::snapshot(Matrix{0,1,{}})),take(numeric::snapshot_vector(Vector{}))})).as_handle();
    auto selected=dependencies(false,false);
    Requirements conversion_requirements;
    conversion_requirements.output.representation={"csl.polyhedron.v"};
    conversion_requirements.output.relation=SetRelation::equivalent;
    selected.conversion=provider(make_high_residual_conversion_registration(),conversion_requirements);
    const auto result=run(request(AffineImage{h,{1,1,{1}},{0}},"high-residual-conversion"),std::move(selected));
    CHECK(std::holds_alternative<Unsupported>(result));
}

TEST_CASE("public geometry operation rejects an H-to-V vertex outside H rows despite zero reported residual") {
    auto h=take(sets::make_h({{"h-interval-inaccurate"},1,{}},
        {take(numeric::snapshot(Matrix{2,1,{-1,1}})),take(numeric::snapshot_vector(Vector{0,1})),
         take(numeric::snapshot(Matrix{0,1,{}})),take(numeric::snapshot_vector(Vector{}))})).as_handle();
    auto selected=dependencies(false,false);
    Requirements conversion_requirements;
    conversion_requirements.output.representation={"csl.polyhedron.v"};
    conversion_requirements.output.relation=SetRelation::equivalent;
    selected.conversion=provider(make_inaccurate_conversion_registration(),conversion_requirements);
    const auto result=run(request(AffineImage{h,{1,1,{1}},{0}},"inaccurate-conversion"),std::move(selected));
    CHECK(std::holds_alternative<Unsupported>(result));
}

TEST_CASE("public geometry operation applies reported conversion residual threshold per H row") {
    auto h=take(sets::make_h({{"h-interval-duplicate-rows"},1,{}},
        {take(numeric::snapshot(Matrix{4,1,{-1,1,-1,1}})),
         take(numeric::snapshot_vector(Vector{0,1,0,1})),
         take(numeric::snapshot(Matrix{0,1,{}})),take(numeric::snapshot_vector(Vector{}))})).as_handle();
    auto selected=dependencies(false,false);
    Requirements conversion_requirements;
    conversion_requirements.output.representation={"csl.polyhedron.v"};
    conversion_requirements.output.relation=SetRelation::equivalent;
    selected.conversion=provider(make_duplicate_row_residual_registration(),conversion_requirements);
    const auto result=run(request(AffineImage{h,{1,1,{1}},{0}},"duplicate-row-conversion-residual"),
        std::move(selected));
    CHECK(std::holds_alternative<Unsupported>(result));
}

TEST_CASE("public geometry operation preserves near-extreme support under loose reducer tolerance") {
    const auto interval=vertices("near-endpoint-interval",1,{0,1e-6},2);
    auto selected=dependencies();
    selected.hull=provider(make_near_endpoint_hull_registration());
    auto ctx=context();
    ctx.numerical={1e-3,0.0};
    const auto result=run(request(AffineImage{interval,{1,1,{1}},{0}},"loose-hull-tolerance"),
        std::move(selected),{},ctx);
    REQUIRE(std::holds_alternative<OperationResult>(result));
    const auto& completed=std::get<OperationResult>(result);
    CHECK(completed.relation==SetRelation::equivalent);
    CHECK(support(completed.output,{1})==doctest::Approx(1e-6));
    const auto rep=take(sets::from_handle(completed.output)).representation();
    REQUIRE(std::holds_alternative<sets::VRepresentation>(rep));
    CHECK(std::get<sets::VRepresentation>(rep).vertices.rows()==2);
}

TEST_CASE("public geometry operation retains a zero endpoint despite subnormal product underflow") {
    const double tiny=std::numeric_limits<double>::denorm_min();
    const auto cloud=vertices("subnormal-candidates",1,{0,tiny,tiny},3);
    auto selected=dependencies();
    selected.hull=provider(make_subnormal_hull_registration());
    const auto result=run(request(AffineImage{cloud,{1,1,{1}},{0}},"subnormal-hull-residual"),
        std::move(selected));
    REQUIRE(std::holds_alternative<OperationResult>(result));
    const auto& completed=std::get<OperationResult>(result);
    CHECK(completed.relation==SetRelation::equivalent);
    CHECK(support(completed.output,{-1})==doctest::Approx(0.0));
    const auto rep=take(sets::from_handle(completed.output)).representation();
    REQUIRE(std::holds_alternative<sets::VRepresentation>(rep));
    CHECK(std::get<sets::VRepresentation>(rep).vertices.rows()==3);
}

TEST_CASE("empty singleton and R0 definitions survive image and sum") {
    const auto empty=take(sets::make_empty({{"empty"},1,{}})).as_handle();
    const auto point=take(sets::make_singleton({{"point"},1,{}},take(numeric::snapshot_vector(Vector{3})))).as_handle();
    auto result=take(run(request(MinkowskiSum{empty,point}),dependencies()));
    CHECK(support(result.output,{1})==-std::numeric_limits<double>::infinity());
    result=take(run(request(MinkowskiSum{point,point}),dependencies()));
    CHECK(support(result.output,{1})==doctest::Approx(6));
    const auto r0=take(sets::make_universal({{"r0"},0,{}})).as_handle();
    result=take(run(request(AffineImage{r0,{2,0,{}},{2,5}}),dependencies()));
    CHECK(support(result.output,{1,1})==doctest::Approx(7));
    result=take(run(request(AffineImage{point,{0,1,{}},{}}),dependencies()));
    CHECK(result.output.metadata.dimension==0);
    CHECK(support(result.output,{})==0);
    result=take(run(request(MinkowskiSum{r0,r0}),dependencies()));
    CHECK(result.output.metadata.dimension==0);
    CHECK(support(result.output,{})==0);
}

TEST_CASE("admission rejects wrong dimensions labels assurance foreign payloads and rays") {
    const auto input=vertices("interval",1,{0,1},2,{"x"});
    auto req=request(AffineImage{input,{1,2,{1,0}},{0}});
    CHECK(std::holds_alternative<Unsupported>(run(req,dependencies())));
    req=request(MinkowskiSum{input,vertices("other",1,{0,1},2,{"u"})});
    CHECK(std::holds_alternative<Unsupported>(run(req,dependencies())));
    req=request(AffineImage{input,{1,1,{1}},{0}});
    req.assurance=Assurance::validated;
    CHECK(std::holds_alternative<Unsupported>(run(req,dependencies())));
    auto foreign=input;
    foreign.payload=std::make_shared<SetPayload>();
    req=request(AffineImage{foreign,{1,1,{1}},{0}});
    CHECK(std::holds_alternative<Unsupported>(run(req,dependencies())));
    const auto ray=take(sets::make_v({{"ray"},1,{}},
        {take(numeric::snapshot(Matrix{1,1,{0}})),take(numeric::snapshot(Matrix{1,1,{1}}))})).as_handle();
    CHECK(std::holds_alternative<Unsupported>(run(request(AffineImage{ray,{1,1,{1}},{0}}),dependencies())));
    const auto universal=take(sets::make_universal({{"r1"},1,{}})).as_handle();
    CHECK(std::holds_alternative<Unsupported>(run(request(MinkowskiSum{universal,input}),dependencies())));
}

TEST_CASE("candidate limits and pre-request stops never publish successful geometry") {
    const auto input=vertices("interval",1,{0,1},2);
    const auto req=request(MinkowskiSum{input,input});
    geometry::AffineSumOptions options;
    options.max_candidates=3;
    CHECK(std::holds_alternative<Unsupported>(run(req,dependencies(),options)));
    std::stop_source stop;
    stop.request_stop();
    auto ctx=context();ctx.cancellation=stop.get_token();
    auto stopped=run(req,dependencies(),{},ctx);
    REQUIRE(std::holds_alternative<OperationStopped>(stopped));
    CHECK(std::get<OperationStopped>(stopped).reason==StopReason::cancelled);
    ctx=context();ctx.deadline=std::chrono::steady_clock::now()-std::chrono::seconds(1);
    stopped=run(req,dependencies(),{},ctx);
    REQUIRE(std::holds_alternative<OperationStopped>(stopped));
    CHECK(std::get<OperationStopped>(stopped).reason==StopReason::resource_limit);
}
