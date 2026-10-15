#pragma once

#include <csl/evidence/contracts.hpp>
#include <csl/optimization/linear_program.hpp>

namespace csl::optimization {
// Returns sealed evidence only when the exact dyadic Farkas identities hold
// for this immutable LP. No solver or floating-point tolerance is involved.
std::variant<ExactFarkasEvidence,Diagnostics> verify_linear_infeasibility_certificate(
    const LinearProgram&,const LinearInfeasibilityCertificate&);
} // namespace csl::optimization
