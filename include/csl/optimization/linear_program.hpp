#pragma once
#include <csl/numeric/data.hpp>
namespace csl::optimization {
template<class T> using Result = std::variant<T, Diagnostics>;
Result<LinearProgram> make_linear_program(const LinearProgramInput&);
struct PrimalEvaluation { double objective; PrimalResiduals residuals; };
Result<PrimalEvaluation> evaluate_primal(const LinearProgram&, std::span<const double>, NumericalPolicy, const Verifier&);
} // namespace csl::optimization
