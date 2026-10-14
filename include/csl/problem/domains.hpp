#pragma once

#include <csl/problem/contracts.hpp>

#include <csl/model/linear_system.hpp>
#include <csl/sets/data.hpp>

namespace csl::problem {
template<class T> using Result = std::variant<T, Diagnostic>;
namespace detail { struct ControlStorage; }

// Immutable snapshot of the canonical authored domain, retaining native set data.
class ControlDomains {
public:
    ControlDomains(const ControlDomains&) = default;
    ControlDomains& operator=(const ControlDomains&) = default;
    std::size_t horizon() const noexcept;
    std::size_t dimension() const noexcept;
    std::shared_ptr<const ControlDomain> description() const noexcept;
private:
    explicit ControlDomains(std::shared_ptr<const detail::ControlStorage>);
    std::shared_ptr<const detail::ControlStorage> storage_;
    friend Result<ControlDomains> snapshot_controls(const ControlDomain&, const model::LinearSystem&);
};
Result<ControlDomains> snapshot_controls(const ControlDomain&, const model::LinearSystem&);
} // namespace csl::problem
