#pragma once

#include <csl/model/contracts.hpp>
#include <csl/sets/generator_sets.hpp>

#include <span>
#include <string_view>

namespace csl::model::catalogue {

struct Coordinate {
    std::string_view name, unit;
};

struct Source {
    std::string_view title, sha256, locator, qualification;
};

struct CaseInfo {
    std::string_view id, title;
    std::span<const Coordinate> states, controls;
    std::size_t transitions;
    std::string_view time_unit;
    Source source;
    // Exercised public paths, not an admission claim for control algorithms.
    std::span<const std::string_view> native_operations;
};

// Forward reachability data only: no objective, terminal target or second player.
// Times are integer stage indices unless a case explicitly declares physical time.
struct DiscreteReachabilityCase {
    CaseInfo info;
    SystemModel model;
    Vector time_grid;
    sets::GeneratorSet initial;
    std::vector<sets::GeneratorSet> controls;
};

std::span<const CaseInfo> discrete_reachability_cases();
std::variant<DiscreteReachabilityCase, Diagnostics>
make_discrete_reachability_case(std::string_view id);

} // namespace csl::model::catalogue
