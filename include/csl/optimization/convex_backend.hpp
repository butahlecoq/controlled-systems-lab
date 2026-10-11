#pragma once
#include <csl/optimization/objectives.hpp>
#include <csl/optimization/lp_backend.hpp>

namespace csl::optimization {
struct ConvexProgramInput {
    ProgramIdentity identity;
    TerminalObjective objective;
    SparseMatrix constraints;
    std::vector<Interval> variables, rows;
    std::optional<ProgramId> squared_program;
};
template<class T> using ConvexDataResult = std::variant<T, Diagnostics, OperationStopped>;
ConvexDataResult<ConvexProgram> make_convex_program(const ConvexProgramInput&, ObjectivePolicy = {});
struct ConvexPrimalEvaluation {
    double original_objective, solver_objective;
    PrimalResiduals residuals;
};
ConvexDataResult<ConvexPrimalEvaluation> evaluate_primal(const ConvexProgram&, std::span<const double>, NumericalPolicy, const Verifier&);
ConvexDataResult<DualResiduals> evaluate_dual(const ConvexProgram&, std::span<const double>, const DualMultipliers&, NumericalPolicy, const Verifier&);
Diagnostics check_program_result(const ProgramResult&, const ConvexProgram&, Assurance);
} // namespace csl::optimization
