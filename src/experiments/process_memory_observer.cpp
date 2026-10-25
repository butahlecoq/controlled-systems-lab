#include "process_memory_observer.hpp"

#if defined(__linux__)
#include <fstream>
#include <limits>
#include <unistd.h>
#elif defined(_WIN32)
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <psapi.h>
#elif defined(__APPLE__)
#include <mach/mach.h>
#endif

namespace csl::experiments::detail {

std::optional<std::uint64_t> process_resident_bytes() noexcept {
    try {
#if defined(__linux__)
    std::ifstream statm("/proc/self/statm");
    std::uint64_t total_pages{};
    std::uint64_t resident_pages{};
    if (!(statm >> total_pages >> resident_pages)) return {};
    const auto page_size = ::sysconf(_SC_PAGESIZE);
    if (page_size <= 0 || resident_pages > std::numeric_limits<std::uint64_t>::max() /
        static_cast<std::uint64_t>(page_size)) return {};
    return resident_pages * static_cast<std::uint64_t>(page_size);
#elif defined(_WIN32)
    using GetProcessMemoryInfoFn = BOOL (WINAPI*)(HANDLE, PPROCESS_MEMORY_COUNTERS, DWORD);
    const auto kernel = ::GetModuleHandleW(L"kernel32.dll");
    if (!kernel) return {};
    const auto query = reinterpret_cast<GetProcessMemoryInfoFn>(
        ::GetProcAddress(kernel, "K32GetProcessMemoryInfo"));
    if (!query) return {};
    PROCESS_MEMORY_COUNTERS counters{};
    counters.cb = sizeof(counters);
    if (!query(::GetCurrentProcess(), &counters, sizeof(counters))) return {};
    return static_cast<std::uint64_t>(counters.WorkingSetSize);
#elif defined(__APPLE__)
    task_basic_info_data_t info{};
    mach_msg_type_number_t count = TASK_BASIC_INFO_COUNT;
    if (::task_info(::mach_task_self(), TASK_BASIC_INFO,
        reinterpret_cast<task_info_t>(&info), &count) != KERN_SUCCESS) return {};
    return static_cast<std::uint64_t>(info.resident_size);
#else
    return {};
#endif
    } catch (...) {
        return {};
    }
}

} // namespace csl::experiments::detail
