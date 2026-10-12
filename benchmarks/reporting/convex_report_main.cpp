#include "convex_report.hpp"
namespace {
struct ConvexAdapter {
    using Fixture=csl::reporting::convex::Fixture;
    static constexpr const char* event_schema="csl.convex-report-events/1";
    static const auto& catalogue() {return csl::reporting::convex::catalogue();}
    static auto catalogue_json() {return csl::reporting::convex::catalogue_json();}
    static auto run_trial(const Fixture& f,std::stop_token s) {return csl::reporting::convex::run_trial(f,s);}
    static auto trial_json(const Fixture& f,const csl::reporting::convex::TrialRecord& r,std::size_t round,std::size_t sequence,const std::string& purpose) {return csl::reporting::convex::trial_json(f,r,round,sequence,purpose);}
};
}
int main(int argc,char** argv) {return csl::reporting::report_main<ConvexAdapter>(argc,argv);}
