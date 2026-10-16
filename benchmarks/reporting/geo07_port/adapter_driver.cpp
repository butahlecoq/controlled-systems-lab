#include <csl/geometry/generator_adapter.hpp>
#include <csl/registry/provider.hpp>
#include <csl/sets/generator_sets.hpp>
#include <nlohmann/json.hpp>

#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <iostream>
#include <stdexcept>
#include <string>
#include <variant>

namespace {
using namespace csl;
using namespace csl::sets;
using namespace csl::geometry::generators;
using nlohmann::json;
using Clock=std::chrono::steady_clock;
constexpr const char* source_commit="41b4b58f2ef982e75554519862afdd803e30f717";
constexpr const char* schema="csl.geo07-port-trial/1";
constexpr std::array<const char*,3> fixtures{
    "affine_box","constrained_disjoint_sum","finite_v"};
constexpr const char* timed_scope="fresh public generator handles and prepared GeometryPort/ConversionPort registration, admission, workspace execution, literal physical H/V and factor checks, scoped rejection controls, per-call nlohmann JSON result construction and assignment; excludes process startup, JSONL serialization, Python saved-row verification, persistence, rendering";

void require(bool condition,const char* reason) {
    if (!condition) throw std::runtime_error(reason);
}

template<class T,class... Alternatives> T take(std::variant<T,Alternatives...> result,
        const char* reason) {
    require(std::holds_alternative<T>(result),reason);
    return std::get<T>(std::move(result));
}

template<class Port> registry::PreparedProvider<Port> provider(
        registry::Registration<Port> registration,RepresentationId representation) {
    registry::Registry<Port> entries;
    const registry::Method method{registration.identity.id,registration.identity.version};
    require(!entries.add(std::move(registration)).has_value(),"registration failed");
    registry::Requirements requirements;
    requirements.output.representation=representation;
    requirements.output.relation=SetRelation::equivalent;
    return take(registry::prepare_provider(registry::select_provider(entries,method,requirements)),
        "provider preparation failed");
}

template<class Port> void expect_unsupported(registry::PreparedProvider<Port>& selected,
        const typename Port::Request& request,const char* field) {
    const auto admission=selected.prepare(request);
    const auto* rejected=std::get_if<registry::Rejection>(&admission);
    require(rejected && rejected->diagnostics.size()==1 &&
        rejected->diagnostics[0].code==DiagnosticCode::unsupported &&
        rejected->diagnostics[0].field==field,"wrong scoped unsupported diagnostic");
}

OperationResult run(registry::PreparedProvider<registry::GeometryPort>& selected,
        const OperationRequest& request) {
    auto prepared=take(selected.prepare(request),"geometry admission failed");
    auto [workspace]=prepared.create();
    return take(workspace->run({{},{},{},{1e-8,1e-8},"geo07-port-report"}),
        "geometry execution failed");
}

OperationResult run(registry::PreparedProvider<registry::ConversionPort>& selected,
        const ConversionRequest& request) {
    auto prepared=take(selected.prepare(request),"conversion admission failed");
    auto [workspace]=prepared.create();
    return take(workspace->run({{},{},{},{1e-8,1e-8},"geo07-port-report"}),
        "conversion execution failed");
}

template<class Request> void check_evidence(const OperationResult& result,
        const Request& request) {
    require(result.relation==SetRelation::equivalent &&
        std::holds_alternative<SymbolicArgument>(result.evidence.support) &&
        !result.evidence.error_bound.has_value() &&
        check_geometry_evidence(result.evidence,request).empty(),
        "numerical equivalent evidence scope changed");
}

struct LiteralH { Matrix inequalities; Vector upper; Matrix equalities; Vector values; };
const GeneratorInput box_source{{"port-box"},{1,2},{2,2,{2,0,0,3}},
    {{"horizontal"},{"vertical"}},{0,2,{}},{},{}};
const Matrix box_map{1,2,{1,1}};
const Vector box_offset{4};
const LiteralH box_h{{2,1,{1,-1}},{12,-2},{0,1,{}},{}};
const std::array<std::pair<Vector,double>,4> box_witnesses{
    std::pair{Vector{-1,-1},2.0},std::pair{Vector{0,0},7.0},
    std::pair{Vector{1,1},12.0},std::pair{Vector{-1,1},8.0}};
const GeneratorInput sum_left{{"port-sum-left"},{1},{1,2,{1,0}},
    {{"u"},{"v"}},{1,2,{1,-1}},{0},{}};
const GeneratorInput sum_right{{"port-sum-right"},{3},{1,2,{0,2}},
    {{"p"},{"q"}},{1,2,{1,1}},{0},{}};
const LiteralH sum_h{{2,1,{1,-1}},{7,-1},{0,1,{}},{}};
const std::array<std::pair<Vector,double>,3> sum_witnesses{
    std::pair{Vector{-1,-1,1,-1},1.0},std::pair{Vector{0,0,0,0},4.0},
    std::pair{Vector{1,1,-1,1},7.0}};
const GeneratorInput v_source{{"port-v-source"},{7},{1,2,{2,3}},
    {{"a"},{"b"}},{0,2,{}},{},{"x"}};
const GeneratorInput v_constrained{{"port-constrained-control"},{0},{1,1,{1}},
    {{"r"}},{1,1,{1}},{0},{}};
const LiteralH v_h{{2,1,{1,-1}},{12,-2},{0,1,{}},{}};

json matrix_json(const Matrix& value) {
    return {{"rows",value.rows},{"cols",value.cols},{"values",value.values}};
}
json generator_json(const GeneratorInput& value) {
    json ids=json::array();
    for (const auto& id:value.factor_ids) ids.push_back(id.value);
    return {{"id",value.id.value},{"center",value.center},
        {"generators",matrix_json(value.generators)},{"factor_ids",ids},
        {"equalities",matrix_json(value.equalities)},
        {"equality_values",value.equality_values},
        {"coordinate_labels",value.coordinate_labels},
        {"factor_interval",json::array({-1.0,1.0})}};
}
json h_json(const LiteralH& value) {
    return {{"inequalities",matrix_json(value.inequalities)},{"upper",value.upper},
        {"equalities",matrix_json(value.equalities)},{"values",value.values}};
}
json request_json(const char* request_id) {
    return {{"problem_id","geo07-port"},{"request_id",request_id},
        {"assurance","numerical"},{"prepared_scalar","binary64"},
        {"prepared_output_relation","equivalent"}};
}
json input_catalogue() {
    json box_factors=json::array(),box_points=json::array();
    for (const auto& [factor,point]:box_witnesses) {
        box_factors.push_back(factor);
        box_points.push_back(Vector{point});
    }
    json sum_factors=json::array(),sum_points=json::array();
    for (const auto& [factor,point]:sum_witnesses) {
        sum_factors.push_back(factor);
        sum_points.push_back(Vector{point});
    }
    return {
        {"affine_box",{{"operation","affine_image"},
            {"registration","csl.geometry.generators.operations"},
            {"public_request",request_json("affine-box")},
            {"source",generator_json(box_source)},{"affine_map",matrix_json(box_map)},
            {"offset",box_offset},{"output_id","port-box-image"},
            {"output_representation","csl.zonotope"},{"physical_h",h_json(box_h)},
            {"feasible_factor_witnesses",box_factors},{"inside_points",box_points},
            {"outside_points",json::array({Vector{1},Vector{13}})},
            {"rejection_controls",{{"validated_assurance",true}}}}},
        {"constrained_disjoint_sum",{{"operation","minkowski_sum"},
            {"registration","csl.geometry.generators.operations"},
            {"public_request",request_json("constrained-sum")},
            {"left",generator_json(sum_left)},{"right",generator_json(sum_right)},
            {"output_id","port-constrained-sum"},
            {"output_representation","csl.constrained-zonotope"},
            {"physical_h",h_json(sum_h)},
            {"feasible_factor_witnesses",sum_factors},{"inside_points",sum_points},
            {"outside_points",json::array({Vector{0},Vector{8}})},
            {"rejection_controls",{{"shared_ids","left used twice"},
                                    {"intersection",true}}}}},
        {"finite_v",{{"operation","conversion"},
            {"registration","csl.geometry.generators.v-conversion"},
            {"public_request",request_json("finite-v")},
            {"source",generator_json(v_source)},{"output_id","port-v"},
            {"output_representation","csl.polyhedron.v"},{"vertex_cap",4},
            {"physical_h",h_json(v_h)},
            {"vertices",json::array({Vector{2},Vector{6},Vector{8},Vector{12}})},
            {"outside_points",json::array({Vector{1},Vector{13}})},
            {"rejection_controls",{{"cap",3},
                {"constrained",generator_json(v_constrained)},
                {"validated_assurance",true},{"h_output","csl.polyhedron.h"}}}}}};
}

bool contains(const LiteralH& h,const Vector& point) {
    if (point.size()!=h.inequalities.cols || point.size()!=h.equalities.cols) return false;
    for (std::size_t row=0;row<h.inequalities.rows;++row) {
        double activity=0;
        for (std::size_t col=0;col<point.size();++col)
            activity+=h.inequalities.values[row*point.size()+col]*point[col];
        if (activity>h.upper[row]) return false;
    }
    for (std::size_t row=0;row<h.equalities.rows;++row) {
        double activity=0;
        for (std::size_t col=0;col<point.size();++col)
            activity+=h.equalities.values[row*point.size()+col]*point[col];
        if (activity!=h.values[row]) return false;
    }
    return true;
}

bool feasible(const GeneratorSet& set,const Vector& factors) {
    if (factors.size()!=set.factor_ids().size()) return false;
    if (std::any_of(factors.begin(),factors.end(),[](double x){return x < -1 || x > 1;})) return false;
    for (std::size_t row=0;row<set.equalities().rows;++row) {
        double activity=0;
        for (std::size_t col=0;col<factors.size();++col)
            activity+=set.equalities().values[row*factors.size()+col]*factors[col];
        if (activity!=set.equality_values()[row]) return false;
    }
    return true;
}

double physical(const GeneratorSet& set,const Vector& factors) {
    require(set.center().size()==1 && factors.size()==set.factor_ids().size(),
        "physical witness shape changed");
    double x=set.center()[0];
    for (std::size_t col=0;col<factors.size();++col)
        x+=set.generators().values[col]*factors[col];
    return x;
}

json affine_box() {
    const auto input=take(make_generator_set(box_source),"box input rejected");
    auto selected=provider(make_operation_registration(),{"csl.zonotope"});
    const OperationRequest request{{{"geo07-port"},{"affine-box"},{"port-box-image"}},
        {"csl.geometry.generators.operations"},
        AffineImage{input.as_handle(),box_map,box_offset},
        SetRelation::equivalent,Assurance::numerical};
    const auto result=run(selected,request);
    check_evidence(result,request);
    const auto output=take(from_generator_handle(result.output),"box output rejected");
    require(result.output.id.value=="port-box-image" && output.center()==Vector{7} &&
        output.generators().values==Vector{2,3} &&
        output.factor_ids()==std::vector<FactorId>{{"horizontal"},{"vertical"}} &&
        output.equalities().rows==0,"box output coefficients or factors changed");
    Vector observed_points;
    for (const auto& [factor,expected]:box_witnesses) {
        const double point=physical(output,factor);
        require(feasible(output,factor) && point==expected &&
            contains(box_h,{point}),"box physical H witness changed");
        observed_points.push_back(point);
    }
    require(!contains(box_h,{1}) && !contains(box_h,{13}),"box H outside changed");
    auto validated=request;
    validated.assurance=Assurance::validated;
    expect_unsupported(selected,validated,"generators.assurance");
    return {{"status","passed"},{"center",output.center()},
        {"generators",output.generators().values},
        {"factor_ids",json::array({"horizontal","vertical"})},
        {"physical_witnesses",observed_points},
        {"outside_points",json::array({1.0,13.0})},
        {"relation","equivalent"},{"support","symbolic_argument"},
        {"error_bound",false},{"rejections",{{"validated","generators.assurance"}}}};
}

json constrained_disjoint_sum() {
    const auto left=take(make_generator_set(sum_left),"left sum input rejected");
    const auto right=take(make_generator_set(sum_right),"right sum input rejected");
    auto selected=provider(make_operation_registration(),{"csl.constrained-zonotope"});
    const OperationRequest request{{{"geo07-port"},{"constrained-sum"},{"port-constrained-sum"}},
        {"csl.geometry.generators.operations"},
        MinkowskiSum{left.as_handle(),right.as_handle()},
        SetRelation::equivalent,Assurance::numerical};
    const auto result=run(selected,request);
    check_evidence(result,request);
    const auto output=take(from_generator_handle(result.output),"sum output rejected");
    require(result.output.id.value=="port-constrained-sum" && output.center()==Vector{4} &&
        output.generators().values==Vector{1,0,0,2} &&
        output.factor_ids()==std::vector<FactorId>{{"u"},{"v"},{"p"},{"q"}} &&
        output.equalities().rows==2 && output.equalities().cols==4 &&
        output.equalities().values==Vector{1,-1,0,0,0,0,1,1} &&
        output.equality_values()==Vector{0,0},"constrained sum payload changed");
    Vector observed_points;
    for (const auto& [factor,expected]:sum_witnesses) {
        const double point=physical(output,factor);
        require(feasible(output,factor) && point==expected &&
            contains(sum_h,{point}),"constrained sum physical H witness changed");
        observed_points.push_back(point);
    }
    require(!contains(sum_h,{0}) && !contains(sum_h,{8}),"constrained sum H outside changed");
    auto shared=request;
    shared.operation=MinkowskiSum{left.as_handle(),left.as_handle()};
    expect_unsupported(selected,shared,"generators.minkowski.factor_ids");
    auto intersection=request;
    intersection.operation=Intersection{left.as_handle(),right.as_handle()};
    expect_unsupported(selected,intersection,"generators.operation");
    return {{"status","passed"},{"center",output.center()},
        {"generators",output.generators().values},
        {"factor_ids",json::array({"u","v","p","q"})},
        {"equalities",output.equalities().values},
        {"physical_witnesses",observed_points},
        {"outside_points",json::array({0.0,8.0})},
        {"relation","equivalent"},{"support","symbolic_argument"},
        {"error_bound",false},
        {"rejections",{{"shared_id","generators.minkowski.factor_ids"},
                       {"intersection","generators.operation"}}}};
}

json finite_v() {
    const auto input=take(make_generator_set(v_source),"V input rejected");
    auto selected=provider(make_v_conversion_registration(4),{"csl.polyhedron.v"});
    const ConversionRequest request{{{"geo07-port"},{"finite-v"},{"port-v"}},
        input.as_handle(),{"csl.polyhedron.v"},Assurance::numerical};
    const auto result=run(selected,request);
    check_evidence(result,request);
    const auto output=take(from_handle(result.output),"V output rejected");
    const auto representation=output.representation();
    const auto* v=std::get_if<VRepresentation>(&representation);
    require(v && result.output.id.value=="port-v" && v->rays.rows()==0 &&
        v->vertices.rows()==4 && v->vertices.cols()==1 &&
        output.metadata()->coordinate_labels==std::vector<std::string>{"x"},
        "V output form, count or labels changed");
    const Vector expected{2,6,8,12};
    Vector observed_vertices;
    for (std::size_t row=0;row<expected.size();++row) {
        const double vertex=v->vertices(row,0);
        require(vertex==expected[row] && contains(v_h,{vertex}),
            "V vertex or physical H oracle changed");
        observed_vertices.push_back(vertex);
    }
    require(!contains(v_h,{1}) && !contains(v_h,{13}),"V H outside changed");
    auto capped=provider(make_v_conversion_registration(3),{"csl.polyhedron.v"});
    expect_unsupported(capped,request,"generators.convert.cap");
    const auto constrained=take(make_generator_set(v_constrained),"constrained control rejected");
    auto restricted=request;
    restricted.input=constrained.as_handle();
    expect_unsupported(selected,restricted,"generators.convert.equalities");
    restricted=request;
    restricted.assurance=Assurance::validated;
    expect_unsupported(selected,restricted,"generators.assurance");
    restricted=request;
    restricted.output={"csl.polyhedron.h"};
    expect_unsupported(selected,restricted,"generators.convert.output");
    return {{"status","passed"},{"vertices",observed_vertices},{"rays",0},
        {"labels",json::array({"x"})},{"outside_points",json::array({1.0,13.0})},
        {"relation","equivalent"},{"support","symbolic_argument"},
        {"error_bound",false},
        {"rejections",{{"cap","generators.convert.cap"},
                       {"constrained","generators.convert.equalities"},
                       {"validated","generators.assurance"},
                       {"h_output","generators.convert.output"}}}};
}

using Fixture=json (*)();
constexpr std::array<Fixture,3> calls{affine_box,constrained_disjoint_sum,finite_v};

int positive(const char* text,int minimum,int maximum) {
    const auto value=std::stoi(text);
    if (value<minimum || value>maximum || std::to_string(value)!=text)
        throw std::invalid_argument("invalid positive integer");
    return value;
}

bool run(std::size_t index,int round,bool warmup,int batch) {
    int checked=0;
    json observed;
    std::string error;
    const auto start=Clock::now();
    for (int call=0;call<batch;++call) {
        try { observed=calls[index](); ++checked; }
        catch (const std::exception& exception) { error=exception.what(); break; }
    }
    const auto stop=Clock::now();
    const auto elapsed=std::chrono::duration_cast<std::chrono::nanoseconds>(stop-start).count();
    std::cout << json{{"schema",schema},{"fixture",fixtures[index]},{"round",round},
        {"warmup",warmup},{"batch",batch},{"checked_calls",checked},
        {"elapsed_ns",elapsed},{"status",error.empty()?"passed":"oracle_failed"},
        {"error",error.empty()?json(nullptr):json(error)},{"result",observed}}.dump() << '\n';
    std::cout.flush();
    return error.empty();
}
} // namespace

int main(int argc,char** argv) {
    try {
        if (argc==2 && std::string(argv[1])=="--describe") {
            std::cout << json{{"schema","csl.geo07-port-driver/1"},
                {"source_commit",source_commit},{"module","CSL::generator_adapter"},
                {"scalar","binary64"},{"fixtures",fixtures},
                {"timed_scope",timed_scope},{"inputs",input_catalogue()}}.dump() << '\n';
            return 0;
        }
        const bool smoke=argc==2 && std::string(argv[1])=="--smoke";
        const bool measure=argc==5 && std::string(argv[1])=="--measure";
        if (!smoke && !measure)
            throw std::invalid_argument("usage: --describe | --smoke | --measure REPETITIONS WARMUPS BATCH");
        const int repetitions=smoke?1:positive(argv[2],7,100);
        const int warmups=smoke?0:positive(argv[3],1,1);
        const int batch=smoke?1:positive(argv[4],1,100000);
        bool passed=true;
        for (int warmup=0;warmup<warmups;++warmup)
            for (std::size_t i=0;i<fixtures.size();++i) passed=run(i,warmup,true,batch) && passed;
        for (int round=0;round<repetitions;++round) {
            if (round%2==0)
                for (std::size_t i=0;i<fixtures.size();++i) passed=run(i,round,false,batch) && passed;
            else
                for (std::size_t i=fixtures.size();i>0;--i) passed=run(i-1,round,false,batch) && passed;
        }
        return passed?0:2;
    } catch (const std::exception& exception) {
        std::cerr << exception.what() << '\n';
        return 2;
    }
}
