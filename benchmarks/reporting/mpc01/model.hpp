#pragma once

#include <cstddef>
#include <cstdint>
#include <optional>
#include <string>
#include <variant>
#include <vector>

namespace csl::mpc01 {

using Vector = std::vector<double>;
using Matrix = std::vector<Vector>;

struct Box {
    Vector lower;
    Vector upper;
};

struct StageDynamics {
    Matrix a;
    Matrix b;
    Vector affine;
};

struct QuadraticTerminalCost {
    Matrix q;
    Vector linear;
    double offset{};
};

struct AffineResidualNormTerminalCost {
    Matrix w;
    Vector target;
};

using TerminalCost = std::variant<QuadraticTerminalCost,
                                  AffineResidualNormTerminalCost>;

struct StageBounds {
    std::optional<Box> state;
    std::optional<Box> control;
};

struct MpcCase {
    std::string id;
    std::string version;
    std::string source_kind;
    std::string source_ref;
    std::string canonical_input_sha256;
    std::string canonical_input_bytes;
    Vector initial_state;
    std::vector<StageDynamics> dynamics;
    std::vector<StageBounds> stages;
    TerminalCost terminal_cost;
    std::vector<std::string> state_labels;
    std::vector<std::string> state_units;
    std::vector<std::string> control_labels;
    std::vector<std::string> control_units;

    std::size_t horizon() const noexcept { return dynamics.size(); }
    std::size_t state_dimension() const noexcept { return initial_state.size(); }
    std::size_t control_dimension() const noexcept {
        return dynamics.empty() || dynamics.front().b.empty()
                   ? 0
                   : dynamics.front().b.front().size();
    }
};

struct ValidationError {
    std::string path;
    std::string message;
};

std::optional<ValidationError> validate(const MpcCase&);

enum class MathematicalOutcome {
    optimal,
    feasible,
    infeasible,
    unbounded,
    undetermined
};

enum class Termination {
    completed,
    refused,
    unsupported,
    failed,
    timed_out,
    resource_limited,
    cancelled,
    incomplete
};

enum class EvidenceStatus { verified, incorrect, inconclusive };

struct IndependentEvidence {
    EvidenceStatus feasibility{EvidenceStatus::inconclusive};
    EvidenceStatus objective{EvidenceStatus::inconclusive};
    EvidenceStatus optimality{EvidenceStatus::inconclusive};
    double max_dynamics_residual{};
    double max_state_violation{};
    double max_control_violation{};
    std::optional<double> original_objective;
    std::string checker_id;
    std::vector<std::string> limitations;
};

struct Trajectory {
    std::vector<Vector> states;
    std::vector<Vector> controls;
};

struct NativeAttempt {
    std::string method;
    Termination termination{Termination::incomplete};
    MathematicalOutcome outcome{MathematicalOutcome::undetermined};
    std::string native_status;
    std::optional<Trajectory> witness;
    Vector solver_primal;
    Vector solver_dual;
    std::optional<double> solver_objective;
    std::optional<double> original_objective;
    std::uint64_t formulation_ns{};
    std::uint64_t setup_ns{};
    std::uint64_t warm_start_ns{};
    std::uint64_t solve_ns{};
    std::uint64_t extraction_ns{};
    bool factorization_in_setup{};
    bool factorization_in_solve{};
    std::string diagnostics;
};

} // namespace csl::mpc01
