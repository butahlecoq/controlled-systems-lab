#include "scenario_json.hpp"
#include <algorithm>
#include <cmath>
#include <limits>
#include <set>

namespace csl::input::detail {
void poll(const LoadOptions& o) {
    if(o.cancellation.stop_requested()) throw OperationStopped{StopReason::cancelled,"scenario input cancelled"};
}
[[noreturn]] void fail(std::string path,std::string observed,std::string expected,InputCategory category) {
    throw InputFailure{category,std::move(path),std::move(observed),std::move(expected)};
}
std::string child(std::string_view parent,std::string_view key) {
    std::string result(parent);result+='/';
    for(char c:key) {if(c=='~') result+="~0";else if(c=='/') result+="~1";else result+=c;}
    return result;
}
void validate_options(const LoadOptions& o) {
    const LoadLimits maximum;
    const auto& l=o.limits;
    const auto limits={std::pair{l.input_bytes,maximum.input_bytes},{l.depth,maximum.depth},{l.nodes,maximum.nodes},
        {l.string_bytes,maximum.string_bytes},{l.description_bytes,maximum.description_bytes},
        {l.matrix_coefficients,maximum.matrix_coefficients},{l.dimension,maximum.dimension},
        {l.horizon,maximum.horizon},{l.expanded_scalars,maximum.expanded_scalars},{l.identity_bytes,maximum.identity_bytes}};
    for(auto [value,cap]:limits) if(value>cap) fail("","increased admission limit","limits no larger than v1 defaults",InputCategory::limit);
}
const Json& member(const Json& v,std::string_view key,std::string_view path) {
    if(!v.is_object()) fail(std::string(path),v.type_name(),"object");
    auto it=v.find(std::string(key));if(it==v.end()) fail(child(path,key),"missing","required member");
    return *it;
}
void object(const Json& v,const std::string& path,std::initializer_list<std::string_view> allowed) {
    if(!v.is_object()) fail(path,v.type_name(),"object");
    for(auto it=v.begin();it!=v.end();++it)
        if(std::find(allowed.begin(),allowed.end(),it.key())==allowed.end()) fail(child(path,it.key()),"unknown member","a documented member");
}
std::string string(const Json& v,const std::string& path) {
    if(!v.is_string()) fail(path,v.type_name(),"string");
    return v.get<std::string>();
}
std::size_t count(const Json& v,const std::string& path) {
    if(!v.is_number_unsigned()) fail(path,v.type_name(),"unsigned integer JSON token");
    const auto n=v.get<std::uint64_t>();
    if(n>std::numeric_limits<std::size_t>::max()) fail(path,"integer exceeds size_t","representable unsigned integer");
    return static_cast<std::size_t>(n);
}
double number(const Json& v,const std::string& path) {
    if(!v.is_number()) fail(path,v.type_name(),"finite binary64 number");
    constexpr std::uint64_t exact=UINT64_C(9007199254740992);
    if(v.is_number_unsigned() && v.get<std::uint64_t>()>exact) fail(path,"integer outside exact binary64 range","integer magnitude at most 2^53");
    if(v.is_number_integer() && !v.is_number_unsigned()) {
        auto n=v.get<std::int64_t>();
        if(n>static_cast<std::int64_t>(exact) || n< -static_cast<std::int64_t>(exact)) fail(path,"integer outside exact binary64 range","integer magnitude at most 2^53");
    }
    const double n=v.get<double>();if(!std::isfinite(n)) fail(path,"nonfinite","finite binary64 number");
    return n;
}
namespace {
class Builder final : public nlohmann::json_sax<Json> {
    struct Frame { Json value; std::string path,key; std::set<std::string> keys; };
    const LoadOptions& options_;
    std::vector<Frame> stack_;
    std::size_t nodes_{};
    std::string path() const {
        if(stack_.empty()) return {};
        const auto& f=stack_.back();return child(f.path,f.value.is_array()?std::to_string(f.value.size()):f.key);
    }
    void node() {
        poll(options_);if(nodes_==options_.limits.nodes) fail(path(),"node quota exceeded","bounded JSON node count",InputCategory::limit);++nodes_;
    }
    void append(Json v) {
        if(stack_.empty()) root=std::move(v);
        else if(stack_.back().value.is_array()) stack_.back().value.push_back(std::move(v));
        else stack_.back().value.emplace(stack_.back().key,std::move(v));
    }
    bool scalar(Json v) {node();append(std::move(v));return true;}
    bool start(bool array) {
        node();if(stack_.size()>=options_.limits.depth) fail(path(),"depth quota exceeded","bounded JSON depth",InputCategory::limit);
        auto p=path();stack_.push_back({array?Json::array():Json::object(),std::move(p),{}, {}});return true;
    }
    bool end() {auto v=std::move(stack_.back().value);stack_.pop_back();append(std::move(v));return true;}
public:
    Json root;
    explicit Builder(const LoadOptions& o):options_(o) {}
    bool null() override {return scalar(nullptr);}
    bool boolean(bool v) override {return scalar(v);}
    bool number_integer(number_integer_t v) override {return scalar(v);}
    bool number_unsigned(number_unsigned_t v) override {return scalar(v);}
    bool number_float(number_float_t v,const string_t& token) override {
        if(token.find_first_of(".eE")==std::string::npos)
            fail(path(),"integer outside exact binary64 range","integer magnitude at most 2^53");
        const auto exponent=token.find_first_of("eE");
        const bool nonzero=std::any_of(token.begin(),exponent==std::string::npos?token.end():token.begin()+static_cast<std::ptrdiff_t>(exponent),[](char c){return c>='1' && c<='9';});
        if(v==0 && nonzero) fail(path(),"nonzero decimal underflows binary64","representable nonzero binary64 number");
        if(!std::isfinite(v)) fail(path(),"nonfinite","finite binary64 number");
        return scalar(v);
    }
    bool string(string_t& v) override {
        auto p=path();const auto cap=p=="/metadata/description"?options_.limits.description_bytes:options_.limits.string_bytes;
        if(v.size()>cap) fail(p,"decoded string quota exceeded","bounded UTF-8 string",InputCategory::limit);
        return scalar(v);
    }
    bool binary(binary_t&) override {fail(path(),"binary token","JSON text",InputCategory::syntax);}
    bool start_object(std::size_t) override {return start(false);}
    bool end_object() override {return end();}
    bool start_array(std::size_t) override {return start(true);}
    bool end_array() override {return end();}
    bool key(string_t& v) override {
        stack_.back().key=v;node();
        if(v.size()>options_.limits.string_bytes) fail(path(),"key quota exceeded","bounded UTF-8 key",InputCategory::limit);
        if(!stack_.back().keys.insert(v).second) fail(path(),"duplicate decoded key","unique object member",InputCategory::syntax);
        return true;
    }
    bool parse_error(std::size_t position,const std::string&,const nlohmann::detail::exception& e) override {
        const std::string message=e.what();
        const auto category=message.find("UTF-8")!=std::string::npos || message.find("surrogate")!=std::string::npos?InputCategory::encoding:InputCategory::syntax;
        throw InputFailure{category,path(),message,"strict UTF-8 JSON",position};
    }
};
}
Json parse(std::span<const std::byte> bytes,const LoadOptions& options) {
    validate_options(options);poll(options);
    if(bytes.size()>options.limits.input_bytes) fail("","input byte quota exceeded","bounded scenario bytes",InputCategory::limit);
    if(bytes.size()>=2) {
        const auto a=std::to_integer<unsigned char>(bytes[0]),b=std::to_integer<unsigned char>(bytes[1]);
        if((a==0xef && b==0xbb) || (a==0xff && b==0xfe) || (a==0xfe && b==0xff) || a==0 || b==0)
            fail("","BOM or UTF-16/UTF-32 input","UTF-8 without BOM",InputCategory::encoding);
    }
    Builder builder(options);
    const auto* begin=bytes.empty()?"":reinterpret_cast<const char*>(bytes.data());
    // Input byte cap bounds lexer token buffering before SAX callbacks.
    if(!Json::sax_parse(begin,begin+bytes.size(),&builder,Json::input_format_t::json,true)) fail("","parse stopped","strict JSON",InputCategory::syntax);
    return std::move(builder.root);
}
} // namespace csl::input::detail
