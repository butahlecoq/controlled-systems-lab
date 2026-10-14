#pragma once

#include <csl/core/values.hpp>
#include <variant>

namespace csl {
struct LinearTerminal { Vector coefficients; double offset; };
struct QuadraticTerminal { Matrix Q; Vector linear; double offset; }; // 1/2 x'Qx+q'x+c
struct ResidualNormTerminal { Matrix map; Vector target; }; // ||Lx-r||_2, rectangular L
using TerminalObjective = std::variant<LinearTerminal, QuadraticTerminal, ResidualNormTerminal>;
} // namespace csl
