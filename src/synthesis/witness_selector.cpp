#include <csl/synthesis/witness_selector.hpp>
#include <csl/synthesis/strategy_ts01/analytic_profile.hpp>
#include <csl/synthesis/ts02_constant_integrator.hpp>
#include <csl/synthesis/ts03_singular_integrator.hpp>
#include <csl/synthesis/strategy_a/nominal_linear_exact_profile.hpp>
#include <csl/optimization/linear_program.hpp>
#include <cmath>
#include <algorithm>
#include <array>
#include <cstdint>
#include <bit>

namespace csl::synthesis::witness_selector {
namespace {
Diagnostics reject(std::string field,std::string reason) {
    return {{DiagnosticCode::unsupported,std::move(field),std::move(reason)}};
}
const sets::SetData* relation_set(const OptimalFamily& family) {
    const auto* complete=std::get_if<CompleteOptimalFamily>(&family.outcome());
    if(!complete)return nullptr;
    const auto& profile=family.identity().request.profile;
    if(profile==strategy_ts01::profile_id) {
        const auto* relation=dynamic_cast<const strategy_ts01::ExactJointRelation*>(complete->relation.payload.get());
        return relation?&relation->h_polyhedron():nullptr;
    }
    if(profile==ts02_constant_integrator_profile) {
        const auto* relation=dynamic_cast<const Ts02ConstantIntegratorRelation*>(complete->relation.payload.get());
        return relation?&relation->h_polyhedron():nullptr;
    }
    if(profile==ts03_singular_integrator_profile) {
        const auto* relation=dynamic_cast<const Ts03SingularIntegratorRelation*>(complete->relation.payload.get());
        return relation?&relation->h_polyhedron():nullptr;
    }
    if(profile==strategy_a::nominal_linear_exact_profile)
        return complete->relation.payload
            ?complete->relation.payload->h_relation_for_recording():nullptr;
    return nullptr;
}

bool exact_nonnegative_sum_equals(double left,double right,double expected) noexcept {
    if(left<0||right<0||expected<0)return false;
    struct Dyadic {std::uint64_t significand;int exponent;};
    const auto decompose=[](double value) noexcept {
        const auto bits=std::bit_cast<std::uint64_t>(value);
        const auto encoded=static_cast<unsigned>((bits>>52)&0x7ffu);
        const auto fraction=bits&((std::uint64_t{1}<<52)-1);
        if(encoded==0)return Dyadic{fraction,-1074};
        return Dyadic{(std::uint64_t{1}<<52)|fraction,static_cast<int>(encoded)-1023-52};
    };
    const auto add_shifted=[](std::array<std::uint64_t,34>& value,std::uint64_t significand,unsigned shift) noexcept {
        const auto index=shift/64u;const auto bits=shift%64u;
        const auto low=significand<<bits;
        const auto high=bits?significand>>(64u-bits):0;
        const auto add_word=[&](std::size_t word,std::uint64_t term) {
            while(term&&word<value.size()) {
                const auto previous=value[word];value[word]+=term;
                term=static_cast<std::uint64_t>(value[word]<previous);++word;
            }
        };
        add_word(index,low);add_word(index+1,high);
    };
    const auto a=decompose(left),b=decompose(right),c=decompose(expected);
    const auto minimum=std::min({a.exponent,b.exponent,c.exponent});
    std::array<std::uint64_t,34> sum{},target{};
    add_shifted(sum,a.significand,static_cast<unsigned>(a.exponent-minimum));
    add_shifted(sum,b.significand,static_cast<unsigned>(b.exponent-minimum));
    add_shifted(target,c.significand,static_cast<unsigned>(c.exponent-minimum));
    return sum==target;
}
bool contains_ts02(std::span<const double> point) noexcept {
    if(point.size()!=5||std::any_of(point.begin(),point.end(),[](double value){return !std::isfinite(value);}))return false;
    const auto x0=point[0],x1=point[1],x2=point[2],u0=point[3],u1=point[4];
    return x0==0&&x1==u0&&u0>=0&&u0<=1&&u1>=0&&u1<=1&&x2>=0&&
        exact_nonnegative_sum_equals(x1,u1,x2);
}
bool contains_ts03(std::span<const double> point) noexcept {
    if(point.size()!=5||std::any_of(point.begin(),point.end(),[](double value){return !std::isfinite(value);}))return false;
    const auto x0=point[0],x1=point[1],x2=point[2],u0=point[3],u1=point[4];
    return x0==0&&x1==u0&&x2==1&&u0>=0&&u0<=1&&u1==1;
}
bool contains_h(const sets::HRepresentation& h,std::span<const double> point,
        const NumericalPolicy& tolerance) noexcept {
    if(point.size()!=h.inequalities.cols()||point.size()!=h.equalities.cols()||
       std::any_of(point.begin(),point.end(),[](double value){return !std::isfinite(value);}))return false;
    const auto within=[&](double value,double bound,double scale) {
        return std::abs(value-bound)<=tolerance.absolute_tolerance+
            tolerance.relative_tolerance*std::max(1.0,scale);
    };
    for(std::size_t row=0;row<h.inequalities.rows();++row) {
        double value=0,scale=std::abs(h.upper_bounds[row]);
        for(std::size_t col=0;col<point.size();++col) {
            const auto term=h.inequalities(row,col)*point[col];
            value+=term;scale+=std::abs(term);
        }
        if(value>h.upper_bounds[row]+tolerance.absolute_tolerance+
                tolerance.relative_tolerance*std::max(1.0,scale))return false;
    }
    for(std::size_t row=0;row<h.equalities.rows();++row) {
        double value=0,scale=std::abs(h.equality_values[row]);
        for(std::size_t col=0;col<point.size();++col) {
            const auto term=h.equalities(row,col)*point[col];
            value+=term;scale+=std::abs(term);
        }
        if(!within(value,h.equality_values[row],scale))return false;
    }
    return true;
}
Diagnostics admission(const OptimalFamily& family,const WitnessRequest& request) {
    const auto* complete=std::get_if<CompleteOptimalFamily>(&family.outcome());
    const auto* relation=relation_set(family);
    bool h_representation=false;
    if(relation) {
        const auto representation=relation->representation();
        if(const auto* h=std::get_if<sets::HRepresentation>(&representation))
            h_representation=h->inequalities.cols()==5&&h->equalities.cols()==5;
    }
    if(!family.registry_verified()||!complete||complete->relation.representation.value!="csl.polyhedron.h"||
       complete->relation.coordinates!=JointCoordinates{{1,1,0},2}||!h_representation||
       !complete->optimum.bounds.lower||!complete->optimum.bounds.upper||
       complete->optimum.bounds.lower->value!=complete->optimum.bounds.upper->value)
        return reject("selector.family","Only registered complete T-S01/T-S02/T-S03 and nominal-linear-exact H relations with matching optimum bounds are supported.");
    if(!std::isfinite(request.distinctness_tolerance)||request.distinctness_tolerance<0)
        return reject("selector.tolerance","Distinctness tolerance must be finite and nonnegative.");
    for(const auto& direction:request.directions)
        if(direction.size()!=2||!std::isfinite(direction[0])||!std::isfinite(direction[1]))
            return reject("selector.directions","Directions must be finite (u0,u1) vectors, minimized over the family.");
    return {};
}
std::variant<LinearProgram,Diagnostics> program(const OptimalFamily& family,const Vector& direction,std::size_t index) {
    const auto* relation=relation_set(family);
    if(!relation)return reject("selector.family","Selected complete-family relation is unsupported.");
    const auto representation=relation->representation();
    const auto* h=std::get_if<sets::HRepresentation>(&representation);
    if(!h||h->inequalities.cols()!=5||h->equalities.cols()!=5)
        return reject("selector.family","Selected complete-family relation must provide a five-coordinate H representation.");
    SparseMatrix matrix{h->inequalities.rows()+h->equalities.rows(),5,{0},{},{}};
    std::vector<Interval> rows;
    const auto append=[&](const numeric::MatrixView& source,const numeric::VectorView& rhs,bool equality) {
        for(std::size_t r=0;r<source.rows();++r) {
            for(std::size_t c=0;c<5;++c)if(source(r,c)!=0) {
                matrix.column_indices.push_back(c);matrix.values.push_back(source(r,c));
            }
            matrix.row_offsets.push_back(matrix.values.size());
            rows.push_back({equality?std::optional<double>{rhs[r]}:std::nullopt,rhs[r]});
        }
    };
    append(h->inequalities,h->upper_bounds,false);append(h->equalities,h->equality_values,true);
    return optimization::make_linear_program({{family.identity().problem,{"witness-selector-direction/"+std::to_string(index)+"/"+std::to_string(std::bit_cast<std::uint64_t>(direction[0]))+"/"+std::to_string(std::bit_cast<std::uint64_t>(direction[1]))}},
        {0,0,0,direction[0],direction[1]},0,std::move(matrix),std::vector<Interval>(5),std::move(rows)});
}
std::optional<OperationStopped> stopped(const ExecutionContext& context) {
    if(context.cancellation.stop_requested())return OperationStopped{StopReason::cancelled,"Query cancelled; earlier observations retained."};
    if(context.deadline&&std::chrono::steady_clock::now()>=*context.deadline)return OperationStopped{StopReason::deadline_expired,"Query deadline expired; earlier observations retained."};
    return {};
}
class Workspace final : public WitnessSelectorWorkspace {
    registry::PreparedProvider<registry::LPPort> provider_;
public:
    explicit Workspace(registry::PreparedProvider<registry::LPPort> provider):provider_(std::move(provider)){}
    std::variant<WitnessSelection,Unsupported> select(const OptimalFamily& family,const WitnessRequest& request,
        const ExecutionContext& context) override {
        if(auto errors=admission(family,request);!errors.empty())return Unsupported{std::move(errors)};
        if(!context.resources)return Unsupported{reject("selector.resources","A resource policy is required.")};
        if(auto errors=check_resources(*context.resources);!errors.empty())return Unsupported{std::move(errors)};
        if(!std::isfinite(context.numerical.absolute_tolerance)||context.numerical.absolute_tolerance<0||
           !std::isfinite(context.numerical.relative_tolerance)||context.numerical.relative_tolerance<0)
            return Unsupported{reject("selector.numerical","Finite nonnegative numerical tolerances are required.")};
        WitnessSelection selected{{{},request.count,{selector_id},request.seed,family.identity(),request.directions,
            request.distinctness_tolerance},Termination::completed,{}};
        if(const auto stop=stopped(context)) {selected.termination=Termination::cancelled;selected.diagnostics=stop->diagnostics;return selected;}
        try {
            // Admit every generated direction before the first native solve.
            std::vector<LinearProgram> programs;
            for(std::size_t i=0;i<request.directions.size()&&request.count!=0;++i) {
                if(const auto stop=stopped(context)) {selected.termination=Termination::cancelled;selected.diagnostics=stop->diagnostics;return selected;}
                auto generated=program(family,request.directions[i],i);
                if(auto* errors=std::get_if<Diagnostics>(&generated))return Unsupported{std::move(*errors)};
                auto lp=std::get<LinearProgram>(std::move(generated));
                auto prepared=provider_.prepare(lp);
                if(const auto* rejected=std::get_if<registry::Rejection>(&prepared))return Unsupported{rejected->diagnostics};
                programs.push_back(std::move(lp));
            }
            registry::RegisteredLPQueryRunner runner{provider_};
            const auto& complete=std::get<CompleteOptimalFamily>(family.outcome());
            const auto* ts01=dynamic_cast<const strategy_ts01::ExactJointRelation*>(complete.relation.payload.get());
            const double original_objective=complete.optimum.bounds.lower->value;
            for(const auto& lp:programs) {
                if(selected.batch.distinct_count()>=request.count)break;
                if(const auto stop=stopped(context)) {selected.termination=Termination::cancelled;selected.diagnostics=stop->diagnostics;return selected;}
                auto outcome=runner.solve(lp,context);
                if(const auto* unsupported=std::get_if<Unsupported>(&outcome)) {
                    selected.termination=Termination::operation_rejected;
                    selected.diagnostics="LP provider rejected a direction query; earlier observations retained.";
                    if(!unsupported->diagnostics.empty())selected.diagnostics+=" "+unsupported->diagnostics.front().explanation;
                    return selected;
                }
                const auto& result=std::get<ProgramResult>(outcome);
                if(result.termination!=Termination::completed) {
                    selected.termination=result.termination;selected.diagnostics=result.raw_diagnostics;
                    if(!runner.records().empty())
                        if(const auto* not_run=std::get_if<registry::LPQueryNotRun>(&runner.records().back());
                           not_run&&not_run->request==lp.identity()&&not_run->reason==registry::LPQueryNotRunReason::deadline) {
                            selected.termination=Termination::cancelled;
                            selected.diagnostics="Query deadline expired before provider execution; earlier observations retained.";
                        }
                    return selected;
                }
                bool member=false;
                if(result.primal&&result.primal->size()==5) {
                    const auto& profile=family.identity().request.profile;
                    if(ts01) member=ts01->contains(*result.primal);
                    else if(profile==ts03_singular_integrator_profile)
                        member=contains_ts03(*result.primal);
                    else if(profile==strategy_a::nominal_linear_exact_profile) {
                        const auto* relation=relation_set(family);
                        member=relation&&contains_h(
                            std::get<sets::HRepresentation>(relation->representation()),
                            *result.primal,context.numerical);
                    } else member=contains_ts02(*result.primal);
                }
                if(result.outcome.subject!=lp.identity()||result.outcome.value!=MathematicalOutcome::optimal||!member) {
                    selected.termination=Termination::numerical_failure;
                    selected.diagnostics="Direction query did not return a consistent registered complete-family history.";return selected;
                }
                const auto& z=*result.primal;
                selected.batch.witnesses.push_back({family.identity().problem,{{z[0]},{z[1]},{z[2]}},{{z[3]},{z[4]}},original_objective});
            }
            selected.diagnostics=selected.batch.distinct_count()<request.count?
                "Search shortfall: directions exhausted; fewer distinct histories do not prove uniqueness.":
                "Requested distinct histories found; no uniform sampling or uniqueness guarantee.";
        } catch(const std::bad_alloc&) {
            selected.termination=Termination::resource_limit;selected.diagnostics="Query allocation failed; earlier observations retained.";return selected;
        }
        return selected;
    }
};
}
registry::Registration<registry::SelectorPort> make_registration(registry::PreparedProvider<registry::LPPort> provider) {
    return {{{selector_id},"1"},[provider](const registry::SelectorRequest& request,const registry::Requirements& requirements)->registry::Capability {
        if(auto errors=admission(request.family,request.selection);!errors.empty())return errors;
        if(requirements.scalar!=registry::Scalar::binary64||requirements.output.assurance!=Assurance::numerical)
            return reject("selector.assurance","Only numerical binary64 queries are supported.");
        for(std::size_t i=0;i<request.selection.directions.size()&&request.selection.count!=0;++i) {
            auto generated=program(request.family,request.selection.directions[i],i);
            if(const auto* errors=std::get_if<Diagnostics>(&generated))return *errors;
            auto prepared=provider.prepare(std::get<LinearProgram>(generated));
            if(const auto* rejected=std::get_if<registry::Rejection>(&prepared))return rejected->diagnostics;
        }
        return registry::Offer{{{"csl.witness-batch.v1"},Assurance::numerical,{},{},registry::Completeness::unestablished}};
    },[provider](const registry::SelectorRequest&)->std::unique_ptr<WitnessSelectorWorkspace> {return std::make_unique<Workspace>(provider);}};
}
}
