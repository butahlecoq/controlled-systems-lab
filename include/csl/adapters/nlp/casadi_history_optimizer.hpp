#pragma once

#include <csl/optimization/history_optimizer.hpp>

namespace csl::adapters::nlp {
// Native local numerical NLP over every canonical history coordinate.
registry::Registration<registry::HistoryOptimizerPort> make_casadi_history_optimizer_registration();

struct CasadiHistoryScaling {
    Vector state;
    Vector control;
};

// Scales each stage by its physical state and control units. Each scale must
// be finite and positive. Starts, objective, and outputs use canonical units.
registry::Registration<registry::HistoryOptimizerPort>
make_casadi_scaled_history_optimizer_registration(CasadiHistoryScaling);
// Enable IPOPT's MUMPS equality dependency detector with right-hand-side
// checking. This numerical policy retains the original history for validation.
registry::Registration<registry::HistoryOptimizerPort>
make_casadi_mumps_history_optimizer_registration(std::optional<CasadiHistoryScaling> = {});
} // namespace csl::adapters::nlp
