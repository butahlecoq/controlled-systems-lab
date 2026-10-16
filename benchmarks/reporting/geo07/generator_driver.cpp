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

template<class T> T take(std::variant<T,Diagnostics> result) {
    if (!std::holds_alternative<T>(result)) throw std::runtime_error("public generator API rejected fixture");
    return std::get<T>(std::move(result));
}

struct LiteralH { Matrix inequalities; Vector upper; Matrix equalities; Vector values; };

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
    const auto input=take(make_generator_set({{"report-box"},{1,2},{2,2,{2,0,0,3}},
        {{"horizontal"},{"vertical"}},{0,2,{}},{},{}}));
    const auto output=take(affine_image(input,{1,2,{1,1}},{4},{"report-image"}));
    const auto lift=take(factor_polyhedron(output));
    const LiteralH reference{{2,1,{1,-1}},{12,-2},{0,1,{}},{}};
    require(output.center()==Vector{7} && output.generators().values==Vector{2,3},"box coefficients");
    require(lift.factor_ids==std::vector<FactorId>{{"horizontal"},{"vertical"}},"box factor identities");
    for (const auto& [factor,expected]:std::array<std::pair<Vector,Vector>,4>{
            std::pair{Vector{-1,-1},Vector{2}}, {Vector{0,0},Vector{7}},
            {Vector{1,1},Vector{12}}, {Vector{-1,1},Vector{8}}}) {
        require(factor_feasible(lift,factor),"box factor witness");
        require(physical(lift,factor)==expected && contains(reference,expected),"box physical H oracle");
    }
    require(!contains(reference,{1}) && !contains(reference,{13}),"box outside H oracle");
    require(!factor_feasible(lift,{2,-1}) && physical(lift,{2,-1})==Vector{8},"box noninjective control");
    return {{"status","passed"},{"center",output.center()},{"generators",output.generators().values},
        {"factor_ids",{"horizontal","vertical"}},{"physical_witnesses",json::array({2,7,12,8})},
        {"outside_points",json::array({1,13})}};
}

json shared_cancellation() {
    const auto left=take(make_generator_set({{"report-left"},{0},{1,1,{1}},{{"history.0"}},
        {0,1,{}},{},{}}));
    const auto right=take(make_generator_set({{"report-right"},{0},{1,1,{-1}},{{"history.0"}},
        {0,1,{}},{},{}}));
    const auto output=take(dependent_sum(left,right,{"report-cancelled"}));
    const auto lift=take(factor_polyhedron(output));
    const LiteralH reference{{0,1,{}},{},{1,1,{1}},{0}};
    require(output.factor_ids()==std::vector<FactorId>{{"history.0"}} &&
        output.generators().values==Vector{0},"shared factor was cloned or dropped");
    require(lift.factor_ids==std::vector<FactorId>{{"history.0"}},"lift identity");
    for (double factor:Vector{-1,0,1}) {
        require(factor_feasible(lift,{factor}),"cancellation factor witness");
        require(physical(lift,{factor})==Vector{0} && contains(reference,{0}),"cancellation H oracle");
    }
    require(!contains(reference,{-1}) && !contains(reference,{1}),"cancellation outside H oracle");
    require(std::holds_alternative<Diagnostics>(minkowski_sum(left,right,{"independent-rejected"})),
        "overlapping independent sum admitted");
    return {{"status","passed"},{"center",output.center()},{"generators",output.generators().values},
        {"factor_ids",{"history.0"}},{"physical_witnesses",json::array({0,0,0})},
        {"outside_points",json::array({-1,1})}};
}

json constrained_sum() {
    const auto left=take(make_generator_set({{"report-constrained-left"},{0,0},
        {2,2,{1,0,0,1}},{{"u"},{"v"}},{1,2,{1,-1}},{0},{}}));
    const auto right=take(make_generator_set({{"report-constrained-right"},{0,0},
        {2,2,{-1,0,0,1}},{{"u"},{"w"}},{1,2,{1,1}},{0},{}}));
    const auto output=take(dependent_sum(left,right,{"report-constrained-sum"}));
    const auto lift=take(factor_polyhedron(output));
    const LiteralH reference{{0,2,{}},{},{2,2,{1,0,0,1}},{0,0}};
    require(lift.factor_ids==std::vector<FactorId>{{"u"},{"v"},{"w"}},"joined factor identities");
    require(output.equalities().rows==2 &&
        output.equalities().values==Vector{1,-1,0,1,0,1},"joined equalities");
    for (const auto& factor:std::array<Vector,2>{Vector{1,1,-1},Vector{0,0,0}}) {
        require(factor_feasible(lift,factor),"constrained factor witness");
        require(physical(lift,factor)==Vector{0,0} && contains(reference,{0,0}),
            "constrained physical H oracle");
    }
    require(!factor_feasible(lift,{1,1,0}) && physical(lift,{1,1,0})==Vector{0,1} &&
        !contains(reference,{0,1}),"left-only factor oracle");
    require(!factor_feasible(lift,{1,0,-1}) && physical(lift,{1,0,-1})==Vector{0,-1} &&
        !contains(reference,{0,-1}),"right-only factor oracle");
    require(!factor_feasible(lift,{1,0,0}) && physical(lift,{1,0,0})==Vector{0,0},
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
                {"fixtures",fixtures},{"timed_scope","fresh public API construction, operation, lift, and literal H oracle checks"}}.dump() << '\n';
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
