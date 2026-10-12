#include <csl/geometry/affine_sum.hpp>
#include <csl/adapters/lp/highs.hpp>
#include <csl/adapters/polyhedral/qhull.hpp>
#include <csl/sets/data.hpp>
#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <type_traits>
#include <vector>
#include <iomanip>
#include <iostream>
#include <numeric>
#include <sstream>
#include <stdexcept>

using namespace csl;
using namespace csl::registry;
namespace {
using Clock=std::chrono::steady_clock;
struct Timer { Clock::time_point t{Clock::now()}; std::uint64_t ns()const{return std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now()-t).count();} };
template<class T,class...R>T take(std::variant<T,R...> x){if(!std::holds_alternative<T>(x))throw std::runtime_error("provider or geometry operation failed");return std::get<T>(std::move(x));}
template<class P>PreparedProvider<P> prepared(Registration<P> entry,std::string id,Requirements req={}){
 if constexpr(std::is_same_v<P,LPPort>)req.output.representation={"csl.program-result.v1"};
 Registry<P> registry; if(registry.add(std::move(entry)))throw std::runtime_error("registration conflict");
 const auto& stored=registry; return take(prepare_provider(select_provider(stored,Method{ModuleId{std::move(id)},std::nullopt},req)));
}
numeric::MatrixView matrix(std::size_t r,std::size_t c,Vector v){return take(numeric::snapshot(Matrix{r,c,std::move(v)}));}
SetHandle points(std::string id,std::size_t dim,Vector values,std::size_t rows){
 return take(sets::make_v({{std::move(id)},dim,{}},{matrix(rows,dim,std::move(values)),matrix(0,dim,{})})).as_handle();
}
struct Case{std::string id; SetHandle left,right; bool sum; Matrix map; Vector offset; std::vector<Vector> expected; std::vector<Vector> dirs; Vector support;};
Case make_case(int i){
 if(i==0)return {"scalar_interval_affine_image",points("interval",1,{-1,1},2),{},false,{1,1,{-2}},{0},{{-2},{2}},{{1},{-1}},{2,2}};
 if(i==1)return {"rectangular_projection_box",points("box",2,{0,0,0,1,1,0,1,1},4),{},false,{1,2,{1,1}},{0},{{0},{2}},{{1},{-1}},{2,0}};
 if(i==2)return {"singular_map_box_segment",points("box",2,{0,0,0,1,1,0,1,1},4),{},false,{2,2,{1,1,2,2}},{0,0},{{0,0},{2,4}},{{1,0},{-1,0},{0,1},{0,-1}},{2,0,4,0}};
 return {"minkowski_interval_sum",points("left",1,{-1,1},2),points("right",1,{2,3},2),true,{},{},{{1},{4}},{{1},{-1}},{4,-1}};
}
bool near(double a,double b){return std::abs(a-b)<=1e-8;}
std::string q(std::string x){std::string o="\"";for(char c:x){if(c=='\"')o+="\"\"";else if(c=='\n'||c=='\r')o+=' ';else o+=c;}return o+'\"';}
std::string json_string(const std::string& x){std::ostringstream o;o<<'\"';for(unsigned char c:x){if(c=='\"')o<<"\\\"";else if(c=='\\')o<<"\\\\";else if(c=='\n')o<<"\\n";else if(c=='\r')o<<"\\r";else if(c=='\t')o<<"\\t";else if(c<0x20)o<<"\\u00"<<std::hex<<std::setw(2)<<std::setfill('0')<<static_cast<unsigned>(c)<<std::dec;else o<<static_cast<char>(c);}o<<'\"';return o.str();}
struct Result{std::string scenario,status="failed",detail;int repetition{};std::uint64_t setup{},operation{},oracle{},total{};std::size_t support_checks{};std::string points_json="[]",support_json="[]";bool pass{};};
void run(Result& r,const Case& c){Timer total;try{
 auto hull=prepared(geometry::make_lp_hull_reducer_registration(),"csl.hull.lp-membership"); auto lp=prepared(take(adapters::lp::make_highs_registration()),"csl.lp.highs");
 geometry::AffineSumDependencies deps{std::move(hull),std::move(lp),std::nullopt};
 Registry<GeometryPort> operations; if(operations.add(geometry::make_affine_sum_registration(std::move(deps))))throw std::runtime_error("affine-sum registration failed");
 OperationRequest request{{{"geo02-report"},{c.id+"-"+std::to_string(r.repetition)},{"geo02-output"}},{"csl.geometry.affine-sum"},c.sum?GeometryOperation{MinkowskiSum{c.left,c.right}}:GeometryOperation{AffineImage{c.left,c.map,c.offset}},SetRelation::equivalent,Assurance::numerical};
 Requirements req;req.output.representation={"csl.polyhedron.v"};req.output.relation=SetRelation::equivalent;
 auto prep=prepare_pipeline(select(operations,{{"csl.geometry.affine-sum"},{}},request,req));auto* pipeline=std::get_if<PreparedPipeline<GeometryPort>>(&prep);if(!pipeline)throw std::runtime_error("operation rejected");auto [workspace]=pipeline->create();r.setup=total.ns();
 Timer op;auto outcome=workspace->run({{},{},{},{1e-8,1e-8},"geo02-report"});r.operation=op.ns();auto* result=std::get_if<OperationResult>(&outcome);if(!result)throw std::runtime_error("affine-sum operation incomplete");
 auto data=take(sets::from_handle(result->output));auto rep=data.representation();auto* v=std::get_if<sets::VRepresentation>(&rep);if(!v||v->rays.rows())throw std::runtime_error("expected bounded V representation");
 std::ostringstream pts,sups;pts<<std::setprecision(17)<<'[';for(std::size_t i=0;i<v->vertices.rows();++i){if(i)pts<<',';pts<<'[';for(std::size_t j=0;j<v->vertices.cols();++j){if(j)pts<<',';pts<<v->vertices(i,j);}pts<<']';}pts<<']';r.points_json=pts.str();
 Timer oracle;bool ok=v->vertices.rows()>=c.expected.size()&&v->vertices.cols()==c.expected.front().size();
 for(const auto& x:std::vector<Vector>{c.expected.front(),c.expected.back()}){bool found=false;for(std::size_t i=0;i<v->vertices.rows();++i){bool same=true;for(std::size_t j=0;j<x.size();++j)same&=near(v->vertices(i,j),x[j]);if(same)found=true;}ok&=found;}
 if(v->vertices.cols()==1){double lo=std::min(c.expected.front()[0],c.expected.back()[0]),hi=std::max(c.expected.front()[0],c.expected.back()[0]);for(std::size_t i=0;i<v->vertices.rows();++i)ok&=v->vertices(i,0)>=lo-1e-8&&v->vertices(i,0)<=hi+1e-8;}
 else if(v->vertices.cols()==2){const auto& a=c.expected.front();const auto& b=c.expected.back();double dx=b[0]-a[0],dy=b[1]-a[1],norm=dx*dx+dy*dy;for(std::size_t i=0;i<v->vertices.rows();++i){double qx=v->vertices(i,0)-a[0],qy=v->vertices(i,1)-a[1],t=(qx*dx+qy*dy)/norm;ok&=t>=-1e-8&&t<=1+1e-8&&near(qx,t*dx)&&near(qy,t*dy);}}
 sups<<std::setprecision(17)<<'[';for(std::size_t k=0;k<c.dirs.size();++k){if(k)sups<<',';double best=-1e300;for(std::size_t i=0;i<v->vertices.rows();++i){double z=0;for(std::size_t j=0;j<v->vertices.cols();++j)z+=c.dirs[k][j]*v->vertices(i,j);best=std::max(best,z);}sups<<best;ok&=near(best,c.support[k]);}sups<<']';r.support_json=sups.str();r.support_checks=c.dirs.size();r.oracle=oracle.ns();r.pass=ok;r.status=ok?"passed":"oracle_failed";
 }catch(const std::exception&e){r.detail=e.what();}r.total=total.ns();}
}
int main(int argc,char**argv){try{
 int reps=7,warmups=1;
 for(int i=1;i<argc;++i){std::string a=argv[i];if(a=="--smoke")reps=1;else if(a=="--repetitions"&&i+1<argc)reps=std::stoi(argv[++i]);else if(a=="--warmups"&&i+1<argc)warmups=std::stoi(argv[++i]);else throw std::runtime_error("usage: csl_geo02_affine_sum_report [--smoke | --repetitions N --warmups N]");}
 if(reps<1||warmups<1)throw std::runtime_error("at least one measured repetition and warmup are required");
 int warmup_failures=0;
 for(int w=0;w<warmups;++w)for(int i=0;i<4;++i){
  auto c=make_case(i);Result r;r.scenario=c.id;r.repetition=w;run(r,c);
  const bool warmup_passed=r.status=="passed"&&r.pass;
  if(!warmup_passed)++warmup_failures;
  std::cerr<<"geo02_warmup={\"scenario\":"<<json_string(c.id)<<",\"repetition\":"<<w
           <<",\"status\":"<<json_string(r.status)<<",\"detail\":"<<json_string(r.detail)
           <<",\"output_points\":"<<r.points_json<<",\"support_checks\":"<<r.support_checks
           <<",\"support_values\":"<<r.support_json<<",\"oracle_passed\":"<<(r.pass?"true":"false")<<"}\n";
 }
 std::cout<<"scenario,repetition,status,detail,setup_ns,operation_ns,oracle_ns,total_ns,output_points,support_checks,support_values,oracle_passed\n";
 bool pass=warmup_failures==0;
 for(int rep=0;rep<reps;++rep)for(int i=0;i<4;++i){
  Timer trial;auto c=make_case(i);Result r;r.scenario=c.id;r.repetition=rep;run(r,c);
  r.total=trial.ns();
  if(r.setup>r.total||r.operation>r.total-r.setup||r.oracle>r.total-r.setup-r.operation)throw std::runtime_error("measured phases exceed total trial time");
  pass&=r.status=="passed"&&r.pass;
  std::cout<<r.scenario<<','<<rep<<','<<r.status<<','<<q(r.detail)<<','<<r.setup<<','<<r.operation<<','<<r.oracle<<','<<r.total<<','<<q(r.points_json)<<','<<r.support_checks<<','<<q(r.support_json)<<','<<(r.pass?"true":"false")<<'\n';
 }
 return pass?0:2;
 }catch(const std::exception&e){std::cerr<<"geo02_error="<<e.what()<<'\n';return 2;}}
