#pragma once

#include <csl/geometry/hull_reducer.hpp>

namespace csl::geometry {

// Registers a within-solve phase-I basis bulk classifier behind HullReducerPort.
// It uses the supplied LP workspace only for conservative baseline fallback;
// phase-I state is local to one reduce() call and never crosses queries.
registry::Registration<registry::HullReducerPort>
make_basis_reuse_hull_reducer_registration();

// Allows a different phase-I provider. Providers without usable basis
// diagnostics cause a conservative fallback to the generic LP hull reducer.
registry::Registration<registry::HullReducerPort>
make_basis_reuse_hull_reducer_registration(
    registry::Registration<registry::LPPort> basis_provider);

HullReductionResult reduce_hull_basis_reuse(const PointCloud&, LPWorkspace&,
                                             const ExecutionContext&);

} // namespace csl::geometry

