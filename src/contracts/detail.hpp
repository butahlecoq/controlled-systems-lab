#pragma once
#include <csl/core/values.hpp>
#include <limits>
namespace csl::contracts_detail {
template<class... Visitors> struct Overloaded : Visitors... { using Visitors::operator()...; };
inline bool matrix_matches(const Matrix& m, std::size_t rows, std::size_t cols) {
    return m.rows == rows && m.cols == cols &&
        (cols == 0 || rows <= std::numeric_limits<std::size_t>::max() / cols) &&
        m.values.size() == rows * cols;
}
} // namespace csl::contracts_detail
