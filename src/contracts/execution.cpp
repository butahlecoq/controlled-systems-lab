#include <csl/execution/contracts.hpp>
#include "detail.hpp"
#include <algorithm>
#include <cmath>
#include <limits>
#include <set>
#include <utility>

namespace csl {
namespace {
using contracts_detail::Overloaded;
using contracts_detail::matrix_matches;
}
Diagnostics check_resources(const ResourcePolicy& r) {
    if (r.total_threads == 0 || r.outer_workers == 0 || r.threads_per_worker == 0 ||
        r.outer_workers > r.total_threads / r.threads_per_worker)
        return {{DiagnosticCode::invalid_input,"resources","Positive worker/thread counts must fit the single total thread budget"}};
    return {};
}
} // namespace csl
