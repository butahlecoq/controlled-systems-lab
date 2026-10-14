#pragma once

#include <csl/core/values.hpp>
#include <variant>

namespace csl {
enum class Assurance { numerical, validated };
struct Unestablished {};
struct NumericalCheck { double absolute_tolerance, relative_tolerance, max_residual; ModuleId verifier; };
struct SymbolicArgument { std::string reference, assumptions; };
struct CertificateReference { std::string artifact, verifier; }; // Unchecked reference, NOT validated evidence.
using EvidenceSupport = std::variant<Unestablished, NumericalCheck, SymbolicArgument, CertificateReference>;
struct ClaimEvidence { ProblemId problem; EvidenceSupport support; };
struct FamilyEvidence { ClaimEvidence feasibility, optimality, completeness; };
} // namespace csl
