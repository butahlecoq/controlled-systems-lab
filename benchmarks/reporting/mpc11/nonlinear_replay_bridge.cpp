#include <csl/simulation/nonlinear_replay.hpp>
#include <nlohmann/json.hpp>
#include <cmath>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <stop_token>
using Json=nlohmann::json;
using csl::Vector;

int main(int argc,char** argv) {
    try {
        if(argc!=2) throw std::invalid_argument("usage: csl_mpc11_nonlinear_replay request.json");
        std::ifstream input(argv[1]);const auto request=Json::parse(input);const auto& s=request.at("scenario");
        const auto case_id=s.at("case_id").get<std::string>();
        if(case_id!="SYN-NL-LV-01" && case_id!="SYN-NL-FUEL-01")throw std::invalid_argument("unsupported synthetic case");
        if(request.at("hold")!="constant-on-original-interval")throw std::invalid_argument("unsupported hold");
        const std::size_t state_width=case_id=="SYN-NL-LV-01" ? 2 : 4;
        const std::size_t control_width=case_id=="SYN-NL-LV-01" ? 1 : 2;
        if(!s.at("states").is_array() || s.at("states").size()!=state_width ||
            !s.at("controls").is_array() || s.at("controls").size()!=control_width)
            throw std::invalid_argument("case-fixed state/control declarations have wrong dimensions");
        const auto finite_vector=[](const Json& values,std::size_t width) {
            if(!values.is_array() || values.size()!=width)return false;
            for(const auto& value:values)if(!value.is_number() || !std::isfinite(value.get<double>()))return false;
            return true;
        };
        if(!finite_vector(request.at("initial_scaled"),state_width))throw std::invalid_argument("initial state width or finiteness");
        for(const auto& state:s.at("states")) {
            const auto& value=state.at("scale");
            if(!value.is_number() || !std::isfinite(value.get<double>()) || value.get<double>()<=0)
                throw std::invalid_argument("state scales must be finite and positive");
        }
        for(const char* key:{"original_controls","controls"}) {
            if(!request.at(key).is_array())throw std::invalid_argument("control history must be an array");
            for(const auto& row:request.at(key))if(!finite_vector(row,control_width))
                throw std::invalid_argument("case-fixed control row width or finiteness");
        }
        const auto count=s.at("time").at("intervals").get<std::size_t>();
        const auto sub=request.at("report_subintervals_per_hold").get<std::size_t>();
        if(sub!=s.at("independent_replay").at("report_subintervals_per_hold").get<std::size_t>())throw std::invalid_argument("report grid mismatch");
        const auto controls=request.at("controls").get<std::vector<Vector>>();
        const auto original=request.at("original_controls").get<std::vector<Vector>>();
        const auto times=request.at("times").get<Vector>();const auto grid=s.at("time").at("grid").get<Vector>();
        if(sub==0 || original.size()!=count || grid.size()!=count+1 || times.size()!=count*sub+1 || controls.size()+1!=times.size())throw std::invalid_argument("incomplete hold association");
        for(std::size_t k=0;k<count;++k)for(std::size_t j=0;j<sub;++j) {
            if(controls[k*sub+j]!=original[k] || std::abs(times[k*sub+j]-(grid[k]+(grid[k+1]-grid[k])*static_cast<double>(j)/static_cast<double>(sub)))>1e-13)
                throw std::invalid_argument("hold/grid association mismatch");
        }
        if(times.back()!=grid.back())throw std::invalid_argument("terminal time mismatch");
        csl::simulation::Plant plant;
        plant.identity={s.at("model_id"),"1","authored synthetic MPC-11 original ODE; independent C++ callback"};
        plant.parameters.emplace();
        for(auto it=s.at("parameters").begin();it!=s.at("parameters").end();++it)
            plant.parameters->push_back({it.key(),it.value().at("value"),it.value().at("unit")});
        Vector scales;
        for(const auto& state:s.at("states")){scales.push_back(state.at("scale"));plant.state_units.push_back("1 (scaled from "+state.at("unit").get<std::string>()+")");}
        for(const auto& control:s.at("controls"))plant.control_units.push_back(control.at("unit"));
        plant.initial_state=request.at("initial_scaled").get<Vector>();plant.times=times;
        plant.time_unit=s.at("time").at("unit");plant.objective_name="scaled terminal squared norm; authored cost reconstructed externally";plant.objective_unit="1";
        plant.integration=csl::simulation::IntegrationMethod::adaptive_rk4_step_doubling;
        plant.hold=csl::simulation::ControlHold::constant_on_interval;
        plant.integration_limits=csl::simulation::IntegrationLimits{request.at("abstol"),request.at("reltol"),request.at("max_attempts")};
        const auto parameter=[&](const char* key){return s.at("parameters").at(key).at("value").get<double>();};
        if(case_id=="SYN-NL-LV-01") {
            const double a=parameter("a"),b=parameter("b"),c=parameter("c"),d=parameter("d");
            plant.dynamics=[=](double,std::span<const double> z,std::span<const double> u,std::span<const csl::simulation::PlantParameter>){
                const double prey=z[0]*scales[0],predator=z[1]*scales[1];
                return Vector{(a-b*predator-u[0])*prey/scales[0],(d*prey-c)*predator/scales[1]};};
        } else {
            const double qo=parameter("Q_ox"),qf=parameter("Q_f"),to=parameter("tau_ox"),tf=parameter("tau_f"),mo=parameter("m_ox0"),mf=parameter("m_f0");
            plant.dynamics=[=](double,std::span<const double> z,std::span<const double> u,std::span<const csl::simulation::PlantParameter>){
                Vector x(z.begin(),z.end());for(std::size_t i=0;i<x.size();++i)x[i]*=scales[i];
                if(x[0]<0 || x[1]<0)throw std::domain_error("negative synthetic fuel mass");
                return Vector{-x[2]/scales[0],-x[3]/scales[1],(qo*u[0]*std::sqrt(x[0]/mo)-x[2])/to/scales[2],(qf*u[1]*std::sqrt(x[1]/mf)-x[3])/tf/scales[3]};};
        }
        plant.objective=[](std::span<const double> x,std::span<const csl::simulation::PlantParameter>){double value=0;for(double v:x)value+=v*v;return value;};
        std::stop_source stop;csl::ExecutionContext context;
        if(request.value("cancel_before_start",false)){stop.request_stop();context.cancellation=stop.get_token();}
        const auto record=csl::simulation::replay(plant,controls,context);
        const char* statuses[]={"complete","unavailable","invalid_input","numerical_failure","callback_failure","cancelled","resource_limit"};
        Json output={{"schema","csl.mpc11.independent-replay/1"},{"provider","CSL::simulation"},{"method","adaptive-rk4-step-doubling"},
            {"status",statuses[static_cast<int>(record.status)]},{"scenario_sha256",request.at("scenario_sha256")},{"witness_sha256",request.at("witness_sha256")},
            {"controls_sha256",request.at("controls_sha256")},{"scaled_states",record.states},{"declared_times",record.times},
            {"abstol",request.at("abstol")},{"reltol",request.at("reltol")},{"elapsed_seconds",std::chrono::duration<double>(record.replay_time).count()}};
        output["times"]=Vector(times.begin(),times.begin()+static_cast<std::ptrdiff_t>(record.states.size()));
        output["physical_states"]=Json::array();for(auto x:record.states){for(std::size_t i=0;i<x.size();++i)x[i]*=scales[i];output["physical_states"].push_back(x);}
        output["integration_receipts"]=Json::array();for(const auto& r:record.integration_receipts)output["integration_receipts"].push_back({{"accepted_steps",r.accepted_steps},{"rejected_steps",r.rejected_steps},{"max_accepted_local_error_estimates",r.max_accepted_local_error_estimates}});
        output["diagnostics"]=Json::array();for(const auto& d:record.diagnostics)output["diagnostics"].push_back({{"field",d.field},{"explanation",d.explanation}});
        output["missing_prerequisites"]=record.missing_prerequisites;
        std::cout<<output.dump(2)<<'\n';return 0;
    } catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 2;}
}
