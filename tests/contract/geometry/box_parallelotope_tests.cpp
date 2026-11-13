#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <csl/geometry/approximation.hpp>
#include <csl/geometry/box_parallelotope.hpp>
#include <csl/sets/data.hpp>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <limits>

using namespace csl;
using namespace csl::geometry::approximation;

namespace {
sets::SetData take(sets::Result<sets::SetData> result) {
    REQUIRE(std::holds_alternative<sets::SetData>(result));
    return std::get<sets::SetData>(std::move(result));
}
SetHandle polygon(const char* id, Matrix points) {
    std::vector<std::string> labels;
    for(std::size_t coordinate=0;coordinate<points.cols;++coordinate)
        labels.push_back(coordinate==0?"x":coordinate==1?"y":"x"+std::to_string(coordinate+1));
    const auto vertices=numeric::snapshot(points);
    const auto rays=numeric::snapshot(Matrix{0,points.cols,{}});
    REQUIRE(std::holds_alternative<numeric::MatrixView>(vertices));
    REQUIRE(std::holds_alternative<numeric::MatrixView>(rays));
    return take(sets::make_v({{id},points.cols,std::move(labels)},
        {std::get<numeric::MatrixView>(vertices),std::get<numeric::MatrixView>(rays)})).as_handle();
}
SetHandle h_polygon(const char* id, Matrix inequalities, Vector bounds) {
    const auto rows=numeric::snapshot(inequalities);
    const auto values=numeric::snapshot_vector(bounds);
    const auto no_rows=numeric::snapshot(Matrix{0,2,{}});
    const auto no_values=numeric::snapshot_vector(Vector{});
    REQUIRE(std::holds_alternative<numeric::MatrixView>(rows));
    REQUIRE(std::holds_alternative<numeric::VectorView>(values));
    REQUIRE(std::holds_alternative<numeric::MatrixView>(no_rows));
    REQUIRE(std::holds_alternative<numeric::VectorView>(no_values));
    return take(sets::make_h({{id},2,{"x","y"}},
        {std::get<numeric::MatrixView>(rows),std::get<numeric::VectorView>(values),
         std::get<numeric::MatrixView>(no_rows),std::get<numeric::VectorView>(no_values)})).as_handle();
}
ApproximationRequest outer(SetHandle input) {
    return {{{"box-problem"},{"box-request"},{"box-reference"}},std::move(input),
        {"csl.polyhedron.h"},SetRelation::outer,4,Assurance::numerical};
}
}

TEST_CASE("registered box encloses every vertex of a shifted interval polygon") {
    const auto input=polygon("rectangle",Matrix{4,2,{-1,0,2,0,2,3,-1,3}});
    registry::Registry<registry::ApproximationPort> methods;
    REQUIRE_FALSE(methods.add(make_box_registration({"box-output"})).has_value());
    const auto result=run_registered(methods,{{"csl.approximation.box"},std::nullopt},
        outer(input),ExecutionContext{});
    REQUIRE(std::holds_alternative<EnclosedApproximation>(result));
    const auto& enclosed=std::get<EnclosedApproximation>(result);
    CHECK(enclosed.basis==StructuralBasis::v_h_containment);
    REQUIRE(enclosed.result.evidence.assumptions.size()==3);
    CHECK(enclosed.result.evidence.assumptions[0]=="orientation_rows=1,0;0,1");
    CHECK(enclosed.result.evidence.assumptions[1]==
        "requested_budget=4; input_vertices=4; input_rays=0; output_h_rows=4");
    CHECK(enclosed.result.evidence.assumptions[2]=="error_bound=unavailable");
    const auto native=sets::from_handle(enclosed.result.output);
    REQUIRE(std::holds_alternative<sets::SetData>(native));
    const auto representation=std::get<sets::SetData>(native).representation();
    REQUIRE(std::holds_alternative<sets::HRepresentation>(representation));
    const auto& h=std::get<sets::HRepresentation>(representation);
    CHECK(h.inequalities.rows()==4);
    CHECK(h.inequalities(0,0)==1.0);
    CHECK(h.inequalities(1,0)==-1.0);
    CHECK(h.inequalities(2,1)==1.0);
    CHECK(h.inequalities(3,1)==-1.0);
    CHECK(h.upper_bounds[0]==2.0);
    CHECK(h.upper_bounds[1]==1.0);
    CHECK(h.upper_bounds[2]==3.0);
    CHECK(h.upper_bounds[3]==0.0);
}

TEST_CASE("box producer reports an expired deadline before enclosure publication") {
    const auto input=polygon("deadline-diamond",Matrix{4,2,{0,2,2,0,0,-2,-2,0}});
    registry::Registry<registry::ApproximationPort> methods;
    REQUIRE_FALSE(methods.add(make_box_registration({"deadline-output"})).has_value());
    ExecutionContext context;
    context.deadline=std::chrono::steady_clock::now()-std::chrono::seconds(1);
    const auto result=run_registered(methods,{{"csl.approximation.box"},std::nullopt},
        outer(input),context);
    REQUIRE(std::holds_alternative<OperationStopped>(result));
    CHECK(std::get<OperationStopped>(result).reason==StopReason::deadline_expired);
}

TEST_CASE("registered rotated parallelotope has literal support bounds") {
    const auto input=polygon("diamond",Matrix{4,2,{0,2,2,0,0,-2,-2,0}});
    registry::Registry<registry::ApproximationPort> methods;
    REQUIRE_FALSE(methods.add(make_parallelotope_registration(
        {"rotated-output"},Matrix{2,2,{1,1,1,-1}})).has_value());
    const auto result=run_registered(methods,{{"csl.approximation.parallelotope"},std::nullopt},
        outer(input),ExecutionContext{});
    REQUIRE(std::holds_alternative<EnclosedApproximation>(result));
    const auto& enclosed=std::get<EnclosedApproximation>(result);
    CHECK(enclosed.basis==StructuralBasis::v_h_containment);
    REQUIRE(enclosed.result.evidence.assumptions.size()==3);
    CHECK(enclosed.result.evidence.assumptions[0]=="orientation_rows=1,1;1,-1");
    CHECK(enclosed.result.evidence.assumptions[1]==
        "requested_budget=4; input_vertices=4; input_rays=0; output_h_rows=4");
    CHECK(enclosed.result.evidence.assumptions[2]=="error_bound=unavailable");
    const auto native=sets::from_handle(enclosed.result.output);
    REQUIRE(std::holds_alternative<sets::SetData>(native));
    const auto representation=std::get<sets::SetData>(native).representation();
    REQUIRE(std::holds_alternative<sets::HRepresentation>(representation));
    const auto& h=std::get<sets::HRepresentation>(representation);
    CHECK(h.inequalities.rows()==4);
    CHECK(h.inequalities(0,0)==1.0);
    CHECK(h.inequalities(0,1)==1.0);
    CHECK(h.inequalities(1,0)==-1.0);
    CHECK(h.inequalities(1,1)==-1.0);
    CHECK(h.inequalities(2,0)==1.0);
    CHECK(h.inequalities(2,1)==-1.0);
    CHECK(h.upper_bounds[0]==2.0);
    CHECK(h.upper_bounds[1]==2.0);
    CHECK(h.upper_bounds[2]==2.0);
    CHECK(h.upper_bounds[3]==2.0);
}

TEST_CASE("registered four-dimensional parallelotope emits one support pair per axis") {
    Matrix points{16,4,Vector(64)};
    for(std::size_t mask=0;mask<16;++mask)
        for(std::size_t coordinate=0;coordinate<4;++coordinate)
            points.values[mask*4+coordinate]=(mask&(std::size_t{1}<<coordinate))?1.0:-1.0;
    const auto input=polygon("hypercube",std::move(points));
    const Matrix orientation{4,4,{1,1,0,0, 0,1,1,0, 0,0,1,1, 1,0,0,2}};
    registry::Registry<registry::ApproximationPort> methods;
    REQUIRE_FALSE(methods.add(make_parallelotope_registration({"four-dimensional"},orientation)).has_value());
    ApproximationRequest query{{{"parallelotope-4d"},{"outer"},{"reference"}},input,
        {"csl.polyhedron.h"},SetRelation::outer,8,Assurance::numerical};
    const auto result=run_registered(methods,{{"csl.approximation.parallelotope"},std::nullopt},
        query,ExecutionContext{});
    REQUIRE(std::holds_alternative<EnclosedApproximation>(result));
    const auto& enclosed=std::get<EnclosedApproximation>(result);
    CHECK(enclosed.basis==StructuralBasis::v_h_containment);
    const auto native=sets::from_handle(enclosed.result.output);
    REQUIRE(std::holds_alternative<sets::SetData>(native));
    const auto representation=std::get<sets::SetData>(native).representation();
    REQUIRE(std::holds_alternative<sets::HRepresentation>(representation));
    const auto& h=std::get<sets::HRepresentation>(representation);
    REQUIRE(h.inequalities.rows()==8);
    CHECK(h.inequalities.cols()==4);
    CHECK(h.upper_bounds.size()==8);
    CHECK(enclosed.result.evidence.assumptions[1]==
        "requested_budget=8; input_vertices=16; input_rays=0; output_h_rows=8");
    for(std::size_t row=0;row<h.inequalities.rows();++row)
        for(std::size_t vertex=0;vertex<16;++vertex) {
            double dot=0.0;
            for(std::size_t coordinate=0;coordinate<4;++coordinate)
                dot+=h.inequalities(row,coordinate)*
                    ((vertex&(std::size_t{1}<<coordinate))?1.0:-1.0);
            CHECK(dot<=h.upper_bounds[row]);
        }
}

TEST_CASE("parallelotope rejects an exactly singular orientation despite elimination growth") {
    constexpr std::size_t n=32;
    const int coefficients[31]={-3,-4,-5,-4,-2,1,-4,-1,-2,4,3,-4,3,-5,-4,0,
        1,-2,0,-1,5,-1,4,3,-5,-2,4,5,-3,-3,-3};
    Matrix orientation{n,n,Vector(n*n,0.0)};
    for(std::size_t row=0;row<n-1;++row) {
        for(std::size_t column=0;column<row;++column)
            orientation.values[row*n+column]=-1.0;
        orientation.values[row*n+row]=1.0;
        orientation.values[row*n+n-1]=1.0;
    }
    for(std::size_t column=0;column<n;++column)
        for(std::size_t row=0;row<n-1;++row)
            orientation.values[(n-1)*n+column]+=
                coefficients[row]*orientation.values[row*n+column];
    // This nonzero exact nullray proves singularity independently of elimination.
    for(std::size_t row=0;row<n;++row) {
        std::int64_t dot=static_cast<std::int64_t>(orientation.values[row*n+n-1]);
        for(std::size_t column=0;column<n-1;++column)
            dot-=static_cast<std::int64_t>(orientation.values[row*n+column])*
                (std::int64_t{1}<<column);
        REQUIRE(dot==0);
    }
    const auto input=polygon("singular-growth-origin",Matrix{1,n,Vector(n,0.0)});
    auto query=outer(input);
    query.size_budget=2*n;
    registry::Registry<registry::ApproximationPort> methods;
    REQUIRE_FALSE(methods.add(make_parallelotope_registration(
        {"singular-growth-output"},orientation)).has_value());
    const auto result=run_registered(methods,{{"csl.approximation.parallelotope"},std::nullopt},
        query,ExecutionContext{});
    REQUIRE(std::holds_alternative<registry::Rejection>(result));
    CHECK(std::get<registry::Rejection>(result).diagnostics.front().field==
        "parallelotope.orientation");
}

TEST_CASE("high-dimensional parallelotope preserves support rows across extreme row scales") {
    constexpr std::size_t n=32;
    for(const bool scaled:{false,true}) {
        Matrix orientation{n,n,Vector(n*n,0.0)};
        for(std::size_t row=0;row<n;++row) {
            const double scale=scaled?std::ldexp(1.0,row%2?900:-900):1.0;
            const auto pivot=(row+1)%n;
            orientation.values[row*n+pivot]=2.0*scale;
            orientation.values[row*n+(pivot+1)%n]=0.3*scale;
        }
        const auto input=polygon("scaled-origin",Matrix{1,n,Vector(n,0.0)});
        auto query=outer(input);
        query.size_budget=2*n;
        registry::Registry<registry::ApproximationPort> methods;
        REQUIRE_FALSE(methods.add(make_parallelotope_registration(
            {"scaled-output"},orientation)).has_value());
        const auto result=run_registered(methods,
            {{"csl.approximation.parallelotope"},std::nullopt},query,ExecutionContext{});
        REQUIRE(std::holds_alternative<EnclosedApproximation>(result));
        const auto native=sets::from_handle(std::get<EnclosedApproximation>(result).result.output);
        REQUIRE(std::holds_alternative<sets::SetData>(native));
        const auto representation=std::get<sets::SetData>(native).representation();
        REQUIRE(std::holds_alternative<sets::HRepresentation>(representation));
        const auto& h=std::get<sets::HRepresentation>(representation);
        REQUIRE(h.inequalities.rows()==2*n);
        for(std::size_t row=0;row<n;++row) {
            CHECK(h.upper_bounds[2*row]==0.0);
            CHECK(h.upper_bounds[2*row+1]==0.0);
            for(std::size_t column=0;column<n;++column) {
                CHECK(h.inequalities(2*row,column)==orientation.values[row*n+column]);
                CHECK(h.inequalities(2*row+1,column)==-orientation.values[row*n+column]);
            }
        }
    }
}

TEST_CASE("parallelotope rejects nonfinite and unresolved inverse candidates") {
    for(const double diagonal:{0.0,std::numeric_limits<double>::denorm_min(),
        std::numeric_limits<double>::infinity(),std::numeric_limits<double>::quiet_NaN()}) {
        const auto input=polygon("unresolved-origin",Matrix{1,3,{0,0,0}});
        auto query=outer(input);
        query.size_budget=6;
        registry::Registry<registry::ApproximationPort> methods;
        REQUIRE_FALSE(methods.add(make_parallelotope_registration({"unresolved-output"},
            Matrix{3,3,{diagonal,0,0,0,1,0,0,0,1}})).has_value());
        const auto result=run_registered(methods,
            {{"csl.approximation.parallelotope"},std::nullopt},query,ExecutionContext{});
        REQUIRE(std::holds_alternative<registry::Rejection>(result));
        CHECK(std::get<registry::Rejection>(result).diagnostics.front().field==
            "parallelotope.orientation");
    }
}

TEST_CASE("registered four-dimensional box reports its full identity orientation") {
    Matrix points{16,4,Vector(64)};
    for(std::size_t mask=0;mask<16;++mask)
        for(std::size_t coordinate=0;coordinate<4;++coordinate)
            points.values[mask*4+coordinate]=(mask&(std::size_t{1}<<coordinate))?1.0:-1.0;
    const auto input=polygon("box-evidence-hypercube",std::move(points));
    registry::Registry<registry::ApproximationPort> methods;
    REQUIRE_FALSE(methods.add(make_box_registration({"box-evidence-output"})).has_value());
    ApproximationRequest query{{{"box-evidence"},{"box-evidence-request"},{"box-evidence-reference"}},
        input,{"csl.polyhedron.h"},SetRelation::outer,8,Assurance::numerical};
    const auto result=run_registered(methods,{{"csl.approximation.box"},std::nullopt},
        query,ExecutionContext{});
    REQUIRE(std::holds_alternative<EnclosedApproximation>(result));
    const auto& enclosed=std::get<EnclosedApproximation>(result);
    REQUIRE(enclosed.result.evidence.assumptions.size()==3);
    CHECK(enclosed.result.evidence.assumptions[0]==
        "orientation_rows=1,0,0,0;0,1,0,0;0,0,1,0;0,0,0,1");
    CHECK(enclosed.result.evidence.assumptions[1]==
        "requested_budget=8; input_vertices=16; input_rays=0; output_h_rows=8");
    const auto native=sets::from_handle(enclosed.result.output);
    REQUIRE(std::holds_alternative<sets::SetData>(native));
    const auto representation=std::get<sets::SetData>(native).representation();
    REQUIRE(std::holds_alternative<sets::HRepresentation>(representation));
    const auto& h=std::get<sets::HRepresentation>(representation);
    REQUIRE(h.inequalities.rows()==8);
    REQUIRE(h.inequalities.cols()==4);
    for(std::size_t row=0;row<h.inequalities.rows();++row)
        for(std::size_t vertex=0;vertex<16;++vertex) {
            double dot=0.0;
            for(std::size_t coordinate=0;coordinate<4;++coordinate)
                dot+=h.inequalities(row,coordinate)*
                    ((vertex&(std::size_t{1}<<coordinate))?1.0:-1.0);
            CHECK(dot<=h.upper_bounds[row]);
        }
}

TEST_CASE("four-dimensional parallelotope rejects a rank-deficient orientation") {
    Matrix points{1,4,{0,0,0,0}};
    const auto input=polygon("four-dimensional-point",std::move(points));
    registry::Registry<registry::ApproximationPort> methods;
    REQUIRE_FALSE(methods.add(make_parallelotope_registration({"singular"},
        Matrix{4,4,{1,0,0,0, 0,1,0,0, 0,0,1,0, 0,0,2,0}})).has_value());
    ApproximationRequest query{{{"parallelotope-4d"},{"singular"},{"reference"}},input,
        {"csl.polyhedron.h"},SetRelation::outer,8,Assurance::numerical};
    const auto result=run_registered(methods,{{"csl.approximation.parallelotope"},std::nullopt},
        query,ExecutionContext{});
    REQUIRE(std::holds_alternative<registry::Rejection>(result));
    CHECK(std::get<registry::Rejection>(result).diagnostics.front().field=="parallelotope.orientation");
}

TEST_CASE("inscribed box checks all four declared corners against H input") {
    const auto input=h_polygon("diamond",Matrix{4,2,{1,1,1,-1,-1,1,-1,-1}},
        Vector{2,2,2,2});
    registry::Registry<registry::ApproximationPort> methods;
    REQUIRE_FALSE(methods.add(make_inscribed_box_registration({"inner-box"},
        Matrix{4,2,{1,1,1,-1,-1,-1,-1,1}})).has_value());
    const ApproximationRequest query{{{"inner-problem"},{"inner-request"},{"inner-reference"}},
        input,{"csl.polyhedron.v"},SetRelation::inner,4,Assurance::numerical};
    const auto result=run_registered(methods,{{"csl.approximation.inner-box"},std::nullopt},
        query,ExecutionContext{});
    REQUIRE(std::holds_alternative<EnclosedApproximation>(result));
    const auto& enclosed=std::get<EnclosedApproximation>(result);
    CHECK(enclosed.basis==StructuralBasis::h_v_containment);
    REQUIRE(enclosed.result.evidence.assumptions.size()==3);
    CHECK(enclosed.result.evidence.assumptions[0]==
        "ordered_corners=1,1;1,-1;-1,-1;-1,1");
    CHECK(enclosed.result.evidence.assumptions[1]==
        "requested_budget=4; input_h_rows=4; output_vertices=4; output_rays=0");
    CHECK(enclosed.result.evidence.assumptions[2]=="error_bound=unavailable");
    const auto native=sets::from_handle(enclosed.result.output);
    REQUIRE(std::holds_alternative<sets::SetData>(native));
    const auto representation=std::get<sets::SetData>(native).representation();
    REQUIRE(std::holds_alternative<sets::VRepresentation>(representation));
    CHECK(std::get<sets::VRepresentation>(representation).vertices.rows()==4);

    registry::Registry<registry::ApproximationPort> outside;
    REQUIRE_FALSE(outside.add(make_inscribed_box_registration({"outside"},
        Matrix{4,2,{2,2,2,-2,-2,-2,-2,2}})).has_value());
    const auto rejected=run_registered(outside,{{"csl.approximation.inner-box"},std::nullopt},
        query,ExecutionContext{});
    REQUIRE(std::holds_alternative<Unsupported>(rejected));
    CHECK(std::get<Unsupported>(rejected).diagnostics.front().field=="approximation.inclusion");
}

TEST_CASE("inscribed rotated parallelotope preserves a certified diamond") {
    const auto input=h_polygon("square",Matrix{4,2,{1,0,-1,0,0,1,0,-1}},
        Vector{2,2,2,2});
    registry::Registry<registry::ApproximationPort> methods;
    REQUIRE_FALSE(methods.add(make_inscribed_parallelotope_registration({"inner-diamond"},
        Matrix{4,2,{0,1,1,0,0,-1,-1,0}})).has_value());
    const ApproximationRequest query{{{"inner-problem"},{"inner-request"},{"inner-reference"}},
        input,{"csl.polyhedron.v"},SetRelation::inner,4,Assurance::numerical};
    const auto result=run_registered(methods,
        {{"csl.approximation.inner-parallelotope"},std::nullopt},query,ExecutionContext{});
    REQUIRE(std::holds_alternative<EnclosedApproximation>(result));
    CHECK(std::get<EnclosedApproximation>(result).basis==StructuralBasis::h_v_containment);
}

TEST_CASE("empty, unbounded and invalid-orientation inputs return named capability results") {
    const auto empty_vertices=numeric::snapshot(Matrix{0,2,{}});
    const auto no_rays=numeric::snapshot(Matrix{0,2,{}});
    const auto ray=numeric::snapshot(Matrix{1,2,{1,0}});
    const auto origin=numeric::snapshot(Matrix{1,2,{0,0}});
    REQUIRE(std::holds_alternative<numeric::MatrixView>(empty_vertices));
    REQUIRE(std::holds_alternative<numeric::MatrixView>(no_rays));
    REQUIRE(std::holds_alternative<numeric::MatrixView>(ray));
    REQUIRE(std::holds_alternative<numeric::MatrixView>(origin));
    const auto empty=take(sets::make_v({{"empty"},2,{"x","y"}},
        {std::get<numeric::MatrixView>(empty_vertices),
         std::get<numeric::MatrixView>(no_rays)})).as_handle();
    const auto unbounded=take(sets::make_v({{"unbounded"},2,{"x","y"}},
        {std::get<numeric::MatrixView>(origin),
         std::get<numeric::MatrixView>(ray)})).as_handle();
    registry::Registry<registry::ApproximationPort> box;
    REQUIRE_FALSE(box.add(make_box_registration({"box"})).has_value());
    const auto empty_result=run_registered(box,{{"csl.approximation.box"},std::nullopt},
        outer(empty),ExecutionContext{});
    REQUIRE(std::holds_alternative<registry::Rejection>(empty_result));
    CHECK(std::get<registry::Rejection>(empty_result).diagnostics.front().field=="box.input.empty");
    const auto ray_result=run_registered(box,{{"csl.approximation.box"},std::nullopt},
        outer(unbounded),ExecutionContext{});
    REQUIRE(std::holds_alternative<registry::Rejection>(ray_result));
    CHECK(std::get<registry::Rejection>(ray_result).diagnostics.front().field=="box.input.unbounded");
    registry::Registry<registry::ApproximationPort> rotated;
    REQUIRE_FALSE(rotated.add(make_parallelotope_registration(
        {"rotated"},Matrix{2,2,{1,1,1,-1}})).has_value());
    const auto rotated_empty=run_registered(rotated,
        {{"csl.approximation.parallelotope"},std::nullopt},
        outer(empty),ExecutionContext{});
    REQUIRE(std::holds_alternative<registry::Rejection>(rotated_empty));
    CHECK(std::get<registry::Rejection>(rotated_empty).diagnostics.front().field==
        "parallelotope.input.empty");
    registry::Registry<registry::ApproximationPort> parallelotope;
    REQUIRE_FALSE(parallelotope.add(make_parallelotope_registration(
        {"slab"},Matrix{2,2,{1,0,2,0}})).has_value());
    const auto invalid=run_registered(parallelotope,
        {{"csl.approximation.parallelotope"},std::nullopt},
        outer(polygon("triangle",Matrix{3,2,{0,0,1,0,0,1}})),ExecutionContext{});
    REQUIRE(std::holds_alternative<registry::Rejection>(invalid));
    CHECK(std::get<registry::Rejection>(invalid).diagnostics.front().field=="parallelotope.orientation");
}

TEST_CASE("degenerate point input retains finite box bounds and budget rejects four rows") {
    const auto input=polygon("point",Matrix{1,2,{0.5,-1}});
    registry::Registry<registry::ApproximationPort> box;
    REQUIRE_FALSE(box.add(make_box_registration({"point-box"})).has_value());
    const auto admitted=run_registered(box,{{"csl.approximation.box"},std::nullopt},
        outer(input),ExecutionContext{});
    REQUIRE(std::holds_alternative<EnclosedApproximation>(admitted));
    const auto native=sets::from_handle(std::get<EnclosedApproximation>(admitted).result.output);
    REQUIRE(std::holds_alternative<sets::SetData>(native));
    const auto representation=std::get<sets::SetData>(native).representation();
    REQUIRE(std::holds_alternative<sets::HRepresentation>(representation));
    const auto& h=std::get<sets::HRepresentation>(representation);
    CHECK(h.upper_bounds[0]==0.5);
    CHECK(h.upper_bounds[1]==-0.5);
    CHECK(h.upper_bounds[2]==-1.0);
    CHECK(h.upper_bounds[3]==1.0);
    auto small_budget=outer(input);
    small_budget.size_budget=3;
    const auto rejected=run_registered(box,{{"csl.approximation.box"},std::nullopt},
        small_budget,ExecutionContext{});
    REQUIRE(std::holds_alternative<registry::Rejection>(rejected));
    CHECK(std::get<registry::Rejection>(rejected).diagnostics.front().field=="box.budget");
}

TEST_CASE("rotated support rounds outward from exact stored binary64 products") {
    const auto input=polygon("fractional-point",Matrix{1,2,{0.3,0.3}});
    registry::Registry<registry::ApproximationPort> methods;
    REQUIRE_FALSE(methods.add(make_parallelotope_registration(
        {"fractional-slab"},Matrix{2,2,{0.1,0.1,1,-1}})).has_value());
    const auto result=run_registered(methods,{{"csl.approximation.parallelotope"},std::nullopt},
        outer(input),ExecutionContext{});
    REQUIRE(std::holds_alternative<EnclosedApproximation>(result));
    const auto native=sets::from_handle(std::get<EnclosedApproximation>(result).result.output);
    REQUIRE(std::holds_alternative<sets::SetData>(native));
    const auto representation=std::get<sets::SetData>(native).representation();
    REQUIRE(std::holds_alternative<sets::HRepresentation>(representation));
    const auto& h=std::get<sets::HRepresentation>(representation);
    CHECK(h.upper_bounds[0]>0.06);
    CHECK(h.upper_bounds[1]<0.0);
}

TEST_CASE("one-dimensional interval obtains its literal enclosing box") {
    const auto vertices=numeric::snapshot(Matrix{2,1,{-1.5,2.25}});
    const auto rays=numeric::snapshot(Matrix{0,1,{}});
    REQUIRE(std::holds_alternative<numeric::MatrixView>(vertices));
    REQUIRE(std::holds_alternative<numeric::MatrixView>(rays));
    const auto input=take(sets::make_v({{"interval"},1,{"x"}},
        {std::get<numeric::MatrixView>(vertices),std::get<numeric::MatrixView>(rays)})).as_handle();
    const ApproximationRequest query{{{"interval-problem"},{"interval-request"},{"interval-reference"}},
        input,{"csl.polyhedron.h"},SetRelation::outer,2,Assurance::numerical};
    registry::Registry<registry::ApproximationPort> methods;
    REQUIRE_FALSE(methods.add(make_box_registration({"interval-box"})).has_value());
    const auto result=run_registered(methods,{{"csl.approximation.box"},std::nullopt},
        query,ExecutionContext{});
    REQUIRE(std::holds_alternative<EnclosedApproximation>(result));
    const auto native=sets::from_handle(std::get<EnclosedApproximation>(result).result.output);
    REQUIRE(std::holds_alternative<sets::SetData>(native));
    const auto representation=std::get<sets::SetData>(native).representation();
    REQUIRE(std::holds_alternative<sets::HRepresentation>(representation));
    const auto& h=std::get<sets::HRepresentation>(representation);
    CHECK(h.upper_bounds[0]==2.25);
    CHECK(h.upper_bounds[1]==1.5);
}

TEST_CASE("malformed candidate corners cannot be called an inner parallelotope") {
    const auto input=h_polygon("square",Matrix{4,2,{1,0,-1,0,0,1,0,-1}},
        Vector{2,2,2,2});
    const ApproximationRequest query{{{"inner-problem"},{"inner-request"},{"inner-reference"}},
        input,{"csl.polyhedron.v"},SetRelation::inner,4,Assurance::numerical};
    registry::Registry<registry::ApproximationPort> methods;
    REQUIRE_FALSE(methods.add(make_inscribed_parallelotope_registration({"bad-shape"},
        Matrix{4,2,{0,1,1,0,0,-1,-1,0.5}})).has_value());
    const auto rejected=run_registered(methods,
        {{"csl.approximation.inner-parallelotope"},std::nullopt},query,ExecutionContext{});
    REQUIRE(std::holds_alternative<registry::Rejection>(rejected));
    CHECK(std::get<registry::Rejection>(rejected).diagnostics.front().field=="inner-template.corners");
}
