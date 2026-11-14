#pragma once

#include <csl/optimization/history_optimizer.hpp>

namespace csl::adapters::nlp {
// Exact conic optimizer for affine-plus-norm history costs; request must select ColdStart.
registry::Registration<registry::HistoryOptimizerPort> make_casadi_superscs_history_optimizer_registration();
} // namespace csl::adapters::nlp
