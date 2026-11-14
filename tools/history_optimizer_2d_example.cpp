#include <csl/adapters/nlp/casadi_superscs_history_optimizer.hpp>
#include <csl/sets/data.hpp>

#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#include <utility>

using namespace csl;
namespace {
template<class T,class... E> T take(std::variant<T,E...> value) {
    if(!std::holds_alternative<T>(value))throw std::runtime_error("failed to construct 2D history example");
    return std::get<T>(std::move(value));
}
optimization::HistoryOptimizationRequest make_request() {
    constexpr std::size_t n=8;
    Matrix inequalities{4,n,{0,0,0,0,0,0,1,0, 0,0,0,0,0,0,-1,0,
        0,0,0,0,0,0,0,1, 0,0,0,0,0,0,0,-1}};
    Matrix equalities{6,n,{1,0,0,0,0,0,0,0, 0,1,0,0,0,0,0,0,
        -1,0,1,0,0,0,-1,0, 0,-1,0,1,0,0,0,0,
        0,0,-1,0,1,0,0,0, 0,0,0,-1,0,1,0,-1}};
    auto set=take(sets::make_h({{"2d-integrator-history"},n,{}},
        {take(numeric::snapshot(inequalities)),take(numeric::snapshot_vector(Vector{1,0,1,0})),
         take(numeric::snapshot(equalities)),take(numeric::snapshot_vector(Vector(6,0)))}));
    synthesis::JointHistoryRelation histories{{{2,1,0},2},std::move(set)};
    Matrix terminal_map{2,2,{1,0,0,1}};
    Vector terminal_target{1,1};
    Vector terminal_weights{1,1};
    TerminalObjective terminal=ResidualNormTerminal{std::move(terminal_map),
        std::move(terminal_target),std::move(terminal_weights)};
    optimization::RunningControlCost running{"half-l1-control",2,{
        {0,{optimization::EuclideanControlPenalty{{1,1,{1}},{0},0.5}}},
        {1,{optimization::EuclideanControlPenalty{{1,1,{1}},{0},0.5}}}}};
    auto compiled=optimization::compile_history_cost(histories,terminal,running,0);
    if(!std::holds_alternative<optimization::HistoryCostProgram>(compiled))
        throw std::runtime_error("source objective did not compile");
    return {{ProblemId{"two-state-integrator"},ProgramId{"terminal-euclidean-plus-running-l1"}},
        std::move(histories),std::get<optimization::HistoryCostProgram>(std::move(compiled)),
        optimization::ColdStart{}};
}
void write_outputs(const std::filesystem::path& directory,const optimization::HistoryOptimizationResult& result) {
    std::filesystem::create_directories(directory);
    std::ofstream csv(directory/"history.csv");
    csv<<std::setprecision(17);
    csv<<"series,stage,state_x,state_y,u0,u1,source_J\n";
    csv<<"whole-history-source-J,0,0,0,"<<result.history[6]<<','<<result.history[7]<<','<<result.source_cost.total
       <<"\nwhole-history-source-J,1,"<<result.history[2]<<','<<result.history[3]<<','<<result.history[6]<<','<<result.history[7]<<','<<result.source_cost.total
       <<"\nwhole-history-source-J,2,"<<result.history[4]<<','<<result.history[5]<<','<<result.history[6]<<','<<result.history[7]<<','<<result.source_cost.total<<'\n';
    csv<<"squared-terminal-surrogate,0,0,0,0.75,0.75,1.1035533905932737\nsquared-terminal-surrogate,1,0.75,0,0.75,0.75,1.1035533905932737\nsquared-terminal-surrogate,2,0.75,0.75,0.75,0.75,1.1035533905932737\n";
    csv<<"target,2,1,1,0,0,0\n";
    csv.close();
    if(!csv)throw std::runtime_error("failed to write history.csv");
    const auto x=[](double p){return 100.0+500.0*p;};
    const auto y=[](double v){return 650.0-500.0*v;};
    std::ofstream svg(directory/"history.svg");
    svg<<std::setprecision(8);
    svg<<"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"800\" height=\"740\" viewBox=\"0 0 800 740\">"
       <<"<rect width=\"800\" height=\"740\" fill=\"white\"/><text x=\"400\" y=\"30\" text-anchor=\"middle\" font-size=\"18\">2D integrator: full-history source-cost optimization</text>"
       <<"<text x=\"400\" y=\"58\" text-anchor=\"middle\" font-size=\"14\">J = ||x₂ − (1,1)||₂ + 0.5(|u₀| + |u₁|)</text>"
       <<"<path d=\"M100 650 H700 M100 650 V150\" stroke=\"#444\" fill=\"none\"/><text x=\"400\" y=\"700\" text-anchor=\"middle\">state x</text><text x=\"32\" y=\"400\" transform=\"rotate(-90 32 400)\" text-anchor=\"middle\">state y</text>";
    svg<<"<polyline points=\""<<x(0)<<','<<y(0)<<' '<<x(result.history[6])<<','<<y(0)<<' '<<x(result.history[6])<<','<<y(result.history[7])<<"\" fill=\"none\" stroke=\"#0072B2\" stroke-width=\"4\"/>";
    svg<<"<polyline points=\""<<x(0)<<','<<y(0)<<' '<<x(0.75)<<','<<y(0)<<' '<<x(0.75)<<','<<y(0.75)<<"\" fill=\"none\" stroke=\"#D55E00\" stroke-width=\"3\" stroke-dasharray=\"8 6\"/>";
    svg<<"<circle cx=\""<<x(1)<<"\" cy=\""<<y(1)<<"\" r=\"8\" fill=\"#009E73\"/><text x=\"520\" y=\"95\" fill=\"#0072B2\">full source J: "<<result.source_cost.total<<" (blue)</text>"
       <<"<text x=\"520\" y=\"120\" fill=\"#D55E00\">squared-terminal candidate: source J = 1.104 (dashed)</text>"
       <<"<text x=\"400\" y=\"728\" text-anchor=\"middle\" font-size=\"12\">u₀ changes state x; u₁ changes state y. Green point is target (1,1).</text></svg>";
    svg.close();
    if(!svg)throw std::runtime_error("failed to write history.svg");
    std::ofstream html(directory/"index.html");
    html<<std::setprecision(17);
    html<<"<!doctype html><html lang=\"en\"><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><title>Native whole-history source-cost example</title>"
        <<"<style>body{font:16px system-ui;max-width:900px;margin:2rem auto;padding:0 1rem;color:#202124}figure{margin:1rem 0}img{max-width:100%;height:auto}table{border-collapse:collapse}td,th{border:1px solid #bbb;padding:.45rem .7rem;text-align:left}code{background:#f2f2f2;padding:.1rem .2rem}</style>"
        <<"<main><h1>Native whole-history source-cost example</h1><p>Two-step integrator: <code>x₀=(0,0)</code>, <code>x₁=x₀+(u₀,0)</code>, <code>x₂=x₁+(0,u₁)</code>, with <code>u₀,u₁∈[0,1]</code>.</p>"
        <<"<p>Authored objective: <code>J=||x₂−(1,1)||₂ + 0.5(|u₀|+|u₁|)</code>. The native CasADi/SuperSCS provider optimized all state and control history coordinates from an explicit cold start, and the checked core recomputed this source objective. Squaring only the terminal norm gives the distinct surrogate <code>J_sq=||x₂−(1,1)||₂² + 0.5(|u₀|+|u₁|)</code>, whose minimizer is (3/4,3/4); its original source cost is about 1.104.</p>"
        <<"<figure><img src=\"history.svg\" alt=\"Actual whole-history source-cost trajectory and squared-terminal surrogate trajectory plotted in state x and state y coordinates\"><figcaption>Blue is the actual whole-history source-J result; dashed orange is the minimizer of the squared-terminal surrogate; green marks the target.</figcaption></figure>"
        <<"<table><tr><th>Candidate</th><th>u₀</th><th>u₁</th><th>Original source J</th></tr><tr><td>Whole-history solve</td><td>"<<result.history[6]<<"</td><td>"<<result.history[7]<<"</td><td>"<<result.source_cost.total<<"</td></tr><tr><td>Squared-terminal surrogate</td><td>3/4</td><td>3/4</td><td>1.1035533906</td></tr></table>"
        <<"<p>Independent full-H residual: "<<result.maximum_history_violation<<". Backend: <code>"<<result.diagnostics<<"</code>.</p>"
        <<"<p><a href=\"history.csv\">Download the trajectory and source-cost data (CSV)</a>.</p><h2>Evidence boundary</h2><p>This is one functional 2D demonstration of a local numerical candidate and independent binary64 checks. It is not a benchmark, global-optimality proof, nonlinear plant guarantee or validated completeness result.</p></main></html>";
    html.close();
    if(!html)throw std::runtime_error("failed to write index.html");
}
}

int main(int argc,char** argv) {
    if(argc!=2) {std::cerr<<"usage: history_optimizer_2d_example OUTPUT_DIR\n";return 2;}
    try {
        auto request=make_request();
        auto entry=adapters::nlp::make_casadi_superscs_history_optimizer_registration();
        registry::Registry<registry::HistoryOptimizerPort> providers;
        const registry::Method method{entry.identity.id,entry.identity.version};
        if(providers.add(std::move(entry)))throw std::runtime_error("could not register CasADi history optimizer");
        registry::Requirements requirements;
        requirements.output.representation={"csl.whole-history-source-cost.v1"};
        auto prepared=registry::prepare_provider(registry::select_provider(providers,method,requirements));
        if(!std::holds_alternative<registry::PreparedProvider<registry::HistoryOptimizerPort>>(prepared))
            throw std::runtime_error("CasADi history optimizer unavailable");
        auto pipeline=std::get<registry::PreparedProvider<registry::HistoryOptimizerPort>>(prepared).prepare(request);
        if(!std::holds_alternative<registry::PreparedPipeline<registry::HistoryOptimizerPort>>(pipeline))
            throw std::runtime_error("whole-history request rejected");
        auto workspaces=std::get<registry::PreparedPipeline<registry::HistoryOptimizerPort>>(pipeline).create();
        auto result=std::get<0>(workspaces)->run(ExecutionContext{});
        if(!std::holds_alternative<optimization::HistoryOptimizationResult>(result))
            throw std::runtime_error("whole-history solve failed");
        const auto& solved=std::get<optimization::HistoryOptimizationResult>(result);
        write_outputs(argv[1],solved);
        std::cout<<std::setprecision(17);
        std::cout<<"provider="<<method.id.value<<'@'<<*method.version<<"; source J="<<solved.source_cost.total
            <<"; u0="<<solved.history[6]<<"; u1="<<solved.history[7]<<"; max H violation="
            <<solved.maximum_history_violation<<"; "<<solved.diagnostics<<"\n";
        return 0;
    } catch(const std::exception& error) {std::cerr<<error.what()<<'\n';return 1;}
}
