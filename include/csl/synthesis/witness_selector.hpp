#pragma once

#include <csl/synthesis/contracts.hpp>
#include <csl/registry/provider.hpp>
namespace csl::synthesis::witness_selector {
inline constexpr const char *selector_id = "csl.selector.ts01-directions";
// Each direction has T finite control coordinates (u0,...,u(T-1)) and is
// minimized over an admitted registry-verified scalar complete H family.
// Histories retain canonical state x0,...,xT and control u0,...,u(T-1) order.
// The original objective comes from the verified coincident optimum bounds;
// the LP direction objective is a separate query and does not replace it.
// Seed is recorded only; this selector has no stochastic or uniform-sampling claim.
registry::Registration<registry::SelectorPort>
    make_registration(registry::PreparedProvider<registry::LPPort>);
}
