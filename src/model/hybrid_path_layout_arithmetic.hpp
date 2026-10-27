#pragma once

#include <cstddef>
#include <limits>
#include <optional>

namespace csl::model::detail {

inline std::optional<std::size_t> checked_coordinate_width(std::size_t width,
    std::size_t amount) noexcept {
    if(width>std::numeric_limits<std::size_t>::max()-amount) return std::nullopt;
    return width+amount;
}

}
