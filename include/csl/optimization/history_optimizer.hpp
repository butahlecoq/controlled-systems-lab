#pragma once

#include <csl/optimization/history_cost.hpp>
#include <csl/registry/provider.hpp>

namespace csl::registry { struct HistoryOptimizerPort; }

namespace csl::optimization {

struct HistoryOptimizationRequest {
    ProgramIdentity identity;
    synthesis::JointHistoryRelation feasible_histories;
    HistoryCostProgram source_cost;
    Vector initial_history;
};

struct RawHistorySolve {
    Vector history;
    double reported_objective;
    Vector supplied_initial_history;
    Vector initial_primal_readback;
    // Solver-specific dual coordinates; backend checks their dimension against its actual NLP.
    Vector supplied_initial_duals;
    Vector initial_dual_readback;
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
    Vector supplied_initial_history;
    Vector initial_primal_readback;
    Vector supplied_initial_duals;
    Vector initial_dual_readback;
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
