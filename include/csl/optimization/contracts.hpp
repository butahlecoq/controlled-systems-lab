#pragma once

#include <csl/core/outcomes.hpp>
#include <csl/execution/contracts.hpp>
#include <chrono>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <span>
#include <memory>
#include <optional>
#include <stop_token>
#include <string>
#include <variant>
#include <utility>
#include <vector>

namespace csl {
struct LinearProgramInput {
    ProgramIdentity identity;
    Vector objective; double offset;
    SparseMatrix constraints;
    std::vector<Interval> variables, rows;
};
namespace numeric { class MatrixView; class VectorView; }
namespace optimization { struct ProgramAccess; }
class LinearProgram {
public:
    LinearProgram(const LinearProgram&) noexcept = default;
    LinearProgram& operator=(const LinearProgram&) noexcept = default;
    const ProgramIdentity& identity() const noexcept;
    const numeric::VectorView& objective() const noexcept;
    double offset() const noexcept;
    const numeric::MatrixView& constraints() const noexcept;
    std::span<const Interval> variables() const noexcept;
    std::span<const Interval> rows() const noexcept;
private:
    struct Storage;
    std::shared_ptr<const Storage> storage_;
    explicit LinearProgram(std::shared_ptr<const Storage> storage) : storage_(std::move(storage)) {}
    friend struct optimization::ProgramAccess;
};
namespace optimization { class Objective; class NormSquareReformulation; struct ConvexAccess; }
class QuadraticProgram {
public:
    QuadraticProgram(const QuadraticProgram&) noexcept = default;
    QuadraticProgram& operator=(const QuadraticProgram&) noexcept = default;
    const ProgramIdentity& identity() const noexcept;
    const optimization::Objective& objective() const noexcept;
    const numeric::MatrixView& hessian() const noexcept;
    const numeric::MatrixView& constraints() const noexcept;
    std::span<const Interval> variables() const noexcept;
    std::span<const Interval> rows() const noexcept;
private:
    struct Storage;
    std::shared_ptr<const Storage> storage_;
    explicit QuadraticProgram(std::shared_ptr<const Storage> storage) : storage_(std::move(storage)) {}
    friend struct optimization::ConvexAccess;
};
class ConvexProgram {
public:
    ConvexProgram(const ConvexProgram&) noexcept = default;
    ConvexProgram& operator=(const ConvexProgram&) noexcept = default;
    const ProgramIdentity& identity() const noexcept;
    const optimization::Objective& original_objective() const noexcept;
    const QuadraticProgram& quadratic_program() const noexcept;
    const optimization::NormSquareReformulation* reformulation() const noexcept;
private:
    struct Storage;
    std::shared_ptr<const Storage> storage_;
    explicit ConvexProgram(std::shared_ptr<const Storage> storage) : storage_(std::move(storage)) {}
    friend struct optimization::ConvexAccess;
};
struct ProgramResult {
    Termination termination;
    ProgramOutcomeClaim outcome;
    std::optional<Vector> primal;
    ProgramObjectiveEvidence objective;
    std::string raw_diagnostics;
    ProgramResiduals residuals{};
};
using ProgramOutcome = std::variant<ProgramResult, Unsupported>;
struct BackendCapabilities { ModuleId id; std::string version; bool linear, convex_quadratic, basis_diagnostics; };
class WorkspaceIdentity {
    struct Token {};
    std::shared_ptr<const Token> token_;
    WorkspaceIdentity() : token_(std::make_shared<const Token>()) {}
    friend class LPWorkspace;
    friend class ConvexWorkspace;
public:
    bool operator==(const WorkspaceIdentity&) const = default;
};
class SolveStamp {
    LinearProgram program_;
    WorkspaceIdentity workspace_;
    std::uint64_t attempt_;
    SolveStamp(const LinearProgram& p, const WorkspaceIdentity& w, std::uint64_t a) noexcept
        : program_(p), workspace_(w), attempt_(a) {}
    friend class LPWorkspace;
public:
    const LinearProgram& program() const noexcept { return program_; }
    const WorkspaceIdentity& workspace() const noexcept { return workspace_; }
    std::uint64_t attempt() const noexcept { return attempt_; }
    bool operator==(const SolveStamp& other) const noexcept {
        return workspace_ == other.workspace_ && attempt_ == other.attempt_;
    }
};
enum class SolveAttemptState { running, returned_result, unsupported, exception };
struct SolveAttempt { SolveStamp stamp; SolveAttemptState state; };
class LPWorkspace : public ExclusiveWorkspace {
    WorkspaceIdentity identity_;
    std::uint64_t sequence_{};
    std::optional<SolveAttempt> attempt_;
public:
    ProgramOutcome solve(const LinearProgram&, const ExecutionContext&);
    const WorkspaceIdentity& workspace_identity() const noexcept { return identity_; }
    const std::optional<SolveAttempt>& last_attempt() const noexcept { return attempt_; }
protected:
    virtual ProgramOutcome do_solve(const LinearProgram&, const ExecutionContext&) = 0;
};
class LPBackend {
public:
    virtual ~LPBackend() = default;
    virtual BackendCapabilities capabilities() const = 0;
    virtual std::unique_ptr<LPWorkspace> make_workspace() const = 0;
};
class ConvexSolveStamp {
    ConvexProgram program_;
    WorkspaceIdentity workspace_;
    std::uint64_t attempt_;
    ConvexSolveStamp(const ConvexProgram& p, const WorkspaceIdentity& w, std::uint64_t a) noexcept
        : program_(p), workspace_(w), attempt_(a) {}
    friend class ConvexWorkspace;
public:
    const ConvexProgram& program() const noexcept { return program_; }
    const WorkspaceIdentity& workspace() const noexcept { return workspace_; }
    std::uint64_t attempt() const noexcept { return attempt_; }
    bool operator==(const ConvexSolveStamp& other) const noexcept {
        return workspace_ == other.workspace_ && attempt_ == other.attempt_;
    }
};
struct ConvexSolveAttempt { ConvexSolveStamp stamp; SolveAttemptState state; };
class ConvexWorkspace : public ExclusiveWorkspace {
    WorkspaceIdentity identity_;
    std::uint64_t sequence_{};
    std::optional<ConvexSolveAttempt> attempt_;
public:
    ProgramOutcome solve(const ConvexProgram&, const ExecutionContext&);
    const WorkspaceIdentity& workspace_identity() const noexcept { return identity_; }
    const std::optional<ConvexSolveAttempt>& last_attempt() const noexcept { return attempt_; }
protected:
    virtual ProgramOutcome do_solve(const ConvexProgram&, const ExecutionContext&) = 0;
};
class ConvexBackend {
public:
    virtual ~ConvexBackend() = default;
    virtual BackendCapabilities capabilities() const = 0;
    virtual std::unique_ptr<ConvexWorkspace> make_workspace() const = 0;
};
// Basis is an optional separate port, never a requirement of LPWorkspace.
struct StructuralColumn { std::size_t index; bool operator==(const StructuralColumn&) const = default; };
struct RowActivityColumn { std::size_t index; bool operator==(const RowActivityColumn&) const = default; };
struct AuxiliaryColumn { std::size_t id; Vector coefficients; bool operator==(const AuxiliaryColumn&) const = default; };
using BasisColumn = std::variant<StructuralColumn, RowActivityColumn, AuxiliaryColumn>;
struct BasisReference { SolveStamp solve; std::uint64_t iteration; bool operator==(const BasisReference&) const = default; };
struct PivotRecord {
    BasisReference before, after;
    std::vector<BasisColumn> before_basis;
    BasisColumn entering, leaving;
    std::size_t position;
    double coefficient; // signed (B_before^-1 * entering)[position]
};
struct BasisSnapshot { BasisReference reference; std::vector<BasisColumn> columns; std::optional<PivotRecord> last_pivot; };
struct BasisCoordinates { BasisReference reference; Vector values; };
enum class BasisUnavailableReason { unsupported, not_solved, unavailable_result, stale_reference };
struct BasisUnavailable { BasisUnavailableReason reason; std::string explanation; };
struct BasisCapabilities { bool snapshot, pivots, coordinates; };
using BasisSnapshotResult = std::variant<BasisSnapshot, BasisUnavailable>;
using BasisCoordinatesResult = std::variant<BasisCoordinates, BasisUnavailable, Diagnostics>;
class BasisDiagnostics {
public:
    virtual ~BasisDiagnostics() = default;
    virtual BasisCapabilities capabilities() const = 0;
    virtual BasisSnapshotResult snapshot() const = 0;
    virtual BasisCoordinatesResult coordinates(const BasisReference&, std::span<const double>) const {
        return BasisUnavailable{BasisUnavailableReason::unsupported, "basis coordinates unavailable"};
    }
    virtual std::string describe_basis() const { return {}; }
};
} // namespace csl
