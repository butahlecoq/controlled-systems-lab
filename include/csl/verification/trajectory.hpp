#pragma once
#include <csl/execution/contracts.hpp>
#include <csl/problem/validator.hpp>
#include <csl/registry/provider.hpp>

namespace csl::verification {
enum class CheckStatus { not_checked, numerical_pass, violation, invalid_input, unsupported };
struct Limits {
    std::size_t residuals{1000000};
    std::size_t membership_queries{1000};
};
// Caller-owned expectations used to independently bind a reported family.
// Problem identity and ordered joint coordinates are derived from ResolvedProblem.
struct ExpectedSynthesisBinding {
    FamilyRequest request;
    ModuleId strategy;
    std::string strategy_version;
    std::vector<TransformStepIdentity> lineage;
};
// Independent verifier policy. Its numerical tolerances and assurance are
// requested for verification only and do not alter the prepared solve claim.
struct VerificationRequest {
    NumericalPolicy numerical{1e-8,1e-8};
    Assurance assurance{Assurance::numerical};
    bool operator==(const VerificationRequest&) const = default;
};
struct TrajectoryRequest {
    Witness witness;
    Assurance assurance{Assurance::numerical};
    std::optional<SynthesisOutcomeClaim> outcome;
    // A candidate family's WitnessFeasibilityEvidence must contain this same
    // witness because the verifier independently recalculates only this field.
    std::optional<OptimalFamily> family;
    ObjectiveEvidence bounds;
    // Retained program provenance only; no unprovided program-to-problem proof is inferred.
    std::vector<ProgramObjectiveEvidence> backend_bounds;
    Limits limits{};
    // Appended to preserve positional aggregate initialization of prior fields.
    // Required when family is supplied; omitted for witness-only verification.
    std::optional<ExpectedSynthesisBinding> expected_synthesis;
    // Appended to preserve positional aggregate initialization of prior fields.
    // When omitted, legacy assurance and ExecutionContext tolerances are used.
    std::optional<VerificationRequest> verification;
};
struct NamedResidual {
    std::string field;
    ResidualMeasure measure;
    double tolerance;
    bool satisfied;
};
struct TrajectoryReport {
    ProblemId problem;
    TrajectoryRequest input;
    Verifier verifier{{"csl.trajectory.original"},"1"};
    // Compatibility view of verification.numerical in returned reports.
    NumericalPolicy numerical{};
    Termination termination{Termination::completed};
    // numerical_pass means all available caller-supplied identity bindings and
    // the original-problem, witness, coordinate and evidence bindings passed.
    // It does not establish optimality, completeness or validated evidence.
    CheckStatus bindings{CheckStatus::not_checked};
    CheckStatus feasibility{CheckStatus::not_checked};
    CheckStatus objective{CheckStatus::not_checked};
    CheckStatus optimality{CheckStatus::unsupported};
    CheckStatus completeness{CheckStatus::unsupported};
    CheckStatus validated{CheckStatus::unsupported};
    std::optional<double> recomputed_objective;
    std::vector<NamedResidual> residuals;
    std::vector<registry::LPQueryRecord> membership_queries;
    Diagnostics diagnostics;
    // Appended to preserve positional aggregate initialization of prior fields.
    VerificationRequest verification{};
};
// Synchronous borrows; the report owns the witness and supplied evidence. Known
// external inputs are prescribed by the problem, never read from witness.controls.
TrajectoryReport verify_trajectory(const problem::ResolvedProblem&, const TrajectoryRequest&,
    const ExecutionContext& = {},
    std::optional<registry::PreparedProvider<registry::LPPort>> membership_provider = std::nullopt);
} // namespace csl::verification
