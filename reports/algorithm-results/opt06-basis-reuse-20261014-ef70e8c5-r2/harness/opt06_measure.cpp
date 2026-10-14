#include <csl/adapters/lp/highs.hpp>
#include <csl/geometry/basis_reuse_reducer.hpp>
#include <csl/geometry/hull_reducer.hpp>
#include <algorithm>
#include <chrono>
#include <cmath>
#include <iostream>
#include <memory>
#include <set>
#include <string>
#include <variant>

using namespace csl;
namespace {
struct Case { const char* id; geometry::PointCloud cloud; };
std::vector<Case> cases() {
 return {
  {"permuted", {{"opt06-permuted"}, {{0,0},{1,1},{2,0},{0,2},{2,2},{1,0},{1,2},{0,1},{2,1},{1,1.5}}}},
  {"degenerate", {{"opt06-degenerate"}, {{0,0},{2,0},{2,2},{0,2},{0,0},{1,0},{1,2}}}},
  {"interior-basis", {{"opt06-interior-basis"}, {{1,1},{0,0},{2,0},{2,2},{0,2}}}}
 };
}
std::unique_ptr<LPWorkspace> workspace() {
 auto registration=adapters::lp::make_highs_registration();
 if(!std::holds_alternative<registry::Registration<registry::LPPort>>(registration)) return {};
 auto adapter=std::get<registry::Registration<registry::LPPort>>(std::move(registration));
 auto seed=optimization::make_linear_program({{{"opt06"},{"workspace-seed"}}, {}, 0, {0,0,{0},{},{ }}, {}, {}});
 if(!std::holds_alternative<LinearProgram>(seed)) return {};
 return adapter.factory(std::get<LinearProgram>(seed));
}
bool member(LPWorkspace& lp,const geometry::PointCloud& cloud,const std::vector<std::size_t>& hull,std::size_t candidate) {
 const auto dim=cloud.points[candidate].size();
 SparseMatrix a{dim+1,hull.size(),{0},{},{}}; Vector rhs=cloud.points[candidate]; rhs.push_back(1.0);
 for(std::size_t r=0;r<=dim;++r){for(std::size_t c=0;c<hull.size();++c){a.column_indices.push_back(c);a.values.push_back(r==dim?1.0:cloud.points[hull[c]][r]);}a.row_offsets.push_back(a.values.size());}
 std::vector<Interval> eq; for(double x:rhs)eq.push_back({x,x});
 auto p=optimization::make_linear_program({{cloud.problem,{"oracle-"+std::to_string(candidate)}},Vector(hull.size(),0),0,std::move(a),std::vector<Interval>(hull.size(),{0,std::nullopt}),std::move(eq)});
 if(!std::holds_alternative<LinearProgram>(p))return false;
 auto out=lp.solve(std::get<LinearProgram>(p),{}); if(!std::holds_alternative<ProgramResult>(out))return false;
 const auto&r=std::get<ProgramResult>(out); if(r.termination!=Termination::completed||r.outcome.value!=MathematicalOutcome::optimal||!r.primal)return false;
 double sum=0; Vector x(dim,0); for(std::size_t c=0;c<hull.size();++c){auto w=(*r.primal)[c]; if(w < -1e-9)return false;sum+=w;for(std::size_t j=0;j<dim;++j)x[j]+=w*cloud.points[hull[c]][j];}
 if(std::abs(sum-1)>1e-8)return false;for(std::size_t j=0;j<dim;++j)if(std::abs(x[j]-cloud.points[candidate][j])>1e-8)return false;return true;
}
bool equivalent(LPWorkspace& oracle,const geometry::PointCloud& cloud,const std::vector<std::size_t>&a,const std::vector<std::size_t>&b){
 for(auto i:a)if(!member(oracle,cloud,b,i))return false;
 for(auto i:b)if(!member(oracle,cloud,a,i))return false;return true;
}
bool valid_ids(const std::vector<std::size_t>& ids,std::size_t point_count){
 if(ids.empty())return false;std::set<std::size_t> unique;
 for(const auto id:ids)if(id>=point_count||!unique.insert(id).second)return false;
 return true;
}
bool contains_all_inputs(LPWorkspace& oracle,const geometry::PointCloud& cloud,const std::vector<std::size_t>& hull){
 if(!valid_ids(hull,cloud.points.size()))return false;
 for(std::size_t input=0;input<cloud.points.size();++input)if(!member(oracle,cloud,hull,input))return false;
 return true;
}
bool validator_contract_test(){
 if(!valid_ids({0,2},3)||valid_ids({1,1},3)||valid_ids({3},3)||valid_ids({},3))return false;
 auto lp=workspace();if(!lp)return false;
 const geometry::PointCloud cloud{{"opt06-validator-contract"},{{1,1},{0,0},{2,0},{2,2},{0,2}}};
 return contains_all_inputs(*lp,cloud,{0,1,2,3,4})&&!contains_all_inputs(*lp,cloud,{1});
}
struct Row{std::string method,case_id;bool warmup,verified;long long ns;std::size_t lp,basis_solves,removed,retained,candidates;std::uint64_t pivots,degenerate;bool fallback;std::vector<std::size_t> basis;std::vector<std::size_t> retained_ids;bool output_ids_valid{},contains_all_inputs{};};
Row run(const Case& test,const char* method,bool warmup,std::size_t round){auto lp=workspace();if(!lp)throw std::runtime_error("workspace creation failed");auto start=std::chrono::steady_clock::now();geometry::HullReductionResult out=std::string(method)=="baseline"?geometry::reduce_hull(test.cloud,*lp,{}):geometry::reduce_hull_basis_reuse(test.cloud,*lp,{});auto end=std::chrono::steady_clock::now();auto ns=std::chrono::duration_cast<std::chrono::nanoseconds>(end-start).count();if(!std::holds_alternative<geometry::HullReduction>(out))return{method,test.id,warmup,false,ns};const auto&r=std::get<geometry::HullReduction>(out);Row row{method,test.id,warmup,r.status==geometry::ReductionStatus::complete,ns,r.lp_calls,0,r.removed.size(),r.retained.size(),0,0,0,false,{},r.retained};if(r.basis_reuse){row.basis_solves=r.basis_reuse->basis_solves;row.candidates=r.basis_reuse->bulk_candidates;row.pivots=r.basis_reuse->pivots;row.degenerate=r.basis_reuse->degenerate_pivots;row.fallback=r.basis_reuse->fell_back_to_lp_baseline;row.basis=r.basis_reuse->structural_basis_points;}if(r.status!=geometry::ReductionStatus::complete)row.verified=false;return row;}
void print(const Row&r,std::size_t round){std::cout<<"{\"round\":"<<round<<",\"case_id\":\""<<r.case_id<<"\",\"method\":\""<<r.method<<"\",\"warmup\":"<<(r.warmup?"true":"false")<<",\"elapsed_ns\":"<<r.ns<<",\"status\":\""<<(r.verified?"complete":"failed")<<"\",\"verified\":"<<(r.verified?"true":"false")<<",\"output_ids_valid\":"<<(r.output_ids_valid?"true":"false")<<",\"contains_all_inputs\":"<<(r.contains_all_inputs?"true":"false")<<",\"lp_calls\":"<<r.lp<<",\"basis_solves\":"<<r.basis_solves<<",\"pivots\":"<<r.pivots<<",\"degenerate_pivots\":"<<r.degenerate<<",\"bulk_candidates\":"<<r.candidates<<",\"bulk_removals\":"<<r.removed<<",\"retained\":"<<r.retained<<",\"fallback\":"<<(r.fallback?"true":"false")<<",\"retained_points\":[";for(std::size_t i=0;i<r.retained_ids.size();++i){if(i)std::cout<<",";std::cout<<r.retained_ids[i];}std::cout<<"],\"basis_points\":[";for(std::size_t i=0;i<r.basis.size();++i){if(i)std::cout<<",";std::cout<<r.basis[i];}std::cout<<"]}\n";}
}
int main(){try{if(!validator_contract_test())throw std::runtime_error("output validator contract self-test failed");auto cs=cases();constexpr int reps=7;for(auto&t:cs){auto a=run(t,"baseline",true,0);auto b=run(t,"basis-reuse",true,0);auto oracle=workspace();if(!oracle)throw std::runtime_error("warmup oracle workspace failed");a.output_ids_valid=valid_ids(a.retained_ids,t.cloud.points.size());b.output_ids_valid=valid_ids(b.retained_ids,t.cloud.points.size());a.contains_all_inputs=a.output_ids_valid&&contains_all_inputs(*oracle,t.cloud,a.retained_ids);b.contains_all_inputs=b.output_ids_valid&&contains_all_inputs(*oracle,t.cloud,b.retained_ids);if(a.verified&&b.verified&&a.contains_all_inputs&&b.contains_all_inputs&&equivalent(*oracle,t.cloud,a.retained_ids,b.retained_ids)){}else{a.verified=b.verified=false;}print(a,0);print(b,0);if(!a.verified||!b.verified)throw std::runtime_error(std::string("warmup output validation failed for ")+t.id);}
for(int round=0;round<reps;++round)for(auto&t:cs){const bool reverse=(round%2)!=0;Row a=run(t,reverse?"basis-reuse":"baseline",false,round);Row b=run(t,reverse?"baseline":"basis-reuse",false,round);auto oracle=workspace();if(!oracle)throw std::runtime_error("oracle workspace failed"); // separate untimed oracle pair below
 a.output_ids_valid=valid_ids(a.retained_ids,t.cloud.points.size());b.output_ids_valid=valid_ids(b.retained_ids,t.cloud.points.size());a.contains_all_inputs=a.output_ids_valid&&contains_all_inputs(*oracle,t.cloud,a.retained_ids);b.contains_all_inputs=b.output_ids_valid&&contains_all_inputs(*oracle,t.cloud,b.retained_ids);
 if(!a.output_ids_valid||!b.output_ids_valid||!a.contains_all_inputs||!b.contains_all_inputs||!equivalent(*oracle,t.cloud,a.retained_ids,b.retained_ids))a.verified=b.verified=false;
 print(a,round+1);print(b,round+1);if(!a.verified||!b.verified)throw std::runtime_error(std::string("timed result or hull oracle failed for ")+t.id);
}
}catch(const std::exception&e){std::cerr<<"measurement failure: "<<e.what()<<"\n";return 1;}return 0;}

