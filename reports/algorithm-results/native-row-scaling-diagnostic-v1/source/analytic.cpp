#include <csl/adapters/convex/highs.hpp>
#include <csl/optimization/convex_backend.hpp>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <stdexcept>
#include "row_scaling.hpp"
int main(int argc, char** argv) try {
    using namespace csl; using namespace csl::optimization; using namespace csl::registry;
    if(argc != 2) throw std::runtime_error("Expected fresh analytic output path");
    const std::filesystem::path output(argv[1]);
    if(!std::filesystem::create_directory(output)) throw std::runtime_error("Output must be new");
    const double tiny = std::scalbn(1.0, -50);
    auto made = make_convex_program({{{"row-diagnostic-analytic"},{"equality-2d-v1"}},
        QuadraticTerminal{{2,2,{2,0,0,2}}, {0,0}, 0},
        {1,2,{0,2},{0,1},{tiny,tiny}}, {{},{}}, {{3*tiny,3*tiny}}, std::nullopt});
    if(!std::holds_alternative<ConvexProgram>(made)) throw std::runtime_error("Analytic construction failed");
    const auto original = std::get<ConvexProgram>(made);
    const auto scaled = row_diagnostic::export_and_scale(original,output/"program",0,0,0,true);
    Registry<ConvexPort> providers;
    if(providers.add(std::get<Registration<ConvexPort>>(adapters::convex::make_highs_registration()))) throw std::runtime_error("Registration failed");
    Requirements req; req.output.representation={"csl.program-result.v1"};
    auto selected=prepare_pipeline(select(providers,{{"csl.convex.highs"},{}},scaled,req));
    if(!std::holds_alternative<PreparedPipeline<ConvexPort>>(selected)) throw std::runtime_error("Analytic scaled admission refused");
    auto [workspace]=std::get<PreparedPipeline<ConvexPort>>(selected).create();
    auto outcome=workspace->run({std::make_shared<const ResourcePolicy>(ResourcePolicy{1,1,1,{}}),{},{},{1e-8,1e-8},"analytic-row-transform"});
    const auto* result=std::get_if<ProgramResult>(&outcome);
    if(!result) throw std::runtime_error("Analytic solver unsupported");
    std::ofstream(output/"native.txt") << result->raw_diagnostics;
    if(!result->primal || result->termination!=Termination::completed || result->outcome.value!=MathematicalOutcome::optimal) throw std::runtime_error("Analytic result not completed optimum");
    const auto& z=*result->primal;
    if(z.size()!=2 || std::abs(z[0]-1.5)>1e-6 || std::abs(z[1]-1.5)>1e-6) throw std::runtime_error("Analytic independent minimizer check failed");
    const auto checked=evaluate_primal(original,z,{1e-8,1e-8},{{"analytic-original"},"1"});
    if(!std::holds_alternative<ConvexPrimalEvaluation>(checked)) throw std::runtime_error("Original evaluation failed");
    std::cout << std::setprecision(17) << "analytic x="<<z[0]<<" y="<<z[1]<<" objective="<<std::get<ConvexPrimalEvaluation>(checked).original_objective<<" expected=4.5\n";
    return 0;
} catch(const std::exception& e) {std::cerr<<e.what()<<'\n';return 1;}
