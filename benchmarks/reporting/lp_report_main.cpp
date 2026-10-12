#include "lp_report.hpp"
namespace {
struct LPAdapter {
    using Fixture=csl::reporting::Fixture;
    static constexpr const char* event_schema="csl.lp-report-events/1";
    static const auto& catalogue() {return csl::reporting::catalogue();}
    static auto catalogue_json() {return csl::reporting::catalogue_json();}
    static auto run_trial(const Fixture& f,std::stop_token s) {return csl::reporting::run_trial(f,s);}
    static auto trial_json(const Fixture& f,const csl::reporting::TrialRecord& r,std::size_t round,std::size_t sequence,const std::string& purpose) {return csl::reporting::trial_json(f,r,round,sequence,purpose);}
};
}
int main(int argc,char** argv) {return csl::reporting::report_main<LPAdapter>(argc,argv);}
