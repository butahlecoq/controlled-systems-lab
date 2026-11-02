#pragma once

#include <csl/core/values.hpp>
#include <variant>

namespace csl {
struct LinearTerminal { Vector coefficients; double offset; };
struct QuadraticTerminal { Matrix Q; Vector linear; double offset; }; // 1/2 x'Qx+q'x+c
// ||sqrt(D)(Lx-r)||_2, rectangular L. Empty weights means D=I.
// Entries in weights are finite, nonnegative binary64 coefficients.
struct ResidualNormTerminal { Matrix map; Vector target; Vector weights{}; };
using TerminalObjective = std::variant<LinearTerminal, QuadraticTerminal, ResidualNormTerminal>;
} // namespace csl
