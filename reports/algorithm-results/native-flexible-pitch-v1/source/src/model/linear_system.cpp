#include <csl/model/linear_system.hpp>

#include <algorithm>
#include <cmath>
#include <initializer_list>
#include <utility>

namespace csl::model {
namespace detail {
struct ChannelStorage {
    std::variant<ObservationMaps, std::vector<ObservationMaps>> coefficients;
    std::vector<ObservationMetadata> samples;
};
struct SystemStorage {
    Dimensions dimensions;
    Vector times;
    std::variant<DynamicsStage, std::vector<DynamicsStage>> coefficients;
    std::vector<ChannelStorage> observations;
};
} // namespace detail
namespace {
Diagnostic invalid(const char* field, const char* explanation) {
    return {DiagnosticCode::invalid_input, field, explanation};
}
template<class T>
const T& at(const std::variant<T, std::vector<T>>& provider, std::size_t index) {
    if (const auto* constant = std::get_if<T>(&provider)) return *constant;
    return std::get<std::vector<T>>(provider)[index];
}
bool shape(const Matrix& matrix, std::size_t rows, std::size_t cols) {
    return matrix.rows == rows && matrix.cols == cols;
}
Result<DynamicsStage> freeze(const LinearStage& authored, Dimensions d) {
    const auto failure = invalid("model.dynamics.coefficients", "Expected finite A(n,n), B(n,m), E(n,p), offset(n) with valid storage");
    if (!shape(authored.A,d.state,d.state) || !shape(authored.B,d.state,d.control) ||
        !shape(authored.E,d.state,d.external) || authored.offset.size() != d.state) return failure;
    auto a = numeric::snapshot(authored.A);
    auto b = numeric::snapshot(authored.B);
    auto e = numeric::snapshot(authored.E);
    auto offset = numeric::snapshot_vector(authored.offset);
    if (std::holds_alternative<Diagnostic>(a) || std::holds_alternative<Diagnostic>(b) ||
        std::holds_alternative<Diagnostic>(e) || std::holds_alternative<Diagnostic>(offset)) return failure;
    return DynamicsStage{std::get<numeric::MatrixView>(a),std::get<numeric::MatrixView>(b),
        std::get<numeric::MatrixView>(e),std::get<numeric::VectorView>(offset)};
}
Result<ObservationMaps> freeze(const ObservationStage& authored, Dimensions d) {
    const auto failure = invalid("model.observation.coefficients", "Expected finite C(r,n), Du(r,m), Dw(r,p), F(r,q), offset(r) with valid storage");
    const auto r = authored.state_map.rows;
    if (!shape(authored.state_map,r,d.state) || !shape(authored.control_map,r,d.control) ||
        !shape(authored.external_map,r,d.external) || authored.error_map.rows != r ||
        authored.offset.size() != r) return failure;
    auto c = numeric::snapshot(authored.state_map);
    auto du = numeric::snapshot(authored.control_map);
    auto dw = numeric::snapshot(authored.external_map);
    auto f = numeric::snapshot(authored.error_map);
    auto offset = numeric::snapshot_vector(authored.offset);
    if (std::holds_alternative<Diagnostic>(c) || std::holds_alternative<Diagnostic>(du) ||
        std::holds_alternative<Diagnostic>(dw) || std::holds_alternative<Diagnostic>(f) ||
        std::holds_alternative<Diagnostic>(offset)) return failure;
    return ObservationMaps{std::get<numeric::MatrixView>(c),std::get<numeric::MatrixView>(du),
        std::get<numeric::MatrixView>(dw),std::get<numeric::MatrixView>(f),std::get<numeric::VectorView>(offset)};
}
template<class Output, class Input>
Result<std::variant<Output,std::vector<Output>>> freeze_provider(
    const std::variant<Input,std::vector<Input>>& provider, std::size_t count, Dimensions d, const char* field) {
    using Provider = std::variant<Output,std::vector<Output>>;
    if (const auto* constant = std::get_if<Input>(&provider)) {
        auto result = freeze(*constant,d);
        if (const auto* error = std::get_if<Diagnostic>(&result)) return *error;
        return Provider{std::get<Output>(std::move(result))};
    }
    const auto& authored = std::get<std::vector<Input>>(provider);
    if (authored.size() != count) return invalid(field,"Indexed coefficient count must match its stages or samples");
    std::vector<Output> records;
    records.reserve(count);
    for (const auto& record : authored) {
        auto result = freeze(record,d);
        if (const auto* error = std::get_if<Diagnostic>(&result)) return *error;
        records.push_back(std::get<Output>(std::move(result)));
    }
    return Provider{std::move(records)};
}
bool valid_point(ObservationPoint point, std::size_t horizon) {
    switch (point.timing) {
    case ObservationTiming::before_decision: return point.stage.value <= horizon;
    case ObservationTiming::after_decision: return point.stage.value < horizon;
    }
    return false;
}
// Called only with validated phases. No stage arithmetic or timestamp comparison.
bool precedes(ObservationPoint left, ObservationPoint right) {
    if (left.stage.value != right.stage.value) return left.stage.value < right.stage.value;
    return left.timing == ObservationTiming::before_decision && right.timing == ObservationTiming::after_decision;
}
double event_time(ObservationPoint point, std::span<const double> times) {
    return times[point.stage.value + (point.timing == ObservationTiming::after_decision ? 1 : 0)];
}
bool zero(const numeric::MatrixView& matrix) {
    for (std::size_t row = 0; row < matrix.rows(); ++row)
        for (std::size_t col = 0; col < matrix.cols(); ++col)
            if (matrix(row,col) != 0) return false;
    return true;
}
Result<detail::ChannelStorage> freeze_channel(const Observation& channel, Dimensions d, std::span<const double> times) {
    auto provider = freeze_provider<ObservationMaps>(channel.coefficients,channel.schedule.size(),d,"model.observation.coefficients");
    if (const auto* error = std::get_if<Diagnostic>(&provider)) return *error;
    auto coefficients = std::get<std::variant<ObservationMaps,std::vector<ObservationMaps>>>(std::move(provider));
    if (const auto* indexed = std::get_if<std::vector<ObservationMaps>>(&coefficients); indexed && !indexed->empty()) {
        for (const auto& record : *indexed)
            if (record.state_map.rows() != indexed->front().state_map.rows() || record.error_map.cols() != indexed->front().error_map.cols())
                return invalid("model.observation.coefficients","Channel output and error dimensions must be constant across samples");
    }
    const auto horizon = times.size()-1;
    std::vector<ObservationMetadata> samples;
    samples.reserve(channel.schedule.size());
    const bool constant = std::holds_alternative<ObservationMaps>(coefficients);
    std::optional<bool> constant_zero_feedthrough;
    for (std::size_t i = 0; i < channel.schedule.size(); ++i) {
        const auto& sample = channel.schedule[i];
        if (sample.state_stage.value > horizon || !valid_point(sample.measured_at,horizon) ||
            !valid_point(sample.available_at,horizon) || (sample.input_stage && sample.input_stage->value >= horizon))
            return invalid("model.observation.schedule","State/input stages or event phases are outside this grid");
        const ObservationPoint state_release = sample.state_stage.value == 0
            ? ObservationPoint{{0},ObservationTiming::before_decision}
            : ObservationPoint{{sample.state_stage.value-1},ObservationTiming::after_decision};
        if (precedes(sample.measured_at,state_release) || precedes(sample.available_at,sample.measured_at) ||
            (sample.input_stage && precedes(sample.measured_at,{*sample.input_stage,ObservationTiming::after_decision})))
            return invalid("model.observation.causality","Measurement must follow source release and availability must follow measurement");
        const auto& maps = at(coefficients,i);
        if (!sample.input_stage) {
            if (constant && !constant_zero_feedthrough)
                constant_zero_feedthrough = zero(maps.control_map) && zero(maps.external_map);
            const bool zero_feedthrough = constant ? *constant_zero_feedthrough
                : zero(maps.control_map) && zero(maps.external_map);
            if (!zero_feedthrough)
                return invalid("model.observation.coefficients","Feedthrough without a declared input stage must be zero");
        }
        samples.push_back({sample,times[sample.state_stage.value],event_time(sample.measured_at,times),event_time(sample.available_at,times)});
    }
    return detail::ChannelStorage{std::move(coefficients),std::move(samples)};
}
bool valid_vector(std::span<const double> input, std::size_t size) {
    return input.size() == size && std::all_of(input.begin(),input.end(),[](double v) { return std::isfinite(v); });
}
struct Term { const numeric::MatrixView& matrix; std::span<const double> input; const char* name; };
EvaluationResult<Vector> evaluate(const numeric::VectorView& offset, std::initializer_list<Term> terms, const char* operation) {
    Vector result(offset.size(),0);
    for (std::size_t row = 0; row < result.size(); ++row) {
        double sum = 0;
        for (const auto& term : terms) {
            for (std::size_t col = 0; col < term.input.size(); ++col) {
                const double product = term.matrix(row,col)*term.input[col];
                if (!std::isfinite(product)) return OperationStopped{StopReason::numerical_failure,
                    std::string(operation)+" nonfinite product in "+term.name+" row "+std::to_string(row)+" column "+std::to_string(col)};
                sum += product;
                if (!std::isfinite(sum)) return OperationStopped{StopReason::numerical_failure,
                    std::string(operation)+" nonfinite sum in "+term.name+" row "+std::to_string(row)};
            }
        }
        sum += offset[row];
        if (!std::isfinite(sum)) return OperationStopped{StopReason::numerical_failure,
            std::string(operation)+" nonfinite offset sum at row "+std::to_string(row)};
        result[row] = sum;
    }
    return result;
}
} // namespace

LinearSystem::LinearSystem(std::shared_ptr<const detail::SystemStorage> storage) : storage_(std::move(storage)) {}
Dimensions LinearSystem::dimensions() const noexcept { return storage_->dimensions; }
std::size_t LinearSystem::horizon() const noexcept { return storage_->times.size()-1; }
Result<double> LinearSystem::time(StageIndex index) const {
    if (index.value > horizon()) return invalid("model.time","Expected a state time in [0,T]");
    return storage_->times[index.value];
}
Result<DynamicsStage> LinearSystem::stage(StageIndex index) const {
    if (index.value >= horizon()) return invalid("model.stage","Expected a transition stage in [0,T)");
    return at(storage_->coefficients,index.value);
}
std::size_t LinearSystem::channel_count() const noexcept { return storage_->observations.size(); }
Result<std::size_t> LinearSystem::sample_count(ObservationIndex channel) const {
    if (channel.value >= channel_count()) return invalid("model.observation.channel","Observation channel is out of range");
    return storage_->observations[channel.value].samples.size();
}
Result<ObservationRecord> LinearSystem::observation(ObservationIndex channel, SampleIndex sample) const {
    auto count = sample_count(channel);
    if (const auto* error = std::get_if<Diagnostic>(&count)) return *error;
    if (sample.value >= std::get<std::size_t>(count)) return invalid("model.observation.sample","Observation sample is out of range");
    const auto& storage = storage_->observations[channel.value];
    return ObservationRecord{at(storage.coefficients,sample.value),storage.samples[sample.value]};
}
EvaluationResult<Vector> LinearSystem::step(StageIndex index, std::span<const double> x,
    std::span<const double> u, std::span<const double> w) const {
    const auto record = stage(index);
    if (const auto* error = std::get_if<Diagnostic>(&record)) return *error;
    const auto d = dimensions();
    if (!valid_vector(x,d.state)) return invalid("model.step.state","Expected a finite state vector of dimension n");
    if (!valid_vector(u,d.control)) return invalid("model.step.control","Expected a finite control vector of dimension m");
    if (!valid_vector(w,d.external)) return invalid("model.step.external","Expected a finite external vector of dimension p");
    const auto& maps = std::get<DynamicsStage>(record);
    return evaluate(maps.offset,{{maps.A,x,"A*x"},{maps.B,u,"B*u"},{maps.E,w,"E*w"}},"step");
}
EvaluationResult<ObservationValue> LinearSystem::observe(ObservationIndex channel, SampleIndex sample,
    std::span<const double> x, std::span<const double> u, std::span<const double> w, std::span<const double> v) const {
    const auto record = observation(channel,sample);
    if (const auto* error = std::get_if<Diagnostic>(&record)) return *error;
    const auto& view = std::get<ObservationRecord>(record);
    const auto& maps = view.maps;
    const auto d = dimensions();
    const bool has_inputs = view.metadata.sample.input_stage.has_value();
    if (!valid_vector(x,d.state)) return invalid("model.observe.state","Expected a finite state vector of dimension n");
    if (!valid_vector(u,has_inputs ? d.control : 0)) return invalid("model.observe.control","Expected declared input-stage control or an empty vector");
    if (!valid_vector(w,has_inputs ? d.external : 0)) return invalid("model.observe.external","Expected declared input-stage external input or an empty vector");
    if (!valid_vector(v,maps.error_map.cols())) return invalid("model.observe.error","Expected a finite measurement error vector of dimension q");
    auto result = evaluate(maps.offset,{{maps.state_map,x,"C*x"},{maps.control_map,u,"Du*u"},
        {maps.external_map,w,"Dw*w"},{maps.error_map,v,"F*v"}},"observe");
    if (const auto* stop = std::get_if<OperationStopped>(&result)) return *stop;
    if (const auto* error = std::get_if<Diagnostic>(&result)) return *error;
    return ObservationValue{std::get<Vector>(std::move(result)),view.metadata};
}
Result<LinearSystem> snapshot(const SystemModel& authored, std::span<const double> times) {
    if (authored.dynamics.time_domain != TimeDomain::discrete)
        return Diagnostic{DiagnosticCode::unsupported,"model.time_domain","Only supplied discrete-time transitions are supported; no discretization is performed"};
    if (times.empty()) return invalid("model.times","Expected at least one finite state time");
    for (std::size_t i = 0; i < times.size(); ++i)
        if (!std::isfinite(times[i]) || (i > 0 && !(times[i-1] < times[i])))
            return invalid("model.times","State times must be finite and strictly increasing");
    const auto d = authored.dynamics.dimensions;
    auto provider = freeze_provider<DynamicsStage>(authored.dynamics.stages,times.size()-1,d,"model.dynamics.coefficients");
    if (const auto* error = std::get_if<Diagnostic>(&provider)) return *error;
    std::vector<detail::ChannelStorage> channels;
    channels.reserve(authored.observations.size());
    for (const auto& channel : authored.observations) {
        auto frozen = freeze_channel(channel,d,times);
        if (const auto* error = std::get_if<Diagnostic>(&frozen)) return *error;
        channels.push_back(std::get<detail::ChannelStorage>(std::move(frozen)));
    }
    return LinearSystem{std::make_shared<const detail::SystemStorage>(detail::SystemStorage{
        d,Vector(times.begin(),times.end()),
        std::get<std::variant<DynamicsStage,std::vector<DynamicsStage>>>(std::move(provider)),std::move(channels)})};
}
} // namespace csl::model
