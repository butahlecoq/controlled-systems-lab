#include <csl/problem/temporal_lifts.hpp>
#include <csl/numeric/data.hpp>
#include <csl/sets/data.hpp>

#include <algorithm>
#include <charconv>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <iostream>
#include <limits>
#include <memory>
#include <stdexcept>
#include <string>
#include <variant>
#include <vector>

#if !defined(NDEBUG) || defined(_DEBUG)
#error "The EXT-03 measurement executable must be compiled as a Release target"
#endif

using namespace csl;
using namespace csl::problem;

namespace {
template<class T, class... R>
T take(std::variant<T, R...> value) {
    if (auto* result = std::get_if<T>(&value)) return std::move(*result);
    throw std::runtime_error("unexpected diagnostic or unsupported result");
}

void require(bool condition, const char* message) {
    if (!condition) throw std::runtime_error(message);
}

sets::SetData interval_data(double lower, double upper, std::string id) {
    const auto h = take(numeric::snapshot(Matrix{2, 1, {1, -1}}));
    const auto bounds = take(numeric::snapshot_vector(Vector{upper, -lower}));
    const auto equalities = take(numeric::snapshot(Matrix{0, 1, {}}));
    const auto values = take(numeric::snapshot_vector(Vector{}));
    return take(sets::make_h({{std::move(id)}, 1, {"u"}},
        {h, bounds, equalities, values}));
}

SetHandle interval(double lower, double upper, std::string id) {
    return interval_data(lower, upper, std::move(id)).as_handle();
}

Problem original_problem() {
    const auto controls = interval(-1, 1, "ext03-control");
    auto model = std::make_shared<const SystemModel>(SystemModel{{
        {1, 1, 0}, TimeDomain::discrete,
        LinearStage{{1, 1, {1}}, {1, 1, {1}}, {1, 0, {}}, {0}}}, {}});
    return {{"ext03-temporal-lift-measurement"}, std::move(model), {0, 1, 2},
        KnownInitial{{0}}, ContinuousDomain{{controls, controls}},
        {UniversalSet{1}, UniversalSet{1}, UniversalSet{1}}, {}, {},
        InformationPattern::nominal_open_loop, LinearTerminal{{1}, 0}};
}

SlewMemoryRequest slew_request() {
    return {RateLimitedFirstAction{{0.25}, interval(-0.25, 0.25, "ext03-first-rate")},
        {interval(-0.25, 0.25, "ext03-later-rate")}};
}

void check_original_history(const ControlHistory& history) {
    require(history.states == std::vector<Vector>{{0}, {0}, {-0.25}},
        "recovered physical states differ from the analytic optimizer");
    require(history.controls == std::vector<Vector>{{0}, {-0.25}},
        "recovered controls differ from the analytic optimizer");
    require(history.controls[0][0] >= -1 && history.controls[0][0] <= 1 &&
        history.controls[1][0] >= -1 && history.controls[1][0] <= 1,
        "recovered controls violate absolute bounds");
    require(std::abs(history.states[1][0] - history.states[0][0] - history.controls[0][0]) <= 1e-12 &&
        std::abs(history.states[2][0] - history.states[1][0] - history.controls[1][0]) <= 1e-12,
        "recovered history violates original dynamics");
    require(std::abs(history.controls[0][0] - 0.25) <= 0.25 + 1e-12 &&
        std::abs(history.controls[1][0] - history.controls[0][0]) <= 0.25 + 1e-12,
        "recovered history violates the slew constraints");
    require(history.states.back()[0] == -0.25,
        "recovered terminal objective differs from the analytic optimum");
}

void one_run() {
    const auto original = original_problem();
    const auto request = slew_request();
    auto lifted_result = lift_one_step_slew(original, request);
    const auto* lifted_value = std::get_if<SlewMemoryLift>(&lifted_result);
    require(lifted_value != nullptr, "one-step slew lift was rejected");
    const auto& lifted = *lifted_value;
    require(lifted.coordinates.original == JointCoordinates{{1, 1, 0}, 2},
        "original coordinate identity differs");
    require(lifted.coordinates.lifted == JointCoordinates{{2, 1, 0}, 2},
        "lifted coordinate identity differs");

    const LiftedControlHistory auxiliary{{{0, 0.25}, {0, 0}, {-0.25, -0.25}}, {{-0.25}, {-0.25}}};
    const auto recovered = take(recover_history(lifted.coordinates, auxiliary, 0, 0));
    check_original_history(recovered);
}

std::uint64_t positive_count(const char* text, std::uint64_t maximum, const char* name) {
    const std::string value{text};
    std::uint64_t parsed{};
    const auto [end, error] = std::from_chars(value.data(), value.data() + value.size(), parsed);
    if (value.empty() || error != std::errc{} || end != value.data() + value.size() ||
        parsed == 0 || parsed > maximum)
        throw std::invalid_argument(std::string{name} + " must be an integer in [1," +
            std::to_string(maximum) + "]");
    return parsed;
}

std::string json_escape(const std::string& value) {
    std::string result;
    for (const unsigned char ch : value) {
        if (ch == '"' || ch == '\\') {
            result.push_back('\\');
            result.push_back(static_cast<char>(ch));
        } else if (ch == '\n') result += "\\n";
        else if (ch == '\r') result += "\\r";
        else if (ch == '\t') result += "\\t";
        else if (ch >= 0x20) result.push_back(static_cast<char>(ch));
    }
    return result;
}
}

int main(int argc, char** argv) {
    try {
        if (argc != 4)
            throw std::invalid_argument("usage: csl_ext03_temporal_lift_report BATCH WARMUPS REPETITIONS");
        const auto batch = positive_count(argv[1], 100, "batch");
        const auto warmups = positive_count(argv[2], 5, "warmups");
        const auto repetitions = positive_count(argv[3], 20, "repetitions");
        if (warmups > std::numeric_limits<std::uint64_t>::max() - repetitions)
            throw std::invalid_argument("warmup and repetition count overflows");
        const auto total_rounds = warmups + repetitions;
        std::cout << "{\"event\":\"header\",\"schema\":\"csl.ext03-transform-measurement/1\",\"batch\":"
                  << batch << ",\"warmups\":" << warmups << ",\"repetitions\":" << repetitions << "}\n";
        bool failed = false;
        for (std::uint64_t round = 0; round < total_rounds; ++round) {
            const auto start = std::chrono::steady_clock::now();
            std::uint64_t attempted = 0;
            std::string failure;
            for (; attempted < batch; ++attempted) {
                try {
                    one_run();
                } catch (const std::exception& error) {
                    failure = error.what();
                    ++attempted;
                    break;
                }
            }
            const auto elapsed = std::chrono::duration_cast<std::chrono::nanoseconds>(
                std::chrono::steady_clock::now() - start).count();
            std::cout << "{\"event\":\"trial\",\"fixture\":\"two_step_slew_integrator\",\"round\":"
                      << round << ",\"warmup\":" << (round < warmups ? "true" : "false")
                      << ",\"batch\":" << batch << ",\"elapsed_ns\":" << elapsed
                      << ",\"attempted_calls\":" << attempted
                      << ",\"checked_calls\":" << (failure.empty() ? attempted : attempted - 1)
                      << ",\"failed_calls\":" << (failure.empty() ? 0 : 1)
                      << ",\"missing_calls\":" << (batch - attempted)
                      << ",\"status\":\"" << (failure.empty() ? "passed" : "failed") << "\"";
            if (!failure.empty()) std::cout << ",\"error\":\"" << json_escape(failure) << "\"";
            std::cout << "}\n";
            if (elapsed <= 0) throw std::runtime_error("nonpositive measured interval");
            if (!failure.empty()) {
                failed = true;
                break;
            }
        }
        return failed ? 2 : 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
