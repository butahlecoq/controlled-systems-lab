#include <csl/optimization/phase_one.hpp>
#include <iostream>

int main() {
    using namespace csl;
    using namespace csl::registry;
    namespace po=csl::optimization::phase_one;
    auto value=po::make_program({{"installed"},{"signed-phase-one"}},{1,1,{0,1},{0},{-2}},Vector{-4});
    const auto* program=std::get_if<LinearProgram>(&value);
    if(!program) return 1;
    auto entry=po::make_registration();
    auto* registration=std::get_if<Registration<LPPort>>(&entry);
    if(!registration) return 2;
    Registry<LPPort> registry;
    if(registry.add(std::move(*registration))) return 3;
    Requirements requirements;requirements.output.representation={"csl.program-result.v1"};requirements.basis_diagnostics=true;
    auto prepared=prepare_pipeline(select(registry,{{"phase-one-bland"},"1"},*program,requirements));
    auto* plan=std::get_if<PreparedPipeline<LPPort>>(&prepared);
    if(!plan) return 4;
    auto [worker]=plan->create();
    const auto outcome=worker->run({{},{},{},{1e-8,0},"installed"});
    const auto* result=std::get_if<ProgramResult>(&outcome);
    if(!result || result->termination!=Termination::completed || result->outcome.value!=MathematicalOutcome::optimal ||
       !result->primal || *result->primal!=Vector{2} || !std::holds_alternative<Unestablished>(result->outcome.support) ||
       result->objective.lower || result->objective.upper || !optimization::check_program_result(*result,*program,Assurance::numerical).empty()) return 5;
    const auto evaluated=optimization::evaluate_primal(*program,*result->primal,{1e-8,0},{{"installed-original"},"1"});
    const auto* check=std::get_if<optimization::PrimalEvaluation>(&evaluated);
    if(!check || check->objective!=0 || check->residuals.rows.violation!=0 || check->residuals.variables.violation!=0) return 6;
    const auto* diagnostics=dynamic_cast<const po::DiagnosticsView*>(worker->basis());
    if(!diagnostics) return 7;
    const auto snapshot=diagnostics->phase_one_snapshot();const auto* report=std::get_if<po::Snapshot>(&snapshot);
    if(!report || report->pivots!=1 || !report->auxiliary || report->auxiliary->value!=0 ||
       !report->normalization || report->normalization->signs!=std::vector<int>{-1}) return 8;
    const auto basis_result=worker->basis()->snapshot();const auto* basis=std::get_if<BasisSnapshot>(&basis_result);
    if(!basis || !basis->last_pivot || basis->last_pivot->coefficient!=2 ||
       std::get<AuxiliaryColumn>(basis->last_pivot->leaving).coefficients!=Vector{-1} ||
       !optimization::check_basis_snapshot(*basis,worker->last_attempt()).empty()) return 9;
    const auto coordinates=worker->basis()->coordinates(basis->reference,Vector{-6});const auto* values=std::get_if<BasisCoordinates>(&coordinates);
    if(!values || values->values!=Vector{3} || !optimization::check_basis_coordinates(*values,*basis,worker->last_attempt()).empty()) return 10;
    std::cout<<"Installed phase one client: signed coefficients, original basis and numerical evidence passed\n";
}
