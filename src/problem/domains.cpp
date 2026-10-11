#include <csl/problem/domains.hpp>
#include "detail.hpp"

namespace csl::problem {
namespace detail {
struct ControlStorage {
    std::size_t horizon, dimension;
    ControlDomain description;
};
}
namespace {
std::optional<Diagnostic> check_finite(const FiniteDomain& domain, std::size_t dimension) {
    if (domain.dimension!=dimension)
        return detail::invalid("problem.controls.dimension","Catalogue dimension must match its control coordinate block.");
    for (std::size_t i=0;i<domain.catalogue.size();++i) {
        const auto& point=domain.catalogue[i];
        if (point.size()!=dimension || !detail::finite(point))
            return detail::invalid(detail::indexed("problem.controls.catalogue",i),"Catalogue actions must have finite coordinates and the declared dimension.");
    }
    return {};
}
}
ControlDomains::ControlDomains(std::shared_ptr<const detail::ControlStorage> storage) : storage_(std::move(storage)) {}
std::size_t ControlDomains::horizon() const noexcept { return storage_->horizon; }
std::size_t ControlDomains::dimension() const noexcept { return storage_->dimension; }
std::shared_ptr<const ControlDomain> ControlDomains::description() const noexcept { return {storage_,&storage_->description}; }

Result<ControlDomains> snapshot_controls(const ControlDomain& authored, const model::LinearSystem& model) {
    const auto dimension=model.dimensions().control;
    const auto horizon=model.horizon();
    auto error=std::visit(detail::Visitor{
        [&](const ContinuousDomain& domain) {
            return detail::check_sets(domain.stages,horizon,dimension,"problem.controls.stages");
        },
        [&](const FiniteDomain& domain) { return check_finite(domain,dimension); },
        [&](const MixedDomain& domain) -> std::optional<Diagnostic> {
            if (domain.discrete.dimension>dimension)
                return detail::invalid("problem.controls.dimension","Discrete dimension must not exceed the full control dimension.");
            if (auto failure=check_finite(domain.discrete,domain.discrete.dimension)) return failure;
            return detail::check_sets(domain.continuous.stages,horizon,dimension-domain.discrete.dimension,"problem.controls.stages");
        }
    },authored);
    if (error) return *error;
    return ControlDomains(std::make_shared<const detail::ControlStorage>(detail::ControlStorage{horizon,dimension,authored}));
}
} // namespace csl::problem
