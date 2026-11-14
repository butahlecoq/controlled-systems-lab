#pragma once

#include <csl/optimization/history_cost.hpp>
#include <csl/registry/provider.hpp>

namespace csl::registry { struct HistoryOptimizerPort; }

namespace csl::optimization {

struct SuppliedStart { Vector history; };
struct ColdStart {};
using HistoryOptimizationStart=std::variant<SuppliedStart,ColdStart>;

struct SuppliedReadbacks {
    Vector supplied_history;
    Vector primal_readback;
    // Solver-specific dual coordinates; backend checks their dimension against its actual solver.
    Vector supplied_duals;
    Vector dual_readback;
};
struct VerifiedSuppliedStart {
    Vector supplied_history;
    Vector primal_readback;
    Vector supplied_duals;
    Vector dual_readback;
};
struct BackendColdStartEvidence {
    std::string backend_identity;
    std::string start_policy;
    std::string readback_unavailable_reason;
};
using RawHistoryInitializationEvidence=std::variant<SuppliedReadbacks,BackendColdStartEvidence>;
using HistoryInitializationReceipt=std::variant<VerifiedSuppliedStart,BackendColdStartEvidence>;

struct HistoryOptimizationRequest {
    ProgramIdentity identity;
    synthesis::JointHistoryRelation feasible_histories;
    HistoryCostProgram source_cost;
    HistoryOptimizationStart start;
};

struct RawHistorySolve {
    Vector history;
    double reported_objective;
    RawHistoryInitializationEvidence initialization;
    std::string diagnostics;
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
