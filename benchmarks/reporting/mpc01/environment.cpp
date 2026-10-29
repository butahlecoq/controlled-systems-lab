#include "environment.hpp"

#include <csl/problem/resolved_problem.hpp>
#include <nlohmann/json.hpp>

#include <fstream>
#include <iterator>
#include <span>
#include <string>
#include <thread>
#include <variant>

#if defined(__linux__)
#include <sys/utsname.h>
#endif

#ifndef CSL_MPC01_SOURCE_DIRTY
#error "MPC-01 provenance definitions are required"
#endif
#ifndef CSL_MPC01_SOURCE_COMMIT
#error "MPC-01 provenance definitions are required"
#endif
#ifndef CSL_MPC01_BUILD_TYPE
#error "MPC-01 build type definition is required"
#endif

namespace csl::mpc01 {
namespace {

using Json = nlohmann::json;

Json unavailable(std::string reason) {
    return {{"status", "unavailable"}, {"reason", std::move(reason)}};
}

Json available(Json value) {
    return {{"status", "available"}, {"value", std::move(value)}};
}

Json binary_digest(std::string_view path) {
    std::ifstream input(std::string(path), std::ios::binary);
    if (!input) return unavailable("executable path could not be opened");
    std::string bytes{std::istreambuf_iterator<char>{input}, std::istreambuf_iterator<char>{}};
    if (input.bad()) return unavailable("executable bytes could not be read");
    const auto content = problem::snapshot_content(std::as_bytes(std::span<const char>{bytes.data(), bytes.size()}));
    if (const auto* error = std::get_if<csl::Diagnostic>(&content))
        return unavailable(error->explanation);
    return available(problem::hex(std::get<problem::ResolvedContent>(content).digest()));
}

#if defined(__linux__)
Json os_release_name() {
    std::ifstream os_release("/etc/os-release");
    std::string line;
    while (std::getline(os_release, line)) {
        constexpr std::string_view prefix = "PRETTY_NAME=";
        if (!line.starts_with(prefix)) continue;
        auto value = line.substr(prefix.size());
        if (value.size() >= 2 && value.front() == '"' && value.back() == '"')
            value = value.substr(1, value.size() - 2);
        if (!value.empty()) return available(std::move(value));
    }
    return unavailable("PRETTY_NAME was not available in /etc/os-release");
}

Json cpu_model() {
    std::ifstream cpu_info("/proc/cpuinfo");
    std::string line;
    while (std::getline(cpu_info, line)) {
        if (!line.starts_with("model name")) continue;
        const auto separator = line.find(':');
        if (separator == std::string::npos) break;
        auto value = line.substr(separator + 1);
        const auto first = value.find_first_not_of(" \t");
        if (first == std::string::npos) break;
        value.erase(0, first);
        return available(std::move(value));
    }
    return unavailable("CPU model was not available in /proc/cpuinfo");
}
#endif

} // namespace

Json environment_manifest(std::string_view executable, bool hpipm_first) {
    const auto logical = std::thread::hardware_concurrency();
    std::string os_family = "Other";
    Json os_version = unavailable("OS version capture is not implemented for this platform");
    Json kernel = unavailable("kernel capture is not implemented for this platform");
    Json cpu = unavailable("CPU model capture is not implemented for this platform");
#if defined(_WIN32)
    os_family = "Windows";
#elif defined(__APPLE__)
    os_family = "Darwin";
#elif defined(__linux__)
    os_family = "Linux";
    struct utsname host {};
    if (uname(&host) == 0) kernel = available(host.release);
    else kernel = unavailable("uname failed");
    os_version = os_release_name();
    cpu = cpu_model();
#endif

    const auto order = hpipm_first ? "HPIPM then OSQP" : "OSQP then HPIPM";
    const auto observed_backend_threads = unavailable("the native adapter does not query effective backend thread count");
    return {
        {"schema", "csl.mpc01-environment/1"},
        {"build", {
            {"schema", "csl.mpc01-build/1"},
            {"source_revision", CSL_MPC01_SOURCE_COMMIT},
            {"source_tree_sha256", CSL_MPC01_SOURCE_TREE_SHA256},
            {"source_snapshot_method", "git-head-tracked-diff-untracked-content-excluding-run-output-sha256/2"},
            {"source_dirty", CSL_MPC01_SOURCE_DIRTY != 0},
            {"compiler_id", CSL_MPC01_COMPILER_ID},
            {"compiler_version", CSL_MPC01_COMPILER_VERSION},
            {"generator", CSL_MPC01_GENERATOR},
            {"architecture", CSL_MPC01_ARCHITECTURE},
            {"build_type", CSL_MPC01_BUILD_TYPE},
            {"cxx_standard", "20"},
            {"c_flags_sha256", CSL_MPC01_C_FLAGS_SHA256},
            {"cxx_flags_sha256", CSL_MPC01_CXX_FLAGS_SHA256},
            {"executable_link_flags_sha256", CSL_MPC01_LINK_FLAGS_SHA256},
            {"target_flags_sha256", CSL_MPC01_TARGET_FLAGS_SHA256},
            {"backends", {
                {"osqp", {{"version", CSL_MPC01_OSQP_VERSION}, {"archive_sha256", CSL_MPC01_OSQP_SHA256}}},
                {"hpipm", {{"version", CSL_MPC01_HPIPM_VERSION}, {"archive_sha256", CSL_MPC01_HPIPM_SHA256}}},
                {"blasfeo", {{"version", CSL_MPC01_BLASFEO_VERSION}, {"archive_sha256", CSL_MPC01_BLASFEO_SHA256}}}}}}},
        {"runtime", {
            {"schema", "csl.obs04-runtime/1"},
            {"binary_sha256", binary_digest(executable)},
            {"os_family", os_family},
            {"os_version", std::move(os_version)},
            {"kernel", std::move(kernel)},
            {"architecture", CSL_MPC01_ARCHITECTURE},
            {"cpu_model", std::move(cpu)},
            {"logical_cpus", logical > 0 ? available(logical) : unavailable("hardware_concurrency returned zero")}}},
        {"execution", {
            {"requested_workers", 1},
            {"observed_driver_workers", 1},
            {"requested_backend_threads", 1},
            {"observed_backend_threads", observed_backend_threads},
            {"workspace_policy", "fresh-workspace-per-attempt"},
            {"cache_policy", std::string("execution order: ") + order +
                "; for each backend, cold solve followed by a fresh workspace seeded from the cold result when available "
                "(otherwise a cold fallback); "
                "no warm-up repetitions; operating-system caches are not flushed"},
            {"warmup_repetitions", 0},
            {"seed_policy", {{"kind", "not_applicable"},
                {"reason", "fixed deterministic MPC fixtures use no random generator"}}},
            {"tolerances", {{"absolute", 1e-8}, {"relative", 1e-8}}}}}};
}

} // namespace csl::mpc01
