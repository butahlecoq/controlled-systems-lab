#include <csl/geometry/approximation.hpp>
#include <csl/geometry/box_parallelotope.hpp>
#include <csl/sets/data.hpp>

#include <array>
#include <chrono>
#include <cstdlib>
#include <iostream>
#include <stdexcept>
#include <string_view>

using namespace csl;
using namespace csl::geometry::approximation;

namespace {
template<class T> T take(sets::Result<T> value) {
    if(!std::holds_alternative<T>(value))throw std::runtime_error("Invalid authored fixture");
    return std::get<T>(std::move(value));
}
SetHandle v_set(std::string_view id,std::size_t dimension,Vector vertices) {
    const auto count=vertices.size()/dimension;
    const auto points=numeric::snapshot(Matrix{count,dimension,std::move(vertices)});
    const auto rays=numeric::snapshot(Matrix{0,dimension,{}});
    if(!std::holds_alternative<numeric::MatrixView>(points) ||
       !std::holds_alternative<numeric::MatrixView>(rays))throw std::runtime_error("Invalid V fixture");
    return take(sets::make_v({{std::string(id)},dimension,
        dimension==1?std::vector<std::string>{"x"}:std::vector<std::string>{"x","y"}},
        {std::get<numeric::MatrixView>(points),std::get<numeric::MatrixView>(rays)})).as_handle();
}
SetHandle h_set(std::string_view id,Vector rows,Vector bounds) {
    const auto inequalities=numeric::snapshot(Matrix{4,2,std::move(rows)});
    const auto values=numeric::snapshot_vector(bounds);
    const auto equalities=numeric::snapshot(Matrix{0,2,{}});
    const auto equality_values=numeric::snapshot_vector(Vector{});
    if(!std::holds_alternative<numeric::MatrixView>(inequalities) ||
       !std::holds_alternative<numeric::VectorView>(values) ||
       !std::holds_alternative<numeric::MatrixView>(equalities) ||
       !std::holds_alternative<numeric::VectorView>(equality_values))
        throw std::runtime_error("Invalid H fixture");
    return take(sets::make_h({{std::string(id)},2,{"x","y"}},
        {std::get<numeric::MatrixView>(inequalities),std::get<numeric::VectorView>(values),
         std::get<numeric::MatrixView>(equalities),std::get<numeric::VectorView>(equality_values)})).as_handle();
}
struct Case {
    std::string_view name;
    ApproximationRequest request;
    registry::Registry<registry::ApproximationPort> methods;
    registry::Method method;
    StructuralBasis basis;
    Matrix expected_rows;
    Vector expected_bounds;
    Matrix expected_vertices;
};
Case outer_interval() {
    Case item{"interval-box",{{{"app02-interval"},{"outer-box"},{"reference"}},
        v_set("interval",1,{-1.5,2.25}),{"csl.polyhedron.h"},SetRelation::outer,2,
        Assurance::numerical},{},{{"csl.approximation.box"},std::nullopt},
        StructuralBasis::v_h_containment,Matrix{2,1,{1,-1}},{2.25,1.5},{}};
    if(item.methods.add(make_box_registration({"interval-box-output"})))
        throw std::runtime_error("Interval registration failed");
    return item;
}
Case outer_diamond(bool rotated) {
    Case item{rotated?"diamond-rotated-outer":"diamond-axis-outer",
        {{{"app02-diamond"},{rotated?"outer-rotated":"outer-axis"},{"reference"}},
         v_set("diamond",2,{0,2,2,0,0,-2,-2,0}),{"csl.polyhedron.h"},
         SetRelation::outer,4,Assurance::numerical},{},
        {{rotated?"csl.approximation.parallelotope":"csl.approximation.box"},std::nullopt},
        StructuralBasis::v_h_containment,
        rotated?Matrix{4,2,{1,1,-1,-1,1,-1,-1,1}}:
                Matrix{4,2,{1,0,-1,0,0,1,0,-1}},
        {2,2,2,2},{}};
    auto error=rotated?item.methods.add(make_parallelotope_registration(
        {"diamond-rotated-output"},Matrix{2,2,{1,1,1,-1}})):
        item.methods.add(make_box_registration({"diamond-axis-output"}));
    if(error)throw std::runtime_error("Diamond registration failed");
    return item;
}
Case inner_diamond(bool rotated) {
    const auto corners=rotated?Matrix{4,2,{0,1,1,0,0,-1,-1,0}}:
        Matrix{4,2,{1,1,1,-1,-1,-1,-1,1}};
    Case item{rotated?"square-rotated-inner":"diamond-axis-inner",
        {{{"app02-inner"},{rotated?"inner-rotated":"inner-axis"},{"reference"}},
         rotated?h_set("square",{1,0,-1,0,0,1,0,-1},{2,2,2,2}):
                 h_set("diamond-h",{1,1,1,-1,-1,1,-1,-1},{2,2,2,2}),
         {"csl.polyhedron.v"},SetRelation::inner,4,Assurance::numerical},{},
        {{rotated?"csl.approximation.inner-parallelotope":"csl.approximation.inner-box"},
         std::nullopt},StructuralBasis::h_v_containment,{},{},corners};
    auto error=rotated?item.methods.add(make_inscribed_parallelotope_registration(
        {"square-inner-output"},corners)):
        item.methods.add(make_inscribed_box_registration({"diamond-inner-output"},corners));
    if(error)throw std::runtime_error("Inner registration failed");
    return item;
}
bool verify(const Case& item,const RunOutcome& outcome) {
    const auto* enclosed=std::get_if<EnclosedApproximation>(&outcome);
    if(!enclosed || enclosed->basis!=item.basis ||
       enclosed->result.relation!=item.request.direction ||
       enclosed->result.evidence.error_bound ||
       enclosed->result.evidence.assumptions.size()!=3 ||
       enclosed->result.evidence.assumptions[2]!="error_bound=unavailable")return false;
    const auto native=sets::from_handle(enclosed->result.output);
    const auto* data=std::get_if<sets::SetData>(&native);
    if(!data)return false;
    const auto representation=data->representation();
    if(item.request.direction==SetRelation::outer) {
        const auto* h=std::get_if<sets::HRepresentation>(&representation);
        if(!h || h->inequalities.rows()!=item.expected_rows.rows ||
           h->inequalities.cols()!=item.expected_rows.cols ||
           h->upper_bounds.size()!=item.expected_bounds.size() ||
           h->equalities.rows()!=0)return false;
        for(std::size_t row=0;row<item.expected_rows.rows;++row) {
            if(h->upper_bounds[row]!=item.expected_bounds[row])return false;
            for(std::size_t column=0;column<item.expected_rows.cols;++column)
                if(h->inequalities(row,column)!=item.expected_rows.values[
                    row*item.expected_rows.cols+column])return false;
        }
    } else {
        const auto* v=std::get_if<sets::VRepresentation>(&representation);
        if(!v || v->vertices.rows()!=item.expected_vertices.rows ||
           v->vertices.cols()!=item.expected_vertices.cols || v->rays.rows()!=0)return false;
        for(std::size_t row=0;row<item.expected_vertices.rows;++row)
            for(std::size_t column=0;column<item.expected_vertices.cols;++column)
                if(v->vertices(row,column)!=item.expected_vertices.values[
                    row*item.expected_vertices.cols+column])return false;
    }
    return true;
}
bool run(const Case& item,std::string_view phase,int repetition,int calls) {
    std::chrono::nanoseconds elapsed{};
    for(int index=0;index<calls;++index) {
        const auto start=std::chrono::steady_clock::now();
        const auto outcome=run_registered(item.methods,item.method,item.request,ExecutionContext{});
        const auto end=std::chrono::steady_clock::now();
        elapsed+=std::chrono::duration_cast<std::chrono::nanoseconds>(end-start);
        if(!verify(item,outcome))return false;
    }
    std::cout<<phase<<','<<item.name<<','<<repetition<<','<<calls
             <<",enclosed,true,"<<elapsed.count()<<','
             <<(item.request.direction==SetRelation::outer?"v_h":"h_v")<<','
             <<(item.request.direction==SetRelation::outer?item.expected_rows.rows:
                 item.expected_vertices.rows)<<'\n';
    return true;
}
}

int main(int argc,char** argv) {
    if(argc!=2 || (std::string_view(argv[1])!="smoke" &&
                   std::string_view(argv[1])!="measure"))return EXIT_FAILURE;
    const std::array<Case,5> cases{outer_interval(),outer_diamond(false),
        outer_diamond(true),inner_diamond(false),inner_diamond(true)};
    std::cout<<"phase,case,repetition,calls,status,verified,elapsed_ns,basis,output_primitives\n";
    if(std::string_view(argv[1])=="smoke") {
        for(const auto& item:cases)if(!run(item,"smoke",0,1))return EXIT_FAILURE;
    } else {
        for(const auto& item:cases)if(!run(item,"warmup",0,100))return EXIT_FAILURE;
        for(int repetition=0;repetition<7;++repetition)
            for(int offset=0;offset<5;++offset)
                if(!run(cases[(offset+repetition)%5],"trial",repetition,100))
                    return EXIT_FAILURE;
    }
    return EXIT_SUCCESS;
}
