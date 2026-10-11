#include <csl/problem/initial_information.hpp>
#include "detail.hpp"

namespace csl::problem {
namespace detail {
struct InitialStorage { InitialInformation description; };
struct ExternalStorage {
    std::size_t horizon, dimension;
    std::optional<ExternalInput> description;
};
}
InitialData::InitialData(std::shared_ptr<const detail::InitialStorage> storage) : storage_(std::move(storage)) {}
std::shared_ptr<const InitialInformation> InitialData::description() const noexcept { return {storage_,&storage_->description}; }
ExternalData::ExternalData(std::shared_ptr<const detail::ExternalStorage> storage) : storage_(std::move(storage)) {}
std::size_t ExternalData::horizon() const noexcept { return storage_->horizon; }
std::size_t ExternalData::dimension() const noexcept { return storage_->dimension; }
std::shared_ptr<const std::optional<ExternalInput>> ExternalData::description() const noexcept { return {storage_,&storage_->description}; }

Result<InitialData> snapshot_initial(const InitialInformation& authored, const model::LinearSystem& model) {
    auto error=std::visit(detail::Visitor{
        [&](const KnownInitial& initial) { return detail::check_point(initial.point,model.dimensions().state,"problem.initial"); },
        [&](const InitialSet& initial) -> std::optional<Diagnostic> {
            if (auto failure=detail::check_quantifier(initial.quantifier,"problem.initial.quantifier")) return failure;
            return detail::check_set(initial.set,model.dimensions().state,"problem.initial");
        }
    },authored);
    if (error) return *error;
    return InitialData(std::make_shared<const detail::InitialStorage>(detail::InitialStorage{authored}));
}

Result<ExternalData> snapshot_external(const std::optional<ExternalInput>& authored, const model::LinearSystem& model) {
    const auto dimension=model.dimensions().external;
    const auto horizon=model.horizon();
    if (!authored && dimension!=0)
        return detail::invalid("problem.external.port","An external port requires an explicit external-input description.");
    if (authored) {
        const auto quantified=[&](const auto& external) -> std::optional<Diagnostic> {
            if (auto error=detail::check_quantifier(external.quantifier,"problem.external.quantifier")) return error;
            return detail::check_sets(external.stages,horizon,dimension,"problem.external.stages");
        };
        auto error=std::visit(detail::Visitor{
            [&](const KnownExternalSequence& external) -> std::optional<Diagnostic> {
                if (external.stages.size()!=horizon)
                    return detail::invalid("problem.external.stages","Known external sequence must have T entries.");
                for (std::size_t i=0;i<external.stages.size();++i)
                    if (auto failure=detail::check_point(external.stages[i],dimension,detail::indexed("problem.external.stages",i))) return failure;
                return {};
            },
            [&](const ExogenousExternalInput& external) { return quantified(external); },
            [&](const AdversarialExternalInput& external) -> std::optional<Diagnostic> {
                if (auto failure=quantified(external)) return failure;
                if (external.semantics_reference.empty())
                    return detail::invalid("problem.external.semantics_reference","Adversarial input requires an explicit deferred semantics reference.");
                return {};
            }
        },*authored);
        if (error) return *error;
    }
    return ExternalData(std::make_shared<const detail::ExternalStorage>(detail::ExternalStorage{horizon,dimension,authored}));
}
} // namespace csl::problem
