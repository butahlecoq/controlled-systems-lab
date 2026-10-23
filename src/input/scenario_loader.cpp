#include "scenario_json.hpp"
#include <csl/sets/data.hpp>
#include <algorithm>
#include <limits>

namespace csl::input {
LoadedScenario::LoadedScenario(std::shared_ptr<const detail::ScenarioStorage> s):storage_(std::move(s)) {}
problem::ResolvedProblem LoadedScenario::problem() const {return storage_->problem;}
std::shared_ptr<const RequestedRun> LoadedScenario::requested_run() const noexcept {return {storage_,&storage_->run};}
std::shared_ptr<const std::vector<DefaultRecord>> LoadedScenario::defaults() const noexcept {return {storage_,&storage_->defaults};}
std::shared_ptr<const ScenarioMetadata> LoadedScenario::metadata() const noexcept {return {storage_,&storage_->metadata};}
std::shared_ptr<const SourceProvenance> LoadedScenario::source() const noexcept {return {storage_,&storage_->source};}
HistoricalScenario::HistoricalScenario(std::shared_ptr<const detail::HistoricalStorage> s):storage_(std::move(s)) {}
std::shared_ptr<const HistoricalRecord> HistoricalScenario::record() const noexcept {return {storage_,&storage_->record};}
std::shared_ptr<const SourceProvenance> HistoricalScenario::source() const noexcept {return {storage_,&storage_->source};}
namespace detail {
namespace {
std::string kind(const Json& value,const std::string& path,const char* category,
                 std::initializer_list<std::string_view> supported,
                 std::initializer_list<std::string_view> reserved,const char* expected) {
    if(!value.is_object()) fail(path,value.type_name(),"object with required string member \"kind\"");
    const auto it=value.find("kind");
    const auto form=std::string("string ")+category+" kind from the closed v1 discriminator table";
    if(it==value.end() || !it->is_string()) fail(child(path,"kind"),it==value.end()?"missing":it->type_name(),form);
    const auto text=it->get<std::string>();
    if(std::find(reserved.begin(),reserved.end(),text)!=reserved.end()) throw UnsupportedInput{text,child(path,"kind"),text,expected};
    if(std::find(supported.begin(),supported.end(),text)==supported.end()) fail(child(path,"kind"),text,form);
    return text;
}
class Reader {
    const LoadOptions& options_;
    std::size_t coefficients_{},expanded_{},objects_{};
public:
    std::vector<DefaultRecord> defaults;
    explicit Reader(const LoadOptions& o):options_(o) {}
    std::size_t product(std::size_t a,std::size_t b,const std::string& path) const {
        if(b && a>std::numeric_limits<std::size_t>::max()/b) fail(path,"extent product overflow","representable extent",InputCategory::limit);
        return a*b;
    }
    void expansion(std::size_t scalars,std::size_t objects,const std::string& path) {
        poll(options_);
        const auto& l=options_.limits;
        if(scalars>l.expanded_scalars-expanded_) fail(path,"expanded scalar quota exceeded","bounded canonical expansion",InputCategory::limit);
        expanded_+=scalars;
        if(objects>std::numeric_limits<std::size_t>::max()-objects_) fail(path,"object count overflow","bounded canonical expansion",InputCategory::limit);
        objects_+=objects;
        const auto scalar_bytes=product(expanded_,16,path),object_bytes=product(objects_,256,path);
        if(scalar_bytes>l.identity_bytes || object_bytes>l.identity_bytes-scalar_bytes || l.identity_bytes-scalar_bytes-object_bytes<1024)
            fail(path,"estimated identity quota exceeded","bounded canonical identity encoding",InputCategory::limit);
    }
    std::size_t dimension(std::size_t n,const std::string& path) const {
        if(n>options_.limits.dimension) fail(path,"dimension exceeds quota","bounded dimension",InputCategory::limit);
        return n;
    }
    Vector vector(const Json& v,const std::string& path) {
        if(!v.is_array()) fail(path,v.type_name(),"array of finite numbers");
        expansion(v.size(),1,path);Vector out;out.reserve(v.size());
        for(std::size_t i=0;i<v.size();++i) out.push_back(number(v[i],child(path,std::to_string(i))));
        return out;
    }
    Vector vector(const Json& v,std::size_t size,const std::string& path) {
        if(!v.is_array() || v.size()!=size) fail(path,"wrong vector shape","array of "+std::to_string(size)+" finite numbers");
        return vector(v,path);
    }
    Matrix matrix(const Json& v,const std::string& path) {
        std::size_t rows=0,cols=0;
        const Json* flat=nullptr;
        if(v.is_object()) {
            if(v.contains("kind") && v["kind"]=="external") {
                object(v,path,{"kind","uri","sha256","rows","cols","layout"});
                (void)string(member(v,"uri",path),child(path,"uri"));
                const auto hash=string(member(v,"sha256",path),child(path,"sha256"));
                if(hash.size()!=64 || !std::all_of(hash.begin(),hash.end(),[](char c){return (c>='0' && c<='9') || (c>='a' && c<='f');}))
                    fail(child(path,"sha256"),"invalid digest spelling","64 lowercase hexadecimal characters");
                (void)count(member(v,"rows",path),child(path,"rows"));(void)count(member(v,"cols",path),child(path,"cols"));
                if(string(member(v,"layout",path),child(path,"layout"))!="row_major") fail(child(path,"layout"),"unknown layout","row_major");
                throw UnsupportedInput{"external matrix",path,"external descriptor","inline matrix data; external matrix IO is not supported in v1"};
            }
            object(v,path,{"rows","cols","values"});
            rows=dimension(count(member(v,"rows",path),child(path,"rows")),child(path,"rows"));
            cols=dimension(count(member(v,"cols",path),child(path,"cols")),child(path,"cols"));
            flat=&member(v,"values",path);
        } else {
            if(!v.is_array()) fail(path,v.type_name(),"rectangular row arrays or explicit rows/cols/values");
            rows=dimension(v.size(),path);
            if(rows && !v[0].is_array()) fail(child(path,"0"),v[0].type_name(),"row array");
            cols=dimension(rows?v[0].size():0,path);
        }
        const auto entries=product(rows,cols,path);
        if(flat && (!flat->is_array() || flat->size()!=entries)) fail(child(path,"values"),"wrong flat value count","rows*cols values in row-major order");
        if(entries>options_.limits.matrix_coefficients-coefficients_) fail(path,"matrix coefficient quota exceeded","bounded input coefficients",InputCategory::limit);
        coefficients_+=entries;expansion(entries,1,path);
        Matrix m{rows,cols,{}};m.values.reserve(entries);
        if(flat) {
            for(std::size_t i=0;i<entries;++i) m.values.push_back(number((*flat)[i],child(child(path,"values"),std::to_string(i))));
        } else for(std::size_t i=0;i<rows;++i) {
            if(!v[i].is_array() || v[i].size()!=cols) fail(child(path,std::to_string(i)),"ragged row","row of "+std::to_string(cols)+" numbers");
            for(std::size_t j=0;j<cols;++j) m.values.push_back(number(v[i][j],child(child(path,std::to_string(i)),std::to_string(j))));
        }
        return m;
    }
    SystemModel model(const Json& root,std::size_t horizon) {
        const auto& value=member(root,"model","");
        const auto tag=kind(value,"/model","model",{"linear_discrete","affine_discrete","linear_discrete_ltv","affine_discrete_ltv"},
            {"linear_continuous","affine_continuous","linear_continuous_ltv","affine_continuous_ltv"},"a discrete transition model; continuous-time input is not supported in v1");
        const bool indexed=tag.ends_with("_ltv"),affine=tag.starts_with("affine");
        const auto stage=[&](const Json& v,const std::string& path,bool outer) {
            if(outer) {
                if(affine) object(v,path,{"kind","A","B","offset"});else object(v,path,{"kind","A","B"});
            } else {
                if(affine) object(v,path,{"A","B","offset"});else object(v,path,{"A","B"});
            }
            auto A=matrix(member(v,"A",path),child(path,"A")),B=matrix(member(v,"B",path),child(path,"B"));
            if(A.rows!=A.cols) fail(child(path,"A"),"nonsquare","square transition matrix");
            if(B.rows!=A.rows) fail(child(path,"B"),"wrong row count","rows matching A");
            const auto n=A.rows;
            if(!affine) {expansion(n,1,child(path,"offset"));defaults.push_back({child(path,"offset"),"zero by linear kind",false});}
            auto offset=affine?vector(member(v,"offset",path),n,child(path,"offset")):Vector(n,0);
            return LinearStage{std::move(A),std::move(B),{n,0,{}},std::move(offset)};
        };
        Dimensions dims{};Coefficients coefficients;
        if(indexed) {
            object(value,"/model",{"kind","stages"});const auto& stages=member(value,"stages","/model");
            if(!stages.is_array() || stages.size()!=horizon) fail("/model/stages","wrong stage count","array of T dynamics stages");
            expansion(0,horizon,"/model/stages");std::vector<LinearStage> items;items.reserve(horizon);
            for(std::size_t i=0;i<horizon;++i) {
                auto item=stage(stages[i],"/model/stages/"+std::to_string(i),false);
                if(i && (item.A.rows!=dims.state || item.B.cols!=dims.control)) fail("/model/stages/"+std::to_string(i),"inconsistent dimensions","same state/control widths at every stage");
                dims={item.A.rows,item.B.cols,0};items.push_back(std::move(item));
            }
            coefficients=std::move(items);
        } else {auto item=stage(value,"/model",true);dims={item.A.rows,item.B.cols,0};coefficients=std::move(item);}
        if(root.contains("dimensions")) {
            const auto& declared=root["dimensions"];object(declared,"/dimensions",{"state","control","external"});
            const Dimensions explicit_dims{dimension(count(member(declared,"state","/dimensions"),"/dimensions/state"),"/dimensions/state"),
                dimension(count(member(declared,"control","/dimensions"),"/dimensions/control"),"/dimensions/control"),count(member(declared,"external","/dimensions"),"/dimensions/external")};
            if(explicit_dims.external!=0) fail("/dimensions/external","nonzero external dimension","zero nominal external width");
            if(indexed && horizon==0) dims=explicit_dims;
            else if(dims.state!=explicit_dims.state || dims.control!=explicit_dims.control) fail("/dimensions","inconsistent declared dimensions","dimensions matching A and B");
        } else if(indexed && horizon==0) fail("/dimensions","missing for empty indexed provider","explicit state/control/external dimensions at T=0");
        return {{dims,TimeDomain::discrete,std::move(coefficients)},{}};
    }
    Vector times(const Json& root,std::size_t horizon) {
        Vector result;
        if(root.contains("times")) result=vector(root["times"],horizon+1,"/times");
        else {expansion(horizon+1,1,"/times");result.reserve(horizon+1);for(std::size_t i=0;i<=horizon;++i) result.push_back(static_cast<double>(i));}
        for(std::size_t i=1;i<result.size();++i) if(!(result[i]>result[i-1])) fail(child("/times",std::to_string(i)),"not strictly increasing","finite strictly increasing times");
        defaults.push_back({"/times",root.contains("times")?"authored transition times":"stage indices, no physical unit",root.contains("times")});
        return result;
    }
    AdmissibleSet h_set(Matrix H,Vector h,Matrix E,Vector e,std::size_t dim,const std::string& path) {
        if(H.cols!=dim) fail(child(path,"H"),"wrong column count","columns matching set dimension");
        if(E.cols!=dim) fail(child(path,"E"),"wrong column count","columns matching set dimension");
        return canonical<sets::SetData>(sets::make_h({{path},dim,{}},{canonical<numeric::MatrixView>(numeric::snapshot(H),child(path,"H")),
            canonical<numeric::VectorView>(numeric::snapshot_vector(h),child(path,"h")),canonical<numeric::MatrixView>(numeric::snapshot(E),child(path,"E")),
            canonical<numeric::VectorView>(numeric::snapshot_vector(e),child(path,"e"))}),path).as_handle();
    }
    AdmissibleSet box(const Json& v,std::size_t dim,const std::string& path) {
        object(v,path,{"kind","lower","upper"});
        const auto& lower=member(v,"lower",path);const auto& upper=member(v,"upper",path);
        for(const auto* key:{"lower","upper"}) if(!v[key].is_array() || v[key].size()!=dim) fail(child(path,key),"wrong bound vector","array of set dimension with finite or null endpoints");
        std::vector<Interval> bounds;bounds.reserve(dim);std::size_t rows=0;
        for(std::size_t i=0;i<dim;++i) {
            Interval bound;
            if(!lower[i].is_null()) {bound.lower=number(lower[i],child(child(path,"lower"),std::to_string(i)));++rows;}
            if(!upper[i].is_null()) {bound.upper=number(upper[i],child(child(path,"upper"),std::to_string(i)));++rows;}
            if(bound.lower && bound.upper && *bound.lower>*bound.upper) fail(path,"reversed endpoints","lower <= upper");
            bounds.push_back(bound);
        }
        const auto entries=product(rows,dim,path);expansion(entries+rows,2,path);
        Matrix H{rows,dim,Vector(entries,0)};Vector h;h.reserve(rows);std::size_t row=0;
        for(std::size_t i=0;i<dim;++i) {
            if(bounds[i].upper) {H.values[row++*dim+i]=1;h.push_back(*bounds[i].upper);}
            if(bounds[i].lower) {H.values[row++*dim+i]=-1;h.push_back(-*bounds[i].lower);}
        }
        return h_set(std::move(H),std::move(h),{0,dim,{}},{},dim,path);
    }
    AdmissibleSet set(const Json& value,std::size_t dim,const std::string& path) {
        const auto tag=kind(value,path,"set",{"empty","universal","singleton","box","polyhedron_h","polyhedron_v"},{},"");
        expansion(0,1,path);
        if(tag=="empty" || tag=="universal") {object(value,path,{"kind"});if(tag=="empty") return EmptySet{dim};return UniversalSet{dim};}
        if(tag=="singleton") {object(value,path,{"kind","point"});return Singleton{vector(member(value,"point",path),dim,child(path,"point"))};}
        if(tag=="box") return box(value,dim,path);
        if(tag=="polyhedron_h") {
            object(value,path,{"kind","H","h","E","e"});
            auto H=matrix(member(value,"H",path),child(path,"H"));auto h=vector(member(value,"h",path),H.rows,child(path,"h"));
            auto E=matrix(member(value,"E",path),child(path,"E"));auto e=vector(member(value,"e",path),E.rows,child(path,"e"));
            return h_set(std::move(H),std::move(h),std::move(E),std::move(e),dim,path);
        }
        object(value,path,{"kind","vertices","rays"});
        auto V=matrix(member(value,"vertices",path),child(path,"vertices")),R=matrix(member(value,"rays",path),child(path,"rays"));
        if(V.cols!=dim) fail(child(path,"vertices"),"wrong column count","columns matching set dimension");
        if(R.cols!=dim) fail(child(path,"rays"),"wrong column count","columns matching set dimension");
        return canonical<sets::SetData>(sets::make_v({{path},dim,{}},{canonical<numeric::MatrixView>(numeric::snapshot(V),child(path,"vertices")),
            canonical<numeric::MatrixView>(numeric::snapshot(R),child(path,"rays"))}),path).as_handle();
    }
    std::vector<AdmissibleSet> sets(const Json& value,std::size_t dim,std::size_t stages,const std::string& path,bool controls) {
        const auto tag=kind(value,path,controls?"control":"set",{"empty","universal","singleton","box","polyhedron_h","polyhedron_v","stages"},
            controls?std::initializer_list<std::string_view>{"finite","mixed"}:std::initializer_list<std::string_view>{},"continuous control sets; finite and mixed domains are not supported in v1");
        if(tag=="stages") {
            object(value,path,{"kind","values"});const auto& values=member(value,"values",path);
            if(!values.is_array() || values.size()!=stages) fail(child(path,"values"),"wrong stage count","array of "+std::to_string(stages)+" sets");
            expansion(0,stages,path);std::vector<AdmissibleSet> out;out.reserve(stages);
            for(std::size_t i=0;i<stages;++i) out.push_back(set(values[i],dim,child(child(path,"values"),std::to_string(i))));
            return out;
        }
        const auto prior_scalars=expanded_,prior_objects=objects_;auto one=set(value,dim,path);
        if(stages>1) expansion(product(expanded_-prior_scalars,stages-1,path),product(objects_-prior_objects,stages-1,path),path);
        return std::vector<AdmissibleSet>(stages,one);
    }
    TerminalObjective objective(const Json& value,std::size_t dim) {
        const std::string path="/objective";
        const auto tag=kind(value,path,"objective",{"linear","quadratic","residual_norm","terminal_distance"},{"sum","mixed"},
            "one original linear, quadratic or residual-norm objective; sums and mixed objectives are not supported in v1");
        if(tag=="linear" || tag=="quadratic") {
            const char* coefficients=tag=="linear"?"coefficients":"linear";
            if(tag=="linear") object(value,path,{"kind","coefficients","offset"});else object(value,path,{"kind","Q","linear","offset"});
            const auto offset=value.contains("offset")?number(value["offset"],"/objective/offset"):0;
            defaults.push_back({"/objective/offset","zero when omitted",value.contains("offset")});
            auto linear=vector(member(value,coefficients,path),dim,child(path,coefficients));
            if(tag=="linear") return LinearTerminal{std::move(linear),offset};
            auto Q=matrix(member(value,"Q",path),"/objective/Q");
            if(Q.rows!=dim || Q.cols!=dim) fail("/objective/Q","wrong quadratic shape","square state-dimensional Q");
            return QuadraticTerminal{std::move(Q),std::move(linear),offset};
        }
        Matrix L{dim,dim,{}};
        if(tag=="terminal_distance") {
            object(value,path,{"kind","target"});const auto entries=product(dim,dim,path);expansion(entries,1,path);L.values.assign(entries,0);
            for(std::size_t i=0;i<dim;++i) L.values[i*dim+i]=1;
        } else {object(value,path,{"kind","L","target"});L=matrix(member(value,"L",path),"/objective/L");}
        if(L.cols!=dim) fail("/objective/L","wrong map width","columns matching state dimension");
        auto target=vector(member(value,"target",path),L.rows,"/objective/target");
        return ResidualNormTerminal{std::move(L),std::move(target)};
    }

    TemporalConstraints temporal(const Json& value,std::size_t n,std::size_t m,std::size_t horizon) {
        constexpr std::string_view order="x0,...,xT,u0,...,u(T-1)";
        const std::string path="/temporal";
        object(value,path,{"coordinate_order","rows","bounds"});
        if(string(member(value,"coordinate_order",path),child(path,"coordinate_order"))!=order)
            fail(child(path,"coordinate_order"),"unknown order","x0,...,xT,u0,...,u(T-1)");
        const auto state_width=product(horizon+1,n,child(path,"rows"));
        const auto control_width=product(horizon,m,child(path,"rows"));
        if(state_width>std::numeric_limits<std::size_t>::max()-control_width)
            fail(child(path,"rows"),"history width overflow","representable full-history width",InputCategory::limit);
        const auto width=state_width+control_width;
        auto rows=matrix(member(value,"rows",path),child(path,"rows"));
        if(rows.cols!=width)
            fail(child(path,"rows"),"wrong column count","columns matching canonical full-history width "+std::to_string(width));
        const auto& authored_bounds=member(value,"bounds",path);
        if(!authored_bounds.is_array() || authored_bounds.size()!=rows.rows)
            fail(child(path,"bounds"),"wrong row count","one interval per temporal row");
        std::vector<Interval> bounds;bounds.reserve(rows.rows);
        for(std::size_t i=0;i<rows.rows;++i) {
            const auto bound_path=child(child(path,"bounds"),std::to_string(i));
            const auto& entry=authored_bounds[i];object(entry,bound_path,{"lower","upper"});
            const auto endpoint=[&](const char* name) -> std::optional<double> {
                const auto field=child(bound_path,name);const auto& item=member(entry,name,bound_path);
                if(item.is_null()) return {};
                return number(item,field);
            };
            Interval bound{endpoint("lower"),endpoint("upper")};
            if(bound.lower && bound.upper && *bound.lower>*bound.upper)
                fail(bound_path,"reversed endpoints","lower <= upper");
            bounds.push_back(bound);
        }
        SparseMatrix sparse{rows.rows,rows.cols,{0},{},{}};
        sparse.values=std::move(rows.values);
        sparse.column_indices.reserve(sparse.values.size());
        for(std::size_t i=0;i<sparse.rows;++i) {
            for(std::size_t j=0;j<width;++j) sparse.column_indices.push_back(j);
            sparse.row_offsets.push_back(sparse.column_indices.size());
        }
        return {std::move(sparse),std::move(bounds)};
    }

    RequestedRun requested_run(const Json& root) {
        RequestedRun out;
        if(!root.contains("run")) return out;
        const auto& run=root["run"];
        object(run,"/run",{"comparison","methods","backends","witnesses","numerical","resources","seed"});
        if(run.contains("comparison") && run.contains("methods")) fail("/run/methods","conflicting selection","methods or comparison, not both");
        if(run.contains("comparison") && string(run["comparison"],"/run/comparison")!="historical_reachability_vs_joint_trajectory")
            fail("/run/comparison","unknown comparison","historical_reachability_vs_joint_trajectory");
        const auto module=[](const Json& value,const std::string& path) {
            object(value,path,{"id","version"});ModuleRequest request{{string(member(value,"id",path),child(path,"id"))},{}};
            if(request.id.value.empty()) fail(child(path,"id"),"empty","nonempty module ID");
            if(value.contains("version")) {request.version=string(value["version"],child(path,"version"));if(request.version->empty()) fail(child(path,"version"),"empty","nonempty requested version");}
            return request;
        };
        if(run.contains("methods")) {
            const auto& methods=run["methods"];if(!methods.is_array() || methods.empty()) fail("/run/methods","empty or non-array","nonempty array of module requests");
            std::vector<ModuleRequest> requests;requests.reserve(methods.size());
            for(std::size_t i=0;i<methods.size();++i) requests.push_back(module(methods[i],child("/run/methods",std::to_string(i))));
            out.selection=std::move(requests);
        }
        if(run.contains("backends")) {
            const auto& b=run["backends"];object(b,"/run/backends",{"lp","convex","hull","geometry","converter","approximation","selector","representation"});
            for(const auto& [name,role]:std::initializer_list<std::pair<const char*,BackendRole>>{{"lp",BackendRole::lp},{"convex",BackendRole::convex},{"hull",BackendRole::hull},{"geometry",BackendRole::geometry},{"converter",BackendRole::converter},{"approximation",BackendRole::approximation},{"selector",BackendRole::selector}})
                if(b.contains(name)) out.backends.emplace(role,module(b[name],child("/run/backends",name)));
            if(b.contains("representation")) {auto id=string(b["representation"],"/run/backends/representation");if(id.empty()) fail("/run/backends/representation","empty","nonempty representation ID");out.representation=RepresentationId{std::move(id)};}
        }
        const auto positive=[](const Json& value,const std::string& path) {const auto n=count(value,path);if(n==0) fail(path,"zero","positive integer");return n;};
        const auto tolerance=[](const Json& value,const std::string& path) {const auto n=number(value,path);if(n<0) fail(path,"negative","finite nonnegative number");return n;};
        if(run.contains("witnesses")) {
            const auto& w=run["witnesses"];object(w,"/run/witnesses",{"count","distinctness_tolerance","directions"});WitnessOptions request;
            if(w.contains("count")) request.count=positive(w["count"],"/run/witnesses/count");
            if(w.contains("distinctness_tolerance")) request.distinctness_tolerance=tolerance(w["distinctness_tolerance"],"/run/witnesses/distinctness_tolerance");
            if(w.contains("directions")) {
                const auto& d=w["directions"];if(!d.is_array()) fail("/run/witnesses/directions",d.type_name(),"array of finite vectors");
                request.directions.emplace();request.directions->reserve(d.size());
                for(std::size_t i=0;i<d.size();++i) request.directions->push_back(vector(d[i],child("/run/witnesses/directions",std::to_string(i))));
            }
            out.witnesses=std::move(request);
        }
        if(run.contains("numerical")) {
            const auto& p=run["numerical"];object(p,"/run/numerical",{"absolute_tolerance","relative_tolerance"});
            out.numerical=NumericalPolicy{tolerance(member(p,"absolute_tolerance","/run/numerical"),"/run/numerical/absolute_tolerance"),tolerance(member(p,"relative_tolerance","/run/numerical"),"/run/numerical/relative_tolerance")};
        }
        if(run.contains("resources")) {
            const auto& p=run["resources"];object(p,"/run/resources",{"total_threads","outer_workers","threads_per_worker","memory_bytes"});
            ResourcePolicy policy{positive(member(p,"total_threads","/run/resources"),"/run/resources/total_threads"),positive(member(p,"outer_workers","/run/resources"),"/run/resources/outer_workers"),positive(member(p,"threads_per_worker","/run/resources"),"/run/resources/threads_per_worker"),{}};
            if(p.contains("memory_bytes")) policy.memory_bytes=positive(p["memory_bytes"],"/run/resources/memory_bytes");
            const auto diagnostics=check_resources(policy);
            if(!diagnostics.empty()) throw InputFailure{InputCategory::field,"/run/resources",diagnostics[0].explanation,"valid resource policy",{},diagnostics[0]};
            out.resources=policy;
        }
        if(run.contains("seed")) out.seed=count(run["seed"],"/run/seed");
        return out;
    }
    ScenarioMetadata metadata(const Json& root,std::size_t n,std::size_t m) {
        ScenarioMetadata out;out.id=root.contains("id")?string(root["id"],"/id"):"";
        if(!root.contains("metadata")) return out;
        const auto& meta=root["metadata"];object(meta,"/metadata",{"title","description","state_labels","control_labels","state_units","control_units","time_unit"});
        for(const auto& [name,target]:std::initializer_list<std::pair<const char*,std::optional<std::string>*>>{{"title",&out.title},{"description",&out.description},{"time_unit",&out.time_unit}})
            if(meta.contains(name)) *target=string(meta[name],child("/metadata",name));
        for(const auto& [name,target]:std::initializer_list<std::pair<const char*,std::optional<std::vector<std::string>>*>>{{"state_labels",&out.state_labels},{"control_labels",&out.control_labels},{"state_units",&out.state_units},{"control_units",&out.control_units}}) {
            if(!meta.contains(name)) continue;
            const auto& list=meta[name];const auto size=std::string_view(name).starts_with("state")?n:m;const auto path=child("/metadata",name);
            if(!list.is_array() || list.size()!=size) fail(path,"wrong coordinate count","array matching coordinate dimension");
            target->emplace();(*target)->reserve(size);
            for(std::size_t i=0;i<size;++i) (*target)->push_back(string(list[i],child(path,std::to_string(i))));
        }
        return out;
    }
};
LoadedScenario translate(const Json& root,std::span<const std::byte> bytes,const LoadOptions& options,const std::filesystem::path& location) {
    Reader r(options);
    const auto schema=string(member(root,"schema",""),"/schema");
    const bool version_one=schema=="csl.scenario/1",version_two=schema=="csl.scenario/2";
    if(!version_one && !version_two) fail("/schema","unknown version","csl.scenario/1 or csl.scenario/2",InputCategory::schema);
    object(root,"",{"schema","id","horizon","times","dimensions","profile","model","initial_state","controls","states","objective","run","metadata",
        "initial_information","external","observations","information","uncertainty","temporal","hybrid"});
    for(const auto required:{"horizon","model","initial_state","controls","objective"}) (void)member(root,required,"");
    if(root.contains("initial_information")) fail("/initial_information","conflicting initial declarations","initial_state and initial_information must not coexist");
    if(root.contains("profile") && (!root["profile"].is_string() || root["profile"]!="nominal_discrete_v1"))
        fail("/profile",root["profile"].is_string()?root["profile"].get<std::string>():root["profile"].type_name(),"string \"nominal_discrete_v1\"");
    r.defaults.push_back({"/profile","nominal_discrete_v1",root.contains("profile")});
    for(const auto reserved:{"initial_information","external","observations","information","uncertainty","hybrid"})
        if(root.contains(reserved)) throw UnsupportedInput{reserved,child("",reserved),"present","omitted unsupported structure in a nominal scenario"};
    if(version_one && root.contains("temporal"))
        throw UnsupportedInput{"temporal","/temporal","present","omitted temporal relation in nominal v1"};
    const auto horizon=count(member(root,"horizon",""),"/horizon");
    if(horizon>options.limits.horizon) fail("/horizon","horizon exceeds quota","bounded horizon",InputCategory::limit);
    auto model=r.model(root,horizon);const auto n=model.dynamics.dimensions.state,m=model.dynamics.dimensions.control;
    r.expansion(r.product(horizon+1,n,"/horizon")+r.product(horizon,m,"/horizon"),2*horizon+1,"/horizon");
    auto times=r.times(root,horizon);
    const auto initial=r.vector(member(root,"initial_state",""),n,"/initial_state");
    auto controls=r.sets(member(root,"controls",""),m,horizon,"/controls",true);
    auto states=root.contains("states")?r.sets(root["states"],n,horizon+1,"/states",false):std::vector<AdmissibleSet>(horizon+1,UniversalSet{n});
    std::optional<TemporalConstraints> temporal;
    if(version_two && root.contains("temporal")) temporal=r.temporal(root["temporal"],n,m,horizon);
    auto objective=r.objective(member(root,"objective",""),n);
    auto run=r.requested_run(root);auto metadata=r.metadata(root,n,m);
    for(const auto& [path,meaning]:std::initializer_list<std::pair<const char*,const char*>>{{"states","T+1 universal state sets"},{"external","absent external input"},{"observations","empty observation list"},{"temporal",version_one?"reserved omitted temporal relation":"omission means no temporal relation"},{"run","historical_reachability_vs_joint_trajectory intent"},{"id","empty display label"},{"metadata","empty display metadata"}})
        r.defaults.push_back({child("",path),meaning,root.contains(path)});
    Problem p{{metadata.id},std::make_shared<const SystemModel>(std::move(model)),std::move(times),KnownInitial{initial},ContinuousDomain{std::move(controls)},
        std::move(states),std::move(temporal),{},InformationPattern::nominal_open_loop,std::move(objective)};
    auto resolution=problem::resolve(p,{problem::UncertaintyStructure::stage_product_uncoupled,options.objective_policy,{}});
    if(const auto* d=std::get_if<Diagnostic>(&resolution)) {
        // Shape/finite checks above retain their exact authored pointers. These
        // remaining canonical checks concern Q or caller-supplied load policy.
        const auto path=d->field=="objective.psd" || d->field=="objective.symmetry"?"/objective/Q":"";
        if(d->code==DiagnosticCode::unsupported)
            throw UnsupportedInput{d->field,path,d->explanation,"supported canonical data and publication policy",*d};
        throw InputFailure{InputCategory::field,path,d->explanation,"valid canonical data",{},*d};
    }
    auto resolved=canonical<problem::ResolvedProblem>(std::move(resolution),"");
    auto source=canonical<problem::ResolvedContent>(problem::snapshot_content(bytes),"");
    poll(options);
    return Access::scenario({std::move(resolved),std::move(run),std::move(r.defaults),std::move(metadata),
        {std::move(source),location,schema,version_one?"csl.scenario-defaults/1":"csl.scenario-defaults/2",options.objective_policy}});
}
}
LoadResult load_bytes(std::span<const std::byte> bytes,const LoadOptions& options,const std::filesystem::path& location) {
    try {
        auto root=parse(bytes,options);
        if(root.is_object() && root.contains("schema_version")) {
            if(root.contains("schema")) fail("/schema","conflicting formats","one scenario format",InputCategory::schema);
            if(!root["schema_version"].is_number_unsigned() || root["schema_version"]!=1 || !root.contains("id") || root["id"]!="B04-historical")
                throw UnsupportedInput{"archival schema","/schema_version","unrecognized archival format","B04-historical schema_version 1"};
            const auto& executable=member(root,"executable","");
            if(!executable.is_boolean() || executable.get<bool>()) fail("/executable",executable.dump(),"false for historical intake");
            HistoricalRecord record{"B04-historical",string(member(root,"restoration_status",""),"/restoration_status"),string(member(root,"execution_gate",""),"/execution_gate"),{}};
            if(record.restoration_status!="incomplete_and_inconsistent") fail("/restoration_status",record.restoration_status,"incomplete_and_inconsistent");
            if(record.execution_gate.empty()) fail("/execution_gate","empty","nonempty execution prohibition");
            const auto& unresolved=member(root,"unresolved","");
            if(!unresolved.is_array() || unresolved.empty()) fail("/unresolved","empty or non-array","nonempty array of unresolved input descriptions");
            record.unresolved.reserve(unresolved.size());
            for(std::size_t i=0;i<unresolved.size();++i) record.unresolved.push_back(string(unresolved[i],child("/unresolved",std::to_string(i))));
            auto source=canonical<problem::ResolvedContent>(problem::snapshot_content(bytes),"");poll(options);
            return Access::historical({std::move(record),{std::move(source),location,"B04-historical/1","none",options.objective_policy}});
        }
        return translate(root,bytes,options,location);
    }
    catch(const InputFailure& f) {return f;}
    catch(const UnsupportedInput& f) {return f;}
    catch(const OperationStopped& s) {return s;}
}
} // namespace detail
LoadResult load_scenario(std::span<const std::byte> bytes,const LoadOptions& options) {return detail::load_bytes(bytes,options,{});}
} // namespace csl::input
