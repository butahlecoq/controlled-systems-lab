#pragma once

#include <nlohmann/json_fwd.hpp>

#include <string_view>

namespace csl::mpc01 {

nlohmann::json environment_manifest(std::string_view executable, bool hpipm_first);

} // namespace csl::mpc01
