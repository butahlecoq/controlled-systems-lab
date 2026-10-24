#include <csl/synthesis/finite_action_histories.hpp>

#include <algorithm>
#include <cmath>
#include <new>
#include <stdexcept>
#include <string>

namespace csl::synthesis {
namespace {
Diagnostics invalid(std::string field,std::string message) {
    return {{DiagnosticCode::invalid_input,std::move(field),std::move(message)}};
}
Diagnostics capacity(std::string field,std::string message) {
    return {{DiagnosticCode::unsupported,std::move(field),std::move(message)}};
}
}

FiniteActionHistoryCursor::FiniteActionHistoryCursor(std::size_t catalogue_size,std::size_t horizon)
    :catalogue_size_(catalogue_size),choices_(horizon),complete_(horizon!=0 && catalogue_size==0) {}

void FiniteActionHistoryCursor::advance() noexcept {
    for(std::size_t stage=choices_.size();stage>0;--stage) {
        if(++choices_[stage-1]<catalogue_size_)return;
        choices_[stage-1]=0;
    }
    complete_=true;
}

std::variant<FiniteActionHistoryCursor,Diagnostics> FiniteActionHistoryCursor::prepare(
        const FiniteDomain& domain,std::size_t horizon) {
    for(const auto& action:domain.catalogue) {
        if(action.size()!=domain.dimension)
            return invalid("finite_history.action_dimension","Every catalogue row must match its declared dimension.");
        for(const auto value:action)
            if(!std::isfinite(value))
                return invalid("finite_history.action_value","Every catalogue value must be finite.");
    }
    if(horizon>std::vector<std::size_t>{}.max_size())
        return capacity("finite_history.horizon","The action history exceeds vector capacity.");
    try {
        return FiniteActionHistoryCursor(domain.catalogue.size(),horizon);
    } catch(const std::bad_alloc&) {
        return capacity("finite_history.capacity","The action history could not be allocated.");
    } catch(const std::length_error&) {
        return capacity("finite_history.capacity","The action history exceeds vector capacity.");
    }
}

FiniteActionHistoryPrefix FiniteActionHistoryCursor::take_prefix(std::size_t max_histories) {
    FiniteActionHistoryPrefix prefix;
    if(max_histories==0 || complete_) {
        prefix.complete=complete_;
        return prefix;
    }
    const auto available=std::min(max_histories,prefix.histories.max_size());
    prefix.histories.reserve(available);
    while(prefix.histories.size()<available && !complete_) {
        prefix.histories.push_back({choices_});
        advance();
    }
    prefix.complete=complete_;
    return prefix;
}

} // namespace csl::synthesis
