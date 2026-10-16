#include <csl/geometry/generators.hpp>
#include <nlohmann/json.hpp>

#include <array>
#include <chrono>
#include <cmath>
#include <cstdint>
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
constexpr const char* source_commit="db7906cb33ca40da55e31b9bf6b21cf7ffcc1ee4";
constexpr const char* schema="csl.geo07-generator-trial/1";
constexpr std::array<const char*,3> fixtures{"box_image","shared_cancellation","constrained_sum"};
constexpr const char* timed_scope="fresh public GeneratorSet construction, public affine/dependent operations and independent-sum rejection control, factor lift, literal physical H, factor identity and coefficient checks, per-call nlohmann JSON result construction and assignment; excludes process startup, JSONL serialization, Python saved-row verification, persistence, rendering";

template<class T> T take(std::variant<T,Diagnostics> result) {
    if (!std::holds_alternative<T>(result)) throw std::runtime_error("public generator API rejected fixture");
    return std::get<T>(std::move(result));
}

struct LiteralH { Matrix inequalities; Vector upper; Matrix equalities; Vector values; };

const GeneratorInput box_source{{"report-box"},{1,2},{2,2,{2,0,0,3}},
    {{"horizontal"},{"vertical"}},{0,2,{}},{},{}};
const Matrix box_map{1,2,{1,1}};
const Vector box_offset{4};
const LiteralH box_h{{2,1,{1,-1}},{12,-2},{0,1,{}},{}};
const std::array<std::pair<Vector,Vector>,4> box_witnesses{
    std::pair{Vector{-1,-1},Vector{2}}, {Vector{0,0},Vector{7}},
    {Vector{1,1},Vector{12}}, {Vector{-1,1},Vector{8}}};
const GeneratorInput cancel_left{{"report-left"},{0},{1,1,{1}},{{"history.0"}},
    {0,1,{}},{},{}};
const GeneratorInput cancel_right{{"report-right"},{0},{1,1,{-1}},{{"history.0"}},
    {0,1,{}},{},{}};
const LiteralH cancel_h{{0,1,{}},{},{1,1,{1}},{0}};
const Vector cancel_witnesses{-1,0,1};
const GeneratorInput constrained_left{{"report-constrained-left"},{0,0},
    {2,2,{1,0,0,1}},{{"u"},{"v"}},{1,2,{1,-1}},{0},{}};
const GeneratorInput constrained_right{{"report-constrained-right"},{0,0},
    {2,2,{-1,0,0,1}},{{"u"},{"w"}},{1,2,{1,1}},{0},{}};
const LiteralH constrained_h{{0,2,{}},{},{2,2,{1,0,0,1}},{0,0}};
const std::array<Vector,2> constrained_witnesses{Vector{1,1,-1},Vector{0,0,0}};
const Vector constrained_left_only{1,1,0};
const Vector constrained_right_only{1,0,-1};
const Vector constrained_infeasible_inside{1,0,0};

json matrix_json(const Matrix& value) {
    return {{"rows",value.rows},{"cols",value.cols},{"values",value.values}};
}

json generator_json(const GeneratorInput& value) {
    json ids=json::array();
    for (const auto& id:value.factor_ids) ids.push_back(id.value);
    return {{"id",value.id.value},{"center",value.center},{"generators",matrix_json(value.generators)},
        {"factor_ids",ids},{"equalities",matrix_json(value.equalities)},
        {"equality_values",value.equality_values},{"coordinate_labels",value.coordinate_labels},
        {"factor_interval",json::array({-1.0,1.0})}};
}

json h_json(const LiteralH& value) {
    return {{"inequalities",matrix_json(value.inequalities)},{"upper",value.upper},
        {"equalities",matrix_json(value.equalities)},{"values",value.values}};
}

json input_catalogue() {
    json box_factors=json::array(),box_points=json::array();
    for (const auto& [factor,point]:box_witnesses) {
        box_factors.push_back(factor);
        box_points.push_back(point);
    }
    json cancel_factors=json::array(),cancel_points=json::array();
    for (double factor:cancel_witnesses) {
        cancel_factors.push_back(Vector{factor});
        cancel_points.push_back(Vector{0});
    }
    return {
        {"box_image",{{"operation","affine_image"},{"source",generator_json(box_source)},
            {"affine_map",matrix_json(box_map)},{"offset",box_offset},{"output_id","report-image"},
            {"physical_h",h_json(box_h)},{"feasible_factor_witnesses",box_factors},
            {"inside_points",box_points},{"outside_points",json::array({Vector{1},Vector{13}})},
            {"infeasible_inside_factor",Vector{2,-1}}}},
        {"shared_cancellation",{{"operation","dependent_sum"},{"output_id","report-cancelled"},
            {"left",generator_json(cancel_left)},{"right",generator_json(cancel_right)},
            {"physical_h",h_json(cancel_h)},{"feasible_factor_witnesses",cancel_factors},
            {"inside_points",cancel_points},{"outside_points",json::array({Vector{-1},Vector{1}})},
            {"independent_sum_rejected",true}}},
        {"constrained_sum",{{"operation","dependent_sum"},{"output_id","report-constrained-sum"},
            {"left",generator_json(constrained_left)},{"right",generator_json(constrained_right)},
            {"physical_h",h_json(constrained_h)},
            {"feasible_factor_witnesses",json::array({constrained_witnesses[0],constrained_witnesses[1]})},
            {"inside_points",json::array({Vector{0,0},Vector{0,0}})},
            {"outside_points",json::array({Vector{0,1},Vector{0,-1}})},
            {"left_only_factor",constrained_left_only},{"right_only_factor",constrained_right_only},
            {"infeasible_inside_factor",constrained_infeasible_inside}}}
    };
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

Vector physical(const FactorPolyhedron& lift,const Vector& factors) {
    if (factors.size()!=lift.map.cols) throw std::runtime_error("factor count changed");
    Vector point=lift.offset;
    for (std::size_t row=0;row<lift.map.rows;++row)
        for (std::size_t col=0;col<lift.map.cols;++col)
            point[row]+=lift.map.values[row*lift.map.cols+col]*factors[col];
    return point;
}

bool factor_feasible(const FactorPolyhedron& lift,const Vector& factors) {
    const auto h=std::get<HRepresentation>(lift.factors.representation());
    if (factors.size()!=h.inequalities.cols()) return false;
    for (std::size_t row=0;row<h.inequalities.rows();++row) {
        double activity=0;
        for (std::size_t col=0;col<factors.size();++col)
            activity+=h.inequalities(row,col)*factors[col];
        if (activity>h.upper_bounds[row]) return false;
    }
    for (std::size_t row=0;row<h.equalities.rows();++row) {
        double activity=0;
        for (std::size_t col=0;col<factors.size();++col)
            activity+=h.equalities(row,col)*factors[col];
        if (activity!=h.equality_values[row]) return false;
    }
    return true;
}

void require(bool condition,const char* reason) {
    if (!condition) throw std::runtime_error(reason);
}

json box_image() {
    const auto input=take(make_generator_set(box_source));
    const auto output=take(affine_image(input,box_map,box_offset,{"report-image"}));
    const auto lift=take(factor_polyhedron(output));
    require(output.center()==Vector{7} && output.generators().values==Vector{2,3},"box coefficients");
    require(lift.factor_ids==std::vector<FactorId>{{"horizontal"},{"vertical"}},"box factor identities");
    for (const auto& [factor,expected]:box_witnesses) {
        require(factor_feasible(lift,factor),"box factor witness");
        require(physical(lift,factor)==expected && contains(box_h,expected),"box physical H oracle");
    }
    require(!contains(box_h,{1}) && !contains(box_h,{13}),"box outside H oracle");
    require(!factor_feasible(lift,{2,-1}) && physical(lift,{2,-1})==Vector{8},"box noninjective control");
    return {{"status","passed"},{"center",output.center()},{"generators",output.generators().values},
        {"factor_ids",{"horizontal","vertical"}},{"physical_witnesses",json::array({2,7,12,8})},
        {"outside_points",json::array({1,13})}};
}

json shared_cancellation() {
    const auto left=take(make_generator_set(cancel_left));
    const auto right=take(make_generator_set(cancel_right));
    const auto output=take(dependent_sum(left,right,{"report-cancelled"}));
    const auto lift=take(factor_polyhedron(output));
    require(output.factor_ids()==std::vector<FactorId>{{"history.0"}} &&
        output.generators().values==Vector{0},"shared factor was cloned or dropped");
    require(lift.factor_ids==std::vector<FactorId>{{"history.0"}},"lift identity");
    for (double factor:cancel_witnesses) {
        require(factor_feasible(lift,{factor}),"cancellation factor witness");
        require(physical(lift,{factor})==Vector{0} && contains(cancel_h,{0}),"cancellation H oracle");
    }
    require(!contains(cancel_h,{-1}) && !contains(cancel_h,{1}),"cancellation outside H oracle");
    require(std::holds_alternative<Diagnostics>(minkowski_sum(left,right,{"independent-rejected"})),
        "overlapping independent sum admitted");
    return {{"status","passed"},{"center",output.center()},{"generators",output.generators().values},
        {"factor_ids",{"history.0"}},{"physical_witnesses",json::array({0,0,0})},
        {"outside_points",json::array({-1,1})}};
}

json constrained_sum() {
    const auto left=take(make_generator_set(constrained_left));
    const auto right=take(make_generator_set(constrained_right));
    const auto output=take(dependent_sum(left,right,{"report-constrained-sum"}));
    const auto lift=take(factor_polyhedron(output));
    require(lift.factor_ids==std::vector<FactorId>{{"u"},{"v"},{"w"}},"joined factor identities");
    require(output.equalities().rows==2 &&
        output.equalities().values==Vector{1,-1,0,1,0,1},"joined equalities");
    for (const auto& factor:constrained_witnesses) {
        require(factor_feasible(lift,factor),"constrained factor witness");
        require(physical(lift,factor)==Vector{0,0} && contains(constrained_h,{0,0}),
            "constrained physical H oracle");
    }
    require(!factor_feasible(lift,constrained_left_only) && physical(lift,constrained_left_only)==Vector{0,1} &&
        !contains(constrained_h,{0,1}),"left-only factor oracle");
    require(!factor_feasible(lift,constrained_right_only) && physical(lift,constrained_right_only)==Vector{0,-1} &&
        !contains(constrained_h,{0,-1}),"right-only factor oracle");
    require(!factor_feasible(lift,constrained_infeasible_inside) && physical(lift,constrained_infeasible_inside)==Vector{0,0},
        "noninjective constrained control");
    return {{"status","passed"},{"center",output.center()},{"generators",output.generators().values},
        {"factor_ids",{"u","v","w"}},{"equalities",output.equalities().values},
        {"physical_witnesses",json::array({json::array({0,0}),json::array({0,0})})},
        {"outside_points",json::array({json::array({0,1}),json::array({0,-1})})}};
}

using Fixture=json (*)();
constexpr std::array<Fixture,3> calls{box_image,shared_cancellation,constrained_sum};

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
}

int main(int argc,char** argv) {
    try {
        if (argc==2 && std::string(argv[1])=="--describe") {
            std::cout << json{{"schema","csl.geo07-generator-driver/1"},{"source_commit",source_commit},
                {"module","CSL::geometry_generators"},{"scalar","binary64"},
                {"fixtures",fixtures},{"timed_scope",timed_scope},{"inputs",input_catalogue()}}.dump() << '\n';
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
