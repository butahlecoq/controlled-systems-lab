#include <csl/geometry/quickhull_2d.hpp>

#include <nlohmann/json.hpp>

#include <chrono>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <variant>
#include <vector>

namespace {
using Json = nlohmann::json;
using Clock = std::chrono::steady_clock;

std::string compiler() {
#ifdef __VERSION__
    return __VERSION__;
#elif defined(_MSC_VER)
    return "MSVC-" + std::to_string(_MSC_VER);
#else
    return "unknown-cxx-compiler";
#endif
}

std::string operating_system() {
#ifdef _WIN32
    return "Windows";
#elif defined(__APPLE__)
    return "macOS";
#elif defined(__linux__)
    return "Linux";
#else
    return "unknown-os";
#endif
}

std::string architecture() {
#if defined(__x86_64__) || defined(_M_X64)
    return "x86_64";
#elif defined(__aarch64__) || defined(_M_ARM64)
    return "aarch64";
#else
    return "unknown-architecture";
#endif
}
}

int main(int argc, char** argv) {
    try {
        if (argc != 3 || std::string(argv[1]) != "--run")
            throw std::invalid_argument("usage: csl_exp06_quickhull --run FIXTURE.json");
        std::ifstream input(argv[2], std::ios::binary);
        if (!input) throw std::runtime_error("could not open fixture");
        const auto fixture = Json::parse(input);
        if (fixture.at("schema") != "csl.geometry-hull-input/1" ||
            !fixture.at("points").is_array() || fixture.at("points").size() > 64)
            throw std::invalid_argument("fixture schema or point count is invalid");
        std::vector<csl::Vector> points;
        for (const auto& row : fixture.at("points")) {
            if (!row.is_array() || row.size() != 2)
                throw std::invalid_argument("fixture must contain 2D point rows");
            csl::Vector point{row[0].get<double>(), row[1].get<double>()};
            points.push_back(std::move(point));
        }
        const auto start = Clock::now();
        const auto hull_result = csl::geometry::quickhull_2d(points);
        const auto end = Clock::now();
        const auto duration = std::chrono::duration_cast<std::chrono::nanoseconds>(end - start).count();
        const auto* hull = std::get_if<csl::geometry::QuickHull2D>(&hull_result);
        if (!hull) throw std::runtime_error("QuickHull returned a failure result");
        Json indices = Json::array();
        for (const auto index : hull->vertex_indices) indices.push_back(index);
        std::cout << Json{{"schema", "csl.exp06-quickhull-result/1"},
            {"duration_ns", duration}, {"indices", std::move(indices)},
            {"method", "csl.geometry.quickhull-2d"}, {"status", "completed"},
            {"runtime", {{"language", "C++"}, {"implementation", "csl.geometry.quickhull-2d"},
                {"version", "1"}, {"compiler", compiler()}, {"os", operating_system()},
                {"architecture", architecture()}, {"build_type",
#ifdef NDEBUG
                    "Release"
#else
                    "Debug"
#endif
            }}}}.dump() << '\n';
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 2;
    }
}
