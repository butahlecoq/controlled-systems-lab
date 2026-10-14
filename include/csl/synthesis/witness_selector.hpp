#pragma once

#include <csl/synthesis/contracts.hpp>
#include <csl/registry/provider.hpp>
namespace csl::synthesis::witness_selector {
inline constexpr const char* selector_id="csl.selector.ts01-directions";
// Each direction has (u0,u1) coordinates and is minimized over the source family.
// Seed is recorded only; this selector has no stochastic or uniform-sampling claim.
registry::Registration<registry::SelectorPort> make_registration(registry::PreparedProvider<registry::LPPort>);
}
