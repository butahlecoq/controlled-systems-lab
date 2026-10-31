#pragma once

#include <cstddef>
#include <vector>

namespace csl::optimization::detail {

inline std::vector<std::size_t> action_plan_indices(std::size_t plan,
    std::size_t actions, std::size_t horizon) {
    std::vector<std::size_t> result(horizon);
    for(std::size_t stage = horizon; stage > 0; --stage) {
        result[stage - 1] = plan % actions;
        plan /= actions;
    }
    return result;
}

} // namespace csl::optimization::detail
