#include "process_counters.hpp"
#include "lp_report.hpp"
#include <limits>
#if defined(_WIN32)
#define NOMINMAX
#include <Windows.h>
#include <Psapi.h>
#elif defined(__linux__)
#include <sys/resource.h>
#endif
namespace csl::reporting {
ProcessCounters process_counters() {
    ProcessCounters result;
#if defined(_WIN32)
    result.source="GetProcessTimes / GetProcessMemoryInfo";
    FILETIME creation{},exit{},kernel{},user{};
    if (GetProcessTimes(GetCurrentProcess(),&creation,&exit,&kernel,&user)) {
        const auto ns=[](FILETIME time)->std::optional<std::uint64_t> {
            const auto ticks=(static_cast<std::uint64_t>(time.dwHighDateTime)<<32)|time.dwLowDateTime;
            if(ticks>std::numeric_limits<std::uint64_t>::max()/100) return {};
            return ticks*100;
        };
        result.user_ns=ns(user);result.kernel_ns=ns(kernel);
    }
    PROCESS_MEMORY_COUNTERS memory{}; memory.cb=sizeof(memory);
    if (GetProcessMemoryInfo(GetCurrentProcess(),&memory,sizeof(memory))) result.peak_resident_bytes=memory.PeakWorkingSetSize;
    if (!result.user_ns || !result.kernel_ns || !result.peak_resident_bytes) result.unavailable_reason="Windows process counter call failed or value overflowed";
#elif defined(__linux__)
    result.source="getrusage(RUSAGE_SELF)";
    rusage usage{};
    if(getrusage(RUSAGE_SELF,&usage)==0) {
        const auto ns=[](timeval t)->std::optional<std::uint64_t> {
            if(t.tv_sec<0 || t.tv_usec<0) return {};
            const auto seconds=static_cast<std::uint64_t>(t.tv_sec);
            const auto fraction=static_cast<std::uint64_t>(t.tv_usec)*1000;
            if(seconds>(std::numeric_limits<std::uint64_t>::max()-fraction)/1000000000) return {};
            return seconds*1000000000+fraction;
        };
        result.user_ns=ns(usage.ru_utime);result.kernel_ns=ns(usage.ru_stime);
        if(usage.ru_maxrss>=0 && static_cast<std::uint64_t>(usage.ru_maxrss)<=std::numeric_limits<std::uint64_t>::max()/1024)
            result.peak_resident_bytes=static_cast<std::uint64_t>(usage.ru_maxrss)*1024;
    }
    if(!result.user_ns || !result.kernel_ns || !result.peak_resident_bytes) result.unavailable_reason="getrusage failed or value overflowed";
#else
    result.source="unsupported platform";result.unavailable_reason="process counters not implemented on this platform";
#endif
    return result;
}
std::string counters_json(const ProcessCounters& counters) {
    const auto metric=[&](const std::optional<std::uint64_t>& value,const char* unit,const char* scope) {
        return value?"{\"available\":true,\"value\":"+std::to_string(*value)+",\"unit\":"+json_string(unit)+",\"scope\":"+json_string(scope)+"}":"{\"available\":false,\"reason\":"+json_string(counters.unavailable_reason)+"}";
    };
    return "{\"source\":"+json_string(counters.source)+",\"user_cpu\":"+metric(counters.user_ns,"ns","process lifetime CPU at snapshot")+",\"kernel_cpu\":"+metric(counters.kernel_ns,"ns","process lifetime CPU at snapshot")+",\"peak_resident\":"+metric(counters.peak_resident_bytes,"bytes","process lifetime peak, not per trial or delta")+"}";
}
}
