#pragma once

#include <string_view>

namespace csl::model::catalogue {

struct Coordinate {
    std::string_view name, unit;
};

struct Source {
    std::string_view title, sha256, locator, qualification;
};

} // namespace csl::model::catalogue
