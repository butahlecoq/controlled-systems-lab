#include <csl/geometry/legacy_btulshor.hpp>

#include <algorithm>
#include <cmath>
#include <iostream>
#include <string>
#include <vector>

namespace {

using csl::Vector;
using csl::geometry::legacy_btulshor::KpabepResult;
using csl::geometry::legacy_btulshor::Outcome;
using csl::geometry::legacy_btulshor::Stopped;

void print_result(const char* label, const Outcome<KpabepResult>& result,
                  const std::vector<std::size_t>& source_order) {
    std::cout << label << ' ';
    if (const auto* stopped = std::get_if<Stopped>(&result)) {
        std::cout << "stopped=" << stopped->message << '\n';
        return;
    }

    const auto& reduction = std::get<KpabepResult>(result);
    std::cout << "returned_original_ids=";
    for (const auto local_id : reduction.retained_indices)
        std::cout << source_order[local_id] << ',';
    std::cout << "simplex_pivot_calls=" << reduction.modif_calls
              << " pivots=" << reduction.pivots << '\n';
}

} // namespace

int main() {
    std::cout << "When tolerance removes a true hull vertex\n"
                 "Candidate-elimination hull reducer (KPABEP), driven by the simplex pivot oracle (MODIF)\n";
    const std::vector<Vector> points{
        {121.95041958088437, 61.00721298737068},
        {121.70061953288986, 61.001215386986715},
        {121.45081948489535, 60.995217786602744},
    };
    const std::vector<std::size_t> original_ids{0, 1, 2};

    print_result("original", csl::geometry::legacy_btulshor::kpabep(points), original_ids);

    for (const int exponent : {-10, -5, 0, 5, 10}) {
        const double scale = std::ldexp(1.0, exponent);
        auto scaled = points;
        for (auto& point : scaled)
            for (double& coordinate : point) coordinate *= scale;
        const auto label = std::string("scale_2^") + std::to_string(exponent);
        print_result(label.c_str(), csl::geometry::legacy_btulshor::kpabep(scaled), original_ids);
    }

    std::vector<std::size_t> permutation{0, 1, 2};
    do {
        std::vector<Vector> reordered;
        for (const auto id : permutation) reordered.push_back(points[id]);
        const auto label = std::string("order_") + std::to_string(permutation[0]) +
                           std::to_string(permutation[1]) + std::to_string(permutation[2]);
        print_result(label.c_str(), csl::geometry::legacy_btulshor::kpabep(reordered), permutation);
    } while (std::next_permutation(permutation.begin(), permutation.end()));

    const std::vector<Vector> ordinary_triangle{{0, 0}, {2, 0}, {0, 3}};
    print_result("ordinary_triangle",
                 csl::geometry::legacy_btulshor::kpabep(ordinary_triangle), {0, 1, 2});
}
