#include <csl/geometry/quickhull_2d.hpp>

#include <array>
#include <chrono>
#include <cstddef>
#include <cstdint>
#include <iostream>
#include <stdexcept>
#include <string>
#include <variant>
#include <vector>

namespace {
using Clock = std::chrono::steady_clock;
using Cloud = std::vector<csl::Vector>;

struct Case {
    const char* name;
    Cloud points;
    std::vector<std::size_t> expected;
};

const std::array<Case, 3> cases{{
    {"square_duplicates", {{0, 0}, {1, 0}, {1, 1}, {0, 1}, {0.5, 0.5}, {0, 0}, {1, 0}}, {0, 1, 2, 3}},
    {"collinear_endpoints", {{2, 2}, {0, 0}, {1, 1}, {3, 3}, {2, 2}}, {1, 3}},
    {"skinny_triangle", {{0, 0}, {1, 0}, {1, 0x1p-50}, {0.5, 0x1p-52}}, {0, 1, 2}},
}};

std::string indices(const std::vector<std::size_t>& values) {
    std::string result;
    for (const auto value : values) {
        if (!result.empty()) result += ':';
        result += std::to_string(value);
    }
    return result;
}

int positive(const char* text, int minimum, int maximum) {
    const auto value = std::stoi(text);
    if (value < minimum || value > maximum || std::to_string(value) != text) throw std::invalid_argument("invalid positive integer");
    return value;
}

void run(const Case& item, int repetition, bool warmup, int calls) {
    std::uint64_t observed = 0;
    bool passed = true;
    std::vector<std::size_t> final_indices;
    const auto start = Clock::now();
    for (int call = 0; call < calls; ++call) {
        auto result = csl::geometry::quickhull_2d(item.points);
        auto* hull = std::get_if<csl::geometry::QuickHull2D>(&result);
        if (!hull) { passed = false; break; }
        final_indices = hull->vertex_indices;
        observed += final_indices.size();
        if (final_indices != item.expected) passed = false;
    }
    const auto end = Clock::now();
    const auto elapsed = std::chrono::duration_cast<std::chrono::nanoseconds>(end - start).count();
    std::cout << item.name << ',' << repetition << ',' << (warmup ? 1 : 0) << ',' << calls << ','
              << elapsed << ',' << (passed ? "passed" : "oracle_failed") << ','
              << observed << ',' << indices(final_indices) << '\n';
    if (!passed) throw std::runtime_error(std::string("fixture mismatch: ") + item.name);
}
}

int main(int argc, char** argv) {
    try {
        if (argc == 2 && std::string(argv[1]) == "--describe") {
            std::cout << "csl.geo06-driver/1,QuickHull2D,3 fixtures,call-only steady_clock nanoseconds\n";
            return 0;
        }
        bool smoke = argc == 2 && std::string(argv[1]) == "--smoke";
        bool measure = argc == 5 && std::string(argv[1]) == "--measure";
        if (!smoke && !measure) throw std::invalid_argument("usage: --describe | --smoke | --measure REPETITIONS WARMUPS CALLS");
        const int repetitions = smoke ? 1 : positive(argv[2], 7, 100);
        const int warmups = smoke ? 0 : positive(argv[3], 1, 1);
        const int calls = smoke ? 1 : positive(argv[4], 1, 100000);
        std::cout << "scenario,repetition,warmup,calls,duration_ns,status,observed_vertices,indices\n";
        for (int w = 0; w < warmups; ++w)
            for (const auto& item : cases) run(item, w, true, calls);
        for (int rep = 0; rep < repetitions; ++rep) {
            if (rep % 2 == 0) for (const auto& item : cases) run(item, rep, false, calls);
            else for (auto it = cases.rbegin(); it != cases.rend(); ++it) run(*it, rep, false, calls);
        }
        return 0;
    } catch (const std::exception& e) {
        std::cerr << e.what() << '\n';
        return 2;
    }
}
