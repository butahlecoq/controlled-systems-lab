#include "crossover_explicit.hpp"
#include "crossover_online.hpp"

#include <nlohmann/json.hpp>
#include <chrono>
#include <ctime>
#include <cstdio>
#include <type_traits>
#include <fstream>
#include <iostream>
#include <memory>
#include <string>

namespace {
using namespace mpc_crossover;
using Json = nlohmann::json;
using Clock = std::chrono::steady_clock;
using Stamp = Clock::time_point;
long long elapsed(Stamp start, Stamp end) {
    return std::chrono::duration_cast<std::chrono::nanoseconds>(end - start).count();
}

struct Step {
    Point observed{};
    std::optional<double> action;
    long long duration_ns{};
};

struct Episode {
    std::array<Step, 3> steps{};
    std::size_t decisions{};
    double cost{};
    bool feasible{};
    std::string error;
};

template <class Policy> struct Fleet {
    std::array<std::unique_ptr<Policy>, 3> horizons;
    Fleet() {
        for (int n = 1; n <= 3; ++n)
            horizons[n - 1] = std::make_unique<Policy>(n);
    }
    Policy &at(int n) { return *horizons.at(n - 1); }
};

Json paired_queries(const Json &queries) {
    Fleet<ExplicitController> explicit_mpc;
    Fleet<OnlineController> online_mpc;
    Json rows = Json::array();
    for (const auto &q : queries) {
        auto x = q.at("state").get<Point>();
        int n = q.at("remaining").get<int>();
        const auto a = explicit_mpc.at(n).decide(x);
        Json row{{"id", q.at("id")}, {"explicit", nullptr}, {"online", nullptr}};
        if (a)
            row["explicit"] = *a;
        try {
            if (const auto u = online_mpc.at(n).decide(x))
                row["online"] = *u;
        } catch (const std::runtime_error &error) {
            row["error"] = error.what();
        }
        rows.push_back(std::move(row));
    }
    Json regions = Json::array();
    for (int n = 1; n <= 3; ++n) {
        Json cells = Json::array();
        for (auto &r : explicit_mpc.at(n).regions())
            cells.push_back({{"vertices", r.vertices}, {"first_action", r.action}});
        regions.push_back({{"remaining", n}, {"cells", std::move(cells)}});
    }
    return {{"queries", std::move(rows)}, {"regions", std::move(regions)}};
}

template <class Policy> Json deploy(const std::vector<Point> &states, int count) {
    std::vector<Episode> episodes(count);
    const auto cpu_start = std::clock();
    const auto start = Clock::now();
    Fleet<Policy> controller;
    const auto serving = Clock::now();
    for (int i = 0; i < count; ++i) {
        auto x = states[i % states.size()];
        auto &episode = episodes[i];
        std::vector<double> tail;
        for (int n = 3; n > 0; --n) {
            auto &step = episode.steps[episode.decisions++];
            step.observed = x;
            const auto query = Clock::now();
            if constexpr (std::is_same_v<Policy, OnlineController>) {
                try {
                    if (auto u = controller.at(n).decide(x, tail)) {
                        step.action = u->front();
                        tail.assign(u->begin() + 1, u->end());
                    }
                } catch (const std::runtime_error &error) {
                    episode.error = error.what();
                }
            } else {
                step.action = controller.at(n).decide(x);
            }
            step.duration_ns = elapsed(query, Clock::now());
            if (!step.action)
                break;
            const double u = *step.action;
            episode.cost += 0.25 * u * u;
            x = {x[0] + x[1], x[1] + u};
            if (n == 1) {
                episode.feasible = true;
                episode.cost += x[0] * x[0] + x[1] * x[1];
            }
        }
    }
    const auto finish = Clock::now();
    const auto cpu_end = std::clock();
    Json records = Json::array();
    for (const auto &episode : episodes) {
        Json steps = Json::array();
        for (std::size_t i = 0; i < episode.decisions; ++i) {
            const auto &s = episode.steps[i];
            steps.push_back({{"observed", s.observed},
                             {"action", s.action ? Json(*s.action) : Json(nullptr)},
                             {"latency_ns", s.duration_ns}});
        }
        records.push_back(
            {{"status", episode.error.empty() ? (episode.feasible ? "completed" : "infeasible")
                                              : "solver_error"},
             {"error", episode.error},
             {"cost", episode.feasible ? Json(episode.cost) : Json(nullptr)},
             {"steps", std::move(steps)}});
    }
    Json result{
        {"setup_ns", elapsed(start, serving)},      {"service_ns", elapsed(serving, finish)},
        {"total_ns", elapsed(start, finish)},       {"episodes", std::move(records)},
        {"process_cpu_ticks", cpu_end - cpu_start}, {"clock_ticks_per_second", CLOCKS_PER_SEC}};
    if constexpr (std::is_same_v<Policy, ExplicitController>) {
        std::size_t bytes = sizeof(controller);
        for (int n = 1; n <= 3; ++n)
            bytes += controller.at(n).storage_bytes();
        result["policy_owned_bytes"] = bytes;
    } else {
        for (int n = 1; n <= 3; ++n) {
            result["observed_scheduler_width"].push_back(controller.at(n).scheduler_threads());
            result["supplied_warm_starts"].push_back(controller.at(n).supplied_warm_starts());
            result["cold_retries"].push_back(controller.at(n).cold_retries());
        }
    }
    return result;
}
}

int main(int argc, char **argv) {
    try {
        if (argc != 3)
            throw std::invalid_argument("usage: mpc_crossover INPUT.json OUTPUT.jsonl");
        std::ifstream input(argv[1]);
        const Json spec = Json::parse(input);
        const auto states = spec.at("deployment_states").get<std::vector<Point>>();
        if (states.empty())
            throw std::invalid_argument("empty deployment workload");
        auto close_file = [](std::FILE *file) { std::fclose(file); };
        std::unique_ptr<std::FILE, decltype(close_file)> output(std::fopen(argv[2], "wbx"),
                                                                close_file);
        if (!output)
            throw std::runtime_error("cannot exclusively create output JSONL");
        auto save = [&](const Json &row) {
            auto line = row.dump() + "\n";
            if (std::fwrite(line.data(), 1, line.size(), output.get()) != line.size() ||
                std::fflush(output.get()) != 0)
                throw std::runtime_error("failed writing attempt record");
        };
        save({{"type", "validation_started"}});
        try {
            save({{"type", "validation"}, {"data", paired_queries(spec.at("queries"))}});
        } catch (const std::exception &e) {
            save({{"type", "validation_error"}, {"error", e.what()}});
            throw;
        }
        for (int count : spec.at("counts").get<std::vector<int>>()) {
            if (count < 1 || count > 65536)
                throw std::invalid_argument("invalid trajectory count");
            for (int rep = -1; rep < 5; ++rep) {
                for (int position = 0; position < 2; ++position) {
                    const bool offline = (rep % 2 == 0) == (position == 0);
                    Json row{{"type", "started"},
                             {"count", count},
                             {"repetition", rep},
                             {"position", position},
                             {"controller", offline ? "explicit" : "online"}};
                    save(row);
                    try {
                        row["data"] = offline ? deploy<ExplicitController>(states, count)
                                              : deploy<OnlineController>(states, count);
                        row["type"] = "deployment";
                    } catch (const std::exception &e) {
                        row["type"] = "error";
                        row["error"] = e.what();
                        save(row);
                        throw;
                    }
                    save(row);
                }
            }
        }
    } catch (const std::exception &err) {
        std::cerr << err.what() << '\n';
        return 1;
    }
}
