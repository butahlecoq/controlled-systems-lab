#include <csl/geometry/legacy_btulshor.hpp>

#include <iostream>
#include <set>
#include <utility>
#include <vector>
#include <variant>

namespace legacy = csl::geometry::legacy_btulshor;

int main() {
    const legacy::ModifRequest modif_request{
        .a = {3, 1, {1, 2, -1}}, .x = {1, 2, -1}, .initial_status = 1};
    const auto modif_output = legacy::modif(modif_request);
    if (!std::holds_alternative<legacy::ModifResult>(modif_output)) return 1;
    const auto& modif = std::get<legacy::ModifResult>(modif_output);
    if (modif.original_status != 1 || modif.x != csl::Vector{1, 4, 0} ||
        modif.basis != std::vector<int>{1, -2, -3}) return 2;

    const std::vector<csl::Vector> square_with_center{
        {0, 0}, {1, 0}, {1, 1}, {0, 1}, {0.5, 0.5}};
    auto source_modif = legacy::source_modif_port();
    std::size_t modif_calls = 0;
    legacy::ModifPort counted_modif{
        "installed.counted-source-modif",
        [&](const legacy::ModifRequest& request, const legacy::Limits& limits) {
            ++modif_calls;
            return source_modif.run(request, limits);
        }};
    const auto kpabep_output = legacy::kpabep(square_with_center, counted_modif);
    if (!std::holds_alternative<legacy::KpabepResult>(kpabep_output)) return 3;
    const auto& kpabep = std::get<legacy::KpabepResult>(kpabep_output);
    if (kpabep.points.size() != 4 || kpabep.retained_indices.size() != 4 ||
        kpabep.modif_calls != modif_calls || modif_calls == 0) return 4;
    for (std::size_t i = 0; i < kpabep.points.size(); ++i) {
        const auto source_index = kpabep.retained_indices[i];
        if (source_index >= square_with_center.size() ||
            kpabep.points[i] != square_with_center[source_index] || source_index == 4) return 5;
    }

    if (std::set<std::size_t>(kpabep.retained_indices.begin(), kpabep.retained_indices.end()) !=
        std::set<std::size_t>{0, 1, 2, 3}) return 10;

    const legacy::ReachRequest reach_request{
        .a = {2, 2, {1, 0, 0, 1}}, .b = {2, 1, {1, 2}},
        .initial_points = {{0, 0}, {1, 0}}, .control_points = {{0}, {1}}};
    const auto reach_output = legacy::reach(
        reach_request, legacy::source_kpabep_port(), legacy::source_modif_port());
    if (!std::holds_alternative<legacy::ReachResult>(reach_output)) return 6;
    const auto& reach = std::get<legacy::ReachResult>(reach_output);
    if (reach.points.size() != 4 || reach.source_vertices.size() != reach.points.size()) return 7;
    std::set<std::pair<double, double>> reached;
    for (std::size_t i = 0; i < reach.points.size(); ++i) {
        reached.emplace(reach.points[i][0], reach.points[i][1]);
        const auto source = reach.source_vertices[i];
        if (source.initial_point_index >= reach_request.initial_points.size() ||
            source.control_point_index >= reach_request.control_points.size()) return 8;
        const auto& x = reach_request.initial_points[source.initial_point_index];
        const double u = reach_request.control_points[source.control_point_index][0];
        const csl::Vector reconstructed{x[0] + u, x[1] + 2.0 * u};
        if (reach.points[i] != reconstructed) return 9;
    }

    if (reached != std::set<std::pair<double, double>>{{0, 0}, {1, 0}, {1, 2}, {2, 2}}) return 11;

    std::cout << "Installed legacy BTULSHOR client: MODIF, KPABEP port and REACH source pairs passed\n";
    return 0;
}
