#pragma once

#include <csl/optimization/history_optimizer.hpp>

namespace csl::adapters::nlp {
// Native local numerical NLP over every canonical history coordinate.
registry::Registration<registry::HistoryOptimizerPort> make_casadi_history_optimizer_registration();
} // namespace csl::adapters::nlp
