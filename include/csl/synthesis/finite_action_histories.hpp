#pragma once

#include <csl/problem/contracts.hpp>
#include <csl/core/diagnostics.hpp>

#include <cstddef>
#include <variant>
#include <vector>

namespace csl::synthesis {

// Catalogue indices, not action values, identify a finite branch. Duplicate
// rows therefore remain distinct histories.
struct FiniteActionHistory {
    std::vector<std::size_t> catalogue_indices;
    bool operator==(const FiniteActionHistory&) const = default;
};

struct FiniteActionHistoryPrefix {
    std::vector<FiniteActionHistory> histories;
    bool complete{};
};

// Deterministically emits lexicographic catalogue-index histories in bounded
// prefixes. A prefix is never evidence that the remaining histories are
// infeasible or suboptimal; only complete() records full inventory traversal.
class FiniteActionHistoryCursor {
    std::size_t catalogue_size_{};
    std::vector<std::size_t> choices_;
    bool complete_{};

    FiniteActionHistoryCursor(std::size_t catalogue_size,std::size_t horizon);
    void advance() noexcept;

public:
    static std::variant<FiniteActionHistoryCursor,Diagnostics> prepare(
        const FiniteDomain&,std::size_t horizon);

    bool complete() const noexcept { return complete_; }
    FiniteActionHistoryPrefix take_prefix(std::size_t max_histories);
};

} // namespace csl::synthesis
