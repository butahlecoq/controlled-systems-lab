#pragma once

#include <csl/contracts.hpp>

namespace csl::synthesis::strategy_b::detail {

inline std::vector<TransformStepIdentity> expected_ts01_lineage(const ProblemId& problem) {
    const SetId feasible{"syn04-feasible:"+problem.value};
    const SetId optimal{"syn04-optimal-level:"+problem.value};
    const ModuleId strategy{"csl.synthesis.strategy-b"};
    return {
        {{"syn04-build:"+problem.value}, {problem.value}, feasible, strategy, "1"},
        {{"syn04-extract:"+problem.value}, feasible, optimal, strategy, "1"}
    };
}
inline std::vector<TransformStepIdentity> expected_ts02_lineage(const ProblemId& problem) {
    return {{{"syn04-build:"+problem.value},{problem.value},{"syn04-feasible:"+problem.value},
        {"csl.synthesis.strategy-b"},"1"}};
}
inline std::vector<TransformStepIdentity> expected_ts03_lineage(const ProblemId& problem) {
    const SetId feasible{"syn04-feasible:"+problem.value};
    const SetId optimal{"syn04-optimal-level:"+problem.value};
    const ModuleId strategy{"csl.synthesis.strategy-b"};
    return {
        {{"syn04-build:"+problem.value},{problem.value},feasible,strategy,"1"},
        {{"syn04-extract:"+problem.value},feasible,optimal,strategy,"1"}
    };
}

} // namespace csl::synthesis::strategy_b::detail
