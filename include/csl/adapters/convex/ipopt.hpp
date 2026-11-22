#pragma once

#include <csl/optimization/convex_backend.hpp>
#include <csl/registry/registry.hpp>

namespace csl::adapters::convex {

struct IpoptConvexOptions {
    std::optional<std::size_t> iteration_limit;
};

// Registers csl.convex.ipopt for numerical convex QPs. Cancellation and
// deadlines are checked between Ipopt iterations.
std::variant<registry::Registration<registry::ConvexPort>, Diagnostics>
    make_ipopt_registration(IpoptConvexOptions = {});

} // namespace csl::adapters::convex
