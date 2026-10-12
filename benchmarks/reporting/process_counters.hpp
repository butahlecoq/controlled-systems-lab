#pragma once
#include <cstdint>
#include <optional>
#include <string>
namespace csl::reporting {
struct ProcessCounters {
    std::optional<std::uint64_t> user_ns, kernel_ns, peak_resident_bytes;
    std::string source, unavailable_reason;
};
ProcessCounters process_counters();
std::string counters_json(const ProcessCounters&);
}
