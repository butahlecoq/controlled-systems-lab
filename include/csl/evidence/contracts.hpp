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
class LinearProgram;
namespace optimization { class FarkasEvidenceFactory; }
class ExactFarkasEvidence {
    LinearInfeasibilityCertificate certificate_;
    explicit ExactFarkasEvidence(LinearInfeasibilityCertificate certificate)
        :certificate_(std::move(certificate)){}
    friend class optimization::FarkasEvidenceFactory;
public:
    ExactFarkasEvidence(const ExactFarkasEvidence&)=default;
    ExactFarkasEvidence(ExactFarkasEvidence&&) noexcept=default;
    ExactFarkasEvidence& operator=(const ExactFarkasEvidence&)=default;
    ExactFarkasEvidence& operator=(ExactFarkasEvidence&&) noexcept=default;
    const ProgramIdentity& subject() const noexcept { return certificate_.subject; }
    const LinearInfeasibilityCertificate& certificate() const noexcept { return certificate_; }
};
namespace optimization {
// This complete, non-constructible type reserves the only construction seam.
// Its private factory is callable only by the exact LP verifier below.
class FarkasEvidenceFactory final {
    FarkasEvidenceFactory() = delete;
    static ExactFarkasEvidence create(LinearInfeasibilityCertificate certificate);
    friend std::variant<ExactFarkasEvidence,Diagnostics> verify_linear_infeasibility_certificate(
        const ::csl::LinearProgram&,const LinearInfeasibilityCertificate&);
};
}
using EvidenceSupport = std::variant<Unestablished, NumericalCheck, SymbolicArgument, CertificateReference,
    ExactFarkasEvidence>;
struct ClaimEvidence { ProblemId problem; EvidenceSupport support; };
struct FamilyEvidence { ClaimEvidence feasibility, optimality, completeness; };
} // namespace csl
