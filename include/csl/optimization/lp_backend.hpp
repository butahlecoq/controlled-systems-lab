#pragma once
#include <csl/optimization/linear_program.hpp>
namespace csl::optimization {
Diagnostics check_program_result(const ProgramResult&, const LinearProgram&, Assurance);
struct DualMultipliers { Vector row_lower, row_upper, variable_lower, variable_upper; };
// Numerical Lagrangian evaluation, never a certified objective bound.
struct DualEvaluation { double lagrangian_constant; DualResiduals residuals; };
Result<DualEvaluation> evaluate_dual(const LinearProgram&, const DualMultipliers&, NumericalPolicy, const Verifier&);
Diagnostics check_basis_snapshot(const BasisSnapshot&, const std::optional<SolveAttempt>& expected_current_attempt);
Diagnostics check_basis_coordinates(const BasisCoordinates&, const BasisSnapshot&, const std::optional<SolveAttempt>& expected_current_attempt);
} // namespace csl::optimization
