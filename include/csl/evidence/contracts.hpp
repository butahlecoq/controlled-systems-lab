#pragma once

#include <csl/core/values.hpp>
#include <csl/core/diagnostics.hpp>
#include <utility>
#include <variant>
#include <vector>

namespace csl {
enum class Assurance { numerical, validated };
struct Unestablished {};
struct NumericalCheck { double absolute_tolerance, relative_tolerance, max_residual; ModuleId verifier; };
struct SymbolicArgument { std::string reference, assumptions; };
struct CertificateReference { std::string artifact, verifier; }; // Unchecked reference, NOT validated evidence.
struct LinearInfeasibilityCertificate {
    ProgramIdentity subject;
    Vector row_lower, row_upper, variable_lower, variable_upper;
    bool operator==(const LinearInfeasibilityCertificate&) const = default;
};
namespace optimization::detail { class FarkasEvidenceFactory; }
class ExactFarkasEvidence {
    LinearInfeasibilityCertificate certificate_;
    explicit ExactFarkasEvidence(LinearInfeasibilityCertificate certificate)
        :certificate_(std::move(certificate)){}
    friend class optimization::detail::FarkasEvidenceFactory;
public:
    ExactFarkasEvidence(const ExactFarkasEvidence&)=default;
    ExactFarkasEvidence(ExactFarkasEvidence&&) noexcept=default;
    ExactFarkasEvidence& operator=(const ExactFarkasEvidence&)=default;
    ExactFarkasEvidence& operator=(ExactFarkasEvidence&&) noexcept=default;
    const ProgramIdentity& subject() const noexcept { return certificate_.subject; }
    const LinearInfeasibilityCertificate& certificate() const noexcept { return certificate_; }
};
using EvidenceSupport = std::variant<Unestablished, NumericalCheck, SymbolicArgument, CertificateReference,
    ExactFarkasEvidence>;
struct ClaimEvidence { ProblemId problem; EvidenceSupport support; };
struct FamilyEvidence { ClaimEvidence feasibility, optimality, completeness; };
} // namespace csl
