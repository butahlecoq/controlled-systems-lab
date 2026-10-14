#pragma once

#include <csl/problem/contracts.hpp>

#include <csl/problem/domains.hpp>

namespace csl::problem {
namespace detail { struct InitialStorage; struct ExternalStorage; }

class InitialData {
public:
    InitialData(const InitialData&) = default;
    InitialData& operator=(const InitialData&) = default;
    std::shared_ptr<const InitialInformation> description() const noexcept;
private:
    explicit InitialData(std::shared_ptr<const detail::InitialStorage>);
    std::shared_ptr<const detail::InitialStorage> storage_;
    friend Result<InitialData> snapshot_initial(const InitialInformation&, const model::LinearSystem&);
};
class ExternalData {
public:
    ExternalData(const ExternalData&) = default;
    ExternalData& operator=(const ExternalData&) = default;
    std::size_t horizon() const noexcept;
    std::size_t dimension() const noexcept;
    std::shared_ptr<const std::optional<ExternalInput>> description() const noexcept;
private:
    explicit ExternalData(std::shared_ptr<const detail::ExternalStorage>);
    std::shared_ptr<const detail::ExternalStorage> storage_;
    friend Result<ExternalData> snapshot_external(const std::optional<ExternalInput>&, const model::LinearSystem&);
};
Result<InitialData> snapshot_initial(const InitialInformation&, const model::LinearSystem&);
Result<ExternalData> snapshot_external(const std::optional<ExternalInput>&, const model::LinearSystem&);
} // namespace csl::problem
