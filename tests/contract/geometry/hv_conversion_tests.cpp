#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <csl/adapters/polyhedral/qhull.hpp>
#include <csl/adapters/lp/highs.hpp>
#include <csl/sets/data.hpp>
#include "../../../src/adapters/polyhedral/exact_h_interval.hpp"
#include <algorithm>
#include <array>
#include <bit>
#include <cmath>
#include <cstdint>
#include <limits>

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
constexpr double conversion_tolerance=1e-8;
ExecutionContext context() { return {{}, {}, {}, {conversion_tolerance,conversion_tolerance}, "geo03-tests"}; }
SetHandle make_h_handle(std::string id,std::size_t n,Matrix a,Vector b,Matrix e={},Vector f={}) {
    if (e.rows==0&&e.cols==0) e={0,n,{}};
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
bool within_tolerance(double actual,double expected,double tolerance=conversion_tolerance) {
    return std::abs(actual-expected)<=tolerance;
}

TEST_CASE("ambient-one H conversion publishes a global stored-dyadic interval bound") {
    const auto h=make_h_handle("third-interval",1,Matrix{2,1,{-1,3}},Vector{0,1});
    const auto req=request(h,"csl.polyhedron.v","third-coverage");
    const auto result=take(convert(h,"csl.polyhedron.v","third-coverage"));
    CHECK(check_geometry_evidence(result.evidence,req).empty());
    REQUIRE(result.evidence.error_bound.has_value());
    CHECK(result.evidence.error_bound->metric.value=="csl.geometry.metric.l-infinity");
    // The exact distance is 1/3 - 6004799503160661/2^54 = 1/(3*2^54).
    // This literal is its least outward-rounded binary64 representation.
    CHECK(std::bit_cast<std::uint64_t>(result.evidence.error_bound->bound)==0x3c75555555555556ULL);
}

TEST_CASE("independent ambient-one checker detects a missing H endpoint despite zero row residual") {
    const auto h=make_h_handle("full-interval",1,Matrix{2,1,{-1,1}},Vector{0,4});
    const auto omitted=make_v_handle("omitted-endpoint",1,Matrix{1,1,{0}});
    const auto original=take(sets::from_handle(h));
    const auto converted=take(sets::from_handle(omitted));
    const auto certificate=adapters::polyhedral::detail::certify_h_interval(
        std::get<sets::HRepresentation>(original.representation()),
        std::get<sets::VRepresentation>(converted.representation()));
    REQUIRE(std::holds_alternative<double>(certificate));
    CHECK(std::get<double>(certificate)==4.0);
}

TEST_CASE("ambient-one checker distinguishes empty equality and unbounded H inputs") {
    const auto empty=make_h_handle("empty-h",1,Matrix{2,1,{1,-1}},Vector{0,-1});
    const auto empty_result=take(convert(empty,"csl.polyhedron.v","empty-coverage"));
    REQUIRE(empty_result.evidence.error_bound.has_value());
    CHECK(empty_result.evidence.error_bound->bound==0.0);
    const auto singleton=make_h_handle("equality-h",1,Matrix{0,1,{}},Vector{},
        Matrix{1,1,{3}},Vector{1});
    const auto singleton_result=take(convert(singleton,"csl.polyhedron.v","equality-coverage"));
    REQUIRE(singleton_result.evidence.error_bound.has_value());
    CHECK(singleton_result.evidence.error_bound->bound>0.0);
    const auto unbounded=make_h_handle("unbounded-h",1,Matrix{1,1,{-1}},Vector{0});
    CHECK(std::holds_alternative<Unsupported>(convert(unbounded,"csl.polyhedron.v","unbounded-coverage")));
}

TEST_CASE("ambient-one checker fails closed when exact H coverage exceeds finite binary64") {
    const auto h=make_h_handle("huge-endpoint",1,
        Matrix{2,1,{-1,std::numeric_limits<double>::denorm_min()}},
        Vector{0,std::numeric_limits<double>::max()});
    const auto zero=make_v_handle("incorrect-singleton",1,Matrix{1,1,{0}});
    const auto original=take(sets::from_handle(h));
    const auto converted=take(sets::from_handle(zero));
    const auto certificate=adapters::polyhedral::detail::certify_h_interval(
        std::get<sets::HRepresentation>(original.representation()),
        std::get<sets::VRepresentation>(converted.representation()));
    CHECK(std::holds_alternative<std::string>(certificate));
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
    CHECK(vertices.metadata()->set.dimension==2);
    const std::array<std::array<double,2>,3> expected_vertices{{{0,0},{1,0},{0,1}}};
    for (const auto& expected : expected_vertices) {
        bool found=false;
        for (std::size_t row=0;row<v.vertices.rows();++row)
            found=found || (within_tolerance(v.vertices(row,0),expected[0])
                && within_tolerance(v.vertices(row,1),expected[1]));
        CHECK(found);
    }
    double support= -std::numeric_limits<double>::infinity();
    for (std::size_t i=0;i<v.vertices.rows();++i) support=std::max(support,v.vertices(i,0)+2*v.vertices(i,1));
    CHECK(support==doctest::Approx(2));
    const auto support_x=std::max({v.vertices(0,0),v.vertices(1,0),v.vertices(2,0)});
    const auto support_y=std::max({v.vertices(0,1),v.vertices(1,1),v.vertices(2,1)});
    const auto support_negative_x=std::max({-v.vertices(0,0),-v.vertices(1,0),-v.vertices(2,0)});
    CHECK(within_tolerance(support_x,1.0));
    CHECK(within_tolerance(support_y,1.0));
    CHECK(within_tolerance(support_negative_x,0.0));
    // Three non-collinear literal vertices establish affine dimension two.
    auto to_h=convert(std::get<OperationResult>(to_v).output,"csl.polyhedron.h","simplex-v-to-h");
    REQUIRE(std::holds_alternative<OperationResult>(to_h));
    auto h=take(sets::from_handle(std::get<OperationResult>(to_h).output));
    const auto hr=h.representation(); REQUIRE(std::holds_alternative<sets::HRepresentation>(hr));
    const auto& triangle_h=std::get<sets::HRepresentation>(hr);
    REQUIRE(triangle_h.inequalities.rows()==3);
    CHECK(triangle_h.equalities.rows()==0);
    // H facets are positive multiples of -x<=0, -y<=0, x+y<=1.
    const std::array<std::array<double,3>,3> expected_facets{{
        {-1,0,0}, {0,-1,0}, {1,1,1}}};
    std::array<bool,3> found_facet{};
    for (std::size_t row=0;row<triangle_h.inequalities.rows();++row) {
        bool matched=false;
        for (std::size_t facet=0;facet<expected_facets.size();++facet) {
            const auto& expected=expected_facets[facet];
            const auto scale=expected[0]!=0.0
                ? triangle_h.inequalities(row,0)/expected[0]
                : triangle_h.inequalities(row,1)/expected[1];
            if (scale>0.0
                && within_tolerance(triangle_h.inequalities(row,0),scale*expected[0])
                && within_tolerance(triangle_h.inequalities(row,1),scale*expected[1])
                && within_tolerance(triangle_h.upper_bounds[row],scale*expected[2])) {
                matched=true;
                found_facet[facet]=true;
            }
        }
        CHECK(matched);
    }
    CHECK(found_facet[0]); CHECK(found_facet[1]); CHECK(found_facet[2]);
    const std::array<double,2> in{0.25,0.25},out{0.75,0.75};
    CHECK(satisfies(triangle_h,in));
    CHECK_FALSE(satisfies(triangle_h,out));
    std::vector<std::array<double,2>> roundtrip_vertices;
    for (std::size_t first=0;first<triangle_h.inequalities.rows();++first) {
        for (std::size_t second=first+1;second<triangle_h.inequalities.rows();++second) {
            const auto a=triangle_h.inequalities(first,0);
            const auto b=triangle_h.inequalities(first,1);
            const auto c=triangle_h.inequalities(second,0);
            const auto d=triangle_h.inequalities(second,1);
            const auto det=a*d-c*b;
            if (det==0.0) continue;
            const std::array<double,2> point{
                (triangle_h.upper_bounds[first]*d-triangle_h.upper_bounds[second]*b)/det,
                (a*triangle_h.upper_bounds[second]-c*triangle_h.upper_bounds[first])/det};
            if (satisfies(triangle_h,point)) roundtrip_vertices.push_back(point);
        }
    }
    REQUIRE(roundtrip_vertices.size()==3);
    for (const auto& expected : expected_vertices) {
        bool found=false;
        for (const auto& point : roundtrip_vertices)
            found=found || (within_tolerance(point[0],expected[0]) && within_tolerance(point[1],expected[1]));
        CHECK(found);
    }
    const auto roundtrip_support=[&](std::array<double,2> direction) {
        auto value=-std::numeric_limits<double>::infinity();
        for (const auto& point : roundtrip_vertices)
            value=std::max(value,direction[0]*point[0]+direction[1]*point[1]);
        return value;
    };
    CHECK(within_tolerance(roundtrip_support({1,0}),1.0));
    CHECK(within_tolerance(roundtrip_support({0,1}),1.0));
    CHECK(within_tolerance(roundtrip_support({-1,0}),0.0));
    CHECK(within_tolerance(roundtrip_support({0,-1}),0.0));
    CHECK(within_tolerance(roundtrip_support({1,1}),1.0));
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
    REQUIRE(h.equalities.rows()==1);
    CHECK(h.equalities(0,0)==0.0);
    CHECK(std::abs(h.equalities(0,1))==1.0);
    CHECK(h.equality_values[0]==0.0);
    // Ambient dimension is two; y=0 and two distinct endpoints establish
    // affine dimension one for this bounded segment.
    const std::array<double,2> left{-1,0},right{2,0},middle{0,0},off{0,1};
    CHECK(satisfies(h,left)); CHECK(satisfies(h,right)); CHECK(satisfies(h,middle)); CHECK_FALSE(satisfies(h,off));
    const std::array<double,2> beyond_left{-1.01,0},beyond_right{2.01,0};
    CHECK_FALSE(satisfies(h,beyond_left)); CHECK_FALSE(satisfies(h,beyond_right));
    auto segment_v=convert(std::get<OperationResult>(segment_h).output,"csl.polyhedron.v","segment-h-to-v-roundtrip");
    REQUIRE(std::holds_alternative<OperationResult>(segment_v));
    auto segment_data=take(sets::from_handle(std::get<OperationResult>(segment_v).output));
    const auto segment_rep=segment_data.representation(); REQUIRE(std::holds_alternative<sets::VRepresentation>(segment_rep));
    const auto& segment_v_rep=std::get<sets::VRepresentation>(segment_rep);
    CHECK(segment_v_rep.rays.rows()==0);
    const auto& segment_points=segment_v_rep.vertices;
    REQUIRE(segment_points.rows()==2);
    double support_x=-std::numeric_limits<double>::infinity();
    double support_negative_x=-std::numeric_limits<double>::infinity();
    double support_y=-std::numeric_limits<double>::infinity();
    double support_negative_y=-std::numeric_limits<double>::infinity();
    bool found_left=false,found_right=false;
    for (std::size_t i=0;i<segment_points.rows();++i) {
        const std::array<double,2> point{segment_points(i,0),segment_points(i,1)};
        CHECK(satisfies(h,point));
        support_x=std::max(support_x,point[0]);
        support_negative_x=std::max(support_negative_x,-point[0]);
        support_y=std::max(support_y,point[1]);
        support_negative_y=std::max(support_negative_y,-point[1]);
        found_left=found_left||within_tolerance(point[0],-1.0);
        found_right=found_right||within_tolerance(point[0],2.0);
    }
    CHECK(found_left); CHECK(found_right);
    CHECK(support_x==doctest::Approx(2));
    CHECK(support_negative_x==doctest::Approx(1));
    CHECK(within_tolerance(support_y,0.0));
    CHECK(within_tolerance(support_negative_y,0.0));
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

TEST_CASE("zero-dimensional contradictions inside numerical tolerance are unsupported") {
    auto r0_inequality=make_h_handle("R0-near-contradiction",0,Matrix{1,0,{}},Vector{-1e-9});
    auto inequality_result=convert(r0_inequality,"csl.polyhedron.v","R0-near-contradiction-to-V");
    CHECK(std::holds_alternative<Unsupported>(inequality_result));

    auto clear_r0_inequality=make_h_handle("R0-clear-contradiction",0,Matrix{1,0,{}},Vector{-1e-6});
    auto clear_inequality_result=convert(clear_r0_inequality,"csl.polyhedron.v","R0-clear-contradiction-to-V");
    REQUIRE(std::holds_alternative<OperationResult>(clear_inequality_result));
    auto clear_empty=take(sets::from_handle(std::get<OperationResult>(clear_inequality_result).output));
    const auto clear_empty_rep=clear_empty.representation(); REQUIRE(std::holds_alternative<sets::VRepresentation>(clear_empty_rep));
    CHECK(std::get<sets::VRepresentation>(clear_empty_rep).vertices.rows()==0);

    auto r0_equality=make_h_handle("R0-near-inconsistent-equality",0,Matrix{0,0,{}},Vector{},Matrix{1,0,{}},Vector{1e-9});
    auto equality_result=convert(r0_equality,"csl.polyhedron.v","R0-near-inconsistent-equality-to-V");
    CHECK(std::holds_alternative<Unsupported>(equality_result));

    auto singleton=make_h_handle("singleton-near-contradiction",1,Matrix{1,1,{0}},Vector{-1e-9},Matrix{1,1,{1}},Vector{0});
    auto singleton_result=convert(singleton,"csl.polyhedron.v","singleton-near-contradiction-to-V");
    CHECK(std::holds_alternative<Unsupported>(singleton_result));

    auto reduced_constant=make_h_handle("reduced-constant-near-contradiction",2,
        Matrix{1,2,{0,1}},Vector{-1e-9},Matrix{1,2,{0,1}},Vector{0});
    auto reduced_constant_result=convert(reduced_constant,"csl.polyhedron.v","reduced-constant-near-contradiction-to-V");
    CHECK(std::holds_alternative<Unsupported>(reduced_constant_result));
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

TEST_CASE("Qhull generated LPs retain the selected owning provider and query identities") {
    std::vector<ProgramIdentity> admitted;
    std::size_t factories=0;
    auto native=take(make_highs_registration());
    auto capability=native.capabilities;
    auto factory=native.factory;
    native.identity={{"test.lp.alternate"},"7"};
    native.capabilities=[&](const LinearProgram& lp,const Requirements& requirements)->Capability {
        admitted.push_back(lp.identity());
        CHECK(requirements.output.representation.value=="csl.program-result.v1");
        CHECK(requirements.output.assurance==Assurance::numerical);
        CHECK_FALSE(requirements.basis_diagnostics);
        return capability(lp,requirements);
    };
    native.factory=[&](const LinearProgram& lp) { ++factories; return factory(lp); };
    auto req=request(square_h(),"csl.polyhedron.v","alternate-provider");
    auto prepared=[&] {
        Registry<ConversionPort> conversions;
        REQUIRE_FALSE(conversions.add(take(make_qhull_registration(std::move(native)))).has_value());
        return take(prepare_pipeline(select(conversions,{{"csl.conversion.qhull"},{}},req,
            conversion_requirements(req.output.value))));
    }(); // Both registration sources are gone before generated LP execution.
    auto [worker]=prepared.create();
    auto outcome=worker->run(context());
    REQUIRE(std::holds_alternative<OperationResult>(outcome));
    const auto& result=std::get<OperationResult>(outcome);
    CHECK(result.evidence.reference.identity==req.identity);
    CHECK(result.evidence.scope==GeometryClaimScope::set_relation);
    REQUIRE(admitted.size()>1);
    CHECK(factories==admitted.size());
    for (std::size_t i=0;i<admitted.size();++i) {
        CHECK(admitted[i].problem.value=="geo03-tests");
        CHECK(admitted[i].program.value=="alternate-provider:qhull-"+std::to_string(i));
    }
}

TEST_CASE("Qhull generated LP provider rejection and late stops publish no geometry") {
    bool reject=false,cancel=false;
    SUBCASE("capability rejection") { reject=true; }
    SUBCASE("cancellation during provider admission") { cancel=true; }
    SUBCASE("deadline during provider admission") {}
    std::stop_source stop;
    auto execution=context();
    execution.cancellation=stop.get_token();
    // Mutate the live execution deadline in admission to exercise the stop
    // between provider admission and native workspace creation deterministically.
    auto native=take(make_highs_registration());
    auto capability=native.capabilities;
    std::size_t factories=0;
    native.capabilities=[&](const LinearProgram& lp,const Requirements& r)->Capability {
        if(reject) return Diagnostics{{DiagnosticCode::unsupported,"test.lp","deliberately rejected"}};
        if(cancel) stop.request_stop();
        else execution.deadline=std::chrono::steady_clock::now();
        return capability(lp,r);
    };
    auto factory=native.factory;
    native.factory=[&](const LinearProgram& lp) { ++factories; return factory(lp); };
    Registry<ConversionPort> conversions;
    REQUIRE_FALSE(conversions.add(take(make_qhull_registration(std::move(native)))).has_value());
    auto req=request(square_h(),"csl.polyhedron.v","provider-stop");
    auto prepared=take(prepare_pipeline(select(conversions,{{"csl.conversion.qhull"},{}},req,
        conversion_requirements(req.output.value))));
    auto [worker]=prepared.create();
    const auto outcome=worker->run(execution);
    CHECK(factories==0);
    if(reject) CHECK(std::holds_alternative<Unsupported>(outcome));
    else {
        REQUIRE(std::holds_alternative<OperationStopped>(outcome));
        CHECK(std::get<OperationStopped>(outcome).reason==(cancel?StopReason::cancelled:StopReason::resource_limit));
    }
}
