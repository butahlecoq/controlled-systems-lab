#pragma once

#include <csl/synthesis/hybrid_path_program.hpp>
#include <ostream>

namespace csl::reports::ext07 {
inline void write_process_cpu_observation(std::ostream& output,
    const synthesis::ProcessCpuObservation& observation) {
    if(const auto* duration=std::get_if<synthesis::ProcessCpuDuration>(&observation)) {
        output << "{\"status\":\"observed\",\"nanoseconds\":" << duration->nanoseconds << '}';
        return;
    }
    const auto reason=std::get<synthesis::ProcessCpuUnavailable>(observation).reason;
    const char* name="not_measured";
    switch(reason) {
    case synthesis::ProcessCpuUnavailable::Reason::not_measured: name="not_measured"; break;
    case synthesis::ProcessCpuUnavailable::Reason::unsupported_platform: name="unsupported_platform"; break;
    case synthesis::ProcessCpuUnavailable::Reason::clock_read_failed: name="clock_read_failed"; break;
    case synthesis::ProcessCpuUnavailable::Reason::clock_regressed: name="clock_regressed"; break;
    }
    output << "{\"status\":\"unavailable\",\"reason\":\"" << name << "\"}";
}
}
