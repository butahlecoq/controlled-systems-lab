#pragma once
#include <csl/optimization/lp_backend.hpp>
#include <csl/registry/registry.hpp>

namespace csl::optimization::phase_one {
LPDataResult<LinearProgram> make_program(ProgramIdentity, const SparseMatrix&, std::span<const double>);
struct StructuralVariable { std::size_t column; };
struct ArtificialVariable { std::size_t row; };
using Variable = std::variant<StructuralVariable,ArtificialVariable>;
struct PivotEvent {
    std::uint64_t iteration;
    Variable entering, leaving;
    std::size_t leaving_position;
    double coefficient, step, auxiliary_before, auxiliary_after;
};
struct Options {
    std::uint64_t pivot_limit{10000};
    std::size_t dense_entry_limit{1048576}, trace_limit{128};
    double pivot_relative_tolerance{1e-12};
    // Synchronous post-commit borrow; may be copied. No workspace reentrancy.
    // Captured owners/synchronization are the caller's responsibility.
    std::function<void(const PivotEvent&)> pivot_observer{};
};
using RegistrationResult = std::variant<registry::Registration<registry::LPPort>,Diagnostics>;
RegistrationResult make_registration(Options = {});
struct Normalization { std::vector<int> signs; };
struct AuxiliaryState {
    Vector artificial;
    double value;
    ResidualMeasure equations, nonnegativity;
    std::optional<ResidualMeasure> dual_equations;
    std::optional<double> minimum_reduced_cost;
};
enum class Reason {
    feasible, positive_auxiliary_optimum, cancelled, deadline, pivot_limit,
    capacity, arithmetic, ill_conditioned_basis, uncertain_pricing,
    uncertain_pivot, invalid_basic_point
};
struct Snapshot {
    SolveStamp solve;
    Termination termination;
    Reason reason;
    std::uint64_t pivots, degenerate_pivots, factorizations, pricing_passes;
    std::optional<Normalization> normalization;
    std::optional<AuxiliaryState> auxiliary;
    std::vector<PivotEvent> trace;
    bool trace_truncated;
    std::size_t accounted_workspace_bytes;
};
using SnapshotResult = std::variant<Snapshot,BasisUnavailable>;
class DiagnosticsView : public BasisDiagnostics {
public:
    virtual SnapshotResult phase_one_snapshot() const = 0;
};
} // namespace csl::optimization::phase_one
