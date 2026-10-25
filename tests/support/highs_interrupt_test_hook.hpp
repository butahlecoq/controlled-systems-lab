#pragma once

#include <stop_token>

namespace csl::adapters::lp::test_support {
void cancel_on_next_simplex_interrupt(std::stop_source&) noexcept;
void request_stop_on_simplex_interrupt_for_test() noexcept;
void clear_pending_simplex_interrupt_for_test() noexcept;
}
