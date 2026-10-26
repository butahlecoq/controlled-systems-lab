#pragma once

#include "model.hpp"

#include <filesystem>
#include <variant>

namespace csl::mpc01 {

using FixtureLoad = std::variant<MpcCase, std::string>;

MpcCase make_ts01();
MpcCase make_ts02();
FixtureLoad load_double_integrator_421(const std::filesystem::path&);
FixtureLoad load_b04_reference_v1(const std::filesystem::path&);

} // namespace csl::mpc01
