#include "lp_report.hpp"
#include "process_counters.hpp"
#include <algorithm>
#include <charconv>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string_view>

using namespace csl::reporting;
namespace {
std::size_t positive(const char* text,std::size_t maximum) {
    std::size_t value=0; const std::string_view input(text);
    const auto parsed=std::from_chars(input.data(),input.data()+input.size(),value);
    if(parsed.ec!=std::errc{} || parsed.ptr!=input.data()+input.size() || value==0 || value>maximum)
        throw std::invalid_argument("positive bounded integer required");
    return value;
}
void event(const std::string& text) { std::cout<<text<<'\n'<<std::flush; }
std::string prefix(const char* type) { return "{\"schema\":\"csl.lp-report-events/1\",\"event\":"+json_string(type); }
}
int main(int argc,char** argv) {
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
        event(prefix("header")+",\"purpose\":"+json_string(purpose)+",\"repetitions\":"+std::to_string(count)+",\"warmups\":"+std::to_string(mode=="--measure"?warmups:0)+",\"build\":"+build_info_json()+",\"clock\":{\"is_steady\":"+(Clock::is_steady?"true":"false")+",\"period_num\":"+std::to_string(Clock::period::num)+",\"period_den\":"+std::to_string(Clock::period::den)+"},\"scenarios\":"+catalogue_json()+"}");
        if(mode=="--describe") return 0;
        if(mode=="--profile") {
            const auto before=process_counters();
            const auto begin=Clock::now();
            std::array<std::uint64_t,6> totals{};
            std::size_t failures=0;std::uint64_t observation=0;
            for(std::size_t r=0;r<rounds;++r) for(const auto& fixture:catalogue()) {
                const auto trial=run_trial(fixture,{});failures+=!trial.passed();observation=(observation^trial.observation)*UINT64_C(1099511628211);
                for(std::size_t i=0;i<totals.size();++i) if(trial.timings[i].available) totals[i]+=static_cast<std::uint64_t>(trial.timings[i].nanoseconds());
            }
            const auto end=Clock::now();const auto after=process_counters();
            std::string phases="[";for(std::size_t i=0;i<totals.size();++i) {if(i)phases+=',';phases+=std::to_string(totals[i]);}phases+=']';
            event(prefix("profile")+",\"purpose\":\"profile\",\"rounds\":"+std::to_string(rounds)+",\"trials\":"+std::to_string(rounds*catalogue().size())+",\"failures\":"+std::to_string(failures)+",\"observation_token\":"+json_string(std::to_string(observation))+",\"wall_ns\":"+std::to_string(std::chrono::duration_cast<std::chrono::nanoseconds>(end-begin).count())+",\"phase_totals_ns\":"+phases+",\"before\":"+counters_json(before)+",\"after\":"+counters_json(after)+",\"scope\":\"separate sequential fresh-workspace profile, no per-trial serialization; lifetime peak is not per-call memory\"}");
            return failures?2:0;
        }
        if(mode=="--measure") {
            auto minimum=std::numeric_limits<Clock::rep>::max();std::size_t positives=0;
            for(std::size_t i=0;i<10000;++i) {const auto a=Clock::now();const auto b=Clock::now();const auto delta=(b-a).count();if(delta>0){minimum=std::min(minimum,delta);++positives;}}
            event(prefix("calibration")+",\"purpose\":\"calibration\",\"clock_reads\":20000,\"positive_deltas\":"+std::to_string(positives)+",\"minimum_positive_ticks\":"+(positives?json_string(std::to_string(minimum)):"null")+",\"scope\":\"observed clock-read delta; not guaranteed resolution\"}");
        }
        std::size_t sequence=0,emitted=0,failures=0,warmup_failures=0;
        const auto emit_trial=[&](const Fixture& f,std::size_t round,const std::string& trial_purpose) {
            const auto trial=run_trial(f,{});
            const auto begin=Clock::now();
            const auto bytes=trial_json(f,trial,round,++sequence,trial_purpose);
            const auto end=Clock::now();
            event(prefix("trial")+",\"trial\":"+bytes+"}");
            event(prefix("serialization")+",\"sequence\":"+std::to_string(sequence)+",\"purpose\":"+json_string(trial_purpose)+",\"duration_ns\":"+std::to_string(std::chrono::duration_cast<std::chrono::nanoseconds>(end-begin).count())+",\"scope\":\"build trial JSON bytes; excludes event framing, write and flush\"}");
            return trial.passed();
        };
        if(mode=="--measure") for(const auto& f:catalogue()) warmup_failures+=!emit_trial(f,1,"warmup");
        for(std::size_t round=1;round<=count;++round) for(const auto& f:catalogue()) {failures+=!emit_trial(f,round,purpose);++emitted;}
        event(prefix("end")+",\"purpose\":"+json_string(purpose)+",\"emitted_trials\":"+std::to_string(emitted)+",\"failures\":"+std::to_string(failures)+",\"warmup_failures\":"+std::to_string(warmup_failures)+",\"complete\":true}");
        return failures||warmup_failures?2:0;
    } catch(const std::exception& error) {std::cerr<<"report driver: "<<error.what()<<'\n';return 3;}
}
