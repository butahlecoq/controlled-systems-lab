#pragma once

#include <csl/core/values.hpp>
#include <csl/core/diagnostics.hpp>
#include <csl/evidence/contracts.hpp>
#include <optional>
#include <variant>

namespace csl {
enum class Termination { completed, cancelled, resource_limit, numerical_failure, operation_rejected, contract_rejected };
enum class MathematicalOutcome { optimal, infeasible, unbounded, infimum_not_attained, undetermined };
template<class Subject> struct OutcomeClaim {
    Subject subject;
    MathematicalOutcome value;
    EvidenceSupport support;
    std::vector<std::string> assumptions;
};
using ProgramOutcomeClaim = OutcomeClaim<ProgramIdentity>;
using SynthesisOutcomeClaim = OutcomeClaim<ProblemId>;
struct ObjectiveBound { double value; ClaimEvidence evidence; };
struct ObjectiveEvidence { std::optional<ObjectiveBound> lower, upper; };
struct ProgramBoundEvidence { ProgramIdentity subject; EvidenceSupport support; std::vector<std::string> assumptions; };
struct ProgramObjectiveBound { double value; ProgramBoundEvidence evidence; };
struct ProgramObjectiveEvidence { std::optional<ProgramObjectiveBound> lower, upper; };
struct Verifier { ModuleId id; std::string version; };
struct ResidualMeasure { double violation, scale; };
// All checks use binary64 and violation <= absolute + relative * scale.
struct ResidualContext { ProgramIdentity subject; Verifier verifier; double absolute_tolerance, relative_tolerance; };
struct PrimalResiduals { ResidualContext context; ResidualMeasure rows, variables; };
struct DualResiduals { ResidualContext context; std::optional<ResidualMeasure> stationarity, signs, complementarity; };
struct ProgramResiduals { std::optional<PrimalResiduals> primal; std::optional<DualResiduals> dual; };

enum class StopReason { cancelled, deadline_expired, resource_limit, numerical_failure };
struct OperationStopped { StopReason reason; std::string diagnostics; }; // no successful set/guarantee
struct Unsupported { Diagnostics diagnostics; };
Diagnostics check_outcome_evidence(const ProgramOutcomeClaim&, const ProgramIdentity&, Assurance);
Diagnostics check_outcome_evidence(const SynthesisOutcomeClaim&, const ProblemId&, Assurance);
} // namespace csl
