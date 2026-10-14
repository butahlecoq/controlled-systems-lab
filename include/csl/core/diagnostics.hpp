#pragma once

#include <string>
#include <vector>

namespace csl {
enum class DiagnosticCode { invalid_input, unsupported, evidence_mismatch, invalid_claim };
struct Diagnostic { DiagnosticCode code; std::string field, explanation; };
using Diagnostics = std::vector<Diagnostic>;
} // namespace csl
