#pragma once

#include <csl/optimization/contracts.hpp>
#include <csl/numeric/data.hpp>
namespace csl::optimization {
template<class T> using LPDataResult = std::variant<T, Diagnostics>;
LPDataResult<LinearProgram> make_linear_program(const LinearProgramInput&);
struct PrimalEvaluation { double objective; PrimalResiduals residuals; };
LPDataResult<PrimalEvaluation> evaluate_primal(const LinearProgram&, std::span<const double>, NumericalPolicy, const Verifier&);
} // namespace csl::optimization
