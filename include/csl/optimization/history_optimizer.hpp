#pragma once

#include <csl/optimization/history_cost.hpp>
#include <csl/optimization/history_domain.hpp>
#include <csl/registry/provider.hpp>

namespace csl::registry { struct HistoryOptimizerPort; }

namespace csl::optimization {

struct SuppliedStart {
    Vector history;
    std::vector<HistoryMembershipWitness> membership_witnesses{};
};
struct ColdStart {};
using HistoryOptimizationStart = std::variant<SuppliedStart, ColdStart>;

struct SuppliedReadbacks {
    Vector supplied_history;
    Vector primal_readback;
    // Solver-specific dual coordinates; backend checks their dimension against its actual solver.
    Vector supplied_duals;
    Vector dual_readback;
    std::vector<HistoryMembershipWitness> supplied_membership_witnesses{};
    std::vector<HistoryMembershipWitness> membership_witness_readback{};
};
struct VerifiedSuppliedStart {
    Vector supplied_history;
    Vector primal_readback;
    Vector supplied_duals;
    Vector dual_readback;
    std::vector<HistoryMembershipWitness> supplied_membership_witnesses{};
    std::vector<HistoryMembershipWitness> membership_witness_readback{};
};
struct BackendColdStartEvidence {
    std::string backend_identity;
    std::string start_policy;
    std::string readback_unavailable_reason;
};
using RawHistoryInitializationEvidence = std::variant<SuppliedReadbacks, BackendColdStartEvidence>;
using HistoryInitializationReceipt = std::variant<VerifiedSuppliedStart, BackendColdStartEvidence>;

struct HistoryOptimizationRequest {
    ProgramIdentity identity;
    HistoryDomain domain;
    HistoryCostProgram source_cost;
    HistoryOptimizationStart start;
};

// Authored, immutable inputs needed to optimize a recovered full history.
// The resolved problem supplies the terminal objective and binds the task;
// these fields retain the separately authored running cost and selected set
// memberships without reducing the original feasible-history relation.
struct StrategyHistoryOptimizationProfile {
    ProgramId program;
    RunningControlCost running_cost;
    std::size_t absolute_stage_offset{};
    std::string state_frame;
    std::vector<HistoryMembership> memberships;
    HistoryOptimizationStart start{ColdStart{}};
};

using HistoryOptimizationRequestCompilation =
    std::variant<HistoryOptimizationRequest, Diagnostics, OperationStopped>;

HistoryOptimizationRequestCompilation
compile_strategy_history_optimization_request(const problem::ResolvedProblem &,
                                              const synthesis::JointHistoryRelation &,
                                              const StrategyHistoryOptimizationProfile &);

struct RawHistorySolve {
    Vector history;
    double reported_objective;
    RawHistoryInitializationEvidence initialization;
    std::string diagnostics;
    std::vector<HistoryMembershipWitness> membership_witnesses{};
};
using RawHistorySolveOutcome=std::variant<RawHistorySolve,Diagnostic,OperationStopped>;

class HistoryOptimizerWorkspace:public ExclusiveWorkspace {
    friend struct registry::HistoryOptimizerPort;
protected:
    virtual RawHistorySolveOutcome solve_candidate(const HistoryOptimizationRequest&,
        const ExecutionContext&)=0;
};

struct HistoryOptimizationResult {
    ProgramIdentity identity;
    Vector history;
    HistoryCostEvaluation source_cost;
    double reported_objective;
    double maximum_history_violation;
    HistoryInitializationReceipt initialization;
    std::string diagnostics;
    std::vector<HistoryMembershipWitness> membership_witnesses{};
};
using HistoryOptimizationOutcome=std::variant<HistoryOptimizationResult,Diagnostic,OperationStopped>;

Diagnostics check_history_optimization_request(const HistoryOptimizationRequest&);

} // namespace csl::optimization

namespace csl::registry {
struct HistoryOptimizerPort {
    using Request=optimization::HistoryOptimizationRequest;
    using Workspace=optimization::HistoryOptimizerWorkspace;
    static constexpr const char* name="whole-history-optimizer";
    static Request snapshot(const Request& request) { return request; }
    static optimization::HistoryOptimizationOutcome run(Workspace& workspace,const Request& request,
        const ExecutionContext& context);
};
} // namespace csl::registry
