#pragma once

#include <csl/model/hybrid_system.hpp>
#include <cstdint>
#include <limits>
#if defined(_WIN32)
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#elif defined(__unix__) || defined(__APPLE__)
#include <time.h>
#endif

namespace csl::synthesis::detail {

inline model::HybridOperationThreadCpuReading read_current_thread_cpu() noexcept {
    using Unavailable=model::HybridOperationThreadCpuReadUnavailable;
#if defined(_WIN32)
    FILETIME creation{},exit{},kernel{},user{};
    if(!GetThreadTimes(GetCurrentThread(),&creation,&exit,&kernel,&user))
        return Unavailable{Unavailable::Reason::read_failed};
    ULARGE_INTEGER kernel_ticks{},user_ticks{};
    kernel_ticks.LowPart=kernel.dwLowDateTime;kernel_ticks.HighPart=kernel.dwHighDateTime;
    user_ticks.LowPart=user.dwLowDateTime;user_ticks.HighPart=user.dwHighDateTime;
    const auto maximum_ticks=static_cast<ULONGLONG>(
        std::numeric_limits<std::uint64_t>::max()/100);
    if(kernel_ticks.QuadPart>maximum_ticks||user_ticks.QuadPart>maximum_ticks-kernel_ticks.QuadPart)
        return Unavailable{Unavailable::Reason::read_failed};
    return model::HybridOperationThreadCpuTick{
        static_cast<std::uint64_t>((kernel_ticks.QuadPart+user_ticks.QuadPart)*100)};
#elif defined(CLOCK_THREAD_CPUTIME_ID)
    timespec reading{};
    if(clock_gettime(CLOCK_THREAD_CPUTIME_ID,&reading)!=0||reading.tv_sec<0||
       reading.tv_nsec<0||reading.tv_nsec>=1'000'000'000)
        return Unavailable{Unavailable::Reason::read_failed};
    constexpr auto billion=std::uint64_t{1'000'000'000};
    const auto seconds=static_cast<std::uint64_t>(reading.tv_sec);
    const auto nanos=static_cast<std::uint64_t>(reading.tv_nsec);
    const auto maximum=std::numeric_limits<std::uint64_t>::max();
    if(seconds>(maximum-nanos)/billion) return Unavailable{Unavailable::Reason::read_failed};
    return model::HybridOperationThreadCpuTick{seconds*billion+nanos};
#else
    return Unavailable{Unavailable::Reason::unsupported_platform};
#endif
}

inline model::HybridRelationInstrumentation make_hybrid_operation_instrumentation() {
    return {{[] { return read_current_thread_cpu(); }}};
}

} // namespace csl::synthesis::detail
