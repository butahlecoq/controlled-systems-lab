#include <csl/optimization/validated_finite_action_minimax.hpp>
#include <nlohmann/json.hpp>

#include <chrono>
#include <cmath>
#include <iostream>
#include <limits>
#include <sstream>
#include <stdexcept>
#include <string>
#include <string_view>
#include <variant>
#include <vector>

#ifndef CSL_ISSUE3_VALIDATED_SOURCE_COMMIT
#define CSL_ISSUE3_VALIDATED_SOURCE_COMMIT "unknown"
#endif
#ifndef CSL_ISSUE3_VALIDATED_HARNESS_COMMIT
#define CSL_ISSUE3_VALIDATED_HARNESS_COMMIT "unknown"
#endif
#ifndef CSL_ISSUE3_VALIDATED_FIXTURE_SHA256
#define CSL_ISSUE3_VALIDATED_FIXTURE_SHA256 "unknown"
#endif

namespace {
using namespace csl;
using namespace csl::optimization;
using json = nlohmann::json;
using Clock = std::chrono::steady_clock;

template<class T> T take(std::variant<T, Diagnostic> value) {
    if (!std::holds_alternative<T>(value))
        throw std::runtime_error("invalid validated minimax fixture");
    return std::get<T>(std::move(value));
}

sets::SetData singleton(std::string id, std::vector<double> point,
                        std::vector<std::string> labels) {
    const auto dimension=point.size();
    return take(sets::make_singleton({{std::move(id)}, dimension, std::move(labels)},
        take(numeric::snapshot_vector(std::move(point)))));
}

sets::SetData universal(std::string id, std::size_t dimension) {
    return take(sets::make_universal({{std::move(id)}, dimension, {}}));
}

Objective residual(std::size_t dimension, std::vector<double> c,
                   std::vector<double> target) {
    auto result=snapshot(ResidualNormTerminal{
        {dimension, dimension, std::move(c)}, std::move(target)});
    if (!std::holds_alternative<Objective>(result))
        throw std::runtime_error("invalid residual objective fixture");
    return std::get<Objective>(std::move(result));
}

std::string hex(double value) {
    std::ostringstream stream;
    stream << std::hexfloat << value;
    return stream.str();
}

json vector_hex(const std::vector<double>& values) {
    json result=json::array();
    for (double value:values) result.push_back(hex(value));
    return result;
}

json matrix_hex(std::size_t rows, std::size_t columns,
                const std::vector<double>& values) {
    if (rows*columns!=values.size())
        throw std::invalid_argument("fixture matrix dimensions do not match");
    json result=json::array();
    for (std::size_t row=0;row<rows;++row) {
        json current=json::array();
        for (std::size_t column=0;column<columns;++column)
            current.push_back(hex(values[row*columns+column]));
        result.push_back(std::move(current));
    }
    return result;
}

json fixture_input(std::string_view name) {
    json input;
    if (name=="analytic_2d") {
        input["system"]={{"A",matrix_hex(2,2,{1,0,0,1})},
            {"B",matrix_hex(2,2,{1,0,0,1})},
            {"E",matrix_hex(2,2,{1,0,0,1})},
            {"c",vector_hex({0,0})},{"horizon",1}};
        input["initial"]=vector_hex({0,0});
        input["actions"]=json::array({vector_hex({0,0}),vector_hex({1,0})});
        input["disturbance_vertices"]=json::array({vector_hex({0,0})});
        input["safe_sets"]="universal";
        input["objective"]={{"type","residual_norm_terminal"},
            {"C",matrix_hex(2,2,{1,0,0,1})},{"target",vector_hex({1,0})}};
        return input;
    }
    if (name=="all_infeasible") {
        input["system"]={{"A",matrix_hex(1,1,{1})},
            {"B",matrix_hex(1,1,{0})},{"E",matrix_hex(1,1,{0})},
            {"c",vector_hex({0})},{"horizon",1}};
        input["initial"]=vector_hex({0});
        input["actions"]=json::array({vector_hex({0})});
        input["disturbance_vertices"]=json::array({vector_hex({0})});
        input["safe_sets"]={"universal","singleton(0x1p+0)"};
        input["objective"]={{"type","linear_terminal"},
            {"coefficients",vector_hex({1})},{"offset",hex(0)} };
        return input;
    }
    if (name=="b08_rounded") {
        json disturbances=json::array();
        for (std::size_t stage=0;stage<4;++stage) {
            const double a=0.1+0.1*static_cast<double>(stage);
            const double b=0.1+0.3*static_cast<double>(stage);
            json vertices=json::array();
            for (const auto& point : std::vector<std::vector<double>>{
                    {-a,-b},{-a,b},{a,-b},{a,b}}) {
                json row=json::array();
                for (double value:point) row.push_back(hex(value));
                vertices.push_back(std::move(row));
            }
            disturbances.push_back(std::move(vertices));
        }
        input["system"]={{"A",matrix_hex(4,4,{1,0,0,0,-25,1,0,0,0,0,1,0,0,0,-25,1})},
            {"B",matrix_hex(4,1,{20.073,0,-10.473,0})},
            {"E",matrix_hex(4,2,{1,0,0,0,0,-1,0,0})},
            {"c",vector_hex({0,0,0,0})},{"horizon",4}};
        input["initial"]=vector_hex({1182.074,119560,459.832,45260});
        input["actions"]=json::array({vector_hex({0.6}),vector_hex({0.3}),
            vector_hex({0}),vector_hex({-0.3}),vector_hex({-0.6})});
        input["disturbance_vertices_binary64_hex"]=std::move(disturbances);
        input["safe_sets"]="universal";
        input["objective"]={{"type","residual_norm_terminal"},
            {"C",matrix_hex(4,4,{1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1})},
            {"target",vector_hex({1200,0,450,0})}};
        return input;
    }
    throw std::invalid_argument("unknown fixture metadata");
}

ValidatedFiniteActionMinimaxRequest analytic_2d() {
    const auto authored = SystemModel{{{2, 2, 2}, TimeDomain::discrete,
        LinearStage{{2, 2, {1,0,0,1}}, {2,2,{1,0,0,1}},
                    {2,2,{1,0,0,1}}, {0,0}}}, {}};
    const auto resolved = take(model::snapshot(authored, Vector{0,1}));
    const auto initial = singleton("initial", {0,0}, {"x","y"});
    const auto noise = singleton("disturbance", {0,0}, {"w0","w1"});
    return {{"issue3-validated-2d"}, {"issue3-validated-2d-run"}, resolved,
        initial, {2, {{0,0},{1,0}}}, {noise},
        {universal("safe0",2), universal("safe1",2)},
        residual(2,{1,0,0,1},{1,0})};
}

ValidatedFiniteActionMinimaxRequest infeasible_1d() {
    const auto authored = SystemModel{{{1,1,1}, TimeDomain::discrete,
        LinearStage{{1,1,{1}}, {1,1,{0}}, {1,1,{0}}, {0}}}, {}};
    const auto resolved = take(model::snapshot(authored, Vector{0,1}));
    const auto impossible = singleton("impossible-safe", {1}, {"x"});
    return {{"issue3-validated-infeasible"}, {"issue3-validated-infeasible-run"},
        resolved, singleton("initial",{0},{"x"}), {1,{{0}}},
        {singleton("disturbance",{0},{"w"})},
        {universal("safe0",1), impossible},
        [] {
            auto result=snapshot(LinearTerminal{{1},0});
            if (!std::holds_alternative<Objective>(result))
                throw std::runtime_error("invalid linear objective fixture");
            return std::get<Objective>(std::move(result));
        }()};
}

ValidatedFiniteActionMinimaxRequest b08() {
    const auto authored = SystemModel{{{4,1,2}, TimeDomain::discrete,
        LinearStage{{4,4,{1,0,0,0,-25,1,0,0,0,0,1,0,0,0,-25,1}},
                    {4,1,{20.073,0,-10.473,0}},
                    {4,2,{1,0,0,0,0,-1,0,0}}, {0,0,0,0}}}, {}};
    const auto resolved = take(model::snapshot(authored, Vector{0,1,2,3,4}));
    const auto initial = singleton("b08-initial",{1182.074,119560,459.832,45260},
                                  {"x0","x1","x2","x3"});
    std::vector<sets::SetData> disturbances;
    for (std::size_t stage=0; stage<4; ++stage) {
        const double a=0.1+0.1*static_cast<double>(stage);
        const double b=0.1+0.3*static_cast<double>(stage);
        disturbances.push_back(take(sets::make_v(
            {{"b08-w"+std::to_string(stage)},2,{"w0","w1"}},
            {take(numeric::snapshot(Matrix{4,2,{-a,-b,-a,b,a,-b,a,b}})),
             take(numeric::snapshot(Matrix{0,2,{}}))})));
    }
    std::vector<sets::SetData> safe_sets;
    for (std::size_t stage=0; stage<5; ++stage)
        safe_sets.push_back(universal("b08-safe"+std::to_string(stage),4));
    return {{"b08-displayed-rounded"},{"issue3-validated-b08"},resolved,initial,
        {1,{{0.6},{0.3},{0},{-0.3},{-0.6}}},disturbances,safe_sets,
        residual(4,{1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1},{1200,0,450,0})};
}

json inspect(std::string_view fixture,
              const ValidatedFiniteActionMinimaxOutcome& outcome) {
    if (fixture == "analytic_2d") {
        if (!std::holds_alternative<ValidatedMinimaxBounds>(outcome))
            throw std::runtime_error("2D analytic outcome was not bounded");
        const auto& bounds=std::get<ValidatedMinimaxBounds>(outcome);
        if (bounds.plans().size()!=2 || bounds.lower()!=0.0 || bounds.upper()!=0.0 ||
            !std::holds_alternative<ValidatedPlanFeasible>(bounds.plans()[1]))
            throw std::runtime_error("2D analytic literal result mismatch");
        const auto& plan=std::get<ValidatedPlanFeasible>(bounds.plans()[1]);
        if (plan.action_indices!=std::vector<std::size_t>{1} ||
            plan.worst_case.lower!=0.0 || plan.worst_case.upper!=0.0)
            throw std::runtime_error("2D minimizing action mismatch");
        return {{"status","validated_bounds"},{"lower",bounds.lower()},
            {"upper",bounds.upper()},{"plans",bounds.plans().size()},
            {"histories_examined",2}};
    }
    if (fixture == "all_infeasible") {
        if (!std::holds_alternative<ValidatedMinimaxInfeasible>(outcome))
            throw std::runtime_error("infeasible literal result mismatch");
        const auto& result=std::get<ValidatedMinimaxInfeasible>(outcome);
        if (result.plans().size()!=1 ||
            !std::holds_alternative<ValidatedPlanInfeasible>(result.plans()[0]))
            throw std::runtime_error("infeasible ledger mismatch");
        return {{"status","all_plans_infeasible"},{"plans",result.plans().size()}};
    }
    if (!std::holds_alternative<ValidatedMinimaxBounds>(outcome)) {
        if (const auto* unsupported=std::get_if<Unsupported>(&outcome)) {
            const auto& diagnostic=unsupported->diagnostics.front();
            throw std::runtime_error("B08 unsupported: "+diagnostic.field+" "+diagnostic.explanation);
        }
        if (const auto* stopped=std::get_if<OperationStopped>(&outcome))
            throw std::runtime_error("B08 stopped: "+stopped->diagnostics);
        throw std::runtime_error("B08 validated outcome was not bounded; variant="+
                                 std::to_string(outcome.index()));
    }
    const auto& bounds=std::get<ValidatedMinimaxBounds>(outcome);
    if (bounds.plans().size()!=625 || !std::isfinite(bounds.lower()) ||
        !std::isfinite(bounds.upper()) || bounds.lower()>67.150602 ||
        bounds.upper()<67.150600 || bounds.lower()>bounds.upper())
        throw std::runtime_error("B08 validated interval/literal result mismatch");
    std::size_t feasible=0, histories=0;
    for (const auto& evidence:bounds.plans()) {
        if (const auto* plan=std::get_if<ValidatedPlanFeasible>(&evidence)) {
            ++feasible; histories+=plan->histories_examined;
        } else {
            throw std::runtime_error("B08 contains non-feasible plan evidence");
        }
    }
    if (feasible!=625 || histories!=160000)
        throw std::runtime_error("B08 plan/history work count mismatch");
    return {{"status","validated_bounds"},{"lower",bounds.lower()},
        {"upper",bounds.upper()},{"plans",feasible},{"histories_examined",histories}};
}

void run(std::string_view name, const ValidatedFiniteActionMinimaxRequest& request,
         int round, bool warmup, int calls, ValidatedFiniteActionMinimaxLimits limits) {
    json final;
    const auto start=Clock::now();
    for (int call=0; call<calls; ++call) {
        const auto result=validated_finite_action_minimax(request,limits);
        final=inspect(name,result);
    }
    const auto elapsed=std::chrono::duration_cast<std::chrono::nanoseconds>(
        Clock::now()-start).count();
    std::cout << json{{"schema","csl.issue3-validated-raw-trial/1"},
        {"source_commit",CSL_ISSUE3_VALIDATED_SOURCE_COMMIT},
        {"harness_commit",CSL_ISSUE3_VALIDATED_HARNESS_COMMIT},
        {"fixture_sha256",CSL_ISSUE3_VALIDATED_FIXTURE_SHA256},
        {"fixture",name},{"round",round},{"warmup",warmup},
        {"calls",calls},{"elapsed_ns",elapsed},{"status","passed"},
        {"input_canonical",fixture_input(name).dump()},
        {"limits",{{"max_plans",limits.max_plans},
                    {"max_histories_per_plan",limits.max_histories_per_plan},
                    {"max_interval_operations",limits.max_interval_operations}}},
        {"objective_convention",name=="all_infeasible"?"linear terminal objective":"Euclidean terminal residual norm"},
        {"assurance","validated"},
        {"result",final}}.dump() << '\n';
}

} // namespace

int main(int argc,char** argv) {
    try {
        if (argc==2 && std::string_view(argv[1])=="--smoke") {
            run("analytic_2d",analytic_2d(),0,true,1,{2,2,100000});
            run("all_infeasible",infeasible_1d(),0,true,1,{1,1,100000});
            run("b08_rounded",b08(),0,true,1,{625,256,100000000});
            return 0;
        }
        if (argc!=4 || std::string_view(argv[1])!="--measure")
            throw std::invalid_argument("usage: --smoke | --measure REPETITIONS WARMUP");
        const int repetitions=std::stoi(argv[2]);
        if (repetitions<5 || repetitions>100 || std::string_view(argv[3])!="1")
            throw std::invalid_argument("repetitions must be 5..100 and warmup must be 1");
        const auto small=analytic_2d();
        const auto infeasible=infeasible_1d();
        const auto large=b08();
        for (int round=0; round<=repetitions; ++round) {
            const bool warmup=round==0;
            if (round%2==0) {
                run("analytic_2d",small,round,warmup,100,{2,2,100000});
                run("all_infeasible",infeasible,round,warmup,100,{1,1,100000});
                run("b08_rounded",large,round,warmup,1,{625,256,100000000});
            } else {
                run("b08_rounded",large,round,warmup,1,{625,256,100000000});
                run("all_infeasible",infeasible,round,warmup,100,{1,1,100000});
                run("analytic_2d",small,round,warmup,100,{2,2,100000});
            }
        }
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 2;
    }
}
