#include <csl/controllers/observed_replay.hpp>
#include <cmath>

namespace csl::controllers {
namespace {
Diagnostic invalid(std::string field, std::string explanation) {
    return {DiagnosticCode::invalid_input,std::move(field),std::move(explanation)};
}
bool finite(std::span<const double> values) {
    for (double value : values) if (!std::isfinite(value)) return false;
    return true;
}
bool same(ObservationPoint left, ObservationPoint right) {
    return left.stage.value==right.stage.value && left.timing==right.timing;
}
}

ReplayResult replay_observed_policy(const model::LinearSystem& system,
    const ReplayInputs& inputs,const Estimator& estimator,const Controller& controller) {
    if (!estimator || !controller)
        return invalid("controllers.callbacks","Estimator and controller callbacks are required.");
    const auto dimensions=system.dimensions();
    const auto horizon=system.horizon();
    if (inputs.initial_state.size()!=dimensions.state || !finite(inputs.initial_state))
        return invalid("controllers.initial_state","Initial state must be finite with the model state dimension.");
    if (inputs.external.size()!=horizon)
        return invalid("controllers.external","Supply one external vector for every transition.");
    for (const auto& external : inputs.external)
        if (external.size()!=dimensions.external || !finite(external))
            return invalid("controllers.external","External samples must be finite with the model external dimension.");
    if (inputs.measurement_errors.size()!=system.channel_count())
        return invalid("controllers.measurement_errors","Supply one error sequence for every declared channel.");
    std::vector<std::vector<model::ObservationRecord>> metadata;
    metadata.reserve(system.channel_count());
    for (std::size_t channel=0;channel<system.channel_count();++channel) {
        const auto count=system.sample_count({channel});
        if (const auto* error=std::get_if<Diagnostic>(&count)) return *error;
        const auto size=std::get<std::size_t>(count);
        if (inputs.measurement_errors[channel].size()!=size)
            return invalid("controllers.measurement_errors","Supply one error vector for every declared sample.");
        std::vector<model::ObservationRecord> records;
        records.reserve(size);
        for (std::size_t sample=0;sample<size;++sample) {
            auto record=system.observation({channel},{sample});
            if (const auto* error=std::get_if<Diagnostic>(&record)) return *error;
            const auto observed=std::get<model::ObservationRecord>(record);
            const auto& noise=inputs.measurement_errors[channel][sample];
            if (noise.size()!=observed.maps.error_map.cols() || !finite(noise))
                return invalid("model.observe.error","Measurement error must match the declared sample map and be finite.");
            records.push_back(observed);
        }
        metadata.push_back(std::move(records));
    }
    ReplayRecord record;
    record.inputs=inputs;
    record.states.push_back(inputs.initial_state);
    std::vector<Vector> controls;
    controls.reserve(horizon);
    const auto release=[&](ObservationPoint event) -> std::optional<ReplayResult> {
        for (std::size_t channel=0;channel<metadata.size();++channel)
            for (std::size_t sample=0;sample<metadata[channel].size();++sample) {
                const auto& source=metadata[channel][sample].metadata.sample;
                if (!same(source.available_at,event)) continue;
                const Vector empty;
                const Vector& control=source.input_stage ? controls[source.input_stage->value] : empty;
                const Vector& external=source.input_stage ? inputs.external[source.input_stage->value] : empty;
                auto evaluated=system.observe({channel},{sample},record.states[source.state_stage.value],
                    control,external,inputs.measurement_errors[channel][sample]);
                if (const auto* failure=std::get_if<Diagnostic>(&evaluated)) return ReplayResult{*failure};
                if (const auto* stopped=std::get_if<OperationStopped>(&evaluated)) return ReplayResult{*stopped};
                record.released.push_back({{channel},{sample},event,
                    std::get<model::ObservationValue>(std::move(evaluated))});
            }
        return {};
    };
    for (std::size_t stage=0;stage<horizon;++stage) {
        if (auto failure=release({{stage},ObservationTiming::before_decision})) return std::move(*failure);
        auto estimate=estimator({stage},record.released);
        if (estimate.size()!=dimensions.state || !finite(estimate))
            return invalid("controllers.estimate","State hypothesis must be finite with the model state dimension.");
        auto action=controller({stage},record.released,estimate);
        if (action.size()!=dimensions.control || !finite(action))
            return invalid("controllers.action","Selected action must be finite with the model control dimension.");
        record.decisions.push_back({{stage},record.released,estimate,action});
        controls.push_back(std::move(action));
        auto next=system.step({stage},record.states.back(),controls.back(),inputs.external[stage]);
        if (const auto* failure=std::get_if<Diagnostic>(&next)) return *failure;
        if (const auto* stopped=std::get_if<OperationStopped>(&next)) return *stopped;
        record.states.push_back(std::get<Vector>(std::move(next)));
        if (auto failure=release({{stage},ObservationTiming::after_decision})) return std::move(*failure);
    }
    if (auto failure=release({{horizon},ObservationTiming::before_decision})) return std::move(*failure);
    return record;
}
} // namespace csl::controllers
