#pragma once
#include <csl/contracts.hpp>
#include "process_counters.hpp"
#include <array>
#include <chrono>
#include <cstdint>
#include <stop_token>
#include <stdexcept>
#include <utility>
#include <algorithm>
#include <charconv>
#include <iostream>
#include <limits>
#include <string_view>
namespace csl::reporting {
using Clock = std::chrono::steady_clock;
struct Interval {
    bool available = false;
    bool includes_unwind = false;
    Clock::rep start = 0, end = 0;
    std::int64_t nanoseconds() const;
};
// The caller stamps success before its owners die. On failure the action's
// owners have unwound before this catch: retain that different scope explicitly.
template<class F> decltype(auto) record_failure_unwind(Interval& total,F&& action) {
    try { return std::forward<F>(action)(); }
    catch (...) {
        total.end=Clock::now().time_since_epoch().count();
        total.includes_unwind=true;
        throw;
    }
}

inline constexpr std::array<const char*,6> phases{"input_publication","registration_preparation","workspace_creation","public_run","independent_verification","end_to_end"};
Clock::rep now();
std::string diagnostic_text(const Diagnostics&);
std::string json_string(const std::string&);
std::string json_number(double);
std::string build_info_json();
bool close(double,double);
bool passes(const ResidualMeasure&,const ResidualContext&);
std::uint64_t observe(const ProgramOutcome&);
const char* outcome_name(MathematicalOutcome);
const char* termination_name(Termination);
std::string identity_json(const ProgramIdentity&);
std::string numbers(const Vector&);
std::string optional_number(const std::optional<double>&);
std::string primal_json(const std::optional<PrimalResiduals>&);
std::string dual_json(const std::optional<DualResiduals>&);
struct Rejected : std::runtime_error {
    Diagnostics diagnostics;
    explicit Rejected(Diagnostics);
};
template<class F> auto timed(Interval& span, F&& action) {
    span.available=true; span.start=now();
    try { auto value=action(); span.end=now(); return value; }
    catch (...) { span.end=now(); throw; }
}
template<class T, class... Rest> T accepted(std::variant<T,Rest...> value) {
    if (auto* result=std::get_if<T>(&value)) return std::move(*result);
    auto diagnostics=std::visit([](const auto& alternative)->Diagnostics {
        if constexpr(std::is_same_v<std::decay_t<decltype(alternative)>,Diagnostics>) return alternative;
        else if constexpr(std::is_same_v<std::decay_t<decltype(alternative)>,OperationStopped>) return {{DiagnosticCode::invalid_input,"report.publication",alternative.diagnostics}};
        else if constexpr(requires {alternative.diagnostics;}) return alternative.diagnostics;
        else return {};
    },value);
    throw Rejected(std::move(diagnostics));
}
template<class Range, class F> std::string array(const Range& values,F f) {
    std::string out="["; bool first=true;
    for (const auto& value:values) { if (!first) out+=','; first=false; out+=f(value); }
    return out+"]";
}
template<class Record> std::string trial_envelope(const std::string& case_id,const ProgramIdentity& id,const char* backend,const Record& r,const std::string& result,std::size_t round,std::size_t sequence,const std::string& purpose) {
    std::string timings="{";
    for (std::size_t i=0;i<phases.size();++i) {
        if(i) timings+=',';
        timings+=json_string(phases[i])+":";
        const auto& t=r.timings[i];
        timings+=t.available?"{\"available\":true,\"start_tick\":"+json_string(std::to_string(t.start))+",\"end_tick\":"+json_string(std::to_string(t.end))+",\"duration_ns\":"+std::to_string(t.nanoseconds())+",\"unit\":\"ns\",\"scope\":"+json_string(t.includes_unwind?"end_to_end_including_unwind":phases[i])+"}":"{\"available\":false,\"reason\":\"phase not reached\"}";
    }
    timings+='}';
    const auto actual=r.actual_version.empty()?"null":"{\"id\":"+json_string(backend)+",\"version\":"+json_string(r.actual_version)+"}";
    std::string attempt="null";
    if(r.attempt) attempt="{\"number\":"+std::to_string(r.attempt->stamp.attempt())+",\"state\":"+json_string(r.attempt->state==SolveAttemptState::returned_result?"returned_result":r.attempt->state==SolveAttemptState::unsupported?"unsupported":r.attempt->state==SolveAttemptState::exception?"exception":"running")+",\"workspace_reuse\":false}";
    const auto diagnostics=array(r.diagnostics,[](const auto& d){return "{\"code\":"+std::to_string(static_cast<int>(d.code))+",\"field\":"+json_string(d.field)+",\"explanation\":"+json_string(d.explanation)+"}";});
    return "{\"case_id\":"+json_string(case_id)+",\"round\":"+std::to_string(round)+",\"sequence\":"+std::to_string(sequence)+",\"purpose\":"+json_string(purpose)+",\"identity\":"+identity_json(id)+",\"registry\":{\"requested\":"+json_string(backend)+",\"actual\":"+actual+"},\"attempt\":"+attempt+",\"timings\":"+timings+",\"observation_token\":"+json_string(std::to_string(r.observation))+",\"harness\":{\"status\":"+json_string(r.harness_status)+",\"error\":"+(r.error.empty()?"null":json_string(r.error))+",\"diagnostics\":"+diagnostics+"},\"result\":"+result+",\"validation\":{\"passed\":"+(r.passed()?"true":"false")+",\"errors\":"+array(r.errors,[](const auto& x){return json_string(x);})+"}}";
}
inline std::size_t positive(const char* text,std::size_t maximum) {
    std::size_t value=0; const std::string_view input(text);
    const auto parsed=std::from_chars(input.data(),input.data()+input.size(),value);
    if(parsed.ec!=std::errc{} || parsed.ptr!=input.data()+input.size() || value==0 || value>maximum)
        throw std::invalid_argument("positive bounded integer required");
    return value;
}
inline void event(const std::string& text) { std::cout<<text<<'\n'<<std::flush; }
template<class Adapter> int report_main(int argc,char** argv) {
    const auto prefix=[](const char* type) { return "{\"schema\":"+json_string(Adapter::event_schema)+",\"event\":"+json_string(type); };
    try {
        if(argc<2) throw std::invalid_argument("expected --describe, --smoke, --measure or --profile");
        const std::string mode=argv[1];
        if(mode!="--describe" && mode!="--smoke" && mode!="--measure" && mode!="--profile") throw std::invalid_argument("unknown mode");
        std::size_t repetitions=7,warmups=1,rounds=1000;
        bool rep_seen=false,warm_seen=false,round_seen=false;
        for(int i=2;i<argc;++i) {
            const std::string option=argv[i];
            if(i+1>=argc) throw std::invalid_argument("missing option value");
            if(option=="--repetitions" && mode=="--measure" && !rep_seen) {repetitions=positive(argv[++i],1000);rep_seen=true;}
            else if(option=="--warmups" && mode=="--measure" && !warm_seen) {warmups=positive(argv[++i],1);warm_seen=true;}
            else if(option=="--rounds" && mode=="--profile" && !round_seen) {rounds=positive(argv[++i],10000);round_seen=true;}
            else throw std::invalid_argument("unknown, duplicate or inapplicable option");
        }
        if(mode=="--measure" && repetitions<5) throw std::invalid_argument("measurement requires at least five repetitions");
        std::cout.exceptions(std::ios::badbit|std::ios::failbit);
        const std::string purpose=mode=="--smoke"?"test":mode=="--measure"?"measurement":mode=="--profile"?"profile":"catalogue";
        const auto count=mode=="--smoke"?1:repetitions;
        event(prefix("header")+",\"purpose\":"+json_string(purpose)+",\"repetitions\":"+std::to_string(count)+",\"warmups\":"+std::to_string(mode=="--measure"?warmups:0)+",\"build\":"+build_info_json()+",\"clock\":{\"is_steady\":"+(Clock::is_steady?"true":"false")+",\"period_num\":"+std::to_string(Clock::period::num)+",\"period_den\":"+std::to_string(Clock::period::den)+"},\"scenarios\":"+Adapter::catalogue_json()+"}");
        if(mode=="--describe") return 0;
        if(mode=="--profile") {
            const auto before=process_counters();
            const auto begin=Clock::now();
            std::array<std::uint64_t,6> totals{};
            std::size_t failures=0;std::uint64_t observation=0;
            for(std::size_t r=0;r<rounds;++r) for(const auto& fixture:Adapter::catalogue()) {
                const auto trial=Adapter::run_trial(fixture,{});failures+=!trial.passed();observation=(observation^trial.observation)*UINT64_C(1099511628211);
                for(std::size_t i=0;i<totals.size();++i) if(trial.timings[i].available) totals[i]+=static_cast<std::uint64_t>(trial.timings[i].nanoseconds());
            }
            const auto end=Clock::now();const auto after=process_counters();
            std::string totals_json="[";for(std::size_t i=0;i<totals.size();++i) {if(i)totals_json+=',';totals_json+=std::to_string(totals[i]);}totals_json+=']';
            event(prefix("profile")+",\"purpose\":\"profile\",\"rounds\":"+std::to_string(rounds)+",\"trials\":"+std::to_string(rounds*Adapter::catalogue().size())+",\"failures\":"+std::to_string(failures)+",\"observation_token\":"+json_string(std::to_string(observation))+",\"wall_ns\":"+std::to_string(std::chrono::duration_cast<std::chrono::nanoseconds>(end-begin).count())+",\"phase_totals_ns\":"+totals_json+",\"before\":"+counters_json(before)+",\"after\":"+counters_json(after)+",\"scope\":\"separate sequential fresh-workspace profile, no per-trial serialization; lifetime peak is not per-call memory\"}");
            return failures?2:0;
        }
        if(mode=="--measure") {
            auto minimum=std::numeric_limits<Clock::rep>::max();std::size_t positives=0;
            for(std::size_t i=0;i<10000;++i) {const auto a=Clock::now();const auto b=Clock::now();const auto delta=(b-a).count();if(delta>0){minimum=std::min(minimum,delta);++positives;}}
            event(prefix("calibration")+",\"purpose\":\"calibration\",\"clock_reads\":20000,\"positive_deltas\":"+std::to_string(positives)+",\"minimum_positive_ticks\":"+(positives?json_string(std::to_string(minimum)):"null")+",\"scope\":\"observed clock-read delta; not guaranteed resolution\"}");
        }
        std::size_t sequence=0,emitted=0,failures=0,warmup_failures=0;
        const auto emit_trial=[&](const typename Adapter::Fixture& f,std::size_t round,const std::string& trial_purpose) {
            const auto trial=Adapter::run_trial(f,{});
            const auto begin=Clock::now();
            const auto bytes=Adapter::trial_json(f,trial,round,++sequence,trial_purpose);
            const auto end=Clock::now();
            event(prefix("trial")+",\"trial\":"+bytes+"}");
            event(prefix("serialization")+",\"sequence\":"+std::to_string(sequence)+",\"purpose\":"+json_string(trial_purpose)+",\"duration_ns\":"+std::to_string(std::chrono::duration_cast<std::chrono::nanoseconds>(end-begin).count())+",\"scope\":\"build trial JSON bytes; excludes event framing, write and flush\"}");
            return trial.passed();
        };
        if(mode=="--measure") for(const auto& f:Adapter::catalogue()) warmup_failures+=!emit_trial(f,1,"warmup");
        for(std::size_t round=1;round<=count;++round) for(const auto& f:Adapter::catalogue()) {failures+=!emit_trial(f,round,purpose);++emitted;}
        event(prefix("end")+",\"purpose\":"+json_string(purpose)+",\"emitted_trials\":"+std::to_string(emitted)+",\"failures\":"+std::to_string(failures)+",\"warmup_failures\":"+std::to_string(warmup_failures)+",\"complete\":true}");
        return failures||warmup_failures?2:0;
    } catch(const std::exception& error) {std::cerr<<"report driver: "<<error.what()<<'\n';return 3;}
}

} // namespace csl::reporting
