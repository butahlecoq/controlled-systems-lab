#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <csl/adapters/polyhedral/qhull.hpp>
#include <csl/adapters/lp/highs.hpp>
#include <csl/sets/data.hpp>
#include <algorithm>
#include <array>
#include <cmath>

using namespace csl;
using namespace csl::registry;
using namespace csl::adapters::lp;
using namespace csl::adapters::polyhedral;

namespace {
template<class T, class... Rest> T take(std::variant<T, Rest...> value) {
    REQUIRE(std::holds_alternative<T>(value));
    return std::get<T>(std::move(value));
}

numeric::MatrixView matrix(std::size_t rows, std::size_t cols, Vector values) {
    return take(numeric::snapshot(Matrix{rows, cols, std::move(values)}));
}
numeric::VectorView vector(Vector values) {
    return take(numeric::snapshot_vector(values));
}
SetHandle square_h() {
    auto h = take(sets::make_h({{"square-h"}, 2, {}},
        {matrix(4, 2, {1,0, -1,0, 0,1, 0,-1}), vector({1,0,1,0}),
         matrix(0,2,{}), vector({})}));
    return h.as_handle();
}
ConversionRequest request(SetHandle input, std::string output, std::string tag) {
    return {{{"geo03-tests"}, {tag}, {"ideal-" + tag}}, std::move(input), {std::move(output)}, Assurance::numerical};
}
Requirements conversion_requirements(std::string output) {
    Requirements r;
    r.output.representation = {std::move(output)};
    r.output.assurance = Assurance::numerical;
    r.output.relation = SetRelation::equivalent;
    return r;
}
ExecutionContext context() { return {{}, {}, {}, {1e-8,1e-8}, "geo03-tests"}; }
SetHandle make_h_handle(std::string id,std::size_t n,Matrix a,Vector b,Matrix e={},Vector f={}) {
    if (e.cols==0) e={0,n,{}};
    return take(sets::make_h({{std::move(id)},n,{}},
        {take(numeric::snapshot(a)),take(numeric::snapshot_vector(b)),
         take(numeric::snapshot(e)),take(numeric::snapshot_vector(f))})).as_handle();
}
SetHandle make_v_handle(std::string id,std::size_t n,Matrix vertices,Matrix rays={}) {
    if (rays.cols==0) rays={0,n,{}};
    return take(sets::make_v({{std::move(id)},n,{}},
        {take(numeric::snapshot(vertices)),take(numeric::snapshot(rays))})).as_handle();
}
SetTransformOutcome convert(SetHandle input,std::string output,std::string tag,QhullOptions options={}) {
    auto conversion=take(make_qhull_registration(take(make_highs_registration()),std::move(options)));
    Registry<ConversionPort> conversions;
    REQUIRE_FALSE(conversions.add(std::move(conversion)).has_value());
    auto req=request(std::move(input),std::move(output),std::move(tag));
    auto prepared=prepare_pipeline(select(conversions,{{"csl.conversion.qhull"},{}},req,conversion_requirements(req.output.value)));
    REQUIRE(std::holds_alternative<PreparedPipeline<ConversionPort>>(prepared));
    auto [worker]=std::get<PreparedPipeline<ConversionPort>>(prepared).create();
    return worker->run(context());
}
bool satisfies(const sets::HRepresentation& h,std::span<const double> x,double tolerance=1e-7) {
    for (std::size_t i=0;i<h.inequalities.rows();++i) {
        double value=0; for (std::size_t j=0;j<x.size();++j) value+=h.inequalities(i,j)*x[j];
        if (value>h.upper_bounds[i]+tolerance) return false;
    }
    for (std::size_t i=0;i<h.equalities.rows();++i) {
        double value=0; for (std::size_t j=0;j<x.size();++j) value+=h.equalities(i,j)*x[j];
        if (std::abs(value-h.equality_values[i])>tolerance) return false;
    }
    return true;
}
class WrongSizeLpWorkspace final : public LPWorkspace {
protected:
    ProgramOutcome do_solve(const LinearProgram& program,const ExecutionContext&) override {
        return ProgramResult{Termination::completed,
            {program.identity(),MathematicalOutcome::optimal,Unestablished{},{}},Vector{0},{} ,"malformed fixture"};
    }
};
}

TEST_CASE("bounded H to V conversion retains the square under independent checks") {
    const auto lp = take(make_highs_registration());
    auto conversion = take(make_qhull_registration(lp));
    Registry<ConversionPort> conversions;
    REQUIRE_FALSE(conversions.add(std::move(conversion)).has_value());
    const auto input = square_h();
    auto req = request(input, "csl.polyhedron.v", "square-h-to-v");
    auto prepared = prepare_pipeline(select(conversions, { {"csl.conversion.qhull"}, {} }, req,
        conversion_requirements("csl.polyhedron.v")));
    REQUIRE(std::holds_alternative<PreparedPipeline<ConversionPort>>(prepared));
    auto [worker] = std::get<PreparedPipeline<ConversionPort>>(prepared).create();
    auto outcome = worker->run(context());
    REQUIRE(std::holds_alternative<OperationResult>(outcome));
    const auto result = std::get<OperationResult>(outcome);
    CHECK(result.relation == SetRelation::equivalent);
    CHECK(result.evidence.reference.identity == req.identity);
    auto converted = take(sets::from_handle(result.output));
    const auto representation = converted.representation();
    REQUIRE(std::holds_alternative<sets::VRepresentation>(representation));
    const auto v = std::get<sets::VRepresentation>(representation);
    CHECK(v.vertices.rows() == 4);
    CHECK(v.rays.rows() == 0);
    // Literal support/membership checks are independent of Qhull output order.
    CHECK(v.vertices(0,0) >= -1e-8);
    CHECK(v.vertices(0,0) <= 1.0 + 1e-8);
    std::vector<std::array<double,2>> corners;
    for (std::size_t i=0;i<v.vertices.rows();++i) corners.push_back({v.vertices(i,0),v.vertices(i,1)});
    CHECK(std::any_of(corners.begin(),corners.end(),[](auto p){return std::abs(p[0])<1e-7&&std::abs(p[1])<1e-7;}));
    CHECK(std::any_of(corners.begin(),corners.end(),[](auto p){return std::abs(p[0]-1)<1e-7&&std::abs(p[1]-1)<1e-7;}));
    CHECK(std::any_of(corners.begin(),corners.end(),[](auto p){return std::abs(p[0])<1e-7&&std::abs(p[1]-1)<1e-7;}));
    CHECK(std::any_of(corners.begin(),corners.end(),[](auto p){return std::abs(p[0]-1)<1e-7&&std::abs(p[1])<1e-7;}));
    const auto maximum_sum=*std::max_element(corners.begin(),corners.end(),[](auto x,auto y){return x[0]+x[1]<y[0]+y[1];});
    CHECK(maximum_sum[0]+maximum_sum[1]==doctest::Approx(2));
    auto roundtrip=convert(result.output,"csl.polyhedron.h","square-v-to-h");
    REQUIRE(std::holds_alternative<OperationResult>(roundtrip));
    auto h_data=take(sets::from_handle(std::get<OperationResult>(roundtrip).output));
    const auto h_rep=h_data.representation(); REQUIRE(std::holds_alternative<sets::HRepresentation>(h_rep));
    const auto& h_out=std::get<sets::HRepresentation>(h_rep);
    const std::array<double,2> inside{0.5,0.5}, edge{1,0}, outside{2,0};
    CHECK(satisfies(h_out,inside)); CHECK(satisfies(h_out,edge)); CHECK_FALSE(satisfies(h_out,outside));
}

TEST_CASE("simplex H/V conversions preserve literal membership, support, and empty cases") {
    const auto simplex=make_h_handle("simplex-h",2,Matrix{3,2,{-1,0,0,-1,1,1}},Vector{0,0,1});
    auto to_v=convert(simplex,"csl.polyhedron.v","simplex-h-to-v");
    REQUIRE(std::holds_alternative<OperationResult>(to_v));
    auto vertices=take(sets::from_handle(std::get<OperationResult>(to_v).output));
    const auto vr=vertices.representation(); REQUIRE(std::holds_alternative<sets::VRepresentation>(vr));
    const auto& v=std::get<sets::VRepresentation>(vr);
    CHECK(v.vertices.rows()==3); CHECK(v.rays.rows()==0);
    double support= -std::numeric_limits<double>::infinity();
    for (std::size_t i=0;i<v.vertices.rows();++i) support=std::max(support,v.vertices(i,0)+2*v.vertices(i,1));
    CHECK(support==doctest::Approx(2));
    auto to_h=convert(std::get<OperationResult>(to_v).output,"csl.polyhedron.h","simplex-v-to-h");
    REQUIRE(std::holds_alternative<OperationResult>(to_h));
    auto h=take(sets::from_handle(std::get<OperationResult>(to_h).output));
    const auto hr=h.representation(); REQUIRE(std::holds_alternative<sets::HRepresentation>(hr));
    const std::array<double,2> in{0.25,0.25},out{0.75,0.75};
    CHECK(satisfies(std::get<sets::HRepresentation>(hr),in));
    CHECK_FALSE(satisfies(std::get<sets::HRepresentation>(hr),out));
    const auto empty=make_h_handle("contradiction",1,Matrix{2,1,{1,-1}},Vector{0,-1});
    auto empty_v=convert(empty,"csl.polyhedron.v","empty-h-to-v");
    REQUIRE(std::holds_alternative<OperationResult>(empty_v));
    auto empty_data=take(sets::from_handle(std::get<OperationResult>(empty_v).output));
    const auto er=empty_data.representation(); REQUIRE(std::holds_alternative<sets::VRepresentation>(er));
    CHECK(std::get<sets::VRepresentation>(er).vertices.rows()==0);
}

TEST_CASE("embedded segments, singleton and explicit equality rows retain their affine hull") {
    auto segment=make_v_handle("segment-v",2,Matrix{3,2,{-1,0,2,0,2,0}});
    auto segment_h=convert(segment,"csl.polyhedron.h","segment-to-h");
    REQUIRE(std::holds_alternative<OperationResult>(segment_h));
    auto data=take(sets::from_handle(std::get<OperationResult>(segment_h).output));
    const auto rep=data.representation(); REQUIRE(std::holds_alternative<sets::HRepresentation>(rep));
    const auto& h=std::get<sets::HRepresentation>(rep);
    const std::array<double,2> left{-1,0},right{2,0},middle{0,0},off{0,1};
    CHECK(satisfies(h,left)); CHECK(satisfies(h,right)); CHECK(satisfies(h,middle)); CHECK_FALSE(satisfies(h,off));
    const std::array<double,2> beyond_left{-1.01,0},beyond_right{2.01,0};
    CHECK_FALSE(satisfies(h,beyond_left)); CHECK_FALSE(satisfies(h,beyond_right));
    auto segment_v=convert(std::get<OperationResult>(segment_h).output,"csl.polyhedron.v","segment-h-to-v-roundtrip");
    REQUIRE(std::holds_alternative<OperationResult>(segment_v));
    auto segment_data=take(sets::from_handle(std::get<OperationResult>(segment_v).output));
    const auto segment_rep=segment_data.representation(); REQUIRE(std::holds_alternative<sets::VRepresentation>(segment_rep));
    const auto& segment_points=std::get<sets::VRepresentation>(segment_rep).vertices;
    REQUIRE(segment_points.rows()==2);
    double support_x=-std::numeric_limits<double>::infinity();
    double support_negative_x=-std::numeric_limits<double>::infinity();
    bool found_left=false,found_right=false;
    for (std::size_t i=0;i<segment_points.rows();++i) {
        const std::array<double,2> point{segment_points(i,0),segment_points(i,1)};
        CHECK(satisfies(h,point));
        support_x=std::max(support_x,point[0]);
        support_negative_x=std::max(support_negative_x,-point[0]);
        found_left=found_left||std::abs(point[0]+1)<1e-7;
        found_right=found_right||std::abs(point[0]-2)<1e-7;
    }
    CHECK(found_left); CHECK(found_right);
    CHECK(support_x==doctest::Approx(2));
    CHECK(support_negative_x==doctest::Approx(1));
    auto equality_h=make_h_handle("segment-explicit-equality",2,Matrix{2,2,{1,0,-1,0}},Vector{2,1},Matrix{1,2,{0,1}},Vector{0});
    auto equality_v=convert(equality_h,"csl.polyhedron.v","segment-equality-to-v");
    REQUIRE(std::holds_alternative<OperationResult>(equality_v));
    auto equality_data=take(sets::from_handle(std::get<OperationResult>(equality_v).output));
    const auto ev=equality_data.representation(); REQUIRE(std::holds_alternative<sets::VRepresentation>(ev));
    CHECK(std::get<sets::VRepresentation>(ev).vertices.rows()==2);
    auto singleton=make_h_handle("singleton-equalities",2,Matrix{0,2,{}},Vector{},Matrix{2,2,{1,0,0,1}},Vector{2,-3});
    auto singleton_v=convert(singleton,"csl.polyhedron.v","singleton-to-v");
    REQUIRE(std::holds_alternative<OperationResult>(singleton_v));
    auto sd=take(sets::from_handle(std::get<OperationResult>(singleton_v).output));
    const auto sv=sd.representation(); REQUIRE(std::holds_alternative<sets::VRepresentation>(sv));
    const auto& points=std::get<sets::VRepresentation>(sv).vertices; REQUIRE(points.rows()==1);
    CHECK(points(0,0)==doctest::Approx(2)); CHECK(points(0,1)==doctest::Approx(-3));
    CHECK(4.0*points(0,0)+points(0,1)==doctest::Approx(5));
    auto singleton_h_roundtrip=convert(std::get<OperationResult>(singleton_v).output,"csl.polyhedron.h","singleton-v-to-h-roundtrip");
    REQUIRE(std::holds_alternative<OperationResult>(singleton_h_roundtrip));
    auto singleton_h_data=take(sets::from_handle(std::get<OperationResult>(singleton_h_roundtrip).output));
    const auto singleton_hr=singleton_h_data.representation(); REQUIRE(std::holds_alternative<sets::HRepresentation>(singleton_hr));
    const auto& singleton_h_rep=std::get<sets::HRepresentation>(singleton_hr);
    const std::array<double,2> literal_point{2,-3},nearby_point{2,-2};
    CHECK(satisfies(singleton_h_rep,literal_point)); CHECK_FALSE(satisfies(singleton_h_rep,nearby_point));
    auto singleton_v_roundtrip=convert(std::get<OperationResult>(singleton_h_roundtrip).output,"csl.polyhedron.v","singleton-h-to-v-roundtrip");
    REQUIRE(std::holds_alternative<OperationResult>(singleton_v_roundtrip));
    auto singleton_v_data=take(sets::from_handle(std::get<OperationResult>(singleton_v_roundtrip).output));
    const auto singleton_vr=singleton_v_data.representation(); REQUIRE(std::holds_alternative<sets::VRepresentation>(singleton_vr));
    const auto& singleton_roundtrip_points=std::get<sets::VRepresentation>(singleton_vr).vertices;
    REQUIRE(singleton_roundtrip_points.rows()==1);
    CHECK(singleton_roundtrip_points(0,0)==doctest::Approx(2));
    CHECK(singleton_roundtrip_points(0,1)==doctest::Approx(-3));
    CHECK(4.0*singleton_roundtrip_points(0,0)+singleton_roundtrip_points(0,1)==doctest::Approx(5));
}

TEST_CASE("zero-dimensional and vertex-free ray descriptions follow the set convention") {
    auto point0=make_h_handle("R0",0,Matrix{0,0,{}},Vector{});
    auto point0_v=convert(point0,"csl.polyhedron.v","R0-to-V");
    REQUIRE(std::holds_alternative<OperationResult>(point0_v));
    auto point=take(sets::from_handle(std::get<OperationResult>(point0_v).output));
    const auto pr=point.representation(); REQUIRE(std::holds_alternative<sets::VRepresentation>(pr));
    const auto& vertices=std::get<sets::VRepresentation>(pr).vertices;
    REQUIRE(vertices.rows()==1); CHECK(vertices.cols()==0);

    auto empty_data=take(sets::make_v({{"empty-with-ray"},2,{}},
        {matrix(0,2,{}),matrix(1,2,{1,0})}));
    auto empty_h=convert(empty_data.as_handle(),"csl.polyhedron.h","empty-ray-to-H");
    REQUIRE(std::holds_alternative<OperationResult>(empty_h));
    auto h=take(sets::from_handle(std::get<OperationResult>(empty_h).output));
    const auto hr=h.representation(); REQUIRE(std::holds_alternative<sets::HRepresentation>(hr));
    CHECK(std::get<sets::HRepresentation>(hr).inequalities.rows()==1);
    const std::array<double,2> any{0,0}; CHECK_FALSE(satisfies(std::get<sets::HRepresentation>(hr),any));
}

TEST_CASE("equality coefficient scale does not erase independent inequality dimensions") {
    auto h=make_h_handle("scaled-equality",2,Matrix{2,2,{1,0,-1,0}},Vector{1,0},
        Matrix{1,2,{0,1e20}},Vector{0});
    auto converted=convert(h,"csl.polyhedron.v","scaled-equality-to-v");
    REQUIRE(std::holds_alternative<OperationResult>(converted));
    auto set=take(sets::from_handle(std::get<OperationResult>(converted).output));
    const auto rep=set.representation(); REQUIRE(std::holds_alternative<sets::VRepresentation>(rep));
    const auto& v=std::get<sets::VRepresentation>(rep);
    REQUIRE(v.vertices.rows()==2); CHECK(v.vertices.cols()==2);
    bool has_zero=false,has_one=false;
    for (std::size_t i=0;i<v.vertices.rows();++i) {
        has_zero=has_zero||std::abs(v.vertices(i,0))<1e-8;
        has_one=has_one||std::abs(v.vertices(i,0)-1)<1e-8;
        CHECK(std::abs(v.vertices(i,1))<1e-8);
    }
    CHECK(has_zero); CHECK(has_one);
}

TEST_CASE("H-to-V refuses an LP witness whose vector shape violates its contract") {
    Registration<LPPort> malformed{{{"test.lp.wrong-size"},"1"},
        [](const LinearProgram&,const Requirements&)->Capability{return Offer{};},
        [](const LinearProgram&){return std::make_unique<WrongSizeLpWorkspace>();}};
    auto conversion=take(make_qhull_registration(std::move(malformed)));
    Registry<ConversionPort> conversions; REQUIRE_FALSE(conversions.add(std::move(conversion)).has_value());
    auto input=square_h(); auto req=request(input,"csl.polyhedron.v","wrong-lp-shape");
    auto prepared=prepare_pipeline(select(conversions,{{"csl.conversion.qhull"},{}},req,
        conversion_requirements("csl.polyhedron.v")));
    REQUIRE(std::holds_alternative<PreparedPipeline<ConversionPort>>(prepared));
    auto [worker]=std::get<PreparedPipeline<ConversionPort>>(prepared).create();
    CHECK(std::holds_alternative<Unsupported>(worker->run(context())));
}

TEST_CASE("unbounded, near-degenerate, observations, and caller capacity are explicit") {
    auto unbounded=make_h_handle("unbounded-halfline",1,Matrix{1,1,{-1}},Vector{0});
    auto rejected=convert(unbounded,"csl.polyhedron.v","unbounded-to-v");
    REQUIRE(std::holds_alternative<Unsupported>(rejected));
    auto thin=make_v_handle("thin-triangle",2,Matrix{3,2,{0,0,1,0,0,1e-16}});
    auto rank=convert(thin,"csl.polyhedron.h","thin-rank");
    REQUIRE(std::holds_alternative<Unsupported>(rank));
    std::optional<ConversionObservation> observation;
    QhullOptions options; options.observe=[&](const ConversionObservation& value){observation=value;};
    auto observed=convert(square_h(),"csl.polyhedron.v","observed-square",options);
    REQUIRE(std::holds_alternative<OperationResult>(observed)); REQUIRE(observation.has_value());
    CHECK(observation->converter.id.value=="csl.conversion.qhull");
    CHECK(observation->lp_backend.id.value=="csl.lp.highs");
    CHECK(observation->input_inequalities==4); CHECK(observation->output_vertices==4);
    REQUIRE(observation->affine_dimension.has_value()); CHECK(*observation->affine_dimension==2);
    CHECK(observation->elapsed_seconds>=0); CHECK(observation->numerical_check.has_value());
    QhullOptions limit; limit.max_ambient_dimension=1;
    auto limited=take(make_qhull_registration(take(make_highs_registration()),limit));
    Registry<ConversionPort> registry; REQUIRE_FALSE(registry.add(std::move(limited)).has_value());
    auto req=request(square_h(),"csl.polyhedron.v","limited-square");
    auto admission=prepare_pipeline(select(registry,{{"csl.conversion.qhull"},{}},req,conversion_requirements("csl.polyhedron.v")));
    REQUIRE(std::holds_alternative<Rejection>(admission));
}

TEST_CASE("nonempty ray descriptions reject bounded V to H conversion") {
    auto input_data = take(sets::make_v({{"ray"}, 2, {}},
        {matrix(1,2,{0,0}), matrix(1,2,{1,0})}));
    const auto input = input_data.as_handle();
    const auto lp = take(make_highs_registration());
    auto conversion = take(make_qhull_registration(lp));
    Registry<ConversionPort> conversions;
    REQUIRE_FALSE(conversions.add(std::move(conversion)).has_value());
    auto req = request(input, "csl.polyhedron.h", "ray-v-to-h");
    auto prepared = prepare_pipeline(select(conversions, {{"csl.conversion.qhull"}, {}}, req,
        conversion_requirements("csl.polyhedron.h")));
    REQUIRE(std::holds_alternative<PreparedPipeline<ConversionPort>>(prepared));
    auto [worker] = std::get<PreparedPipeline<ConversionPort>>(prepared).create();
    auto outcome = worker->run(context());
    REQUIRE(std::holds_alternative<Unsupported>(outcome));
}
