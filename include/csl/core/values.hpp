#pragma once

#include <cstddef>
#include <optional>
#include <string>
#include <vector>

namespace csl {
struct ProblemId { std::string value; bool operator==(const ProblemId&) const = default; };
struct ProgramId { std::string value; bool operator==(const ProgramId&) const = default; };
struct ProgramIdentity { ProblemId problem; ProgramId program; bool operator==(const ProgramIdentity&) const = default; };
struct SetId { std::string value; bool operator==(const SetId&) const = default; };
struct RequestId { std::string value; bool operator==(const RequestId&) const = default; };
struct ReferenceId { std::string value; bool operator==(const ReferenceId&) const = default; };
struct ModuleId { std::string value; bool operator==(const ModuleId&) const = default; };
struct RepresentationId { std::string value; bool operator==(const RepresentationId&) const = default; };
struct StageIndex { std::size_t value; };
struct Dimensions { std::size_t state, control, external; bool operator==(const Dimensions&) const = default; };
using Vector = std::vector<double>;
// Owning row-major buffer. Empty rows/columns are legal; shape validated at entry.
struct Matrix { std::size_t rows, cols; Vector values; };
struct SparseMatrix {
    std::size_t rows, cols;
    std::vector<std::size_t> row_offsets, column_indices; // CSR, sorted columns
    Vector values;
};
struct Interval { std::optional<double> lower, upper; }; // null means infinite
} // namespace csl
