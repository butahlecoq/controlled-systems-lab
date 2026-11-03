#pragma once

#include <csl/model/hybrid_system.hpp>

#include <cstddef>
#include <ostream>
#include <string_view>
#include <vector>

namespace csl::reports::ext07 {

inline void write_string(std::ostream& output, std::string_view value) {
  output << '"';
  for (const unsigned char character : value) {
    switch (character) {
    case '"': output << "\\\""; break;
    case '\\': output << "\\\\"; break;
    case '\b': output << "\\b"; break;
    case '\f': output << "\\f"; break;
    case '\n': output << "\\n"; break;
    case '\r': output << "\\r"; break;
    case '\t': output << "\\t"; break;
    default:
      if (character < 0x20) {
        constexpr char digits[] = "0123456789abcdef";
        output << "\\u00" << digits[character >> 4] << digits[character & 0xf];
      } else {
        output << static_cast<char>(character);
      }
    }
  }
  output << '"';
}

inline const char* operation_kind(model::HybridRelationOperationKind kind) {
  using Kind = model::HybridRelationOperationKind;
  switch (kind) {
  case Kind::initial_state: return "initial_state";
  case Kind::post_state_invariant: return "post_state_invariant";
  case Kind::mode_flow: return "mode_flow";
  case Kind::continuous_control: return "continuous_control";
  case Kind::pre_reset_invariant: return "pre_reset_invariant";
  case Kind::transition_guard: return "transition_guard";
  case Kind::reset_relation: return "reset_relation";
  }
  return "unknown";
}

inline const char* unavailable_reason(model::HybridOperationThreadCpuUnavailable::Reason reason) {
  using Reason = model::HybridOperationThreadCpuUnavailable::Reason;
  switch (reason) {
  case Reason::not_requested: return "not_requested";
  case Reason::unsupported_platform: return "unsupported_platform";
  case Reason::read_failed: return "read_failed";
  case Reason::clock_regressed: return "clock_regressed";
  }
  return "read_failed";
}

inline void write_operation_record(std::ostream& output,
    const model::HybridRelationOperationRecord& operation) {
  output << "{\"kind\":";
  write_string(output, operation_kind(operation.operation));
  output << ",\"stage\":" << operation.stage << ",\"mode\":";
  if (operation.mode) write_string(output, operation.mode->value);
  else output << "null";
  output << ",\"edge\":";
  if (operation.edge) write_string(output, operation.edge->value);
  else output << "null";
  output << ",\"implementation_id\":";
  write_string(output, operation.implementation_id);
  output << ",\"implementation_version\":";
  write_string(output, operation.implementation_version);
  output << ",\"joint_variables\":" << operation.joint_variables
      << ",\"rows_added\":" << operation.rows_added
      << ",\"matrix_elements_added\":" << operation.matrix_elements_added
      << ",\"cumulative_rows\":" << operation.cumulative_rows
      << ",\"cumulative_matrix_elements\":" << operation.cumulative_matrix_elements
      << ",\"elapsed_wall_nanoseconds\":" << operation.elapsed_wall_nanoseconds
      << ",\"completed\":" << (operation.completed ? "true" : "false")
      << ",\"thread_cpu\":";
  if (const auto* duration = std::get_if<model::HybridOperationThreadCpuDuration>(
          &operation.thread_cpu)) {
    output << "{\"status\":\"observed\",\"nanoseconds\":"
        << duration->nanoseconds << '}';
  } else {
    const auto& unavailable = std::get<model::HybridOperationThreadCpuUnavailable>(
        operation.thread_cpu);
    output << "{\"status\":\"unavailable\",\"reason\":";
    write_string(output, unavailable_reason(unavailable.reason));
    output << '}';
  }
  output << '}';
}

inline void write_operation_records(std::ostream& output,
    const std::vector<model::HybridRelationOperationRecord>& operations) {
  output << '[';
  for (std::size_t index = 0; index < operations.size(); ++index) {
    if (index) output << ',';
    write_operation_record(output, operations[index]);
  }
  output << ']';
}

} // namespace csl::reports::ext07
