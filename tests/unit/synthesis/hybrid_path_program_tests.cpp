#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>

#include <csl/synthesis/hybrid_path_program.hpp>
#include <csl/sets/data.hpp>
#include <csl/registry/provider.hpp>
#include "hybrid_family_verifier_internal.hpp"
#include "hybrid_exact_polytope.hpp"
#include "hybrid_exact_model_relation.hpp"
#include <algorithm>
#include <array>
#include <limits>
#include <memory>
#include <stdexcept>
#include <string_view>
#include <type_traits>
#include <utility>

using namespace csl;
using namespace csl::synthesis;

namespace {
SetHandle universal(std::string id,std::size_t dimension) {
    auto data=sets::make_universal({SetId{std::move(id)},dimension,{}});
    REQUIRE(std::holds_alternative<sets::SetData>(data));
    return std::get<sets::SetData>(std::move(data)).as_handle();
}

SetHandle empty_handle(std::string id,std::size_t dimension) {
    auto data=sets::make_empty({SetId{std::move(id)},dimension,{}});
    REQUIRE(std::holds_alternative<sets::SetData>(data));
    return std::get<sets::SetData>(std::move(data)).as_handle();
}

SetHandle h_set(std::string id,std::size_t dimension,Matrix inequalities,
                Vector upper_bounds,Matrix equalities,Vector equality_values) {
    auto a=numeric::snapshot(inequalities);
    auto b=numeric::snapshot_vector(upper_bounds);
    auto e=numeric::snapshot(equalities);
    auto f=numeric::snapshot_vector(equality_values);
    REQUIRE(std::holds_alternative<numeric::MatrixView>(a));
    REQUIRE(std::holds_alternative<numeric::VectorView>(b));
    REQUIRE(std::holds_alternative<numeric::MatrixView>(e));
    REQUIRE(std::holds_alternative<numeric::VectorView>(f));
    auto data=sets::make_h({SetId{std::move(id)},dimension,{}},
        {std::get<numeric::MatrixView>(a),std::get<numeric::VectorView>(b),
         std::get<numeric::MatrixView>(e),std::get<numeric::VectorView>(f)});
    REQUIRE(std::holds_alternative<sets::SetData>(data));
    return std::get<sets::SetData>(std::move(data)).as_handle();
}

sets::SetData append_redundant_zero_inequality(std::string id,
    const sets::SetData& relation) {
    const auto representation=relation.representation();
    const auto& h=std::get<sets::HRepresentation>(representation);
    Vector inequalities;
    inequalities.reserve((h.inequalities.rows()+1)*h.inequalities.cols());
    for(std::size_t row=0;row<h.inequalities.rows();++row)
        for(std::size_t column=0;column<h.inequalities.cols();++column)
            inequalities.push_back(h.inequalities(row,column));
    inequalities.insert(inequalities.end(),h.inequalities.cols(),0);
    Vector upper_bounds(h.upper_bounds.values().begin(),h.upper_bounds.values().end());
    upper_bounds.push_back(0);
    Vector equalities;
    equalities.reserve(h.equalities.rows()*h.equalities.cols());
    for(std::size_t row=0;row<h.equalities.rows();++row)
        for(std::size_t column=0;column<h.equalities.cols();++column)
            equalities.push_back(h.equalities(row,column));
    Vector equality_values(h.equality_values.values().begin(),h.equality_values.values().end());
    const auto handle=h_set(std::move(id),relation.metadata()->set.dimension,
        Matrix{h.inequalities.rows()+1,h.inequalities.cols(),std::move(inequalities)},
        std::move(upper_bounds),Matrix{h.equalities.rows(),h.equalities.cols(),
        std::move(equalities)},std::move(equality_values));
    return std::get<sets::SetData>(sets::from_handle(handle));
}

void set_synthetic_relation_trace_rows(HybridPathProgram& program) {
    const auto representation=program.joint_relation.representation();
    const auto& h=std::get<sets::HRepresentation>(representation);
    const auto total_rows=h.inequalities.rows()+h.equalities.rows();
    const auto dimension=program.joint_relation.metadata()->set.dimension;
    if(dimension!=0)
        REQUIRE(total_rows<=std::numeric_limits<std::size_t>::max()/dimension);
    REQUIRE_FALSE(program.relation_operations.empty());
    const auto operation_count=program.relation_operations.size();
    const auto rows_per_operation=total_rows/operation_count;
    const auto extra_rows=total_rows%operation_count;
    std::size_t previous_rows=0;
    for(std::size_t i=0;i<operation_count;++i) {
        auto& operation=program.relation_operations[i];
        const auto cumulative_rows=rows_per_operation*(i+1)+
            std::min(i+1,extra_rows);
        operation.rows_added=cumulative_rows-previous_rows;
        operation.cumulative_rows=cumulative_rows;
        operation.cumulative_matrix_elements=cumulative_rows*dimension;
        previous_rows=cumulative_rows;
    }
}

SetHandle singleton_relation(std::string id,Vector point) {
    auto snapshot=numeric::snapshot_vector(point);
    REQUIRE(std::holds_alternative<numeric::VectorView>(snapshot));
    auto data=sets::make_singleton({SetId{std::move(id)},point.size(),{}},
        std::get<numeric::VectorView>(std::move(snapshot)));
    REQUIRE(std::holds_alternative<sets::SetData>(data));
    return std::get<sets::SetData>(std::move(data)).as_handle();
}

sets::SetData singleton_data(Vector point) {
    auto snapshot=numeric::snapshot_vector(point);
    REQUIRE(std::holds_alternative<numeric::VectorView>(snapshot));
    auto data=sets::make_singleton({SetId{"fixture.singleton"},point.size(),{}},
        std::get<numeric::VectorView>(std::move(snapshot)));
    REQUIRE(std::holds_alternative<sets::SetData>(data));
    return std::get<sets::SetData>(std::move(data));
}

std::pair<model::HybridSystem,model::HybridRequest> exact_singleton_portfolio() {
    model::HybridMode source{{"source"},1,1,{"x"},{"u"}};
    source.flow=LinearStage{Matrix{1,1,{1}},Matrix{1,1,{1}},Matrix{1,0,{}},Vector{0}};
    source.control_sets={Singleton{{1}}};
    source.invariants={UniversalSet{1},UniversalSet{1}};
    model::HybridMode target{{"target"},2,0,{"y","z"},{}};
    target.flow=LinearStage{Matrix{2,2,{1,0,0,1}},Matrix{2,0,{}},Matrix{2,0,{}},Vector{0,0}};
    target.control_sets={UniversalSet{0}};
    target.invariants={UniversalSet{2},UniversalSet{2}};
    model::HybridSystem system{1,{source,target},
        {{{"tie-a"},{"source"},{"target"},{Singleton{{3}}},{singleton_relation("reset-a",{3,0,0})}},
         {{"tie-b"},{"source"},{"target"},{Singleton{{3}}},{singleton_relation("reset-b",{3,0,0})}},
         {{"worse"},{"source"},{"target"},{Singleton{{3}}},{singleton_relation("reset-worse",{3,1,0})}}}};
    model::HybridRequest request{{{"source"},{2}},{{"target"}},
        {{{"target"},LinearTerminal{{1,0},0},"cost","u"}}};
    return {std::move(system),std::move(request)};
}

struct OneStepOracleBranch {
    model::HybridPath path;
    Vector joint_tuple;
    double objective{};
};

std::size_t equality_rank(const numeric::MatrixView& equalities) {
    std::vector<Vector> reduced(equalities.rows(),Vector(equalities.cols()));
    for(std::size_t row=0;row<equalities.rows();++row)
        for(std::size_t col=0;col<equalities.cols();++col)
            reduced[row][col]=equalities(row,col);
    std::size_t rank=0;
    for(std::size_t col=0;col<equalities.cols() && rank<reduced.size();++col) {
        auto pivot=rank;
        while(pivot<reduced.size() && reduced[pivot][col]==0) ++pivot;
        if(pivot==reduced.size()) continue;
        std::swap(reduced[pivot],reduced[rank]);
        const double scale=reduced[rank][col];
        for(std::size_t j=col;j<equalities.cols();++j) reduced[rank][j]/=scale;
        for(std::size_t row=0;row<reduced.size();++row) {
            if(row==rank) continue;
            const double factor=reduced[row][col];
            for(std::size_t j=col;j<equalities.cols();++j)
                reduced[row][j]-=factor*reduced[rank][j];
        }
        ++rank;
    }
    return rank;
}

bool equality_rows_have_full_column_rank(const numeric::MatrixView& equalities) {
    return equality_rank(equalities)==equalities.cols();
}

bool has_conflicting_equalities(const sets::HRepresentation& relation) {
    std::vector<Vector> augmented(relation.equalities.rows(),Vector(relation.equalities.cols()+1));
    for(std::size_t row=0;row<relation.equalities.rows();++row) {
        for(std::size_t col=0;col<relation.equalities.cols();++col)
            augmented[row][col]=relation.equalities(row,col);
        augmented[row].back()=relation.equality_values[row];
    }
    std::size_t pivot_row=0;
    for(std::size_t col=0;col<relation.equalities.cols() && pivot_row<augmented.size();++col) {
        auto pivot=pivot_row;
        while(pivot<augmented.size() && augmented[pivot][col]==0) ++pivot;
        if(pivot==augmented.size()) continue;
        std::swap(augmented[pivot],augmented[pivot_row]);
        const double scale=augmented[pivot_row][col];
        for(std::size_t j=col;j<=relation.equalities.cols();++j)
            augmented[pivot_row][j]/=scale;
        for(std::size_t row=0;row<augmented.size();++row) {
            if(row==pivot_row) continue;
            const double factor=augmented[row][col];
            for(std::size_t j=col;j<=relation.equalities.cols();++j)
                augmented[row][j]-=factor*augmented[pivot_row][j];
        }
        ++pivot_row;
    }
    return std::any_of(augmented.begin(),augmented.end(),[&](const auto& row) {
        const bool zero_coefficients=std::all_of(row.begin(),row.end()-1,[](double value) { return value==0; });
        return zero_coefficients && row.back()!=0;
    });
}

// Deliberately independent of the production path enumerator, relation
// composer, and verifier. This small exhaustive oracle directly interprets
// the one-step singleton fixture from its raw mode/edge data.
std::vector<OneStepOracleBranch> enumerate_one_step_singleton_oracle(
    const model::HybridSystem& system,const model::HybridRequest& request) {
    REQUIRE(system.horizon==1);
    std::vector<OneStepOracleBranch> branches;
    const auto source=std::find_if(system.modes.begin(),system.modes.end(),[&](const auto& mode) {
        return mode.id==request.initial.mode;
    });
    REQUIRE(source!=system.modes.end());
    const auto* flow=std::get_if<LinearStage>(&source->flow);
    REQUIRE(flow!=nullptr);
    REQUIRE(flow->A.rows==request.initial.state.size());
    REQUIRE(flow->A.cols==request.initial.state.size());
    REQUIRE(flow->B.cols==source->control_dimension);
    REQUIRE(flow->B.rows==flow->A.rows);
    REQUIRE(flow->offset.size()==flow->A.rows);
    REQUIRE(source->control_sets.size()==1);
    const auto* control_singleton=std::get_if<Singleton>(&source->control_sets[0]);
    REQUIRE(control_singleton!=nullptr);
    const Vector control=control_singleton->point;
    Vector pre(flow->A.rows);
    for(std::size_t row=0;row<pre.size();++row) {
        pre[row]=flow->offset[row];
        for(std::size_t col=0;col<request.initial.state.size();++col)
            pre[row]+=flow->A.values[row*flow->A.cols+col]*request.initial.state[col];
        for(std::size_t col=0;col<control.size();++col)
            pre[row]+=flow->B.values[row*flow->B.cols+col]*control[col];
    }

    for(const auto& edge:system.edges) {
        if(edge.source!=request.initial.mode) continue;
        if(std::find(request.allowed_terminal_modes.begin(),request.allowed_terminal_modes.end(),edge.target)==
           request.allowed_terminal_modes.end()) continue;
        REQUIRE(edge.guards.size()==1);
        const auto* guard=std::get_if<Singleton>(&edge.guards[0]);
        REQUIRE(guard!=nullptr);
        if(guard->point!=pre) continue;
        REQUIRE(edge.reset_relations.size()==1);
        const auto reset_data=sets::from_handle(edge.reset_relations[0]);
        REQUIRE(std::holds_alternative<sets::SetData>(reset_data));
        const auto reset_rep=std::get<sets::SetData>(reset_data).representation();
        REQUIRE(std::holds_alternative<sets::SingletonRepresentation>(reset_rep));
        const auto reset_view=std::get<sets::SingletonRepresentation>(reset_rep).point;
        const auto target=std::find_if(system.modes.begin(),system.modes.end(),[&](const auto& mode) {
            return mode.id==edge.target;
        });
        REQUIRE(target!=system.modes.end());
        REQUIRE(reset_view.size()==pre.size()+target->state_dimension);
        bool reset_matches=true;
        for(std::size_t i=0;i<pre.size();++i) reset_matches=reset_matches && reset_view[i]==pre[i];
        if(!reset_matches) continue;
        Vector post(reset_view.size()-pre.size());
        for(std::size_t i=0;i<post.size();++i) post[i]=reset_view[pre.size()+i];
        const auto objective=std::find_if(request.terminal_objectives.begin(),request.terminal_objectives.end(),
            [&](const auto& candidate) { return candidate.mode==edge.target; });
        REQUIRE(objective!=request.terminal_objectives.end());
        const auto* linear=std::get_if<LinearTerminal>(&objective->objective);
        REQUIRE(linear!=nullptr);
        REQUIRE(linear->coefficients.size()==post.size());
        double cost=linear->offset;
        for(std::size_t i=0;i<post.size();++i) cost+=linear->coefficients[i]*post[i];
        Vector joint=request.initial.state;
        joint.insert(joint.end(),control.begin(),control.end());
        joint.insert(joint.end(),pre.begin(),pre.end());
        joint.insert(joint.end(),post.begin(),post.end());
        branches.push_back({{{request.initial.mode,edge.target},{edge.id}},std::move(joint),cost});
    }
    return branches;
}

HybridPathOptimalFaceCandidate exact_candidate(const HybridPathProgram& program,Vector point) {
    const auto& linear=std::get<LinearProgram>(program.program);
    const auto support=SymbolicArgument{"exact singleton fixture","literal exact branch"};
    ProgramResult result{Termination::completed,
        {linear.identity(),MathematicalOutcome::optimal,support,{}},point,{},"exact fixture"};
    return {program.path,program.joint_relation,std::move(point),std::move(result),{},
        "independently specified singleton branch",{}};
}

model::HybridSystem example_system() {
    model::HybridMode source{{"source"},1,1,{"position"},{"thrust"}};
    source.flow=LinearStage{Matrix{1,1,{1}},Matrix{1,1,{1}},Matrix{1,0,{}},Vector{0}};
    source.control_sets={UniversalSet{1}};
    source.invariants={UniversalSet{1},UniversalSet{1}};
    model::HybridMode target{{"target"},2,0,{"position","velocity"},{}};
    target.flow=LinearStage{Matrix{2,2,{1,0,0,1}},Matrix{2,0,{}},Matrix{2,0,{}},Vector{0,0}};
    target.control_sets={UniversalSet{0}};
    target.invariants={UniversalSet{2},UniversalSet{2}};
    model::HybridTransitionEdge edge{{"switch"},{"source"},{"target"},
        {UniversalSet{1}},{universal("reset",3)}};
    return {1,{std::move(source),std::move(target)},{std::move(edge)}};
}

model::HybridRequest example_request() {
    return {{{"source"},{2}},{{"target"}},
        {{{"target"},LinearTerminal{{2,-1},0},"energy","J"}}};
}

model::HybridPath example_path() {
    return {{{"source"},{"target"}},{{"switch"}}};
}

TEST_CASE("hybrid exact polytope rows preserve binary64 dyadics") {
    using namespace detail::hybrid_exact;
    const std::array<double,2> coefficients{0.5,-1.25};
    Row row;
    REQUIRE(make_row(coefficients,0.125,false,default_max_integer_bits,row));
    CHECK(exact_detail::compare(row.coefficients[0],exact_detail::from_u64(4))==0);
    CHECK(exact_detail::compare(row.coefficients[1],exact_detail::from_u64(10,true))==0);
    CHECK(exact_detail::compare(row.bound,exact_detail::from_u64(1))==0);

    const std::array<double,1> subnormal{std::numeric_limits<double>::denorm_min()};
    REQUIRE(make_row(subnormal,0,false,default_max_integer_bits,row));
    CHECK(exact_detail::compare(row.coefficients[0],exact_detail::from_u64(1))==0);
    CHECK_FALSE(make_row(coefficients,0.125,false,3,row));

    // The unshifted significand exceeds this cap before row normalization.
    const std::array<double,1> odd_significand{1.1};
    CHECK_FALSE(make_row(odd_significand,0,false,52,row));
}

TEST_CASE("hybrid exact integer arithmetic handles multiword carries") {
    using namespace detail::hybrid_exact;
    using exact_detail::add;
    using exact_detail::compare;
    using exact_detail::from_u64;
    using exact_detail::multiply;

    Integer sum=from_u64(0xffffffffULL);
    REQUIRE(add(sum,from_u64(1),64));
    CHECK(compare(sum,from_u64(0x100000000ULL))==0);

    Integer product;
    REQUIRE(multiply(from_u64(0x100000001ULL),
                     from_u64(0x100000003ULL),128,product));
    const Integer expected_product{{3U,4U,1U},false};
    CHECK(compare(product,expected_product)==0);
    CHECK_FALSE(multiply(from_u64(0x100000001ULL),
                         from_u64(0x100000003ULL),63,product));
}

TEST_CASE("hybrid exact polytope feasibility retains strict and closed bounds") {
    using namespace detail::hybrid_exact;
    const std::array<double,1> positive{1}, negative{-1};
    std::vector<Row> strict_conflict;
    REQUIRE(append_inequality(positive,0,true,default_max_integer_bits,strict_conflict));
    REQUIRE(append_inequality(negative,0,false,default_max_integer_bits,strict_conflict));
    CHECK(feasible(std::move(strict_conflict),1).state==FeasibilityState::infeasible);

    std::vector<Row> open_interval;
    REQUIRE(append_inequality(positive,1,true,default_max_integer_bits,open_interval));
    REQUIRE(append_inequality(negative,0,true,default_max_integer_bits,open_interval));
    CHECK(feasible(std::move(open_interval),1).state==FeasibilityState::feasible);

    std::vector<Row> closed_point;
    REQUIRE(append_inequality(positive,0,false,default_max_integer_bits,closed_point));
    REQUIRE(append_inequality(negative,0,false,default_max_integer_bits,closed_point));
    CHECK(feasible(std::move(closed_point),1).state==FeasibilityState::feasible);

    const std::array<double,2> coupled_upper{2,1}, coupled_lower{-3,2}, y_lower{0,-1};
    std::vector<Row> coupled_conflict;
    REQUIRE(append_inequality(coupled_upper,0,false,default_max_integer_bits,coupled_conflict));
    REQUIRE(append_inequality(coupled_lower,-1,false,default_max_integer_bits,coupled_conflict));
    REQUIRE(append_inequality(y_lower,0,false,default_max_integer_bits,coupled_conflict));
    CHECK(feasible(std::move(coupled_conflict),2).state==FeasibilityState::infeasible);
}

TEST_CASE("hybrid exact polytope proves half-space relation inclusion") {
    using namespace detail::hybrid_exact;
    const std::array<double,1> x{1};
    std::vector<Row> source;
    REQUIRE(append_equality(x,0,default_max_integer_bits,source));

    std::vector<Row> containing_target;
    REQUIRE(append_inequality(x,1,false,default_max_integer_bits,containing_target));
    CHECK(included_in(source,containing_target,1).state==InclusionState::included);

    std::vector<Row> excluding_target;
    REQUIRE(append_inequality(x,-1,false,default_max_integer_bits,excluding_target));
    CHECK(included_in(source,excluding_target,1).state==InclusionState::not_included);

    // The strict complement must catch a source point on a closed boundary.
    std::vector<Row> boundary_target;
    REQUIRE(append_inequality(x,0,false,default_max_integer_bits,boundary_target));
    CHECK(included_in(source,boundary_target,1).state==InclusionState::included);
    boundary_target.front().strict=true;
    CHECK(included_in(source,boundary_target,1).state==InclusionState::not_included);
    CHECK(included_in(source,std::span<const Row>{},1).state==
          InclusionState::included);
    const std::vector<Row> malformed_source{Row{}};
    CHECK(included_in(malformed_source,std::span<const Row>{},1).state==
          InclusionState::unsupported);

    Limits limits;
    limits.max_operations=0;
    CHECK(included_in(source,containing_target,1,limits).state==
          InclusionState::unsupported);

    limits.max_operations=default_max_operations;
    limits.max_variables=0;
    CHECK(included_in(source,std::span<const Row>{},1,limits).state==
          InclusionState::unsupported);

    limits={};
    std::stop_source cancelled;
    cancelled.request_stop();
    CHECK(included_in(source,std::span<const Row>{},1,limits,
                      cancelled.get_token()).state==InclusionState::cancelled);
}

TEST_CASE("hybrid exact polytope projects linear objective bounds") {
    using namespace detail::hybrid_exact;
    const std::array<double,1> x{1}, negative_x{-1};
    std::vector<Row> interval_rows;
    REQUIRE(append_inequality(x,2,false,default_max_integer_bits,interval_rows));
    REQUIRE(append_inequality(negative_x,0,false,default_max_integer_bits,interval_rows));

    const auto minimum_x=minimize_linear(interval_rows,1,x,0);
    REQUIRE(minimum_x.state==LinearMinimumState::minimum);
    CHECK(minimum_x.attained);
    CHECK(exact_detail::compare(minimum_x.value.numerator,{})==0);
    CHECK(exact_detail::compare(minimum_x.value.denominator,
                                exact_detail::from_u64(1))==0);

    const std::array<double,1> negative_objective{-1};
    const auto minimum_negative_x=minimize_linear(interval_rows,1,
                                                   negative_objective,3);
    REQUIRE(minimum_negative_x.state==LinearMinimumState::minimum);
    CHECK(minimum_negative_x.attained);
    CHECK(exact_detail::compare(minimum_negative_x.value.numerator,
                                exact_detail::from_u64(1))==0);

    const std::array<double,1> scaled_objective{0.5};
    const auto scaled_minimum=minimize_linear(interval_rows,1,
                                               scaled_objective,0.25);
    REQUIRE(scaled_minimum.state==LinearMinimumState::minimum);
    CHECK(scaled_minimum.value.binary_exponent==-2);
    CHECK(exact_detail::compare(scaled_minimum.value.numerator,
                                exact_detail::from_u64(1))==0);
    int order=0;
    REQUIRE(compare_scaled_rationals(scaled_minimum.value,
        minimum_negative_x.value,default_max_integer_bits,order));
    CHECK(order<0);

    std::vector<Row> open_interval;
    REQUIRE(append_inequality(x,2,true,default_max_integer_bits,open_interval));
    REQUIRE(append_inequality(negative_x,0,true,default_max_integer_bits,open_interval));
    const auto open_minimum=minimize_linear(open_interval,1,x,0);
    REQUIRE(open_minimum.state==LinearMinimumState::minimum);
    CHECK_FALSE(open_minimum.attained);
    CHECK(exact_detail::compare(open_minimum.value.numerator,{})==0);

    const auto unbounded=minimize_linear(std::span<const Row>{},1,x,0);
    CHECK(unbounded.state==LinearMinimumState::unbounded_below);
    const auto constant=minimize_linear(interval_rows,1,
                                         std::array<double,1>{0},-2.5);
    REQUIRE(constant.state==LinearMinimumState::minimum);
    CHECK(constant.attained);
    CHECK(constant.value.binary_exponent==-1);
    CHECK(exact_detail::compare(constant.value.numerator,
                                exact_detail::from_u64(5,true))==0);

    std::vector<Row> thirds_lower_bound;
    const std::array<double,1> negative_three{-3};
    REQUIRE(append_inequality(negative_three,-1,false,
                              default_max_integer_bits,thirds_lower_bound));
    const auto one_third=minimize_linear(thirds_lower_bound,1,x,0);
    REQUIRE(one_third.state==LinearMinimumState::minimum);
    CHECK(one_third.attained);
    CHECK(exact_detail::compare(one_third.value.numerator,
                                exact_detail::from_u64(1))==0);
    CHECK(exact_detail::compare(one_third.value.denominator,
                                exact_detail::from_u64(3))==0);

    std::vector<Row> positive_open_domain;
    REQUIRE(append_inequality(negative_x,0,true,
                              default_max_integer_bits,positive_open_domain));
    REQUIRE(append_inequality(negative_x,0,false,
                              default_max_integer_bits,positive_open_domain));
    const auto strict_tied_bound=minimize_linear(positive_open_domain,1,x,0);
    REQUIRE(strict_tied_bound.state==LinearMinimumState::minimum);
    CHECK_FALSE(strict_tied_bound.attained);

    const std::array<double,1> shifted_domain{-1};
    std::vector<Row> x_at_least_one;
    REQUIRE(append_inequality(shifted_domain,-1,false,
                              default_max_integer_bits,x_at_least_one));
    const auto shifted_objective=minimize_linear(x_at_least_one,1,
                                                  scaled_objective,0.25);
    REQUIRE(shifted_objective.state==LinearMinimumState::minimum);
    CHECK(shifted_objective.value.binary_exponent==-2);
    CHECK(exact_detail::compare(shifted_objective.value.numerator,
                                exact_detail::from_u64(3))==0);
    ExactRational same_value{exact_detail::from_u64(3),
                             exact_detail::from_u64(4),0};
    REQUIRE(compare_scaled_rationals(shifted_objective.value,same_value,
                                     default_max_integer_bits,order));
    CHECK(order==0);
    ExactRational extreme_low{exact_detail::from_u64(1),
                              exact_detail::from_u64(1),
                              std::numeric_limits<int>::min()};
    ExactRational extreme_high{exact_detail::from_u64(1),
                               exact_detail::from_u64(1),
                               std::numeric_limits<int>::max()};
    CHECK_FALSE(compare_scaled_rationals(extreme_high,extreme_low,
                                         default_max_integer_bits,order));
}

TEST_CASE("exact linear H verifier proves complete continuous optimal faces") {
    model::HybridMode source{{"source"},1,1,{"x"},{"u"}};
    source.flow=LinearStage{Matrix{1,1,{1}},Matrix{1,1,{1}},
        Matrix{1,0,{}},Vector{0}};
    source.control_sets={h_set("exact-linear-control",1,
        Matrix{2,1,{1,-1}},Vector{2,0},Matrix{0,1,{}},Vector{})};
    source.invariants={UniversalSet{1},UniversalSet{1}};
    model::HybridMode target{{"target"},1,0,{"y"},{}};
    target.flow=LinearStage{Matrix{1,1,{1}},Matrix{1,0,{}},
        Matrix{1,0,{}},Vector{0}};
    target.control_sets={UniversalSet{0}};
    target.invariants={UniversalSet{1},UniversalSet{1}};
    model::HybridSystem system{1,{source,target},
        {{{"switch"},{"source"},{"target"},{UniversalSet{1}},
          {h_set("exact-linear-reset",2,Matrix{0,2,{}},Vector{},
              Matrix{1,2,{-1,1}},Vector{0})}}}};
    model::HybridRequest request{{{"source"},{0}},{{"target"}},
        {{{"target"},LinearTerminal{{1},0},"terminal cost","units"}}};
    const auto built=build_hybrid_portfolio_programs(system,request,{"exact-linear"},
        {1,8},{16,64,4096});
    REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(built));
    const auto& programs=std::get<std::vector<HybridPathProgram>>(built);
    REQUIRE(programs.size()==1);
    auto candidate=exact_candidate(programs.front(),{0,0,0,0});
    candidate.relation=singleton_data({0,0,0,0});
    ExactLinearHHybridFamilyVerifier verifier;
    const auto result=verify_hybrid_portfolio_family(verifier,system,request,
        programs,std::span<const HybridPathOptimalFaceCandidate>(&candidate,1),
        {1,8},{1e-9,1e-9});
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(result));
    const auto& report=std::get<HybridFamilyVerificationReport>(result);
    CHECK(report.verifier_id=="csl.hybrid.exact-linear-h");
    CHECK(report.global_objective_optimality==HybridVerificationStatus::established);
    CHECK(report.complete_family_coverage==HybridVerificationStatus::established);
    REQUIRE(report.branches.size()==1);
    CHECK(report.branches[0].feasibility==HybridVerificationStatus::established);
    CHECK(report.branches[0].objective_optimality==HybridVerificationStatus::established);
    CHECK(report.branches[0].continuous_coverage==HybridVerificationStatus::established);

    auto mixed_system=system;
    mixed_system.edges.push_back({{"free-reset"},{"source"},{"target"},
        {UniversalSet{1}},{universal("free-terminal-reset",2)}});
    const auto mixed_built=build_hybrid_portfolio_programs(mixed_system,request,
        {"exact-linear-mixed"},{1,8},{16,64,4096});
    REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(mixed_built));
    const auto& mixed_programs=std::get<std::vector<HybridPathProgram>>(mixed_built);
    REQUIRE(mixed_programs.size()==2);
    auto finite_face=exact_candidate(mixed_programs[0],{0,0,0,0});
    finite_face.relation=singleton_data({0,0,0,0});
    const auto mixed_result=verify_hybrid_portfolio_family(verifier,mixed_system,
        request,mixed_programs,
        std::span<const HybridPathOptimalFaceCandidate>(&finite_face,1),
        {1,8},{1e-9,1e-9});
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(mixed_result));
    const auto& mixed_report=std::get<HybridFamilyVerificationReport>(mixed_result);
    CHECK(mixed_report.global_objective_optimality==HybridVerificationStatus::refuted);
    CHECK(mixed_report.complete_family_coverage==HybridVerificationStatus::refuted);
    CHECK(mixed_report.branches[0].objective_optimality==HybridVerificationStatus::refuted);
    CHECK(mixed_report.branches[1].objective_optimality==HybridVerificationStatus::refuted);

    auto forged_face=exact_candidate(programs.front(),{0,1,1,1});
    const auto forged=verify_hybrid_portfolio_family(verifier,system,request,
        programs,std::span<const HybridPathOptimalFaceCandidate>(&forged_face,1),
        {1,8},{1e-9,1e-9});
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(forged));
    CHECK(std::get<HybridFamilyVerificationReport>(forged).complete_family_coverage==
          HybridVerificationStatus::refuted);

    auto flat_request=request;
    flat_request.terminal_objectives[0].objective=LinearTerminal{{0},0};
    const auto flat_built=build_hybrid_portfolio_programs(system,flat_request,
        {"exact-linear-flat"},{1,8},{16,64,4096});
    REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(flat_built));
    const auto& flat_programs=std::get<std::vector<HybridPathProgram>>(flat_built);
    auto flat_candidate=exact_candidate(flat_programs.front(),{0,1,1,1});
    flat_candidate.relation=flat_programs.front().joint_relation;
    const auto flat_result=verify_hybrid_portfolio_family(verifier,system,
        flat_request,flat_programs,
        std::span<const HybridPathOptimalFaceCandidate>(&flat_candidate,1),
        {1,8},{1e-9,1e-9});
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(flat_result));
    CHECK(std::get<HybridFamilyVerificationReport>(flat_result).complete_family_coverage==
          HybridVerificationStatus::established);
}

TEST_CASE("exact linear H verifier retains tied paths across objective scales") {
    model::HybridMode source{{"source"},1,1,{"x"},{"u"}};
    source.flow=LinearStage{Matrix{1,1,{1}},Matrix{1,1,{1}},
        Matrix{1,0,{}},Vector{0}};
    source.control_sets={h_set("scaled-tie-control",1,
        Matrix{2,1,{1,-1}},Vector{1,0},Matrix{0,1,{}},Vector{})};
    source.invariants={UniversalSet{1},UniversalSet{1}};
    model::HybridMode target_a{{"target-a"},1,0,{"y"},{}};
    target_a.flow=LinearStage{Matrix{1,1,{1}},Matrix{1,0,{}},
        Matrix{1,0,{}},Vector{0}};
    target_a.control_sets={UniversalSet{0}};
    target_a.invariants={UniversalSet{1},UniversalSet{1}};
    model::HybridMode target_b=target_a;
    target_b.id={"target-b"};
    model::HybridSystem system{1,{source,target_a,target_b},
        {{{"tie-a"},{"source"},{"target-a"},{UniversalSet{1}},
          {h_set("scaled-tie-reset-a",2,Matrix{0,2,{}},Vector{},
              Matrix{1,2,{0,1}},Vector{0})}},
         {{"tie-b"},{"source"},{"target-b"},{UniversalSet{1}},
          {h_set("scaled-tie-reset-b",2,Matrix{0,2,{}},Vector{},
              Matrix{1,2,{0,1}},Vector{0.25})}},
         {{"worse"},{"source"},{"target-b"},{UniversalSet{1}},
          {h_set("scaled-worse-reset",2,Matrix{0,2,{}},Vector{},
              Matrix{1,2,{0,1}},Vector{1})}}}};
    model::HybridRequest request{{{"source"},{0}},{{"target-a"},{"target-b"}},
        {{{"target-a"},LinearTerminal{{0.5},0.25},"cost","units"},
         {{"target-b"},LinearTerminal{{1},0},"cost","units"}}};
    const auto built=build_hybrid_portfolio_programs(system,request,{"scaled-tie"},
        {1,8},{16,64,4096});
    REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(built));
    const auto& programs=std::get<std::vector<HybridPathProgram>>(built);
    REQUIRE(programs.size()==3);
    std::vector<HybridPathOptimalFaceCandidate> candidates{
        exact_candidate(programs[0],{0,0.5,0.5,0}),
        exact_candidate(programs[1],{0,0.5,0.5,0.25})};
    ExactLinearHHybridFamilyVerifier verifier;
    const auto result=verify_hybrid_portfolio_family(verifier,system,request,
        programs,candidates,{1,8},{1e-9,1e-9});
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(result));
    const auto& report=std::get<HybridFamilyVerificationReport>(result);
    CHECK(report.global_objective_optimality==HybridVerificationStatus::established);
    CHECK(report.complete_family_coverage==HybridVerificationStatus::established);
    REQUIRE(report.branches.size()==3);
    CHECK(report.branches[0].objective_optimality==HybridVerificationStatus::established);
    CHECK(report.branches[0].continuous_coverage==HybridVerificationStatus::established);
    CHECK(report.branches[1].objective_optimality==HybridVerificationStatus::established);
    CHECK(report.branches[1].continuous_coverage==HybridVerificationStatus::established);
    CHECK(report.branches[2].objective_optimality==HybridVerificationStatus::refuted);
    CHECK(report.branches[2].continuous_coverage==HybridVerificationStatus::established);
}

TEST_CASE("exact linear H verifier matches literal two-control tied path oracle") {
    const auto scalar_interval=[](std::string id,double lower,double upper) {
        return h_set(std::move(id),1,Matrix{2,1,{-1,1}},
            Vector{-lower,upper},Matrix{0,1,{}},Vector{});
    };
    const LinearStage first{Matrix{1,1,{0}},Matrix{1,1,{1}},
        Matrix{1,0,{}},Vector{0}};
    const LinearStage second{Matrix{1,1,{1}},Matrix{1,1,{0}},
        Matrix{1,0,{}},Vector{0}};
    model::HybridMode source{{"source"},1,1,{"x"},{"u"}};
    source.flow=std::vector<LinearStage>{first,second};
    source.control_sets={scalar_interval("oracle-u0",0,1),Singleton{{0}}};
    source.invariants={UniversalSet{1},UniversalSet{1},UniversalSet{1}};
    model::HybridMode middle{{"middle"},1,1,{"x"},{"u"}};
    middle.flow=std::vector<LinearStage>{first,second};
    middle.control_sets={Singleton{{0}},scalar_interval("oracle-u1",0,1)};
    middle.invariants={UniversalSet{1},UniversalSet{1},UniversalSet{1}};
    model::HybridMode terminal{{"terminal"},1,1,{"x"},{"u"}};
    terminal.flow=std::vector<LinearStage>{first,second};
    terminal.control_sets={Singleton{{0}},Singleton{{0}}};
    terminal.invariants={UniversalSet{1},UniversalSet{1},UniversalSet{1}};
    const auto identity=[](std::string id) {
        return h_set(std::move(id),2,Matrix{0,2,{}},Vector{},
            Matrix{1,2,{1,-1}},Vector{0});
    };
    const auto universal_reset=[](std::string id) {
        return h_set(std::move(id),2,Matrix{0,2,{}},Vector{},
            Matrix{0,2,{}},Vector{});
    };
    model::HybridSystem system{2,{source,middle,terminal},
        {{{"enter-half"},{"source"},{"middle"},
          {scalar_interval("oracle-half-guard",0,0.5),UniversalSet{1}},
          {identity("oracle-half-reset"),universal_reset("unused-half-reset")}},
         {{"enter-full"},{"source"},{"middle"},
          {UniversalSet{1},UniversalSet{1}},
          {identity("oracle-full-reset"),universal_reset("unused-full-reset")}},
         {{"finish"},{"middle"},{"terminal"},
          {UniversalSet{1},UniversalSet{1}},
          {universal_reset("unused-finish-reset"),identity("oracle-terminal-reset")}}}};
    model::HybridRequest request{{{"source"},{0}},{{"terminal"}},
        {{{"terminal"},LinearTerminal{{1},0},"terminal cost","units"}}};

    // Walk the raw edge catalogue directly for horizon two; do not call the
    // production path enumerator. Then state the exact answer directly: u0 is
    // in [0,0.5] or [0,1], u1 is in [0,1], and both paths minimize u0 at zero
    // with complete face u0=0, 0<=u1<=1.
    std::vector<model::HybridPath> oracle_paths;
    for (const auto& first_edge:system.edges) {
        if (first_edge.source.value!="source") continue;
        for (const auto& second_edge:system.edges) {
            if (second_edge.source!=first_edge.target ||
                second_edge.target.value!="terminal") continue;
            oracle_paths.push_back({
                {request.initial.mode,first_edge.target,second_edge.target},
                {first_edge.id,second_edge.id}});
        }
    }
    const std::vector<model::HybridPath> expected_oracle_paths{
        {{{"source"},{"middle"},{"terminal"}},{{"enter-half"},{"finish"}}},
        {{{"source"},{"middle"},{"terminal"}},{{"enter-full"},{"finish"}}}};
    REQUIRE(oracle_paths==expected_oracle_paths);
    const auto built=build_hybrid_portfolio_programs(system,request,{"literal-oracle"},
        {2,8},{64,4096,65536});
    REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(built));
    const auto& programs=std::get<std::vector<HybridPathProgram>>(built);
    REQUIRE(programs.size()==oracle_paths.size());
    for (std::size_t i=0;i<oracle_paths.size();++i)
        CHECK(programs[i].path==oracle_paths[i]);

    // Independently state both complete branch relations in the documented
    // joint coordinate order (x0,u0,xpre0,x1,u1,xpre1,x2). The path guard
    // restricts u0 on the first branch; both controls are bounded by [0,1].
    // The flow and identity-reset equations give x2=u0. Since u0>=0 on each
    // branch and u0=0,u1=0.5 is feasible, each branch minimum is exactly zero.
    const auto matches_rows=[](const numeric::MatrixView& actual,
        const numeric::VectorView& actual_rhs,const std::vector<double>& expected,
        const std::vector<double>& expected_rhs,std::size_t columns) {
        REQUIRE(actual.rows()==expected_rhs.size());
        REQUIRE(actual_rhs.size()==expected_rhs.size());
        REQUIRE(actual.cols()==columns);
        std::vector<bool> matched(expected_rhs.size(),false);
        for (std::size_t row=0;row<actual.rows();++row) {
            bool found=false;
            for (std::size_t candidate=0;candidate<expected_rhs.size()&&!found;++candidate) {
                if (matched[candidate] || actual_rhs[row]!=expected_rhs[candidate]) continue;
                bool same=true;
                for (std::size_t col=0;col<columns;++col)
                    same=same && actual(row,col)==expected[candidate*columns+col];
                if (same) { matched[candidate]=true; found=true; }
            }
            CHECK_MESSAGE(found,"row "<<row<<" rhs "<<actual_rhs[row]<<" coefficients "<<
                actual(row,0)<<","<<actual(row,1)<<","<<actual(row,2)<<","<<actual(row,3)<<","<<
                actual(row,4)<<","<<actual(row,5)<<","<<actual(row,6));
        }
    };
    const std::vector<double> literal_equalities{
        1,0,0,0,0,0,0,
        0,-1,1,0,0,0,0,
        0,0,1,-1,0,0,0,
        0,0,0,-1,0,1,0,
        0,0,0,0,0,1,-1};
    const std::vector<double> literal_equality_rhs{0,0,0,0,0};
    for (std::size_t branch=0;branch<programs.size();++branch) {
        const auto representation=programs[branch].joint_relation.representation();
        REQUIRE(std::holds_alternative<sets::HRepresentation>(representation));
        const auto& h=std::get<sets::HRepresentation>(representation);
        if (branch==0) {
            matches_rows(h.inequalities,h.upper_bounds,
                {0,-1,0,0,0,0,0,
                 0,1,0,0,0,0,0,
                 0,0,-1,0,0,0,0,
                 0,0,1,0,0,0,0,
                 0,0,0,0,-1,0,0,
                 0,0,0,0,1,0,0},
                {0,1,0,0.5,0,1},7);
        } else {
            matches_rows(h.inequalities,h.upper_bounds,
                {0,-1,0,0,0,0,0,
                 0,1,0,0,0,0,0,
                 0,0,0,0,-1,0,0,
                 0,0,0,0,1,0,0},
                {0,1,0,1},7);
        }
        matches_rows(h.equalities,h.equality_values,literal_equalities,
            literal_equality_rhs,7);
        CHECK(std::get<LinearTerminal>(programs[branch].lifted_objective).coefficients==
            Vector{0,0,0,0,0,0,1});
        CHECK(std::get<LinearTerminal>(programs[branch].lifted_objective).offset==0);
    }

    const std::vector<double> face_inequalities{
        0,0,0,0,1,0,0,
        0,0,0,0,-1,0,0};
    const std::vector<double> face_equalities{
        1,0,0,0,0,0,0,
        0,1,0,0,0,0,0,
        0,0,1,0,0,0,0,
        0,0,0,1,0,0,0,
        0,0,0,0,0,1,0,
        0,0,0,0,0,0,1};
    const auto literal_face=[&](std::string id) {
        auto decoded=sets::from_handle(h_set(std::move(id),7,
            Matrix{2,7,face_inequalities},Vector{1,0},
            Matrix{6,7,face_equalities},Vector{0,0,0,0,0,0}));
        REQUIRE(std::holds_alternative<sets::SetData>(decoded));
        return std::get<sets::SetData>(std::move(decoded));
    };
    std::vector<HybridPathOptimalFaceCandidate> candidates;
    candidates.push_back(exact_candidate(programs[0],{0,0,0,0,0.5,0,0}));
    candidates.push_back(exact_candidate(programs[1],{0,0,0,0,0.5,0,0}));
    candidates[0].relation=literal_face("oracle-half-optimal-face");
    candidates[1].relation=literal_face("oracle-full-optimal-face");
    for (std::size_t branch=0;branch<candidates.size();++branch) {
        REQUIRE(candidates[branch].solver_result.primal.has_value());
        const auto& point=*candidates[branch].solver_result.primal;
        const auto& objective=std::get<LinearTerminal>(programs[branch].lifted_objective);
        double literal_cost=objective.offset;
        for (std::size_t coordinate=0;coordinate<point.size();++coordinate)
            literal_cost+=objective.coefficients[coordinate]*point[coordinate];
        CHECK(literal_cost==0.0);
    }
    ExactLinearHHybridFamilyVerifier verifier;
    const auto result=verify_hybrid_portfolio_family(verifier,system,request,
        programs,candidates,{2,8},{1e-9,1e-9});
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(result));
    const auto& report=std::get<HybridFamilyVerificationReport>(result);
    CHECK(report.global_objective_optimality==HybridVerificationStatus::established);
    CHECK(report.complete_family_coverage==HybridVerificationStatus::established);
    REQUIRE(report.branches.size()==2);
    CHECK(report.branches[0].objective_optimality==HybridVerificationStatus::established);
    CHECK(report.branches[0].continuous_coverage==HybridVerificationStatus::established);
    CHECK(report.branches[1].objective_optimality==HybridVerificationStatus::established);
    CHECK(report.branches[1].continuous_coverage==HybridVerificationStatus::established);
}

TEST_CASE("exact linear H verifier matches independent 2D continuous oracle") {
    const auto box2=h_set("oracle-control-box",2,
        Matrix{4,2,{-1,0,1,0,0,-1,0,1}},Vector{0,1,0,1},
        Matrix{0,2,{}},Vector{});
    const auto identity_reset=h_set("oracle-2d-identity-reset",4,
        Matrix{0,4,{}},Vector{},Matrix{2,4,{1,0,-1,0,0,1,0,-1}},Vector{0,0});
    model::HybridMode source{{"oracle-source-2d"},2,2,{"x0","x1"},{"u0","u1"}};
    source.flow=LinearStage{Matrix{2,2,{0,0,0,0}},Matrix{2,2,{1,0,0,1}},
        Matrix{2,0,{}},Vector{0,0}};
    source.control_sets={box2};
    source.invariants={UniversalSet{2},UniversalSet{2}};
    model::HybridMode terminal{{"oracle-terminal-2d"},2,0,{"y0","y1"},{}};
    terminal.flow=LinearStage{Matrix{2,2,{1,0,0,1}},Matrix{2,0,{}},
        Matrix{2,0,{}},Vector{0,0}};
    terminal.control_sets={UniversalSet{0}};
    terminal.invariants={UniversalSet{2},UniversalSet{2}};
    model::HybridSystem system{1,{source,terminal},
        {{{"oracle-edge-2d"},source.id,terminal.id,{UniversalSet{2}},{identity_reset}}}};
    model::HybridRequest request{{source.id,{0,0}},{terminal.id},
        {{terminal.id,LinearTerminal{{1,0},0},"first terminal coordinate","units"}}};

    // Independently enumerate the raw one-edge graph. The literal joint tuple
    // is (x0[0],x0[1],u0[0],u0[1],xpre[0],xpre[1],xpost[0],xpost[1]).
    std::vector<model::HybridPath> oracle_paths;
    for (const auto& edge:system.edges)
        if (edge.source==request.initial.mode && edge.target==terminal.id)
            oracle_paths.push_back({{request.initial.mode,edge.target},{edge.id}});
    const std::vector<model::HybridPath> expected_paths{
        {{source.id,terminal.id},{{"oracle-edge-2d"}}}};
    REQUIRE(oracle_paths==expected_paths);
    const auto built=build_hybrid_portfolio_programs(system,request,{"literal-2d-oracle"},
        {1,4},{32,128,2048});
    REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(built));
    const auto& programs=std::get<std::vector<HybridPathProgram>>(built);
    REQUIRE(programs.size()==1);
    CHECK(programs[0].path==oracle_paths[0]);
    const auto representation=programs[0].joint_relation.representation();
    REQUIRE(std::holds_alternative<sets::HRepresentation>(representation));
    const auto& h=std::get<sets::HRepresentation>(representation);

    const auto matches_literal_rows=[](const numeric::MatrixView& actual,
        const numeric::VectorView& rhs,const std::vector<double>& expected,
        const std::vector<double>& expected_rhs,std::size_t width) {
        REQUIRE(actual.rows()==expected_rhs.size());
        REQUIRE(rhs.size()==expected_rhs.size());
        REQUIRE(actual.cols()==width);
        std::vector<bool> matched(expected_rhs.size(),false);
        for (std::size_t row=0;row<actual.rows();++row) {
            bool found=false;
            for (std::size_t candidate=0;candidate<expected_rhs.size()&&!found;++candidate) {
                if (matched[candidate] || rhs[row]!=expected_rhs[candidate]) continue;
                bool equal=true;
                for (std::size_t column=0;column<width;++column)
                    equal=equal && actual(row,column)==expected[candidate*width+column];
                if (equal) { matched[candidate]=true; found=true; }
            }
            CHECK(found);
        }
    };
    matches_literal_rows(h.inequalities,h.upper_bounds,
        {0,0,-1,0,0,0,0,0,
         0,0,1,0,0,0,0,0,
         0,0,0,-1,0,0,0,0,
         0,0,0,1,0,0,0,0},
        {0,1,0,1},8);
    matches_literal_rows(h.equalities,h.equality_values,
        {1,0,0,0,0,0,0,0,
         0,1,0,0,0,0,0,0,
         0,0,-1,0,1,0,0,0,
         0,0,0,-1,0,1,0,0,
         0,0,0,0,1,0,-1,0,
         0,0,0,0,0,1,0,-1},
        {0,0,0,0,0,0},8);
    CHECK(std::get<LinearTerminal>(programs[0].lifted_objective).coefficients==
        Vector{0,0,0,0,0,0,1,0});
    CHECK(std::get<LinearTerminal>(programs[0].lifted_objective).offset==0);

    // The literal rows imply objective u0 >= 0. This feasible point attains
    // zero while u1 remains free, so the complete optimal face is u0=0,
    // 0<=u1<=1 across the two-dimensional state relation.
    const auto face=sets::from_handle(h_set("oracle-2d-optimal-face",8,
        Matrix{2,8,{0,0,0,1,0,0,0,0,0,0,0,-1,0,0,0,0}},Vector{1,0},
        Matrix{7,8,{1,0,0,0,0,0,0,0,
                    0,1,0,0,0,0,0,0,
                    0,0,1,0,0,0,0,0,
                    0,0,0,0,1,0,0,0,
                    0,0,0,0,0,0,1,0,
                    0,0,0,-1,0,1,0,0,
                    0,0,0,0,0,1,0,-1}},Vector{0,0,0,0,0,0,0}));
    REQUIRE(std::holds_alternative<sets::SetData>(face));
    auto candidate=exact_candidate(programs[0],{0,0,0,0.5,0,0.5,0,0.5});
    candidate.relation=std::get<sets::SetData>(face);
    REQUIRE(candidate.solver_result.primal.has_value());
    const auto& point=*candidate.solver_result.primal;
    const auto& objective=std::get<LinearTerminal>(programs[0].lifted_objective);
    double literal_cost=objective.offset;
    for (std::size_t i=0;i<point.size();++i)
        literal_cost+=objective.coefficients[i]*point[i];
    CHECK(literal_cost==0.0);

    ExactLinearHHybridFamilyVerifier verifier;
    const std::array<HybridPathOptimalFaceCandidate,1> candidates{std::move(candidate)};
    const auto verified=verify_hybrid_portfolio_family(verifier,system,request,
        programs,candidates,{1,4},{0,0});
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(verified));
    const auto& report=std::get<HybridFamilyVerificationReport>(verified);
    REQUIRE(report.branches.size()==1);
    std::string branch_diagnostics;
    for (const auto& diagnostic:report.branches[0].diagnostics)
        branch_diagnostics+=diagnostic.field+": "+diagnostic.explanation+"; ";
    CHECK(report.global_objective_optimality==HybridVerificationStatus::established);
    CHECK_MESSAGE(report.complete_family_coverage==HybridVerificationStatus::established,
        "Diagnostics: "<<branch_diagnostics);
    CHECK(report.branches[0].objective_optimality==HybridVerificationStatus::established);
    CHECK_MESSAGE(report.branches[0].continuous_coverage==HybridVerificationStatus::established,
        "Diagnostics: "<<branch_diagnostics);
}

TEST_CASE("exact linear H verifier preserves a continuous optimum across an existential reset") {
    const auto control=h_set("oracle-existential-reset-control",1,
        Matrix{2,1,{-1,1}},Vector{0,1},Matrix{0,1,{}},Vector{});
    const auto reset=h_set("oracle-existential-reset-relation",2,
        Matrix{2,2,{1,-1,-1,1}},Vector{0,1},Matrix{0,2,{}},Vector{});
    model::HybridMode source{{"oracle-reset-source"},1,1,{"x"},{"u"}};
    source.flow=LinearStage{Matrix{1,1,{1}},Matrix{1,1,{0}},
        Matrix{1,0,{}},Vector{0}};
    source.control_sets={control};
    source.invariants={UniversalSet{1},UniversalSet{1}};
    model::HybridMode target{{"oracle-reset-target"},1,0,{"y"},{}};
    target.flow=LinearStage{Matrix{1,1,{1}},Matrix{1,0,{}},
        Matrix{1,0,{}},Vector{0}};
    target.control_sets={UniversalSet{0}};
    target.invariants={UniversalSet{1},UniversalSet{1}};
    model::HybridSystem system{1,{source,target},
        {{{"oracle-existential-reset-edge"},source.id,target.id,
          {UniversalSet{1}},{reset}}}};
    model::HybridRequest request{{source.id,{0}},{target.id},
        {{target.id,LinearTerminal{{1},0},"terminal state","units"}}};

    const auto built=build_hybrid_portfolio_programs(system,request,
        {"oracle-existential-reset"},{1,2},{8,32,512});
    REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(built));
    const auto& programs=std::get<std::vector<HybridPathProgram>>(built);
    REQUIRE(programs.size()==1);
    CHECK(programs.front().joint_relation.metadata()->set.dimension==4);
    CHECK(std::get<LinearTerminal>(programs.front().lifted_objective).coefficients==
        Vector{0,0,0,1});

    // In tuple order (x0,u,x_pre,y), x0=0 and x_pre=x0 force x_pre=0.
    // The reset is 0<=y-x_pre<=1, so minimizing y fixes y=0 while leaving
    // the independent control coordinate u anywhere in [0,1].
    const auto full_face=sets::from_handle(h_set("oracle-existential-reset-full-face",4,
        Matrix{4,4,{0,-1,0,0, 0,1,0,0, 0,0,1,-1, 0,0,-1,1}},
        Vector{0,1,0,1},
        Matrix{3,4,{1,0,0,0, -1,0,1,0, 0,0,0,1}},Vector{0,0,0}));
    REQUIRE(std::holds_alternative<sets::SetData>(full_face));
    auto complete=exact_candidate(programs.front(),{0,0.5,0,0});
    complete.relation=std::get<sets::SetData>(full_face);

    ExactLinearHHybridFamilyVerifier verifier;
    const std::array<HybridPathOptimalFaceCandidate,1> complete_candidates{std::move(complete)};
    const auto verified=verify_hybrid_portfolio_family(verifier,system,request,
        programs,complete_candidates,{1,2},{0,0});
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(verified));
    const auto& report=std::get<HybridFamilyVerificationReport>(verified);
    CHECK(report.global_objective_optimality==HybridVerificationStatus::established);
    CHECK(report.complete_family_coverage==HybridVerificationStatus::established);
    REQUIRE(report.branches.size()==1);
    CHECK(report.branches.front().feasibility==HybridVerificationStatus::established);
    CHECK(report.branches.front().objective_optimality==HybridVerificationStatus::established);
    CHECK(report.branches.front().continuous_coverage==HybridVerificationStatus::established);

    // A face that fixes u=0 is feasible and optimal, but omits other optimal
    // points. The verifier must refute completeness instead of accepting it.
    const auto narrow_face=sets::from_handle(h_set("oracle-existential-reset-narrow-face",4,
        Matrix{4,4,{0,-1,0,0, 0,1,0,0, 0,0,1,-1, 0,0,-1,1}},
        Vector{0,1,0,1},
        Matrix{4,4,{1,0,0,0, -1,0,1,0, 0,0,0,1, 0,1,0,0}},
        Vector{0,0,0,0}));
    REQUIRE(std::holds_alternative<sets::SetData>(narrow_face));
    auto incomplete=exact_candidate(programs.front(),{0,0,0,0});
    incomplete.relation=std::get<sets::SetData>(narrow_face);
    const std::array<HybridPathOptimalFaceCandidate,1> incomplete_candidates{std::move(incomplete)};
    const auto rejected=verify_hybrid_portfolio_family(verifier,system,request,
        programs,incomplete_candidates,{1,2},{0,0});
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(rejected));
    const auto& rejected_report=std::get<HybridFamilyVerificationReport>(rejected);
    CHECK(rejected_report.global_objective_optimality==HybridVerificationStatus::established);
    CHECK(rejected_report.complete_family_coverage==HybridVerificationStatus::refuted);
    REQUIRE(rejected_report.branches.size()==1);
    CHECK(rejected_report.branches.front().feasibility==HybridVerificationStatus::established);
    CHECK(rejected_report.branches.front().objective_optimality==HybridVerificationStatus::established);
    CHECK(rejected_report.branches.front().continuous_coverage==HybridVerificationStatus::refuted);
}

TEST_CASE("exact linear H verifier checks a coupled two-control polytope through an existential reset") {
    const auto control=h_set("oracle-coupled-control-polytope",2,
        Matrix{4,2,{-1,0,0,-1,1,1,-1,-1}},Vector{0,0,2,-1},
        Matrix{0,2,{}},Vector{});
    const auto reset=h_set("oracle-coupled-existential-reset",2,
        Matrix{2,2,{1,-1,-1,1}},Vector{0,1},Matrix{0,2,{}},Vector{});
    model::HybridMode source{{"oracle-coupled-source"},1,2,{"x"},{"u","v"}};
    source.flow=LinearStage{Matrix{1,1,{0}},Matrix{1,2,{1,1}},
        Matrix{1,0,{}},Vector{0}};
    source.control_sets={control};
    source.invariants={UniversalSet{1},UniversalSet{1}};
    model::HybridMode target{{"oracle-coupled-target"},1,0,{"y"},{}};
    target.flow=LinearStage{Matrix{1,1,{1}},Matrix{1,0,{}},
        Matrix{1,0,{}},Vector{0}};
    target.control_sets={UniversalSet{0}};
    target.invariants={UniversalSet{1},UniversalSet{1}};
    model::HybridSystem system{1,{source,target},
        {{{"oracle-coupled-edge"},source.id,target.id,
          {UniversalSet{1}},{reset}}}};
    model::HybridRequest request{{source.id,{0}},{target.id},
        {{target.id,LinearTerminal{{1},0},"terminal state","units"}}};

    const auto built=build_hybrid_portfolio_programs(system,request,
        {"oracle-coupled-polytope"},{1,2},{8,32,512});
    REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(built));
    const auto& programs=std::get<std::vector<HybridPathProgram>>(built);
    REQUIRE(programs.size()==1);
    CHECK(programs.front().joint_relation.metadata()->set.dimension==5);
    CHECK(std::get<LinearTerminal>(programs.front().lifted_objective).coefficients==
        Vector{0,0,0,0,1});

    // Raw constraints are u,v>=0, 1<=u+v<=2, x_pre=u+v, and
    // x_pre<=y<=x_pre+1. Minimizing y gives y=x_pre=1 and the full
    // slanted optimal segment u+v=1, u,v>=0.
    const auto full_face=sets::from_handle(h_set("oracle-coupled-full-face",5,
        Matrix{6,5,{0,-1,0,0,0, 0,0,-1,0,0, 0,1,1,0,0,
                    0,-1,-1,0,0, 0,0,0,1,-1, 0,0,0,-1,1}},
        Vector{0,0,2,-1,0,1},
        Matrix{4,5,{1,0,0,0,0, 0,-1,-1,1,0,
                    0,1,1,0,0, 0,0,0,0,1}},
        Vector{0,0,1,1}));
    REQUIRE(std::holds_alternative<sets::SetData>(full_face));
    auto complete=exact_candidate(programs.front(),{0,0.5,0.5,1,1});
    complete.relation=std::get<sets::SetData>(full_face);
    ExactLinearHHybridFamilyVerifier verifier;
    const std::array<HybridPathOptimalFaceCandidate,1> complete_candidates{std::move(complete)};
    const auto verified=verify_hybrid_portfolio_family(verifier,system,request,
        programs,complete_candidates,{1,2},{0,0});
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(verified));
    const auto& report=std::get<HybridFamilyVerificationReport>(verified);
    CHECK(report.global_objective_optimality==HybridVerificationStatus::established);
    CHECK(report.complete_family_coverage==HybridVerificationStatus::established);
    REQUIRE(report.branches.size()==1);
    CHECK(report.branches.front().feasibility==HybridVerificationStatus::established);
    CHECK(report.branches.front().objective_optimality==HybridVerificationStatus::established);
    CHECK(report.branches.front().continuous_coverage==HybridVerificationStatus::established);

    // This proper subset still has feasible points with the optimal objective.
    const auto narrow_face=sets::from_handle(h_set("oracle-coupled-narrow-face",5,
        Matrix{7,5,{0,-1,0,0,0, 0,0,-1,0,0, 0,1,1,0,0,
                    0,-1,-1,0,0, 0,0,0,1,-1, 0,0,0,-1,1,
                    0,1,0,0,0}},
        Vector{0,0,2,-1,0,1,0.5},
        Matrix{4,5,{1,0,0,0,0, 0,-1,-1,1,0,
                    0,1,1,0,0, 0,0,0,0,1}},
        Vector{0,0,1,1}));
    REQUIRE(std::holds_alternative<sets::SetData>(narrow_face));
    auto incomplete=exact_candidate(programs.front(),{0,0.25,0.75,1,1});
    incomplete.relation=std::get<sets::SetData>(narrow_face);
    const std::array<HybridPathOptimalFaceCandidate,1> incomplete_candidates{std::move(incomplete)};
    const auto rejected=verify_hybrid_portfolio_family(verifier,system,request,
        programs,incomplete_candidates,{1,2},{0,0});
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(rejected));
    const auto& rejected_report=std::get<HybridFamilyVerificationReport>(rejected);
    CHECK(rejected_report.global_objective_optimality==HybridVerificationStatus::established);
    CHECK(rejected_report.complete_family_coverage==HybridVerificationStatus::refuted);
    REQUIRE(rejected_report.branches.size()==1);
    CHECK(rejected_report.branches.front().feasibility==HybridVerificationStatus::established);
    CHECK(rejected_report.branches.front().objective_optimality==HybridVerificationStatus::established);
    CHECK(rejected_report.branches.front().continuous_coverage==HybridVerificationStatus::refuted);
}

TEST_CASE("exact linear H verifier preserves a three-control simplex through an existential reset") {
    const auto control=h_set("oracle-three-control-simplex",3,
        Matrix{4,3,{-1,0,0, 0,-1,0, 0,0,-1, 1,1,1}},Vector{0,0,0,1},
        Matrix{0,3,{}},Vector{});
    const auto reset=h_set("oracle-three-control-reset",2,
        Matrix{2,2,{0,-1,-1,1}},Vector{0,0},Matrix{0,2,{}},Vector{});
    model::HybridMode source{{"oracle-simplex-source"},1,3,{"x"},{"u","v","w"}};
    source.flow=LinearStage{Matrix{1,1,{0}},Matrix{1,3,{1,1,1}},
        Matrix{1,0,{}},Vector{0}};
    source.control_sets={control};
    source.invariants={UniversalSet{1},UniversalSet{1}};
    model::HybridMode target{{"oracle-simplex-target"},1,0,{"y"},{}};
    target.flow=LinearStage{Matrix{1,1,{1}},Matrix{1,0,{}},
        Matrix{1,0,{}},Vector{0}};
    target.control_sets={UniversalSet{0}};
    target.invariants={UniversalSet{1},UniversalSet{1}};
    model::HybridSystem system{1,{source,target},
        {{{"oracle-simplex-edge"},source.id,target.id,
          {UniversalSet{1}},{reset}}}};
    model::HybridRequest request{{source.id,{0}},{target.id},
        {{target.id,LinearTerminal{{1},0},"terminal state","units"}}};

    const auto built=build_hybrid_portfolio_programs(system,request,
        {"oracle-three-control-simplex"},{1,2},{8,32,512});
    REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(built));
    const auto& programs=std::get<std::vector<HybridPathProgram>>(built);
    REQUIRE(programs.size()==1);
    CHECK(programs.front().joint_relation.metadata()->set.dimension==6);
    CHECK(std::get<LinearTerminal>(programs.front().lifted_objective).coefficients==
        Vector{0,0,0,0,0,1});

    // Controls form the simplex u,v,w>=0, u+v+w<=1. The flow gives
    // x_pre=u+v+w, and the existential reset gives 0<=y<=x_pre. The
    // minimum y=0 leaves the entire three-dimensional control simplex free.
    const auto full_face=sets::from_handle(h_set("oracle-three-control-full-face",6,
        Matrix{6,6,{0,-1,0,0,0,0, 0,0,-1,0,0,0, 0,0,0,-1,0,0,
                    0,1,1,1,0,0, 0,0,0,0,-1,0, 0,0,0,0,-1,1}},
        Vector{0,0,0,1,0,0},
        Matrix{3,6,{1,0,0,0,0,0, 0,-1,-1,-1,1,0,
                    0,0,0,0,0,1}},
        Vector{0,0,0}));
    REQUIRE(std::holds_alternative<sets::SetData>(full_face));
    auto complete=exact_candidate(programs.front(),{0,0.25,0.25,0.25,0.75,0});
    complete.relation=std::get<sets::SetData>(full_face);
    ExactLinearHHybridFamilyVerifier verifier;
    const std::array<HybridPathOptimalFaceCandidate,1> complete_candidates{std::move(complete)};
    const auto verified=verify_hybrid_portfolio_family(verifier,system,request,
        programs,complete_candidates,{1,2},{0,0});
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(verified));
    const auto& report=std::get<HybridFamilyVerificationReport>(verified);
    CHECK(report.global_objective_optimality==HybridVerificationStatus::established);
    CHECK(report.complete_family_coverage==HybridVerificationStatus::established);
    REQUIRE(report.branches.size()==1);
    CHECK(report.branches.front().feasibility==HybridVerificationStatus::established);
    CHECK(report.branches.front().objective_optimality==HybridVerificationStatus::established);
    CHECK(report.branches.front().continuous_coverage==HybridVerificationStatus::established);

    // The additional u<=0.5 facet excludes part of the simplex but retains
    // optimal points such as (u,v,w)=(0.25,0.25,0.25).
    const auto narrow_face=sets::from_handle(h_set("oracle-three-control-narrow-face",6,
        Matrix{7,6,{0,-1,0,0,0,0, 0,0,-1,0,0,0, 0,0,0,-1,0,0,
                    0,1,1,1,0,0, 0,0,0,0,-1,0, 0,0,0,0,-1,1,
                    0,1,0,0,0,0}},
        Vector{0,0,0,1,0,0,0.5},
        Matrix{3,6,{1,0,0,0,0,0, 0,-1,-1,-1,1,0,
                    0,0,0,0,0,1}},
        Vector{0,0,0}));
    REQUIRE(std::holds_alternative<sets::SetData>(narrow_face));
    auto incomplete=exact_candidate(programs.front(),{0,0.25,0.25,0.25,0.75,0});
    incomplete.relation=std::get<sets::SetData>(narrow_face);
    const std::array<HybridPathOptimalFaceCandidate,1> incomplete_candidates{std::move(incomplete)};
    const auto rejected=verify_hybrid_portfolio_family(verifier,system,request,
        programs,incomplete_candidates,{1,2},{0,0});
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(rejected));
    const auto& rejected_report=std::get<HybridFamilyVerificationReport>(rejected);
    CHECK(rejected_report.global_objective_optimality==HybridVerificationStatus::established);
    CHECK(rejected_report.complete_family_coverage==HybridVerificationStatus::refuted);
    REQUIRE(rejected_report.branches.size()==1);
    CHECK(rejected_report.branches.front().feasibility==HybridVerificationStatus::established);
    CHECK(rejected_report.branches.front().objective_optimality==HybridVerificationStatus::established);
    CHECK(rejected_report.branches.front().continuous_coverage==HybridVerificationStatus::refuted);
}

TEST_CASE("exact linear H verifier preserves a truncated three-control box through an existential reset") {
    const auto control=h_set("oracle-three-control-truncated-box",3,
        Matrix{7,3,{-1,0,0, 0,-1,0, 0,0,-1, 1,0,0, 0,1,0, 0,0,1, 1,1,1}},
        Vector{0,0,0,1,1,1,2},Matrix{0,3,{}},Vector{});
    const auto reset=h_set("oracle-truncated-box-reset",2,
        Matrix{2,2,{0,-1,-1,1}},Vector{0,0},Matrix{0,2,{}},Vector{});
    model::HybridMode source{{"oracle-truncated-box-source"},1,3,{"x"},{"u","v","w"}};
    source.flow=LinearStage{Matrix{1,1,{0}},Matrix{1,3,{1,1,1}},
        Matrix{1,0,{}},Vector{0}};
    source.control_sets={control};
    source.invariants={UniversalSet{1},UniversalSet{1}};
    model::HybridMode target{{"oracle-truncated-box-target"},1,0,{"y"},{}};
    target.flow=LinearStage{Matrix{1,1,{1}},Matrix{1,0,{}},
        Matrix{1,0,{}},Vector{0}};
    target.control_sets={UniversalSet{0}};
    target.invariants={UniversalSet{1},UniversalSet{1}};
    model::HybridSystem system{1,{source,target},
        {{{"oracle-truncated-box-edge"},source.id,target.id,
          {UniversalSet{1}},{reset}}}};
    model::HybridRequest request{{source.id,{0}},{target.id},
        {{target.id,LinearTerminal{{1},0},"terminal state","units"}}};

    const auto built=build_hybrid_portfolio_programs(system,request,
        {"oracle-three-control-truncated-box"},{1,2},{8,32,512});
    REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(built));
    const auto& programs=std::get<std::vector<HybridPathProgram>>(built);
    REQUIRE(programs.size()==1);
    CHECK(programs.front().joint_relation.metadata()->set.dimension==6);

    // The controls lie in [0,1]^3 with u+v+w<=2, a truncated cube rather
    // than a simplex. The reset gives 0<=y<=u+v+w. Minimizing y leaves the
    // full three-dimensional truncated-cube family at y=0.
    const auto full_face=sets::from_handle(h_set("oracle-truncated-box-full-face",6,
        Matrix{9,6,{0,-1,0,0,0,0, 0,0,-1,0,0,0, 0,0,0,-1,0,0,
                    0,1,0,0,0,0, 0,0,1,0,0,0, 0,0,0,1,0,0,
                    0,1,1,1,0,0, 0,0,0,0,-1,0, 0,0,0,0,-1,1}},
        Vector{0,0,0,1,1,1,2,0,0},
        Matrix{3,6,{1,0,0,0,0,0, 0,-1,-1,-1,1,0,
                    0,0,0,0,0,1}},
        Vector{0,0,0}));
    REQUIRE(std::holds_alternative<sets::SetData>(full_face));
    auto complete=exact_candidate(programs.front(),{0,0.5,0.5,0.5,1.5,0});
    complete.relation=std::get<sets::SetData>(full_face);
    ExactLinearHHybridFamilyVerifier verifier;
    const std::array<HybridPathOptimalFaceCandidate,1> complete_candidates{std::move(complete)};
    const auto verified=verify_hybrid_portfolio_family(verifier,system,request,
        programs,complete_candidates,{1,2},{0,0});
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(verified));
    const auto& report=std::get<HybridFamilyVerificationReport>(verified);
    CHECK(report.global_objective_optimality==HybridVerificationStatus::established);
    CHECK(report.complete_family_coverage==HybridVerificationStatus::established);
    REQUIRE(report.branches.size()==1);
    CHECK(report.branches.front().feasibility==HybridVerificationStatus::established);
    CHECK(report.branches.front().objective_optimality==HybridVerificationStatus::established);
    CHECK(report.branches.front().continuous_coverage==HybridVerificationStatus::established);

    // u<=0.5 retains feasible optimal points but cuts off part of the cube.
    const auto narrow_face=sets::from_handle(h_set("oracle-truncated-box-narrow-face",6,
        Matrix{10,6,{0,-1,0,0,0,0, 0,0,-1,0,0,0, 0,0,0,-1,0,0,
                     0,1,0,0,0,0, 0,0,1,0,0,0, 0,0,0,1,0,0,
                     0,1,1,1,0,0, 0,0,0,0,-1,0, 0,0,0,0,-1,1,
                     0,1,0,0,0,0}},
        Vector{0,0,0,1,1,1,2,0,0,0.5},
        Matrix{3,6,{1,0,0,0,0,0, 0,-1,-1,-1,1,0,
                    0,0,0,0,0,1}},
        Vector{0,0,0}));
    REQUIRE(std::holds_alternative<sets::SetData>(narrow_face));
    auto incomplete=exact_candidate(programs.front(),{0,0.5,0.5,0.5,1.5,0});
    incomplete.relation=std::get<sets::SetData>(narrow_face);
    const std::array<HybridPathOptimalFaceCandidate,1> incomplete_candidates{std::move(incomplete)};
    const auto rejected=verify_hybrid_portfolio_family(verifier,system,request,
        programs,incomplete_candidates,{1,2},{0,0});
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(rejected));
    const auto& rejected_report=std::get<HybridFamilyVerificationReport>(rejected);
    CHECK(rejected_report.global_objective_optimality==HybridVerificationStatus::established);
    CHECK(rejected_report.complete_family_coverage==HybridVerificationStatus::refuted);
    REQUIRE(rejected_report.branches.size()==1);
    CHECK(rejected_report.branches.front().feasibility==HybridVerificationStatus::established);
    CHECK(rejected_report.branches.front().objective_optimality==HybridVerificationStatus::established);
    CHECK(rejected_report.branches.front().continuous_coverage==HybridVerificationStatus::refuted);
}

TEST_CASE("exact linear H verifier preserves a four-control simplex through an existential reset") {
    const auto control=h_set("oracle-four-control-simplex",4,
        Matrix{5,4,{-1,0,0,0, 0,-1,0,0, 0,0,-1,0, 0,0,0,-1, 1,1,1,1}},
        Vector{0,0,0,0,1},Matrix{0,4,{}},Vector{});
    const auto reset=h_set("oracle-four-control-reset",2,
        Matrix{2,2,{0,-1,-1,1}},Vector{0,0},Matrix{0,2,{}},Vector{});
    model::HybridMode source{{"oracle-four-simplex-source"},1,4,{"x"},{"u","v","w","z"}};
    source.flow=LinearStage{Matrix{1,1,{0}},Matrix{1,4,{1,1,1,1}},
        Matrix{1,0,{}},Vector{0}};
    source.control_sets={control};
    source.invariants={UniversalSet{1},UniversalSet{1}};
    model::HybridMode target{{"oracle-four-simplex-target"},1,0,{"y"},{}};
    target.flow=LinearStage{Matrix{1,1,{1}},Matrix{1,0,{}},
        Matrix{1,0,{}},Vector{0}};
    target.control_sets={UniversalSet{0}};
    target.invariants={UniversalSet{1},UniversalSet{1}};
    model::HybridSystem system{1,{source,target},
        {{{"oracle-four-simplex-edge"},source.id,target.id,
          {UniversalSet{1}},{reset}}}};
    model::HybridRequest request{{source.id,{0}},{target.id},
        {{target.id,LinearTerminal{{1},0},"terminal state","units"}}};

    const auto built=build_hybrid_portfolio_programs(system,request,
        {"oracle-four-control-simplex"},{1,2},{9,40,768});
    REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(built));
    const auto& programs=std::get<std::vector<HybridPathProgram>>(built);
    REQUIRE(programs.size()==1);
    CHECK(programs.front().joint_relation.metadata()->set.dimension==7);

    // The controls satisfy u,v,w,z>=0 and u+v+w+z<=1. The flow gives
    // x_pre=u+v+w+z; the existential reset gives 0<=y<=x_pre. Minimizing
    // y leaves the full four-dimensional simplex at y=0.
    const auto full_face=sets::from_handle(h_set("oracle-four-simplex-full-face",7,
        Matrix{7,7,{0,-1,0,0,0,0,0, 0,0,-1,0,0,0,0,
                    0,0,0,-1,0,0,0, 0,0,0,0,-1,0,0,
                    0,1,1,1,1,0,0, 0,0,0,0,0,-1,0,
                    0,0,0,0,0,-1,1}},
        Vector{0,0,0,0,1,0,0},
        Matrix{3,7,{1,0,0,0,0,0,0, 0,-1,-1,-1,-1,1,0,
                    0,0,0,0,0,0,1}},
        Vector{0,0,0}));
    REQUIRE(std::holds_alternative<sets::SetData>(full_face));
    auto complete=exact_candidate(programs.front(),{0,0.125,0.125,0.125,0.125,0.5,0});
    complete.relation=std::get<sets::SetData>(full_face);
    ExactLinearHHybridFamilyVerifier verifier;
    const std::array<HybridPathOptimalFaceCandidate,1> complete_candidates{std::move(complete)};
    const auto verified=verify_hybrid_portfolio_family(verifier,system,request,
        programs,complete_candidates,{1,2},{0,0});
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(verified));
    const auto& report=std::get<HybridFamilyVerificationReport>(verified);
    CHECK(report.global_objective_optimality==HybridVerificationStatus::established);
    CHECK(report.complete_family_coverage==HybridVerificationStatus::established);
    REQUIRE(report.branches.size()==1);
    CHECK(report.branches.front().feasibility==HybridVerificationStatus::established);
    CHECK(report.branches.front().objective_optimality==HybridVerificationStatus::established);
    CHECK(report.branches.front().continuous_coverage==HybridVerificationStatus::established);

    // u<=0.125 keeps the dyadic witness but excludes the rest of the simplex.
    const auto narrow_face=sets::from_handle(h_set("oracle-four-simplex-narrow-face",7,
        Matrix{8,7,{0,-1,0,0,0,0,0, 0,0,-1,0,0,0,0,
                    0,0,0,-1,0,0,0, 0,0,0,0,-1,0,0,
                    0,1,1,1,1,0,0, 0,0,0,0,0,-1,0,
                    0,0,0,0,0,-1,1, 0,1,0,0,0,0,0}},
        Vector{0,0,0,0,1,0,0,0.125},
        Matrix{3,7,{1,0,0,0,0,0,0, 0,-1,-1,-1,-1,1,0,
                    0,0,0,0,0,0,1}},
        Vector{0,0,0}));
    REQUIRE(std::holds_alternative<sets::SetData>(narrow_face));
    auto incomplete=exact_candidate(programs.front(),{0,0.125,0.125,0.125,0.125,0.5,0});
    incomplete.relation=std::get<sets::SetData>(narrow_face);
    const std::array<HybridPathOptimalFaceCandidate,1> incomplete_candidates{std::move(incomplete)};
    const auto rejected=verify_hybrid_portfolio_family(verifier,system,request,
        programs,incomplete_candidates,{1,2},{0,0});
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(rejected));
    const auto& rejected_report=std::get<HybridFamilyVerificationReport>(rejected);
    CHECK(rejected_report.global_objective_optimality==HybridVerificationStatus::established);
    CHECK(rejected_report.complete_family_coverage==HybridVerificationStatus::refuted);
    REQUIRE(rejected_report.branches.size()==1);
    CHECK(rejected_report.branches.front().feasibility==HybridVerificationStatus::established);
    CHECK(rejected_report.branches.front().objective_optimality==HybridVerificationStatus::established);
    CHECK(rejected_report.branches.front().continuous_coverage==HybridVerificationStatus::refuted);
}

TEST_CASE("exact linear H verifier checks a five-control simplex optimal family") {
    std::vector<double> control_rows(6*5,0.0);
    std::vector<double> control_bounds(6,0.0);
    for(std::size_t control=0;control<5;++control) {
        control_rows[control*5+control]=-1;
        control_rows[5*5+control]=1;
    }
    control_bounds[5]=1;
    const auto control=h_set("oracle-five-control-simplex",5,
        Matrix{6,5,std::move(control_rows)},std::move(control_bounds),
        Matrix{0,5,{}},Vector{});
    const auto reset=h_set("oracle-five-control-reset",2,
        Matrix{2,2,{0,-1,-1,1}},Vector{0,0},Matrix{0,2,{}},Vector{});
    model::HybridMode source{{"oracle-five-simplex-source"},1,5,{"x"},
        {"u0","u1","u2","u3","u4"}};
    source.flow=LinearStage{Matrix{1,1,{0}},Matrix{1,5,{1,1,1,1,1}},
        Matrix{1,0,{}},Vector{0}};
    source.control_sets={control};
    source.invariants={UniversalSet{1},UniversalSet{1}};
    model::HybridMode target{{"oracle-five-simplex-target"},1,0,{"y"},{}};
    target.flow=LinearStage{Matrix{1,1,{1}},Matrix{1,0,{}},
        Matrix{1,0,{}},Vector{0}};
    target.control_sets={UniversalSet{0}};
    target.invariants={UniversalSet{1},UniversalSet{1}};
    model::HybridSystem system{1,{source,target},
        {{{"oracle-five-simplex-edge"},source.id,target.id,
          {UniversalSet{1}},{reset}}}};
    model::HybridRequest request{{source.id,{0}},{target.id},
        {{target.id,LinearTerminal{{1},0},"terminal state","units"}}};

    const auto built=build_hybrid_portfolio_programs(system,request,
        {"oracle-five-control-simplex"},{1,2},{10,64,1024});
    REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(built));
    const auto& programs=std::get<std::vector<HybridPathProgram>>(built);
    REQUIRE(programs.size()==1);
    CHECK(programs.front().joint_relation.metadata()->set.dimension==8);

    // [x0,u0..u4,x_pre,y] has u_i>=0, sum(u)<=1, x_pre=sum(u),
    // and 0<=y<=x_pre. The minimum y=0 leaves the complete simplex free.
    const auto make_face=[](bool narrow) {
        const std::size_t inequality_count=narrow?9:8;
        std::vector<double> inequalities(inequality_count*8,0.0);
        std::vector<double> upper_bounds(inequality_count,0.0);
        for(std::size_t control=0;control<5;++control)
            inequalities[control*8+1+control]=-1;
        for(std::size_t control=0;control<5;++control)
            inequalities[5*8+1+control]=1;
        upper_bounds[5]=1;
        inequalities[6*8+7]=-1;
        inequalities[7*8+6]=-1;
        inequalities[7*8+7]=1;
        if(narrow) {
            inequalities[8*8+1]=1;
            upper_bounds[8]=0.25;
        }
        const Matrix equalities{3,8,{1,0,0,0,0,0,0,0,
            0,-1,-1,-1,-1,-1,1,0, 0,0,0,0,0,0,0,1}};
        const Vector equality_values{0,0,0};
        return sets::from_handle(h_set(narrow?"oracle-five-simplex-narrow":"oracle-five-simplex-full",
            8,Matrix{inequality_count,8,std::move(inequalities)},std::move(upper_bounds),
            equalities,equality_values));
    };
    const auto full_face=make_face(false);
    REQUIRE(std::holds_alternative<sets::SetData>(full_face));
    auto complete=exact_candidate(programs.front(),{0,0.125,0.125,0.125,0.125,0.125,0.625,0});
    complete.relation=std::get<sets::SetData>(full_face);
    ExactLinearHHybridFamilyVerifier verifier;
    const std::array<HybridPathOptimalFaceCandidate,1> complete_candidates{std::move(complete)};
    const auto verified=verify_hybrid_portfolio_family(verifier,system,request,
        programs,complete_candidates,{1,2},{0,0});
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(verified));
    const auto& report=std::get<HybridFamilyVerificationReport>(verified);
    CHECK(report.global_objective_optimality==HybridVerificationStatus::established);
    CHECK(report.complete_family_coverage==HybridVerificationStatus::established);
    REQUIRE(report.branches.size()==1);
    CHECK(report.branches.front().feasibility==HybridVerificationStatus::established);
    CHECK(report.branches.front().objective_optimality==HybridVerificationStatus::established);
    CHECK(report.branches.front().continuous_coverage==HybridVerificationStatus::established);

    const auto narrow_face=make_face(true);
    REQUIRE(std::holds_alternative<sets::SetData>(narrow_face));
    auto incomplete=exact_candidate(programs.front(),{0,0.125,0.125,0.125,0.125,0.125,0.625,0});
    incomplete.relation=std::get<sets::SetData>(narrow_face);
    const std::array<HybridPathOptimalFaceCandidate,1> incomplete_candidates{std::move(incomplete)};
    const auto rejected=verify_hybrid_portfolio_family(verifier,system,request,
        programs,incomplete_candidates,{1,2},{0,0});
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(rejected));
    const auto& rejected_report=std::get<HybridFamilyVerificationReport>(rejected);
    CHECK(rejected_report.global_objective_optimality==HybridVerificationStatus::established);
    CHECK(rejected_report.complete_family_coverage==HybridVerificationStatus::refuted);
    REQUIRE(rejected_report.branches.size()==1);
    CHECK(rejected_report.branches.front().feasibility==HybridVerificationStatus::established);
    CHECK(rejected_report.branches.front().objective_optimality==HybridVerificationStatus::established);
    CHECK(rejected_report.branches.front().continuous_coverage==HybridVerificationStatus::refuted);
}

TEST_CASE("exact linear H verifier checks tied two-stage continuous branches with four controls") {
    const auto interval=[](std::string id,double lower,double upper) {
        return h_set(std::move(id),1,Matrix{2,1,{-1,1}},
            Vector{-lower,upper},Matrix{0,1,{}},Vector{});
    };
    const auto raw_path_oracle=[](const model::HybridSystem& graph,
            model::HybridModeId initial,const std::vector<model::HybridModeId>& terminals) {
        std::vector<model::HybridPath> paths{{{initial},{}}};
        for(std::size_t stage=0;stage<graph.horizon;++stage) {
            std::vector<model::HybridPath> next;
            for(const auto& prefix:paths) for(const auto& edge:graph.edges) {
                if(edge.source!=prefix.modes.back()) continue;
                auto extended=prefix;
                extended.edges.push_back(edge.id);
                extended.modes.push_back(edge.target);
                next.push_back(std::move(extended));
            }
            paths=std::move(next);
        }
        paths.erase(std::remove_if(paths.begin(),paths.end(),[&](const auto& path) {
            return std::find(terminals.begin(),terminals.end(),path.modes.back())==terminals.end();
        }),paths.end());
        return paths;
    };
    const auto literal_h_contains=[](const sets::HRepresentation& h,const Vector& point) {
        if(point.size()!=h.inequalities.cols() || point.size()!=h.equalities.cols()) return false;
        for(std::size_t i=0;i<h.inequalities.rows();++i) {
            double value=0;
            for(std::size_t j=0;j<h.inequalities.cols();++j) value+=h.inequalities(i,j)*point[j];
            if(value>h.upper_bounds[i]) return false;
        }
        for(std::size_t i=0;i<h.equalities.rows();++i) {
            double value=0;
            for(std::size_t j=0;j<h.equalities.cols();++j) value+=h.equalities(i,j)*point[j];
            if(value!=h.equality_values[i]) return false;
        }
        return true;
    };
    const auto control_box=[](std::string id) {
        return h_set(std::move(id),2,
            Matrix{4,2,{-1,0,1,0,0,-1,0,1}},Vector{0,1,0,1},
            Matrix{1,2,{0,0}},Vector{0});
    };
    const auto reset_to_middle=h_set("oracle-two-stage-set-valued-reset",3,
        Matrix{2,3,{0,0,-1,0,0,1}},Vector{0,1},
        Matrix{1,3,{-1,1,0}},Vector{0});
    const auto identity_reset=h_set("oracle-two-stage-identity-reset",4,
        Matrix{1,4,{0,0,0,0}},Vector{0},
        Matrix{2,4,{1,0,-1,0,0,1,0,-1}},Vector{0,0});
    const auto source_control=control_box("oracle-two-stage-source-control");
    const auto middle_control=control_box("oracle-two-stage-middle-control");
    model::HybridMode source{{"oracle-two-stage-source"},1,2,{"x"},{"u0","u1"}};
    const LinearStage source_flow{Matrix{1,1,{0}},Matrix{1,2,{1,1}},
        Matrix{1,0,{}},Vector{0}};
    source.flow=std::vector<LinearStage>{source_flow,source_flow};
    source.control_sets={source_control,source_control};
    source.invariants={UniversalSet{1},UniversalSet{1},UniversalSet{1}};
    model::HybridMode middle{{"oracle-two-stage-middle"},2,2,{"p","q"},{"v0","v1"}};
    const LinearStage unused_middle_flow{Matrix{2,2,{1,0,0,1}},Matrix{2,2,{0,0,0,0}},
        Matrix{2,0,{}},Vector{0,0}};
    const LinearStage terminal_flow{Matrix{2,2,{0,1,1,0}},Matrix{2,2,{0,0,1,1}},
        Matrix{2,0,{}},Vector{0,0}};
    middle.flow=std::vector<LinearStage>{unused_middle_flow,terminal_flow};
    middle.control_sets={middle_control,middle_control};
    middle.invariants={UniversalSet{2},UniversalSet{2},UniversalSet{2}};
    model::HybridMode target{{"oracle-two-stage-target"},2,0,{"y","z"},{}};
    const LinearStage target_stage{Matrix{2,2,{1,0,0,1}},Matrix{2,0,{}},
        Matrix{2,0,{}},Vector{0,0}};
    target.flow=std::vector<LinearStage>{target_stage,target_stage};
    target.control_sets={UniversalSet{0},UniversalSet{0}};
    target.invariants={UniversalSet{2},UniversalSet{2},UniversalSet{2}};
    model::HybridSystem system{2,{source,middle,target},
        {{{"branch-wide"},source.id,middle.id,
          {interval("oracle-two-stage-wide-guard",0,1),UniversalSet{1}},
          {reset_to_middle,reset_to_middle}},
         {{"branch-narrow"},source.id,middle.id,
          {interval("oracle-two-stage-narrow-guard",0,0.5),UniversalSet{1}},
          {reset_to_middle,reset_to_middle}},
         {{"branch-finish"},middle.id,target.id,
          {UniversalSet{2},UniversalSet{2}},{identity_reset,identity_reset}}}};
    model::HybridRequest request{{source.id,{0}},{target.id},
        {{target.id,LinearTerminal{{1,0},0},"terminal y","units"}}};

    // Independent raw-graph expansion finds both parallel-edge histories.
    const auto oracle_paths=raw_path_oracle(system,request.initial.mode,
        request.allowed_terminal_modes);
    const std::vector<model::HybridPath> expected_paths{
        {{source.id,middle.id,target.id},{{"branch-wide"},{"branch-finish"}}},
        {{source.id,middle.id,target.id},{{"branch-narrow"},{"branch-finish"}}}};
    REQUIRE(oracle_paths==expected_paths);
    const auto built=build_hybrid_portfolio_programs(system,request,
        {"oracle-two-stage-four-control"},{2,2},{13,4096,131072});
    REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(built));
    const auto& programs=std::get<std::vector<HybridPathProgram>>(built);
    REQUIRE(programs.size()==oracle_paths.size());
    for(std::size_t i=0;i<programs.size();++i) {
        CHECK(programs[i].path==oracle_paths[i]);
        CHECK(programs[i].joint_relation.metadata()->set.dimension==12);
    }

    // Joint coordinate order is (x0,u0,u1,x_pre,p,q,v0,v1,r0,r1,y,z).
    // Raw equations give x_pre=p=u0+u1, 0<=q<=1, r0=q,
    // r1=p+v0+v1, and (y,z)=(r0,r1). Both branches minimize y=q at zero.
    // Their distinct guards leave four free controls in separate full-dimensional
    // optimal polytopes: u0+u1<=1 and u0+u1<=0.5 respectively.
    const auto optimal_face=[](std::string id,double guard_upper,bool clip_u0) {
        std::vector<double> inequalities;
        std::vector<double> upper_bounds;
        const auto add_inequality=[&](std::size_t coordinate,double coefficient,double rhs) {
            std::vector<double> row(12,0);
            row[coordinate]=coefficient;
            inequalities.insert(inequalities.end(),row.begin(),row.end());
            upper_bounds.push_back(rhs);
        };
        add_inequality(1,-1,0); add_inequality(1,1,1);
        add_inequality(2,-1,0); add_inequality(2,1,1);
        add_inequality(6,-1,0); add_inequality(6,1,1);
        add_inequality(7,-1,0); add_inequality(7,1,1);
        add_inequality(5,-1,0); add_inequality(5,1,1);
        add_inequality(3,-1,0); add_inequality(3,1,guard_upper);
        if(clip_u0) add_inequality(1,1,0.125);

        std::vector<double> equalities;
        const auto add_equality=[&](std::initializer_list<std::pair<std::size_t,double>> entries) {
            std::vector<double> row(12,0);
            for(const auto& [coordinate,coefficient]:entries) row[coordinate]=coefficient;
            equalities.insert(equalities.end(),row.begin(),row.end());
        };
        add_equality({{0,1}});
        add_equality({{1,-1},{2,-1},{3,1}});
        add_equality({{3,-1},{4,1}});
        add_equality({{5,-1},{8,1}});
        add_equality({{4,-1},{6,-1},{7,-1},{9,1}});
        add_equality({{8,-1},{10,1}});
        add_equality({{9,-1},{11,1}});
        add_equality({{10,1}});
        const auto inequality_count=upper_bounds.size();
        return h_set(std::move(id),12,
            Matrix{inequality_count,12,std::move(inequalities)},std::move(upper_bounds),
            Matrix{8,12,std::move(equalities)},Vector(8,0));
    };

    const auto candidate_for=[&](const HybridPathProgram& program,bool clip_u0) {
        const bool narrow=program.path.edges.front().value=="branch-narrow";
        auto candidate=exact_candidate(program,narrow
            ?Vector{0,0.125,0.125,0.25,0.25,0,0.125,0.125,0,0.5,0,0.5}
            :Vector{0,0.25,0.25,0.5,0.5,0,0.25,0.25,0,1,0,1});
        const auto face=sets::from_handle(optimal_face(
            narrow?"oracle-two-stage-narrow-face":"oracle-two-stage-wide-face",
            narrow?0.5:1,clip_u0));
        REQUIRE(std::holds_alternative<sets::SetData>(face));
        candidate.relation=std::get<sets::SetData>(face);
        return candidate;
    };
    ExactLinearHHybridFamilyVerifier verifier;
    std::vector<HybridPathOptimalFaceCandidate> complete_candidates;
    for(const auto& program:programs) complete_candidates.push_back(candidate_for(program,false));
    const auto complete=verify_hybrid_portfolio_family(verifier,system,request,programs,
        complete_candidates,{2,2},{0,0});
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(complete));
    const auto& complete_report=std::get<HybridFamilyVerificationReport>(complete);
    CHECK(complete_report.global_objective_optimality==HybridVerificationStatus::established);
    CHECK(complete_report.complete_family_coverage==HybridVerificationStatus::established);
    REQUIRE(complete_report.branches.size()==2);
    for(const auto& branch:complete_report.branches) {
        CHECK(branch.feasibility==HybridVerificationStatus::established);
        CHECK(branch.objective_optimality==HybridVerificationStatus::established);
        CHECK(branch.continuous_coverage==HybridVerificationStatus::established);
        REQUIRE(branch.exact_verifier_resources.has_value());
        const auto& resources=*branch.exact_verifier_resources;
        CHECK(resources.max_variables==13);
        CHECK(resources.max_rows==4096);
        CHECK(resources.max_generated_rows>0);
        CHECK(resources.max_integer_bits==8192);
        CHECK(resources.max_charged_operations>0);
        CHECK(resources.peak_rows>0);
        CHECK(resources.generated_rows>0);
        CHECK(resources.charged_operations>0);
        CHECK(resources.maximum_integer_bits>0);
        CHECK(resources.maximum_integer_bits<=resources.max_integer_bits);
    }

    // The clipped wide face retains its literal witness but excludes another
    // valid wide-branch optimum with u0=0.5, u1=0.25.
    auto clipped_h=sets::from_handle(optimal_face("oracle-two-stage-wide-clipped",1,true));
    REQUIRE(std::holds_alternative<sets::SetData>(clipped_h));
    const auto clipped_rep=std::get<sets::SetData>(clipped_h).representation();
    REQUIRE(std::holds_alternative<sets::HRepresentation>(clipped_rep));
    CHECK(literal_h_contains(std::get<sets::HRepresentation>(clipped_rep),
        {0,0.125,0.125,0.25,0.25,0,0.125,0.125,0,0.5,0,0.5}));
    CHECK_FALSE(literal_h_contains(std::get<sets::HRepresentation>(clipped_rep),
        {0,0.5,0.25,0.75,0.75,0,0.25,0.25,0,1.25,0,1.25}));
    std::vector<HybridPathOptimalFaceCandidate> incomplete_candidates;
    for(const auto& program:programs)
        incomplete_candidates.push_back(candidate_for(program,
            program.path.edges.front().value=="branch-wide"));
    const auto incomplete=verify_hybrid_portfolio_family(verifier,system,request,programs,
        incomplete_candidates,{2,2},{0,0});
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(incomplete));
    const auto& incomplete_report=std::get<HybridFamilyVerificationReport>(incomplete);
    CHECK(incomplete_report.global_objective_optimality==HybridVerificationStatus::established);
    CHECK(incomplete_report.complete_family_coverage==HybridVerificationStatus::refuted);
    REQUIRE(incomplete_report.branches.size()==2);
    for(const auto& branch:incomplete_report.branches) {
        CHECK(branch.feasibility==HybridVerificationStatus::established);
        CHECK(branch.objective_optimality==HybridVerificationStatus::established);
        CHECK(branch.continuous_coverage==(branch.path.edges.front().value=="branch-wide"
            ?HybridVerificationStatus::refuted:HybridVerificationStatus::established));
    }

    // The second branch's equivalent H-face is padded with redundant zero
    // inequalities to exercise the per-check inclusion budget. The first path
    // remains fully verified; exhaustion on the later path cannot claim full
    // family coverage.
    auto bounded_candidates=complete_candidates;
    auto& bounded_face=bounded_candidates[1].relation;
    const auto bounded_representation=bounded_face.representation();
    REQUIRE(std::holds_alternative<sets::HRepresentation>(bounded_representation));
    const auto& base_face=std::get<sets::HRepresentation>(bounded_representation);
    constexpr std::size_t exact_row_cap=4096;
    const auto inequality_rows=exact_row_cap-2*base_face.equalities.rows();
    REQUIRE(inequality_rows>=base_face.inequalities.rows());
    std::vector<double> bounded_inequalities;
    bounded_inequalities.reserve(inequality_rows*12);
    std::vector<double> bounded_upper_bounds;
    bounded_upper_bounds.reserve(inequality_rows);
    for(std::size_t row=0;row<base_face.inequalities.rows();++row) {
        for(std::size_t column=0;column<12;++column)
            bounded_inequalities.push_back(base_face.inequalities(row,column));
        bounded_upper_bounds.push_back(base_face.upper_bounds[row]);
    }
    bounded_inequalities.resize(inequality_rows*12,0.0);
    bounded_upper_bounds.resize(inequality_rows,1.0);
    std::vector<double> equality_coefficients;
    equality_coefficients.reserve(base_face.equalities.rows()*12);
    for(std::size_t row=0;row<base_face.equalities.rows();++row)
        for(std::size_t column=0;column<12;++column)
            equality_coefficients.push_back(base_face.equalities(row,column));
    std::vector<double> equality_values;
    equality_values.reserve(base_face.equality_values.size());
    for(std::size_t row=0;row<base_face.equality_values.size();++row)
        equality_values.push_back(base_face.equality_values[row]);
    const auto padded_face=h_set("oracle-two-stage-bounded-narrow-face",12,
        Matrix{inequality_rows,12,std::move(bounded_inequalities)},
        std::move(bounded_upper_bounds),
        Matrix{base_face.equalities.rows(),12,std::move(equality_coefficients)},
        std::move(equality_values));
    const auto padded_data=sets::from_handle(padded_face);
    REQUIRE(std::holds_alternative<sets::SetData>(padded_data));
    bounded_candidates[1].relation=std::get<sets::SetData>(padded_data);
    const auto bounded=verify_hybrid_portfolio_family(verifier,system,request,programs,
        bounded_candidates,{2,2},{0,0});
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(bounded));
    const auto& bounded_report=std::get<HybridFamilyVerificationReport>(bounded);
    CHECK(bounded_report.global_objective_optimality==HybridVerificationStatus::established);
    REQUIRE_FALSE(bounded_report.branches[1].diagnostics.empty());
    const auto resource_diagnostic=std::find_if(
        bounded_report.branches[1].diagnostics.begin(),
        bounded_report.branches[1].diagnostics.end(),[](const auto& diagnostic) {
            return diagnostic.code==DiagnosticCode::unsupported &&
                diagnostic.field=="hybrid.verification.exact_linear_h_face_mismatch";
        });
    REQUIRE(resource_diagnostic!=bounded_report.branches[1].diagnostics.end());
    CHECK(resource_diagnostic->explanation.find(
        "Fourier-Motzkin resource limit would be exceeded")!=std::string::npos);
    REQUIRE_FALSE(bounded_report.branches[1].diagnostics.empty());
    CHECK(bounded_report.complete_family_coverage==HybridVerificationStatus::unsupported);
    REQUIRE(bounded_report.branches.size()==2);
    CHECK(bounded_report.branches[0].continuous_coverage==HybridVerificationStatus::established);
    CHECK(bounded_report.branches[1].continuous_coverage==HybridVerificationStatus::unsupported);
}

TEST_CASE("exact linear H verifier matches independent 3D control-box oracle") {
    using namespace model;
    const auto control_box=h_set("oracle-control-box-3d",3,
        Matrix{6,3,{-1,0,0,1,0,0,0,-1,0,0,1,0,0,0,-1,0,0,1}},
        Vector{0,1,0,1,0,1},Matrix{0,3,{}},Vector{});
    const auto identity_reset=h_set("oracle-3d-identity-reset",6,
        Matrix{0,6,{}},Vector{},
        Matrix{3,6,{1,0,0,-1,0,0,0,1,0,0,-1,0,0,0,1,0,0,-1}},
        Vector{0,0,0});
    HybridMode source{{"oracle-source-3d"},3,3,{"x0","x1","x2"},
        {"u0","u1","u2"}};
    source.flow=LinearStage{Matrix{3,3,{0,0,0,0,0,0,0,0,0}},
        Matrix{3,3,{1,0,0,0,1,0,0,0,1}},Matrix{3,0,{}},Vector{0,0,0}};
    source.control_sets={control_box};
    source.invariants={UniversalSet{3},UniversalSet{3}};
    HybridMode terminal{{"oracle-terminal-3d"},3,0,{"y0","y1","y2"},{}};
    terminal.flow=LinearStage{Matrix{3,3,{1,0,0,0,1,0,0,0,1}},
        Matrix{3,0,{}},Matrix{3,0,{}},Vector{0,0,0}};
    terminal.control_sets={UniversalSet{0}};
    terminal.invariants={UniversalSet{3},UniversalSet{3}};
    HybridSystem system{1,{source,terminal},
        {{{"oracle-edge-3d"},source.id,terminal.id,{UniversalSet{3}},
            {identity_reset}}}};
    HybridRequest request{{source.id,{0,0,0}},{terminal.id},
        {{terminal.id,LinearTerminal{{1,0,0},0},"first terminal coordinate","units"}}};

    // Independently traverse the raw graph and specify all twelve joint
    // coordinates (x0[0..2], u0[0..2], xpre[0..2], xpost[0..2]).
    std::vector<HybridPath> oracle_paths;
    for(const auto& edge:system.edges)
        if(edge.source==request.initial.mode && edge.target==terminal.id)
            oracle_paths.push_back({{request.initial.mode,edge.target},{edge.id}});
    const std::vector<HybridPath> expected_paths{
        {{source.id,terminal.id},{{"oracle-edge-3d"}}}};
    REQUIRE(oracle_paths==expected_paths);
    const auto built=build_hybrid_portfolio_programs(system,request,{"literal-3d-oracle"},
        {1,4},{48,256,8192});
    REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(built));
    const auto& programs=std::get<std::vector<HybridPathProgram>>(built);
    REQUIRE(programs.size()==1);
    CHECK(programs[0].path==oracle_paths[0]);
    const auto representation=programs[0].joint_relation.representation();
    REQUIRE(std::holds_alternative<sets::HRepresentation>(representation));
    const auto& h=std::get<sets::HRepresentation>(representation);

    const auto matches_literal_rows=[](const numeric::MatrixView& actual,
        const numeric::VectorView& rhs,const std::vector<double>& expected,
        const std::vector<double>& expected_rhs,std::size_t width) {
        REQUIRE(actual.rows()==expected_rhs.size());
        REQUIRE(rhs.size()==expected_rhs.size());
        REQUIRE(actual.cols()==width);
        std::vector<bool> matched(expected_rhs.size(),false);
        for(std::size_t row=0;row<actual.rows();++row) {
            bool found=false;
            for(std::size_t candidate=0;candidate<expected_rhs.size()&&!found;++candidate) {
                if(matched[candidate]||rhs[row]!=expected_rhs[candidate])continue;
                bool equal=true;
                for(std::size_t column=0;column<width;++column)
                    equal=equal&&actual(row,column)==expected[candidate*width+column];
                if(equal){matched[candidate]=true;found=true;}
            }
            CHECK(found);
        }
    };
    matches_literal_rows(h.inequalities,h.upper_bounds,
        {0,0,0,-1,0,0,0,0,0,0,0,0,
         0,0,0,1,0,0,0,0,0,0,0,0,
         0,0,0,0,-1,0,0,0,0,0,0,0,
         0,0,0,0,1,0,0,0,0,0,0,0,
         0,0,0,0,0,-1,0,0,0,0,0,0,
         0,0,0,0,0,1,0,0,0,0,0,0},
        {0,1,0,1,0,1},12);
    matches_literal_rows(h.equalities,h.equality_values,
        {1,0,0,0,0,0,0,0,0,0,0,0,
         0,1,0,0,0,0,0,0,0,0,0,0,
         0,0,1,0,0,0,0,0,0,0,0,0,
         0,0,0,-1,0,0,1,0,0,0,0,0,
         0,0,0,0,-1,0,0,1,0,0,0,0,
         0,0,0,0,0,-1,0,0,1,0,0,0,
         0,0,0,0,0,0,1,0,0,-1,0,0,
         0,0,0,0,0,0,0,1,0,0,-1,0,
         0,0,0,0,0,0,0,0,1,0,0,-1},
        {0,0,0,0,0,0,0,0,0},12);
    CHECK(std::get<LinearTerminal>(programs[0].lifted_objective).coefficients==
        Vector{0,0,0,0,0,0,0,0,0,1,0,0});

    // The literal objective is u0 in [0,1]. Its zero face fixes u0=0 and
    // leaves the other two controls independently free in [0,1].
    const auto face=sets::from_handle(h_set("oracle-3d-optimal-face",12,
        Matrix{6,12,{0,0,0,-1,0,0,0,0,0,0,0,0,
                      0,0,0,1,0,0,0,0,0,0,0,0,
                      0,0,0,0,-1,0,0,0,0,0,0,0,
                      0,0,0,0,1,0,0,0,0,0,0,0,
                      0,0,0,0,0,-1,0,0,0,0,0,0,
                      0,0,0,0,0,1,0,0,0,0,0,0}},
        Vector{0,0,0,1,0,1},
        Matrix{10,12,{1,0,0,0,0,0,0,0,0,0,0,0,
                       0,1,0,0,0,0,0,0,0,0,0,0,
                       0,0,1,0,0,0,0,0,0,0,0,0,
                       0,0,0,-1,0,0,1,0,0,0,0,0,
                       0,0,0,0,-1,0,0,1,0,0,0,0,
                       0,0,0,0,0,-1,0,0,1,0,0,0,
                       0,0,0,0,0,0,1,0,0,-1,0,0,
                       0,0,0,0,0,0,0,1,0,0,-1,0,
                       0,0,0,0,0,0,0,0,1,0,0,-1,
                       0,0,0,1,0,0,0,0,0,0,0,0}},
        Vector{0,0,0,0,0,0,0,0,0,0}));
    REQUIRE(std::holds_alternative<sets::SetData>(face));
    auto candidate=exact_candidate(programs[0],{0,0,0,0,0.5,0.5,0,0.5,0.5,0,0.5,0.5});
    candidate.relation=std::get<sets::SetData>(face);
    REQUIRE(candidate.solver_result.primal.has_value());
    const auto& point=*candidate.solver_result.primal;
    const auto& objective=std::get<LinearTerminal>(programs[0].lifted_objective);
    double literal_cost=objective.offset;
    for(std::size_t i=0;i<point.size();++i)
        literal_cost+=objective.coefficients[i]*point[i];
    CHECK(literal_cost==0.0);

    ExactLinearHHybridFamilyVerifier verifier;
    const std::array<HybridPathOptimalFaceCandidate,1> candidates{std::move(candidate)};
    const auto verified=verify_hybrid_portfolio_family(verifier,system,request,
        programs,candidates,{1,4},{0,0});
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(verified));
    const auto& report=std::get<HybridFamilyVerificationReport>(verified);
    REQUIRE(report.branches.size()==1);
    std::string branch_diagnostics;
    for(const auto& diagnostic:report.branches[0].diagnostics)
        branch_diagnostics+=diagnostic.field+": "+diagnostic.explanation+"; ";
    CHECK(report.global_objective_optimality==HybridVerificationStatus::established);
    CHECK_MESSAGE(report.complete_family_coverage==HybridVerificationStatus::established,
        "Diagnostics: "<<branch_diagnostics);
    CHECK(report.branches[0].objective_optimality==HybridVerificationStatus::established);
    CHECK_MESSAGE(report.branches[0].continuous_coverage==HybridVerificationStatus::established,
        "Diagnostics: "<<branch_diagnostics);
}

TEST_CASE("hybrid exact raw path relation matches the joint H composer") {
    using namespace detail::hybrid_exact;
    const auto system=example_system();
    const auto request=example_request();
    const auto path=example_path();
    const model::HybridRelationLimits relation_limits{32,4096,100000};
    const auto raw=reconstruct_path_relation(system,request,path,relation_limits);
    REQUIRE(raw.state==RawRelationState::built);

    const auto composed=model::compose_hybrid_path_relation(
        system,request,path,relation_limits);
    REQUIRE(std::holds_alternative<sets::SetData>(composed));
    const auto representation=std::get<sets::SetData>(composed).representation();
    REQUIRE(std::holds_alternative<sets::HRepresentation>(representation));
    const auto& h=std::get<sets::HRepresentation>(representation);
    std::vector<Row> composed_rows;
    for(std::size_t row=0;row<h.inequalities.rows();++row) {
        Vector coefficients(h.inequalities.cols());
        for(std::size_t column=0;column<coefficients.size();++column)
            coefficients[column]=h.inequalities(row,column);
        REQUIRE(append_inequality(coefficients,h.upper_bounds[row],false,
                                  default_max_integer_bits,composed_rows));
    }
    for(std::size_t row=0;row<h.equalities.rows();++row) {
        Vector coefficients(h.equalities.cols());
        for(std::size_t column=0;column<coefficients.size();++column)
            coefficients[column]=h.equalities(row,column);
        REQUIRE(append_equality(coefficients,h.equality_values[row],
                                default_max_integer_bits,composed_rows));
    }
    REQUIRE(h.inequalities.cols()==raw.variables);
    CHECK(included_in(raw.rows,composed_rows,raw.variables).state==
          InclusionState::included);
    CHECK(included_in(composed_rows,raw.rows,raw.variables).state==
          InclusionState::included);

    auto mutated_system=system;
    std::get<LinearStage>(mutated_system.modes[0].flow).A.values[0]=2.0;
    const auto mutated=reconstruct_path_relation(mutated_system,request,path,
                                                 relation_limits);
    REQUIRE(mutated.state==RawRelationState::built);
    CHECK(included_in(mutated.rows,composed_rows,mutated.variables).state==
          InclusionState::not_included);

    auto small_limits=relation_limits;
    small_limits.max_rows=1;
    CHECK(reconstruct_path_relation(system,request,path,small_limits).state==
          RawRelationState::unsupported);
    std::stop_source cancelled;
    cancelled.request_stop();
    CHECK(reconstruct_path_relation(system,request,path,relation_limits,{},
                                    cancelled.get_token()).state==
          RawRelationState::cancelled);
}

TEST_CASE("hybrid exact raw relation preserves H sets and heterogeneous reset timing") {
    using namespace detail::hybrid_exact;
    const auto source_interval=h_set("raw-source-interval",1,
        Matrix{2,1,{-1,1}},Vector{0,3},Matrix{0,1,{}},Vector{});
    const auto pre_invariant=h_set("raw-pre-invariant",1,
        Matrix{2,1,{-1,1}},Vector{0,2},Matrix{0,1,{}},Vector{});
    const auto transition_guard=h_set("raw-transition-guard",1,
        Matrix{2,1,{-1,1}},Vector{0,1.25},Matrix{0,1,{}},Vector{});
    const auto target_interval=h_set("raw-target-interval",1,
        Matrix{2,1,{-1,1}},Vector{0,4},Matrix{0,1,{}},Vector{});
    const auto box2=h_set("raw-box2",2,
        Matrix{4,2,{-1,0,0,-1,1,0,0,1}},Vector{0,0,3,3},
        Matrix{0,2,{}},Vector{});
    const auto reset_source=h_set("raw-reset-source",3,
        Matrix{1,3,{0,1,0}},Vector{1},
        Matrix{2,3,{1,-1,0,0,0,1}},Vector{0,0});
    const auto reset_target=h_set("raw-reset-target",3,
        Matrix{1,3,{0,1,0}},Vector{2},
        Matrix{1,3,{1,1,-1}},Vector{0});

    const LinearStage source_flow{Matrix{1,1,{1}},Matrix{1,1,{1}},
        Matrix{1,0,{}},Vector{0}};
    const LinearStage middle_flow{Matrix{2,2,{1,0,0,1}},
        Matrix{2,1,{1,0}},Matrix{2,0,{}},Vector{0,0}};
    auto source=model::HybridMode{{"raw-source"},1,1,{"x"},{"u"}};
    source.flow=std::vector<LinearStage>{source_flow,source_flow};
    source.control_sets={source_interval,source_interval};
    source.invariants={source_interval,pre_invariant,source_interval};
    auto middle=model::HybridMode{{"raw-middle"},2,1,{"y","z"},{"v"}};
    middle.flow=std::vector<LinearStage>{middle_flow,middle_flow};
    middle.control_sets={source_interval,source_interval};
    middle.invariants={box2,box2,box2};
    auto target=model::HybridMode{{"raw-target"},1,0,{"w"},{}};
    target.flow=std::vector<LinearStage>{
        LinearStage{Matrix{1,1,{1}},Matrix{1,0,{}},Matrix{1,0,{}},Vector{0}},
        LinearStage{Matrix{1,1,{1}},Matrix{1,0,{}},Matrix{1,0,{}},Vector{0}}};
    target.control_sets={UniversalSet{0},UniversalSet{0}};
    target.invariants={target_interval,target_interval,target_interval};
    model::HybridSystem system{2,{source,middle,target},
        {{{"raw-edge-a"},{"raw-source"},{"raw-middle"},
            {transition_guard,transition_guard},{reset_source,reset_source}},
         {{"raw-edge-b"},{"raw-middle"},{"raw-target"},
            {box2,box2},{reset_target,reset_target}}}};
    model::HybridRequest request{{{"raw-source"},{1}},{{"raw-target"}},
        {{{"raw-target"},LinearTerminal{{1},0},"cost","u"}}};
    const model::HybridPath path{{{"raw-source"},{"raw-middle"},{"raw-target"}},
        {{"raw-edge-a"},{"raw-edge-b"}}};
    const model::HybridRelationLimits limits{32,4096,100000};

    const auto raw=reconstruct_path_relation(system,request,path,limits);
    REQUIRE(raw.state==RawRelationState::built);
    const auto tuple_state=[&](const Vector& tuple) {
        auto rows=raw.rows;
        REQUIRE(tuple.size()==raw.variables);
        for(std::size_t column=0;column<tuple.size();++column) {
            Vector coefficient(tuple.size(),0.0);
            coefficient[column]=1.0;
            REQUIRE(append_equality(coefficient,tuple[column],
                                    default_max_integer_bits,rows));
        }
        return feasible(std::move(rows),raw.variables).state;
    };
    CHECK(tuple_state({1,0,1,1,0,0,1,0,1})==FeasibilityState::feasible);
    CHECK(tuple_state({1,0.5,1.5,1.5,0,0,1.5,0,1.5})==
          FeasibilityState::infeasible);
    const auto composed=model::compose_hybrid_path_relation(system,request,path,limits);
    REQUIRE(std::holds_alternative<sets::SetData>(composed));
    const auto representation=std::get<sets::SetData>(composed).representation();
    REQUIRE(std::holds_alternative<sets::HRepresentation>(representation));
    const auto& h=std::get<sets::HRepresentation>(representation);
    std::vector<Row> composed_rows;
    for(std::size_t row=0;row<h.inequalities.rows();++row) {
        Vector coefficients(h.inequalities.cols());
        for(std::size_t column=0;column<coefficients.size();++column)
            coefficients[column]=h.inequalities(row,column);
        REQUIRE(append_inequality(coefficients,h.upper_bounds[row],false,
                                  default_max_integer_bits,composed_rows));
    }
    for(std::size_t row=0;row<h.equalities.rows();++row) {
        Vector coefficients(h.equalities.cols());
        for(std::size_t column=0;column<coefficients.size();++column)
            coefficients[column]=h.equalities(row,column);
        REQUIRE(append_equality(coefficients,h.equality_values[row],
                                default_max_integer_bits,composed_rows));
    }
    REQUIRE(h.inequalities.cols()==raw.variables);
    CHECK(included_in(raw.rows,composed_rows,raw.variables).state==
          InclusionState::included);
    CHECK(included_in(composed_rows,raw.rows,raw.variables).state==
          InclusionState::included);
}

TEST_CASE("hybrid exact raw relation handles singleton and empty representations") {
    using namespace detail::hybrid_exact;
    const model::HybridRelationLimits limits{32,4096,100000};
    auto [singleton_system,singleton_request]=exact_singleton_portfolio();
    const model::HybridPath singleton_path{{{"source"},{"target"}},{{"tie-a"}}};
    const auto singleton_raw=reconstruct_path_relation(
        singleton_system,singleton_request,singleton_path,limits);
    REQUIRE(singleton_raw.state==RawRelationState::built);
    const auto singleton_composed=model::compose_hybrid_path_relation(
        singleton_system,singleton_request,singleton_path,limits);
    REQUIRE(std::holds_alternative<sets::SetData>(singleton_composed));
    const auto singleton_rep=std::get<sets::SetData>(singleton_composed).representation();
    REQUIRE(std::holds_alternative<sets::HRepresentation>(singleton_rep));
    const auto& singleton_h=std::get<sets::HRepresentation>(singleton_rep);
    std::vector<Row> singleton_composed_rows;
    for(std::size_t row=0;row<singleton_h.inequalities.rows();++row) {
        Vector coefficients(singleton_h.inequalities.cols());
        for(std::size_t column=0;column<coefficients.size();++column)
            coefficients[column]=singleton_h.inequalities(row,column);
        REQUIRE(append_inequality(coefficients,singleton_h.upper_bounds[row],false,
                                  default_max_integer_bits,singleton_composed_rows));
    }
    for(std::size_t row=0;row<singleton_h.equalities.rows();++row) {
        Vector coefficients(singleton_h.equalities.cols());
        for(std::size_t column=0;column<coefficients.size();++column)
            coefficients[column]=singleton_h.equalities(row,column);
        REQUIRE(append_equality(coefficients,singleton_h.equality_values[row],
                                default_max_integer_bits,singleton_composed_rows));
    }
    CHECK(included_in(singleton_raw.rows,singleton_composed_rows,
                      singleton_raw.variables).state==InclusionState::included);
    CHECK(included_in(singleton_composed_rows,singleton_raw.rows,
                      singleton_raw.variables).state==InclusionState::included);

    auto [empty_system,empty_request]=std::make_pair(example_system(),example_request());
    empty_system.edges[0].reset_relations[0]=empty_handle("raw-empty-reset",3);
    const auto empty_path=example_path();
    const auto empty_raw=reconstruct_path_relation(empty_system,empty_request,
                                                    empty_path,limits);
    REQUIRE(empty_raw.state==RawRelationState::built);
    const auto empty_composed=model::compose_hybrid_path_relation(
        empty_system,empty_request,empty_path,limits);
    REQUIRE(std::holds_alternative<sets::SetData>(empty_composed));
    const auto empty_rep=std::get<sets::SetData>(empty_composed).representation();
    REQUIRE(std::holds_alternative<sets::HRepresentation>(empty_rep));
    const auto& h=std::get<sets::HRepresentation>(empty_rep);
    std::vector<Row> empty_composed_rows;
    for(std::size_t row=0;row<h.inequalities.rows();++row) {
        Vector coefficients(h.inequalities.cols());
        for(std::size_t column=0;column<coefficients.size();++column)
            coefficients[column]=h.inequalities(row,column);
        REQUIRE(append_inequality(coefficients,h.upper_bounds[row],false,
                                  default_max_integer_bits,empty_composed_rows));
    }
    for(std::size_t row=0;row<h.equalities.rows();++row) {
        Vector coefficients(h.equalities.cols());
        for(std::size_t column=0;column<coefficients.size();++column)
            coefficients[column]=h.equalities(row,column);
        REQUIRE(append_equality(coefficients,h.equality_values[row],
                                default_max_integer_bits,empty_composed_rows));
    }
    CHECK(included_in(empty_raw.rows,empty_composed_rows,empty_raw.variables).state==
          InclusionState::included);
    CHECK(included_in(empty_composed_rows,empty_raw.rows,empty_raw.variables).state==
          InclusionState::included);

    Limits exact_limits;
    exact_limits.max_stages=0;
    CHECK(reconstruct_path_relation(singleton_system,singleton_request,
                                    singleton_path,limits,exact_limits).state==
          RawRelationState::unsupported);
}

TEST_CASE("hybrid exact polytope feasibility handles inconsistent equalities and lower dimension") {
    using namespace detail::hybrid_exact;
    const std::array<double,1> x{1};
    std::vector<Row> inconsistent;
    REQUIRE(append_equality(x,0,default_max_integer_bits,inconsistent));
    REQUIRE(append_equality(x,1,default_max_integer_bits,inconsistent));
    CHECK(feasible(std::move(inconsistent),1).state==FeasibilityState::infeasible);

    const std::array<double,2> x_only{1,0}, y_upper{0,1}, y_lower{0,-1};
    std::vector<Row> lower_dimensional;
    REQUIRE(append_equality(x_only,0,default_max_integer_bits,lower_dimensional));
    REQUIRE(append_inequality(y_upper,1,false,default_max_integer_bits,lower_dimensional));
    REQUIRE(append_inequality(y_lower,0,false,default_max_integer_bits,lower_dimensional));
    CHECK(feasible(std::move(lower_dimensional),2).state==FeasibilityState::feasible);
}

TEST_CASE("hybrid exact polytope feasibility stops at resource and cancellation limits") {
    using namespace detail::hybrid_exact;
    const std::array<double,1> x{1}, negative_x{-1};
    std::vector<Row> rows;
    REQUIRE(append_inequality(x,1,false,default_max_integer_bits,rows));
    REQUIRE(append_inequality(negative_x,2,false,default_max_integer_bits,rows));
    Limits limits;
    limits.max_rows=1;
    CHECK(feasible(rows,1,limits).state==FeasibilityState::unsupported);
    limits.max_rows=default_max_rows;
    limits.max_operations=1;
    CHECK(feasible(rows,1,limits).state==FeasibilityState::unsupported);

    std::stop_source cancelled;
    cancelled.request_stop();
    CHECK(feasible({},0,{},cancelled.get_token()).state==FeasibilityState::cancelled);
}

class RejectingTrajectoryAdapter final : public HybridDirectTrajectoryAdapter {
public:
    mutable int calls{};
    mutable int capability_calls{};
    HybridDirectTrajectoryCapabilities capabilities() const noexcept override {
        ++capability_calls;
        return {true,true,true,Assurance::numerical};
    }
    HybridPathProgramResult build_path(const model::HybridSystem&,
        const model::HybridRequest&, const model::HybridPath&, ProblemId,
        model::HybridRelationLimits, optimization::ObjectivePolicy,
        std::stop_token) const override {
        ++calls;
        return Diagnostics{{DiagnosticCode::unsupported,"fixture.hybrid_adapter","fixture rejection"}};
    }
};

class LinearOnlyRejectingTrajectoryAdapter final : public HybridDirectTrajectoryAdapter {
public:
    mutable int calls{};
    mutable int capability_calls{};
    HybridDirectTrajectoryCapabilities capabilities() const noexcept override {
        ++capability_calls;
        return {true,true,false,Assurance::numerical};
    }
    HybridPathProgramResult build_path(const model::HybridSystem&,
        const model::HybridRequest&, const model::HybridPath&, ProblemId,
        model::HybridRelationLimits, optimization::ObjectivePolicy,
        std::stop_token) const override {
        ++calls;
        return Diagnostics{{DiagnosticCode::unsupported,"fixture.hybrid_adapter","fixture rejection"}};
    }
};

class RejectingTrajectoryPreflightAdapter final : public HybridDirectTrajectoryAdapter {
public:
    int corruption{3};
    mutable int preflight_calls{};
    mutable std::size_t preflight_path_count{};
    mutable int capability_calls{};
    mutable int build_calls{};
    HybridDirectTrajectoryPreflightResult preflight(const model::HybridSystem&,
        const model::HybridRequest&,std::span<const model::HybridPath> paths,
        model::HybridRelationLimits limits,std::span<const model::HybridPlannedOperation>,
        optimization::ObjectivePolicy,
        std::stop_token) const override {
        ++preflight_calls;
        preflight_path_count=paths.size();
        auto path=paths.back();
        auto reported_limits=limits;
        if(corruption==0) path.edges.front().value+="-wrong";
        if(corruption==1) ++reported_limits.max_rows;
        Diagnostic diagnostic{DiagnosticCode::unsupported,"fixture.trajectory.preflight",
            "fixture rejects a later path operation"};
        if(corruption==2) diagnostic={DiagnosticCode::unsupported,"",""};
        return HybridDirectTrajectoryPreflightFailure{std::move(path),reported_limits,{},
            std::move(diagnostic)};
    }
    HybridDirectTrajectoryCapabilities capabilities() const noexcept override {
        ++capability_calls;
        return {true,true,true,Assurance::numerical};
    }
    HybridPathProgramResult build_path(const model::HybridSystem&,
        const model::HybridRequest&,const model::HybridPath&,ProblemId,
        model::HybridRelationLimits,optimization::ObjectivePolicy,
        std::stop_token) const override {
        ++build_calls;
        return Diagnostics{{DiagnosticCode::unsupported,"fixture.trajectory","unexpected build"}};
    }
};

class RecordingDefaultPreflightTrajectoryAdapter final : public HybridDirectTrajectoryAdapter {
public:
    mutable int capability_calls{};
    mutable int build_calls{};
    HybridDirectTrajectoryCapabilities capabilities() const noexcept override {
        ++capability_calls;
        return {true,true,true,Assurance::numerical};
    }
    HybridPathProgramResult build_path(const model::HybridSystem&,
        const model::HybridRequest&,const model::HybridPath&,ProblemId,
        model::HybridRelationLimits,optimization::ObjectivePolicy,
        std::stop_token) const override {
        ++build_calls;
        return Diagnostics{{DiagnosticCode::unsupported,"fixture.default_preflight",
            "unexpected build after default operation preflight"}};
    }
};

class CancellingTrajectoryPreflightAdapter final : public HybridDirectTrajectoryAdapter {
public:
    explicit CancellingTrajectoryPreflightAdapter(std::stop_source& cancellation)
        : cancellation_(&cancellation) {}
    mutable int capability_calls{};
    mutable int build_calls{};
    HybridDirectTrajectoryPreflightResult preflight(const model::HybridSystem&,
        const model::HybridRequest&,std::span<const model::HybridPath>,
        model::HybridRelationLimits,std::span<const model::HybridPlannedOperation>,
        optimization::ObjectivePolicy,
        std::stop_token) const override {
        cancellation_->request_stop();
        return OperationStopped{StopReason::cancelled,"fixture requested cancellation"};
    }
    HybridDirectTrajectoryCapabilities capabilities() const noexcept override {
        ++capability_calls;
        return {true,true,true,Assurance::numerical};
    }
    HybridPathProgramResult build_path(const model::HybridSystem&,
        const model::HybridRequest&,const model::HybridPath&,ProblemId,
        model::HybridRelationLimits,optimization::ObjectivePolicy,
        std::stop_token) const override {
        ++build_calls;
        return Diagnostics{{DiagnosticCode::unsupported,"fixture.trajectory","unexpected build"}};
    }
private:
    std::stop_source* cancellation_;
};

class AdmittingTrajectoryPreflightAdapter final : public HybridDirectTrajectoryAdapter {
public:
    mutable int preflight_calls{};
    mutable int capability_calls{};
    mutable int build_calls{};
    HybridDirectTrajectoryPreflightResult preflight(const model::HybridSystem&,
        const model::HybridRequest&,std::span<const model::HybridPath> paths,
        model::HybridRelationLimits limits,std::span<const model::HybridPlannedOperation> operations,
        optimization::ObjectivePolicy,
        std::stop_token) const override {
        ++preflight_calls;
        return HybridDirectTrajectoryPreflightSuccess{
            std::vector<model::HybridPath>(paths.begin(),paths.end()),limits,
            std::vector<model::HybridPlannedOperation>(operations.begin(),operations.end())};
    }
    HybridDirectTrajectoryCapabilities capabilities() const noexcept override {
        ++capability_calls;
        return {true,true,true,Assurance::numerical};
    }
    HybridPathProgramResult build_path(const model::HybridSystem&,
        const model::HybridRequest&,const model::HybridPath&,ProblemId,
        model::HybridRelationLimits,optimization::ObjectivePolicy,
        std::stop_token) const override {
        ++build_calls;
        return Diagnostics{{DiagnosticCode::unsupported,"fixture.alternate_representation",
            "fixture stopped after custom operation admission"}};
    }
};

class PolicyAwareTrajectoryAdapter final : public HybridDirectTrajectoryAdapter {
public:
    explicit PolicyAwareTrajectoryAdapter(optimization::ObjectivePolicy accepted)
        : accepted_(accepted) {}
    mutable int preflight_calls{};
    mutable int capability_calls{};
    mutable int build_calls{};
    mutable std::optional<optimization::ObjectivePolicy> observed_policy;
    HybridDirectTrajectoryPreflightResult preflight(const model::HybridSystem&,
        const model::HybridRequest&,std::span<const model::HybridPath> paths,
        model::HybridRelationLimits limits,std::span<const model::HybridPlannedOperation> operations,
        optimization::ObjectivePolicy policy,
        std::stop_token) const override {
        ++preflight_calls;
        observed_policy=policy;
        if(policy.assurance!=accepted_.assurance||
           policy.numerical.absolute_tolerance!=accepted_.numerical.absolute_tolerance||
           policy.numerical.relative_tolerance!=accepted_.numerical.relative_tolerance)
            return HybridDirectTrajectoryPreflightFailure{paths.front(),limits,{},
                {DiagnosticCode::unsupported,"fixture.trajectory.objective_policy",
                 "Adapter does not admit this numerical tolerance policy"}};
        return HybridDirectTrajectoryPreflightSuccess{
            std::vector<model::HybridPath>(paths.begin(),paths.end()),limits,
            std::vector<model::HybridPlannedOperation>(operations.begin(),operations.end())};
    }
    HybridDirectTrajectoryCapabilities capabilities() const noexcept override {
        ++capability_calls;
        return {true,true,true,Assurance::numerical};
    }
    HybridPathProgramResult build_path(const model::HybridSystem&,
        const model::HybridRequest&,const model::HybridPath&,ProblemId,
        model::HybridRelationLimits,optimization::ObjectivePolicy,
        std::stop_token) const override {
        ++build_calls;
        return Diagnostics{{DiagnosticCode::unsupported,"fixture.trajectory.policy_adapter",
            "fixture stopped after policy admission"}};
    }
private:
    optimization::ObjectivePolicy accepted_;
};

class InventoryOnlyTrajectoryPreflightAdapter final : public HybridDirectTrajectoryAdapter {
public:
    mutable int preflight_calls{};
    mutable int capability_calls{};
    mutable int build_calls{};
    HybridDirectTrajectoryPreflightResult preflight(const model::HybridSystem&,
        const model::HybridRequest&,std::span<const model::HybridPath> paths,
        model::HybridRelationLimits limits,std::span<const model::HybridPlannedOperation> operations,
        optimization::ObjectivePolicy,
        std::stop_token) const override {
        ++preflight_calls;
        if(paths.size()==3) return HybridDirectTrajectoryPreflightSuccess{
            std::vector<model::HybridPath>(paths.begin(),paths.end()),limits,
            std::vector<model::HybridPlannedOperation>(operations.begin(),operations.end())};
        const auto path=paths.empty()?model::HybridPath{}:paths.front();
        return HybridDirectTrajectoryPreflightFailure{path,limits,{},Diagnostic{
            DiagnosticCode::unsupported,"fixture.inventory_only",
            "preflight requires the complete path inventory"}};
    }
    HybridDirectTrajectoryCapabilities capabilities() const noexcept override {
        ++capability_calls;
        return {true,true,true,Assurance::numerical};
    }
    HybridPathProgramResult build_path(const model::HybridSystem&,
        const model::HybridRequest&,const model::HybridPath&,ProblemId,
        model::HybridRelationLimits,optimization::ObjectivePolicy,
        std::stop_token) const override {
        ++build_calls;
        return Diagnostics{{DiagnosticCode::unsupported,"fixture.inventory_build",
            "fixture stopped after full inventory admission"}};
    }
};

class PartialReceiptTrajectoryPreflightAdapter final : public HybridDirectTrajectoryAdapter {
public:
    explicit PartialReceiptTrajectoryPreflightAdapter(int corruption = 0)
        : corruption_(corruption) {}
    mutable int capability_calls{};
    mutable int build_calls{};
    HybridDirectTrajectoryPreflightResult preflight(const model::HybridSystem&,
        const model::HybridRequest&,std::span<const model::HybridPath> paths,
        model::HybridRelationLimits limits,std::span<const model::HybridPlannedOperation> operations,
        optimization::ObjectivePolicy,
        std::stop_token) const override {
        std::vector<model::HybridPath> admitted;
        if(corruption_==0) {
            if(!paths.empty()) admitted.push_back(paths.front());
        } else admitted.assign(paths.begin(),paths.end());
        std::vector<model::HybridPlannedOperation> receipt(operations.begin(),operations.end());
        if(corruption_==1&&!receipt.empty()) receipt.resize(1);
        if(corruption_==2&&receipt.size()>1) std::swap(receipt[0],receipt[1]);
        if(corruption_==3&&!receipt.empty()) receipt.push_back(receipt.front());
        return HybridDirectTrajectoryPreflightSuccess{std::move(admitted),limits,std::move(receipt)};
    }
    HybridDirectTrajectoryCapabilities capabilities() const noexcept override {
        ++capability_calls;
        return {true,true,true,Assurance::numerical};
    }
    HybridPathProgramResult build_path(const model::HybridSystem&,
        const model::HybridRequest&,const model::HybridPath&,ProblemId,
        model::HybridRelationLimits,optimization::ObjectivePolicy,
        std::stop_token) const override {
        ++build_calls;
        return Diagnostics{{DiagnosticCode::unsupported,"fixture.partial_receipt",
            "unexpected build after partial admission receipt"}};
    }
private:
    int corruption_;
};

class CancellingCapabilityTrajectoryAdapter final : public HybridDirectTrajectoryAdapter {
public:
    explicit CancellingCapabilityTrajectoryAdapter(std::stop_source& cancellation)
        : cancellation_(&cancellation) {}
    mutable int calls{};
    HybridDirectTrajectoryCapabilities capabilities() const noexcept override {
        cancellation_->request_stop();
        return {true,true,true,Assurance::numerical};
    }
    HybridPathProgramResult build_path(const model::HybridSystem&,
        const model::HybridRequest&, const model::HybridPath&, ProblemId,
        model::HybridRelationLimits, optimization::ObjectivePolicy,
        std::stop_token) const override {
        ++calls;
        return Diagnostics{{DiagnosticCode::unsupported,"fixture.hybrid_adapter","fixture rejection"}};
    }
private:
    std::stop_source* cancellation_;
};

class MismatchingTrajectoryAdapter final : public HybridDirectTrajectoryAdapter {
public:
    bool append_redundant_row{};
    HybridDirectTrajectoryCapabilities capabilities() const noexcept override { return {true,true,true,Assurance::numerical}; }
    HybridPathProgramResult build_path(const model::HybridSystem& system,
        const model::HybridRequest& request, const model::HybridPath& path, ProblemId problem,
        model::HybridRelationLimits limits, optimization::ObjectivePolicy policy,
        std::stop_token cancellation) const override {
        JointHDirectTrajectoryAdapter delegate;
        auto built=delegate.build_path(system,request,path,std::move(problem),limits,policy,cancellation);
        if(auto* program=std::get_if<HybridPathProgram>(&built)) {
            if(append_redundant_row)
                program->joint_relation=append_redundant_zero_inequality(
                    "fixture.trajectory-extra-row",program->joint_relation);
            else
                program->path.edges.front().value="wrong-edge";
        }
        return built;
    }
};

class RejectingReachabilityAdapter final : public HybridReachabilityAdapter {
public:
    mutable int calls{};
    mutable int capability_calls{};
    HybridReachabilityCapabilities capabilities() const noexcept override {
        ++capability_calls;
        return {true,Assurance::numerical};
    }
    HybridReachabilityPreflightResult preflight(const model::HybridSystem& system,
        const model::HybridRequest& request,std::span<const model::HybridPath> paths,
        model::HybridRelationLimits limits,std::span<const model::HybridPlannedOperation> plan,
        std::stop_token cancellation) const override {
        const auto result=model::preflight_hybrid_path_relations(system,request,paths,limits,cancellation);
        if(const auto* failure=std::get_if<model::HybridPathCompositionFailureReport>(&result)) return *failure;
        if(const auto* diagnostics=std::get_if<Diagnostics>(&result)) return *diagnostics;
        if(const auto* stopped=std::get_if<OperationStopped>(&result)) return *stopped;
        return HybridOperationAdmissionSuccess{
            std::vector<model::HybridPlannedOperation>(plan.begin(),plan.end())};
    }
    HybridPathReachabilityResult compose_path(const model::HybridSystem&,
        const model::HybridRequest&,const model::HybridPath& path,
        model::HybridRelationLimits limits,std::stop_token) const override {
        ++calls;
        return model::HybridPathCompositionFailureReport{path,limits,{},
            Diagnostic{DiagnosticCode::unsupported,"fixture.reachability","fixture rejection"}};
    }
};

class DefaultPreflightReachabilityAdapter final : public HybridReachabilityAdapter {
public:
    mutable int calls{};
    mutable int capability_calls{};
    HybridReachabilityCapabilities capabilities() const noexcept override {
        ++capability_calls;
        return {true,Assurance::numerical};
    }
    HybridPathReachabilityResult compose_path(const model::HybridSystem&,
        const model::HybridRequest&,const model::HybridPath& path,
        model::HybridRelationLimits limits,std::stop_token) const override {
        ++calls;
        return model::HybridPathCompositionFailureReport{path,limits,{},
            Diagnostic{DiagnosticCode::unsupported,"fixture.reachability","fixture rejection"}};
    }
};

class MisreportingReachabilityPreflightAdapter final : public HybridReachabilityAdapter {
public:
    int corruption{};
    mutable int capability_calls{};
    mutable int calls{};
    HybridReachabilityCapabilities capabilities() const noexcept override {
        ++capability_calls;
        return {true,Assurance::numerical};
    }
    HybridReachabilityPreflightResult preflight(const model::HybridSystem&,
        const model::HybridRequest&,std::span<const model::HybridPath> paths,
        model::HybridRelationLimits limits,std::span<const model::HybridPlannedOperation>,
        std::stop_token) const override {
        auto reported_path=paths.back();
        auto reported_limits=limits;
        if(corruption==0) reported_path.edges.front().value+="-wrong";
        else ++reported_limits.max_rows;
        return model::HybridPathCompositionFailureReport{std::move(reported_path),
            reported_limits,{},Diagnostic{DiagnosticCode::unsupported,
                "fixture.reachability.preflight","fixture preflight rejection"}};
    }
    HybridPathReachabilityResult compose_path(const model::HybridSystem&,
        const model::HybridRequest&,const model::HybridPath& path,
        model::HybridRelationLimits limits,std::stop_token) const override {
        ++calls;
        return model::HybridPathCompositionFailureReport{path,limits,{},
            Diagnostic{DiagnosticCode::unsupported,"fixture.reachability","not expected"}};
    }
};

class CancellingReachabilityPreflightAdapter final : public HybridReachabilityAdapter {
public:
    explicit CancellingReachabilityPreflightAdapter(std::stop_source& cancellation)
        : cancellation_(&cancellation) {}
    mutable int capability_calls{};
    mutable int calls{};
    HybridReachabilityCapabilities capabilities() const noexcept override {
        ++capability_calls;
        return {true,Assurance::numerical};
    }
    HybridReachabilityPreflightResult preflight(const model::HybridSystem&,
        const model::HybridRequest&,std::span<const model::HybridPath>,
        model::HybridRelationLimits,std::span<const model::HybridPlannedOperation>,
        std::stop_token) const override {
        cancellation_->request_stop();
        return OperationStopped{StopReason::cancelled,"fixture cancelled reachability preflight"};
    }
    HybridPathReachabilityResult compose_path(const model::HybridSystem&,
        const model::HybridRequest&,const model::HybridPath& path,
        model::HybridRelationLimits limits,std::stop_token) const override {
        ++calls;
        return model::HybridPathCompositionFailureReport{path,limits,{},
            Diagnostic{DiagnosticCode::unsupported,"fixture.reachability","not expected"}};
    }
private:
    std::stop_source* cancellation_;
};

registry::PreparedProvider<registry::GeometryPort> row_limited_projection_provider(
    std::size_t maximum_rows,
    const std::shared_ptr<std::vector<std::pair<std::string,std::size_t>>>& admissions,
    const std::shared_ptr<int>& workspace_creations,
    std::stop_source* cancel_during_admission=nullptr,
    const std::shared_ptr<bool>& observed_actual_relation=nullptr,
    bool require_actual_relation=false,
    std::size_t estimated_peak_rows=0) {
    registry::Registry<registry::GeometryPort> providers;
    registry::Registration<registry::GeometryPort> registration{
        {ModuleId{"fixture.row-limited-projection"},"1.0"},
        [maximum_rows,admissions,cancel_during_admission,observed_actual_relation,
            require_actual_relation,estimated_peak_rows](const OperationRequest& request,
            const registry::Requirements&) -> registry::Capability {
            if(cancel_during_admission) cancel_during_admission->request_stop();
            const auto* projection=std::get_if<Projection>(&request.operation);
            if(!projection)
                return Diagnostics{{DiagnosticCode::invalid_input,"fixture.projection.operation",
                    "fixture expected a projection request"}};
            if(!projection->maximum_peak_rows)
                return Diagnostics{{DiagnosticCode::unsupported,"fixture.projection.unbounded",
                    "fixture requires the caller's peak-row budget during provider admission"}};
            const auto imported=sets::from_handle(projection->input);
            if(!std::holds_alternative<sets::SetData>(imported))
                return Diagnostics{{DiagnosticCode::invalid_input,"fixture.projection.input",
                    "fixture expected an importable projection input"}};
            const auto representation=std::get<sets::SetData>(imported).representation();
            if(!std::holds_alternative<sets::HRepresentation>(representation))
                return Diagnostics{{DiagnosticCode::unsupported,"fixture.projection.representation",
                    "fixture expected an H projection input"}};
            const auto& h=std::get<sets::HRepresentation>(representation);
            const auto rows=h.inequalities.rows()+h.equalities.rows();
            admissions->emplace_back(request.identity.request.value,rows);
            if(require_actual_relation) {
                const auto& data=std::get<sets::SetData>(imported);
                const auto has_nonzero_coefficient=[](const numeric::MatrixView& matrix) {
                    for(std::size_t row=0;row<matrix.rows();++row)
                        for(std::size_t col=0;col<matrix.cols();++col)
                            if(matrix(row,col)!=0.0) return true;
                    return false;
                };
                if(!request.identity.request.value.starts_with("terminal-state:") ||
                   projection->coordinates!=std::vector<std::size_t>{3} ||
                   h.equalities.rows()==0 ||
                   (!has_nonzero_coefficient(h.inequalities)&&!has_nonzero_coefficient(h.equalities)) ||
                   data.metadata()->coordinate_labels.size()!=4)
                    return Diagnostics{{DiagnosticCode::unsupported,"fixture.projection.actual_relation",
                        "fixture requires the exact labelled joint H relation and terminal coordinate"}};
                if(observed_actual_relation) *observed_actual_relation=true;
            }
            if(rows>maximum_rows || estimated_peak_rows>maximum_rows ||
               estimated_peak_rows>*projection->maximum_peak_rows)
                return Diagnostics{{DiagnosticCode::unsupported,"fixture.projection.preflight",
                    "fixture projection admission cannot honor the requested row budget"}};
            registry::Output output;
            output.representation={"csl.polyhedron.h"};
            output.relation=SetRelation::equivalent;
            return registry::Offer{output};
        },
        [workspace_creations](const OperationRequest&) -> std::unique_ptr<SetOperatorWorkspace> {
            ++*workspace_creations;
            return {};
        }};
    REQUIRE_FALSE(providers.add(std::move(registration)).has_value());
    registry::Requirements requirements;
    requirements.output.representation={"csl.polyhedron.h"};
    requirements.output.relation=SetRelation::equivalent;
    const auto prepared=registry::prepare_provider(registry::select_provider(providers,
        {ModuleId{"fixture.row-limited-projection"},std::string{"1.0"}},requirements));
    REQUIRE(std::holds_alternative<registry::PreparedProvider<registry::GeometryPort>>(prepared));
    return std::get<registry::PreparedProvider<registry::GeometryPort>>(prepared);
}

class MisreportingReachabilityAdapter final : public HybridReachabilityAdapter {
public:
    int corruption{};
    int admission_corruption{};
    mutable int calls{};
    mutable int capability_calls{};
    mutable int preflight_calls{};
    mutable std::size_t preflight_path_count{};
    mutable std::size_t preflight_plan_count{};
    HybridReachabilityCapabilities capabilities() const noexcept override {
        ++capability_calls;
        return {true,Assurance::numerical};
    }
    HybridReachabilityPreflightResult preflight(const model::HybridSystem& system,
        const model::HybridRequest& request,std::span<const model::HybridPath> paths,
        model::HybridRelationLimits limits,std::span<const model::HybridPlannedOperation> plan,
        std::stop_token cancellation) const override {
        ++preflight_calls;
        preflight_path_count=paths.size();
        preflight_plan_count=plan.size();
        const auto result=model::preflight_hybrid_path_relations(system,request,paths,limits,cancellation);
        if(const auto* failure=std::get_if<model::HybridPathCompositionFailureReport>(&result)) return *failure;
        if(const auto* diagnostics=std::get_if<Diagnostics>(&result)) return *diagnostics;
        if(const auto* stopped=std::get_if<OperationStopped>(&result)) return *stopped;
        std::vector<model::HybridPlannedOperation> receipt(plan.begin(),plan.end());
        if(admission_corruption==1&&!receipt.empty()) receipt.pop_back();
        if(admission_corruption==2&&receipt.size()>1) std::swap(receipt[0],receipt[1]);
        if(admission_corruption==3&&!receipt.empty()) receipt.push_back(receipt.front());
        return HybridOperationAdmissionSuccess{std::move(receipt)};
    }
    HybridPathReachabilityResult compose_path(const model::HybridSystem& system,
        const model::HybridRequest& request,const model::HybridPath& path,
        model::HybridRelationLimits limits,std::stop_token cancellation) const override {
        ++calls;
        JointHReachabilityAdapter delegate;
        auto result=delegate.compose_path(system,request,path,limits,cancellation);
        if(auto* reachable=std::get_if<HybridPathReachability>(&result)) {
            if(corruption==0) reachable->assurance=Assurance::validated;
            else if(corruption==1) ++reachable->relation_limits.max_rows;
            else if(corruption==2) ++reachable->relation_operations.front().rows_added;
            else if(corruption==3) reachable->relation_operations.front().stage=1;
            else if(corruption==4) {
                for(auto& operation:reachable->relation_operations) {
                    operation.joint_variables=0;
                    operation.cumulative_matrix_elements=0;
                }
            } else if(corruption==6)
                reachable->joint_relation=append_redundant_zero_inequality(
                    "fixture.reachability-extra-row",reachable->joint_relation);
        }
        return result;
    }
};

class FixtureHybridFamilyVerifier final : public HybridFamilyVerificationAdapter {
public:
    mutable int calls{};
    mutable int preflight_calls{};
    mutable int capability_calls{};
    mutable std::size_t preflight_path_count{};
    mutable std::size_t preflight_plan_count{};
    bool omit_last_branch{};
    bool claim_established_aggregates{};
    bool claim_coverage_only{};
    bool mark_all_branches_refuted{};
    bool inject_candidate_providers{};
    bool reject_preflight{};
    bool partial_operation_receipt{};
    std::stop_source* request_cancellation_after_preflight{};
    HybridFamilyVerificationCapabilities capabilities() const noexcept override {
        ++capability_calls;
        return {true,true,true,Assurance::numerical};
    }
    HybridFamilyVerificationPreflightResult preflight(const model::HybridSystem&,
        const model::HybridRequest&,std::span<const model::HybridPath> paths,
        std::span<const model::HybridPlannedOperation> plan,
        std::stop_token cancellation) const override {
        ++preflight_calls;
        preflight_path_count=paths.size();
        preflight_plan_count=plan.size();
        if(cancellation.stop_requested())
            return OperationStopped{StopReason::cancelled,"fixture preflight cancelled"};
        if(reject_preflight)
            return Diagnostics{{DiagnosticCode::unsupported,"fixture.verifier.preflight",
                "fixture rejects this verification request"}};
        std::vector<model::HybridPlannedOperation> admitted(plan.begin(),plan.end());
        if(partial_operation_receipt&&!admitted.empty()) admitted.resize(1);
        if(request_cancellation_after_preflight)
            request_cancellation_after_preflight->request_stop();
        return HybridOperationAdmissionSuccess{std::move(admitted)};
    }
    HybridFamilyVerificationResult verify(const model::HybridSystem&,
        const model::HybridRequest&,std::span<const model::HybridPath> paths,
        std::span<const HybridPathProgram>,std::span<const HybridPathOptimalFaceCandidate>,
        NumericalPolicy policy,std::stop_token cancellation) const override {
        ++calls;
        if(cancellation.stop_requested())
            return OperationStopped{StopReason::cancelled,"fixture verifier cancelled"};
        std::vector<model::HybridPath> inventory(paths.begin(),paths.end());
        std::vector<HybridPathVerificationRecord> branches;
        const auto count=omit_last_branch && !paths.empty()?paths.size()-1:paths.size();
        for(std::size_t i=0;i<count;++i) {
            const auto status=mark_all_branches_refuted?HybridVerificationStatus::refuted:
                (claim_coverage_only?HybridVerificationStatus::established:
                    HybridVerificationStatus::unsupported);
            branches.push_back({paths[i],status,status,status,{}});
            if(inject_candidate_providers)
                branches.back().candidate_providers.push_back({"fabricated provider",
                    {"fabricated.id",std::string{"0"}},registry::Identity{{"fabricated.id"},"0"}});
        }
        const auto aggregate=claim_established_aggregates?HybridVerificationStatus::established:
            HybridVerificationStatus::unsupported;
        const auto global=claim_established_aggregates?HybridVerificationStatus::established:
            HybridVerificationStatus::unsupported;
        const auto coverage=claim_coverage_only?HybridVerificationStatus::established:aggregate;
        return HybridFamilyVerificationReport{"fixture.hybrid.verifier","1",policy,
            Assurance::numerical,std::move(inventory),std::move(branches),
            global,coverage,{}, {}};
    }
};

class DefaultPreflightHybridFamilyVerifier final : public HybridFamilyVerificationAdapter {
public:
    HybridFamilyVerificationCapabilities capabilities() const noexcept override {
        return {true,true,true,Assurance::numerical};
    }
    HybridFamilyVerificationResult verify(const model::HybridSystem&,
        const model::HybridRequest&,std::span<const model::HybridPath>,
        std::span<const HybridPathProgram>,std::span<const HybridPathOptimalFaceCandidate>,
        NumericalPolicy,std::stop_token) const override {
        return Diagnostics{{DiagnosticCode::unsupported,"fixture.hybrid.verifier","not used"}};
    }
};

std::pair<model::HybridSystem,model::HybridRequest> variable_size_parallel_profile() {
    auto source=model::HybridMode{{"source"},1,0,{"x"},{}};
    source.flow=LinearStage{Matrix{1,1,{1}},Matrix{1,0,{}},Matrix{1,0,{}},Vector{0}};
    source.control_sets={UniversalSet{0}};
    source.invariants={UniversalSet{1},UniversalSet{1}};
    auto small=model::HybridMode{{"small"},1,0,{"x"},{}};
    small.flow=LinearStage{Matrix{1,1,{1}},Matrix{1,0,{}},Matrix{1,0,{}},Vector{0}};
    small.control_sets={UniversalSet{0}};
    small.invariants={UniversalSet{1},UniversalSet{1}};
    auto large=model::HybridMode{{"large"},2,0,{"x","y"},{}};
    large.flow=LinearStage{Matrix{2,2,{1,0,0,1}},Matrix{2,0,{}},Matrix{2,0,{}},Vector{0,0}};
    large.control_sets={UniversalSet{0}};
    large.invariants={UniversalSet{2},UniversalSet{2}};
    auto wide=model::HybridMode{{"wide"},3,0,{"x","y","z"},{}};
    wide.flow=LinearStage{Matrix{3,3,{1,0,0,0,1,0,0,0,1}},Matrix{3,0,{}},Matrix{3,0,{}},Vector{0,0,0}};
    wide.control_sets={UniversalSet{0}};
    wide.invariants={UniversalSet{3},UniversalSet{3}};
    model::HybridSystem system{1,{source,small,large,wide},
        {{{"to-small"},{"source"},{"small"},{UniversalSet{1}},{universal("small-reset",2)}},
         {{"to-large"},{"source"},{"large"},{UniversalSet{1}},{universal("large-reset",3)}},
         {{"to-wide"},{"source"},{"wide"},{UniversalSet{1}},{universal("wide-reset",4)}}}};
    model::HybridRequest request{{{"source"},{0}},{{"small"},{"large"},{"wide"}},
        {{{"small"},LinearTerminal{{1},0},"cost","u"},
         {{"large"},LinearTerminal{{1,0},0},"cost","u"},
         {{"wide"},LinearTerminal{{1,0,0},0},"cost","u"}}};
    return {std::move(system),std::move(request)};
}

SetHandle interval(std::string id,double lower,double upper) {
    auto matrix=numeric::snapshot(Matrix{2,1,{-1,1}});
    auto bounds=numeric::snapshot_vector(Vector{-lower,upper});
    auto equalities=numeric::snapshot(Matrix{0,1,{}});
    auto rhs=numeric::snapshot_vector(Vector{});
    REQUIRE(std::holds_alternative<numeric::MatrixView>(matrix));
    REQUIRE(std::holds_alternative<numeric::VectorView>(bounds));
    REQUIRE(std::holds_alternative<numeric::MatrixView>(equalities));
    REQUIRE(std::holds_alternative<numeric::VectorView>(rhs));
    auto data=sets::make_h({SetId{std::move(id)},1,{"guard-coordinate"}},
        {std::get<numeric::MatrixView>(matrix),std::get<numeric::VectorView>(bounds),
         std::get<numeric::MatrixView>(equalities),std::get<numeric::VectorView>(rhs)});
    REQUIRE(std::holds_alternative<sets::SetData>(data));
    return std::get<sets::SetData>(std::move(data)).as_handle();
}

SetHandle scaled_interval(std::string id,double lower,double upper,double scale) {
    auto inequalities=numeric::snapshot(Matrix{2,1,{-scale,scale}});
    auto bounds=numeric::snapshot_vector(Vector{-scale*lower,scale*upper});
    auto equalities=numeric::snapshot(Matrix{0,1,{}});
    auto equality_values=numeric::snapshot_vector(Vector{});
    REQUIRE(std::holds_alternative<numeric::MatrixView>(inequalities));
    REQUIRE(std::holds_alternative<numeric::VectorView>(bounds));
    REQUIRE(std::holds_alternative<numeric::MatrixView>(equalities));
    REQUIRE(std::holds_alternative<numeric::VectorView>(equality_values));
    auto data=sets::make_h({SetId{std::move(id)},1,{"scaled-coordinate"}},
        {std::get<numeric::MatrixView>(inequalities),std::get<numeric::VectorView>(bounds),
         std::get<numeric::MatrixView>(equalities),std::get<numeric::VectorView>(equality_values)});
    REQUIRE(std::holds_alternative<sets::SetData>(data));
    return std::get<sets::SetData>(std::move(data)).as_handle();
}

std::pair<model::HybridSystem,model::HybridRequest> projected_interval_fixture() {
    model::HybridMode source{{"source"},1,1,{"x"},{"u"}};
    source.flow=LinearStage{Matrix{1,1,{1}},Matrix{1,1,{1}},Matrix{1,0,{}},Vector{0}};
    source.control_sets={interval("projected-control",0,1)};
    source.invariants={UniversalSet{1},UniversalSet{1}};
    model::HybridMode target{{"target"},1,0,{"y"},{}};
    target.flow=LinearStage{Matrix{1,1,{1}},Matrix{1,0,{}},Matrix{1,0,{}},Vector{0}};
    target.control_sets={UniversalSet{0}};
    target.invariants={UniversalSet{1},UniversalSet{1}};
    auto reset=sets::make_h({{"projected-identity-reset"},2,{"pre","post"}},
        {std::get<numeric::MatrixView>(numeric::snapshot(Matrix{0,2,{}})),
         std::get<numeric::VectorView>(numeric::snapshot_vector(Vector{})),
         std::get<numeric::MatrixView>(numeric::snapshot(Matrix{1,2,{1,-1}})),
         std::get<numeric::VectorView>(numeric::snapshot_vector(Vector{0}))});
    REQUIRE(std::holds_alternative<sets::SetData>(reset));
    model::HybridSystem system{1,{source,target},
        {{{"transition"},{"source"},{"target"},{interval("projected-guard",0,0.5)},
            {std::get<sets::SetData>(std::move(reset)).as_handle()}}}};
    model::HybridRequest request{{{"source"},{0}},{{"target"}},
        {{{"target"},LinearTerminal{{1},0},"cost","u"}}};
    return {std::move(system),std::move(request)};
}

SetHandle vertex_guard(std::string id) {
    const auto vertices=numeric::snapshot(Matrix{1,1,{0}});
    const auto rays=numeric::snapshot(Matrix{0,1,{}});
    REQUIRE(std::holds_alternative<numeric::MatrixView>(vertices));
    REQUIRE(std::holds_alternative<numeric::MatrixView>(rays));
    auto data=sets::make_v({SetId{std::move(id)},1,{"guard-coordinate"}},
        {std::get<numeric::MatrixView>(vertices),std::get<numeric::MatrixView>(rays)});
    REQUIRE(std::holds_alternative<sets::SetData>(data));
    return std::get<sets::SetData>(std::move(data)).as_handle();
}

SetHandle affine_reset() {
    auto inequalities=numeric::snapshot(Matrix{0,3,{}});
    auto upper=numeric::snapshot_vector(Vector{});
    auto equalities=numeric::snapshot(Matrix{1,3,{-1,1,0}});
    auto rhs=numeric::snapshot_vector(Vector{0});
    REQUIRE(std::holds_alternative<numeric::MatrixView>(inequalities));
    REQUIRE(std::holds_alternative<numeric::VectorView>(upper));
    REQUIRE(std::holds_alternative<numeric::MatrixView>(equalities));
    REQUIRE(std::holds_alternative<numeric::VectorView>(rhs));
    auto data=sets::make_h({{"affine-reset"},3,{}},
        {std::get<numeric::MatrixView>(inequalities),std::get<numeric::VectorView>(upper),
         std::get<numeric::MatrixView>(equalities),std::get<numeric::VectorView>(rhs)});
    REQUIRE(std::holds_alternative<sets::SetData>(data));
    return std::get<sets::SetData>(std::move(data)).as_handle();
}

sets::SetData relation_excluding_anchor() {
    auto inequalities=numeric::snapshot(Matrix{0,5,{}});
    auto upper=numeric::snapshot_vector(Vector{});
    auto equalities=numeric::snapshot(Matrix{1,5,{1,0,0,0,0}});
    auto rhs=numeric::snapshot_vector(Vector{0});
    REQUIRE(std::holds_alternative<numeric::MatrixView>(inequalities));
    REQUIRE(std::holds_alternative<numeric::VectorView>(upper));
    REQUIRE(std::holds_alternative<numeric::MatrixView>(equalities));
    REQUIRE(std::holds_alternative<numeric::VectorView>(rhs));
    auto data=sets::make_h({{"wrong-joint-relation"},5,{}},
        {std::get<numeric::MatrixView>(inequalities),std::get<numeric::VectorView>(upper),
         std::get<numeric::MatrixView>(equalities),std::get<numeric::VectorView>(rhs)});
    REQUIRE(std::holds_alternative<sets::SetData>(data));
    return std::get<sets::SetData>(std::move(data));
}

bool satisfies(const sets::HRepresentation& h,const Vector& point) {
    for(std::size_t i=0;i<h.inequalities.rows();++i) {
        double value=0;
        for(std::size_t j=0;j<h.inequalities.cols();++j) value+=h.inequalities(i,j)*point[j];
        if(value>h.upper_bounds[i]) return false;
    }
    for(std::size_t i=0;i<h.equalities.rows();++i) {
        double value=0;
        for(std::size_t j=0;j<h.equalities.cols();++j) value+=h.equalities(i,j)*point[j];
        if(value!=h.equality_values[i]) return false;
    }
    return true;
}

class RejectingLP final : public LPWorkspace {
    ProgramOutcome do_solve(const LinearProgram&,const ExecutionContext&) override {
        return Unsupported{{{DiagnosticCode::unsupported,"fixture.lp","fixture rejection"}}};
    }
};

class CompletingLP final : public LPWorkspace {
    ProgramOutcome do_solve(const LinearProgram& program,const ExecutionContext&) override {
        return ProgramResult{Termination::completed,
            {program.identity(),MathematicalOutcome::undetermined,Unestablished{},{}},
            {},{},"fixture completed"};
    }
};

class RejectingConvex final : public ConvexWorkspace {
    ProgramOutcome do_solve(const ConvexProgram&,const ExecutionContext&) override {
        return Unsupported{{{DiagnosticCode::unsupported,"fixture.convex","fixture rejection"}}};
    }
};

registry::PreparedProvider<registry::LPPort> lp_provider(std::stop_source* cancel_during_prepare=nullptr,
    std::shared_ptr<int> factory_calls=std::make_shared<int>(0),std::string reject_problem={},
    std::string cancel_problem={}) {
    registry::Registry<registry::LPPort> providers;
    REQUIRE_FALSE(providers.add({{{"reject-lp"},"1"},
        [cancel_during_prepare,reject_problem,cancel_problem](const LinearProgram& program,const registry::Requirements&)->registry::Capability{
            if(cancel_during_prepare && (cancel_problem.empty() || program.identity().problem.value==cancel_problem))
                cancel_during_prepare->request_stop();
            if(program.identity().problem.value==reject_problem && !reject_problem.empty())
                return Diagnostics{{DiagnosticCode::unsupported,"fixture.capability","requested fixture rejection"}};
            return registry::Offer{};
        },
        [factory_calls](const LinearProgram&){++*factory_calls; return std::make_unique<RejectingLP>();}}));
    auto prepared=registry::prepare_provider(registry::select_provider(providers,{{"reject-lp"},{}}));
    REQUIRE(std::holds_alternative<registry::PreparedProvider<registry::LPPort>>(prepared));
    return std::get<registry::PreparedProvider<registry::LPPort>>(std::move(prepared));
}

registry::PreparedProvider<registry::LPPort> completing_lp_provider() {
    registry::Registry<registry::LPPort> providers;
    REQUIRE_FALSE(providers.add({{{"completing-lp"},"1"},
        [](const LinearProgram&,const registry::Requirements&)->registry::Capability{return registry::Offer{};},
        [](const LinearProgram&){return std::make_unique<CompletingLP>();}}));
    auto prepared=registry::prepare_provider(registry::select_provider(providers,{{"completing-lp"},{}}));
    REQUIRE(std::holds_alternative<registry::PreparedProvider<registry::LPPort>>(prepared));
    return std::get<registry::PreparedProvider<registry::LPPort>>(std::move(prepared));
}

registry::PreparedProvider<registry::ConvexPort> convex_provider() {
    registry::Registry<registry::ConvexPort> providers;
    REQUIRE_FALSE(providers.add({{{"reject-convex"},"1"},
        [](const ConvexProgram&,const registry::Requirements&)->registry::Capability{return registry::Offer{};},
        [](const ConvexProgram&){return std::make_unique<RejectingConvex>();}}));
    auto prepared=registry::prepare_provider(registry::select_provider(providers,{{"reject-convex"},{}}));
    REQUIRE(std::holds_alternative<registry::PreparedProvider<registry::ConvexPort>>(prepared));
    return std::get<registry::PreparedProvider<registry::ConvexPort>>(std::move(prepared));
}
}

TEST_CASE("hybrid direct path program preserves branch and terminal objective coordinates") {
    const auto result=build_hybrid_path_program(example_system(),example_request(),example_path(),
        {"hybrid-problem"},{16,64,1024});
    REQUIRE(std::holds_alternative<HybridPathProgram>(result));
    const auto& built=std::get<HybridPathProgram>(result);
    REQUIRE(std::holds_alternative<LinearProgram>(built.program));
    const auto& program=std::get<LinearProgram>(built.program);
    CHECK(program.identity().problem.value=="hybrid-problem");
    CHECK(program.identity().program.value=="hybrid-path:6:switch");
    CHECK(program.objective().size()==5);
    CHECK(program.objective()[0]==0);
    CHECK(program.objective()[1]==0);
    CHECK(program.objective()[2]==0);
    CHECK(program.objective()[3]==2);
    CHECK(program.objective()[4]==-1);
    const auto constraints=std::get<numeric::CsrInput>(program.constraints().descriptor());
    CHECK(std::vector<std::size_t>(constraints.row_offsets.begin(),constraints.row_offsets.end())==
        std::vector<std::size_t>{0,1,4});
    CHECK(std::vector<std::size_t>(constraints.column_indices.begin(),constraints.column_indices.end())==
        std::vector<std::size_t>{0,0,1,2});
    CHECK(std::vector<double>(constraints.values.begin(),constraints.values.end())==
        std::vector<double>{1,-1,-1,1});
    CHECK(program.rows().size()==2);
    CHECK(program.rows()[0].lower==2);
    CHECK(program.rows()[0].upper==2);
    CHECK(program.rows()[1].lower==0);
    CHECK(program.rows()[1].upper==0);
    CHECK(built.joint_relation.metadata()->set.dimension==5);
    CHECK(built.path==example_path());
    CHECK(built.relation_limits.max_variables==16);
    REQUIRE(built.relation_operations.size()==8);
    CHECK(built.relation_operations[2].operation==model::HybridRelationOperationKind::mode_flow);
    CHECK(built.relation_operations[2].mode==model::HybridModeId{"source"});
    CHECK(built.relation_operations[5].operation==model::HybridRelationOperationKind::transition_guard);
    CHECK(built.relation_operations[5].edge==model::HybridEdgeId{"switch"});
}

TEST_CASE("hybrid program construction preserves cancellation and unsupported limits") {
    std::stop_source cancellation;
    cancellation.request_stop();
    const auto stopped=build_hybrid_path_program(example_system(),example_request(),example_path(),
        {"hybrid-problem"},{16,64,1024},{},cancellation.get_token());
    REQUIRE(std::holds_alternative<OperationStopped>(stopped));
    CHECK(std::get<OperationStopped>(stopped).reason==StopReason::cancelled);

    const auto limited=build_hybrid_path_program(example_system(),example_request(),example_path(),
        {"hybrid-problem"},{4,64,1024});
    REQUIRE(std::holds_alternative<model::HybridPathCompositionFailureReport>(limited));
    const auto& failure=std::get<model::HybridPathCompositionFailureReport>(limited);
    CHECK(failure.path==example_path());
    CHECK(failure.limits.max_variables==4);
    const auto* diagnostic=std::get_if<Diagnostic>(&failure.failure);
    REQUIRE(diagnostic);
    CHECK(diagnostic->code==DiagnosticCode::unsupported);
}

TEST_CASE("hybrid direct path programs admit quadratic and residual terminal objectives") {
    auto request=example_request();
    request.terminal_objectives[0].objective=QuadraticTerminal{
        Matrix{2,2,{1,0,0,1}},Vector{0,0},0};
    auto quadratic=build_hybrid_path_program(example_system(),request,example_path(),
        {"hybrid-problem"},{16,64,1024});
    REQUIRE(std::holds_alternative<HybridPathProgram>(quadratic));
    REQUIRE(std::holds_alternative<ConvexProgram>(std::get<HybridPathProgram>(quadratic).program));
    CHECK(std::get<ConvexProgram>(std::get<HybridPathProgram>(quadratic).program).original_objective().dimension()==5);

    request.terminal_objectives[0].objective=ResidualNormTerminal{Matrix{1,2,{1,-1}},Vector{0}};
    auto residual=build_hybrid_path_program(example_system(),request,example_path(),
        {"hybrid-problem"},{16,64,1024});
    REQUIRE(std::holds_alternative<HybridPathProgram>(residual));
    REQUIRE(std::holds_alternative<ConvexProgram>(std::get<HybridPathProgram>(residual).program));
    CHECK(std::get<ConvexProgram>(std::get<HybridPathProgram>(residual).program).original_objective().dimension()==5);
}

TEST_CASE("hybrid portfolio builder returns every parallel edge branch transactionally") {
    auto system=example_system();
    auto parallel=system.edges.front();
    parallel.id={"switch-parallel"};
    system.edges.push_back(std::move(parallel));
    const auto built=build_hybrid_portfolio_programs(system,example_request(),{"hybrid-problem"},
        {1,8},{16,64,1024});
    REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(built));
    const auto& programs=std::get<std::vector<HybridPathProgram>>(built);
    REQUIRE(programs.size()==2);
    CHECK(programs[0].path.modes==programs[1].path.modes);
    CHECK(programs[0].path.edges!=programs[1].path.edges);
    const auto& first=std::get<LinearProgram>(programs[0].program);
    const auto& second=std::get<LinearProgram>(programs[1].program);
    CHECK(first.identity().program!=second.identity().program);

    const auto limited=build_hybrid_portfolio_programs(system,example_request(),{"hybrid-problem"},
        {1,8},{4,64,1024});
    REQUIRE(std::holds_alternative<model::HybridPathCompositionFailureReport>(limited));
    const auto& failure=std::get<model::HybridPathCompositionFailureReport>(limited);
    CHECK(failure.path==example_path());
    const auto* diagnostic=std::get_if<Diagnostic>(&failure.failure);
    REQUIRE(diagnostic);
    CHECK(diagnostic->field=="hybrid.relation.variables");
}

TEST_CASE("hybrid portfolio builder dispatches through the injected direct trajectory adapter") {
    auto system=example_system();
    auto parallel=system.edges.front();
    parallel.id={"switch-parallel"};
    system.edges.push_back(std::move(parallel));
    RejectingTrajectoryAdapter adapter;
    const auto result=build_hybrid_portfolio_programs(adapter,system,example_request(),
        {"hybrid-problem"},{1,8},{16,64,1024});
    REQUIRE(std::holds_alternative<Diagnostics>(result));
    CHECK(std::get<Diagnostics>(result).front().field=="fixture.hybrid_adapter");
    CHECK(adapter.calls==1);
}

TEST_CASE("hybrid portfolio preflights all terminal objective capabilities before adapter dispatch") {
    auto system=example_system();
    auto second_terminal=system.modes.back();
    second_terminal.id={"target-quadratic"};
    system.modes.push_back(std::move(second_terminal));
    auto second_edge=system.edges.front();
    second_edge.id={"switch-quadratic"};
    second_edge.target={"target-quadratic"};
    system.edges.push_back(std::move(second_edge));

    auto request=example_request();
    request.allowed_terminal_modes.push_back({"target-quadratic"});
    request.terminal_objectives.push_back({{"target-quadratic"},
        QuadraticTerminal{Matrix{2,2,{1,0,0,1}},Vector{0,0},0},"energy","J"});

    LinearOnlyRejectingTrajectoryAdapter adapter;
    const auto result=build_hybrid_portfolio_programs(adapter,system,request,
        {"hybrid-problem"},{1,8},{16,64,1024});
    REQUIRE(std::holds_alternative<Diagnostics>(result));
    CHECK(std::get<Diagnostics>(result).front().code==DiagnosticCode::unsupported);
    CHECK(std::get<Diagnostics>(result).front().field=="hybrid.portfolio.objective");
    CHECK(adapter.calls==0);
    CHECK(adapter.capability_calls==1);

    FixtureHybridFamilyVerifier verifier;
    LinearOnlyRejectingTrajectoryAdapter verified_adapter;
    const auto verified=build_hybrid_portfolio_programs_with_verifier(verifier,verified_adapter,
        system,request,{"hybrid-problem"},{1,8},{16,64,1024});
    REQUIRE(std::holds_alternative<Diagnostics>(verified));
    CHECK(std::get<Diagnostics>(verified).front().code==DiagnosticCode::unsupported);
    CHECK(std::get<Diagnostics>(verified).front().field=="hybrid.portfolio.objective");
    CHECK(verified_adapter.calls==0);
}

TEST_CASE("hybrid portfolio validates objectives for unreachable allowed terminal modes") {
    auto system=example_system();
    auto unreachable_terminal=system.modes.back();
    unreachable_terminal.id={"unreachable-terminal"};
    system.modes.push_back(std::move(unreachable_terminal));

    auto request=example_request();
    request.allowed_terminal_modes.push_back({"unreachable-terminal"});
    request.terminal_objectives.push_back({{"unreachable-terminal"},
        QuadraticTerminal{Matrix{2,2,{1,0,0,1}},Vector{0,0},0},"energy","J"});

    LinearOnlyRejectingTrajectoryAdapter adapter;
    const auto result=build_hybrid_portfolio_programs(adapter,system,request,
        {"hybrid-problem"},{1,8},{16,64,1024});
    REQUIRE(std::holds_alternative<Diagnostics>(result));
    CHECK(std::get<Diagnostics>(result).front().code==DiagnosticCode::unsupported);
    CHECK(std::get<Diagnostics>(result).front().field=="hybrid.portfolio.objective");
    CHECK(std::get<Diagnostics>(result).front().explanation.find("unreachable-terminal")!=
        std::string::npos);
    CHECK(adapter.capability_calls==1);
    CHECK(adapter.calls==0);

    FixtureHybridFamilyVerifier verifier;
    LinearOnlyRejectingTrajectoryAdapter verified_adapter;
    const auto verified=build_hybrid_portfolio_programs_with_verifier(verifier,
        verified_adapter,system,request,{"hybrid-problem"},{1,8},{16,64,1024});
    REQUIRE(std::holds_alternative<Diagnostics>(verified));
    CHECK(std::get<Diagnostics>(verified).front().field=="hybrid.portfolio.objective");
    CHECK(std::get<Diagnostics>(verified).front().explanation.find("unreachable-terminal")!=
        std::string::npos);
    CHECK(verified_adapter.capability_calls==1);
    CHECK(verified_adapter.calls==0);
}

TEST_CASE("exact linear H verifier rejects unreachable unsupported terminal objectives before dispatch") {
    auto system=example_system();
    auto unreachable_terminal=system.modes.back();
    unreachable_terminal.id={"unreachable-terminal"};
    system.modes.push_back(std::move(unreachable_terminal));

    auto request=example_request();
    request.allowed_terminal_modes.push_back({"unreachable-terminal"});
    request.terminal_objectives.push_back({{"unreachable-terminal"},
        QuadraticTerminal{Matrix{2,2,{1,0,0,1}},Vector{0,0},0},"energy","J"});

    ExactLinearHHybridFamilyVerifier verifier;
    RejectingTrajectoryAdapter trajectory;
    const auto result=build_hybrid_portfolio_programs_with_verifier(verifier,trajectory,
        system,request,{"unreachable-terminal-objective"},{1,8},{16,64,1024});
    REQUIRE(std::holds_alternative<Diagnostics>(result));
    const auto& diagnostics=std::get<Diagnostics>(result);
    REQUIRE_FALSE(diagnostics.empty());
    CHECK(diagnostics.front().code==DiagnosticCode::unsupported);
    CHECK(diagnostics.front().field=="hybrid.verification.exact_linear_h_objective");
    CHECK(diagnostics.front().explanation.find("unreachable-terminal")!=std::string::npos);
    CHECK(trajectory.calls==0);
    CHECK(trajectory.capability_calls==0);
}

TEST_CASE("exact singleton verifier rejects unreachable unsupported terminal objectives before dispatch") {
    auto system=example_system();
    auto unreachable_terminal=system.modes.back();
    unreachable_terminal.id={"unreachable-terminal"};
    system.modes.push_back(std::move(unreachable_terminal));

    auto request=example_request();
    request.allowed_terminal_modes.push_back({"unreachable-terminal"});
    request.terminal_objectives.push_back({{"unreachable-terminal"},
        QuadraticTerminal{Matrix{2,2,{1,0,0,1}},Vector{0,0},0},"energy","J"});

    ExactSingletonHybridFamilyVerifier verifier;
    RejectingTrajectoryAdapter trajectory;
    const auto result=build_hybrid_portfolio_programs_with_verifier(verifier,trajectory,
        system,request,{"unreachable-singleton-terminal-objective"},{1,8},{16,64,1024});
    REQUIRE(std::holds_alternative<Diagnostics>(result));
    const auto& diagnostics=std::get<Diagnostics>(result);
    REQUIRE_FALSE(diagnostics.empty());
    CHECK(diagnostics.front().code==DiagnosticCode::unsupported);
    CHECK(diagnostics.front().field=="hybrid.verification.exact_singleton_objective");
    CHECK(diagnostics.front().explanation.find("unreachable-terminal")!=std::string::npos);
    CHECK(trajectory.calls==0);
    CHECK(trajectory.capability_calls==0);
}

TEST_CASE("scalar interval verifiers preflight objectives for every allowed terminal mode") {
    const auto make_scalar_system=[](std::size_t horizon) {
        model::HybridMode source{{"source"},1,1,{"x"},{"u"}};
        model::HybridMode target{{"target"},1,0,{"y"},{}};
        const LinearStage source_flow{
            Matrix{1,1,{1}},Matrix{1,1,{1}},Matrix{1,0,{}},Vector{0}};
        const LinearStage target_flow{
            Matrix{1,1,{1}},Matrix{1,0,{}},Matrix{1,0,{}},Vector{0}};
        source.flow=std::vector<LinearStage>(horizon,source_flow);
        source.control_sets.assign(horizon,UniversalSet{1});
        source.invariants.assign(horizon+1,UniversalSet{1});
        target.flow=std::vector<LinearStage>(horizon,target_flow);
        target.control_sets.assign(horizon,UniversalSet{0});
        target.invariants.assign(horizon+1,UniversalSet{1});
        auto unreachable=target;
        unreachable.id={"unreachable-terminal"};
        return model::HybridSystem{horizon,
            {std::move(source),std::move(target),std::move(unreachable)}, {}};
    };
    const auto make_request=[] {
        return model::HybridRequest{{{"source"},{0}},{{"target"},{"unreachable-terminal"}},
            {{{"target"},LinearTerminal{{1},0},"energy","J"},
             {{"unreachable-terminal"},
                 QuadraticTerminal{Matrix{1,1,{1}},Vector{0},0},"energy","J"}}};
    };
    const auto check_rejection=[&](auto& verifier,std::size_t horizon) {
        const auto system=make_scalar_system(horizon);
        const auto request=make_request();
        const std::vector<model::HybridPath> paths;
        const std::vector<model::HybridPlannedOperation> operation_plan;
        const auto result=verifier.preflight(system,request,paths,operation_plan,{});
        REQUIRE(std::holds_alternative<Diagnostics>(result));
        REQUIRE_FALSE(std::get<Diagnostics>(result).empty());
        CHECK(std::get<Diagnostics>(result).front().code==DiagnosticCode::unsupported);
        CHECK(std::get<Diagnostics>(result).front().field==
            "hybrid.verification.scalar_interval_objective");
        CHECK(std::get<Diagnostics>(result).front().explanation.find("unreachable-terminal")!=
            std::string::npos);
    };

    OneStepScalarIntervalHybridFamilyVerifier one_step;
    SingleParameterScalarIntervalHybridFamilyVerifier single_parameter;
    TwoStageScalarIntervalHybridFamilyVerifier two_stage;
    TwoParameterScalarPolytopeHybridFamilyVerifier two_parameter;
    check_rejection(one_step,1);
    const auto single_parameter_system=make_scalar_system(1);
    const auto single_parameter_request=make_request();
    const std::vector<model::HybridPath> no_single_parameter_paths;
    const std::vector<model::HybridPlannedOperation> no_single_parameter_operations;
    const auto single_parameter_preflight=single_parameter.preflight(single_parameter_system,
        single_parameter_request,no_single_parameter_paths,no_single_parameter_operations,{});
    CHECK(std::holds_alternative<HybridOperationAdmissionSuccess>(single_parameter_preflight));
    auto malformed_request=single_parameter_request;
    malformed_request.terminal_objectives.back().objective=
        QuadraticTerminal{Matrix{1,1,{}},Vector{0},0};
    const auto malformed_preflight=single_parameter.preflight(single_parameter_system,
        malformed_request,no_single_parameter_paths,no_single_parameter_operations,{});
    REQUIRE(std::holds_alternative<Diagnostics>(malformed_preflight));
    CHECK(std::get<Diagnostics>(malformed_preflight).front().code==DiagnosticCode::unsupported);
    const auto two_stage_system=make_scalar_system(2);
    const auto two_stage_request=make_request();
    const std::vector<model::HybridPath> no_two_stage_paths;
    const std::vector<model::HybridPlannedOperation> no_two_stage_operations;
    const auto two_stage_preflight=two_stage.preflight(two_stage_system,two_stage_request,
        no_two_stage_paths,no_two_stage_operations,{});
    CHECK(std::holds_alternative<HybridOperationAdmissionSuccess>(two_stage_preflight));
    const auto two_parameter_system=make_scalar_system(2);
    const auto two_parameter_request=make_request();
    const std::vector<model::HybridPath> no_paths;
    const std::vector<model::HybridPlannedOperation> no_operations;
    const auto two_parameter_result=two_parameter.preflight(two_parameter_system,
        two_parameter_request,no_paths,no_operations,{});
    REQUIRE(std::holds_alternative<Diagnostics>(two_parameter_result));
    REQUIRE_FALSE(std::get<Diagnostics>(two_parameter_result).empty());
    CHECK(std::get<Diagnostics>(two_parameter_result).front().code==
        DiagnosticCode::unsupported);
    CHECK(std::get<Diagnostics>(two_parameter_result).front().field==
        "hybrid.verification.two_parameter_objective");
    CHECK(std::get<Diagnostics>(two_parameter_result).front().explanation.find(
        "unreachable-terminal")!=std::string::npos);
    auto wrong_dimension_request=two_parameter_request;
    wrong_dimension_request.terminal_objectives.back().objective=
        LinearTerminal{{1,0},0};
    const auto wrong_dimension=two_parameter.preflight(two_parameter_system,
        wrong_dimension_request,no_paths,no_operations,{});
    REQUIRE(std::holds_alternative<Diagnostics>(wrong_dimension));
    CHECK(std::get<Diagnostics>(wrong_dimension).front().code==
        DiagnosticCode::unsupported);
    CHECK(std::get<Diagnostics>(wrong_dimension).front().field==
        "hybrid.verification.two_parameter_objective");
}

TEST_CASE("hybrid portfolio capability preflight honors cancellation before scanning paths") {
    std::stop_source cancellation;
    CancellingCapabilityTrajectoryAdapter adapter{cancellation};
    const auto result=build_hybrid_portfolio_programs(adapter,example_system(),example_request(),
        {"hybrid-problem"},{1,8},{16,64,1024},{},cancellation.get_token());
    REQUIRE(std::holds_alternative<OperationStopped>(result));
    CHECK(std::get<OperationStopped>(result).reason==StopReason::cancelled);
    CHECK(adapter.calls==0);
}

TEST_CASE("hybrid portfolio preflights objective policy before adapter dispatch") {
    RejectingTrajectoryAdapter validated_adapter;
    optimization::ObjectivePolicy validated_policy;
    validated_policy.assurance=Assurance::validated;
    const auto validated=build_hybrid_portfolio_programs(validated_adapter,
        example_system(),example_request(),{"hybrid-problem"},{1,8},{16,64,1024},
        validated_policy);
    REQUIRE(std::holds_alternative<Diagnostics>(validated));
    CHECK(std::get<Diagnostics>(validated).front().code==DiagnosticCode::unsupported);
    CHECK(std::get<Diagnostics>(validated).front().field=="hybrid.adapter.objective_policy");
    CHECK(validated_adapter.calls==0);
    CHECK(validated_adapter.capability_calls==0);

    FixtureHybridFamilyVerifier verifier;
    RejectingTrajectoryAdapter verified_adapter;
    const auto verified=build_hybrid_portfolio_programs_with_verifier(verifier,verified_adapter,
        example_system(),example_request(),{"hybrid-problem"},{1,8},{16,64,1024},
        validated_policy);
    REQUIRE(std::holds_alternative<Diagnostics>(verified));
    CHECK(std::get<Diagnostics>(verified).front().code==DiagnosticCode::unsupported);
    CHECK(std::get<Diagnostics>(verified).front().field=="hybrid.adapter.objective_policy");
    CHECK(verified_adapter.calls==0);
    CHECK(verified_adapter.capability_calls==0);
    CHECK(verifier.capability_calls==0);
    CHECK(verifier.preflight_calls==0);

    RejectingTrajectoryAdapter invalid_tolerance_adapter;
    optimization::ObjectivePolicy invalid_tolerance_policy;
    invalid_tolerance_policy.numerical.absolute_tolerance=
        std::numeric_limits<double>::quiet_NaN();
    const auto invalid_tolerance=build_hybrid_portfolio_programs(invalid_tolerance_adapter,
        example_system(),example_request(),{"hybrid-problem"},{1,8},{16,64,1024},
        invalid_tolerance_policy);
    REQUIRE(std::holds_alternative<Diagnostics>(invalid_tolerance));
    CHECK(std::get<Diagnostics>(invalid_tolerance).front().code==DiagnosticCode::invalid_input);
    CHECK(std::get<Diagnostics>(invalid_tolerance).front().field=="hybrid.adapter.objective_policy");
    CHECK(invalid_tolerance_adapter.calls==0);
    CHECK(invalid_tolerance_adapter.capability_calls==0);
}

TEST_CASE("hybrid path builder validates objective policy before adapter dispatch") {
    RejectingTrajectoryAdapter validated_adapter;
    optimization::ObjectivePolicy validated_policy;
    validated_policy.assurance=Assurance::validated;
    const auto validated=build_hybrid_path_program(validated_adapter,example_system(),
        example_request(),example_path(),{"hybrid-problem"},{16,64,1024},validated_policy);
    REQUIRE(std::holds_alternative<Diagnostics>(validated));
    CHECK(std::get<Diagnostics>(validated).front().code==DiagnosticCode::unsupported);
    CHECK(std::get<Diagnostics>(validated).front().field=="hybrid.adapter.objective_policy");
    CHECK(validated_adapter.calls==0);
    CHECK(validated_adapter.capability_calls==0);

    RejectingTrajectoryAdapter invalid_tolerance_adapter;
    optimization::ObjectivePolicy invalid_tolerance_policy;
    invalid_tolerance_policy.numerical.absolute_tolerance=
        std::numeric_limits<double>::quiet_NaN();
    const auto invalid_tolerance=build_hybrid_path_program(invalid_tolerance_adapter,
        example_system(),example_request(),example_path(),{"hybrid-problem"},
        {16,64,1024},invalid_tolerance_policy);
    REQUIRE(std::holds_alternative<Diagnostics>(invalid_tolerance));
    CHECK(std::get<Diagnostics>(invalid_tolerance).front().code==DiagnosticCode::invalid_input);
    CHECK(std::get<Diagnostics>(invalid_tolerance).front().field=="hybrid.adapter.objective_policy");
    CHECK(invalid_tolerance_adapter.calls==0);
    CHECK(invalid_tolerance_adapter.capability_calls==0);

    RejectingTrajectoryAdapter unknown_assurance_adapter;
    optimization::ObjectivePolicy unknown_assurance_policy;
    unknown_assurance_policy.assurance=static_cast<Assurance>(255);
    const auto unknown_assurance=build_hybrid_path_program(unknown_assurance_adapter,
        example_system(),example_request(),example_path(),{"hybrid-problem"},
        {16,64,1024},unknown_assurance_policy);
    REQUIRE(std::holds_alternative<Diagnostics>(unknown_assurance));
    CHECK(std::get<Diagnostics>(unknown_assurance).front().code==DiagnosticCode::invalid_input);
    CHECK(std::get<Diagnostics>(unknown_assurance).front().field=="hybrid.adapter.objective_policy");
    CHECK(unknown_assurance_adapter.calls==0);
    CHECK(unknown_assurance_adapter.capability_calls==0);
}

TEST_CASE("hybrid path builder stops if adapter capabilities request cancellation") {
    std::stop_source cancellation;
    CancellingCapabilityTrajectoryAdapter adapter{cancellation};
    const auto result=build_hybrid_path_program(adapter,example_system(),example_request(),
        example_path(),{"hybrid-problem"},{16,64,1024},{},cancellation.get_token());
    REQUIRE(std::holds_alternative<OperationStopped>(result));
    CHECK(std::get<OperationStopped>(result).reason==StopReason::cancelled);
    CHECK(adapter.calls==0);
}

TEST_CASE("hybrid path builder rejects an adapter result with mismatched branch identity") {
    MismatchingTrajectoryAdapter adapter;
    const auto result=build_hybrid_path_program(adapter,example_system(),example_request(),
        example_path(),{"hybrid-problem"},{16,64,1024});
    REQUIRE(std::holds_alternative<Diagnostics>(result));
    CHECK(std::get<Diagnostics>(result).front().field=="hybrid.adapter.path");
}

TEST_CASE("hybrid path builder rejects H relation rows omitted from adapter resource trace") {
    MismatchingTrajectoryAdapter adapter;
    adapter.append_redundant_row=true;
    const auto result=build_hybrid_path_program(adapter,example_system(),example_request(),
        example_path(),{"hybrid-extra-relation-row"},{16,64,1024});
    REQUIRE(std::holds_alternative<Diagnostics>(result));
    CHECK(std::get<Diagnostics>(result).front().code==DiagnosticCode::evidence_mismatch);
    CHECK(std::get<Diagnostics>(result).front().field==
        "hybrid.adapter.relation_resources");
}

TEST_CASE("hybrid path builder rejects a missing terminal objective before adapter dispatch") {
    auto request=example_request();
    request.terminal_objectives.clear();
    RejectingTrajectoryAdapter adapter;
    const auto result=build_hybrid_path_program(adapter,example_system(),request,
        example_path(),{"hybrid-problem"},{16,64,1024});
    REQUIRE(std::holds_alternative<Diagnostics>(result));
    CHECK(std::get<Diagnostics>(result).front().field=="hybrid.terminal_objectives");
    CHECK(adapter.calls==0);
}

TEST_CASE("hybrid path builder rejects a path that does not span the system horizon before dispatch") {
    auto request=example_request();
    request.allowed_terminal_modes={{"source"}};
    request.terminal_objectives={{{"source"},LinearTerminal{{1},0},"energy","J"}};
    RejectingTrajectoryAdapter adapter;
    const model::HybridPath short_path{{{"source"}},{}};
    const auto result=build_hybrid_path_program(adapter,example_system(),request,short_path,
        {"hybrid-problem"},{16,64,1024});
    REQUIRE(std::holds_alternative<Diagnostics>(result));
    CHECK(std::get<Diagnostics>(result).front().field=="hybrid.adapter.path");
    CHECK(adapter.calls==0);
}

TEST_CASE("hybrid path builder preserves pre-cancellation precedence over profile validation") {
    auto request=example_request();
    request.terminal_objectives.clear();
    std::stop_source source;
    source.request_stop();
    RejectingTrajectoryAdapter adapter;
    const auto result=build_hybrid_path_program(adapter,example_system(),request,example_path(),
        {"hybrid-problem"},{16,64,1024},{},source.get_token());
    REQUIRE(std::holds_alternative<OperationStopped>(result));
    CHECK(std::get<OperationStopped>(result).reason==StopReason::cancelled);
    CHECK(adapter.calls==0);
}

TEST_CASE("hybrid reachability boundary retains a branch-labelled joint relation") {
    JointHReachabilityAdapter adapter;
    const auto result=compute_hybrid_path_reachability(adapter,example_system(),example_request(),
        example_path(),{16,64,1024});
    REQUIRE(std::holds_alternative<HybridPathReachability>(result));
    const auto& reachable=std::get<HybridPathReachability>(result);
    CHECK(reachable.path==example_path());
    CHECK(reachable.assurance==Assurance::numerical);
    CHECK_FALSE(reachable.relation_operations.empty());
    CHECK(reachable.relation_limits.max_variables==16);
}

TEST_CASE("projected hybrid reachability returns the literal terminal interval and path relation") {
    auto [system,request]=projected_interval_fixture();
    const model::HybridPath path{{{"source"},{"target"}},{{"transition"}}};
    ProjectedStateHybridReachabilityAdapter adapter(16);
    const auto result=compute_hybrid_path_reachability(adapter,system,request,path,{4,16,128});
    REQUIRE(std::holds_alternative<HybridPathReachability>(result));
    const auto& reachable=std::get<HybridPathReachability>(result);
    REQUIRE(reachable.projected_state.has_value());
    const auto terminal=reachable.projected_state->terminal_state_set.representation();
    REQUIRE(std::holds_alternative<sets::HRepresentation>(terminal));
    const auto& terminal_h=std::get<sets::HRepresentation>(terminal);
    REQUIRE(terminal_h.inequalities.rows()>=2);
    bool has_upper=false,has_lower=false;
    for(std::size_t row=0;row<terminal_h.inequalities.rows();++row) {
        const auto coefficient=terminal_h.inequalities(row,0);
        const auto bound=terminal_h.upper_bounds[row];
        CHECK(bound>=0.5*coefficient);
        has_upper=has_upper || (coefficient>0.0 && bound/coefficient==0.5);
        if(coefficient<0.0) {
            CHECK(bound>=0.0);
            has_lower=has_lower || (bound/(-coefficient)==0.0);
        } else if(coefficient==0.0) CHECK(bound>=0.0);
    }
    CHECK(has_upper);
    CHECK(has_lower);
    CHECK(satisfies(terminal_h,{0.0}));
    CHECK(satisfies(terminal_h,{0.25}));
    CHECK(satisfies(terminal_h,{0.5}));
    CHECK_FALSE(satisfies(terminal_h,{-0.125}));
    CHECK_FALSE(satisfies(terminal_h,{0.625}));

    const auto relation=reachable.joint_relation.representation();
    REQUIRE(std::holds_alternative<sets::HRepresentation>(relation));
    const auto& relation_h=std::get<sets::HRepresentation>(relation);
    REQUIRE(relation_h.equalities.rows()==3);
    REQUIRE(relation_h.inequalities.rows()==4);
    const Matrix expected_equalities{3,4,{1,0,0,0,-1,-1,1,0,0,0,1,-1}};
    const Vector expected_equality_values{0,0,0};
    const Matrix expected_inequalities{4,4,{0,1,0,0,0,-1,0,0,0,0,1,0,0,0,-1,0}};
    const Vector expected_upper_bounds{1,0,0.5,0};
    for(std::size_t row=0;row<expected_equalities.rows;++row) {
        CHECK(relation_h.equality_values[row]==expected_equality_values[row]);
        for(std::size_t col=0;col<expected_equalities.cols;++col)
            CHECK(relation_h.equalities(row,col)==expected_equalities.values[row*expected_equalities.cols+col]);
    }
    for(std::size_t row=0;row<expected_inequalities.rows;++row) {
        CHECK(relation_h.upper_bounds[row]==expected_upper_bounds[row]);
        for(std::size_t col=0;col<expected_inequalities.cols;++col)
            CHECK(relation_h.inequalities(row,col)==expected_inequalities.values[row*expected_inequalities.cols+col]);
    }
    CHECK(satisfies(relation_h,{0.0,0.25,0.25,0.25}));
    CHECK_FALSE(satisfies(relation_h,{0.0,0.25,0.25,0.375}));
    CHECK(reachable.projected_state->input_rows==relation_h.inequalities.rows()+relation_h.equalities.rows());
    CHECK(reachable.projected_state->output_rows==terminal_h.inequalities.rows()+terminal_h.equalities.rows());
    CHECK(reachable.projected_state->maximum_projection_rows==16);
    CHECK(reachable.projected_state->projection_provider.actual->id.value=="csl.geometry.polyhedral-projection");

    auto shifted_request=request;
    shifted_request.initial.state[0]=0.25;
    ProjectedStateHybridReachabilityAdapter shifted_adapter(16);
    const auto shifted_result=compute_hybrid_path_reachability(shifted_adapter,
        system,shifted_request,path,{4,16,128});
    REQUIRE(std::holds_alternative<HybridPathReachability>(shifted_result));
    const auto& shifted=std::get<HybridPathReachability>(shifted_result);
    CHECK(shifted.joint_relation.metadata()->id!=reachable.joint_relation.metadata()->id);
    CHECK(shifted.projected_state->terminal_state_set.metadata()->id!=
        reachable.projected_state->terminal_state_set.metadata()->id);
    const auto shifted_h=std::get<sets::HRepresentation>(shifted.projected_state->terminal_state_set.representation());
    CHECK(satisfies(shifted_h,{0.25}));
    CHECK_FALSE(satisfies(shifted_h,{0.125}));

    auto negative_control=projected_interval_fixture();
    negative_control.first.modes[0].control_sets[0]=
        interval("projected-negative-control",-1.0,1.0);
    negative_control.first.edges[0].guards[0]=interval("projected-negative-guard",-0.5,0.5);
    ProjectedStateHybridReachabilityAdapter negative_adapter(16);
    const auto negative_result=compute_hybrid_path_reachability(negative_adapter,
        negative_control.first,negative_control.second,path,{4,16,128});
    REQUIRE(std::holds_alternative<HybridPathReachability>(negative_result));
    const auto negative_representation=
        std::get<HybridPathReachability>(negative_result).joint_relation.representation();
    const auto& negative_relation=std::get<sets::HRepresentation>(negative_representation);
    CHECK(satisfies(negative_relation,{0.0,-0.25,-0.25,-0.25}));

    auto scaled=projected_interval_fixture();
    scaled.first.modes[0].control_sets[0]=scaled_interval("projected-scaled-control",0.0,1.0,2.0);
    scaled.first.edges[0].guards[0]=scaled_interval("projected-scaled-guard",0.0,0.5,3.0);
    ProjectedStateHybridReachabilityAdapter scaled_adapter(16);
    const auto scaled_result=compute_hybrid_path_reachability(scaled_adapter,
        scaled.first,scaled.second,path,{4,16,128});
    REQUIRE(std::holds_alternative<HybridPathReachability>(scaled_result));
    const auto scaled_representation=
        std::get<HybridPathReachability>(scaled_result).projected_state->terminal_state_set.representation();
    const auto& scaled_terminal=std::get<sets::HRepresentation>(scaled_representation);
    CHECK(satisfies(scaled_terminal,{0.0}));
    CHECK(satisfies(scaled_terminal,{0.5}));
    CHECK_FALSE(satisfies(scaled_terminal,{0.625}));
}

TEST_CASE("projected hybrid reachability preflights a projection input exceeding its provider row limit") {
    auto [system,request]=projected_interval_fixture();
    const model::HybridPath path{{{"source"},{"target"}},{{"transition"}}};
    ProjectedStateHybridReachabilityAdapter adapter(1);
    const auto result=compute_hybrid_path_reachability(adapter,system,request,path,{4,16,128});
    REQUIRE(std::holds_alternative<Diagnostics>(result));
    CHECK(std::get<Diagnostics>(result).front().field=="hybrid.projected.row_limit");
}

TEST_CASE("general projected hybrid reachability projects the terminal state across a finite horizon") {
    auto [system,request]=projected_interval_fixture();
    auto reset=system.edges.front().reset_relations.front();
    auto first_guard=system.edges.front().guards.front();
    auto source=system.modes.front();
    auto target=system.modes.back();
    source.control_sets={interval("general-source-u0",0,1),UniversalSet{1}};
    source.invariants={UniversalSet{1},UniversalSet{1},UniversalSet{1}};
    auto middle=source;
    middle.id={"middle"};
    middle.control_coordinate_labels={"v"};
    middle.control_sets={UniversalSet{1},interval("general-middle-u1",0,0)};
    middle.flow=LinearStage{Matrix{1,1,{1}},Matrix{1,1,{1}},Matrix{1,0,{}},Vector{0}};
    target.control_sets={UniversalSet{0},UniversalSet{0}};
    target.invariants={UniversalSet{1},UniversalSet{1},UniversalSet{1}};
    system.horizon=2;
    system.modes={source,middle,target};
    system.edges={
        {{"first"},{"source"},{"middle"},{first_guard,UniversalSet{1}},{reset,reset}},
        {{"second"},{"middle"},{"target"},{UniversalSet{1},UniversalSet{1}},{reset,reset}}
    };
    request.allowed_terminal_modes={{"target"}};
    request.terminal_objectives={{{"target"},LinearTerminal{{1},0},"cost","u"}};
    const model::HybridPath path{{{"source"},{"middle"},{"target"}},{{"first"},{"second"}}};
    GeneralProjectedStateHybridReachabilityAdapter limited_adapter(1);
    const auto limited=compute_hybrid_path_reachability(limited_adapter,system,request,path,{16,64,1024});
    REQUIRE(std::holds_alternative<Diagnostics>(limited));
    CHECK(std::get<Diagnostics>(limited).front().field=="hybrid.projected.row_limit");

    GeneralProjectedStateHybridReachabilityAdapter adapter(64);
    const auto result=compute_hybrid_path_reachability(adapter,system,request,path,{16,64,1024});
    REQUIRE(std::holds_alternative<HybridPathReachability>(result));
    const auto& reachable=std::get<HybridPathReachability>(result);
    REQUIRE(reachable.projected_state.has_value());
    CHECK(reachable.path==path);
    CHECK(reachable.relation_operations.size()>=10);
    const auto terminal=reachable.projected_state->terminal_state_set.representation();
    REQUIRE(std::holds_alternative<sets::HRepresentation>(terminal));
    const auto& terminal_h=std::get<sets::HRepresentation>(terminal);
    CHECK(reachable.projected_state->terminal_state_set.metadata()->set.dimension==1);
    CHECK(satisfies(terminal_h,{0.0}));
    CHECK(satisfies(terminal_h,{0.25}));
    CHECK(satisfies(terminal_h,{0.5}));
    CHECK_FALSE(satisfies(terminal_h,{0.625}));
    const auto relation=reachable.joint_relation.representation();
    REQUIRE(std::holds_alternative<sets::HRepresentation>(relation));
    const auto& relation_h=std::get<sets::HRepresentation>(relation);
    CHECK(relation_h.equalities.rows()>=5);
    CHECK(satisfies(relation_h,{0.0,0.25,0.25,0.25,0.0,0.25,0.25}));
    CHECK(reachable.projected_state->input_rows==
        relation_h.inequalities.rows()+relation_h.equalities.rows());
}

TEST_CASE("general projected reachability preflights the geometry provider before workspace creation") {
    auto [system,request]=projected_interval_fixture();
    const model::HybridPath path{{{"source"},{"target"}},{{"transition"}}};
    auto admissions=std::make_shared<std::vector<std::pair<std::string,std::size_t>>>();
    auto workspace_creations=std::make_shared<int>(0);
    GeneralProjectedStateHybridReachabilityAdapter adapter(
        row_limited_projection_provider(1,admissions,workspace_creations),16);

    const auto result=compute_hybrid_path_reachability(adapter,system,request,path,{8,32,256});
    REQUIRE(std::holds_alternative<Diagnostics>(result));
    CHECK(std::get<Diagnostics>(result).front().field=="fixture.projection.preflight");
    REQUIRE(admissions->size()==1);
    CHECK(admissions->front().first.starts_with("terminal-state:"));
    CHECK(admissions->front().second>1);
    CHECK(*workspace_creations==0);
}

TEST_CASE("general projected preflight passes the peak-row cap to provider admission") {
    auto [system,request]=projected_interval_fixture();
    const model::HybridPath path{{{"source"},{"target"}},{{"transition"}}};
    auto admissions=std::make_shared<std::vector<std::pair<std::string,std::size_t>>>();
    auto workspace_creations=std::make_shared<int>(0);
    GeneralProjectedStateHybridReachabilityAdapter adapter(
        row_limited_projection_provider(64,admissions,workspace_creations,nullptr,
            nullptr,false,17),16);

    const auto result=compute_hybrid_path_reachability(adapter,system,request,path,{8,32,256});
    REQUIRE(std::holds_alternative<Diagnostics>(result));
    CHECK(std::get<Diagnostics>(result).front().field=="fixture.projection.preflight");
    REQUIRE(admissions->size()==1);
    CHECK(admissions->front().second<16);
    CHECK(*workspace_creations==0);
}

TEST_CASE("general projected preflight admits the actual labelled joint relation") {
    auto [system,request]=projected_interval_fixture();
    const model::HybridPath path{{{"source"},{"target"}},{{"transition"}}};
    auto admissions=std::make_shared<std::vector<std::pair<std::string,std::size_t>>>();
    auto workspace_creations=std::make_shared<int>(0);
    auto observed_actual_relation=std::make_shared<bool>(false);
    GeneralProjectedStateHybridReachabilityAdapter adapter(
        row_limited_projection_provider(64,admissions,workspace_creations,nullptr,
            observed_actual_relation,true),16);

    const std::array<model::HybridPath,1> paths{path};
    const auto operation_plan=model::plan_hybrid_operations(paths);
    const auto admitted=adapter.preflight(system,request,paths,{8,32,256},operation_plan,{});
    REQUIRE(std::holds_alternative<HybridOperationAdmissionSuccess>(admitted));
    REQUIRE(admissions->size()==1);
    CHECK(*observed_actual_relation);
    CHECK(admissions->front().first.starts_with("terminal-state:"));
    CHECK(*workspace_creations==0);
}

TEST_CASE("one-step projected reachability preflights the geometry provider before workspace creation") {
    auto [system,request]=projected_interval_fixture();
    const model::HybridPath path{{{"source"},{"target"}},{{"transition"}}};
    auto admissions=std::make_shared<std::vector<std::pair<std::string,std::size_t>>>();
    auto workspace_creations=std::make_shared<int>(0);
    ProjectedStateHybridReachabilityAdapter adapter(
        row_limited_projection_provider(1,admissions,workspace_creations),16);

    const auto result=compute_hybrid_path_reachability(adapter,system,request,path,{8,32,256});
    REQUIRE(std::holds_alternative<Diagnostics>(result));
    CHECK(std::get<Diagnostics>(result).front().field=="fixture.projection.preflight");
    REQUIRE(admissions->size()==1);
    CHECK(admissions->front().first.starts_with("terminal-state:"));
    CHECK(admissions->front().second==7);
    CHECK(*workspace_creations==0);
}

TEST_CASE("one-step projected preflight admits the actual labelled joint relation") {
    auto [system,request]=projected_interval_fixture();
    const model::HybridPath path{{{"source"},{"target"}},{{"transition"}}};
    auto admissions=std::make_shared<std::vector<std::pair<std::string,std::size_t>>>();
    auto workspace_creations=std::make_shared<int>(0);
    auto observed_actual_relation=std::make_shared<bool>(false);
    ProjectedStateHybridReachabilityAdapter adapter(
        row_limited_projection_provider(64,admissions,workspace_creations,nullptr,
            observed_actual_relation,true),16);

    const std::array<model::HybridPath,1> paths{path};
    const auto operation_plan=model::plan_hybrid_operations(paths);
    const auto admitted=adapter.preflight(system,request,paths,{8,32,256},operation_plan,{});
    REQUIRE(std::holds_alternative<HybridOperationAdmissionSuccess>(admitted));
    REQUIRE(admissions->size()==1);
    CHECK(*observed_actual_relation);
    CHECK(admissions->front().first.starts_with("terminal-state:"));
    CHECK(*workspace_creations==0);
}

TEST_CASE("one-step projected reachability honors cancellation during provider admission") {
    auto [system,request]=projected_interval_fixture();
    const model::HybridPath path{{{"source"},{"target"}},{{"transition"}}};
    auto admissions=std::make_shared<std::vector<std::pair<std::string,std::size_t>>>();
    auto workspace_creations=std::make_shared<int>(0);
    std::stop_source cancellation;
    ProjectedStateHybridReachabilityAdapter adapter(
        row_limited_projection_provider(64,admissions,workspace_creations,&cancellation),16);

    const auto result=compute_hybrid_path_reachability(adapter,system,request,path,{8,32,256},
        cancellation.get_token());
    REQUIRE(std::holds_alternative<OperationStopped>(result));
    CHECK(std::get<OperationStopped>(result).reason==StopReason::cancelled);
    REQUIRE(admissions->size()==1);
    CHECK(admissions->front().first.starts_with("terminal-state:"));
    CHECK(*workspace_creations==0);
}

TEST_CASE("general projected reachability honors cancellation during provider admission") {
    auto [system,request]=projected_interval_fixture();
    const model::HybridPath path{{{"source"},{"target"}},{{"transition"}}};
    auto admissions=std::make_shared<std::vector<std::pair<std::string,std::size_t>>>();
    auto workspace_creations=std::make_shared<int>(0);
    std::stop_source cancellation;
    GeneralProjectedStateHybridReachabilityAdapter adapter(
        row_limited_projection_provider(64,admissions,workspace_creations,&cancellation),16);

    const auto result=compute_hybrid_path_reachability(adapter,system,request,path,{8,32,256},
        cancellation.get_token());
    REQUIRE(std::holds_alternative<OperationStopped>(result));
    CHECK(std::get<OperationStopped>(result).reason==StopReason::cancelled);
    REQUIRE(admissions->size()==1);
    CHECK(admissions->front().first.starts_with("terminal-state:"));
    CHECK(*workspace_creations==0);
}

TEST_CASE("general projected hybrid reachability selects a dimension-changing terminal block") {
    const auto system=example_system();
    const auto request=example_request();
    const auto path=example_path();
    GeneralProjectedStateHybridReachabilityAdapter adapter(16);
    const auto result=compute_hybrid_path_reachability(adapter,system,request,path,{16,32,512});
    REQUIRE(std::holds_alternative<HybridPathReachability>(result));
    const auto& reachable=std::get<HybridPathReachability>(result);
    REQUIRE(reachable.projected_state.has_value());
    CHECK(reachable.joint_relation.metadata()->set.dimension==5);
    CHECK(reachable.projected_state->terminal_state_set.metadata()->set.dimension==2);
    const auto representation=reachable.projected_state->terminal_state_set.representation();
    REQUIRE(std::holds_alternative<sets::HRepresentation>(representation));
    const auto& projected=std::get<sets::HRepresentation>(representation);
    CHECK(satisfies(projected,{0.0,0.0}));
    CHECK(satisfies(projected,{11.0,-7.0}));
}

TEST_CASE("hybrid reachability boundary dispatches injected adapters and propagates rejection") {
    RejectingReachabilityAdapter adapter;
    const auto result=compute_hybrid_path_reachability(adapter,example_system(),example_request(),
        example_path(),{16,64,1024});
    REQUIRE(std::holds_alternative<model::HybridPathCompositionFailureReport>(result));
    const auto& failure=std::get<model::HybridPathCompositionFailureReport>(result);
    CHECK(failure.path==example_path());
    CHECK(std::get<Diagnostic>(failure.failure).field=="fixture.reachability");
    CHECK(adapter.calls==1);
}

TEST_CASE("hybrid reachability preflights unsupported relations and limits before adapter calls") {
    auto unsupported_system=example_system();
    unsupported_system.edges.front().guards.front()=vertex_guard("unsupported-reachability-guard");
    RejectingReachabilityAdapter unsupported_adapter;
    const auto unsupported=compute_hybrid_path_reachability(unsupported_adapter,
        unsupported_system,example_request(),example_path(),{16,64,1024});
    REQUIRE(std::holds_alternative<model::HybridPathCompositionFailureReport>(unsupported));
    const auto& unsupported_failure=
        std::get<model::HybridPathCompositionFailureReport>(unsupported);
    REQUIRE(std::holds_alternative<Diagnostic>(unsupported_failure.failure));
    CHECK(std::get<Diagnostic>(unsupported_failure.failure).field=="hybrid.guard.representation");
    CHECK(unsupported_adapter.capability_calls==0);
    CHECK(unsupported_adapter.calls==0);

    RejectingReachabilityAdapter limited_adapter;
    const auto limited=compute_hybrid_path_reachability(limited_adapter,example_system(),
        example_request(),example_path(),{1,64,1024});
    REQUIRE(std::holds_alternative<model::HybridPathCompositionFailureReport>(limited));
    const auto& limited_failure=std::get<model::HybridPathCompositionFailureReport>(limited);
    REQUIRE(std::holds_alternative<Diagnostic>(limited_failure.failure));
    CHECK(std::get<Diagnostic>(limited_failure.failure).field=="hybrid.relation.variables");
    CHECK(limited_adapter.capability_calls==0);
    CHECK(limited_adapter.calls==0);
}

TEST_CASE("reachability adapter default preflight fails closed before capability queries") {
    DefaultPreflightReachabilityAdapter adapter;
    const auto result=compute_hybrid_path_reachability(adapter,example_system(),
        example_request(),example_path(),{16,64,1024});
    REQUIRE(std::holds_alternative<Diagnostics>(result));
    CHECK(std::get<Diagnostics>(result).front().field=="hybrid.reachability.preflight");
    CHECK(adapter.capability_calls==0);
    CHECK(adapter.calls==0);
}

TEST_CASE("reachability boundary validates preflight failure path and limits") {
    for(const int corruption : {0,1}) {
        MisreportingReachabilityPreflightAdapter adapter;
        adapter.corruption=corruption;
        const auto result=compute_hybrid_path_reachability(adapter,example_system(),
            example_request(),example_path(),{16,64,1024});
        REQUIRE(std::holds_alternative<Diagnostics>(result));
        const auto& diagnostic=std::get<Diagnostics>(result).front();
        if(corruption==0) CHECK(diagnostic.field=="hybrid.reachability.preflight_path");
        else CHECK(diagnostic.field=="hybrid.reachability.preflight_limits");
        CHECK(diagnostic.code==DiagnosticCode::evidence_mismatch);
        CHECK(adapter.capability_calls==0);
        CHECK(adapter.calls==0);
    }
}

TEST_CASE("reachability boundary rejects incomplete or reordered operation admission receipts") {
    for(const int corruption:{1,2,3}) {
        MisreportingReachabilityAdapter adapter;
        adapter.admission_corruption=corruption;
        const auto result=compute_hybrid_path_reachability(adapter,example_system(),
            example_request(),example_path(),{16,64,1024});
        REQUIRE(std::holds_alternative<Diagnostics>(result));
        CHECK(std::get<Diagnostics>(result).front().field==
            "hybrid.reachability.preflight_operations");
        CHECK(adapter.capability_calls==0);
        CHECK(adapter.calls==0);
    }
}

TEST_CASE("reachability portfolio admits one complete model-wide operation plan") {
    auto [system,request]=variable_size_parallel_profile();
    MisreportingReachabilityAdapter adapter;
    adapter.corruption=5;
    const auto result=compute_hybrid_reachability_portfolio(adapter,system,request,
        {1,8},{16,64,1024});
    REQUIRE(std::holds_alternative<HybridReachabilityPortfolio>(result));
    const auto& portfolio=std::get<HybridReachabilityPortfolio>(result);
    REQUIRE(portfolio.branches.size()==3);
    CHECK(adapter.preflight_calls==1);
    CHECK(adapter.preflight_path_count==3);
    CHECK(adapter.preflight_plan_count==24);
    CHECK(adapter.capability_calls==1);
    CHECK(adapter.calls==3);
}

TEST_CASE("reachability boundary stops after a cancelling successful preflight") {
    std::stop_source cancellation;
    CancellingReachabilityPreflightAdapter adapter{cancellation};
    const auto result=compute_hybrid_path_reachability(adapter,example_system(),
        example_request(),example_path(),{16,64,1024},cancellation.get_token());
    REQUIRE(std::holds_alternative<OperationStopped>(result));
    CHECK(std::get<OperationStopped>(result).reason==StopReason::cancelled);
    CHECK(adapter.capability_calls==0);
    CHECK(adapter.calls==0);
}

TEST_CASE("hybrid reachability boundary rejects mismatched assurance and resource reports") {
    for(const int corruption : {0,1,2,3,4}) {
        MisreportingReachabilityAdapter adapter;
        adapter.corruption=corruption;
        const auto result=compute_hybrid_path_reachability(adapter,example_system(),example_request(),
            example_path(),{16,64,1024});
        REQUIRE(std::holds_alternative<Diagnostics>(result));
        const auto& field=std::get<Diagnostics>(result).front().field;
        if(corruption==0) CHECK(field=="hybrid.reachability.assurance");
        else if(corruption==1) CHECK(field=="hybrid.reachability.limits");
        else CHECK(field=="hybrid.adapter.operations");
    }
}

TEST_CASE("hybrid reachability rejects H relation rows omitted from adapter resource trace") {
    MisreportingReachabilityAdapter adapter;
    adapter.corruption=6;
    const auto result=compute_hybrid_path_reachability(adapter,example_system(),
        example_request(),example_path(),{16,64,1024});
    REQUIRE(std::holds_alternative<Diagnostics>(result));
    CHECK(std::get<Diagnostics>(result).front().code==DiagnosticCode::evidence_mismatch);
    CHECK(std::get<Diagnostics>(result).front().field==
        "hybrid.adapter.relation_resources");
    CHECK(adapter.capability_calls==1);
    CHECK(adapter.calls==1);
}

TEST_CASE("verifier preflight rejects an unsupported domain before relation construction") {
    OneStepScalarIntervalHybridFamilyVerifier verifier;
    RejectingTrajectoryAdapter trajectory;
    const auto result=build_hybrid_portfolio_programs_with_verifier(verifier,trajectory,
        example_system(),example_request(),{"preflight-rejected"},{1,8},{16,64,1024});
    REQUIRE(std::holds_alternative<Diagnostics>(result));
    const auto& admission_error=std::get<Diagnostics>(result).front();
    CHECK(admission_error.field=="hybrid.verification.scalar_interval_domain");
    CHECK(admission_error.explanation.find("stage 0 edge switch")!=std::string::npos);
    CHECK(trajectory.calls==0);

    model::HybridMode source{{"preflight-source"},1,1,{"x"},{"u"}};
    source.flow=LinearStage{Matrix{1,1,{1}},Matrix{1,1,{1}},Matrix{1,0,{}},Vector{0}};
    source.control_sets={interval("preflight-supported-control",0,1)};
    source.invariants={UniversalSet{1},UniversalSet{1}};
    model::HybridMode target{{"preflight-target"},1,1,{"x"},{"u"}};
    target.flow=LinearStage{Matrix{1,1,{1}},Matrix{1,1,{0}},Matrix{1,0,{}},Vector{0}};
    target.control_sets={Singleton{{0}}};
    target.invariants={UniversalSet{1},UniversalSet{1}};
    const auto inequalities=numeric::snapshot(Matrix{0,2,{}});
    const auto upper_bounds=numeric::snapshot_vector(Vector{});
    const auto equalities=numeric::snapshot(Matrix{1,2,{1,-1}});
    const auto equality_values=numeric::snapshot_vector(Vector{0});
    REQUIRE(std::holds_alternative<numeric::MatrixView>(inequalities));
    REQUIRE(std::holds_alternative<numeric::VectorView>(upper_bounds));
    REQUIRE(std::holds_alternative<numeric::MatrixView>(equalities));
    REQUIRE(std::holds_alternative<numeric::VectorView>(equality_values));
    const auto identity_data=sets::make_h({{"preflight-identity-reset"},2,{"pre","post"}},
        {std::get<numeric::MatrixView>(inequalities),std::get<numeric::VectorView>(upper_bounds),
         std::get<numeric::MatrixView>(equalities),std::get<numeric::VectorView>(equality_values)});
    REQUIRE(std::holds_alternative<sets::SetData>(identity_data));
    model::HybridSystem supported_system{1,{source,target},
        {{{"preflight-edge"},{"preflight-source"},{"preflight-target"},
          {interval("preflight-supported-guard",0,1)},
          {std::get<sets::SetData>(identity_data).as_handle()}}}};
    model::HybridRequest supported_request{{{"preflight-source"},{0}},{{"preflight-target"}},
        {{{"preflight-target"},LinearTerminal{{1},0},"terminal-state","units"}}};
    const auto accepted=build_hybrid_portfolio_programs_with_verifier(verifier,trajectory,
        supported_system,supported_request,{"preflight-accepted"},{1,8},{16,64,1024});
    REQUIRE(std::holds_alternative<Diagnostics>(accepted));
    CHECK(std::get<Diagnostics>(accepted).front().field=="fixture.hybrid_adapter");
    CHECK(trajectory.calls==1);

    auto [integral_system,integral_request]=exact_singleton_portfolio();
    ExactSingletonHybridFamilyVerifier exact_verifier;
    RejectingTrajectoryAdapter exact_trajectory;
    const auto exact_accepted=build_hybrid_portfolio_programs_with_verifier(exact_verifier,
        exact_trajectory,integral_system,integral_request,{"exact-preflight-accepted"},
        {1,8},{16,64,1024});
    REQUIRE(std::holds_alternative<Diagnostics>(exact_accepted));
    CHECK(std::get<Diagnostics>(exact_accepted).front().field=="fixture.hybrid_adapter");
    CHECK(exact_trajectory.calls==1);

    DefaultPreflightHybridFamilyVerifier default_verifier;
    RejectingTrajectoryAdapter default_trajectory;
    const auto default_rejected=build_hybrid_portfolio_programs_with_verifier(
        default_verifier,default_trajectory,supported_system,supported_request,
        {"default-preflight-rejected"},{1,8},{16,64,1024});
    REQUIRE(std::holds_alternative<Diagnostics>(default_rejected));
    CHECK(std::get<Diagnostics>(default_rejected).front().field=="hybrid.verification.preflight");
    CHECK(default_trajectory.calls==0);
}

TEST_CASE("standalone family verification admits the verifier before dispatch") {
    auto [system,request]=exact_singleton_portfolio();
    const auto built=build_hybrid_portfolio_programs(system,request,{"standalone-verifier-preflight"},
        {1,8},{32,128,4096});
    REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(built));

    FixtureHybridFamilyVerifier verifier;
    verifier.reject_preflight=true;
    const auto result=verify_hybrid_portfolio_family(verifier,system,request,
        std::get<std::vector<HybridPathProgram>>(built),{}, {1,8},{1e-10,1e-10});
    REQUIRE(std::holds_alternative<Diagnostics>(result));
    CHECK(std::get<Diagnostics>(result).front().field=="fixture.verifier.preflight");
    CHECK(verifier.capability_calls==0);
    CHECK(verifier.preflight_calls==1);
    CHECK(verifier.calls==0);

    FixtureHybridFamilyVerifier partial_receipt;
    partial_receipt.partial_operation_receipt=true;
    const auto receipt_rejected=verify_hybrid_portfolio_family(partial_receipt,system,request,
        std::get<std::vector<HybridPathProgram>>(built),{}, {1,8},{1e-10,1e-10});
    REQUIRE(std::holds_alternative<Diagnostics>(receipt_rejected));
    CHECK(std::get<Diagnostics>(receipt_rejected).front().field==
        "hybrid.verification.preflight_operations");
    CHECK(partial_receipt.capability_calls==0);
    CHECK(partial_receipt.preflight_calls==1);
    CHECK(partial_receipt.calls==0);
}

TEST_CASE("verifier preflight cancellation skips capabilities and dispatch") {
    auto [system,request]=exact_singleton_portfolio();
    const auto built=build_hybrid_portfolio_programs(system,request,{"verifier-cancel-preflight"},
        {1,8},{32,128,4096});
    REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(built));

    std::stop_source cancellation;
    FixtureHybridFamilyVerifier standalone;
    standalone.request_cancellation_after_preflight=&cancellation;
    const auto verified=verify_hybrid_portfolio_family(standalone,system,request,
        std::get<std::vector<HybridPathProgram>>(built),{}, {1,8},{1e-10,1e-10},
        cancellation.get_token());
    REQUIRE(std::holds_alternative<OperationStopped>(verified));
    CHECK(standalone.capability_calls==0);
    CHECK(standalone.calls==0);

    std::stop_source build_cancellation;
    FixtureHybridFamilyVerifier portfolio;
    portfolio.request_cancellation_after_preflight=&build_cancellation;
    RejectingTrajectoryAdapter trajectory;
    const auto constructed=build_hybrid_portfolio_programs_with_verifier(portfolio,trajectory,
        system,request,{"verifier-cancel-build"},{1,8},{32,128,4096},{},
        build_cancellation.get_token());
    REQUIRE(std::holds_alternative<OperationStopped>(constructed));
    CHECK(portfolio.capability_calls==0);
    CHECK(portfolio.calls==0);
    CHECK(trajectory.calls==0);
}

TEST_CASE("family verifier receives one complete model-wide operation plan") {
    auto [system,request]=variable_size_parallel_profile();
    const auto built=build_hybrid_portfolio_programs(system,request,{"verifier-plan-inventory"},
        {1,8},{16,64,1024});
    REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(built));

    FixtureHybridFamilyVerifier verifier;
    const auto verified=verify_hybrid_portfolio_family(verifier,system,request,
        std::get<std::vector<HybridPathProgram>>(built),{}, {1,8},{0,0});
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(verified));
    CHECK(verifier.preflight_calls==1);
    CHECK(verifier.preflight_path_count==3);
    CHECK(verifier.preflight_plan_count==24);
    CHECK(verifier.capability_calls==1);
    CHECK(verifier.calls==1);
}

TEST_CASE("portfolio preflights every path before constructing the first relation") {
    auto system=example_system();
    auto unsupported=system.edges.front();
    unsupported.id={"unsupported-switch"};
    unsupported.guards[0]=vertex_guard("unsupported-portfolio-guard");
    system.edges.push_back(std::move(unsupported));

    RejectingTrajectoryAdapter trajectory;
    const auto result=build_hybrid_portfolio_programs(trajectory,system,example_request(),
        {"portfolio-preflight"},{1,8},{16,64,1024});
    REQUIRE(std::holds_alternative<model::HybridPathCompositionFailureReport>(result));
    CHECK(std::get<model::HybridPathCompositionFailureReport>(result).path.edges[0].value==
        "unsupported-switch");
    CHECK(std::get<model::HybridPathCompositionFailureReport>(result).failure.index()==0);
    CHECK(std::get<Diagnostic>(std::get<model::HybridPathCompositionFailureReport>(result).failure).field==
        "hybrid.guard.representation");
    CHECK(std::get<Diagnostic>(std::get<model::HybridPathCompositionFailureReport>(result).failure).
        explanation.find("stage 0 edge unsupported-switch")!=std::string::npos);
    CHECK(trajectory.calls==0);
}

TEST_CASE("hybrid family verification adapter receives the exhaustive path inventory") {
    auto system=example_system();
    auto parallel=system.edges.front();
    parallel.id={"switch-parallel"};
    system.edges.push_back(std::move(parallel));
    auto built=build_hybrid_portfolio_programs(system,example_request(),{"hybrid-problem"},
        {1,8},{16,64,1024});
    REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(built));
    const auto& programs=std::get<std::vector<HybridPathProgram>>(built);
    FixtureHybridFamilyVerifier verifier;
    const auto result=verify_hybrid_portfolio_family(verifier,system,example_request(),programs,{},
        {1,8},{1e-8,1e-8});
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(result));
    const auto& report=std::get<HybridFamilyVerificationReport>(result);
    REQUIRE(report.enumerated_paths.size()==2);
    REQUIRE(report.branches.size()==2);
    CHECK(report.branches[0].path==programs[0].path);
    CHECK(report.branches[1].path==programs[1].path);
    CHECK(report.complete_family_coverage==HybridVerificationStatus::unsupported);
    CHECK(verifier.calls==1);
}

TEST_CASE("hybrid family verification rejects a duplicated edge path in the inventory") {
    auto system=example_system();
    auto parallel=system.edges.front();
    parallel.id={"switch-parallel"};
    system.edges.push_back(std::move(parallel));
    const auto request=example_request();
    auto built=build_hybrid_portfolio_programs(system,request,{"hybrid-problem"},
        {1,8},{16,64,1024});
    REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(built));
    auto programs=std::get<std::vector<HybridPathProgram>>(std::move(built));
    REQUIRE(programs.size()==2);
    CHECK(programs[0].path.modes==programs[1].path.modes);
    CHECK(programs[0].path.edges!=programs[1].path.edges);
    const std::vector<model::HybridPath> raw_graph_oracle{
        example_path(),{{{"source"},{"target"}},{{"switch-parallel"}}}};
    std::vector<model::HybridPath> actual_paths;
    for(const auto& program:programs) actual_paths.push_back(program.path);
    CHECK(actual_paths==raw_graph_oracle);

    // The raw graph has two parallel edge paths with the same mode sequence.
    // Duplicating one edge identity must not be accepted as coverage of both.
    programs[1].path=programs[0].path;
    FixtureHybridFamilyVerifier verifier;
    const auto result=verify_hybrid_portfolio_family(verifier,system,request,programs,{},
        {1,8},{1e-8,1e-8});
    REQUIRE(std::holds_alternative<Diagnostics>(result));
    CHECK(std::get<Diagnostics>(result).front().field=="hybrid.verification.program_path");
    CHECK(programs[0].path==programs[1].path);
    CHECK(verifier.calls==0);
}

TEST_CASE("hybrid family verification report only retains candidate providers from supplied faces") {
    auto system=example_system();
    auto parallel=system.edges.front();
    parallel.id={"switch-parallel"};
    system.edges.push_back(std::move(parallel));
    auto built=build_hybrid_portfolio_programs(system,example_request(),{"hybrid-problem"},
        {1,8},{16,64,1024});
    REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(built));
    const auto& programs=std::get<std::vector<HybridPathProgram>>(built);
    FixtureHybridFamilyVerifier verifier;
    verifier.inject_candidate_providers=true;
    const auto result=verify_hybrid_portfolio_family(verifier,system,example_request(),programs,{},
        {1,8},{1e-8,1e-8});
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(result));
    const auto& report=std::get<HybridFamilyVerificationReport>(result);
    REQUIRE(report.branches.size()==programs.size());
    for(const auto& branch:report.branches) CHECK(branch.candidate_providers.empty());
}

TEST_CASE("hybrid family verification rejects a missing program operation trace before dispatch") {
    auto system=example_system();
    auto built=build_hybrid_portfolio_programs(system,example_request(),{"hybrid-problem"},
        {1,8},{16,64,1024});
    REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(built));
    auto programs=std::get<std::vector<HybridPathProgram>>(std::move(built));
    programs[0].relation_operations.clear();
    FixtureHybridFamilyVerifier verifier;
    const auto result=verify_hybrid_portfolio_family(verifier,system,example_request(),programs,{},
        {1,8},{1e-8,1e-8});
    REQUIRE(std::holds_alternative<Diagnostics>(result));
    CHECK(std::get<Diagnostics>(result).front().field=="hybrid.adapter.operations");
    CHECK(verifier.calls==0);
}

TEST_CASE("hybrid family verification rejects missing inventory or report branches") {
    auto system=example_system();
    auto parallel=system.edges.front();
    parallel.id={"switch-parallel"};
    system.edges.push_back(std::move(parallel));
    auto built=build_hybrid_portfolio_programs(system,example_request(),{"hybrid-problem"},
        {1,8},{16,64,1024});
    REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(built));
    auto programs=std::get<std::vector<HybridPathProgram>>(built);
    FixtureHybridFamilyVerifier verifier;
    programs.pop_back();
    auto incomplete=verify_hybrid_portfolio_family(verifier,system,example_request(),programs,{},
        {1,8},{1e-8,1e-8});
    REQUIRE(std::holds_alternative<Diagnostics>(incomplete));
    CHECK(verifier.calls==0);
    programs=std::get<std::vector<HybridPathProgram>>(built);
    verifier.omit_last_branch=true;
    auto omitted=verify_hybrid_portfolio_family(verifier,system,example_request(),programs,{},
        {1,8},{1e-8,1e-8});
    REQUIRE(std::holds_alternative<Diagnostics>(omitted));
    CHECK(std::get<Diagnostics>(omitted).front().field=="hybrid.verification.report");
    CHECK(verifier.calls==1);
}

TEST_CASE("hybrid family verification rejects aggregates unsupported by branch evidence") {
    auto system=example_system();
    auto built=build_hybrid_portfolio_programs(system,example_request(),{"hybrid-problem"},
        {1,8},{16,64,1024});
    REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(built));
    FixtureHybridFamilyVerifier verifier;
    verifier.claim_established_aggregates=true;
    const auto result=verify_hybrid_portfolio_family(verifier,system,example_request(),
        std::get<std::vector<HybridPathProgram>>(built),{}, {1,8},{1e-8,1e-8});
    REQUIRE(std::holds_alternative<Diagnostics>(result));
    CHECK(std::get<Diagnostics>(result).front().field=="hybrid.verification.consistency");
}

TEST_CASE("hybrid family verification requires global optimum before complete coverage") {
    auto system=example_system();
    auto built=build_hybrid_portfolio_programs(system,example_request(),{"hybrid-problem"},
        {1,8},{16,64,1024});
    REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(built));
    FixtureHybridFamilyVerifier verifier;
    verifier.claim_coverage_only=true;
    const auto result=verify_hybrid_portfolio_family(verifier,system,example_request(),
        std::get<std::vector<HybridPathProgram>>(built),{}, {1,8},{1e-8,1e-8});
    REQUIRE(std::holds_alternative<Diagnostics>(result));
    CHECK(std::get<Diagnostics>(result).front().field=="hybrid.verification.consistency");
}

TEST_CASE("hybrid family verification rejects global optimum with no feasible optimal branch") {
    auto system=example_system();
    auto built=build_hybrid_portfolio_programs(system,example_request(),{"hybrid-problem"},
        {1,8},{16,64,1024});
    REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(built));
    FixtureHybridFamilyVerifier verifier;
    verifier.claim_established_aggregates=true;
    verifier.mark_all_branches_refuted=true;
    const auto result=verify_hybrid_portfolio_family(verifier,system,example_request(),
        std::get<std::vector<HybridPathProgram>>(built),{}, {1,8},{1e-8,1e-8});
    REQUIRE(std::holds_alternative<Diagnostics>(result));
    CHECK(std::get<Diagnostics>(result).front().field=="hybrid.verification.consistency");
}

TEST_CASE("exact singleton hybrid verifier independently retains every tied edge path") {
    auto [system,request]=exact_singleton_portfolio();
    auto built=build_hybrid_portfolio_programs(system,request,{"exact-hybrid"},
        {1,8},{32,128,4096});
    REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(built));
    const auto& programs=std::get<std::vector<HybridPathProgram>>(built);
    REQUIRE(programs.size()==3);
    const Vector point{2,1,3,0,0};
    std::vector<HybridPathOptimalFaceCandidate> candidates{
        exact_candidate(programs[0],point),exact_candidate(programs[1],point)};
    candidates[0].providers.push_back({"fixture LP",{"fixture.lp",std::string{"1.0"}},
        registry::Identity{{"fixture.lp"},"1.0"}});
    ExactSingletonHybridFamilyVerifier verifier;
    const auto result=verify_hybrid_portfolio_family(verifier,system,request,programs,candidates,
        {1,8},{1e-10,1e-10});
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(result));
    const auto& report=std::get<HybridFamilyVerificationReport>(result);
    CHECK(report.verifier_id=="csl.hybrid.exact-singleton");
    CHECK(report.global_objective_optimality==HybridVerificationStatus::established);
    CHECK(report.complete_family_coverage==HybridVerificationStatus::established);
    REQUIRE(report.branches.size()==3);
    CHECK(report.branches[0].feasibility==HybridVerificationStatus::established);
    CHECK(report.branches[0].objective_optimality==HybridVerificationStatus::established);
    CHECK(report.branches[0].continuous_coverage==HybridVerificationStatus::established);
    CHECK(report.branches[1].objective_optimality==HybridVerificationStatus::established);
    CHECK(report.branches[2].objective_optimality==HybridVerificationStatus::refuted);
    CHECK(report.branches[2].continuous_coverage==HybridVerificationStatus::established);
    for(std::size_t i=0;i<programs.size();++i) {
        CHECK(report.branches[i].relation_limits.max_variables==programs[i].relation_limits.max_variables);
        CHECK(report.branches[i].relation_limits.max_rows==programs[i].relation_limits.max_rows);
        CHECK(report.branches[i].relation_limits.max_matrix_elements==
            programs[i].relation_limits.max_matrix_elements);
        REQUIRE(report.branches[i].relation_operations.size()==programs[i].relation_operations.size());
        CHECK_FALSE(report.branches[i].relation_operations.empty());
        CHECK(report.branches[i].relation_operations.front().implementation_id==
            programs[i].relation_operations.front().implementation_id);
        CHECK(report.branches[i].relation_operations.front().cumulative_rows==
            programs[i].relation_operations.front().cumulative_rows);
    }
    REQUIRE(report.branches[0].candidate_providers.size()==1);
    CHECK(report.branches[0].candidate_providers[0].actual->id.value=="fixture.lp");
    CHECK(report.branches[0].candidate_providers[0].actual->version=="1.0");
    CHECK(report.branches[1].candidate_providers.empty());
    CHECK(report.branches[2].candidate_providers.empty());
}

TEST_CASE("independent one-step oracle matches exhaustive hybrid portfolio and tied optimum") {
    auto [system,request]=exact_singleton_portfolio();
    system.edges[1].reset_relations[0]=singleton_relation("oracle-reset-b",{3,0,1});
    system.edges.push_back({{"guard-exit"},{"source"},{"target"},{Singleton{{4}}},
        {singleton_relation("reset-guard-exit",{3,0,0})}});
    const auto oracle=enumerate_one_step_singleton_oracle(system,request);
    REQUIRE(oracle.size()==3);
    CHECK(oracle[0].path.edges[0].value=="tie-a");
    CHECK(oracle[0].joint_tuple==Vector{2,1,3,0,0});
    CHECK(oracle[0].objective==0);
    CHECK(oracle[1].path.edges[0].value=="tie-b");
    CHECK(oracle[1].joint_tuple==Vector{2,1,3,0,1});
    CHECK(oracle[1].objective==0);
    CHECK(oracle[2].path.edges[0].value=="worse");
    CHECK(oracle[2].joint_tuple==Vector{2,1,3,1,0});
    CHECK(oracle[2].objective==1);

    // Flow produces pre-reset state 3: one edge allows 3 while this parallel
    // outgoing edge requires 4, so the latter branch must be empty.
    CHECK(oracle[0].joint_tuple[2]==3);
    const auto built=build_hybrid_portfolio_programs(system,request,{"oracle-hybrid"},
        {1,8},{32,128,4096});
    REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(built));
    const auto& programs=std::get<std::vector<HybridPathProgram>>(built);
    REQUIRE(programs.size()==system.edges.size());
    std::vector<double> costs;
    for(std::size_t i=0;i<oracle.size();++i) {
        CHECK(programs[i].path==oracle[i].path);
        const auto representation=programs[i].joint_relation.representation();
        REQUIRE(std::holds_alternative<sets::HRepresentation>(representation));
        const auto& h=std::get<sets::HRepresentation>(representation);
        CHECK(satisfies(h,oracle[i].joint_tuple));
        CHECK(equality_rows_have_full_column_rank(h.equalities));
        const auto& linear=std::get<LinearProgram>(programs[i].program);
        costs.push_back(linear.offset());
        for(std::size_t j=0;j<linear.objective().size();++j)
            costs.back()+=linear.objective()[j]*oracle[i].joint_tuple[j];
        CHECK(costs.back()==oracle[i].objective);
    }
    CHECK(programs.back().path.edges==std::vector<model::HybridEdgeId>{{"guard-exit"}});
    const auto rejected_representation=programs.back().joint_relation.representation();
    REQUIRE(std::holds_alternative<sets::HRepresentation>(rejected_representation));
    CHECK(has_conflicting_equalities(std::get<sets::HRepresentation>(rejected_representation)));

    // With the same edge guard (pre-state 3), changing the initial state to 3
    // makes the affine flow produce 4 and the branch exits that guard.
    auto exiting_request=request;
    exiting_request.initial.state={3};
    auto exiting_system=system;
    exiting_system.edges.resize(1);
    exiting_system.edges[0].reset_relations[0]=singleton_relation("reset-exiting-flow",{4,0,0});
    const model::HybridPath entering_edge{{{"source"},{"target"}},{{"tie-a"}}};
    CHECK(enumerate_one_step_singleton_oracle(exiting_system,exiting_request).empty());
    const auto exiting=build_hybrid_path_program(exiting_system,exiting_request,entering_edge,
        {"oracle-guard-exit"},{32,128,4096});
    REQUIRE(std::holds_alternative<HybridPathProgram>(exiting));
    const auto exiting_relation=std::get<HybridPathProgram>(exiting).joint_relation.representation();
    REQUIRE(std::holds_alternative<sets::HRepresentation>(exiting_relation));
    CHECK(has_conflicting_equalities(std::get<sets::HRepresentation>(exiting_relation)));

    const auto minimum=std::min_element(oracle.begin(),oracle.end(),[](const auto& left,const auto& right) {
        return left.objective<right.objective;
    })->objective;
    std::vector<std::string> oracle_optima;
    for(const auto& branch:oracle) if(branch.objective==minimum)
        oracle_optima.push_back(branch.path.edges[0].value);
    CHECK(oracle_optima==std::vector<std::string>{"tie-a","tie-b"});
}

TEST_CASE("independent two-stage oracle checks every edge history and tied mode sequence") {
    model::HybridMode first{{"first"},1,1,{"x"},{"u"}};
    first.flow=std::vector<LinearStage>{
        {Matrix{1,1,{1}},Matrix{1,1,{1}},Matrix{1,0,{}},Vector{1}},
        {Matrix{1,1,{1}},Matrix{1,1,{1}},Matrix{1,0,{}},Vector{1}}};
    first.control_sets={Singleton{{0}},Singleton{{0}}};
    first.invariants={UniversalSet{1},UniversalSet{1},UniversalSet{1}};
    model::HybridMode middle{{"middle"},1,1,{"y"},{"v"}};
    middle.flow=std::vector<LinearStage>{
        {Matrix{1,1,{1}},Matrix{1,1,{1}},Matrix{1,0,{}},Vector{0}},
        {Matrix{1,1,{1}},Matrix{1,1,{1}},Matrix{1,0,{}},Vector{0}}};
    middle.control_sets={Singleton{{0}},Singleton{{0}}};
    middle.invariants={UniversalSet{1},UniversalSet{1},UniversalSet{1}};
    model::HybridMode terminal{{"terminal"},1,0,{"z"},{}};
    terminal.flow=LinearStage{Matrix{1,1,{1}},Matrix{1,0,{}},Matrix{1,0,{}},Vector{0}};
    terminal.control_sets={UniversalSet{0},UniversalSet{0}};
    terminal.invariants={UniversalSet{1},UniversalSet{1},UniversalSet{1}};
    const auto reset_to_middle=[](std::string id) {
        return singleton_relation(std::move(id),{1,1});
    };
    const auto reset_to_terminal=[](std::string id,double post) {
        return singleton_relation(std::move(id),{1,post});
    };
    model::HybridSystem system{2,{first,middle,terminal},
        {{{"first-a"},{"first"},{"middle"},{Singleton{{1}},Singleton{{1}}},
            {reset_to_middle("first-a-reset-0"),reset_to_middle("first-a-reset-1")}},
         {{"first-b"},{"first"},{"middle"},{Singleton{{1}},Singleton{{1}}},
            {reset_to_middle("first-b-reset-0"),reset_to_middle("first-b-reset-1")}},
         {{"second-a"},{"middle"},{"terminal"},{Singleton{{1}},Singleton{{1}}},
            {reset_to_terminal("second-a-reset-0",0),reset_to_terminal("second-a-reset-1",0)}},
         {{"second-b"},{"middle"},{"terminal"},{Singleton{{1}},Singleton{{1}}},
            {reset_to_terminal("second-b-reset-0",2),reset_to_terminal("second-b-reset-1",2)}}}};
    model::HybridRequest request{{{"first"},{0}},{{"terminal"}},
        {{{"terminal"},LinearTerminal{{1},0},"terminal-cost","J"}}};

    // This oracle traverses the raw edge graph at each stage and directly
    // evaluates the singleton controls, affine flows, guards, resets, and
    // terminal costs. It does not call the production path enumerator,
    // composer, or verifier.
    struct OracleBranch { model::HybridPath path; Vector tuple; double cost; };
    std::vector<OracleBranch> oracle;
    const auto* first_flow=std::get_if<std::vector<LinearStage>>(&first.flow);
    REQUIRE(first_flow!=nullptr);
    for(const auto& first_edge:system.edges) {
        if(first_edge.source!=request.initial.mode) continue;
        const auto& initial_control=std::get<Singleton>(first.control_sets[0]).point;
        const auto& first_stage=(*first_flow)[0];
        const double first_pre=first_stage.A.values[0]*request.initial.state[0]+
            first_stage.B.values[0]*initial_control[0]+first_stage.offset[0];
        if(std::get<Singleton>(first_edge.guards[0]).point[0]!=first_pre) continue;
        const auto first_reset_data=sets::from_handle(first_edge.reset_relations[0]);
        REQUIRE(std::holds_alternative<sets::SetData>(first_reset_data));
        const auto first_reset=std::get<sets::SetData>(first_reset_data).representation();
        REQUIRE(std::holds_alternative<sets::SingletonRepresentation>(first_reset));
        const auto& first_reset_point=std::get<sets::SingletonRepresentation>(first_reset).point;
        if(first_reset_point[0]!=first_pre) continue;
        const double middle_state=first_reset_point[1];
        for(const auto& second_edge:system.edges) {
            if(second_edge.source!=first_edge.target||
               std::find(request.allowed_terminal_modes.begin(),request.allowed_terminal_modes.end(),
                   second_edge.target)==request.allowed_terminal_modes.end()) continue;
            const auto& middle_control=std::get<Singleton>(middle.control_sets[1]).point;
            const auto& second_flow=std::get<std::vector<LinearStage>>(middle.flow)[1];
            const double second_pre=second_flow.A.values[0]*middle_state+
                second_flow.B.values[0]*middle_control[0]+second_flow.offset[0];
            if(std::get<Singleton>(second_edge.guards[1]).point[0]!=second_pre) continue;
            const auto second_reset_data=sets::from_handle(second_edge.reset_relations[1]);
            REQUIRE(std::holds_alternative<sets::SetData>(second_reset_data));
            const auto second_reset=std::get<sets::SetData>(second_reset_data).representation();
            REQUIRE(std::holds_alternative<sets::SingletonRepresentation>(second_reset));
            const auto& second_reset_point=std::get<sets::SingletonRepresentation>(second_reset).point;
            if(second_reset_point[0]!=second_pre) continue;
            const double terminal_state=second_reset_point[1];
            oracle.push_back({{{request.initial.mode,first_edge.target,second_edge.target},
                {first_edge.id,second_edge.id}},
                {request.initial.state[0],initial_control[0],first_pre,middle_state,
                 middle_control[0],second_pre,terminal_state},terminal_state});
        }
    }
    REQUIRE(oracle.size()==4);
    CHECK((oracle[0].path.edges==std::vector<model::HybridEdgeId>{{"first-a"},{"second-a"}}));
    CHECK(oracle[0].tuple==Vector{0,0,1,1,0,1,0});
    CHECK(oracle[0].cost==0);
    CHECK((oracle[1].path.edges==std::vector<model::HybridEdgeId>{{"first-a"},{"second-b"}}));
    CHECK(oracle[1].tuple==Vector{0,0,1,1,0,1,2});
    CHECK(oracle[1].cost==2);
    CHECK((oracle[2].path.edges==std::vector<model::HybridEdgeId>{{"first-b"},{"second-a"}}));
    CHECK(oracle[2].tuple==Vector{0,0,1,1,0,1,0});
    CHECK(oracle[2].cost==0);
    CHECK((oracle[3].path.edges==std::vector<model::HybridEdgeId>{{"first-b"},{"second-b"}}));
    CHECK(oracle[3].tuple==Vector{0,0,1,1,0,1,2});
    CHECK(oracle[3].cost==2);

    const auto built=build_hybrid_portfolio_programs(system,request,{"two-stage-oracle"},
        {2,16},{32,256,8192});
    REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(built));
    const auto& programs=std::get<std::vector<HybridPathProgram>>(built);
    REQUIRE(programs.size()==oracle.size());
    std::vector<bool> matched_oracle(oracle.size(),false);
    for(std::size_t i=0;i<oracle.size();++i) {
        const auto expected=std::find_if(oracle.begin(),oracle.end(),[&](const auto& branch) {
            return branch.path==programs[i].path;
        });
        REQUIRE(expected!=oracle.end());
        const auto oracle_index=static_cast<std::size_t>(std::distance(oracle.begin(),expected));
        REQUIRE_FALSE(matched_oracle[oracle_index]);
        matched_oracle[oracle_index]=true;
        const auto representation=programs[i].joint_relation.representation();
        REQUIRE(std::holds_alternative<sets::HRepresentation>(representation));
        const auto& h=std::get<sets::HRepresentation>(representation);
        CHECK(satisfies(h,expected->tuple));
        CHECK(equality_rows_have_full_column_rank(h.equalities));
        const auto& program=std::get<LinearProgram>(programs[i].program);
        double cost=program.offset();
        for(std::size_t j=0;j<program.objective().size();++j)
            cost+=program.objective()[j]*expected->tuple[j];
        CHECK(cost==expected->cost);
    }
    CHECK(std::all_of(matched_oracle.begin(),matched_oracle.end(),[](bool matched) { return matched; }));
    const auto minimum=std::min_element(oracle.begin(),oracle.end(),[](const auto& left,const auto& right) {
        return left.cost<right.cost;
    })->cost;
    std::vector<model::HybridPath> optimal_paths;
    for(const auto& branch:oracle) if(branch.cost==minimum) optimal_paths.push_back(branch.path);
    REQUIRE(optimal_paths.size()==2);
    CHECK(optimal_paths[0].modes==optimal_paths[1].modes);
    CHECK(optimal_paths[0].edges!=optimal_paths[1].edges);
    CHECK(optimal_paths[0].edges[0].value=="first-a");
    CHECK(optimal_paths[1].edges[0].value=="first-b");
}

TEST_CASE("independent interval oracle matches the full continuous hybrid branch") {
    model::HybridMode source{{"source"},1,1,{"x"},{"u"}};
    source.flow=LinearStage{Matrix{1,1,{1}},Matrix{1,1,{1}},Matrix{1,0,{}},Vector{0}};
    source.control_sets={interval("oracle-control",0,1)};
    source.invariants={UniversalSet{1},UniversalSet{1}};
    model::HybridMode target{{"target"},1,0,{"y"},{}};
    target.flow=LinearStage{Matrix{1,1,{1}},Matrix{1,0,{}},Matrix{1,0,{}},Vector{0}};
    target.control_sets={UniversalSet{0}};
    target.invariants={UniversalSet{1},UniversalSet{1}};
    auto reset_equalities=numeric::snapshot(Matrix{1,2,{-1,1}});
    auto reset_rhs=numeric::snapshot_vector(Vector{0});
    auto reset_inequalities=numeric::snapshot(Matrix{0,2,{}});
    auto reset_bounds=numeric::snapshot_vector(Vector{});
    REQUIRE(std::holds_alternative<numeric::MatrixView>(reset_equalities));
    REQUIRE(std::holds_alternative<numeric::VectorView>(reset_rhs));
    REQUIRE(std::holds_alternative<numeric::MatrixView>(reset_inequalities));
    REQUIRE(std::holds_alternative<numeric::VectorView>(reset_bounds));
    auto reset_data=sets::make_h({{"oracle-identity-reset"},2,{}},
        {std::get<numeric::MatrixView>(reset_inequalities),std::get<numeric::VectorView>(reset_bounds),
         std::get<numeric::MatrixView>(reset_equalities),std::get<numeric::VectorView>(reset_rhs)});
    REQUIRE(std::holds_alternative<sets::SetData>(reset_data));
    model::HybridSystem system{1,{source,target},
        {{{"switch-wide"},{"source"},{"target"},{interval("oracle-guard-wide",0,0.5)},
          {std::get<sets::SetData>(reset_data).as_handle()}},
         {{"switch-narrow"},{"source"},{"target"},{interval("oracle-guard-narrow",0,0.25)},
          {std::get<sets::SetData>(reset_data).as_handle()}}}};
    model::HybridRequest request{{{"source"},{0}},{{"target"}},
        {{{"target"},LinearTerminal{{0},0},"cost","u"}}};

    // Both paths minimize the same constant objective. Their exact optimal
    // joint relations are (0,t,t,t), with 0<=t<=1/2 and 0<=t<=1/4.
    const std::vector<model::HybridPath> oracle_paths{
        {{{"source"},{"target"}},{{"switch-wide"}}},
        {{{"source"},{"target"}},{{"switch-narrow"}}}};
    const auto built=build_hybrid_portfolio_programs(system,request,{"continuous-oracle"},
        {1,8},{32,128,4096});
    REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(built));
    const auto& programs=std::get<std::vector<HybridPathProgram>>(built);
    REQUIRE(programs.size()==oracle_paths.size());

    auto check_branch=[&](const HybridPathProgram& branch,const model::HybridPath& expected_path,
        double expected_upper) {
        CHECK(branch.path==expected_path);
        const auto representation=branch.joint_relation.representation();
        REQUIRE(std::holds_alternative<sets::HRepresentation>(representation));
        const auto& h=std::get<sets::HRepresentation>(representation);
        REQUIRE(h.equalities.cols()==4);
        CHECK(equality_rank(h.equalities)==3);
        CHECK(satisfies(h,{0,0,0,0}));
        CHECK(satisfies(h,{0,expected_upper,expected_upper,expected_upper}));

        double lower=-std::numeric_limits<double>::infinity();
        double upper=std::numeric_limits<double>::infinity();
        for(std::size_t row=0;row<h.inequalities.rows();++row) {
            const double intercept=0;
            const double slope=h.inequalities(row,1)+h.inequalities(row,2)+h.inequalities(row,3);
            if(slope>0) upper=std::min(upper,(h.upper_bounds[row]-intercept)/slope);
            else if(slope<0) lower=std::max(lower,(h.upper_bounds[row]-intercept)/slope);
            else CHECK(intercept<=h.upper_bounds[row]);
        }
        CHECK(lower==0);
        CHECK(upper==expected_upper);
        const auto& program=std::get<LinearProgram>(branch.program);
        CHECK(program.objective().size()==4);
        CHECK(program.offset()==0);
        CHECK(program.objective()[0]==0);
        CHECK(program.objective()[1]==0);
        CHECK(program.objective()[2]==0);
        CHECK(program.objective()[3]==0);
    };
    check_branch(programs[0],oracle_paths[0],0.5);
    check_branch(programs[1],oracle_paths[1],0.25);
}

TEST_CASE("one-step scalar interval verifier certifies distinct tied continuous branches") {
    model::HybridMode source{{"source"},1,1,{"x"},{"u"}};
    source.flow=LinearStage{Matrix{1,1,{1}},Matrix{1,1,{1}},Matrix{1,0,{}},Vector{0}};
    source.control_sets={interval("verifier-control",0,1)};
    source.invariants={UniversalSet{1},UniversalSet{1}};
    model::HybridMode target{{"target"},1,0,{"y"},{}};
    target.flow=LinearStage{Matrix{1,1,{1}},Matrix{1,0,{}},Matrix{1,0,{}},Vector{0}};
    target.control_sets={UniversalSet{0}};
    target.invariants={UniversalSet{1},UniversalSet{1}};
    auto reset_equalities=numeric::snapshot(Matrix{1,2,{-1,1}});
    auto reset_rhs=numeric::snapshot_vector(Vector{0});
    auto reset_inequalities=numeric::snapshot(Matrix{0,2,{}});
    auto reset_bounds=numeric::snapshot_vector(Vector{});
    REQUIRE(std::holds_alternative<numeric::MatrixView>(reset_equalities));
    REQUIRE(std::holds_alternative<numeric::VectorView>(reset_rhs));
    REQUIRE(std::holds_alternative<numeric::MatrixView>(reset_inequalities));
    REQUIRE(std::holds_alternative<numeric::VectorView>(reset_bounds));
    auto reset=sets::make_h({{"verifier-identity-reset"},2,{}},
        {std::get<numeric::MatrixView>(reset_inequalities),std::get<numeric::VectorView>(reset_bounds),
         std::get<numeric::MatrixView>(reset_equalities),std::get<numeric::VectorView>(reset_rhs)});
    REQUIRE(std::holds_alternative<sets::SetData>(reset));
    auto system=model::HybridSystem{1,{source,target},
        {{{"wide"},{"source"},{"target"},{interval("verifier-wide-guard",0,0.5)},
            {std::get<sets::SetData>(reset).as_handle()}},
         {{"narrow"},{"source"},{"target"},{interval("verifier-narrow-guard",0,0.25)},
            {std::get<sets::SetData>(reset).as_handle()}}}};
    auto request=model::HybridRequest{{{"source"},{0}},{{"target"}},
        {{{"target"},LinearTerminal{{0},0},"cost","u"}}};
    const auto built=build_hybrid_portfolio_programs(system,request,{"interval-family-verifier"},
        {1,8},{32,128,4096});
    REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(built));
    const auto& programs=std::get<std::vector<HybridPathProgram>>(built);
    REQUIRE(programs.size()==2);
    std::vector<HybridPathOptimalFaceCandidate> candidates{
        exact_candidate(programs[0],{0,0,0,0}),exact_candidate(programs[1],{0,0,0,0})};
    OneStepScalarIntervalHybridFamilyVerifier verifier;
    const auto capabilities=verifier.capabilities();
    CHECK(capabilities.checks_original_hybrid_feasibility);
    CHECK(capabilities.checks_global_objective_optimality);
    CHECK(capabilities.checks_continuous_branch_coverage);
    CHECK(capabilities.assurance==Assurance::numerical);
    const auto result=verify_hybrid_portfolio_family(verifier,system,request,programs,candidates,
        {1,8},{1e-10,1e-10});
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(result));
    const auto& report=std::get<HybridFamilyVerificationReport>(result);
    CHECK(report.verifier_id=="csl.hybrid.one-step-scalar-interval");
    CHECK(report.global_objective_optimality==HybridVerificationStatus::established);
    CHECK(report.complete_family_coverage==HybridVerificationStatus::established);
    REQUIRE(report.branches.size()==2);
    for(const auto& branch:report.branches) {
        CHECK(branch.feasibility==HybridVerificationStatus::established);
        CHECK(branch.objective_optimality==HybridVerificationStatus::established);
        CHECK(branch.continuous_coverage==HybridVerificationStatus::established);
    }

    auto affine_reset_equalities=numeric::snapshot(Matrix{1,2,{-2,1}});
    auto affine_reset_rhs=numeric::snapshot_vector(Vector{1});
    REQUIRE(std::holds_alternative<numeric::MatrixView>(affine_reset_equalities));
    REQUIRE(std::holds_alternative<numeric::VectorView>(affine_reset_rhs));
    auto affine_reset=sets::make_h({{"verifier-affine-reset"},2,{}},
        {std::get<numeric::MatrixView>(reset_inequalities),
         std::get<numeric::VectorView>(reset_bounds),
         std::get<numeric::MatrixView>(affine_reset_equalities),
         std::get<numeric::VectorView>(affine_reset_rhs)});
    REQUIRE(std::holds_alternative<sets::SetData>(affine_reset));
    auto affine_reset_system=system;
    affine_reset_system.modes[1].invariants[1]=interval("verifier-affine-reset-target",1,2);
    for(auto& edge:affine_reset_system.edges)
        edge.reset_relations[0]=std::get<sets::SetData>(affine_reset).as_handle();
    const auto affine_reset_built=build_hybrid_portfolio_programs(affine_reset_system,request,
        {"affine-reset-interval-verifier"},{1,8},{32,128,4096});
    REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(affine_reset_built));
    const auto& affine_reset_programs=std::get<std::vector<HybridPathProgram>>(affine_reset_built);
    std::vector<HybridPathOptimalFaceCandidate> affine_reset_candidates{
        exact_candidate(affine_reset_programs[0],{0,0,0,1}),
        exact_candidate(affine_reset_programs[1],{0,0,0,1})};
    const auto affine_reset_result=verify_hybrid_portfolio_family(verifier,affine_reset_system,
        request,affine_reset_programs,affine_reset_candidates,{1,8},{1e-10,1e-10});
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(affine_reset_result));
    CHECK(std::get<HybridFamilyVerificationReport>(affine_reset_result).complete_family_coverage==
        HybridVerificationStatus::established);

    auto negative_reset_equalities=numeric::snapshot(Matrix{1,2,{2,1}});
    auto negative_reset_rhs=numeric::snapshot_vector(Vector{1});
    REQUIRE(std::holds_alternative<numeric::MatrixView>(negative_reset_equalities));
    REQUIRE(std::holds_alternative<numeric::VectorView>(negative_reset_rhs));
    auto negative_reset=sets::make_h({{"verifier-negative-affine-reset"},2,{}},
        {std::get<numeric::MatrixView>(reset_inequalities),
         std::get<numeric::VectorView>(reset_bounds),
         std::get<numeric::MatrixView>(negative_reset_equalities),
         std::get<numeric::VectorView>(negative_reset_rhs)});
    REQUIRE(std::holds_alternative<sets::SetData>(negative_reset));
    auto negative_reset_system=system;
    negative_reset_system.modes[1].invariants[1]=interval("verifier-negative-reset-target",0,1);
    for(auto& edge:negative_reset_system.edges)
        edge.reset_relations[0]=std::get<sets::SetData>(negative_reset).as_handle();
    const auto negative_reset_built=build_hybrid_portfolio_programs(negative_reset_system,request,
        {"negative-affine-reset-verifier"},{1,8},{32,128,4096});
    REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(negative_reset_built));
    const auto& negative_reset_programs=std::get<std::vector<HybridPathProgram>>(negative_reset_built);
    std::vector<HybridPathOptimalFaceCandidate> negative_reset_candidates{
        exact_candidate(negative_reset_programs[0],{0,0,0,1}),
        exact_candidate(negative_reset_programs[1],{0,0,0,1})};
    const auto negative_reset_result=verify_hybrid_portfolio_family(verifier,negative_reset_system,
        request,negative_reset_programs,negative_reset_candidates,{1,8},{1e-10,1e-10});
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(negative_reset_result));
    CHECK(std::get<HybridFamilyVerificationReport>(negative_reset_result).complete_family_coverage==
        HybridVerificationStatus::established);

    auto constant_reset_equalities=numeric::snapshot(Matrix{1,2,{0,1}});
    auto constant_reset_rhs=numeric::snapshot_vector(Vector{1});
    REQUIRE(std::holds_alternative<numeric::MatrixView>(constant_reset_equalities));
    REQUIRE(std::holds_alternative<numeric::VectorView>(constant_reset_rhs));
    auto constant_reset=sets::make_h({{"verifier-constant-affine-reset"},2,{}},
        {std::get<numeric::MatrixView>(reset_inequalities),
         std::get<numeric::VectorView>(reset_bounds),
         std::get<numeric::MatrixView>(constant_reset_equalities),
         std::get<numeric::VectorView>(constant_reset_rhs)});
    REQUIRE(std::holds_alternative<sets::SetData>(constant_reset));
    auto constant_reset_system=system;
    constant_reset_system.modes[1].invariants[1]=interval("verifier-constant-reset-target",1,1);
    for(auto& edge:constant_reset_system.edges)
        edge.reset_relations[0]=std::get<sets::SetData>(constant_reset).as_handle();
    const auto constant_reset_built=build_hybrid_portfolio_programs(constant_reset_system,request,
        {"constant-affine-reset-verifier"},{1,8},{32,128,4096});
    REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(constant_reset_built));
    const auto& constant_reset_programs=std::get<std::vector<HybridPathProgram>>(constant_reset_built);
    std::vector<HybridPathOptimalFaceCandidate> constant_reset_candidates{
        exact_candidate(constant_reset_programs[0],{0,0,0,1}),
        exact_candidate(constant_reset_programs[1],{0,0,0,1})};
    const auto constant_reset_result=verify_hybrid_portfolio_family(verifier,constant_reset_system,
        request,constant_reset_programs,constant_reset_candidates,{1,8},{1e-10,1e-10});
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(constant_reset_result));
    CHECK(std::get<HybridFamilyVerificationReport>(constant_reset_result).complete_family_coverage==
        HybridVerificationStatus::established);

    auto inexact_reset_equalities=numeric::snapshot(Matrix{1,2,{-1,3}});
    auto inexact_reset_rhs=numeric::snapshot_vector(Vector{0});
    REQUIRE(std::holds_alternative<numeric::MatrixView>(inexact_reset_equalities));
    REQUIRE(std::holds_alternative<numeric::VectorView>(inexact_reset_rhs));
    auto inexact_reset=sets::make_h({{"verifier-inexact-affine-reset"},2,{}},
        {std::get<numeric::MatrixView>(reset_inequalities),
         std::get<numeric::VectorView>(reset_bounds),
         std::get<numeric::MatrixView>(inexact_reset_equalities),
         std::get<numeric::VectorView>(inexact_reset_rhs)});
    REQUIRE(std::holds_alternative<sets::SetData>(inexact_reset));
    auto inexact_reset_system=system;
    for(auto& edge:inexact_reset_system.edges)
        edge.reset_relations[0]=std::get<sets::SetData>(inexact_reset).as_handle();
    const auto inexact_reset_built=build_hybrid_portfolio_programs(inexact_reset_system,request,
        {"inexact-affine-reset-verifier"},{1,8},{32,128,4096});
    REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(inexact_reset_built));
    const auto& inexact_reset_programs=std::get<std::vector<HybridPathProgram>>(inexact_reset_built);
    std::vector<HybridPathOptimalFaceCandidate> inexact_reset_candidates{
        exact_candidate(inexact_reset_programs[0],{0,0,0,0}),
        exact_candidate(inexact_reset_programs[1],{0,0,0,0})};
    const auto inexact_reset_result=verify_hybrid_portfolio_family(verifier,inexact_reset_system,
        request,inexact_reset_programs,inexact_reset_candidates,{1,8},{1e-10,1e-10});
    REQUIRE(std::holds_alternative<Diagnostics>(inexact_reset_result));
    CHECK(std::get<Diagnostics>(inexact_reset_result).front().field==
        "hybrid.verification.scalar_interval_domain");

    const double maximum=std::numeric_limits<double>::max();
    auto overflow_reset_equalities=numeric::snapshot(Matrix{1,2,{-maximum,1}});
    auto overflow_reset_rhs=numeric::snapshot_vector(Vector{0});
    REQUIRE(std::holds_alternative<numeric::MatrixView>(overflow_reset_equalities));
    REQUIRE(std::holds_alternative<numeric::VectorView>(overflow_reset_rhs));
    auto overflow_reset=sets::make_h({{"verifier-overflow-affine-reset"},2,{}},
        {std::get<numeric::MatrixView>(reset_inequalities),
         std::get<numeric::VectorView>(reset_bounds),
         std::get<numeric::MatrixView>(overflow_reset_equalities),
         std::get<numeric::VectorView>(overflow_reset_rhs)});
    REQUIRE(std::holds_alternative<sets::SetData>(overflow_reset));
    auto overflow_reset_system=system;
    overflow_reset_system.edges.resize(1);
    overflow_reset_system.edges[0].guards[0]=interval("verifier-overflow-reset-guard",0,1);
    overflow_reset_system.edges[0].reset_relations[0]=std::get<sets::SetData>(overflow_reset).as_handle();
    const auto overflow_reset_built=build_hybrid_portfolio_programs(overflow_reset_system,request,
        {"overflow-affine-reset-verifier"},{1,8},{32,128,4096});
    REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(overflow_reset_built));
    const auto& overflow_reset_programs=std::get<std::vector<HybridPathProgram>>(overflow_reset_built);
    std::vector<HybridPathOptimalFaceCandidate> overflow_reset_candidates{
        exact_candidate(overflow_reset_programs[0],{0,1.0000000001,1.0000000001,maximum})};
    const auto overflow_reset_result=verify_hybrid_portfolio_family(verifier,overflow_reset_system,
        request,overflow_reset_programs,overflow_reset_candidates,{1,8},{1e-10,1e-10});
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(overflow_reset_result));
    CHECK(std::get<HybridFamilyVerificationReport>(overflow_reset_result).branches[0].continuous_coverage==
        HybridVerificationStatus::refuted);

    auto ratio_system=system;
    ratio_system.edges[1].guards[0]=interval("verifier-inexact-row-ratio-guard",0,0.3);
    const auto ratio_built=build_hybrid_portfolio_programs(ratio_system,request,
        {"inexact-row-ratio-verifier"},{1,8},{32,128,4096});
    REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(ratio_built));
    const auto& ratio_programs=std::get<std::vector<HybridPathProgram>>(ratio_built);
    std::vector<HybridPathOptimalFaceCandidate> ratio_candidates{
        exact_candidate(ratio_programs[0],{0,0,0,0}),exact_candidate(ratio_programs[1],{0,0,0,0})};
    auto ratio_inequalities=numeric::snapshot(Matrix{3,4,{0,-1,0,0,0,1,0,0,0,0.1,0,0}});
    auto ratio_bounds=numeric::snapshot_vector(Vector{0,0.3,0.03});
    auto ratio_equalities=numeric::snapshot(Matrix{3,4,{1,0,0,0,0,-1,1,0,0,0,-1,1}});
    auto ratio_rhs=numeric::snapshot_vector(Vector{0,0,0});
    REQUIRE(std::holds_alternative<numeric::MatrixView>(ratio_inequalities));
    REQUIRE(std::holds_alternative<numeric::VectorView>(ratio_bounds));
    REQUIRE(std::holds_alternative<numeric::MatrixView>(ratio_equalities));
    REQUIRE(std::holds_alternative<numeric::VectorView>(ratio_rhs));
    auto inexact_row_relation=sets::make_h({{"verifier-inexact-row-ratio"},4,{}},
        {std::get<numeric::MatrixView>(ratio_inequalities),std::get<numeric::VectorView>(ratio_bounds),
         std::get<numeric::MatrixView>(ratio_equalities),std::get<numeric::VectorView>(ratio_rhs)});
    REQUIRE(std::holds_alternative<sets::SetData>(inexact_row_relation));
    ratio_candidates[1].relation=std::get<sets::SetData>(inexact_row_relation);
    const auto inexact_row_result=verify_hybrid_portfolio_family(verifier,ratio_system,request,
        ratio_programs,ratio_candidates,{1,8},{1e-10,1e-10});
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(inexact_row_result));
    CHECK(std::get<HybridFamilyVerificationReport>(inexact_row_result).branches[1].continuous_coverage==
        HybridVerificationStatus::unsupported);

    auto rank_overcount_inequalities=numeric::snapshot(Matrix{2,4,{0,-1,0,0,0,1,0,0}});
    auto rank_overcount_bounds=numeric::snapshot_vector(Vector{0,1});
    auto rank_overcount_equalities=numeric::snapshot(Matrix{3,4,{
        -2,18372082061.0,-42348971870.0,23976889809.0,
        1,-14888587493.0,81823523113.0,-66934935620.0,
        -9,76971822812.0,-129921336237.0,52949513425.0}});
    auto rank_overcount_rhs=numeric::snapshot_vector(Vector{0,0,0});
    REQUIRE(std::holds_alternative<numeric::MatrixView>(rank_overcount_inequalities));
    REQUIRE(std::holds_alternative<numeric::VectorView>(rank_overcount_bounds));
    REQUIRE(std::holds_alternative<numeric::MatrixView>(rank_overcount_equalities));
    REQUIRE(std::holds_alternative<numeric::VectorView>(rank_overcount_rhs));
    auto rank_overcount_relation=sets::make_h({{"verifier-dependent-row-rank"},4,{}},
        {std::get<numeric::MatrixView>(rank_overcount_inequalities),
         std::get<numeric::VectorView>(rank_overcount_bounds),
         std::get<numeric::MatrixView>(rank_overcount_equalities),
         std::get<numeric::VectorView>(rank_overcount_rhs)});
    REQUIRE(std::holds_alternative<sets::SetData>(rank_overcount_relation));
    auto rank_overcount_system=system;
    rank_overcount_system.edges[1].guards[0]=interval("verifier-dependent-row-rank-guard",0,1);
    auto rank_overcount_programs=programs;
    auto rank_overcount_candidates=std::vector<HybridPathOptimalFaceCandidate>{
        exact_candidate(programs[0],{0,0,0,0}),exact_candidate(programs[1],{0,0,0,0})};
    rank_overcount_programs[1].joint_relation=std::get<sets::SetData>(rank_overcount_relation);
    set_synthetic_relation_trace_rows(rank_overcount_programs[1]);
    rank_overcount_candidates[1].relation=std::get<sets::SetData>(rank_overcount_relation);
    const auto rank_overcount_result=verify_hybrid_portfolio_family(verifier,rank_overcount_system,request,
        rank_overcount_programs,rank_overcount_candidates,{1,8},{1e-10,1e-10});
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(rank_overcount_result));
    CHECK(std::get<HybridFamilyVerificationReport>(rank_overcount_result).branches[1].continuous_coverage==
        HybridVerificationStatus::refuted);

    auto inexact_rank_equalities=numeric::snapshot(Matrix{3,4,{1,0,0,0,0,3,0,-3,0,1,2,-3}});
    REQUIRE(std::holds_alternative<numeric::MatrixView>(inexact_rank_equalities));
    auto inexact_rank_relation=sets::make_h({{"verifier-inexact-elimination-rank"},4,{}},
        {std::get<numeric::MatrixView>(rank_overcount_inequalities),
         std::get<numeric::VectorView>(rank_overcount_bounds),
         std::get<numeric::MatrixView>(inexact_rank_equalities),
         std::get<numeric::VectorView>(rank_overcount_rhs)});
    REQUIRE(std::holds_alternative<sets::SetData>(inexact_rank_relation));
    auto inexact_rank_programs=programs;
    auto inexact_rank_candidates=std::vector<HybridPathOptimalFaceCandidate>{
        exact_candidate(programs[0],{0,0,0,0}),exact_candidate(programs[1],{0,0,0,0})};
    inexact_rank_programs[1].joint_relation=std::get<sets::SetData>(inexact_rank_relation);
    set_synthetic_relation_trace_rows(inexact_rank_programs[1]);
    inexact_rank_candidates[1].relation=std::get<sets::SetData>(inexact_rank_relation);
    const auto inexact_rank_result=verify_hybrid_portfolio_family(verifier,rank_overcount_system,request,
        inexact_rank_programs,inexact_rank_candidates,{1,8},{1e-10,1e-10});
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(inexact_rank_result));
    CHECK(std::get<HybridFamilyVerificationReport>(inexact_rank_result).branches[1].continuous_coverage==
        HybridVerificationStatus::unsupported);

    auto narrow_tied_system=system;
    narrow_tied_system.edges[1].guards[0]=interval("verifier-narrow-tied-guard",0,5e-11);
    const auto narrow_tied_built=build_hybrid_portfolio_programs(narrow_tied_system,request,
        {"narrow-tied-verifier"},{1,8},{32,128,4096});
    REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(narrow_tied_built));
    const auto& narrow_tied_programs=std::get<std::vector<HybridPathProgram>>(narrow_tied_built);
    std::vector<HybridPathOptimalFaceCandidate> narrow_tied_candidates{
        exact_candidate(narrow_tied_programs[0],{0,0,0,0}),
        exact_candidate(narrow_tied_programs[1],{0,0,0,0})};
    narrow_tied_candidates[1].relation=singleton_data({0,0,0,0});
    const auto narrow_tied_result=verify_hybrid_portfolio_family(verifier,narrow_tied_system,request,
        narrow_tied_programs,narrow_tied_candidates,{1,8},{1e-10,1e-10});
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(narrow_tied_result));
    CHECK(std::get<HybridFamilyVerificationReport>(narrow_tied_result).complete_family_coverage==
        HybridVerificationStatus::refuted);

    auto underflow_system=system;
    underflow_system.modes[0].flow=LinearStage{Matrix{1,1,{1}},Matrix{1,1,{1e-200}},
        Matrix{1,0,{}},Vector{0}};
    auto underflow_request=request;
    underflow_request.terminal_objectives[0].objective=LinearTerminal{{1e-200},0};
    const auto underflow_built=build_hybrid_portfolio_programs(underflow_system,underflow_request,
        {"underflow-verifier"},{1,8},{32,128,4096});
    REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(underflow_built));
    const auto& underflow_programs=std::get<std::vector<HybridPathProgram>>(underflow_built);
    std::vector<HybridPathOptimalFaceCandidate> underflow_candidates{
        exact_candidate(underflow_programs[0],{0,0,0,0}),
        exact_candidate(underflow_programs[1],{0,0,0,0})};
    const auto underflow_result=verify_hybrid_portfolio_family(verifier,underflow_system,underflow_request,
        underflow_programs,underflow_candidates,{1,8},{1e-10,1e-10});
    REQUIRE(std::holds_alternative<Diagnostics>(underflow_result));
    CHECK(std::get<Diagnostics>(underflow_result).front().field==
        "hybrid.verification.scalar_interval_domain");

    auto subnormal_residual_system=system;
    subnormal_residual_system.modes[0].flow=LinearStage{Matrix{1,1,{1}},Matrix{1,1,{0x1p-511}},
        Matrix{1,0,{}},Vector{0}};
    auto subnormal_residual_request=request;
    subnormal_residual_request.terminal_objectives[0].objective=LinearTerminal{{0x1p-511},0};
    const auto subnormal_residual_built=build_hybrid_portfolio_programs(subnormal_residual_system,
        subnormal_residual_request,{"subnormal-residual-verifier"},{1,8},{32,128,4096});
    REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(subnormal_residual_built));
    const auto& subnormal_residual_programs=
        std::get<std::vector<HybridPathProgram>>(subnormal_residual_built);
    std::vector<HybridPathOptimalFaceCandidate> subnormal_residual_candidates{
        exact_candidate(subnormal_residual_programs[0],{0,0,0,0}),
        exact_candidate(subnormal_residual_programs[1],{0,0,0,0})};
    const auto subnormal_residual_result=verify_hybrid_portfolio_family(verifier,
        subnormal_residual_system,subnormal_residual_request,subnormal_residual_programs,
        subnormal_residual_candidates,{1,8},{1e-10,1e-10});
    REQUIRE(std::holds_alternative<Diagnostics>(subnormal_residual_result));
    CHECK(std::get<Diagnostics>(subnormal_residual_result).front().field==
        "hybrid.verification.scalar_interval_domain");

    auto inexact_flow_system=system;
    inexact_flow_system.edges.resize(1);
    inexact_flow_system.modes[0].control_sets[0]=Singleton{{0.3}};
    inexact_flow_system.modes[0].flow=LinearStage{Matrix{1,1,{1}},Matrix{1,1,{0.1}},
        Matrix{1,0,{}},Vector{0}};
    auto inexact_flow_request=request;
    const auto inexact_flow_built=build_hybrid_portfolio_programs(inexact_flow_system,inexact_flow_request,
        {"inexact-flow-verifier"},{1,8},{32,128,4096});
    REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(inexact_flow_built));
    const auto& inexact_flow_programs=std::get<std::vector<HybridPathProgram>>(inexact_flow_built);
    std::vector<HybridPathOptimalFaceCandidate> inexact_flow_candidates{
        exact_candidate(inexact_flow_programs[0],{0,0.3,0.03,0.03})};
    const auto inexact_flow_result=verify_hybrid_portfolio_family(verifier,inexact_flow_system,
        inexact_flow_request,inexact_flow_programs,inexact_flow_candidates,{1,8},{1e-10,1e-10});
    REQUIRE(std::holds_alternative<Diagnostics>(inexact_flow_result));
    CHECK(std::get<Diagnostics>(inexact_flow_result).front().field==
        "hybrid.verification.scalar_interval_domain");

    auto sub_ulp_system=system;
    sub_ulp_system.edges[0].guards[0]=interval("verifier-sub-ulp-zero",0,0.5);
    sub_ulp_system.edges[1].guards[0]=interval("verifier-sub-ulp-positive",
        2.7755575615628914e-17,0.25);
    auto sub_ulp_request=request;
    sub_ulp_request.terminal_objectives[0].objective=LinearTerminal{{1},1};
    const auto sub_ulp_built=build_hybrid_portfolio_programs(sub_ulp_system,sub_ulp_request,
        {"sub-ulp-verifier"},{1,8},{32,128,4096});
    REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(sub_ulp_built));
    const auto& sub_ulp_programs=std::get<std::vector<HybridPathProgram>>(sub_ulp_built);
    std::vector<HybridPathOptimalFaceCandidate> sub_ulp_candidates{
        exact_candidate(sub_ulp_programs[0],{0,0,0,0}),
        exact_candidate(sub_ulp_programs[1],{0,2.7755575615628914e-17,2.7755575615628914e-17,
            2.7755575615628914e-17})};
    const auto sub_ulp_result=verify_hybrid_portfolio_family(verifier,sub_ulp_system,sub_ulp_request,
        sub_ulp_programs,sub_ulp_candidates,{1,8},{1e-10,1e-10});
    REQUIRE(std::holds_alternative<Diagnostics>(sub_ulp_result));
    CHECK(std::get<Diagnostics>(sub_ulp_result).front().field==
        "hybrid.verification.scalar_interval_domain");

    candidates.pop_back();
    const auto missing_tie=verify_hybrid_portfolio_family(verifier,system,request,programs,candidates,
        {1,8},{1e-10,1e-10});
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(missing_tie));
    CHECK(std::get<HybridFamilyVerificationReport>(missing_tie).complete_family_coverage==
        HybridVerificationStatus::refuted);

    candidates={exact_candidate(programs[0],{0,0,0,0}),exact_candidate(programs[1],{0,0,0,0})};
    candidates[1].relation=singleton_data({0,0,0,0});
    const auto altered_tie=verify_hybrid_portfolio_family(verifier,system,request,programs,candidates,
        {1,8},{1e-10,1e-10});
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(altered_tie));
    CHECK(std::get<HybridFamilyVerificationReport>(altered_tie).complete_family_coverage==
        HybridVerificationStatus::refuted);

    auto increasing_request=request;
    increasing_request.terminal_objectives[0].objective=LinearTerminal{{1},0};
    const auto increasing_built=build_hybrid_portfolio_programs(system,increasing_request,
        {"interval-endpoint-verifier"},{1,8},{32,128,4096});
    REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(increasing_built));
    const auto& increasing_programs=std::get<std::vector<HybridPathProgram>>(increasing_built);
    std::vector<HybridPathOptimalFaceCandidate> endpoint_candidates{
        exact_candidate(increasing_programs[0],{0,0,0,0}),
        exact_candidate(increasing_programs[1],{0,0,0,0})};
    endpoint_candidates[0].relation=singleton_data({0,0,0,0});
    endpoint_candidates[1].relation=singleton_data({0,0,0,0});
    const auto endpoint_result=verify_hybrid_portfolio_family(verifier,system,increasing_request,
        increasing_programs,endpoint_candidates,{1,8},{1e-10,1e-10});
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(endpoint_result));
    const auto& endpoint_report=std::get<HybridFamilyVerificationReport>(endpoint_result);
    CHECK(endpoint_report.global_objective_optimality==HybridVerificationStatus::established);
    CHECK(endpoint_report.complete_family_coverage==HybridVerificationStatus::established);

    auto decreasing_request=request;
    decreasing_request.terminal_objectives[0].objective=LinearTerminal{{-1},0};
    const auto decreasing_built=build_hybrid_portfolio_programs(system,decreasing_request,
        {"decreasing-endpoint-verifier"},{1,8},{32,128,4096});
    REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(decreasing_built));
    const auto& decreasing_programs=std::get<std::vector<HybridPathProgram>>(decreasing_built);
    std::vector<HybridPathOptimalFaceCandidate> decreasing_candidates{
        exact_candidate(decreasing_programs[0],{0,0.5,0.5,0.5}),
        exact_candidate(decreasing_programs[1],{0,0.25,0.25,0.25})};
    decreasing_candidates[0].relation=singleton_data({0,0.5,0.5,0.5});
    decreasing_candidates[1].relation=singleton_data({0,0.25,0.25,0.25});
    const auto decreasing_result=verify_hybrid_portfolio_family(verifier,system,decreasing_request,
        decreasing_programs,decreasing_candidates,{1,8},{1e-10,1e-10});
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(decreasing_result));
    const auto& decreasing_report=std::get<HybridFamilyVerificationReport>(decreasing_result);
    CHECK(decreasing_report.global_objective_optimality==HybridVerificationStatus::established);
    CHECK(decreasing_report.complete_family_coverage==HybridVerificationStatus::refuted);
    CHECK(decreasing_report.branches[0].continuous_coverage==HybridVerificationStatus::established);
    CHECK(decreasing_report.branches[1].objective_optimality==HybridVerificationStatus::refuted);

    auto enlarged_inequalities=numeric::snapshot(Matrix{2,4,{0,-1,0,0,0,1,0,0}});
    auto enlarged_bounds=numeric::snapshot_vector(Vector{0,5e-11});
    auto line_equalities=numeric::snapshot(Matrix{3,4,{1,0,0,0,0,-1,1,0,0,0,-1,1}});
    auto line_rhs=numeric::snapshot_vector(Vector{0,0,0});
    REQUIRE(std::holds_alternative<numeric::MatrixView>(enlarged_inequalities));
    REQUIRE(std::holds_alternative<numeric::VectorView>(enlarged_bounds));
    REQUIRE(std::holds_alternative<numeric::MatrixView>(line_equalities));
    REQUIRE(std::holds_alternative<numeric::VectorView>(line_rhs));
    auto enlarged_face=sets::make_h({{"verifier-enlarged-optimal-face"},4,{}},
        {std::get<numeric::MatrixView>(enlarged_inequalities),
         std::get<numeric::VectorView>(enlarged_bounds),std::get<numeric::MatrixView>(line_equalities),
         std::get<numeric::VectorView>(line_rhs)});
    REQUIRE(std::holds_alternative<sets::SetData>(enlarged_face));
    auto enlarged_candidates=endpoint_candidates;
    enlarged_candidates[0].relation=std::get<sets::SetData>(enlarged_face);
    const auto enlarged_result=verify_hybrid_portfolio_family(verifier,system,increasing_request,
        increasing_programs,enlarged_candidates,{1,8},{1e-10,1e-10});
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(enlarged_result));
    CHECK(std::get<HybridFamilyVerificationReport>(enlarged_result).complete_family_coverage==
        HybridVerificationStatus::refuted);

    auto shifted_singleton_candidates=endpoint_candidates;
    shifted_singleton_candidates[0].relation=singleton_data({0,5e-11,5e-11,5e-11});
    const auto shifted_singleton_result=verify_hybrid_portfolio_family(verifier,system,increasing_request,
        increasing_programs,shifted_singleton_candidates,{1,8},{1e-10,1e-10});
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(shifted_singleton_result));
    CHECK(std::get<HybridFamilyVerificationReport>(shifted_singleton_result).complete_family_coverage==
        HybridVerificationStatus::refuted);

    auto contradictory_inequality=numeric::snapshot(Matrix{1,4,{1,0,0,0}});
    auto contradictory_bound=numeric::snapshot_vector(Vector{-5e-11});
    auto fixed_equalities=numeric::snapshot(Matrix{4,4,{1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1}});
    auto fixed_rhs=numeric::snapshot_vector(Vector{0,0,0,0});
    REQUIRE(std::holds_alternative<numeric::MatrixView>(contradictory_inequality));
    REQUIRE(std::holds_alternative<numeric::VectorView>(contradictory_bound));
    REQUIRE(std::holds_alternative<numeric::MatrixView>(fixed_equalities));
    REQUIRE(std::holds_alternative<numeric::VectorView>(fixed_rhs));
    auto empty_candidate=sets::make_h({{"verifier-contradictory-face"},4,{}},
        {std::get<numeric::MatrixView>(contradictory_inequality),
         std::get<numeric::VectorView>(contradictory_bound),std::get<numeric::MatrixView>(fixed_equalities),
         std::get<numeric::VectorView>(fixed_rhs)});
    REQUIRE(std::holds_alternative<sets::SetData>(empty_candidate));
    auto contradictory_candidates=endpoint_candidates;
    contradictory_candidates[0].relation=std::get<sets::SetData>(empty_candidate);
    const auto contradictory_result=verify_hybrid_portfolio_family(verifier,system,increasing_request,
        increasing_programs,contradictory_candidates,{1,8},{1e-10,1e-10});
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(contradictory_result));
    CHECK(std::get<HybridFamilyVerificationReport>(contradictory_result).complete_family_coverage==
        HybridVerificationStatus::refuted);

    auto conflicting_equalities=numeric::snapshot(Matrix{5,4,
        {1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1,1,0,0,0}});
    auto conflicting_rhs=numeric::snapshot_vector(Vector{0,0,0,0,5e-11});
    auto conflicting_inequalities=numeric::snapshot(Matrix{0,4,{}});
    auto conflicting_bounds=numeric::snapshot_vector(Vector{});
    REQUIRE(std::holds_alternative<numeric::MatrixView>(conflicting_equalities));
    REQUIRE(std::holds_alternative<numeric::VectorView>(conflicting_rhs));
    REQUIRE(std::holds_alternative<numeric::MatrixView>(conflicting_inequalities));
    REQUIRE(std::holds_alternative<numeric::VectorView>(conflicting_bounds));
    auto conflicting_face=sets::make_h({{"verifier-conflicting-face"},4,{}},
        {std::get<numeric::MatrixView>(conflicting_inequalities),std::get<numeric::VectorView>(conflicting_bounds),
         std::get<numeric::MatrixView>(conflicting_equalities),std::get<numeric::VectorView>(conflicting_rhs)});
    REQUIRE(std::holds_alternative<sets::SetData>(conflicting_face));
    auto conflicting_candidates=endpoint_candidates;
    conflicting_candidates[0].relation=std::get<sets::SetData>(conflicting_face);
    const auto conflicting_result=verify_hybrid_portfolio_family(verifier,system,increasing_request,
        increasing_programs,conflicting_candidates,{1,8},{1e-10,1e-10});
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(conflicting_result));
    CHECK(std::get<HybridFamilyVerificationReport>(conflicting_result).complete_family_coverage==
        HybridVerificationStatus::refuted);

    auto rotated_equalities=numeric::snapshot(Matrix{3,4,
        {1,0,0,0,0,1,-(1+5e-11),0,0,0,1,-1}});
    auto rotated_rhs=numeric::snapshot_vector(Vector{0,0,0});
    REQUIRE(std::holds_alternative<numeric::MatrixView>(rotated_equalities));
    REQUIRE(std::holds_alternative<numeric::VectorView>(rotated_rhs));
    auto rotated_face=sets::make_h({{"verifier-rotated-singleton-face"},4,{}},
        {std::get<numeric::MatrixView>(conflicting_inequalities),
         std::get<numeric::VectorView>(conflicting_bounds),std::get<numeric::MatrixView>(rotated_equalities),
         std::get<numeric::VectorView>(rotated_rhs)});
    REQUIRE(std::holds_alternative<sets::SetData>(rotated_face));
    auto rotated_candidates=endpoint_candidates;
    rotated_candidates[0].relation=std::get<sets::SetData>(rotated_face);
    const auto rotated_result=verify_hybrid_portfolio_family(verifier,system,increasing_request,
        increasing_programs,rotated_candidates,{1,8},{1e-10,1e-10});
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(rotated_result));
    CHECK(std::get<HybridFamilyVerificationReport>(rotated_result).complete_family_coverage==
        HybridVerificationStatus::refuted);

    auto insufficient_variable_limits=increasing_programs;
    insufficient_variable_limits[0].relation_limits.max_variables=3;
    const auto variable_limit_result=verify_hybrid_portfolio_family(verifier,system,increasing_request,
        insufficient_variable_limits,endpoint_candidates,{1,8},{1e-10,1e-10});
    REQUIRE(std::holds_alternative<Diagnostics>(variable_limit_result));
    CHECK(std::get<Diagnostics>(variable_limit_result).front().field=="hybrid.adapter.operations");

    auto near_tie_system=system;
    near_tie_system.edges[1].guards[0]=interval("verifier-near-tie-guard",5e-11,0.25);
    const auto near_tie_built=build_hybrid_portfolio_programs(near_tie_system,increasing_request,
        {"near-tie-verifier"},{1,8},{32,128,4096});
    REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(near_tie_built));
    const auto& near_tie_programs=std::get<std::vector<HybridPathProgram>>(near_tie_built);
    std::vector<HybridPathOptimalFaceCandidate> near_tie_candidates{
        exact_candidate(near_tie_programs[0],{0,0,0,0}),
        exact_candidate(near_tie_programs[1],{0,5e-11,5e-11,5e-11})};
    near_tie_candidates[0].relation=singleton_data({0,0,0,0});
    near_tie_candidates[1].relation=singleton_data({0,5e-11,5e-11,5e-11});
    const auto near_tie_result=verify_hybrid_portfolio_family(verifier,near_tie_system,increasing_request,
        near_tie_programs,near_tie_candidates,{1,8},{1e-10,1e-10});
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(near_tie_result));
    const auto& near_tie_report=std::get<HybridFamilyVerificationReport>(near_tie_result);
    CHECK(near_tie_report.global_objective_optimality==HybridVerificationStatus::established);
    CHECK(near_tie_report.complete_family_coverage==HybridVerificationStatus::refuted);
    CHECK(near_tie_report.branches[1].objective_optimality==HybridVerificationStatus::refuted);

    auto free_post_equalities=numeric::snapshot(Matrix{3,4,{1,0,0,0,0,1,0,0,0,0,1,0}});
    auto free_post_rhs=numeric::snapshot_vector(Vector{0,0,0});
    auto free_post_inequalities=numeric::snapshot(Matrix{0,4,{}});
    auto free_post_bounds=numeric::snapshot_vector(Vector{});
    REQUIRE(std::holds_alternative<numeric::MatrixView>(free_post_equalities));
    REQUIRE(std::holds_alternative<numeric::VectorView>(free_post_rhs));
    REQUIRE(std::holds_alternative<numeric::MatrixView>(free_post_inequalities));
    REQUIRE(std::holds_alternative<numeric::VectorView>(free_post_bounds));
    auto free_post_data=sets::make_h({{"verifier-free-post"},4,{}},
        {std::get<numeric::MatrixView>(free_post_inequalities),std::get<numeric::VectorView>(free_post_bounds),
         std::get<numeric::MatrixView>(free_post_equalities),std::get<numeric::VectorView>(free_post_rhs)});
    REQUIRE(std::holds_alternative<sets::SetData>(free_post_data));
    auto malformed_face=endpoint_candidates;
    malformed_face[0].relation=std::get<sets::SetData>(free_post_data);
    const auto malformed_face_result=verify_hybrid_portfolio_family(verifier,system,increasing_request,
        increasing_programs,malformed_face,{1,8},{1e-10,1e-10});
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(malformed_face_result));
    CHECK(std::get<HybridFamilyVerificationReport>(malformed_face_result).complete_family_coverage==
        HybridVerificationStatus::refuted);

    auto malformed_programs=increasing_programs;
    malformed_programs[0].joint_relation=std::get<sets::SetData>(free_post_data);
    const auto malformed_program_result=verify_hybrid_portfolio_family(verifier,system,increasing_request,
        malformed_programs,endpoint_candidates,{1,8},{1e-10,1e-10});
    REQUIRE(std::holds_alternative<Diagnostics>(malformed_program_result));
    CHECK(std::get<Diagnostics>(malformed_program_result).front().code==
        DiagnosticCode::evidence_mismatch);

    auto malformed_suboptimal_programs=near_tie_programs;
    malformed_suboptimal_programs[1].joint_relation=std::get<sets::SetData>(free_post_data);
    std::vector<HybridPathOptimalFaceCandidate> only_optimal_near_tie_candidate{
        near_tie_candidates[0]};
    const auto malformed_suboptimal_result=verify_hybrid_portfolio_family(verifier,near_tie_system,
        increasing_request,malformed_suboptimal_programs,only_optimal_near_tie_candidate,
        {1,8},{1e-10,1e-10});
    REQUIRE(std::holds_alternative<Diagnostics>(malformed_suboptimal_result));
    CHECK(std::get<Diagnostics>(malformed_suboptimal_result).front().code==
        DiagnosticCode::evidence_mismatch);
}

TEST_CASE("one-step interval verifier accepts a point face fixed by objective equality") {
    const auto reset_equalities = numeric::snapshot(Matrix{1, 2, {-1, 1}});
    const auto reset_rhs = numeric::snapshot_vector(Vector{0});
    const auto reset_inequalities = numeric::snapshot(Matrix{0, 2, {}});
    const auto reset_bounds = numeric::snapshot_vector(Vector{});
    REQUIRE(std::holds_alternative<numeric::MatrixView>(reset_equalities));
    REQUIRE(std::holds_alternative<numeric::VectorView>(reset_rhs));
    REQUIRE(std::holds_alternative<numeric::MatrixView>(reset_inequalities));
    REQUIRE(std::holds_alternative<numeric::VectorView>(reset_bounds));
    const auto reset = sets::make_h({{"point-face-reset"}, 2, {"pre", "post"}},
        {std::get<numeric::MatrixView>(reset_inequalities),
         std::get<numeric::VectorView>(reset_bounds),
         std::get<numeric::MatrixView>(reset_equalities),
         std::get<numeric::VectorView>(reset_rhs)});
    REQUIRE(std::holds_alternative<sets::SetData>(reset));
    auto system = model::HybridSystem{
        1,
        {{{"source"}, 1, 1, {"x"}, {"u"},
          LinearStage{Matrix{1,1,{1}}, Matrix{1,1,{1}}, Matrix{1,0,{}}, Vector{0}},
          {interval("point-face-control", 0, 1)}, {UniversalSet{1}, UniversalSet{1}}},
         {{"target"}, 1, 0, {"y"}, {},
          LinearStage{Matrix{1,1,{1}}, Matrix{1,0,{}}, Matrix{1,0,{}}, Vector{0}},
          {UniversalSet{0}}, {UniversalSet{1}, UniversalSet{1}}}},
        {{{"point-face-edge"}, {"source"}, {"target"}, {interval("point-face-guard", 0, 0.5)},
          {std::get<sets::SetData>(reset).as_handle()}}}};
    auto request = model::HybridRequest{{{"source"}, {0}}, {{"target"}},
        {{{"target"}, LinearTerminal{{1}, 0}, "cost", "units"}}};
    const auto built = build_hybrid_portfolio_programs(system, request, {"point-face-regression"},
        {1, 4}, {16, 64, 1024});
    REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(built));
    const auto& programs = std::get<std::vector<HybridPathProgram>>(built);
    REQUIRE(programs.size() == 1);
    const auto& linear = std::get<LinearProgram>(programs[0].program);
    ProgramResult solver_result{Termination::completed,
        {linear.identity(), MathematicalOutcome::optimal,
         SymbolicArgument{"literal point optimum", "u=0 minimizes x_terminal=u"}, {}},
        Vector{0, 0, 0, 0}, {}, "independent analytic fixture"};
    const auto candidate_result = build_hybrid_path_optimal_face_candidate(
        programs[0], solver_result, {1e-10, 1e-10});
    REQUIRE(std::holds_alternative<HybridPathOptimalFaceCandidate>(candidate_result));
    const std::array<HybridPathOptimalFaceCandidate, 1> candidates{
        std::get<HybridPathOptimalFaceCandidate>(candidate_result)};
    OneStepScalarIntervalHybridFamilyVerifier verifier;
    const auto verified = verify_hybrid_portfolio_family(verifier, system, request, programs,
        candidates, {1, 4}, {1e-10, 1e-10});
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(verified));
    const auto& report = std::get<HybridFamilyVerificationReport>(verified);
    CHECK(report.global_objective_optimality == HybridVerificationStatus::established);
    CHECK(report.complete_family_coverage == HybridVerificationStatus::established);
    REQUIRE(report.branches.size() == 1);
    CHECK(report.branches[0].continuous_coverage == HybridVerificationStatus::established);
}

TEST_CASE("exact singleton hybrid verifier checks guard entry and rejects forbidden mode paths") {
    auto [system,request]=exact_singleton_portfolio();
    system.edges[0].guards[0]=Singleton{{3}};
    system.edges[1].guards[0]=Singleton{{4}};
    auto built=build_hybrid_portfolio_programs(system,request,{"exact-hybrid-guards"},
        {1,8},{32,128,4096});
    REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(built));
    const auto& programs=std::get<std::vector<HybridPathProgram>>(built);
    ExactSingletonHybridFamilyVerifier verifier;
    const Vector point{2,1,3,0,0};
    std::vector<HybridPathOptimalFaceCandidate> candidates{exact_candidate(programs[0],point)};
    const auto result=verify_hybrid_portfolio_family(verifier,system,request,programs,candidates,
        {1,8},{1e-10,1e-10});
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(result));
    const auto& report=std::get<HybridFamilyVerificationReport>(result);
    CHECK(report.branches[0].feasibility==HybridVerificationStatus::established);
    CHECK(report.branches[1].feasibility==HybridVerificationStatus::refuted);
    CHECK(report.complete_family_coverage==HybridVerificationStatus::established);

    auto forbidden_paths=std::vector<model::HybridPath>{programs[0].path,programs[1].path,programs[2].path};
    forbidden_paths[0].modes[1]={"source"};
    const auto rejected=verifier.verify(system,request,forbidden_paths,programs,candidates,
        {1e-10,1e-10},{});
    REQUIRE(std::holds_alternative<Diagnostics>(rejected));
    CHECK(std::get<Diagnostics>(rejected).front().field=="hybrid.verification.oracle_paths");
}

TEST_CASE("exact singleton hybrid verifier bounds independent path expansion") {
    auto [system,request]=exact_singleton_portfolio();
    system.horizon=20;
    system.edges.resize(2);
    for(std::size_t i=0;i<system.edges.size();++i) {
        system.edges[i].id={"loop-"+std::to_string(i)};
        system.edges[i].source={"source"};
        system.edges[i].target={"source"};
    }
    request.allowed_terminal_modes={{"target"}};
    ExactSingletonHybridFamilyVerifier verifier;
    const auto result=verifier.verify(system,request,{}, {}, {},{1e-10,1e-10},{});
    REQUIRE(std::holds_alternative<Diagnostics>(result));
    CHECK(std::get<Diagnostics>(result).front().field=="hybrid.verification.oracle_limit");
}

TEST_CASE("independent verifier path enumeration observes cancellation after traversal begins") {
    auto [system,request]=exact_singleton_portfolio();
    std::size_t polls=0;
    const auto result=detail::independently_enumerate_paths(system,request,10,100,[&] {
        return ++polls==7;
    });
    CHECK(result.cancelled);
    CHECK_FALSE(result.resource_limit);
    CHECK(result.paths.size()==1);
    CHECK(polls==7);
}

TEST_CASE("exact singleton hybrid verifier reports missing or altered optimal faces") {
    auto [system,request]=exact_singleton_portfolio();
    auto built=build_hybrid_portfolio_programs(system,request,{"exact-hybrid-face"},
        {1,8},{32,128,4096});
    REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(built));
    const auto& programs=std::get<std::vector<HybridPathProgram>>(built);
    ExactSingletonHybridFamilyVerifier verifier;
    const Vector point{2,1,3,0,0};
    std::vector<HybridPathOptimalFaceCandidate> missing{exact_candidate(programs[0],point)};
    const auto omitted=verify_hybrid_portfolio_family(verifier,system,request,programs,missing,
        {1,8},{1e-10,1e-10});
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(omitted));
    CHECK(std::get<HybridFamilyVerificationReport>(omitted).global_objective_optimality==
        HybridVerificationStatus::established);
    CHECK(std::get<HybridFamilyVerificationReport>(omitted).complete_family_coverage==
        HybridVerificationStatus::refuted);

    std::vector<HybridPathOptimalFaceCandidate> altered{
        exact_candidate(programs[0],point),exact_candidate(programs[1],point)};
    altered[1].relation=singleton_data({2,1,3,1,0});
    const auto wrong_face=verify_hybrid_portfolio_family(verifier,system,request,programs,altered,
        {1,8},{1e-10,1e-10});
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(wrong_face));
    CHECK(std::get<HybridFamilyVerificationReport>(wrong_face).complete_family_coverage==
        HybridVerificationStatus::refuted);

    auto wrong_programs=programs;
    wrong_programs[0].joint_relation=singleton_data({2,1,3,0,1});
    const auto wrong_relation=verify_hybrid_portfolio_family(verifier,system,request,wrong_programs,altered,
        {1,8},{1e-10,1e-10});
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(wrong_relation));
    CHECK(std::get<HybridFamilyVerificationReport>(wrong_relation).complete_family_coverage==
        HybridVerificationStatus::refuted);

    auto over_limit_programs=programs;
    over_limit_programs[0].relation_limits.max_matrix_elements=1;
    const auto over_limit=verify_hybrid_portfolio_family(verifier,system,request,over_limit_programs,altered,
        {1,8},{1e-10,1e-10});
    REQUIRE(std::holds_alternative<Diagnostics>(over_limit));
    CHECK(std::get<Diagnostics>(over_limit).front().field=="hybrid.adapter.operations");

    std::vector<HybridPathOptimalFaceCandidate> extra_worse{
        exact_candidate(programs[0],point),exact_candidate(programs[1],point),
        exact_candidate(programs[2],Vector{2,1,3,1,0})};
    const auto suboptimal=verify_hybrid_portfolio_family(verifier,system,request,programs,extra_worse,
        {1,8},{1e-10,1e-10});
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(suboptimal));
    CHECK(std::get<HybridFamilyVerificationReport>(suboptimal).complete_family_coverage==
        HybridVerificationStatus::refuted);
}

TEST_CASE("independent two-stage singleton oracle matches every mode branch and objective") {
    const auto reset_point=[](double pre,double post) {
        return singleton_relation("two-stage-reset",{pre,post});
    };
    const auto scalar_mode=[](std::string id,double stage_zero_control,double stage_one_control) {
        model::HybridMode mode{{std::move(id)},1,1,{"x"},{"u"}};
        const LinearStage flow{Matrix{1,1,{1}},Matrix{1,1,{1}},Matrix{1,0,{}},Vector{0}};
        mode.flow=std::vector<LinearStage>{flow,flow};
        mode.control_sets={Singleton{{stage_zero_control}},Singleton{{stage_one_control}}};
        mode.invariants={UniversalSet{1},UniversalSet{1},UniversalSet{1}};
        return mode;
    };
    auto start=scalar_mode("start",1,0);
    auto middle=scalar_mode("middle",0,2);
    auto terminal=scalar_mode("terminal",0,0);
    model::HybridSystem system{2,{start,middle,terminal},
        {{{"enter"},{"start"},{"middle"},{Singleton{{1}},UniversalSet{1}},
            {reset_point(1,2),universal("unused-enter-reset",2)}},
         {{"tie-a"},{"middle"},{"terminal"},{UniversalSet{1},Singleton{{4}}},
            {universal("unused-tie-a-reset",2),reset_point(4,5)}},
         {{"tie-b"},{"middle"},{"terminal"},{UniversalSet{1},Singleton{{4}}},
            {universal("unused-tie-b-reset",2),reset_point(4,5)}},
         {{"worse"},{"middle"},{"terminal"},{UniversalSet{1},Singleton{{4}}},
            {universal("unused-worse-reset",2),reset_point(4,7)}}}};
    model::HybridRequest request{{{"start"},{0}},{{"terminal"}},
        {{{"terminal"},LinearTerminal{{1},0},"terminal-state","units"}}};

    struct OracleBranch {
        model::HybridPath path;
        Vector tuple;
        double objective;
    };
    std::vector<OracleBranch> oracle;
    // Exhaustively interpret this two-stage graph from raw input data. This
    // deliberately does not call production path enumeration, composition,
    // objective lifting, or verification.
    const auto find_mode_raw=[&](const model::HybridModeId& id)->const model::HybridMode* {
        const auto found=std::find_if(system.modes.begin(),system.modes.end(),
            [&](const auto& mode){return mode.id==id;});
        return found==system.modes.end()?nullptr:&*found;
    };
    const auto singleton_set=[](const AdmissibleSet& set)->const Singleton* {
        return std::get_if<Singleton>(&set);
    };
    const auto reset_target=[&](const SetHandle& handle,double pre,double& post) {
        const auto decoded=sets::from_handle(handle);
        if(std::holds_alternative<Diagnostic>(decoded)) return false;
        const auto representation=std::get<sets::SetData>(decoded).representation();
        const auto* point=std::get_if<sets::SingletonRepresentation>(&representation);
        if(!point||point->point.size()!=2||point->point[0]!=pre) return false;
        post=point->point[1];
        return true;
    };
    for(const auto& first:system.edges) {
        if(first.source!=request.initial.mode) continue;
        const auto* first_mode=find_mode_raw(first.source);
        const auto* first_control=singleton_set(first_mode->control_sets[0]);
        REQUIRE(first_control!=nullptr);
        REQUIRE(first_control->point.size()==1);
        const auto& first_flow=std::get<std::vector<LinearStage>>(first_mode->flow)[0];
        const double first_pre=first_flow.A.values[0]*request.initial.state[0]+
            first_flow.B.values[0]*first_control->point[0];
        const auto* first_guard=singleton_set(first.guards[0]);
        if(!first_guard||first_guard->point!=Vector{first_pre}) continue;
        double middle_state=0;
        if(!reset_target(first.reset_relations[0],first_pre,middle_state)) continue;
        for(const auto& second:system.edges) {
            if(second.source!=first.target) continue;
            const auto* second_mode=find_mode_raw(second.source);
            const auto* second_control=singleton_set(second_mode->control_sets[1]);
            REQUIRE(second_control!=nullptr);
            REQUIRE(second_control->point.size()==1);
            const auto& second_flow=std::get<std::vector<LinearStage>>(second_mode->flow)[1];
            const double second_pre=second_flow.A.values[0]*middle_state+
                second_flow.B.values[0]*second_control->point[0];
            const auto* second_guard=singleton_set(second.guards[1]);
            if(!second_guard||second_guard->point!=Vector{second_pre}) continue;
            const auto decoded=sets::from_handle(second.reset_relations[1]);
            REQUIRE(std::holds_alternative<sets::SetData>(decoded));
            const auto rep=std::get<sets::SetData>(decoded).representation();
            const auto* point=std::get_if<sets::SingletonRepresentation>(&rep);
            REQUIRE(point!=nullptr);
            REQUIRE(point->point.size()==2);
            REQUIRE(point->point[0]==second_pre);
            const double terminal_state=point->point[1];
            oracle.push_back({{{first.source,first.target,second.target},{first.id,second.id}},
                {request.initial.state[0],first_control->point[0],first_pre,middle_state,
                 second_control->point[0],second_pre,terminal_state},terminal_state});
        }
    }
    REQUIRE(oracle.size()==3);

    const auto built=build_hybrid_portfolio_programs(system,request,{"two-stage-independent-oracle"},
        {2,16},{32,256,4096});
    REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(built));
    const auto& programs=std::get<std::vector<HybridPathProgram>>(built);
    REQUIRE(programs.size()==oracle.size());
    for(const auto& expected:oracle) {
        const auto found=std::find_if(programs.begin(),programs.end(),[&](const auto& program) {
            return program.path==expected.path;
        });
        REQUIRE(found!=programs.end());
        const auto relation_representation=found->joint_relation.representation();
        REQUIRE(std::holds_alternative<sets::HRepresentation>(relation_representation));
        const auto& relation=std::get<sets::HRepresentation>(relation_representation);
        CHECK(satisfies(relation,expected.tuple));
        CHECK(equality_rank(relation.equalities)==expected.tuple.size());
        const auto& linear=std::get<LinearProgram>(found->program);
        REQUIRE(linear.objective().size()==expected.tuple.size());
        double objective=linear.offset();
        for(std::size_t i=0;i<expected.tuple.size();++i)
            objective+=linear.objective()[i]*expected.tuple[i];
        CHECK(objective==expected.objective);
    }
    CHECK(oracle[0].objective==5);
    CHECK(oracle[1].objective==5);
    CHECK(oracle[2].objective==7);

    std::vector<HybridPathOptimalFaceCandidate> optimal_candidates;
    for(const auto& expected:oracle) {
        if(expected.objective!=5) continue;
        const auto found=std::find_if(programs.begin(),programs.end(),[&](const auto& program) {
            return program.path==expected.path;
        });
        REQUIRE(found!=programs.end());
        optimal_candidates.push_back(exact_candidate(*found,expected.tuple));
    }
    REQUIRE(optimal_candidates.size()==2);
    ExactSingletonHybridFamilyVerifier verifier;
    const auto verified=verify_hybrid_portfolio_family(verifier,system,request,programs,
        optimal_candidates,{2,16},{0,0});
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(verified));
    const auto& report=std::get<HybridFamilyVerificationReport>(verified);
    CHECK(report.global_objective_optimality==HybridVerificationStatus::established);
    CHECK(report.complete_family_coverage==HybridVerificationStatus::established);
    REQUIRE(report.branches.size()==3);
    const auto branch_record=[&](const std::string& edge_id) {
        return std::find_if(report.branches.begin(),report.branches.end(),[&](const auto& branch) {
            return branch.path.edges.size()==2&&branch.path.edges[1].value==edge_id;
        });
    };
    const auto tie_a=branch_record("tie-a");
    const auto tie_b=branch_record("tie-b");
    const auto worse=branch_record("worse");
    REQUIRE(tie_a!=report.branches.end());
    REQUIRE(tie_b!=report.branches.end());
    REQUIRE(worse!=report.branches.end());
    CHECK(tie_a->feasibility==HybridVerificationStatus::established);
    CHECK(tie_a->objective_optimality==HybridVerificationStatus::established);
    CHECK(tie_b->feasibility==HybridVerificationStatus::established);
    CHECK(tie_b->objective_optimality==HybridVerificationStatus::established);
    CHECK(worse->feasibility==HybridVerificationStatus::established);
    CHECK(worse->objective_optimality==HybridVerificationStatus::refuted);
}

TEST_CASE("two-stage scalar interval verifier checks tied continuous families independently") {
    const auto interval_reset=[](std::string id,double pre,double post,double rhs) {
        auto inequalities=numeric::snapshot(Matrix{0,2,{}});
        auto upper=numeric::snapshot_vector(Vector{});
        auto equalities=numeric::snapshot(Matrix{1,2,{pre,post}});
        auto values=numeric::snapshot_vector(Vector{rhs});
        REQUIRE(std::holds_alternative<numeric::MatrixView>(inequalities));
        REQUIRE(std::holds_alternative<numeric::VectorView>(upper));
        REQUIRE(std::holds_alternative<numeric::MatrixView>(equalities));
        REQUIRE(std::holds_alternative<numeric::VectorView>(values));
        auto data=sets::make_h({SetId{std::move(id)},2,{"pre","post"}},
            {std::get<numeric::MatrixView>(inequalities),std::get<numeric::VectorView>(upper),
             std::get<numeric::MatrixView>(equalities),std::get<numeric::VectorView>(values)});
        REQUIRE(std::holds_alternative<sets::SetData>(data));
        return std::get<sets::SetData>(std::move(data)).as_handle();
    };
    const auto scalar_mode=[](std::string id,AdmissibleSet first_control,
        AdmissibleSet second_control) {
        model::HybridMode mode{{std::move(id)},1,1,{"x"},{"u"}};
        const LinearStage flow{Matrix{1,1,{1}},Matrix{1,1,{1}},Matrix{1,0,{}},Vector{0}};
        mode.flow=std::vector<LinearStage>{flow,flow};
        mode.control_sets={std::move(first_control),std::move(second_control)};
        mode.invariants={UniversalSet{1},UniversalSet{1},UniversalSet{1}};
        return mode;
    };
    auto start=scalar_mode("start",interval("two-stage-free-control",0,1),Singleton{{0}});
    auto middle=scalar_mode("middle",Singleton{{0}},Singleton{{0}});
    auto terminal=scalar_mode("terminal",Singleton{{0}},Singleton{{0}});
    struct OracleEdge { std::string id; double lower; double upper; double terminal_value; };
    const std::vector<OracleEdge> second_stage_edges{
        {"tie-a",0,0.5,0},{"tie-b",0,1,0},{"worse",1,1,1}};
    const auto identity=interval_reset("two-stage-identity-reset",-1,1,0);
    std::vector<model::HybridTransitionEdge> edges{
        {{"enter"},{"start"},{"middle"},{interval("two-stage-entry-guard",0,1),UniversalSet{1}},
            {identity,universal("two-stage-unused-entry-reset",2)}}};
    for(const auto& spec:second_stage_edges) {
        edges.push_back({{spec.id},{"middle"},{"terminal"},
            {UniversalSet{1},interval("two-stage-guard-"+spec.id,spec.lower,spec.upper)},
            {universal("two-stage-unused-reset-"+spec.id,2),
             interval_reset("two-stage-terminal-reset-"+spec.id,0,1,spec.terminal_value)}});
    }
    model::HybridSystem system{2,{start,middle,terminal},std::move(edges)};
    model::HybridRequest request{{{"start"},{0}},{{"terminal"}},
        {{{"terminal"},LinearTerminal{{1},0},"terminal-state","units"}}};

    struct OracleBranch { model::HybridPath path; double lower; double upper; double cost; };
    std::vector<OracleBranch> oracle;
    for(const auto& spec:second_stage_edges) {
        // Raw rational fixture equations: x_pre[0]=u[0], x_post[1]=x_pre[0],
        // x_pre[1]=x_post[1], and the selected edge clips u[0] to its guard.
        const double lower=std::max(0.0,spec.lower);
        const double upper=std::min(1.0,spec.upper);
        if(lower<=upper)
            oracle.push_back({model::HybridPath{{model::HybridModeId{"start"},
                    model::HybridModeId{"middle"},model::HybridModeId{"terminal"}},
                {model::HybridEdgeId{"enter"},model::HybridEdgeId{spec.id}}},
                lower,upper,spec.terminal_value});
    }
    REQUIRE(oracle.size()==3);
    CHECK(oracle[0].lower==0);
    CHECK(oracle[0].upper==0.5);
    CHECK(oracle[1].lower==0);
    CHECK(oracle[1].upper==1);
    CHECK(oracle[2].lower==1);
    CHECK(oracle[2].upper==1);
    CHECK(oracle[0].cost==0);
    CHECK(oracle[1].cost==0);
    CHECK(oracle[2].cost==1);

    const auto built=build_hybrid_portfolio_programs(system,request,{"two-stage-continuous-verifier"},
        {2,16},{64,512,8192});
    REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(built));
    const auto& programs=std::get<std::vector<HybridPathProgram>>(built);
    REQUIRE(programs.size()==oracle.size());
    std::vector<HybridPathOptimalFaceCandidate> candidates;
    for(std::size_t i=0;i<2;++i) {
        const auto found=std::find_if(programs.begin(),programs.end(),[&](const auto& program) {
            return program.path.edges.back().value==oracle[i].path.edges.back().value;
        });
        REQUIRE(found!=programs.end());
        candidates.push_back(exact_candidate(*found,{0,0,0,0,0,0,0}));
    }
    TwoStageScalarIntervalHybridFamilyVerifier verifier;
    const auto result=verify_hybrid_portfolio_family(verifier,system,request,programs,candidates,
        {2,16},{0,0});
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(result));
    const auto& report=std::get<HybridFamilyVerificationReport>(result);
    CHECK(report.verifier_id=="csl.hybrid.two-stage-scalar-interval");
    CHECK(report.global_objective_optimality==HybridVerificationStatus::established);
    CHECK(report.complete_family_coverage==HybridVerificationStatus::established);
    const auto record_for=[&](const std::string& edge_id) {
        return std::find_if(report.branches.begin(),report.branches.end(),[&](const auto& branch) {
            return branch.path.edges.back().value==edge_id;
        });
    };
    for(const auto& expected:oracle) {
        const auto record=record_for(expected.path.edges.back().value);
        REQUIRE(record!=report.branches.end());
        INFO("branch " << expected.path.edges.back().value << " coverage " <<
            static_cast<int>(record->continuous_coverage));
        for(const auto& diagnostic:record->diagnostics)
            INFO("diagnostic " << diagnostic.field << ": " << diagnostic.explanation);
        CHECK(record->feasibility==HybridVerificationStatus::established);
        CHECK(record->objective_optimality==(expected.cost==0?HybridVerificationStatus::established:
            HybridVerificationStatus::refuted));
        CHECK(record->continuous_coverage==HybridVerificationStatus::established);
    }

    auto disjoint_system=system;
    disjoint_system.edges.push_back({{"infeasible"},{"middle"},{"terminal"},
        {UniversalSet{1},interval("two-stage-disjoint-guard",2,3)},
        {universal("two-stage-disjoint-unused-reset",2),identity}});
    const auto disjoint_built=build_hybrid_portfolio_programs(disjoint_system,request,
        {"two-stage-infeasible-relation"},{2,16},{64,512,8192});
    REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(disjoint_built));
    const auto& disjoint_programs=std::get<std::vector<HybridPathProgram>>(disjoint_built);
    const auto disjoint_result=verify_hybrid_portfolio_family(verifier,disjoint_system,request,
        disjoint_programs,{}, {2,16},{0,0});
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(disjoint_result));
    const auto& disjoint_report=std::get<HybridFamilyVerificationReport>(disjoint_result);
    CHECK(disjoint_report.global_objective_optimality==HybridVerificationStatus::unsupported);
    const auto infeasible_record=std::find_if(disjoint_report.branches.begin(),
        disjoint_report.branches.end(),[](const auto& branch) {
            return branch.path.edges.back().value=="infeasible";
        });
    REQUIRE(infeasible_record!=disjoint_report.branches.end());
    CHECK(infeasible_record->feasibility==HybridVerificationStatus::unsupported);
    CHECK(infeasible_record->continuous_coverage==HybridVerificationStatus::unsupported);
}

TEST_CASE("independent continuous oracle retains ties across differently sized terminal modes") {
    const auto interval=[](std::string id,double lower,double upper) {
        return h_set(std::move(id),1,Matrix{2,1,{-1,1}},Vector{-lower,upper},
            Matrix{0,1,{}},Vector{});
    };
    model::HybridMode source{{"oracle-source"},1,1,{"x"},{"u"}};
    source.flow=LinearStage{Matrix{1,1,{1}},Matrix{1,1,{0}},Matrix{1,0,{}},Vector{0}};
    source.control_sets={interval("oracle-continuous-control",0,1)};
    source.invariants={UniversalSet{1},UniversalSet{1}};
    const auto terminal_mode=[](std::string id,std::size_t dimension) {
        std::vector<std::string> labels;
        for(std::size_t i=0;i<dimension;++i) labels.push_back("terminal-"+std::to_string(i));
        model::HybridMode mode{{std::move(id)},dimension,0,std::move(labels),{}};
        mode.flow=LinearStage{Matrix{dimension,dimension,std::vector<double>(dimension*dimension,0)},
            Matrix{dimension,0,{}},Matrix{dimension,0,{}},Vector(dimension,0)};
        mode.control_sets={UniversalSet{0}};
        mode.invariants={UniversalSet{dimension},UniversalSet{dimension}};
        return mode;
    };
    auto terminal_a=terminal_mode("terminal-a",1);
    auto terminal_b=terminal_mode("terminal-b",2);
    auto terminal_c=terminal_mode("terminal-c",1);
    model::HybridSystem system{1,{source,terminal_a,terminal_b,terminal_c},
        {{{"to-a"},source.id,terminal_a.id,{UniversalSet{1}},
            {singleton_relation("oracle-reset-a",{0,0})}},
         {{"to-b"},source.id,terminal_b.id,{UniversalSet{1}},
            {singleton_relation("oracle-reset-b",{0,0,0})}},
         {{"to-c"},source.id,terminal_c.id,{UniversalSet{1}},
            {singleton_relation("oracle-reset-c",{0,0})}}}};
    model::HybridRequest request{{source.id,{0}},
        {terminal_a.id,terminal_b.id,terminal_c.id},
        {{terminal_a.id,LinearTerminal{{0},5},"cost","units"},
         {terminal_b.id,LinearTerminal{{0,0},5},"cost","units"},
         {terminal_c.id,LinearTerminal{{0},7},"cost","units"}}};

    struct OracleBranch { model::HybridPath path; Vector terminal; double objective{}; };
    std::vector<OracleBranch> oracle;
    // Interpret the raw one-step graph independently: the source flow leaves
    // the pre-transition state at zero, each reset is a literal singleton,
    // and u remains free on [0,1]. No production enumerator, composer,
    // objective lift, or verifier participates in this calculation.
    for(const auto& edge:system.edges) {
        if(edge.source!=request.initial.mode ||
           std::find(request.allowed_terminal_modes.begin(),request.allowed_terminal_modes.end(),
               edge.target)==request.allowed_terminal_modes.end()) continue;
        const auto* flow=std::get_if<LinearStage>(&source.flow);
        REQUIRE(flow!=nullptr);
        const double pre=flow->A.values[0]*request.initial.state[0]+
            flow->offset[0];
        const auto target=std::find_if(system.modes.begin(),system.modes.end(),
            [&](const auto& mode){return mode.id==edge.target;});
        REQUIRE(target!=system.modes.end());
        const auto reset=sets::from_handle(edge.reset_relations[0]);
        REQUIRE(std::holds_alternative<sets::SetData>(reset));
        const auto reset_rep=std::get<sets::SetData>(reset).representation();
        REQUIRE(std::holds_alternative<sets::SingletonRepresentation>(reset_rep));
        const auto& point=std::get<sets::SingletonRepresentation>(reset_rep).point;
        REQUIRE(point.size()==1+target->state_dimension);
        REQUIRE(point[0]==pre);
        Vector terminal(target->state_dimension);
        for(std::size_t i=0;i<terminal.size();++i) terminal[i]=point[1+i];
        const auto objective=std::find_if(request.terminal_objectives.begin(),
            request.terminal_objectives.end(),[&](const auto& item){return item.mode==edge.target;});
        REQUIRE(objective!=request.terminal_objectives.end());
        const auto* linear=std::get_if<LinearTerminal>(&objective->objective);
        REQUIRE(linear!=nullptr);
        REQUIRE(linear->coefficients.size()==terminal.size());
        double cost=linear->offset;
        for(std::size_t i=0;i<terminal.size();++i) cost+=linear->coefficients[i]*terminal[i];
        oracle.push_back({{{source.id,edge.target},{edge.id}},std::move(terminal),cost});
    }
    REQUIRE(oracle.size()==3);
    CHECK(oracle[0].objective==5);
    CHECK(oracle[1].objective==5);
    CHECK(oracle[2].objective==7);

    const auto literal_optimal_face=[](std::string id,std::size_t terminal_dimension) {
        const std::size_t variables=3+terminal_dimension;
        std::vector<double> inequalities(2*variables,0);
        inequalities[1]=-1;
        inequalities[variables+1]=1;
        std::vector<double> equalities((2+terminal_dimension)*variables,0);
        equalities[0]=1;
        equalities[variables+2]=1;
        for(std::size_t i=0;i<terminal_dimension;++i)
            equalities[(2+i)*variables+3+i]=1;
        return h_set(std::move(id),variables,
            Matrix{2,variables,std::move(inequalities)},Vector{0,1},
            Matrix{2+terminal_dimension,variables,std::move(equalities)},
            Vector(2+terminal_dimension,0));
    };
    const auto evaluate=[&](const model::HybridRequest& current_request,
        const std::string& problem) {
        const auto built=build_hybrid_portfolio_programs(system,current_request,{problem},
            {1,8},{16,128,2048});
        REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(built));
        const auto& programs=std::get<std::vector<HybridPathProgram>>(built);
        REQUIRE(programs.size()==oracle.size());
        std::vector<HybridPathOptimalFaceCandidate> candidates;
        std::vector<double> costs;
        for(const auto& expected:oracle) {
            const auto objective=std::find_if(current_request.terminal_objectives.begin(),
                current_request.terminal_objectives.end(),[&](const auto& item) {
                    return item.mode==expected.path.modes.back();
                });
            REQUIRE(objective!=current_request.terminal_objectives.end());
            const auto& linear=std::get<LinearTerminal>(objective->objective);
            double cost=linear.offset;
            for(std::size_t i=0;i<expected.terminal.size();++i)
                cost+=linear.coefficients[i]*expected.terminal[i];
            costs.push_back(cost);
        }
        const auto global_minimum=*std::min_element(costs.begin(),costs.end());
        for(std::size_t branch_index=0;branch_index<oracle.size();++branch_index) {
            const auto& expected=oracle[branch_index];
            const auto found=std::find_if(programs.begin(),programs.end(),[&](const auto& program) {
                return program.path==expected.path;
            });
            REQUIRE(found!=programs.end());
            const auto expected_dimension=3+expected.terminal.size();
            CHECK(found->joint_relation.metadata()->set.dimension==expected_dimension);
            const auto representation=found->joint_relation.representation();
            REQUIRE(std::holds_alternative<sets::HRepresentation>(representation));
            const auto& relation=std::get<sets::HRepresentation>(representation);
            for(const double u:{0.0,0.5,1.0}) {
                Vector joint{0,u,0};
                joint.insert(joint.end(),expected.terminal.begin(),expected.terminal.end());
                CHECK(satisfies(relation,joint));
            }
            for(const double u:{-0.125,1.125}) {
                Vector joint{0,u,0};
                joint.insert(joint.end(),expected.terminal.begin(),expected.terminal.end());
                CHECK_FALSE(satisfies(relation,joint));
            }
            if(costs[branch_index]==global_minimum) {
                Vector witness{0,0,0};
                witness.insert(witness.end(),expected.terminal.begin(),expected.terminal.end());
                auto candidate=exact_candidate(*found,std::move(witness));
                const auto face=sets::from_handle(literal_optimal_face(
                    "literal-cross-mode-face-"+expected.path.edges.front().value,
                    expected.terminal.size()));
                REQUIRE(std::holds_alternative<sets::SetData>(face));
                candidate.relation=std::get<sets::SetData>(face);
                candidates.push_back(std::move(candidate));
            }
        }
        ExactLinearHHybridFamilyVerifier verifier;
        return verify_hybrid_portfolio_family(verifier,system,current_request,programs,
            candidates,{1,8},{0,0});
    };

    const auto tied=evaluate(request,"cross-terminal-mode-tie");
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(tied));
    const auto& tied_report=std::get<HybridFamilyVerificationReport>(tied);
    CHECK(tied_report.global_objective_optimality==HybridVerificationStatus::established);
    CHECK(tied_report.complete_family_coverage==HybridVerificationStatus::established);
    REQUIRE(tied_report.branches.size()==3);
    const auto status_for=[&](const HybridFamilyVerificationReport& report,const std::string& id) {
        return std::find_if(report.branches.begin(),report.branches.end(),[&](const auto& branch) {
            return branch.path.edges.front().value==id;
        });
    };
    for(const auto& id:{"to-a","to-b"}) {
        const auto branch=status_for(tied_report,id);
        REQUIRE(branch!=tied_report.branches.end());
        CHECK(branch->objective_optimality==HybridVerificationStatus::established);
        CHECK(branch->continuous_coverage==HybridVerificationStatus::established);
    }
    const auto worse=status_for(tied_report,"to-c");
    REQUIRE(worse!=tied_report.branches.end());
    CHECK(worse->objective_optimality==HybridVerificationStatus::refuted);

    auto separated=request;
    separated.terminal_objectives[1].objective=LinearTerminal{{0,0},5.25};
    const auto broken_tie=evaluate(separated,"cross-terminal-mode-offset-change");
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(broken_tie));
    const auto& separated_report=std::get<HybridFamilyVerificationReport>(broken_tie);
    CHECK(separated_report.global_objective_optimality==HybridVerificationStatus::established);
    CHECK(separated_report.complete_family_coverage==HybridVerificationStatus::established);
    const auto separated_a=status_for(separated_report,"to-a");
    const auto separated_b=status_for(separated_report,"to-b");
    const auto separated_c=status_for(separated_report,"to-c");
    REQUIRE(separated_a!=separated_report.branches.end());
    REQUIRE(separated_b!=separated_report.branches.end());
    REQUIRE(separated_c!=separated_report.branches.end());
    CHECK(separated_a->objective_optimality==HybridVerificationStatus::established);
    CHECK(separated_b->objective_optimality==HybridVerificationStatus::refuted);
    CHECK(separated_c->objective_optimality==HybridVerificationStatus::refuted);
}

TEST_CASE("independent two-stage continuous oracle ties terminal modes after a guarded set-valued reset") {
    const auto interval=[](std::string id,double lower,double upper) {
        return h_set(std::move(id),1,Matrix{2,1,{-1,1}},Vector{-lower,upper},
            Matrix{0,1,{}},Vector{});
    };
    const auto first_coordinate_interval=[](std::string id,double lower,double upper) {
        return h_set(std::move(id),2,Matrix{2,2,{-1,0,1,0}},Vector{-lower,upper},
            Matrix{0,2,{}},Vector{});
    };
    const auto identity_flow=[](std::size_t dimension) {
        Matrix A{dimension,dimension,Vector(dimension*dimension)};
        for(std::size_t i=0;i<dimension;++i) A.values[i*dimension+i]=1;
        return LinearStage{std::move(A),Matrix{dimension,0,{}},Matrix{dimension,0,{}},Vector(dimension,0)};
    };
    auto source_control=interval("oracle-guarded-reset-control",0,1);
    model::HybridMode source{{"oracle-guarded-reset-source"},1,1,{"x"},{"u"}};
    const LinearStage source_flow{Matrix{1,1,{0}},Matrix{1,1,{1}},Matrix{1,0,{}},Vector{0}};
    source.flow=std::vector<LinearStage>{source_flow,source_flow};
    source.control_sets={source_control,source_control};
    source.invariants={UniversalSet{1},UniversalSet{1},UniversalSet{1}};

    model::HybridMode middle{{"oracle-guarded-reset-middle"},2,0,{"p","q"},{}};
    middle.flow=std::vector<LinearStage>{identity_flow(2),identity_flow(2)};
    middle.control_sets={UniversalSet{0},UniversalSet{0}};
    middle.invariants={UniversalSet{2},UniversalSet{2},UniversalSet{2}};

    model::HybridMode terminal_a{{"oracle-guarded-reset-terminal-a"},1,0,{"a"},{}};
    terminal_a.flow=std::vector<LinearStage>{identity_flow(1),identity_flow(1)};
    terminal_a.control_sets={UniversalSet{0},UniversalSet{0}};
    terminal_a.invariants={UniversalSet{1},UniversalSet{1},UniversalSet{1}};
    model::HybridMode terminal_b{{"oracle-guarded-reset-terminal-b"},2,0,{"b0","b1"},{}};
    terminal_b.flow=std::vector<LinearStage>{identity_flow(2),identity_flow(2)};
    terminal_b.control_sets={UniversalSet{0},UniversalSet{0}};
    terminal_b.invariants={UniversalSet{2},UniversalSet{2},UniversalSet{2}};

    const auto source_to_middle=h_set("oracle-guarded-reset-set-valued",3,
        Matrix{2,3,{0,0,-1, 0,0,1}},Vector{0,1},
        Matrix{1,3,{-1,1,0}},Vector{0});
    const auto middle_to_a=h_set("oracle-guarded-reset-drop-q",3,
        Matrix{0,3,{}},Vector{},Matrix{1,3,{-1,0,1}},Vector{0});
    const auto middle_to_b=h_set("oracle-guarded-reset-preserve-q",4,
        Matrix{0,4,{}},Vector{},Matrix{2,4,{-1,0,1,0, 0,-1,0,1}},Vector{0,0});
    model::HybridSystem system{2,{source,middle,terminal_a,terminal_b},
        {{{"oracle-enter-middle"},source.id,middle.id,
            {UniversalSet{1},UniversalSet{1}},{source_to_middle,source_to_middle}},
         {{"oracle-finish-a"},middle.id,terminal_a.id,
            {first_coordinate_interval("oracle-unused-a-guard",0,1),
             first_coordinate_interval("oracle-a-guard",0,0.5)},
            {middle_to_a,middle_to_a}},
         {{"oracle-finish-b"},middle.id,terminal_b.id,
            {first_coordinate_interval("oracle-unused-b-guard",0,1),
             first_coordinate_interval("oracle-b-guard",0.5,1)},
            {middle_to_b,middle_to_b}}}};
    model::HybridRequest request{{source.id,{0}},{terminal_a.id,terminal_b.id},
        {{terminal_a.id,LinearTerminal{{1},0},"terminal cost","units"},
         {terminal_b.id,LinearTerminal{{1,0},-0.5},"terminal cost","units"}}};

    // Independent raw graph and equation oracle. It does not call the
    // production path enumerator, relation composer, or verifier.
    std::vector<model::HybridPath> oracle_paths{{{source.id},{}}};
    for(std::size_t stage=0;stage<system.horizon;++stage) {
        std::vector<model::HybridPath> next;
        for(const auto& prefix:oracle_paths) for(const auto& edge:system.edges) {
            if(edge.source!=prefix.modes.back()) continue;
            auto extended=prefix;
            extended.edges.push_back(edge.id);
            extended.modes.push_back(edge.target);
            next.push_back(std::move(extended));
        }
        oracle_paths=std::move(next);
    }
    oracle_paths.erase(std::remove_if(oracle_paths.begin(),oracle_paths.end(),[&](const auto& path) {
        return std::find(request.allowed_terminal_modes.begin(),request.allowed_terminal_modes.end(),
            path.modes.back())==request.allowed_terminal_modes.end();
    }),oracle_paths.end());
    const std::vector<model::HybridPath> expected_paths{
        {{source.id,middle.id,terminal_a.id},{{"oracle-enter-middle"},{"oracle-finish-a"}}},
        {{source.id,middle.id,terminal_b.id},{{"oracle-enter-middle"},{"oracle-finish-b"}}}};
    REQUIRE(oracle_paths==expected_paths);

    // Read the small raw H data and affine equations directly. The source flow
    // gives pre1=u, the first reset gives p=pre1 and 0<=q<=1, and the middle
    // flow is identity. Each second-edge guard therefore clips u directly;
    // its reset maps the first terminal coordinate to p. No composed relation
    // or production objective lift is used to derive these bounds or costs.
    const auto coordinate_interval=[](const sets::HRepresentation& h,std::size_t coordinate) {
        std::pair<double,double> bounds{-std::numeric_limits<double>::infinity(),
            std::numeric_limits<double>::infinity()};
        for(std::size_t row=0;row<h.inequalities.rows();++row) {
            double coefficient=h.inequalities(row,coordinate);
            for(std::size_t col=0;col<h.inequalities.cols();++col)
                if(col!=coordinate&&h.inequalities(row,col)!=0)
                    throw std::runtime_error("Oracle expects axis-aligned raw constraints");
            if(coefficient<0) bounds.first=std::max(bounds.first,h.upper_bounds[row]/coefficient);
            else if(coefficient>0) bounds.second=std::min(bounds.second,h.upper_bounds[row]/coefficient);
            else if(h.upper_bounds[row]<0) return std::pair{1.0,0.0};
        }
        return bounds;
    };
    const auto h_rep=[](const SetHandle& handle) -> sets::HRepresentation {
        const auto data=sets::from_handle(handle);
        if(!std::holds_alternative<sets::SetData>(data)) throw std::runtime_error("Oracle H input is invalid");
        const auto representation=std::get<sets::SetData>(data).representation();
        if(!std::holds_alternative<sets::HRepresentation>(representation))
            throw std::runtime_error("Oracle expects literal raw H input");
        return std::get<sets::HRepresentation>(representation);
    };
    const auto raw_reset=h_rep(system.edges.front().reset_relations[0]);
    REQUIRE(raw_reset.equalities.rows()==1);
    CHECK(raw_reset.equalities(0,0)==-1);
    CHECK(raw_reset.equalities(0,1)==1);
    const auto existential_q=coordinate_interval(raw_reset,2);
    CHECK(existential_q.first==0);
    CHECK(existential_q.second==1);
    const auto& raw_middle_flow=std::get<std::vector<LinearStage>>(middle.flow)[1];
    CHECK(raw_middle_flow.A.values==std::vector<double>{1,0,0,1});
    const auto input_bounds=coordinate_interval(h_rep(std::get<SetHandle>(source.control_sets[0])),0);

    struct OracleResult { model::HybridPath path; double minimizing_u; double objective; };
    std::vector<OracleResult> oracle;
    for(const auto& path:oracle_paths) {
        const auto second_edge=std::find_if(system.edges.begin(),system.edges.end(),[&](const auto& edge) {
            return edge.id==path.edges[1];
        });
        REQUIRE(second_edge!=system.edges.end());
        const auto guard_bounds=coordinate_interval(h_rep(std::get<SetHandle>(second_edge->guards[1])),0);
        const auto target_reset=h_rep(second_edge->reset_relations[1]);
        if(path.modes.back()==terminal_a.id) {
            REQUIRE(target_reset.equalities.rows()==1);
            CHECK(target_reset.equalities(0,0)==-1);
            CHECK(target_reset.equalities(0,2)==1);
        } else {
            REQUIRE(target_reset.equalities.rows()==2);
            CHECK(target_reset.equalities(0,0)==-1);
            CHECK(target_reset.equalities(0,2)==1);
            CHECK(target_reset.equalities(1,1)==-1);
            CHECK(target_reset.equalities(1,3)==1);
        }
        const double slope=source_flow.B.values[0];
        REQUIRE(slope==1);
        const double flow_offset=source_flow.offset[0];
        double lower_u=std::max(input_bounds.first,(guard_bounds.first-flow_offset)/slope);
        double upper_u=std::min(input_bounds.second,(guard_bounds.second-flow_offset)/slope);
        REQUIRE(lower_u<=upper_u);
        const auto objective=std::find_if(request.terminal_objectives.begin(),request.terminal_objectives.end(),
            [&](const auto& item){return item.mode==path.modes.back();});
        REQUIRE(objective!=request.terminal_objectives.end());
        const auto& linear=std::get<LinearTerminal>(objective->objective);
        const double terminal_slope=linear.coefficients[0]*slope;
        const double lower_cost=terminal_slope*lower_u+linear.offset+linear.coefficients[0]*flow_offset;
        const double upper_cost=terminal_slope*upper_u+linear.offset+linear.coefficients[0]*flow_offset;
        const double minimum=std::min(lower_cost,upper_cost);
        const double minimizing_u=lower_cost<=upper_cost?lower_u:upper_u;
        oracle.push_back({path,minimizing_u,minimum});
    }
    REQUIRE(oracle.size()==2);
    CHECK(oracle[0].minimizing_u==0);
    CHECK(oracle[1].minimizing_u==0.5);
    CHECK(oracle[0].objective==0);
    CHECK(oracle[1].objective==0);
    CHECK(oracle[0].objective==oracle[1].objective);

    const auto built=build_hybrid_portfolio_programs(system,request,
        {"oracle-guarded-reset-cross-mode-tie"},{2,8},{32,256,8192});
    std::string admission_debug="variant "+std::to_string(built.index());
    if(const auto* errors=std::get_if<Diagnostics>(&built))
        for(const auto& diagnostic:*errors)
            admission_debug+="; "+diagnostic.field+": "+diagnostic.explanation;
    if(const auto* failure=std::get_if<model::HybridPathCompositionFailureReport>(&built)) {
        if(const auto* diagnostic=std::get_if<Diagnostic>(&failure->failure))
            admission_debug+="; "+diagnostic->field+": "+diagnostic->explanation;
        else if(const auto* stopped=std::get_if<OperationStopped>(&failure->failure))
            admission_debug+="; stopped: "+stopped->diagnostics;
    }
    CAPTURE(admission_debug);
    REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(built));
    const auto& programs=std::get<std::vector<HybridPathProgram>>(built);
    REQUIRE(programs.size()==oracle.size());
    for(std::size_t i=0;i<oracle.size();++i) CHECK(programs[i].path==oracle[i].path);

    const auto literal_face=[&](std::size_t width,std::size_t pre_middle,
        std::size_t q_middle,std::size_t terminal,double optimal_u,bool preserve_q) {
        std::vector<Vector> inequalities;
        Vector bounds;
        const auto add_le=[&](std::initializer_list<std::pair<std::size_t,double>> terms,double rhs) {
            Vector row(width);
            for(const auto [column,value]:terms) row[column]=value;
            inequalities.push_back(std::move(row));
            bounds.push_back(rhs);
        };
        std::vector<Vector> equalities;
        Vector values;
        const auto add_eq=[&](std::initializer_list<std::pair<std::size_t,double>> terms,double rhs) {
            Vector row(width);
            for(const auto [column,value]:terms) row[column]=value;
            equalities.push_back(std::move(row));
            values.push_back(rhs);
        };
        add_le({{1,-1}},0); add_le({{1,1}},1);
        add_le({{4,-1}},0); add_le({{4,1}},1);
        if(optimal_u==0) { add_le({{pre_middle,-1}},0); add_le({{pre_middle,1}},0.5); }
        else { add_le({{pre_middle,-1}},-0.5); add_le({{pre_middle,1}},1); }
        add_eq({{0,1}},0);
        add_eq({{2,1},{1,-1}},0);
        add_eq({{3,1},{2,-1}},0);
        add_eq({{5,1},{3,-1}},0);
        add_eq({{6,1},{4,-1}},0);
        add_eq({{1,1}},optimal_u);
        add_eq({{terminal,1},{5,-1}},0);
        if(preserve_q) add_eq({{terminal+1,1},{6,-1}},0);
        const auto flatten=[&](const std::vector<Vector>& rows) {
            Vector flat;
            flat.reserve(rows.size()*width);
            for(const auto& row:rows) flat.insert(flat.end(),row.begin(),row.end());
            return flat;
        };
        return h_set("literal-guarded-reset-face",width,
            Matrix{inequalities.size(),width,flatten(inequalities)},std::move(bounds),
            Matrix{equalities.size(),width,flatten(equalities)},std::move(values));
    };

    std::vector<HybridPathOptimalFaceCandidate> candidates;
    for(const auto& expected:oracle) {
        const auto program=std::find_if(programs.begin(),programs.end(),[&](const auto& item) {
            return item.path==expected.path;
        });
        REQUIRE(program!=programs.end());
        const bool preserve_q=expected.path.modes.back()==terminal_b.id;
        const std::size_t width=preserve_q?9:8;
        CHECK(program->joint_relation.metadata()->set.dimension==width);
        const std::size_t terminal=width-(preserve_q?2:1);
        Vector witness(width);
        witness[1]=expected.minimizing_u;
        witness[2]=expected.minimizing_u;
        witness[3]=expected.minimizing_u;
        witness[4]=0.25;
        witness[5]=expected.minimizing_u;
        witness[6]=0.25;
        witness[terminal]=expected.minimizing_u;
        if(preserve_q) witness[terminal+1]=0.25;
        auto candidate=exact_candidate(*program,std::move(witness));
        const auto face=sets::from_handle(literal_face(width,5,6,terminal,
            expected.minimizing_u,preserve_q));
        REQUIRE(std::holds_alternative<sets::SetData>(face));
        candidate.relation=std::get<sets::SetData>(face);
        candidates.push_back(std::move(candidate));
    }
    ExactLinearHHybridFamilyVerifier verifier;
    const auto verified=verify_hybrid_portfolio_family(verifier,system,request,programs,
        candidates,{2,8},{0,0});
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(verified));
    const auto& report=std::get<HybridFamilyVerificationReport>(verified);
    CHECK(report.global_objective_optimality==HybridVerificationStatus::established);
    CHECK(report.complete_family_coverage==HybridVerificationStatus::established);
    REQUIRE(report.branches.size()==2);
    for(const auto& branch:report.branches) {
        CHECK(branch.feasibility==HybridVerificationStatus::established);
        CHECK(branch.objective_optimality==HybridVerificationStatus::established);
        CHECK(branch.continuous_coverage==HybridVerificationStatus::established);
    }
}

TEST_CASE("exact linear H verifier covers a two-stage coupled control polygon through a set-valued reset") {
    const auto triangle=[](const std::string& id) {
        return h_set(id,2,Matrix{3,2,{-1,0,0,-1,1,1}},Vector{0,0,1},
            Matrix{0,2,{}},Vector{});
    };
    const auto source_reset=h_set("two-stage-coupled-reset",3,
        Matrix{2,3,{0,0,-1,0,0,1}},Vector{0,1},
        Matrix{1,3,{-1,1,0}},Vector{0});
    const auto terminal_reset=h_set("two-stage-coupled-terminal-reset",3,
        Matrix{0,3,{}},Vector{},Matrix{1,3,{-1,0,1}},Vector{0});
    const LinearStage source_flow{Matrix{1,1,{0}},Matrix{1,2,{1,1}},
        Matrix{1,0,{}},Vector{0}};
    const LinearStage middle_flow{Matrix{2,2,{0,1,0,0}},Matrix{2,2,{1,1,0,0}},
        Matrix{2,0,{}},Vector{0,0}};
    const auto identity_flow=[](std::size_t dimension) {
        Matrix A{dimension,dimension,Vector(dimension*dimension)};
        for(std::size_t i=0;i<dimension;++i) A.values[i*dimension+i]=1;
        return LinearStage{std::move(A),Matrix{dimension,0,{}},Matrix{dimension,0,{}},
            Vector(dimension,0)};
    };
    model::HybridMode source{{"two-stage-coupled-source"},1,2,{"x"},{"u","v"}};
    source.flow=std::vector<LinearStage>{source_flow,source_flow};
    source.control_sets={triangle("two-stage-coupled-source-control-0"),
        triangle("two-stage-coupled-source-control-1")};
    source.invariants={UniversalSet{1},UniversalSet{1},UniversalSet{1}};
    model::HybridMode middle{{"two-stage-coupled-middle"},2,2,{"p","q"},{"r","s"}};
    middle.flow=std::vector<LinearStage>{middle_flow,middle_flow};
    middle.control_sets={triangle("two-stage-coupled-middle-control-0"),
        triangle("two-stage-coupled-middle-control-1")};
    middle.invariants={UniversalSet{2},UniversalSet{2},UniversalSet{2}};
    model::HybridMode terminal{{"two-stage-coupled-terminal"},1,0,{"y"},{}};
    terminal.flow=std::vector<LinearStage>{identity_flow(1),identity_flow(1)};
    terminal.control_sets={UniversalSet{0},UniversalSet{0}};
    terminal.invariants={UniversalSet{1},UniversalSet{1},UniversalSet{1}};
    model::HybridSystem system{2,{source,middle,terminal},
        {{{"two-stage-coupled-enter"},source.id,middle.id,
            {UniversalSet{1},UniversalSet{1}},{source_reset,source_reset}},
         {{"two-stage-coupled-finish"},middle.id,terminal.id,
            {UniversalSet{2},UniversalSet{2}},{terminal_reset,terminal_reset}}}};
    model::HybridRequest request{{source.id,{0}},{terminal.id},
        {{terminal.id,LinearTerminal{{1},0},"terminal value","units"}}};
    const model::HybridPath path{{source.id,middle.id,terminal.id},
        {{"two-stage-coupled-enter"},{"two-stage-coupled-finish"}}};
    const auto built=build_hybrid_portfolio_programs(system,request,
        {"two-stage-coupled-polygon"},{2,8},{64,512,32768});
    std::string build_errors;
    if(const auto* diagnostics=std::get_if<Diagnostics>(&built))
        for(const auto& diagnostic:*diagnostics)
            build_errors+=diagnostic.field+": "+diagnostic.explanation+"; ";
    if(const auto* failure=std::get_if<model::HybridPathCompositionFailureReport>(&built))
        if(const auto* diagnostic=std::get_if<Diagnostic>(&failure->failure))
            build_errors+=diagnostic->field+": "+diagnostic->explanation;
    CAPTURE(build_errors);
    REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(built));
    const auto& programs=std::get<std::vector<HybridPathProgram>>(built);
    REQUIRE(programs.size()==1);
    CHECK(programs.front().path==path);
    REQUIRE(programs.front().joint_relation.metadata()->set.dimension==11);
    const auto& authored_objective=std::get<LinearTerminal>(request.terminal_objectives[0].objective);
    CHECK(authored_objective.coefficients==Vector{1});
    CHECK(authored_objective.offset==0);
    const auto& lifted_objective=std::get<LinearTerminal>(programs.front().lifted_objective);
    CHECK(lifted_objective.coefficients==Vector{0,0,0,0,0,0,0,0,0,0,1});

    // Joint coordinates are ordered as x0, (u0,v0), x_pre1, (p1,q1),
    // (r1,s1), (p_pre2,q_pre2), y2. Independently read every authored raw
    // equation used below: x_pre1=u0+v0, p1=x_pre1, q1 in [0,1],
    // p_pre2=q1+r1+s1, q_pre2=0, and y2=p_pre2. Since q1,r1,s1 are
    // nonnegative, minimizing y2 fixes q1=r1=s1=y2=0 while leaving the
    // entire first-stage control triangle free.
    const auto raw_control=sets::from_handle(std::get<SetHandle>(source.control_sets[0]));
    REQUIRE(std::holds_alternative<sets::SetData>(raw_control));
    const auto control_h=std::get<sets::HRepresentation>(
        std::get<sets::SetData>(raw_control).representation());
    REQUIRE(control_h.inequalities.rows()==3);
    CHECK(control_h.inequalities(0,0)==-1);
    CHECK(control_h.inequalities(1,1)==-1);
    CHECK(control_h.inequalities(2,0)==1);
    CHECK(control_h.inequalities(2,1)==1);
    const auto raw_middle_control=sets::from_handle(
        std::get<SetHandle>(middle.control_sets[1]));
    REQUIRE(std::holds_alternative<sets::SetData>(raw_middle_control));
    const auto middle_control_h=std::get<sets::HRepresentation>(
        std::get<sets::SetData>(raw_middle_control).representation());
    REQUIRE(middle_control_h.inequalities.rows()==3);
    CHECK(middle_control_h.inequalities(0,0)==-1);
    CHECK(middle_control_h.inequalities(1,1)==-1);
    CHECK(middle_control_h.inequalities(2,0)==1);
    CHECK(middle_control_h.inequalities(2,1)==1);
    const auto reset_h=std::get<sets::HRepresentation>(
        std::get<sets::SetData>(sets::from_handle(source_reset)).representation());
    REQUIRE(reset_h.inequalities.rows()==2);
    CHECK(reset_h.inequalities(0,2)==-1);
    CHECK(reset_h.upper_bounds[0]==0);
    CHECK(reset_h.inequalities(1,2)==1);
    CHECK(reset_h.upper_bounds[1]==1);
    CHECK(reset_h.equalities(0,0)==-1);
    CHECK(reset_h.equalities(0,1)==1);
    const auto& raw_source_flows=std::get<std::vector<LinearStage>>(source.flow);
    REQUIRE(raw_source_flows.size()==2);
    for(const auto& flow:raw_source_flows) {
        CHECK(flow.A.values==Vector{0});
        CHECK(flow.B.values==Vector{1,1});
        CHECK(flow.E.values.empty());
        CHECK(flow.offset==Vector{0});
    }
    const auto& raw_middle_flows=std::get<std::vector<LinearStage>>(middle.flow);
    REQUIRE(raw_middle_flows.size()==2);
    CHECK(raw_middle_flows[1].A.values==Vector{0,1,0,0});
    CHECK(raw_middle_flows[1].B.values==Vector{1,1,0,0});
    CHECK(raw_middle_flows[1].E.values.empty());
    CHECK(raw_middle_flows[1].offset==Vector{0,0});
    const auto terminal_reset_h=std::get<sets::HRepresentation>(
        std::get<sets::SetData>(sets::from_handle(terminal_reset)).representation());
    REQUIRE(terminal_reset_h.equalities.rows()==1);
    CHECK(terminal_reset_h.equalities(0,0)==-1);
    CHECK(terminal_reset_h.equalities(0,1)==0);
    CHECK(terminal_reset_h.equalities(0,2)==1);
    CHECK(terminal_reset_h.equality_values[0]==0);

    constexpr std::size_t joint_width=11;
    constexpr std::size_t initial_x=0,first_u=1,first_v=2,first_pre=3;
    constexpr std::size_t middle_p=4,middle_q=5,second_r=6,second_s=7;
    constexpr std::size_t second_pre_p=8,second_pre_q=9,terminal_y=10;
    std::vector<Vector> inequalities;
    Vector upper_bounds;
    const auto add_le=[&](std::initializer_list<std::pair<std::size_t,double>> terms,double rhs) {
        Vector row(joint_width);
        for(const auto [coordinate,value]:terms) row[coordinate]=value;
        inequalities.push_back(std::move(row));
        upper_bounds.push_back(rhs);
    };
    add_le({{first_u,-1}},0); add_le({{first_v,-1}},0);
    add_le({{first_u,1},{first_v,1}},1);
    add_le({{second_r,-1}},0); add_le({{second_s,-1}},0);
    add_le({{second_r,1},{second_s,1}},1);
    add_le({{middle_q,-1}},0); add_le({{middle_q,1}},1);
    std::vector<Vector> equalities;
    Vector equality_values;
    const auto add_eq=[&](std::initializer_list<std::pair<std::size_t,double>> terms,double rhs) {
        Vector row(joint_width);
        for(const auto [coordinate,value]:terms) row[coordinate]=value;
        equalities.push_back(std::move(row));
        equality_values.push_back(rhs);
    };
    add_eq({{initial_x,1}},0);
    add_eq({{first_pre,1},{first_u,-1},{first_v,-1}},0);
    add_eq({{middle_p,1},{first_pre,-1}},0);
    add_eq({{second_pre_p,1},{middle_q,-1},{second_r,-1},{second_s,-1}},0);
    add_eq({{second_pre_q,1}},0);
    add_eq({{terminal_y,1},{second_pre_p,-1}},0);
    add_eq({{terminal_y,1}},0);
    const auto flatten=[](const std::vector<Vector>& rows) {
        Vector values;
        values.reserve(rows.size()*joint_width);
        for(const auto& row:rows) values.insert(values.end(),row.begin(),row.end());
        return values;
    };
    const auto full_face=h_set("two-stage-coupled-full-face",joint_width,
        Matrix{inequalities.size(),joint_width,flatten(inequalities)},upper_bounds,
        Matrix{equalities.size(),joint_width,flatten(equalities)},equality_values);
    auto complete=exact_candidate(programs.front(),{0,0.25,0.25,0.5,0.5,0,0,0,0,0,0});
    complete.relation=std::get<sets::SetData>(sets::from_handle(full_face));
    ExactLinearHHybridFamilyVerifier verifier;
    const std::array<HybridPathOptimalFaceCandidate,1> candidates{std::move(complete)};
    const auto verified=verify_hybrid_portfolio_family(verifier,system,request,
        programs,candidates,{2,8},{0,0});
    std::string verification_errors;
    if(const auto* diagnostics=std::get_if<Diagnostics>(&verified))
        for(const auto& diagnostic:*diagnostics)
            verification_errors+=diagnostic.field+": "+diagnostic.explanation+"; ";
    CAPTURE(verification_errors);
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(verified));
    const auto& report=std::get<HybridFamilyVerificationReport>(verified);
    CHECK(report.global_objective_optimality==HybridVerificationStatus::established);
    CHECK(report.complete_family_coverage==HybridVerificationStatus::established);
    REQUIRE(report.branches.size()==1);
    CHECK(report.branches.front().feasibility==HybridVerificationStatus::established);
    CHECK(report.branches.front().objective_optimality==HybridVerificationStatus::established);
    CHECK(report.branches.front().continuous_coverage==HybridVerificationStatus::established);

    auto narrowed_inequalities=inequalities;
    Vector cut(11);
    cut[first_u]=1;
    narrowed_inequalities.push_back(std::move(cut));
    auto narrow_face=h_set("two-stage-coupled-narrow-face",joint_width,
        Matrix{narrowed_inequalities.size(),joint_width,flatten(narrowed_inequalities)},
        [&] { auto bounds=upper_bounds; bounds.push_back(0.125); return bounds; }(),
        Matrix{equalities.size(),joint_width,flatten(equalities)},equality_values);
    auto narrowed=exact_candidate(programs.front(),{0,0.125,0,0.125,0.125,0,0,0,0,0,0});
    narrowed.relation=std::get<sets::SetData>(sets::from_handle(narrow_face));
    const std::array<HybridPathOptimalFaceCandidate,1> narrowed_candidates{std::move(narrowed)};
    const auto rejected=verify_hybrid_portfolio_family(verifier,system,request,
        programs,narrowed_candidates,{2,8},{0,0});
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(rejected));
    const auto& rejected_report=std::get<HybridFamilyVerificationReport>(rejected);
    CHECK(rejected_report.global_objective_optimality==HybridVerificationStatus::established);
    CHECK(rejected_report.complete_family_coverage==HybridVerificationStatus::refuted);
    REQUIRE(rejected_report.branches.size()==1);
    CHECK(rejected_report.branches.front().feasibility==HybridVerificationStatus::established);
    CHECK(rejected_report.branches.front().objective_optimality==HybridVerificationStatus::established);
    CHECK(rejected_report.branches.front().continuous_coverage==HybridVerificationStatus::refuted);
}

TEST_CASE("single-parameter scalar interval verifier covers arbitrary finite horizons") {
    const auto make_reset=[](const std::string& id,double pre,double post,double rhs) {
        auto inequalities=numeric::snapshot(Matrix{0,2,{}});
        auto upper=numeric::snapshot_vector(Vector{});
        auto equalities=numeric::snapshot(Matrix{1,2,{pre,post}});
        auto values=numeric::snapshot_vector(Vector{rhs});
        REQUIRE(std::holds_alternative<numeric::MatrixView>(inequalities));
        REQUIRE(std::holds_alternative<numeric::VectorView>(upper));
        REQUIRE(std::holds_alternative<numeric::MatrixView>(equalities));
        REQUIRE(std::holds_alternative<numeric::VectorView>(values));
        auto data=sets::make_h({SetId{id},2,{"pre","post"}},
            {std::get<numeric::MatrixView>(inequalities),std::get<numeric::VectorView>(upper),
             std::get<numeric::MatrixView>(equalities),std::get<numeric::VectorView>(values)});
        REQUIRE(std::holds_alternative<sets::SetData>(data));
        return std::get<sets::SetData>(std::move(data)).as_handle();
    };
    const auto scalar_mode=[](std::string id) {
        model::HybridMode mode{{std::move(id)},1,1,{"x"},{"u"}};
        const LinearStage flow{Matrix{1,1,{1}},Matrix{1,1,{1}},Matrix{1,0,{}},Vector{0}};
        mode.flow=std::vector<LinearStage>{flow,flow,flow};
        mode.control_sets={interval("multi-horizon-free",0,1),Singleton{{0}},Singleton{{0}}};
        mode.invariants={UniversalSet{1},UniversalSet{1},UniversalSet{1},UniversalSet{1}};
        return mode;
    };
    auto start=scalar_mode("start");
    auto middle=scalar_mode("middle");
    auto late=scalar_mode("late");
    auto terminal=scalar_mode("terminal");
    const auto identity=make_reset("multi-horizon-identity",1,-1,0);
    const auto constant_zero=make_reset("multi-horizon-zero",0,1,0);
    const auto constant_one=make_reset("multi-horizon-one",0,1,1);
    const std::vector<AdmissibleSet> universal_guards(3,UniversalSet{1});
    const std::vector<SetHandle> unused_resets(3,universal("multi-horizon-unused-reset",2));
    std::vector<model::HybridTransitionEdge> edges{
        {{"enter"},{"start"},{"middle"},universal_guards,{identity,unused_resets[1],unused_resets[2]}},
        {{"continue"},{"middle"},{"late"},universal_guards,{unused_resets[0],identity,unused_resets[2]}},
        {{"tie-a"},{"late"},{"terminal"},
            {UniversalSet{1},UniversalSet{1},interval("multi-horizon-guard-a",0,0.5)},
            {unused_resets[0],unused_resets[1],constant_zero}},
        {{"tie-b"},{"late"},{"terminal"},
            {UniversalSet{1},UniversalSet{1},interval("multi-horizon-guard-b",0,1)},
            {unused_resets[0],unused_resets[1],constant_zero}},
        {{"worse"},{"late"},{"terminal"},
            {UniversalSet{1},UniversalSet{1},Singleton{{1}}},
            {unused_resets[0],unused_resets[1],constant_one}}};
    model::HybridSystem system{3,{start,middle,late,terminal},std::move(edges)};
    model::HybridRequest request{{{"start"},{0}},{{"terminal"}},
        {{{"terminal"},LinearTerminal{{1},0},"terminal-state","units"}}};

    struct OracleEdge { const char* id; double lower; double upper; double cost; };
    const std::array<OracleEdge,3> oracle{{
        {"tie-a",0,0.5,0},{"tie-b",0,1,0},{"worse",1,1,1}}};
    for(const auto& expected:oracle) {
        CHECK(expected.lower==(std::string_view(expected.id)=="worse"?1:0));
        CHECK(expected.upper==(std::string_view(expected.id)=="tie-a"?0.5:1));
        CHECK(expected.cost==(std::string_view(expected.id)=="worse"?1:0));
    }
    const auto built=build_hybrid_portfolio_programs(system,request,{"multi-horizon-verifier"},
        {3,32},{64,1024,16384});
    REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(built));
    const auto& programs=std::get<std::vector<HybridPathProgram>>(built);
    REQUIRE(programs.size()==oracle.size());
    for(const auto& expected:oracle) {
        const auto found=std::find_if(programs.begin(),programs.end(),[&](const auto& program) {
            return program.path.edges.back().value==expected.id;
        });
        REQUIRE(found!=programs.end());
        const auto representation=found->joint_relation.representation();
        REQUIRE(std::holds_alternative<sets::HRepresentation>(representation));
        const auto& relation=std::get<sets::HRepresentation>(representation);
        const auto tuple_at=[&](double free_control) {
            return Vector{0,free_control,free_control,free_control,0,free_control,
                free_control,0,free_control,expected.cost};
        };
        CHECK(satisfies(relation,tuple_at(expected.lower)));
        CHECK(satisfies(relation,tuple_at(expected.upper)));
        if(std::string_view(expected.id)=="tie-a")
            CHECK_FALSE(satisfies(relation,tuple_at(0.75)));
        if(std::string_view(expected.id)=="worse")
            CHECK_FALSE(satisfies(relation,tuple_at(0.5)));
    }
    std::vector<HybridPathOptimalFaceCandidate> candidates;
    for(std::size_t i=0;i<2;++i) {
        const auto found=std::find_if(programs.begin(),programs.end(),[&](const auto& program) {
            return program.path.edges.back().value==oracle[i].id;
        });
        REQUIRE(found!=programs.end());
        candidates.push_back(exact_candidate(*found,Vector(10,0)));
    }
    SingleParameterScalarIntervalHybridFamilyVerifier verifier;
    const auto result=verify_hybrid_portfolio_family(verifier,system,request,programs,candidates,
        {3,32},{0,0});
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(result));
    const auto& report=std::get<HybridFamilyVerificationReport>(result);
    CHECK(report.verifier_id=="csl.hybrid.scalar-single-parameter-interval");
    CHECK(report.global_objective_optimality==HybridVerificationStatus::established);
    CHECK(report.complete_family_coverage==HybridVerificationStatus::established);
    for(const auto& expected:oracle) {
        const auto record=std::find_if(report.branches.begin(),report.branches.end(),[&](const auto& item) {
            return item.path.edges.back().value==expected.id;
        });
        REQUIRE(record!=report.branches.end());
        CHECK(record->feasibility==HybridVerificationStatus::established);
        CHECK(record->objective_optimality==(expected.cost==0?HybridVerificationStatus::established:
            HybridVerificationStatus::refuted));
        CHECK(record->continuous_coverage==HybridVerificationStatus::established);
    }
}

TEST_CASE("single-parameter verifier certifies quadratic interior and full optimal faces") {
    model::HybridMode mode{{"quadratic-mode"},1,1,{"x"},{"u"}};
    mode.flow=LinearStage{Matrix{1,1,{1}},Matrix{1,1,{2}},Matrix{1,0,{}},Vector{1}};
    mode.control_sets={interval("quadratic-control",0,1)};
    mode.invariants={UniversalSet{1},UniversalSet{1}};
    const auto reset=h_set("quadratic-identity-reset",2,Matrix{0,2,{}},Vector{},
        Matrix{1,2,{-1,1}},Vector{0});
    model::HybridSystem system{1,{mode},{{{"quadratic-loop"},{"quadratic-mode"},
        {"quadratic-mode"},{UniversalSet{1}},{reset}}}};
    model::HybridRequest request{{{"quadratic-mode"},{0}},{{"quadratic-mode"}},
        {{{"quadratic-mode"},QuadraticTerminal{Matrix{1,1,{2}},Vector{-4},0},
            "quadratic cost","units"}}};
    auto built=build_hybrid_portfolio_programs(system,request,{"quadratic-interval"},
        {1,8},{16,64,4096});
    REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(built));
    auto programs=std::get<std::vector<HybridPathProgram>>(std::move(built));
    REQUIRE(programs.size()==1);
    SingleParameterScalarIntervalHybridFamilyVerifier verifier;
    const auto paths=std::vector<model::HybridPath>{programs.front().path};
    const auto operation_plan=model::plan_hybrid_operations(paths);
    const auto preflight=verifier.preflight(system,request,paths,operation_plan,{});
    REQUIRE(std::holds_alternative<HybridOperationAdmissionSuccess>(preflight));
    auto& convex=std::get<ConvexProgram>(programs.front().program);
    const Vector optimum{0,0.5,2,2};
    ProgramResult solver{Termination::completed,
        {convex.quadratic_program().identity(),MathematicalOutcome::optimal,
            SymbolicArgument{"raw scalar quadratic oracle","minimum at x=2"},{}},
        optimum,{},"independent scalar quadratic optimum"};
    HybridPathOptimalFaceCandidate candidate{programs.front().path, singleton_data(optimum),
        optimum,std::move(solver),{},"independent singleton quadratic minimizer",{}};
    const auto result=verify_hybrid_portfolio_family(verifier,system,request,programs,
        std::span<const HybridPathOptimalFaceCandidate>(&candidate,1),{1,8},{0,0});
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(result));
    const auto& report=std::get<HybridFamilyVerificationReport>(result);
    CHECK(report.global_objective_optimality==HybridVerificationStatus::established);
    CHECK(report.complete_family_coverage==HybridVerificationStatus::established);
    CHECK(report.branches.front().continuous_coverage==HybridVerificationStatus::established);

    request.terminal_objectives.front().objective=QuadraticTerminal{Matrix{1,1,{0}},Vector{0},0};
    built=build_hybrid_portfolio_programs(system,request,{"flat-quadratic-interval"},
        {1,8},{16,64,4096});
    REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(built));
    programs=std::get<std::vector<HybridPathProgram>>(std::move(built));
    auto& flat_convex=std::get<ConvexProgram>(programs.front().program);
    ProgramResult flat_solver{Termination::completed,
        {flat_convex.quadratic_program().identity(),MathematicalOutcome::optimal,
            SymbolicArgument{"raw flat quadratic oracle","every control u in [0,1] minimizes"},{}},
        optimum,{},"independent flat quadratic optimum"};
    HybridPathOptimalFaceCandidate narrowed{programs.front().path,singleton_data(optimum),
        optimum,std::move(flat_solver),{},"deliberately narrowed flat minimizer",{}};
    const auto narrowed_result=verify_hybrid_portfolio_family(verifier,system,request,programs,
        std::span<const HybridPathOptimalFaceCandidate>(&narrowed,1),{1,8},{0,0});
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(narrowed_result));
    CHECK(std::get<HybridFamilyVerificationReport>(narrowed_result).complete_family_coverage==
        HybridVerificationStatus::refuted);
}

TEST_CASE("single-parameter verifier certifies residual-norm optimal faces") {
    model::HybridMode mode{{"residual-mode"},1,1,{"x"},{"u"}};
    mode.flow=LinearStage{Matrix{1,1,{1}},Matrix{1,1,{2}},Matrix{1,0,{}},Vector{1}};
    mode.control_sets={interval("residual-control",0,1)};
    mode.invariants={UniversalSet{1},UniversalSet{1}};
    const auto reset=h_set("residual-identity-reset",2,Matrix{0,2,{}},Vector{},
        Matrix{1,2,{-1,1}},Vector{0});
    model::HybridSystem system{1,{mode},{{{"residual-loop"},{"residual-mode"},
        {"residual-mode"},{UniversalSet{1}},{reset}}}};
    model::HybridRequest request{{{"residual-mode"},{0}},{{"residual-mode"}},
        {{{"residual-mode"},ResidualNormTerminal{Matrix{2,1,{1,1}},Vector{2,3}},
            "residual magnitude","units"}}};
    auto built=build_hybrid_portfolio_programs(system,request,{"residual-interval"},
        {1,8},{16,64,4096});
    REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(built));
    auto programs=std::get<std::vector<HybridPathProgram>>(std::move(built));
    REQUIRE(programs.size()==1);
    SingleParameterScalarIntervalHybridFamilyVerifier verifier;
    const auto paths=std::vector<model::HybridPath>{programs.front().path};
    const auto operation_plan=model::plan_hybrid_operations(paths);
    const auto preflight=verifier.preflight(system,request,paths,operation_plan,{});
    REQUIRE(std::holds_alternative<HybridOperationAdmissionSuccess>(preflight));
    auto& convex=std::get<ConvexProgram>(programs.front().program);
    const Vector optimum{0,0.75,2.5,2.5};
    ProgramResult solver{Termination::completed,
        {convex.quadratic_program().identity(),MathematicalOutcome::optimal,
            SymbolicArgument{"raw residual-norm oracle","minimum at x=2.5"},{}},
        optimum,{},"independent residual-norm optimum"};
    HybridPathOptimalFaceCandidate candidate{programs.front().path,singleton_data(optimum),
        optimum,std::move(solver),{},"independent singleton residual minimizer",{}};
    const auto result=verify_hybrid_portfolio_family(verifier,system,request,programs,
        std::span<const HybridPathOptimalFaceCandidate>(&candidate,1),{1,8},{0,0});
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(result));
    const auto& report=std::get<HybridFamilyVerificationReport>(result);
    CHECK(report.global_objective_optimality==HybridVerificationStatus::established);
    CHECK(report.complete_family_coverage==HybridVerificationStatus::established);

    auto perturbed_request=request;
    std::get<ResidualNormTerminal>(perturbed_request.terminal_objectives.front().objective).target[0]+=0.125;
    const auto perturbed_paths=std::vector<model::HybridPath>{programs.front().path};
    const auto perturbed_result=verifier.verify(system,perturbed_request,perturbed_paths,programs,
        std::span<const HybridPathOptimalFaceCandidate>(&candidate,1),{0.2,0.2},{});
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(perturbed_result));
    const auto& perturbed_report=std::get<HybridFamilyVerificationReport>(perturbed_result);
    CHECK(perturbed_report.complete_family_coverage==HybridVerificationStatus::refuted);
    REQUIRE(!perturbed_report.branches.front().diagnostics.empty());
    CHECK(perturbed_report.branches.front().diagnostics.front().field==
        "hybrid.verification.scalar_parameter_program");

    request.terminal_objectives.front().objective=ResidualNormTerminal{Matrix{1,1,{0}},Vector{2}};
    built=build_hybrid_portfolio_programs(system,request,{"flat-residual-interval"},
        {1,8},{16,64,4096});
    REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(built));
    programs=std::get<std::vector<HybridPathProgram>>(std::move(built));
    auto& flat_convex=std::get<ConvexProgram>(programs.front().program);
    const Vector flat_anchor{0,0.5,2,2};
    ProgramResult flat_solver{Termination::completed,
        {flat_convex.quadratic_program().identity(),MathematicalOutcome::optimal,
            SymbolicArgument{"raw flat residual-norm oracle","every control u in [0,1] minimizes"},{}},
        flat_anchor,{},"independent flat residual-norm optimum"};
    HybridPathOptimalFaceCandidate full_flat{programs.front().path,programs.front().joint_relation,
        flat_anchor,std::move(flat_solver),{},"independent full residual minimizer interval",{}};
    const auto full_flat_result=verify_hybrid_portfolio_family(verifier,system,request,programs,
        std::span<const HybridPathOptimalFaceCandidate>(&full_flat,1),{1,8},{0,0});
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(full_flat_result));
    CHECK(std::get<HybridFamilyVerificationReport>(full_flat_result).complete_family_coverage==
        HybridVerificationStatus::established);

    ProgramResult narrowed_solver{Termination::completed,
        {flat_convex.quadratic_program().identity(),MathematicalOutcome::optimal,
            SymbolicArgument{"raw flat residual-norm oracle","every control u in [0,1] minimizes"},{}},
        flat_anchor,{},"independent flat residual-norm optimum"};
    HybridPathOptimalFaceCandidate narrowed{programs.front().path,singleton_data(flat_anchor),
        flat_anchor,std::move(narrowed_solver),{},"deliberately narrowed residual minimizers",{}};
    const auto narrowed_result=verify_hybrid_portfolio_family(verifier,system,request,programs,
        std::span<const HybridPathOptimalFaceCandidate>(&narrowed,1),{1,8},{0,0});
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(narrowed_result));
    CHECK(std::get<HybridFamilyVerificationReport>(narrowed_result).complete_family_coverage==
        HybridVerificationStatus::refuted);
}

TEST_CASE("single-parameter residual norms compare with other terminal modes without false ties") {
    const auto make_mode=[](model::HybridModeId id) {
        model::HybridMode mode{std::move(id),1,1,{"x"},{"u"}};
        mode.flow=LinearStage{Matrix{1,1,{1}},Matrix{1,1,{2}},Matrix{1,0,{}},Vector{1}};
        mode.control_sets={interval("mode-control",0,1)};
        mode.invariants={UniversalSet{1},UniversalSet{1}};
        return mode;
    };
    const auto reset=h_set("shared-identity-reset",2,Matrix{0,2,{}},Vector{},
        Matrix{1,2,{-1,1}},Vector{0});
    model::HybridSystem system{1,
        {make_mode({"source"}),make_mode({"residual-target"}),make_mode({"linear-target"}),
         make_mode({"near-target"})},
        {{{"to-residual"},{"source"},{"residual-target"},{UniversalSet{1}},{reset}},
         {{"to-linear"},{"source"},{"linear-target"},{UniversalSet{1}},{reset}},
         {{"to-near"},{"source"},{"near-target"},{UniversalSet{1}},{reset}}}};
    model::HybridRequest request{{{"source"},{0}},
        {{"residual-target"},{"linear-target"},{"near-target"}},
        {{{"residual-target"},ResidualNormTerminal{Matrix{1,1,{1}},Vector{0}},"cost","units"},
         {{"linear-target"},LinearTerminal{Vector{1},0},"cost","units"},
         {{"near-target"},LinearTerminal{Vector{1},0x1p-26},"cost","units"}}};
    auto built=build_hybrid_portfolio_programs(system,request,{"mixed-terminal-objectives"},
        {3,8},{32,128,4096});
    REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(built));
    auto programs=std::get<std::vector<HybridPathProgram>>(std::move(built));
    REQUIRE(programs.size()==3);
    std::vector<HybridPathOptimalFaceCandidate> candidates;
    const Vector optimum{0,0,1,1};
    for(const auto& program:programs) {
        if(program.path.modes.back().value=="near-target") continue;
        const auto& identity=std::visit([](const auto& value) -> const ProgramIdentity& {
            if constexpr(std::is_same_v<std::decay_t<decltype(value)>,LinearProgram>) return value.identity();
            else return value.quadratic_program().identity();
        },program.program);
        ProgramResult solver{Termination::completed,
            {identity,MathematicalOutcome::optimal,
                SymbolicArgument{"raw mixed-mode oracle","both exact minima equal one"},{}},
            optimum,{},"independent mixed-mode optimum"};
        candidates.push_back({program.path,singleton_data(optimum),optimum,std::move(solver),{},
            "independent mixed-mode minimizer",{}});
    }
    SingleParameterScalarIntervalHybridFamilyVerifier verifier;
    const auto result=verify_hybrid_portfolio_family(verifier,system,request,programs,candidates,
        {3,8},{0,0});
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(result));
    const auto& report=std::get<HybridFamilyVerificationReport>(result);
    CHECK(report.global_objective_optimality==HybridVerificationStatus::established);
    CHECK(report.complete_family_coverage==HybridVerificationStatus::established);
    REQUIRE(report.branches.size()==3);
    CHECK(report.branches[0].objective_optimality==HybridVerificationStatus::established);
    CHECK(report.branches[1].objective_optimality==HybridVerificationStatus::established);
    CHECK(report.branches[2].objective_optimality==HybridVerificationStatus::refuted);

    request.terminal_objectives.back().objective=LinearTerminal{Vector{1},0x1p-27};
    built=build_hybrid_portfolio_programs(system,request,{"inexact-cross-objective-comparison"},
        {3,8},{32,128,4096});
    REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(built));
    programs=std::get<std::vector<HybridPathProgram>>(std::move(built));
    const auto inexact_paths=std::vector<model::HybridPath>{
        programs[0].path,programs[1].path,programs[2].path};
    const auto inexact_plan=model::plan_hybrid_operations(inexact_paths);
    const auto inexact_preflight=verifier.preflight(system,request,inexact_paths,inexact_plan,{});
    REQUIRE(std::holds_alternative<Diagnostics>(inexact_preflight));
    CHECK(std::get<Diagnostics>(inexact_preflight).front().field==
        "hybrid.verification.scalar_parameter_objective_comparison");
    const auto inexact_comparison=verify_hybrid_portfolio_family(verifier,system,request,programs,{},
        {3,8},{0,0});
    REQUIRE(std::holds_alternative<Diagnostics>(inexact_comparison));
    CHECK(std::get<Diagnostics>(inexact_comparison).front().field==
        "hybrid.verification.scalar_parameter_objective_comparison");
}

TEST_CASE("single-parameter residual-norm verifier rejects inexact objective pullbacks") {
    model::HybridMode mode{{"inexact-residual-mode"},1,1,{"x"},{"u"}};
    mode.flow=LinearStage{Matrix{1,1,{1}},Matrix{1,1,{0.2}},Matrix{1,0,{}},Vector{0}};
    mode.control_sets={interval("inexact-residual-control",0,1)};
    mode.invariants={UniversalSet{1},UniversalSet{1}};
    const auto reset=h_set("inexact-residual-identity",2,Matrix{0,2,{}},Vector{},
        Matrix{1,2,{-1,1}},Vector{0});
    model::HybridSystem system{1,{mode},{{{"inexact-residual-loop"},{"inexact-residual-mode"},
        {"inexact-residual-mode"},{UniversalSet{1}},{reset}}}};
    model::HybridRequest request{{{"inexact-residual-mode"},{0}},{{"inexact-residual-mode"}},
        {{{"inexact-residual-mode"},ResidualNormTerminal{Matrix{1,1,{0.1}},Vector{0}},
            "residual magnitude","units"}}};
    auto built=build_hybrid_portfolio_programs(system,request,{"inexact-residual-pullback"},
        {1,8},{16,64,4096});
    REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(built));
    const auto& programs=std::get<std::vector<HybridPathProgram>>(built);
    const auto paths=std::vector<model::HybridPath>{programs.front().path};
    const auto operation_plan=model::plan_hybrid_operations(paths);
    SingleParameterScalarIntervalHybridFamilyVerifier verifier;
    const auto preflight=verifier.preflight(system,request,paths,operation_plan,{});
    REQUIRE(std::holds_alternative<Diagnostics>(preflight));
    CHECK(std::get<Diagnostics>(preflight).front().field==
        "hybrid.verification.scalar_parameter_domain");
}

TEST_CASE("exact singleton hybrid verifier handles empty branches and rejects continuous domains") {
    auto [system,request]=exact_singleton_portfolio();
    system.edges[0].guards[0]=EmptySet{1};
    auto built=build_hybrid_portfolio_programs(system,request,{"exact-hybrid-empty"},
        {1,8},{32,128,4096});
    REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(built));
    const auto& programs=std::get<std::vector<HybridPathProgram>>(built);
    ExactSingletonHybridFamilyVerifier verifier;
    const Vector point{2,1,3,0,0};
    std::vector<HybridPathOptimalFaceCandidate> candidates{exact_candidate(programs[1],point)};
    const auto result=verify_hybrid_portfolio_family(verifier,system,request,programs,candidates,
        {1,8},{1e-10,1e-10});
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(result));
    const auto& report=std::get<HybridFamilyVerificationReport>(result);
    CHECK(report.branches[0].feasibility==HybridVerificationStatus::refuted);
    CHECK(report.branches[0].objective_optimality==HybridVerificationStatus::refuted);
    CHECK(report.complete_family_coverage==HybridVerificationStatus::established);
    candidates.push_back(exact_candidate(programs[0],point));
    const auto infeasible_face=verify_hybrid_portfolio_family(verifier,system,request,programs,candidates,
        {1,8},{1e-10,1e-10});
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(infeasible_face));
    CHECK(std::get<HybridFamilyVerificationReport>(infeasible_face).complete_family_coverage==
        HybridVerificationStatus::refuted);

    auto continuous_system=example_system();
    auto continuous_built=build_hybrid_portfolio_programs(continuous_system,example_request(),
        {"continuous-hybrid"},{1,8},{32,128,4096});
    REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(continuous_built));
    const auto unsupported=verify_hybrid_portfolio_family(verifier,continuous_system,example_request(),
        std::get<std::vector<HybridPathProgram>>(continuous_built),{}, {1,8},{1e-10,1e-10});
    REQUIRE(std::holds_alternative<Diagnostics>(unsupported));
    CHECK(std::get<Diagnostics>(unsupported).front().field==
        "hybrid.verification.exact_singleton_domain");

    auto [mixed_system,mixed_request]=exact_singleton_portfolio();
    mixed_system.edges[0].reset_relations[0]=affine_reset();
    const auto mixed_programs=build_hybrid_portfolio_programs(mixed_system,mixed_request,
        {"mixed-domain-hybrid"},{1,8},{32,128,4096});
    REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(mixed_programs));
    const auto mixed=verify_hybrid_portfolio_family(verifier,mixed_system,mixed_request,
        std::get<std::vector<HybridPathProgram>>(mixed_programs),{}, {1,8},{1e-10,1e-10});
    REQUIRE(std::holds_alternative<Diagnostics>(mixed));
    CHECK(std::get<Diagnostics>(mixed).front().field==
        "hybrid.verification.exact_singleton_domain");

    auto [limited_system,limited_request]=exact_singleton_portfolio();
    const auto limited_programs=build_hybrid_portfolio_programs(limited_system,limited_request,
        {"exact-hybrid-limit"},{1,8},{32,128,4096});
    REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(limited_programs));
    const auto path_limit=verify_hybrid_portfolio_family(verifier,limited_system,limited_request,
        std::get<std::vector<HybridPathProgram>>(limited_programs),{}, {1,2},{1e-10,1e-10});
    REQUIRE(std::holds_alternative<Diagnostics>(path_limit));
    CHECK(std::get<Diagnostics>(path_limit).front().field=="hybrid.paths.limit");

    std::stop_source cancellation;
    cancellation.request_stop();
    const auto cancelled=verify_hybrid_portfolio_family(verifier,limited_system,limited_request,
        std::get<std::vector<HybridPathProgram>>(limited_programs),{}, {1,8},{1e-10,1e-10},
        cancellation.get_token());
    CHECK(std::holds_alternative<OperationStopped>(cancelled));
    std::vector<model::HybridPath> paths;
    for(const auto& program:std::get<std::vector<HybridPathProgram>>(limited_programs))
        paths.push_back(program.path);
    const auto adapter_cancelled=verifier.verify(limited_system,limited_request,paths,
        std::get<std::vector<HybridPathProgram>>(limited_programs),{}, {1e-10,1e-10},
        cancellation.get_token());
    CHECK(std::holds_alternative<OperationStopped>(adapter_cancelled));
}

TEST_CASE("two parameter scalar verifier supports free controls at separated stages") {
  auto identity_reset = [] {
    auto equalities = numeric::snapshot(Matrix{1, 2, {-1, 1}});
    auto equality_values = numeric::snapshot_vector(Vector{0});
    auto inequalities = numeric::snapshot(Matrix{0, 2, {}});
    auto upper_bounds = numeric::snapshot_vector(Vector{});
    REQUIRE(std::holds_alternative<numeric::MatrixView>(equalities));
    REQUIRE(std::holds_alternative<numeric::VectorView>(equality_values));
    REQUIRE(std::holds_alternative<numeric::MatrixView>(inequalities));
    REQUIRE(std::holds_alternative<numeric::VectorView>(upper_bounds));
    auto set = sets::make_h(
        {SetId{"three-stage-identity"}, 2, {}},
        {std::get<numeric::MatrixView>(inequalities),
         std::get<numeric::VectorView>(upper_bounds),
         std::get<numeric::MatrixView>(equalities),
         std::get<numeric::VectorView>(equality_values)});
    REQUIRE(std::holds_alternative<sets::SetData>(set));
    return std::get<sets::SetData>(set).as_handle();
  };
  const auto free_a = interval("three-stage-u0", 0, 1);
  const auto fixed = singleton_relation("three-stage-u1", {0});
  const auto free_b = interval("three-stage-u2", 0, 1);
  const auto universal_state = UniversalSet{1};
  const auto zero_flow = LinearStage{Matrix{1, 1, {0}}, Matrix{1, 1, {1}},
                                     Matrix{1, 0, {}}, Vector{0}};
  model::HybridMode mode{{"three-stage-mode"}, 1, 1, {"x"}, {"u"}};
  mode.flow = std::vector<LinearStage>{zero_flow, zero_flow, zero_flow};
  mode.control_sets = {free_a, fixed, free_b};
  mode.invariants = {universal_state, universal_state, universal_state,
                     universal_state};
  const auto reset = identity_reset();
  model::HybridTransitionEdge edge{{"three-stage-loop"}, {"three-stage-mode"},
      {"three-stage-mode"}, {universal_state, universal_state, universal_state},
      {reset, reset, reset}};
  model::HybridSystem system{3, {mode}, {edge}};
  model::HybridRequest request{{{"three-stage-mode"}, {0}},
      {{"three-stage-mode"}},
      {{{"three-stage-mode"}, LinearTerminal{{0}, 0}, "constant", "units"}}};
  auto built = build_hybrid_portfolio_programs(
      system, request, {"three-stage-two-parameter"}, {3, 8},
      {32, 128, 1280});
  REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(built));
  auto programs = std::get<std::vector<HybridPathProgram>>(std::move(built));
  REQUIRE(programs.size() == 1);
  CHECK(programs.front().path.modes ==
        std::vector<model::HybridModeId>(4, {"three-stage-mode"}));
  CHECK(programs.front().path.edges ==
        std::vector<model::HybridEdgeId>(3, {"three-stage-loop"}));
  CHECK(programs.front().joint_relation.metadata()->set.dimension == 10);
  auto face = exact_candidate(programs.front(), Vector(10, 0));
  TwoParameterScalarPolytopeHybridFamilyVerifier verifier;
  const std::array<model::HybridPath, 1> paths{programs.front().path};
  auto result = verifier.verify(system, request, paths, programs,
                                std::span<const HybridPathOptimalFaceCandidate>(&face, 1),
                                {3, 8}, {});
  REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(result));
  const auto &report = std::get<HybridFamilyVerificationReport>(result);
  CHECK(report.branches.size() == 1);
  CHECK(report.branches.front().continuous_coverage ==
        HybridVerificationStatus::established);
  CHECK(report.complete_family_coverage == HybridVerificationStatus::established);

  auto three_free_controls = system;
  three_free_controls.modes.front().control_sets[1] =
      interval("three-stage-extra-free-control", 0, 1);
  const auto operation_plan=model::plan_hybrid_operations(paths);
  const auto rejected = verifier.preflight(three_free_controls, request, paths, operation_plan, {});
  CHECK(std::holds_alternative<Diagnostics>(rejected));
}

TEST_CASE("two parameter scalar verifier certifies a coupled polygon and "
          "rejects off-image extensions") {
  const auto reset = [](std::string id) {
    auto a = numeric::snapshot(Matrix{0, 2, {}});
    auto b = numeric::snapshot_vector(Vector{});
    auto e = numeric::snapshot(Matrix{1, 2, {-1, 1}});
    auto v = numeric::snapshot_vector(Vector{0});
    REQUIRE(std::holds_alternative<numeric::MatrixView>(a));
    REQUIRE(std::holds_alternative<numeric::VectorView>(b));
    REQUIRE(std::holds_alternative<numeric::MatrixView>(e));
    REQUIRE(std::holds_alternative<numeric::VectorView>(v));
    auto d = sets::make_h(
        {SetId{std::move(id)}, 2, {}},
        {std::get<numeric::MatrixView>(a), std::get<numeric::VectorView>(b),
         std::get<numeric::MatrixView>(e), std::get<numeric::VectorView>(v)});
    REQUIRE(std::holds_alternative<sets::SetData>(d));
    return std::get<sets::SetData>(d).as_handle();
  };
  const auto mode = [](std::string id, AdmissibleSet u0, AdmissibleSet u1,
                       AdmissibleSet final) {
    model::HybridMode m{{std::move(id)}, 1, 1, {"x"}, {"u"}};
    const LinearStage f0{Matrix{1, 1, {0}}, Matrix{1, 1, {1}}, Matrix{1, 0, {}},
                         Vector{0}};
    const LinearStage f1{Matrix{1, 1, {1}}, Matrix{1, 1, {1}}, Matrix{1, 0, {}},
                         Vector{0}};
    m.flow = std::vector<LinearStage>{f0, f1};
    m.control_sets = {std::move(u0), std::move(u1)};
    m.invariants = {UniversalSet{1}, UniversalSet{1}, std::move(final)};
    return m;
  };
  auto start = mode("two-parameter-start", interval("two-parameter-u0", 0, 1),
                    Singleton{{0}}, UniversalSet{1});
  auto middle = mode("two-parameter-middle", Singleton{{0}},
                     interval("two-parameter-u1", 0, 1), UniversalSet{1});
  auto terminal = mode("two-parameter-terminal", Singleton{{0}}, Singleton{{0}},
                       interval("two-parameter-coupled-terminal", 0, 1));
  const auto identity = reset("two-parameter-identity");
  model::HybridSystem system{
      2,
      {start, middle, terminal},
      {{{"two-parameter-enter-half"},
        {"two-parameter-start"},
        {"two-parameter-middle"},
        {interval("two-parameter-guard-half", 0, 0.5), UniversalSet{1}},
        {identity, universal("two-parameter-unused-a", 2)}},
       {{"two-parameter-enter-full"},
        {"two-parameter-start"},
        {"two-parameter-middle"},
        {UniversalSet{1}, UniversalSet{1}},
        {identity, universal("two-parameter-unused-full", 2)}},
       {{"two-parameter-finish"},
        {"two-parameter-middle"},
        {"two-parameter-terminal"},
        {UniversalSet{1}, UniversalSet{1}},
        {universal("two-parameter-unused-b", 2), identity}}}};
  // Put the lower-resource complete path first so the family summary must
  // compute maxima instead of retaining the first path's measurements.
  std::reverse(system.edges.begin(), system.edges.end());
  model::HybridRequest request{{{"two-parameter-start"}, {0}},
                               {{"two-parameter-terminal"}},
                               {{{"two-parameter-terminal"},
                                 LinearTerminal{{0}, 0},
                                 "constant",
                                 "units"}}};
  const auto capability = report_hybrid_capability(system, request, {2, 8});
  REQUIRE(std::holds_alternative<model::HybridCapabilityReport>(capability));
  const auto &profile = std::get<model::HybridCapabilityReport>(capability);
  CHECK(profile.profile_admitted);
  CHECK(profile.path_enumeration_completed);
  CHECK(profile.horizon == 2);
  CHECK(profile.mode_count == 3);
  CHECK(profile.edge_count == 3);
  CHECK(profile.maximum_state_dimension == 1);
  CHECK(profile.maximum_control_dimension == 1);
  REQUIRE(profile.complete_allowed_path_count);
  CHECK(*profile.complete_allowed_path_count == 2);
  auto built = build_hybrid_portfolio_programs(
      system, request, {"two-parameter-test"}, {2, 8}, {64, 4096, 65536});
  REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(built));
  auto programs = std::get<std::vector<HybridPathProgram>>(built);
  REQUIRE(programs.size() == 2);
  auto unsupported_objective_request=request;
  unsupported_objective_request.terminal_objectives.front().objective=
      QuadraticTerminal{Matrix{1,1,{1}},Vector{0},0};
  auto infeasible_path_system=system;
  for(auto& edge:infeasible_path_system.edges)
    if(edge.target==model::HybridModeId{"two-parameter-middle"})
      edge.guards[0]=EmptySet{1};
  const std::array<model::HybridPath,2> admitted_paths{
      programs[0].path,programs[1].path};
  const auto admission_plan=model::plan_hybrid_operations(admitted_paths);
  TwoParameterScalarPolytopeHybridFamilyVerifier admission_verifier;
  const auto unsupported_admission=admission_verifier.preflight(
      infeasible_path_system,unsupported_objective_request,admitted_paths,
      admission_plan,{});
  REQUIRE(std::holds_alternative<Diagnostics>(unsupported_admission));
  REQUIRE_FALSE(std::get<Diagnostics>(unsupported_admission).empty());
  CHECK(std::get<Diagnostics>(unsupported_admission).front().code==
      DiagnosticCode::unsupported);
  CHECK(std::get<Diagnostics>(unsupported_admission).front().field==
      "hybrid.verification.two_parameter_objective");
  CHECK(std::get<Diagnostics>(unsupported_admission).front().explanation.find(
      "two-parameter-terminal")!=std::string::npos);
  // Independent raw-graph oracle: enumerate two-edge histories directly from
  // the model catalogue instead of using the production path enumerator.
  std::vector<model::HybridPath> oracle_paths;
  for (const auto &first : system.edges) {
    if (first.source != request.initial.mode)
      continue;
    for (const auto &second : system.edges) {
      if (second.source != first.target ||
          std::find(request.allowed_terminal_modes.begin(),
                    request.allowed_terminal_modes.end(), second.target) ==
              request.allowed_terminal_modes.end())
        continue;
      oracle_paths.push_back(
          {{request.initial.mode, first.target, second.target},
           {first.id, second.id}});
    }
  }
  REQUIRE(oracle_paths.size() == 2);
  std::vector<bool> matched_oracle(oracle_paths.size(), false);
  for (const auto &program : programs) {
    const auto expected =
        std::find(oracle_paths.begin(), oracle_paths.end(), program.path);
    REQUIRE(expected != oracle_paths.end());
    const auto index = static_cast<std::size_t>(
        std::distance(oracle_paths.begin(), expected));
    REQUIRE_FALSE(matched_oracle[index]);
    matched_oracle[index] = true;
  }
  CHECK(std::all_of(matched_oracle.begin(), matched_oracle.end(),
                    [](bool matched) { return matched; }));
  std::vector<HybridPathOptimalFaceCandidate> faces;
  for (const auto &program : programs)
    faces.push_back(exact_candidate(program, Vector(7, 0)));
  for (auto &face : faces)
    face.providers.push_back({"linear_program",
                             {"fixture.lp", std::string{"1.0"}},
                             registry::Identity{{"fixture.lp"}, "1.0"}});
  faces.front().providers.push_back(faces.front().providers.back());
  const auto tuple = [](double u0, double u1) {
    return Vector{0, u0, u0, u0, u1, u0 + u1, u0 + u1};
  };
  const std::array<std::array<double, 2>, 4> half_polygon{
      {{0, 0}, {0.5, 0}, {0.5, 0.5}, {0, 1}}};
  const std::array<std::array<double, 2>, 3> full_polygon{
      {{0, 0}, {1, 0}, {0, 1}}};
  const auto half =
      std::find_if(programs.begin(), programs.end(), [](const auto &p) {
        return p.path.edges[0].value == "two-parameter-enter-half";
      });
  const auto full =
      std::find_if(programs.begin(), programs.end(), [](const auto &p) {
        return p.path.edges[0].value == "two-parameter-enter-full";
      });
  REQUIRE(half != programs.end());
  REQUIRE(full != programs.end());
  const auto half_h =
      std::get<sets::HRepresentation>(half->joint_relation.representation());
  const auto full_h =
      std::get<sets::HRepresentation>(full->joint_relation.representation());
  const auto literal_parameter_vertices = [](const sets::HRepresentation &h) {
    constexpr std::array<double, 7> u0_weight{0, 1, 1, 1, 0, 1, 1};
    constexpr std::array<double, 7> u1_weight{0, 0, 0, 0, 1, 1, 1};
    using Constraint = std::array<double, 3>;
    std::vector<Constraint> constraints;
    for (std::size_t row = 0; row < h.equalities.rows(); ++row) {
      double u0 = 0, u1 = 0;
      for (std::size_t col = 0; col < 7; ++col) {
        u0 += h.equalities(row, col) * u0_weight[col];
        u1 += h.equalities(row, col) * u1_weight[col];
      }
      if (u0 != 0 || u1 != 0 || h.equality_values[row] != 0)
        return std::vector<std::array<double, 2>>{};
    }
    for (std::size_t row = 0; row < h.inequalities.rows(); ++row) {
      double u0 = 0, u1 = 0;
      for (std::size_t col = 0; col < 7; ++col) {
        u0 += h.inequalities(row, col) * u0_weight[col];
        u1 += h.inequalities(row, col) * u1_weight[col];
      }
      constraints.push_back({u0, u1, h.upper_bounds[row]});
    }
    std::vector<std::array<double, 2>> vertices;
    for (std::size_t i = 0; i < constraints.size(); ++i) {
      for (std::size_t j = i + 1; j < constraints.size(); ++j) {
        const auto &a = constraints[i];
        const auto &b = constraints[j];
        const double det = a[0] * b[1] - b[0] * a[1];
        if (det == 0)
          continue;
        const std::array<double, 2> point{
            (a[2] * b[1] - b[2] * a[1]) / det,
            (a[0] * b[2] - b[0] * a[2]) / det};
        if (std::all_of(constraints.begin(), constraints.end(),
                        [&](const auto &constraint) {
                          return constraint[0] * point[0] +
                                     constraint[1] * point[1] <=
                                 constraint[2];
                        }))
          vertices.push_back(point);
      }
    }
    std::sort(vertices.begin(), vertices.end());
    vertices.erase(std::unique(vertices.begin(), vertices.end()),
                   vertices.end());
    return vertices;
  };
  CHECK((literal_parameter_vertices(half_h) ==
         std::vector<std::array<double, 2>>{{0, 0}, {0, 1}, {0.5, 0},
                                            {0.5, 0.5}}));
  CHECK((literal_parameter_vertices(full_h) ==
         std::vector<std::array<double, 2>>{{0, 0}, {0, 1}, {1, 0}}));
  for (const auto &vertex : half_polygon)
    CHECK(satisfies(half_h, tuple(vertex[0], vertex[1])));
  for (const auto &vertex : full_polygon)
    CHECK(satisfies(full_h, tuple(vertex[0], vertex[1])));
  CHECK_FALSE(satisfies(half_h, tuple(0.75, 0.1)));
  CHECK(satisfies(full_h, tuple(0.75, 0.1)));
  TwoParameterScalarPolytopeHybridFamilyVerifier verifier;
  auto valid = verify_hybrid_portfolio_family(verifier, system, request,
                                              programs, faces, {2, 8}, {0, 0});
  REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(valid));
  const auto &report = std::get<HybridFamilyVerificationReport>(valid);
  CHECK(report.verifier_id == "csl.hybrid.scalar-two-parameter-polytope");
  CHECK(report.global_objective_optimality ==
        HybridVerificationStatus::established);
  REQUIRE(report.branches.size() == 2);
  const auto shared_mode_flow = std::find_if(
      report.operation_resources.begin(), report.operation_resources.end(),
      [](const auto &resource) {
        return resource.operation ==
                   model::HybridRelationOperationKind::mode_flow &&
               resource.stage == 1 && resource.mode &&
               resource.mode->value == "two-parameter-middle";
      });
  REQUIRE(shared_mode_flow != report.operation_resources.end());
  CHECK(shared_mode_flow->implementation_id ==
        "csl.model.hybrid.joint-h-composer");
  CHECK(shared_mode_flow->implementation_version == "1");
  CHECK(shared_mode_flow->branch_count == 2);
  CHECK(shared_mode_flow->max_joint_variables == 7);
  CHECK(shared_mode_flow->max_rows_added == 1);
  CHECK(shared_mode_flow->max_cumulative_rows == 8);
  CHECK(shared_mode_flow->max_cumulative_matrix_elements == 56);
  REQUIRE(report.candidate_provider_coverage.size() == 1);
  const auto &provider_coverage = report.candidate_provider_coverage.front();
  CHECK(provider_coverage.port == "linear_program");
  CHECK(provider_coverage.requested_method_id == "fixture.lp");
  CHECK(provider_coverage.requested_version == std::optional<std::string>{"1.0"});
  CHECK(provider_coverage.actual_provider_id == std::optional<std::string>{"fixture.lp"});
  CHECK(provider_coverage.actual_provider_version == std::optional<std::string>{"1.0"});
  CHECK(provider_coverage.branch_count == 2);
  CHECK(provider_coverage.provenance_record_count == 3);
  CHECK(report.branches.front().candidate_providers.size() == 2);
  CHECK(report.branches.front().path.edges.front().value ==
        "two-parameter-enter-full");
  const auto full_path_record = std::find_if(
      report.branches.begin(), report.branches.end(), [](const auto &branch) {
        return branch.path.edges.front().value == "two-parameter-enter-full";
      });
  REQUIRE(full_path_record != report.branches.end());
  const auto full_path_flow = std::find_if(
      full_path_record->relation_operations.begin(),
      full_path_record->relation_operations.end(), [](const auto &operation) {
        return operation.operation ==
                   model::HybridRelationOperationKind::mode_flow &&
               operation.stage == 1;
      });
  REQUIRE(full_path_flow != full_path_record->relation_operations.end());
  CHECK(full_path_flow->cumulative_rows == 6);
  CHECK(full_path_flow->cumulative_matrix_elements == 42);
  for (const auto &branch : report.branches) {
    CHECK(branch.feasibility == HybridVerificationStatus::established);
    CHECK(branch.objective_optimality == HybridVerificationStatus::established);
    CHECK(branch.continuous_coverage == HybridVerificationStatus::established);
  }
  CHECK(report.complete_family_coverage ==
        HybridVerificationStatus::established);

  auto missing_face = verify_hybrid_portfolio_family(
      verifier, system, request, programs,
      std::span<const HybridPathOptimalFaceCandidate>(faces.data(), 1), {2, 8},
      {0, 0});
  CHECK(std::holds_alternative<Diagnostics>(missing_face));
  auto duplicate_faces = faces;
  duplicate_faces.push_back(faces.front());
  auto duplicate_face = verify_hybrid_portfolio_family(
      verifier, system, request, programs, duplicate_faces, {2, 8}, {0, 0});
  CHECK(std::holds_alternative<Diagnostics>(duplicate_face));

  auto shared_flow_system = system;
  const LinearStage shared_flow{Matrix{1, 1, {1}}, Matrix{1, 1, {1}},
                                Matrix{1, 0, {}}, Vector{0}};
  for (auto &shared_mode : shared_flow_system.modes)
    shared_mode.flow = shared_flow;
  auto shared_program_result = build_hybrid_portfolio_programs(
      shared_flow_system, request, {"two-parameter-shared-flow"}, {2, 8},
      {64, 4096, 65536});
  REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(
      shared_program_result));
  const auto &shared_programs =
      std::get<std::vector<HybridPathProgram>>(shared_program_result);
  std::vector<HybridPathOptimalFaceCandidate> shared_faces;
  for (const auto &program : shared_programs)
    shared_faces.push_back(exact_candidate(program, Vector(7, 0)));
  auto shared_report = verify_hybrid_portfolio_family(
      verifier, shared_flow_system, request, shared_programs, shared_faces,
      {2, 8}, {0, 0});
  REQUIRE(
      std::holds_alternative<HybridFamilyVerificationReport>(shared_report));
  CHECK(std::get<HybridFamilyVerificationReport>(shared_report)
            .complete_family_coverage == HybridVerificationStatus::established);

  for (const auto &terminal_set :
       std::array<AdmissibleSet, 2>{Singleton{{0.5}}, Singleton{{0}}}) {
    auto degenerate_system = system;
    degenerate_system.modes[2].invariants[2] = terminal_set;
    auto degenerate_programs = build_hybrid_portfolio_programs(
        degenerate_system, request, {"two-parameter-degenerate"}, {2, 8},
        {64, 4096, 65536});
    REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(
        degenerate_programs));
    std::vector<model::HybridPath> degenerate_paths;
    for (const auto &program :
         std::get<std::vector<HybridPathProgram>>(degenerate_programs))
      degenerate_paths.push_back(program.path);
    const auto degenerate_plan=model::plan_hybrid_operations(degenerate_paths);
    CHECK(std::holds_alternative<Diagnostics>(verifier.preflight(
        degenerate_system, request, degenerate_paths, degenerate_plan, {})));
    auto degenerate_report = verify_hybrid_portfolio_family(
        verifier, degenerate_system, request,
        std::get<std::vector<HybridPathProgram>>(degenerate_programs), {},
        {2, 8}, {0, 0});
    CHECK(std::holds_alternative<Diagnostics>(degenerate_report));
  }

  auto inexact_anchor_system = system;
  auto &inexact_middle = inexact_anchor_system.modes[1];
  std::get<std::vector<LinearStage>>(inexact_middle.flow)[1] =
      LinearStage{Matrix{1, 1, {0.1}}, Matrix{1, 1, {1}}, Matrix{1, 0, {}},
                  Vector{0}};
  inexact_anchor_system.modes[2].invariants[2] = UniversalSet{1};
  auto inexact_program_result = build_hybrid_portfolio_programs(
      inexact_anchor_system, request, {"two-parameter-inexact-anchor"},
      {2, 8}, {64, 4096, 65536});
  REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(
      inexact_program_result));
  const auto &inexact_programs =
      std::get<std::vector<HybridPathProgram>>(inexact_program_result);
  std::vector<HybridPathOptimalFaceCandidate> inexact_faces;
  for (const auto &program : inexact_programs) {
    auto candidate = exact_candidate(program, Vector(7, 0));
    candidate.anchor = Vector{0, 0.1, 0.1, 0.1, 0,
                              0.1 * 0.1, 0.1 * 0.1};
    candidate.solver_result.primal = candidate.anchor;
    inexact_faces.push_back(std::move(candidate));
  }
  auto inexact_anchor_report = verify_hybrid_portfolio_family(
      verifier, inexact_anchor_system, request, inexact_programs,
      inexact_faces, {2, 8}, {0, 0});
  std::string inexact_error =
      "hybrid verifier result variant: " +
      std::to_string(inexact_anchor_report.index());
  if (const auto *errors = std::get_if<Diagnostics>(&inexact_anchor_report);
      errors && !errors->empty())
    inexact_error += ": " + (*errors)[0].field + ": " +
                     (*errors)[0].explanation;
  INFO(inexact_error);
  REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(
      inexact_anchor_report));
  const auto &inexact_report =
      std::get<HybridFamilyVerificationReport>(inexact_anchor_report);
  CHECK(inexact_report.branches[0].continuous_coverage ==
        HybridVerificationStatus::unsupported);
  CHECK(inexact_report.branches[1].continuous_coverage ==
        HybridVerificationStatus::unsupported);

  const auto drop_coordinate_zero_equality = [](const sets::SetData &data,
                                                std::string id) {
    const auto repr = data.representation();
    REQUIRE(std::holds_alternative<sets::HRepresentation>(repr));
    const auto &h = std::get<sets::HRepresentation>(repr);
    REQUIRE(h.equalities.cols() == 7);
    std::vector<double> eq, rhs;
    bool dropped = false;
    for (std::size_t row = 0; row < h.equalities.rows(); ++row) {
      bool only_zero_coordinate = h.equalities(row, 0) != 0;
      for (std::size_t col = 1; col < 7; ++col)
        only_zero_coordinate =
            only_zero_coordinate && h.equalities(row, col) == 0;
      if (only_zero_coordinate && !dropped) {
        dropped = true;
        continue;
      }
      for (std::size_t col = 0; col < 7; ++col)
        eq.push_back(h.equalities(row, col));
      rhs.push_back(h.equality_values[row]);
    }
    REQUIRE(dropped);
    std::vector<double> ineq, bounds;
    for (std::size_t row = 0; row < h.inequalities.rows(); ++row) {
      for (std::size_t col = 0; col < 7; ++col)
        ineq.push_back(h.inequalities(row, col));
      bounds.push_back(h.upper_bounds[row]);
    }
    auto im = numeric::snapshot(Matrix{bounds.size(), 7, std::move(ineq)});
    auto bv = numeric::snapshot_vector(std::move(bounds));
    auto em = numeric::snapshot(Matrix{rhs.size(), 7, std::move(eq)});
    auto rv = numeric::snapshot_vector(std::move(rhs));
    REQUIRE(std::holds_alternative<numeric::MatrixView>(im));
    REQUIRE(std::holds_alternative<numeric::VectorView>(bv));
    REQUIRE(std::holds_alternative<numeric::MatrixView>(em));
    REQUIRE(std::holds_alternative<numeric::VectorView>(rv));
    auto forged = sets::make_h(
        {SetId{std::move(id)}, 7, {}},
        {std::get<numeric::MatrixView>(im), std::get<numeric::VectorView>(bv),
         std::get<numeric::MatrixView>(em), std::get<numeric::VectorView>(rv)});
    REQUIRE(std::holds_alternative<sets::SetData>(forged));
    return std::get<sets::SetData>(forged);
  };
  auto forged_program = programs;
  forged_program[0].joint_relation = drop_coordinate_zero_equality(
      forged_program[0].joint_relation, "forged-program-extra-state");
  auto forged_program_report = verify_hybrid_portfolio_family(
      verifier, system, request, forged_program, faces, {2, 8}, {0, 0});
  REQUIRE(std::holds_alternative<Diagnostics>(forged_program_report));
  CHECK(std::get<Diagnostics>(forged_program_report).front().code==
      DiagnosticCode::evidence_mismatch);
  auto forged_faces = faces;
  const auto decoded_face = forged_faces[0].relation;
  forged_faces[0].relation =
      drop_coordinate_zero_equality(decoded_face, "forged-face-extra-state");
  auto forged_face_report = verify_hybrid_portfolio_family(
      verifier, system, request, programs, forged_faces, {2, 8}, {0, 0});
  REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(
      forged_face_report));
  CHECK(std::get<HybridFamilyVerificationReport>(forged_face_report)
            .branches[0]
            .continuous_coverage == HybridVerificationStatus::refuted);
}

TEST_CASE("hybrid portfolio objective bounds retain tied possible branches") {
  auto system = example_system();
  auto second = system.edges.front();
  second.id = {"switch-second"};
  auto third = system.edges.front();
  third.id = {"switch-third"};
  system.edges.push_back(std::move(second));
  system.edges.push_back(std::move(third));
  const auto built = build_hybrid_portfolio_programs(
      system, example_request(), {"hybrid-problem"}, {1, 8}, {16, 64, 1024});
  REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(built));
  const auto &programs = std::get<std::vector<HybridPathProgram>>(built);
  REQUIRE(programs.size() == 3);

  HybridPortfolioExecution execution;
  execution.all_supplied_branches_completed = true;
  const std::array<double, 3> values{5, 5, 7};
  for (std::size_t i = 0; i < programs.size(); ++i) {
    const auto &program = std::get<LinearProgram>(programs[i].program);
    const auto evidence = ProgramBoundEvidence{
        program.identity(),
        SymbolicArgument{"literal fixture bounds", "synthetic test result"},
        {}};
    ProgramResult result{
        Termination::completed,
        {program.identity(),
         MathematicalOutcome::optimal,
         SymbolicArgument{"literal fixture optimum", "synthetic test result"},
         {}},
        {},
        {ProgramObjectiveBound{values[i], evidence},
         ProgramObjectiveBound{values[i], evidence}},
        "literal fixture result"};
    execution.branches.push_back({programs[i].path,
                                  Termination::completed,
                                  MathematicalOutcome::optimal,
                                  std::move(result),
                                  {},
                                  {}});
  }

  const auto comparison =
      compare_hybrid_portfolio_objective_bounds(programs, execution, {0, 0});
  REQUIRE(std::holds_alternative<HybridPortfolioObjectiveBounds>(comparison));
  const auto &bounds = std::get<HybridPortfolioObjectiveBounds>(comparison);
  CHECK(bounds.global_lower_bound == 5);
  CHECK(bounds.global_upper_bound == 5);
  REQUIRE(bounds.potentially_optimal_paths.size() == 2);
  CHECK(bounds.potentially_optimal_paths[0] == programs[0].path);
  CHECK(bounds.potentially_optimal_paths[1] == programs[1].path);
  REQUIRE(bounds.global_lower_bound_sources.size() == 2);
  REQUIRE(bounds.global_upper_bound_sources.size() == 2);
  CHECK(bounds.global_lower_bound_sources[0].path == programs[0].path);
  CHECK(bounds.global_lower_bound_sources[0].bound.evidence.subject ==
        std::get<LinearProgram>(programs[0].program).identity());

  auto incomplete = execution;
  incomplete.branches[2].result->objective.lower.reset();
  const auto partial =
      compare_hybrid_portfolio_objective_bounds(programs, incomplete, {0, 0});
  REQUIRE(std::holds_alternative<HybridPortfolioObjectiveIncomplete>(partial));
  CHECK(std::get<HybridPortfolioObjectiveIncomplete>(partial)
            .branches_without_comparable_bounds == std::vector<std::size_t>{2});

  auto unsupported = execution;
  unsupported.branches[2].result->objective.lower->evidence.support =
      Unestablished{};
  const auto unestablished =
      compare_hybrid_portfolio_objective_bounds(programs, unsupported, {0, 0});
  REQUIRE(std::holds_alternative<HybridPortfolioObjectiveIncomplete>(
      unestablished));
  CHECK(std::get<HybridPortfolioObjectiveIncomplete>(unestablished)
            .branches_without_comparable_bounds == std::vector<std::size_t>{2});

  auto inconsistent = execution;
  inconsistent.branches[1].result->termination = Termination::cancelled;
  const auto interrupted =
      compare_hybrid_portfolio_objective_bounds(programs, inconsistent, {0, 0});
  REQUIRE(
      std::holds_alternative<HybridPortfolioObjectiveIncomplete>(interrupted));
  CHECK(std::get<HybridPortfolioObjectiveIncomplete>(interrupted)
            .branches_without_comparable_bounds == std::vector<std::size_t>{1});
}

TEST_CASE("hybrid path optimal-face candidates preserve the full minimizer "
          "equations") {
  auto check_face = [&](TerminalObjective objective, double objective_value) {
    auto system = example_system();
    system.modes[0].control_sets[0] = interval("bounded-control", -1, 1);
    system.edges[0].reset_relations[0] = affine_reset();
    auto request = example_request();
    request.terminal_objectives[0].objective = std::move(objective);
    auto built = build_hybrid_path_program(system, request, example_path(),
                                           {"hybrid-face"}, {16, 64, 1024});
    REQUIRE(std::holds_alternative<HybridPathProgram>(built));
    const auto &branch = std::get<HybridPathProgram>(built);
    const ProgramIdentity identity = std::visit(
        [](const auto &program) { return program.identity(); }, branch.program);
    const auto support =
        SymbolicArgument{"literal face fixture", "synthetic global optimum"};
    const ProgramBoundEvidence bound{identity, support, {}};
    ProgramResult solved{Termination::completed,
                         {identity, MathematicalOutcome::optimal, support, {}},
                         Vector{2, -1, 1, 1, 0},
                         {ProgramObjectiveBound{objective_value, bound},
                          ProgramObjectiveBound{objective_value, bound}},
                         "literal feasible optimizer"};
    const auto face = build_hybrid_path_optimal_face_candidate(branch, solved,
                                                               {1e-10, 1e-10});
    REQUIRE(std::holds_alternative<HybridPathOptimalFaceCandidate>(face));
    const auto &candidate = std::get<HybridPathOptimalFaceCandidate>(face);
    CHECK(candidate.path == example_path());
    CHECK(candidate.anchor == Vector{2, -1, 1, 1, 0});
    CHECK(candidate.solver_result.objective.upper->value == objective_value);
    const auto representation = candidate.relation.representation();
    REQUIRE(std::holds_alternative<sets::HRepresentation>(representation));
    const auto &h = std::get<sets::HRepresentation>(representation);
    CHECK(satisfies(h, {2, -1, 1, 1, 0}));
    CHECK(satisfies(h, {2, -1, 1, 1, 1}));
    CHECK_FALSE(satisfies(h, {2, 0, 2, 2, 0}));
    CHECK(candidate.assumptions.size() == 3);
  };

  check_face(LinearTerminal{{1, 0}, 0}, 1);
  check_face(QuadraticTerminal{Matrix{2, 2, {2, 0, 0, 0}}, Vector{0, 0}, 0}, 1);
  check_face(ResidualNormTerminal{Matrix{1, 2, {1, 0}}, Vector{1}}, 0);

  auto system = example_system();
  system.modes[0].control_sets[0] = interval("bounded-control-mismatch", -1, 1);
  system.edges[0].reset_relations[0] = affine_reset();
  auto request = example_request();
  request.terminal_objectives[0].objective = LinearTerminal{{1, 0}, 0};
  auto built =
      build_hybrid_path_program(system, request, example_path(),
                                {"hybrid-face-mismatch"}, {16, 64, 1024});
  REQUIRE(std::holds_alternative<HybridPathProgram>(built));
  auto mismatched = std::get<HybridPathProgram>(std::move(built));
  const auto &program = std::get<LinearProgram>(mismatched.program);
  const auto support =
      SymbolicArgument{"literal mismatch fixture", "synthetic global optimum"};
  const ProgramBoundEvidence bound{program.identity(), support, {}};
  ProgramResult solved{
      Termination::completed,
      {program.identity(), MathematicalOutcome::optimal, support, {}},
      Vector{2, -1, 1, 1, 0},
      {ProgramObjectiveBound{1, bound}, ProgramObjectiveBound{1, bound}},
      "literal feasible optimizer"};
  mismatched.joint_relation = relation_excluding_anchor();
  const auto rejected = build_hybrid_path_optimal_face_candidate(
      mismatched, solved, {1e-10, 1e-10});
  REQUIRE(std::holds_alternative<Diagnostics>(rejected));
  CHECK(std::get<Diagnostics>(rejected)[0].field ==
        "hybrid.optimal_face.source_relation");
}

TEST_CASE("hybrid portfolio assembly retains every tied branch face transactionally") {
    auto system=example_system();
    auto parallel=system.edges.front();
    parallel.id={"switch-parallel-face"};
    system.edges.push_back(std::move(parallel));
    auto request=example_request();
    request.terminal_objectives[0].objective=LinearTerminal{{0,0},0};
    const auto built=build_hybrid_portfolio_programs(system,request,{"hybrid-face-portfolio"},
        {1,8},{16,64,1024});
    REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(built));
    const auto& programs=std::get<std::vector<HybridPathProgram>>(built);
    REQUIRE(programs.size()==2);

    HybridPortfolioExecution execution;
    execution.all_supplied_branches_completed=true;
    for(const auto& branch:programs) {
        const auto& program=std::get<LinearProgram>(branch.program);
        const auto support=SymbolicArgument{"constant objective","all feasible points minimize"};
        const ProgramBoundEvidence bound{program.identity(),support,{}};
        ProgramResult result{Termination::completed,
            {program.identity(),MathematicalOutcome::optimal,support,{}},Vector{2,0,2,0,0},
            {ProgramObjectiveBound{0,bound},ProgramObjectiveBound{0,bound}},"constant objective fixture"};
        execution.branches.push_back({branch.path,Termination::completed,MathematicalOutcome::optimal,
            std::move(result),{{"fixture",{ModuleId{"test-provider"},{}},{}}},{}});
    }
    const auto assembled=assemble_hybrid_portfolio_optimal_face_candidates(programs,execution,{0,0});
    REQUIRE(std::holds_alternative<HybridPortfolioOptimalFaceCandidates>(assembled));
    const auto& portfolio=std::get<HybridPortfolioOptimalFaceCandidates>(assembled);
    REQUIRE(portfolio.branches.size()==2);
    CHECK(portfolio.branches[0].path==programs[0].path);
    CHECK(portfolio.branches[1].path==programs[1].path);
    REQUIRE(portfolio.branches[0].providers.size()==1);
    CHECK(portfolio.branches[0].providers[0].port=="fixture");
    CHECK(portfolio.branches[0].providers[0].requested.id.value=="test-provider");
    CHECK(portfolio.branches[0].assumptions.back()=="family completeness and global cross-branch optimality remain unverified");

    auto duplicate_programs=programs;
    duplicate_programs.push_back(programs.front());
    const auto duplicate_paths=assemble_hybrid_portfolio_optimal_face_candidates(
        duplicate_programs,execution,{0,0});
    REQUIRE(std::holds_alternative<Diagnostics>(duplicate_paths));
    CHECK(std::get<Diagnostics>(duplicate_paths)[0].field=="hybrid.optimal_face.path");

    std::stop_source cancellation;
    cancellation.request_stop();
    const auto cancelled=assemble_hybrid_portfolio_optimal_face_candidates(
        programs,execution,{0,0},cancellation.get_token());
    REQUIRE(std::holds_alternative<OperationStopped>(cancelled));
    CHECK(std::get<OperationStopped>(cancelled).reason==StopReason::cancelled);
}

TEST_CASE("hybrid portfolio builder rejects a pre-cancelled request") {
    auto system=example_system();
    std::stop_source source;
    source.request_stop();
    const auto built=build_hybrid_portfolio_programs(system,example_request(),{"hybrid-problem"},
        {1,8},{16,64,1024},{},source.get_token());
    REQUIRE(std::holds_alternative<OperationStopped>(built));
    CHECK(std::get<OperationStopped>(built).reason==StopReason::cancelled);
}

TEST_CASE("zero-horizon synthesis and verification use the initial terminal singleton") {
    auto parked=[](model::HybridModeId id) {
        model::HybridMode mode{std::move(id),1,0,{"x"},{}};
        mode.flow=LinearStage{Matrix{1,1,{1}},Matrix{1,0,{}},Matrix{1,0,{}},Vector{0}};
        mode.invariants={interval("zero-horizon-"+mode.id.value,1,3)};
        return mode;
    };
    model::HybridSystem system{0,{parked({"parked"})},{}};
    model::HybridRequest request{{{"parked"},{2}},{{"parked"}},
        {{{"parked"},LinearTerminal{{2},3},"energy","J"}}};

    const auto built=build_hybrid_portfolio_programs(system,request,{"zero-horizon"},
        {0,8},{4,64,1024});
    REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(built));
    const auto& programs=std::get<std::vector<HybridPathProgram>>(built);
    REQUIRE(programs.size()==1);
    CHECK(programs[0].path.modes==std::vector<model::HybridModeId>{{"parked"}});
    CHECK(programs[0].path.edges.empty());
    CHECK(programs[0].joint_relation.metadata()->set.dimension==1);
    const auto representation=programs[0].joint_relation.representation();
    REQUIRE(std::holds_alternative<sets::HRepresentation>(representation));
    const auto& relation=std::get<sets::HRepresentation>(representation);
    REQUIRE(relation.equalities.rows()==1);
    CHECK(relation.equalities.cols()==1);
    CHECK(relation.equalities(0,0)==1);
    CHECK(relation.equality_values[0]==2);
    REQUIRE(relation.inequalities.rows()==2);
    CHECK(relation.inequalities(0,0)==-1);
    CHECK(relation.upper_bounds[0]==-1);
    CHECK(relation.inequalities(1,0)==1);
    CHECK(relation.upper_bounds[1]==3);

    const auto& linear=std::get<LinearProgram>(programs[0].program);
    REQUIRE(linear.objective().size()==1);
    CHECK(linear.objective()[0]==2);
    CHECK(linear.offset()==3);
    CHECK(linear.objective()[0]*2+linear.offset()==7);
    CHECK(std::get<LinearTerminal>(programs[0].lifted_objective).offset==3);

    auto candidate=exact_candidate(programs[0],{2});
    candidate.relation=singleton_data({2});
    ExactLinearHHybridFamilyVerifier verifier;
    const auto verified=verify_hybrid_portfolio_family(verifier,system,request,
        programs,std::span<const HybridPathOptimalFaceCandidate>(&candidate,1),
        {0,8},{0,0});
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(verified));
    const auto& report=std::get<HybridFamilyVerificationReport>(verified);
    REQUIRE(report.branches.size()==1);
    for(const auto& diagnostic:report.branches.front().diagnostics)
        MESSAGE(diagnostic.field << ": " << diagnostic.explanation);
    CHECK(report.global_objective_optimality==HybridVerificationStatus::established);
    CHECK(report.complete_family_coverage==HybridVerificationStatus::established);
    CHECK(report.branches[0].path.edges.empty());
    CHECK(report.branches[0].feasibility==HybridVerificationStatus::established);
    CHECK(report.branches[0].objective_optimality==HybridVerificationStatus::established);
    CHECK(report.branches[0].continuous_coverage==HybridVerificationStatus::established);

    model::HybridSystem unreachable_system{0,
        {parked({"parked"}),parked({"elsewhere"})},{}};
    model::HybridRequest unreachable_request{{{"parked"},{2}},{{"elsewhere"}},
        {{{"elsewhere"},LinearTerminal{{1},0},"energy","J"}}};
    RejectingTrajectoryPreflightAdapter trajectory;
    FixtureHybridFamilyVerifier unreachable_verifier;
    const auto rejected=build_hybrid_portfolio_programs_with_verifier(unreachable_verifier,
        trajectory,unreachable_system,unreachable_request,{"zero-horizon-no-terminal"},
        {0,8},{4,64,1024});
    REQUIRE(std::holds_alternative<Diagnostics>(rejected));
    const auto& rejection_diagnostics=std::get<Diagnostics>(rejected);
    REQUIRE_FALSE(rejection_diagnostics.empty());
    CHECK(rejection_diagnostics.front().field=="hybrid.verification.paths");
    CHECK(trajectory.preflight_calls==0);
    CHECK(trajectory.capability_calls==0);
    CHECK(trajectory.build_calls==0);
    CHECK(unreachable_verifier.preflight_calls==0);
    CHECK(unreachable_verifier.capability_calls==0);
    CHECK(unreachable_verifier.calls==0);
}

TEST_CASE("hybrid portfolio builder rolls back after a later dimension limit failure") {
    auto [system,request]=variable_size_parallel_profile();
    const auto built=build_hybrid_portfolio_programs(system,request,{"hybrid-problem"},
        {1,8},{3,64,4096});
    REQUIRE(std::holds_alternative<model::HybridPathCompositionFailureReport>(built));
    const auto& failure=std::get<model::HybridPathCompositionFailureReport>(built);
    CHECK(failure.path.edges==std::vector<model::HybridEdgeId>{{"to-large"}});
    CHECK(failure.limits.max_variables==3);
    const auto* diagnostic=std::get_if<Diagnostic>(&failure.failure);
    REQUIRE(diagnostic);
    CHECK(diagnostic->field=="hybrid.relation.variables");
}

TEST_CASE("hybrid portfolio preflights lifted objective storage before any adapter build") {
    for(const bool residual:{false,true}) {
        auto [system,request]=variable_size_parallel_profile();
        request.allowed_terminal_modes={{"small"},{"large"}};
        request.terminal_objectives.resize(2);
        request.terminal_objectives[0]={{"small"},LinearTerminal{{0},0},"cost","u"};
        request.terminal_objectives[1].mode={"large"};
        request.terminal_objectives[1].units="u";
        if(residual) {
            request.terminal_objectives[1].objective=
                ResidualNormTerminal{Matrix{4,2,{1,0,0,1,1,1,-1,1}},Vector{0,0,0,0}};
        } else {
            request.terminal_objectives[1].objective=
                QuadraticTerminal{Matrix{2,2,{1,0,0,1}},Vector{0,0},0};
        }

        constexpr model::HybridRelationLimits limits{8,16,15};
        const auto enumeration=model::enumerate_hybrid_paths(system,request.initial.mode,
            request.allowed_terminal_modes,{1,8});
        REQUIRE(std::holds_alternative<std::vector<model::HybridPath>>(enumeration));
        const auto& paths=std::get<std::vector<model::HybridPath>>(enumeration);
        REQUIRE(paths.size()==2);
        const auto relation_preflight=model::preflight_hybrid_path_relations(
            system,request,paths,limits);
        CHECK(std::holds_alternative<std::monostate>(relation_preflight));
        RecordingDefaultPreflightTrajectoryAdapter adapter;
        const auto result=build_hybrid_portfolio_programs(adapter,system,request,
            {"objective-storage-admission"},{1,8},limits);
        REQUIRE(std::holds_alternative<model::HybridPathCompositionFailureReport>(result));
        const auto& failure=std::get<model::HybridPathCompositionFailureReport>(result);
        CHECK(failure.path.edges==std::vector<model::HybridEdgeId>{{"to-large"}});
        CHECK(failure.limits.max_matrix_elements==15);
        const auto* diagnostic=std::get_if<Diagnostic>(&failure.failure);
        REQUIRE(diagnostic);
        CHECK(diagnostic->field=="hybrid.objective.storage");
        CHECK(adapter.capability_calls==0);
        CHECK(adapter.build_calls==0);
    }
}

TEST_CASE("direct trajectory adapters preflight the full path inventory before capabilities or builds") {
    auto [system,request]=variable_size_parallel_profile();
    RejectingTrajectoryPreflightAdapter adapter;
    const auto portfolio=build_hybrid_portfolio_programs(adapter,system,
        request,{"hybrid-problem"},{1,8},{16,64,1024});
    REQUIRE(std::holds_alternative<model::HybridPathCompositionFailureReport>(portfolio));
    const auto& failure=std::get<model::HybridPathCompositionFailureReport>(portfolio);
    CHECK(failure.path.edges==std::vector<model::HybridEdgeId>{{"to-wide"}});
    CHECK(std::get<Diagnostic>(failure.failure).field=="fixture.trajectory.preflight");
    CHECK(adapter.preflight_calls==1);
    CHECK(adapter.preflight_path_count==3);
    CHECK(adapter.capability_calls==0);
    CHECK(adapter.build_calls==0);

    const auto composed=build_hybrid_portfolio_programs(system,request,
        {"three-branch-inventory"},{1,8},{8,64,4096});
    REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(composed));
    const auto& programs=std::get<std::vector<HybridPathProgram>>(composed);
    REQUIRE(programs.size()==3);
    CHECK(programs[0].path.edges==std::vector<model::HybridEdgeId>{{"to-small"}});
    CHECK(programs[1].path.edges==std::vector<model::HybridEdgeId>{{"to-large"}});
    CHECK(programs[2].path.edges==std::vector<model::HybridEdgeId>{{"to-wide"}});
    CHECK(programs[0].joint_relation.metadata()->set.dimension==3);
    CHECK(programs[1].joint_relation.metadata()->set.dimension==4);
    CHECK(programs[2].joint_relation.metadata()->set.dimension==5);

    RejectingTrajectoryPreflightAdapter single_adapter;
    const auto single=build_hybrid_path_program(single_adapter,example_system(),
        example_request(),example_path(),{"hybrid-problem"},{16,64,1024});
    REQUIRE(std::holds_alternative<model::HybridPathCompositionFailureReport>(single));
    CHECK(std::get<model::HybridPathCompositionFailureReport>(single).path==example_path());
    CHECK(single_adapter.preflight_calls==1);
    CHECK(single_adapter.preflight_path_count==1);
    CHECK(single_adapter.capability_calls==0);
    CHECK(single_adapter.build_calls==0);
}

TEST_CASE("direct trajectory preflight rejects a partial success receipt before capabilities or builds") {
    auto [system,request]=variable_size_parallel_profile();
    PartialReceiptTrajectoryPreflightAdapter adapter;
    const auto result=build_hybrid_portfolio_programs(adapter,system,request,
        {"partial-preflight-receipt"},{1,8},{16,64,1024});
    REQUIRE(std::holds_alternative<model::HybridPathCompositionFailureReport>(result));
    const auto& failure=std::get<model::HybridPathCompositionFailureReport>(result);
    CHECK(failure.path.edges==std::vector<model::HybridEdgeId>{{"to-large"}});
    const auto* diagnostic=std::get_if<Diagnostic>(&failure.failure);
    REQUIRE(diagnostic);
    CHECK(diagnostic->field=="hybrid.adapter.preflight_success_inventory");
    CHECK(adapter.capability_calls==0);
    CHECK(adapter.build_calls==0);
}

TEST_CASE("direct trajectory preflight rejects incomplete operation admission before capabilities or builds") {
    auto [system,request]=variable_size_parallel_profile();
    PartialReceiptTrajectoryPreflightAdapter adapter(1);
    const auto result=build_hybrid_portfolio_programs(adapter,system,request,
        {"partial-operation-receipt"},{1,8},{16,64,1024});
    REQUIRE(std::holds_alternative<model::HybridPathCompositionFailureReport>(result));
    const auto& failure=std::get<model::HybridPathCompositionFailureReport>(result);
    CHECK(failure.path.edges==std::vector<model::HybridEdgeId>{{"to-small"}});
    const auto* diagnostic=std::get_if<Diagnostic>(&failure.failure);
    REQUIRE(diagnostic);
    CHECK(diagnostic->field=="hybrid.adapter.preflight_success_operations");
    CHECK(adapter.capability_calls==0);
    CHECK(adapter.build_calls==0);
}

TEST_CASE("direct trajectory preflight rejects reordered or extra operation receipt entries") {
    for(const int corruption:{2,3}) {
        auto [system,request]=variable_size_parallel_profile();
        PartialReceiptTrajectoryPreflightAdapter adapter(corruption);
        const auto result=build_hybrid_portfolio_programs(adapter,system,request,
            {"invalid-operation-order"},{1,8},{16,64,1024});
        REQUIRE(std::holds_alternative<model::HybridPathCompositionFailureReport>(result));
        const auto& failure=std::get<model::HybridPathCompositionFailureReport>(result);
        const auto* diagnostic=std::get_if<Diagnostic>(&failure.failure);
        REQUIRE(diagnostic);
        CHECK(diagnostic->field=="hybrid.adapter.preflight_success_operations");
        CHECK(adapter.capability_calls==0);
        CHECK(adapter.build_calls==0);
    }
}

TEST_CASE("later unsupported guard and reset operations reject the full inventory before branch builds") {
    for(const bool unsupported_reset:{false,true}) {
        auto [system,request]=variable_size_parallel_profile();
        const std::size_t dimension=unsupported_reset?4:1;
        auto vertices=numeric::snapshot(Matrix{1,dimension,Vector(dimension,0.0)});
        auto rays=numeric::snapshot(Matrix{0,dimension,{}});
        REQUIRE(std::holds_alternative<numeric::MatrixView>(vertices));
        REQUIRE(std::holds_alternative<numeric::MatrixView>(rays));
        auto representation=sets::make_v({SetId{unsupported_reset?
            "later-branch-v-reset":"later-branch-v-guard"},dimension,{}},
            {std::get<numeric::MatrixView>(vertices),std::get<numeric::MatrixView>(rays)});
        REQUIRE(std::holds_alternative<sets::SetData>(representation));
        if(unsupported_reset)
            system.edges.back().reset_relations[0]=
                std::get<sets::SetData>(std::move(representation)).as_handle();
        else
            system.edges.back().guards[0]=
                std::get<sets::SetData>(std::move(representation)).as_handle();

        RecordingDefaultPreflightTrajectoryAdapter adapter;
        const auto result=build_hybrid_portfolio_programs(adapter,system,request,
            {"complete-operation-inventory"},{1,8},{16,64,1024});
        REQUIRE(std::holds_alternative<model::HybridPathCompositionFailureReport>(result));
        const auto& failure=std::get<model::HybridPathCompositionFailureReport>(result);
        CHECK(failure.path.edges==std::vector<model::HybridEdgeId>{{"to-wide"}});
        CHECK(failure.operations.empty());
        const auto* diagnostic=std::get_if<Diagnostic>(&failure.failure);
        REQUIRE(diagnostic);
        CHECK(diagnostic->field==(unsupported_reset?
            "hybrid.reset.representation":"hybrid.guard.representation"));
        CHECK(diagnostic->explanation.find("stage 0 edge to-wide")!=std::string::npos);
        CHECK(adapter.capability_calls==0);
        CHECK(adapter.build_calls==0);
    }
}

TEST_CASE("direct trajectory adapters may admit a representation outside the joint-H default") {
    auto system=example_system();
    system.edges.front().guards.front()=vertex_guard("alternate-guard");
    AdmittingTrajectoryPreflightAdapter adapter;
    const auto result=build_hybrid_path_program(adapter,system,example_request(),
        example_path(),{"hybrid-problem"},{16,64,1024});
    REQUIRE(std::holds_alternative<Diagnostics>(result));
    CHECK(std::get<Diagnostics>(result).front().field=="fixture.alternate_representation");
    CHECK(adapter.preflight_calls==1);
    CHECK(adapter.capability_calls==1);
    CHECK(adapter.build_calls==1);
}

TEST_CASE("direct trajectory preflight admits adapter-specific numerical tolerance policies") {
    const optimization::ObjectivePolicy accepted_policy{
        Assurance::numerical,{0.125,0.25}};
    PolicyAwareTrajectoryAdapter accepting(accepted_policy);
    const auto accepted=build_hybrid_path_program(accepting,example_system(),
        example_request(),example_path(),{"hybrid-problem"},{16,64,1024},accepted_policy);
    REQUIRE(std::holds_alternative<Diagnostics>(accepted));
    CHECK(std::get<Diagnostics>(accepted).front().field=="fixture.trajectory.policy_adapter");
    REQUIRE(accepting.observed_policy.has_value());
    CHECK(accepting.observed_policy->assurance==accepted_policy.assurance);
    CHECK(accepting.observed_policy->numerical.absolute_tolerance==0.125);
    CHECK(accepting.observed_policy->numerical.relative_tolerance==0.25);
    CHECK(accepting.preflight_calls==1);
    CHECK(accepting.capability_calls==1);
    CHECK(accepting.build_calls==1);

    PolicyAwareTrajectoryAdapter rejecting(accepted_policy);
    const auto rejected=build_hybrid_path_program(rejecting,example_system(),
        example_request(),example_path(),{"hybrid-problem"},{16,64,1024});
    REQUIRE(std::holds_alternative<model::HybridPathCompositionFailureReport>(rejected));
    const auto& failure=std::get<model::HybridPathCompositionFailureReport>(rejected);
    REQUIRE(std::holds_alternative<Diagnostic>(failure.failure));
    CHECK(std::get<Diagnostic>(failure.failure).field=="fixture.trajectory.objective_policy");
    REQUIRE(rejecting.observed_policy.has_value());
    CHECK(rejecting.observed_policy->numerical.absolute_tolerance==1e-8);
    CHECK(rejecting.observed_policy->numerical.relative_tolerance==1e-8);
    CHECK(rejecting.preflight_calls==1);
    CHECK(rejecting.capability_calls==0);
    CHECK(rejecting.build_calls==0);
}

TEST_CASE("direct trajectory preflight failures must retain requested path and limits") {
    for(const int corruption : {0,1,2}) {
        RejectingTrajectoryPreflightAdapter adapter;
        adapter.corruption=corruption;
        const model::HybridRelationLimits limits{16,64,1024};
        const auto result=build_hybrid_path_program(adapter,example_system(),
            example_request(),example_path(),{"hybrid-problem"},limits);
        REQUIRE(std::holds_alternative<model::HybridPathCompositionFailureReport>(result));
        const auto& failure=std::get<model::HybridPathCompositionFailureReport>(result);
        CHECK(failure.path==example_path());
        CHECK(failure.limits.max_variables==limits.max_variables);
        CHECK(failure.limits.max_rows==limits.max_rows);
        CHECK(failure.limits.max_matrix_elements==limits.max_matrix_elements);
        const auto* diagnostic=std::get_if<Diagnostic>(&failure.failure);
        REQUIRE(diagnostic);
        CHECK(diagnostic->code==DiagnosticCode::evidence_mismatch);
        const auto expected=corruption==0?"hybrid.adapter.preflight_path":
            (corruption==1?"hybrid.adapter.preflight_limits":"hybrid.adapter.preflight_diagnostics");
        CHECK(diagnostic->field==expected);
        CHECK(adapter.capability_calls==0);
        CHECK(adapter.build_calls==0);
    }
}

TEST_CASE("portfolio uses one inventory-wide trajectory preflight before branch builds") {
    auto [system,request]=variable_size_parallel_profile();
    InventoryOnlyTrajectoryPreflightAdapter adapter;
    const auto result=build_hybrid_portfolio_programs(adapter,system,request,
        {"hybrid-problem"},{1,8},{16,64,1024});
    REQUIRE(std::holds_alternative<Diagnostics>(result));
    CHECK(std::get<Diagnostics>(result).front().field=="fixture.inventory_build");
    CHECK(adapter.preflight_calls==1);
    CHECK(adapter.capability_calls==1);
    CHECK(adapter.build_calls==1);
}

TEST_CASE("hybrid portfolio rejects an empty path inventory before adapter preflight") {
    auto system=example_system();
    system.edges.clear();
    RejectingTrajectoryPreflightAdapter adapter;
    const auto result=build_hybrid_portfolio_programs(adapter,system,example_request(),
        {"hybrid-problem"},{1,8},{16,64,1024});
    REQUIRE(std::holds_alternative<Diagnostics>(result));
    CHECK(std::get<Diagnostics>(result).front().field=="hybrid.portfolio.paths");
    CHECK(adapter.preflight_calls==0);
    CHECK(adapter.capability_calls==0);
    CHECK(adapter.build_calls==0);
}

TEST_CASE("direct trajectory preflight observes cancellation before capabilities and builds") {
    std::stop_source cancellation;
    CancellingTrajectoryPreflightAdapter adapter{cancellation};
    const auto result=build_hybrid_path_program(adapter,example_system(),
        example_request(),example_path(),{"hybrid-problem"},{16,64,1024},
        {},cancellation.get_token());
    REQUIRE(std::holds_alternative<OperationStopped>(result));
    CHECK(std::get<OperationStopped>(result).reason==StopReason::cancelled);
    CHECK(adapter.capability_calls==0);
    CHECK(adapter.build_calls==0);
}

TEST_CASE("hybrid branch execution retains path and solver provenance on rejection") {
    auto built=build_hybrid_path_program(example_system(),example_request(),example_path(),
        {"hybrid-problem"},{16,64,1024});
    REQUIRE(std::holds_alternative<HybridPathProgram>(built));
    const std::array<HybridPathProgram,1> programs{std::get<HybridPathProgram>(std::move(built))};
    const auto report=execute_hybrid_path_programs(programs,lp_provider(),convex_provider(),{});
    REQUIRE(report.branches.size()==1);
    CHECK_FALSE(report.all_supplied_branches_completed);
    CHECK(report.branches[0].path==example_path());
    CHECK(report.branches[0].termination==Termination::operation_rejected);
    REQUIRE(report.branches[0].providers.size()==1);
    REQUIRE(report.branches[0].providers[0].actual);
    CHECK(report.branches[0].providers[0].actual->id.value=="reject-lp");
    REQUIRE(report.branches[0].diagnostics.size()==1);
    CHECK(report.branches[0].diagnostics[0].field=="fixture.lp");
}

TEST_CASE("hybrid branch execution records cancellation without invoking a provider") {
    auto built=build_hybrid_path_program(example_system(),example_request(),example_path(),
        {"hybrid-problem"},{16,64,1024});
    REQUIRE(std::holds_alternative<HybridPathProgram>(built));
    const std::array<HybridPathProgram,1> programs{std::get<HybridPathProgram>(std::move(built))};
    std::stop_source cancellation;
    cancellation.request_stop();
    const ExecutionContext context{{},{cancellation.get_token()},{},{1e-8,1e-8},{},{}};
    const auto report=execute_hybrid_path_programs(programs,lp_provider(),convex_provider(),context);
    REQUIRE(report.branches.size()==1);
    CHECK_FALSE(report.all_supplied_branches_completed);
    CHECK(report.branches[0].termination==Termination::cancelled);
    CHECK(report.branches[0].providers.empty());
    CHECK_FALSE(report.branches[0].result.has_value());
}

TEST_CASE("hybrid branch execution records an expired deadline before provider preparation") {
    auto built=build_hybrid_path_program(example_system(),example_request(),example_path(),
        {"hybrid-problem"},{16,64,1024});
    REQUIRE(std::holds_alternative<HybridPathProgram>(built));
    const std::array<HybridPathProgram,1> programs{std::get<HybridPathProgram>(std::move(built))};
    auto factory_calls=std::make_shared<int>(0);
    const ExecutionContext context{{},{},std::chrono::steady_clock::now()-std::chrono::milliseconds(1),
        {1e-8,1e-8},{},{}};
    const auto report=execute_hybrid_path_programs(programs,lp_provider(nullptr,factory_calls),
        convex_provider(),context);
    REQUIRE(report.branches.size()==1);
    CHECK_FALSE(report.all_supplied_branches_completed);
    CHECK(report.branches[0].termination==Termination::resource_limit);
    CHECK(report.branches[0].providers.empty());
    CHECK(*factory_calls==0);
}

TEST_CASE("hybrid branch execution observes cancellation after provider preparation") {
    auto first=build_hybrid_path_program(example_system(),example_request(),example_path(),
        {"first-problem"},{16,64,1024});
    auto second=build_hybrid_path_program(example_system(),example_request(),example_path(),
        {"stop-during-prepare"},{16,64,1024});
    REQUIRE(std::holds_alternative<HybridPathProgram>(first));
    REQUIRE(std::holds_alternative<HybridPathProgram>(second));
    const std::array<HybridPathProgram,2> programs{
        std::get<HybridPathProgram>(std::move(first)),std::get<HybridPathProgram>(std::move(second))};
    std::stop_source cancellation;
    auto factory_calls=std::make_shared<int>(0);
    const ExecutionContext context{{},cancellation.get_token(),{},{1e-8,1e-8},{},{}};
    const auto report=execute_hybrid_path_programs(programs,
        lp_provider(&cancellation,factory_calls,{},"stop-during-prepare"),
        convex_provider(),context);
    REQUIRE(report.branches.size()==2);
    CHECK_FALSE(report.all_supplied_branches_completed);
    CHECK(report.branches[0].termination==Termination::cancelled);
    CHECK(*factory_calls==0);
    REQUIRE(report.branches[0].providers.size()==1);
    CHECK_FALSE(report.branches[0].result.has_value());
    CHECK(report.branches[0].diagnostics[0].field=="hybrid.portfolio.preflight_interrupted");
    CHECK(report.branches[1].termination==Termination::cancelled);
    CHECK(report.branches[1].diagnostics.empty());
}

TEST_CASE("hybrid branch execution retains a completed solver result and provenance") {
    auto built=build_hybrid_path_program(example_system(),example_request(),example_path(),
        {"hybrid-problem"},{16,64,1024});
    REQUIRE(std::holds_alternative<HybridPathProgram>(built));
    const std::array<HybridPathProgram,1> programs{std::get<HybridPathProgram>(std::move(built))};
    const auto report=execute_hybrid_path_programs(programs,completing_lp_provider(),convex_provider(),{});
    REQUIRE(report.branches.size()==1);
    CHECK(report.all_supplied_branches_completed);
    CHECK(report.branches[0].path==example_path());
    CHECK(report.branches[0].termination==Termination::completed);
    CHECK(report.branches[0].outcome==MathematicalOutcome::undetermined);
    REQUIRE(report.branches[0].result);
    CHECK(report.branches[0].result->raw_diagnostics=="fixture completed");
    REQUIRE(report.branches[0].providers.size()==1);
    REQUIRE(report.branches[0].providers[0].actual);
    CHECK(report.branches[0].providers[0].actual->id.value=="completing-lp");
}

TEST_CASE("hybrid guard entry and exit constrain the pre-reset state") {
    auto system=example_system();
    system.edges[0].guards[0]=interval("guard-3-to-4",3,4);
    const auto relation=model::compose_hybrid_path_relation(system,example_request(),example_path(),
        {16,64,1024});
    REQUIRE(std::holds_alternative<sets::SetData>(relation));
    const auto representation=std::get<sets::SetData>(relation).representation();
    REQUIRE(std::holds_alternative<sets::HRepresentation>(representation));
    const auto& h=std::get<sets::HRepresentation>(representation);
    CHECK(satisfies(h,{2,1,3,0,0}));
    CHECK(satisfies(h,{2,2,4,0,0}));
    CHECK_FALSE(satisfies(h,{2,0,2,0,0}));
    CHECK_FALSE(satisfies(h,{2,3,5,0,0}));
}

TEST_CASE("hybrid empty guard produces an explicitly empty branch relation") {
    auto system=example_system();
    system.edges[0].guards[0]=EmptySet{1};
    const auto relation=model::compose_hybrid_path_relation(system,example_request(),example_path(),
        {16,64,1024});
    REQUIRE(std::holds_alternative<sets::SetData>(relation));
    const auto representation=std::get<sets::SetData>(relation).representation();
    REQUIRE(std::holds_alternative<sets::HRepresentation>(representation));
    const auto& h=std::get<sets::HRepresentation>(representation);
    bool contradictory_row=false;
    for(std::size_t i=0;i<h.inequalities.rows();++i) {
        bool zero=true;
        for(std::size_t j=0;j<h.inequalities.cols();++j) zero=zero && h.inequalities(i,j)==0;
        if(zero && h.upper_bounds[i]<0) contradictory_row=true;
    }
    CHECK(contradictory_row);
}

TEST_CASE("hybrid portfolio admits every branch before creating any solver workspace") {
    auto first=build_hybrid_path_program(example_system(),example_request(),example_path(),
        {"accepted-problem"},{16,64,1024});
    auto rejected=build_hybrid_path_program(example_system(),example_request(),example_path(),
        {"rejected-problem"},{16,64,1024});
    REQUIRE(std::holds_alternative<HybridPathProgram>(first));
    REQUIRE(std::holds_alternative<HybridPathProgram>(rejected));
    const std::array<HybridPathProgram,2> programs{
        std::get<HybridPathProgram>(std::move(first)),std::get<HybridPathProgram>(std::move(rejected))};
    auto factory_calls=std::make_shared<int>(0);
    const auto report=execute_hybrid_path_programs(programs,
        lp_provider(nullptr,factory_calls,"rejected-problem"),convex_provider(),{});
    REQUIRE(report.branches.size()==2);
    CHECK_FALSE(report.all_supplied_branches_completed);
    CHECK(*factory_calls==0);
    CHECK(report.branches[0].termination==Termination::operation_rejected);
    CHECK(report.branches[0].diagnostics[0].field=="hybrid.portfolio.admission");
    CHECK(report.branches[1].termination==Termination::operation_rejected);
    CHECK(report.branches[1].diagnostics[0].field=="fixture.capability");
}
