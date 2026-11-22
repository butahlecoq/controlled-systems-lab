#pragma once

#include <csl/optimization/finite_action_minimax.hpp>

#include <algorithm>
#include <cstddef>
#include <limits>
#include <vector>

namespace csl::optimization::detail {

inline std::vector<std::size_t> action_plan_indices(std::size_t plan, std::size_t actions,
                                                    std::size_t horizon) {
    std::vector<std::size_t> result(horizon);
    for (std::size_t stage = horizon; stage > 0; --stage) {
        result[stage - 1] = plan % actions;
        plan /= actions;
    }
    return result;
}

inline std::size_t full_action_plan_count(const FiniteActionMinimaxRequest &request) {
    const auto horizon = request.system.horizon();
    const auto actions = request.actions.catalogue.size();
    if (horizon != 0 && actions == 0)
        return 0;
    std::size_t count = 1;
    for (std::size_t stage = 0; stage < horizon; ++stage) {
        if (count > std::numeric_limits<std::size_t>::max() / actions)
            return std::numeric_limits<std::size_t>::max();
        count *= actions;
    }
    return count;
}

inline std::size_t selected_plan_count(const FiniteActionMinimaxRequest &request) {
    return request.candidate_action_indices ? request.candidate_action_indices->size()
                                            : full_action_plan_count(request);
}

inline std::vector<std::size_t> selected_plan_indices(const FiniteActionMinimaxRequest &request,
                                                      std::size_t plan) {
    if (request.candidate_action_indices)
        return request.candidate_action_indices->at(plan);
    return action_plan_indices(plan, request.actions.catalogue.size(), request.system.horizon());
}

inline bool valid_candidate_action_indices(const FiniteActionMinimaxRequest &request) {
    if (!request.candidate_action_indices)
        return true;
    if (request.candidate_action_indices->empty())
        return false;
    const auto horizon = request.system.horizon();
    const auto actions = request.actions.catalogue.size();
    std::vector<std::vector<std::size_t>> seen;
    seen.reserve(request.candidate_action_indices->size());
    for (const auto &plan : *request.candidate_action_indices) {
        if (plan.size() != horizon)
            return false;
        for (const auto index : plan)
            if (index >= actions)
                return false;
        if (std::find(seen.begin(), seen.end(), plan) != seen.end())
            return false;
        seen.push_back(plan);
    }
    return true;
}

} // namespace csl::optimization::detail
