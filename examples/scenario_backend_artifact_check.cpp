#include <cmath>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <iterator>
#include <regex>
#include <string>

int main(int argc, char** argv) {
    if (argc != 2) {
        std::cerr << "Usage: scenario_backend_artifact_check <artifact.json>\n";
        return 2;
    }
    std::ifstream input(argv[1], std::ios::binary);
    if (!input) {
        std::cerr << "Cannot read saved artifact\n";
        return 1;
    }
    const std::string json{std::istreambuf_iterator<char>(input), std::istreambuf_iterator<char>()};
    std::smatch match;
    if (!std::regex_search(json, match, std::regex(R"REGEX("termination"\s*:\s*"([^"]+)")REGEX")) ||
        match[1] != "completed") {
        std::cerr << "Saved artifact does not record completed termination\n";
        return 1;
    }
    if (!std::regex_search(json, match,
            std::regex(R"REGEX("controls"\s*:\s*\[\s*([-+0-9.eE]+)\s*,\s*([-+0-9.eE]+)\s*\])REGEX"))) {
        std::cerr << "Saved artifact does not contain two serialized controls\n";
        return 1;
    }
    const auto text0 = match[1].str();
    const auto text1 = match[2].str();
    char* end0{};
    char* end1{};
    const double u0 = std::strtod(text0.c_str(), &end0);
    const double u1 = std::strtod(text1.c_str(), &end1);
    if (!end0 || *end0 != '\0' || !end1 || *end1 != '\0' ||
        !std::isfinite(u0) || !std::isfinite(u1) || u0 < -1e-8 || u1 < -1e-8 ||
        u0 > 1 + 1e-8 || u1 > 1 + 1e-8 || std::abs(u0 + u1 - 1) > 1e-8) {
        std::cerr << "Serialized controls fail the independent bounds or terminal-equation check\n";
        return 1;
    }
}
