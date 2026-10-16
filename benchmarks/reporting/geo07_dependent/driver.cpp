#include <csl/geometry/generator_adapter.hpp>
#include <csl/registry/provider.hpp>
#include <csl/sets/generator_sets.hpp>
#include <nlohmann/json.hpp>

#include <array>
#include <chrono>
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

constexpr const char* source_commit="5411e37ad456f0d5b3bf775130f149622ef5ebfa";
constexpr const char* trial_schema="csl.geo07-dependent-trial/1";
constexpr std::array<const char*,2> fixture_names{"shared_cancellation","constrained_shared"};
constexpr const char* timed_scope="fresh native generator handles and prepared registered GeometryPort, DependentSum admission and workspace execution, literal factor and physical H checks, independent Minkowski rejection, evidence verification and per-call JSON result assignment; excludes process startup, JSONL serialization, Python saved-row validation, persistence and rendering";

void require(bool condition,const char* message) {
    if(!condition) throw std::runtime_error(message);
}
template<class T,class... Rest> T take(std::variant<T,Rest...> result,const char* message) {
    require(std::holds_alternative<T>(result),message);
    return std::get<T>(std::move(result));
}
registry::PreparedProvider<registry::GeometryPort> provider(RepresentationId representation) {
    registry::Registry<registry::GeometryPort> entries;
    auto registration=make_operation_registration();
    const registry::Method method{registration.identity.id,registration.identity.version};
    require(method.version=="1.1.0","registered version changed");
    require(!entries.add(std::move(registration)).has_value(),"registration failed");
    registry::Requirements requirements;
    requirements.output.representation=representation;
    requirements.output.relation=SetRelation::equivalent;
    return take(registry::prepare_provider(registry::select_provider(entries,method,requirements)),
        "provider preparation failed");
}
OperationResult run(registry::PreparedProvider<registry::GeometryPort>& selected,
        const OperationRequest& request) {
    auto prepared=take(selected.prepare(request),"dependent sum admission failed");
    auto [workspace]=prepared.create();
    return take(workspace->run({{},{},{},{1e-8,1e-8},"geo07-dependent-report"}),
        "dependent sum execution failed");
}
void check_result(const OperationResult& result,const OperationRequest& request) {
    require(result.relation==SetRelation::equivalent &&
        std::holds_alternative<SymbolicArgument>(result.evidence.support) &&
        !result.evidence.error_bound && check_geometry_evidence(result.evidence,request).empty(),
        "geometry evidence or relation changed");
}
void check_independent_rejection(registry::PreparedProvider<registry::GeometryPort>& selected,
        const OperationRequest& dependent) {
    auto independent=dependent;
    const auto& sum=std::get<DependentSum>(dependent.operation);
    independent.operation=MinkowskiSum{sum.left,sum.right};
    independent.identity.request={dependent.identity.request.value+"/independent"};
    const auto candidate=selected.prepare(independent);
    const auto* rejection=std::get_if<registry::Rejection>(&candidate);
    require(rejection && rejection->diagnostics.size()==1 &&
        rejection->diagnostics[0].code==DiagnosticCode::unsupported &&
        rejection->diagnostics[0].field=="generators.minkowski.factor_ids",
        "independent Minkowski accepted shared factor IDs");
}
json matrix_json(const Matrix& value) {
    return {{"rows",value.rows},{"cols",value.cols},{"values",value.values}};
}
json generator_json(const GeneratorInput& value) {
    json ids=json::array();
    for(const auto& id:value.factor_ids) ids.push_back(id.value);
    return {{"id",value.id.value},{"center",value.center},
        {"generators",matrix_json(value.generators)},{"factor_ids",ids},
        {"equalities",matrix_json(value.equalities)},
        {"equality_values",value.equality_values},
        {"coordinate_labels",value.coordinate_labels},
        {"factor_interval",json::array({-1.0,1.0})}};
}
json matrix_h_json(const Matrix& inequalities,const Vector& upper,
        const Matrix& equalities,const Vector& values) {
    return {{"inequalities",matrix_json(inequalities)},{"upper",upper},
        {"equalities",matrix_json(equalities)},{"values",values}};
}
bool contains(const Matrix& inequalities,const Vector& upper,
        const Matrix& equalities,const Vector& values,const Vector& point) {
    if(point.size()!=inequalities.cols || point.size()!=equalities.cols) return false;
    for(std::size_t row=0;row<inequalities.rows;++row) {
        double activity=0;
        for(std::size_t col=0;col<point.size();++col)
            activity+=inequalities.values[row*point.size()+col]*point[col];
        if(activity>upper[row]) return false;
    }
    for(std::size_t row=0;row<equalities.rows;++row) {
        double activity=0;
        for(std::size_t col=0;col<point.size();++col)
            activity+=equalities.values[row*point.size()+col]*point[col];
        if(activity!=values[row]) return false;
    }
    return true;
}
bool feasible(const GeneratorSet& set,const Vector& factors) {
    if(factors.size()!=set.factor_ids().size()) return false;
    for(double factor:factors) if(factor < -1 || factor > 1) return false;
    for(std::size_t row=0;row<set.equalities().rows;++row) {
        double activity=0;
        for(std::size_t col=0;col<factors.size();++col)
            activity+=set.equalities().values[row*factors.size()+col]*factors[col];
        if(activity!=set.equality_values()[row]) return false;
    }
    return true;
}
Vector physical(const GeneratorSet& set,const Vector& factors) {
    require(factors.size()==set.factor_ids().size(),"factor count changed");
    Vector point=set.center();
    for(std::size_t row=0;row<point.size();++row)
        for(std::size_t col=0;col<factors.size();++col)
            point[row]+=set.generators().values[row*factors.size()+col]*factors[col];
    return point;
}

const GeneratorInput cancel_left{{"dependent-cancel-left"},{0},{1,1,{1}},
    {{"history.0"}},{0,1,{}},{},{}};
const GeneratorInput cancel_right{{"dependent-cancel-right"},{0},{1,1,{-1}},
    {{"history.0"}},{0,1,{}},{},{}};
const GeneratorInput constrained_left{{"dependent-constrained-left"},{0,0},
    {2,2,{1,0,0,1}},{{"u"},{"v"}},{1,2,{1,-1}},{0},{}};
const GeneratorInput constrained_right{{"dependent-constrained-right"},{0,0},
    {2,2,{-1,0,0,1}},{{"u"},{"w"}},{1,2,{1,1}},{0},{}};
const Matrix point_h_1d{0,1,{}};
const Matrix point_equal_1d{1,1,{1}};
const Matrix point_h_2d{0,2,{}};
const Matrix point_equal_2d{2,2,{1,0,0,1}};

json request_json(const char* request_id) {
    return {{"problem_id","geo07-dependent"},{"request_id",request_id},
        {"assurance","numerical"},{"prepared_scalar","binary64"},
        {"prepared_output_relation","equivalent"},
        {"registration_version","1.1.0"}};
}
json input_catalogue() {
    return {
        {"shared_cancellation",{{"operation","dependent_sum"},
            {"registration","csl.geometry.generators.operations"},
            {"public_request",request_json("shared-cancellation")},
            {"left",generator_json(cancel_left)},{"right",generator_json(cancel_right)},
            {"output_id","dependent-cancel-origin"},
            {"output_representation","csl.zonotope"},
            {"physical_h",matrix_h_json(point_h_1d,{},point_equal_1d,{0})},
            {"feasible_factor_witnesses",json::array({Vector{-1},Vector{0},Vector{1}})},
            {"inside_points",json::array({Vector{0},Vector{0},Vector{0}})},
            {"outside_points",json::array({Vector{-1},Vector{1}})},
            {"rejection_controls",{{"independent_shared_ids",true}}}}},
        {"constrained_shared",{{"operation","dependent_sum"},
            {"registration","csl.geometry.generators.operations"},
            {"public_request",request_json("constrained-shared")},
            {"left",generator_json(constrained_left)},
            {"right",generator_json(constrained_right)},
            {"output_id","dependent-constrained-origin"},
            {"output_representation","csl.constrained-zonotope"},
            {"physical_h",matrix_h_json(point_h_2d,{},point_equal_2d,{0,0})},
            {"feasible_factor_witnesses",json::array({Vector{-1,-1,1},Vector{0,0,0},Vector{1,1,-1}})},
            {"inside_points",json::array({Vector{0,0},Vector{0,0},Vector{0,0}})},
            {"outside_points",json::array({Vector{0,1},Vector{1,0}})},
            {"rejection_controls",{{"independent_shared_ids",true}}}}}};
}

json cancellation() {
    const auto left=take(make_generator_set(cancel_left),"cancellation left rejected");
    const auto right=take(make_generator_set(cancel_right),"cancellation right rejected");
    auto selected=provider({"csl.zonotope"});
    const OperationRequest request{{{"geo07-dependent"},{"shared-cancellation"},
            {"dependent-cancel-origin"}}, {"csl.geometry.generators.operations"},
        DependentSum{left.as_handle(),right.as_handle()},
        SetRelation::equivalent,Assurance::numerical};
    const auto result=run(selected,request);
    check_result(result,request);
    const auto output=take(from_generator_handle(result.output),"cancellation output rejected");
    require(result.output.id.value=="dependent-cancel-origin" &&
        output.center()==Vector{0} && output.generators().values==Vector{0} &&
        output.factor_ids()==std::vector<FactorId>{{"history.0"}} &&
        output.equalities().rows==0,"cancellation payload changed");
    json witnesses=json::array();
    for(const Vector factors:std::array<Vector,3>{Vector{-1},Vector{0},Vector{1}}) {
        const auto point=physical(output,factors);
        require(feasible(output,factors) && point==Vector{0} &&
            contains(point_h_1d,{},point_equal_1d,{0},point),
            "cancellation factor or literal H oracle changed");
        witnesses.push_back(point);
    }
    require(!contains(point_h_1d,{},point_equal_1d,{0},{-1}) &&
        !contains(point_h_1d,{},point_equal_1d,{0},{1}),
        "cancellation outside H oracle changed");
    check_independent_rejection(selected,request);
    return {{"status","passed"},{"center",output.center()},
        {"generators",output.generators().values},
        {"factor_ids",json::array({"history.0"})},{"equalities",json::array()},
        {"physical_witnesses",witnesses},
        {"outside_points",json::array({Vector{-1},Vector{1}})},
        {"relation","equivalent"},{"support","symbolic_argument"},
        {"error_bound",false},
        {"rejections",{{"independent_shared_ids","generators.minkowski.factor_ids"}}}};
}

json constrained() {
    const auto left=take(make_generator_set(constrained_left),"constrained left rejected");
    const auto right=take(make_generator_set(constrained_right),"constrained right rejected");
    auto selected=provider({"csl.constrained-zonotope"});
    const OperationRequest request{{{"geo07-dependent"},{"constrained-shared"},
            {"dependent-constrained-origin"}}, {"csl.geometry.generators.operations"},
        DependentSum{left.as_handle(),right.as_handle()},
        SetRelation::equivalent,Assurance::numerical};
    const auto result=run(selected,request);
    check_result(result,request);
    const auto output=take(from_generator_handle(result.output),"constrained output rejected");
    require(result.output.id.value=="dependent-constrained-origin" &&
        output.center()==Vector{0,0} &&
        output.generators().values==Vector{0,0,0,0,1,1} &&
        output.factor_ids()==std::vector<FactorId>{{"u"},{"v"},{"w"}} &&
        output.equalities().rows==2 && output.equalities().cols==3 &&
        output.equalities().values==Vector{1,-1,0,1,0,1} &&
        output.equality_values()==Vector{0,0},"constrained shared payload changed");
    json witnesses=json::array();
    for(const Vector factors:std::array<Vector,3>{Vector{-1,-1,1},Vector{0,0,0},Vector{1,1,-1}}) {
        const auto point=physical(output,factors);
        require(feasible(output,factors) && point==Vector{0,0} &&
            contains(point_h_2d,{},point_equal_2d,{0,0},point),
            "constrained factor or literal H oracle changed");
        witnesses.push_back(point);
    }
    require(!feasible(output,{1,1,0}) &&
        physical(output,{1,1,0})==Vector{0,1} &&
        !contains(point_h_2d,{},point_equal_2d,{0,0},{0,1}) &&
        !contains(point_h_2d,{},point_equal_2d,{0,0},{1,0}),
        "constrained exclusion oracle changed");
    check_independent_rejection(selected,request);
    return {{"status","passed"},{"center",output.center()},
        {"generators",output.generators().values},
        {"factor_ids",json::array({"u","v","w"})},
        {"equalities",output.equalities().values},
        {"physical_witnesses",witnesses},
        {"outside_points",json::array({Vector{0,1},Vector{1,0}})},
        {"relation","equivalent"},{"support","symbolic_argument"},
        {"error_bound",false},
        {"rejections",{{"independent_shared_ids","generators.minkowski.factor_ids"}}}};
}

using Fixture=json (*)();
constexpr std::array<Fixture,2> calls{cancellation,constrained};
int positive(const char* text,int minimum,int maximum) {
    const auto value=std::stoi(text);
    if(value<minimum || value>maximum || std::to_string(value)!=text)
        throw std::invalid_argument("invalid positive integer");
    return value;
}
bool batch(std::size_t index,int round,bool warmup,int calls_per_batch) {
    int checked=0;
    json observed;
    std::string error;
    const auto begin=Clock::now();
    for(int call=0;call<calls_per_batch;++call) {
        try { observed=calls[index](); ++checked; }
        catch(const std::exception& exception) { error=exception.what(); break; }
    }
    const auto end=Clock::now();
    const auto elapsed=std::chrono::duration_cast<std::chrono::nanoseconds>(end-begin).count();
    std::cout << json{{"schema",trial_schema},{"fixture",fixture_names[index]},
        {"round",round},{"warmup",warmup},{"batch",calls_per_batch},
        {"checked_calls",checked},{"elapsed_ns",elapsed},
        {"status",error.empty()?"passed":"oracle_failed"},
        {"error",error.empty()?json(nullptr):json(error)},
        {"result",observed}}.dump() << '\n';
    std::cout.flush();
    return error.empty();
}
} // namespace

int main(int argc,char** argv) {
    try {
        if(argc==2 && std::string(argv[1])=="--describe") {
            std::cout << json{{"schema","csl.geo07-dependent-driver/1"},
                {"source_commit",source_commit},
                {"module","CSL::generator_adapter"},
                {"registration","csl.geometry.generators.operations@1.1.0"},
                {"scalar","binary64"},{"fixtures",fixture_names},
                {"timed_scope",timed_scope},{"inputs",input_catalogue()}}.dump() << '\n';
            return 0;
        }
        const bool smoke=argc==2 && std::string(argv[1])=="--smoke";
        const bool measure=argc==5 && std::string(argv[1])=="--measure";
        if(!smoke && !measure)
            throw std::invalid_argument("usage: --describe | --smoke | --measure REPETITIONS WARMUPS BATCH");
        const int repetitions=smoke?1:positive(argv[2],7,100);
        const int warmups=smoke?0:positive(argv[3],1,1);
        const int count=smoke?1:positive(argv[4],1,100000);
        bool passed=true;
        for(int warmup=0;warmup<warmups;++warmup)
            for(std::size_t i=0;i<calls.size();++i) passed=batch(i,warmup,true,count) && passed;
        for(int round=0;round<repetitions;++round) {
            if(round%2==0)
                for(std::size_t i=0;i<calls.size();++i) passed=batch(i,round,false,count) && passed;
            else
                for(std::size_t i=calls.size();i>0;--i) passed=batch(i-1,round,false,count) && passed;
        }
        return passed?0:2;
    } catch(const std::exception& exception) {
        std::cerr << exception.what() << '\n';
        return 2;
    }
}
