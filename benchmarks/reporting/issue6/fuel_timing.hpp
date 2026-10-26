#pragma once

#include <csl/artifacts/run_statistics.hpp>
#include <csl/execution/timing_collector.hpp>
#include <csl/optimization/finite_action_minimax.hpp>
#include <csl/problem/resolved_problem.hpp>
#include <csl/synthesis/contracts.hpp>
#include <nlohmann/json.hpp>

#include <algorithm>
#include <chrono>
#include <span>
#include <stdexcept>
#include <type_traits>

namespace csl::issue6::timing {
namespace ar = artifacts;
namespace ob = execution::observability;
using Json=nlohmann::json;

template<class T> T take(std::variant<T,Diagnostic> value) {
    if(const auto* error=std::get_if<Diagnostic>(&value))
        throw std::runtime_error(error->field+": "+error->explanation);
    return std::get<T>(std::move(value));
}
template<class T> T take_artifact(ar::ArtifactResult<T> value) {
    if(const auto* error=std::get_if<ar::ArtifactError>(&value))
        throw std::runtime_error(error->path+": "+error->message);
    return std::get<T>(std::move(value));
}

inline Matrix copy_matrix(const numeric::MatrixView& view) {
    Matrix result{view.rows(),view.cols(),{}};
    result.values.reserve(view.rows()*view.cols());
    for(std::size_t row=0;row<view.rows();++row)
        for(std::size_t column=0;column<view.cols();++column)
            result.values.push_back(view(row,column));
    return result;
}
inline Vector copy_vector(const numeric::VectorView& view) {
    return {view.values().begin(),view.values().end()};
}
inline std::pair<SystemModel,std::vector<double>> authored_model(const model::LinearSystem& system) {
    if(system.channel_count()!=0)
        throw std::runtime_error("Fuel minimax timing binding does not support observation channels");
    std::vector<LinearStage> stages;
    std::vector<double> times;
    stages.reserve(system.horizon());
    times.reserve(system.horizon()+1);
    for(std::size_t stage=0;stage<system.horizon();++stage) {
        const auto value=system.stage({stage});
        if(const auto* error=std::get_if<Diagnostic>(&value))
            throw std::runtime_error(error->field+": "+error->explanation);
        const auto& dynamics=std::get<model::DynamicsStage>(value);
        stages.push_back({copy_matrix(dynamics.A),copy_matrix(dynamics.B),
            copy_matrix(dynamics.E),copy_vector(dynamics.offset)});
        const auto time=system.time({stage});
        if(const auto* error=std::get_if<Diagnostic>(&time))
            throw std::runtime_error(error->field+": "+error->explanation);
        times.push_back(std::get<double>(time));
    }
    const auto terminal_time=system.time({system.horizon()});
    if(const auto* error=std::get_if<Diagnostic>(&terminal_time))
        throw std::runtime_error(error->field+": "+error->explanation);
    times.push_back(std::get<double>(terminal_time));
    return std::pair{SystemModel{Dynamics{system.dimensions(),TimeDomain::discrete,std::move(stages)},{}},
        std::move(times)};
}

inline TerminalObjective authored_objective(const optimization::Objective& objective) {
    return std::visit([](const auto& coefficients)->TerminalObjective {
        using T=std::decay_t<decltype(coefficients)>;
        if constexpr(std::is_same_v<T,optimization::LinearCoefficients>)
            return LinearTerminal{copy_vector(coefficients.coefficients),coefficients.offset};
        else if constexpr(std::is_same_v<T,optimization::QuadraticCoefficients>)
            return QuadraticTerminal{copy_matrix(coefficients.Q),copy_vector(coefficients.linear),coefficients.offset};
        else
            return ResidualNormTerminal{copy_matrix(coefficients.map),copy_vector(coefficients.target)};
    },objective.coefficients());
}

inline problem::ResolvedProblem resolve_problem(const optimization::FiniteActionMinimaxRequest& request) {
    auto [system,times]=authored_model(request.system);
    std::vector<AdmissibleSet> states;
    states.reserve(request.admissible_states.size());
    for(const auto& set:request.admissible_states)states.emplace_back(set.as_handle());
    std::vector<AdmissibleSet> disturbances;
    disturbances.reserve(request.disturbances.size());
    for(const auto& set:request.disturbances)disturbances.emplace_back(set.as_handle());
    const auto initial_representation=request.initial.representation();
    const auto* initial=std::get_if<sets::SingletonRepresentation>(&initial_representation);
    if(!initial)
        throw std::runtime_error("Fuel minimax timing binding requires the saved singleton initial set");
    Problem authored{request.problem,std::make_shared<const SystemModel>(std::move(system)),
        std::move(times),InitialSet{request.initial.as_handle(),SetQuantifier::universal},
        request.actions,std::move(states),{},
        AdversarialExternalInput{std::move(disturbances),SetQuantifier::universal,"fuel-disturbance-product"},
        InformationPattern::nominal_open_loop,authored_objective(request.objective)};
    const std::string semantics="Independent adversarial disturbance set at each modeled fuel stage.";
    const auto bytes=std::as_bytes(std::span{semantics.data(),semantics.size()});
    auto content=take(problem::snapshot_content(bytes));
    problem::ContentBinding binding{"fuel-disturbance-product",std::move(content),"benchmarks/reporting/issue6"};
    problem::ResolutionContext resolution{problem::UncertaintyStructure::stage_product_uncoupled,
        request.objective.policy(),std::span<const problem::ContentBinding>{&binding,1}};
    auto resolved=problem::resolve(authored,resolution);
    if(const auto* error=std::get_if<Diagnostic>(&resolved))
        throw std::runtime_error(error->field+": "+error->explanation);
    if(const auto* stop=std::get_if<OperationStopped>(&resolved))
        throw std::runtime_error(stop->diagnostics);
    return std::get<problem::ResolvedProblem>(std::move(resolved));
}

struct CollectorSetup {
    std::shared_ptr<ob::TimingCollector> collector;
    optimization::FiniteMinimaxTimingSpans spans;
    ar::ResolvedConfiguration configuration;
};
inline CollectorSetup make_collector(const optimization::FiniteActionMinimaxRequest&,
    std::size_t,std::string,std::string);

inline Termination outcome_termination(const optimization::FiniteActionMinimaxOutcome& outcome) {
    if(std::holds_alternative<Unsupported>(outcome))return Termination::operation_rejected;
    if(const auto* stop=std::get_if<OperationStopped>(&outcome)) {
        switch(stop->reason) {
        case StopReason::cancelled:return Termination::cancelled;
        case StopReason::deadline_expired:return Termination::deadline_expired;
        case StopReason::resource_limit:return Termination::resource_limit;
        case StopReason::numerical_failure:return Termination::numerical_failure;
        }
    }
    return Termination::completed;
}
struct TimedOutcome {
    optimization::FiniteActionMinimaxOutcome outcome;
    ob::TimingReport report;
    std::int64_t collector_setup_ns;
    std::int64_t solver_call_ns;
};
inline TimedOutcome run_enabled(const optimization::FiniteActionMinimaxRequest& request,
    optimization::FiniteActionMinimaxLimits limits,std::string run_id,std::string scenario_hash) {
    const auto setup_started=std::chrono::steady_clock::now();
    auto setup=make_collector(request,limits.max_plans,std::move(run_id),std::move(scenario_hash));
    const auto solver_started=std::chrono::steady_clock::now();
    ExecutionContext context;context.timing=setup.collector;
    context.resources=std::make_shared<const ResourcePolicy>(ResourcePolicy{1,1,1,{}});
    std::optional<ob::TimingScope> root;
    auto root_started=ob::start_timing(context,{0});
    if(auto* scope=std::get_if<ob::TimingScope>(&root_started))root.emplace(std::move(*scope));
    auto outcome=optimization::finite_action_minimax(request,limits,context,&setup.spans);
    const auto solver_stopped=std::chrono::steady_clock::now();
    if(root)root->close(outcome_termination(outcome));
    auto report_result=setup.collector->snapshot();
    if(const auto* error=std::get_if<ar::ArtifactError>(&report_result))
        throw std::runtime_error(error->path+": "+error->message);
    return {std::move(outcome),std::get<ob::TimingReport>(std::move(report_result)),
        std::chrono::duration_cast<std::chrono::nanoseconds>(solver_started-setup_started).count(),
        std::chrono::duration_cast<std::chrono::nanoseconds>(solver_stopped-solver_started).count()};
}

inline Json phase_json(const ob::TimingReport& report,std::int64_t collector_setup_ns,
    std::int64_t solver_call_ns) {
    if(!report.diagnostics.empty())
        throw std::runtime_error("OBS-06 timing report contains invalid or incomplete spans");
    const auto& collection=report.observations.description();
    const auto* complete=std::get_if<ar::Available<bool>>(&collection.complete);
    if(!complete || !complete->value)
        throw std::runtime_error("OBS-06 collection is not complete");
    Json observations=Json::array(),counts=Json::object();
    auto ticks=[](const auto& metric)->Json {
        if(const auto* value=std::get_if<ar::Available<std::uint64_t>>(&metric))return value->value;
        const auto& missing=std::get<ar::Unavailable>(metric);
        return {{"unavailable",static_cast<int>(missing.reason)},{"detail",missing.detail}};
    };
    auto raw_ticks=[](const ar::Metric<std::int64_t>& metric)->Json {
        if(const auto* value=std::get_if<ar::Available<std::int64_t>>(&metric))return value->value;
        return nullptr;
    };
    for(const auto& span:report.spans) {
        const auto& record=collection.spans.at(span.id.value);
        const auto& operation=record.descriptor.operation;
        auto& group=counts[operation];
        if(group.is_null())group={{"span_count",0},{"call_count",0},{"returned",0},{"rejected",0},{"not_called",0},
            {"failed",0},{"incomplete",0},
            {"wall_inclusive_ticks_sum",0},{"wall_exclusive_ticks_sum",0}};
        auto increment=[&](const char* key) {group[key]=group[key].get<std::uint64_t>()+1;};
        increment("span_count");
        const bool not_called=std::holds_alternative<ar::NotCalledObservation>(record.execution);
        if(not_called)increment("not_called");
        else {
            increment("call_count");
            if(std::holds_alternative<ar::ReturnedSpan>(record.status))increment("returned");
            else if(std::holds_alternative<ar::RejectedSpan>(record.status))increment("rejected");
            else if(std::holds_alternative<ar::FailedSpan>(record.status))increment("failed");
            else if(std::holds_alternative<ar::IncompleteSpan>(record.status))increment("incomplete");
        }
        if(const auto* value=std::get_if<ar::Available<std::uint64_t>>(&span.inclusive_wall_ticks))
            group["wall_inclusive_ticks_sum"]=group["wall_inclusive_ticks_sum"].get<std::uint64_t>()+value->value;
        if(const auto* value=std::get_if<ar::Available<std::uint64_t>>(&span.exclusive_wall_ticks))
            group["wall_exclusive_ticks_sum"]=group["wall_exclusive_ticks_sum"].get<std::uint64_t>()+value->value;
        const auto* interval=std::get_if<ar::TickInterval>(&record.interval);
        observations.push_back({{"id",span.id.value},{"operation",operation},
            {"parent_id",record.descriptor.parent?Json(record.descriptor.parent->id.value):Json(nullptr)},
            {"parent_kind",record.descriptor.parent?
                Json(record.descriptor.parent->kind==ar::ParentKind::nested?"nested":"spawned"):Json(nullptr)},
            {"plan_index",record.descriptor.query?Json(*record.descriptor.query):Json(nullptr)},
            {"stage",record.descriptor.stage?Json(*record.descriptor.stage):Json(nullptr)},
            {"start_tick",interval?raw_ticks(interval->start):Json(nullptr)},
            {"end_tick",interval?raw_ticks(interval->end):Json(nullptr)},
            {"execution",std::holds_alternative<ar::NotCalledObservation>(record.execution)?"not_called":
                std::holds_alternative<ar::ReturnedObservation>(record.execution)?"returned":"unknown"},
            {"not_called_reason",std::holds_alternative<ar::NotCalledObservation>(record.execution)?
                Json(static_cast<int>(std::get<ar::NotCalledObservation>(record.execution).reason)):Json(nullptr)},
            {"status",std::holds_alternative<ar::ReturnedSpan>(record.status)?"returned":
                std::holds_alternative<ar::RejectedSpan>(record.status)?"rejected":
                std::holds_alternative<ar::FailedSpan>(record.status)?"failed":"other"},
            {"wall_inclusive_ticks",ticks(span.inclusive_wall_ticks)},
            {"wall_exclusive_ticks",ticks(span.exclusive_wall_ticks)},
            {"cpu_ticks",ticks(span.cpu_ticks)}});
    }
    const auto& clock=collection.clocks.front();
    Json run_wall=nullptr;
    if(const auto* value=std::get_if<ar::Available<std::uint64_t>>(&report.run_wall_ticks))run_wall=value->value;
    Json worker_work=nullptr;
    if(const auto* value=std::get_if<ar::Available<std::uint64_t>>(&report.worker_work_ticks))worker_work=value->value;
    else worker_work={{"unavailable",static_cast<int>(
        std::get<ar::Unavailable>(report.worker_work_ticks).reason)}};
    return {{"schema","csl.obs06-fuel-phase/2"},{"span_count",observations.size()},
        {"span_count_is_planned_count",true},{"call_count_excludes_not_called_spans",true},
        {"counts_by_operation",std::move(counts)},
        {"wall_clock",{{"id",clock.id.value},{"period_numerator",clock.period_numerator},
            {"period_denominator",clock.period_denominator},{"origin_label",clock.origin_label}}},
        {"run_wall_ticks",std::move(run_wall)},{"spans",std::move(observations)},
        {"collector_setup_ns",collector_setup_ns},{"solver_call_wall_ns",solver_call_ns},
        {"worker_accounting",{{"requested_outer_workers",1},{"selected_worker_spans",0},
            {"native_backend_threads","not_applicable: no external numerical backend in this solver"}}},
        {"worker_work_ticks",std::move(worker_work)},
        {"cpu_time","not_supported: no CPU clock was supplied"}};
}

inline CollectorSetup make_collector(const optimization::FiniteActionMinimaxRequest& request,
    std::size_t plan_count,std::string run_id,std::string source_hash) {
    const auto resolved=resolve_problem(request);
    auto clock=ob::make_steady_timing_clock();
    const auto missing=ar::Unavailable{ar::MissingReason::not_instrumented,{}};
    constexpr std::string_view module="csl.optimization.finite-action-minimax";
    ar::ConfigurationInput config;
    const auto stride=4+request.system.horizon();
    config.collection={true,ar::CollectionMode::summary,
        static_cast<std::uint64_t>(3+stride*plan_count),256*1024*1024,0,0};
    ar::ModuleConfiguration module_config;
    module_config.role="strategy";
    module_config.implementation={ModuleId{std::string{module}},"1",missing};
    module_config.options.push_back({"scenario_sha256",
        ar::OptionValue{ar::OptionScalar{std::move(source_hash)}}});
    config.modules.push_back(std::move(module_config));
    config.numerical=request.objective.policy().numerical;
    config.resources={1,1,1,{}};
    config.output={ar::OutputKind::finite_minimax,Assurance::numerical,
        FamilyTarget::exact_optimal_relation,{"csl.set.v"},{0,0,{}, {}}};
    config.selector={{"csl.selector.none"},"1",{}};
    config.modules.push_back({"selector",{config.selector.id,config.selector.version,missing},{}});
    config.strategy={ModuleId{std::string{module}},{},{},{},{},{},{},config.selector.id,config.output.representation};
    config.workspace=ar::WorkspacePolicy::fresh;
    auto resolved_config=take_artifact(ar::resolve_configuration(std::move(config)));
    const ar::RunId run{std::move(run_id)};
    std::vector<ar::SpanDescriptor> descriptors;
    std::vector<std::string> operations{
        "finite-minimax/run","finite-minimax/validation","finite-minimax/plan-setup",
        "finite-minimax/propagation","finite-minimax/stage-materialization","finite-minimax/objective",
        "finite-minimax/record-assembly","finite-minimax/result-selection"};
    const auto count=3+stride*plan_count;
    descriptors.reserve(count);
    auto add=[&](std::size_t id,std::string operation,std::optional<std::uint64_t> query={},
        std::optional<ar::SpanId> parent={},std::optional<std::uint64_t> stage={}) {
        ar::SpanDescriptor span{};
        span.id={id};span.parent=ar::SpanParent{parent.value_or(ar::SpanId{0}),ar::ParentKind::nested};
        span.task="finite-minimax";span.operation=std::move(operation);
        span.query=query;span.stage=stage;
        span.module={ModuleId{std::string{module}},"1",missing};
        span.observation_source="csl.optimization.finite_action_minimax";
        span.clock=clock->wall_domain().id;
        span.requested_assurance=Assurance::numerical;
        span.applied_assurance=ar::Available<Assurance>{Assurance::numerical};
        descriptors.push_back(std::move(span));
    };
    add(1,"finite-minimax/validation");
    for(std::size_t plan=0;plan<plan_count;++plan) {
        const auto first=2+stride*plan;
        add(first,"finite-minimax/plan-setup",plan);
        add(first+1,"finite-minimax/propagation",plan);
        for(std::size_t stage=0;stage<request.system.horizon();++stage)
            add(first+2+stage,"finite-minimax/stage-materialization",plan,ar::SpanId{first+1},stage+1);
        add(first+2+request.system.horizon(),"finite-minimax/objective",plan);
        add(first+3+request.system.horizon(),"finite-minimax/record-assembly",plan);
    }
    add(2+stride*plan_count,"finite-minimax/result-selection");
    ar::SpanDescriptor root{};
    root.id={0};root.task="finite-minimax";root.operation="finite-minimax/run";
    root.module={ModuleId{std::string{module}},"1",missing};
    root.observation_source="csl.optimization.finite_action_minimax";
    root.clock=clock->wall_domain().id;root.requested_assurance=Assurance::numerical;
    root.applied_assurance=ar::Available<Assurance>{Assurance::numerical};
    descriptors.push_back(std::move(root));
    std::sort(descriptors.begin(),descriptors.end(),[](const auto& lhs,const auto& rhs){return lhs.id.value<rhs.id.value;});
    ob::PlanInput plan{resolved,resolved_config,run,{clock->wall_domain()},std::move(descriptors),1,
        {"finite-minimax"},std::move(operations)};
    auto collection_plan=take_artifact(ob::make_collection_plan(std::move(plan)));
    auto collector=take_artifact(ob::make_timing_collector(std::move(collection_plan),clock,{0},{}));
    optimization::FiniteMinimaxTimingSpans spans;
    spans.validation={1};spans.plans.resize(plan_count);
    for(std::size_t index=0;index<plan_count;++index) {
        const auto first=2+stride*index;
        auto& current=spans.plans[index];
        current.plan_setup={first};current.propagation={first+1};
        for(std::size_t stage=0;stage<request.system.horizon();++stage)
            current.stage_materialization.push_back({first+2+stage});
        current.objective={first+2+request.system.horizon()};
        current.record_assembly={first+3+request.system.horizon()};
    }
    spans.result_selection={2+stride*plan_count};
    return {std::move(collector),std::move(spans),std::move(resolved_config)};
}
} // namespace csl::issue6::timing
