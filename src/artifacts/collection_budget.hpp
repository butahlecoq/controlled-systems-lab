#pragma once
#include <csl/artifacts/run_statistics.hpp>
#include <limits>

// Private portable logical-byte accounting. This is not a wire encoder or an
// allocator-size estimate. Every retained metadata field has one explicit charge.
namespace csl::artifacts::collection_budget {
struct Counter {
    std::uint64_t bytes{};
    bool valid{true};
    void add(std::uint64_t n) noexcept {
        if(n>std::numeric_limits<std::uint64_t>::max()-bytes){valid=false;return;}
        bytes+=n;
    }
    void text(std::string_view value) noexcept {add(8);add(value.size());}
    bool fits(std::uint64_t limit) const noexcept {return valid&&bytes<=limit;}
};
inline void value(Counter& c,bool){c.add(1);}
inline void value(Counter& c,std::uint64_t){c.add(8);}
inline void value(Counter& c,std::int64_t){c.add(8);}
inline void value(Counter& c,double){c.add(8);}
inline void value(Counter& c,const std::string& s){c.text(s);}
template<class T> requires std::is_enum_v<T>
void value(Counter& c,T){c.add(1);}
inline void value(Counter& c,const ModulePin& p){value(c,p.scope);c.text(p.sha256);}
template<class T> void metric(Counter& c,const Metric<T>& m){
    c.add(1);
    if(const auto* a=std::get_if<Available<T>>(&m))value(c,a->value);
    else {const auto& u=std::get<Unavailable>(m);value(c,u.reason);c.text(u.detail);}
}
inline void module(Counter& c,const ModuleIdentity& m){c.text(m.id.value);c.text(m.version);metric(c,m.pin);}
inline void summary(Counter& c,const std::shared_ptr<const RepresentationSummary>& p){
    c.add(1);if(!p)return;
    c.text(p->representation.value);c.add(8);c.add(8);
    for(const auto& s:p->sizes){c.text(s.quantity);c.text(s.unit);metric(c,s.value);}
}
inline void geometry(Counter& c,const std::shared_ptr<const GeometryEvidence>& p){
    c.add(1);if(!p)return;
    const auto& e=*p;c.text(e.reference.identity.problem.value);c.text(e.reference.identity.request.value);c.text(e.reference.identity.ideal_output.value);
    c.add(8);for(const auto& id:e.reference.inputs)c.text(id.value);
    value(c,e.scope);c.add(1);
    std::visit([&](const auto& s){using T=std::decay_t<decltype(s)>;
        if constexpr(std::is_same_v<T,NumericalCheck>){c.add(24);c.text(s.verifier.value);}
        else if constexpr(std::is_same_v<T,SymbolicArgument>){c.text(s.reference);c.text(s.assumptions);}
        else if constexpr(std::is_same_v<T,CertificateReference>){c.text(s.artifact);c.text(s.verifier);}
        else if constexpr(std::is_same_v<T,ExactFarkasEvidence>){
            c.text(s.subject().problem.value);c.text(s.subject().program.value);
            const auto& proof=s.certificate();
            for(const auto* multipliers:{&proof.row_lower,&proof.row_upper,&proof.variable_lower,&proof.variable_upper}) {
                c.add(8);for(std::size_t i=0;i<multipliers->size();++i)c.add(sizeof(double));
            }
        }
    },e.support);
    c.add(8);for(const auto& a:e.assumptions)c.text(a);
    c.add(1);if(e.error_bound){c.text(e.error_bound->metric.value);c.add(8);c.text(e.error_bound->units);}
}
inline void descriptor(Counter& c,const SpanDescriptor& d){
    c.add(8+1);if(d.parent)c.add(8+1);
    c.add(16);c.text(d.task);c.text(d.operation);module(c,d.module);
    c.add(1);if(d.backend)module(c,*d.backend);
    c.text(d.clock.value);c.add(1);if(d.program){c.text(d.program->problem.value);c.text(d.program->program.value);}
    for(const auto* o:{&d.stage,&d.query,&d.input_size,&d.output_size}){c.add(1);if(*o)c.add(8);}
    for(const auto* p:{&d.input_representation,&d.output_representation}){c.add(1);if(*p)c.text((*p)->value);}
    value(c,d.requested_assurance);metric(c,d.applied_assurance);
    c.add(1);if(d.relation)value(c,*d.relation);
    c.add(1);if(d.applied_relation)value(c,*d.applied_relation);
    geometry(c,d.relation_evidence);summary(c,d.input_summary);summary(c,d.output_summary);c.text(d.observation_source);
}
inline void clock(Counter& c,const ClockDomain& d){
    c.text(d.id.value);value(c,d.metric);c.text(d.scope);c.add(16);metric(c,d.resolution_ticks);c.text(d.origin_label);metric(c,d.calibration);
}
inline void status(Counter& c,const SpanStatus& s){
    c.add(1);
    std::visit([&](const auto& x){using T=std::decay_t<decltype(x)>;
        if constexpr(std::is_same_v<T,ReturnedSpan>){value(c,x.termination);metric(c,x.outcome);}
        else if constexpr(std::is_same_v<T,RejectedSpan>||std::is_same_v<T,SkippedSpan>)c.text(x.reason);
        else if constexpr(std::is_same_v<T,FailedSpan>){c.text(x.phase);c.text(x.reason);}
    },s);
}
inline void span(Counter& c,const SpanRecord& s){
    descriptor(c,s.descriptor);c.add(1);
    if(const auto* t=std::get_if<TickInterval>(&s.interval)){metric(c,t->start);metric(c,t->end);}else c.add(16);
    c.add(1);if(const auto* n=std::get_if<NotCalledObservation>(&s.execution)){value(c,n->reason);c.text(n->source_location);c.text(n->source_version);}
    metric(c,s.termination);metric(c,s.iterations);
    // Available detail payload alone is governed by detail_bytes. Its variant
    // and length framing still belong to metadata; unavailable prose does too.
    if(std::holds_alternative<Available<std::string>>(s.detail))c.add(9);else metric(c,s.detail);
    status(c,s.status);c.add(2);
}
inline void bucket(Counter& c,const BucketSummary& b){c.add(8);c.text(b.clock.value);c.add(10*9);metric(c,b.inclusive_ticks);}
inline Counter root(const ProblemId& p,const ConfigId& config,const RunId& run){
    Counter c;c.text(p.value);c.text(config.value);c.text(run.value);
    c.add(34); // enabled, mode, four unsigned64 caps
    c.add(40); // clocks, spans, buckets, task dictionary, operation dictionary
    return c;
}
inline Counter retained(const CollectionRecord& r){
    auto c=root(r.problem,r.configuration,r.run);metric(c,r.complete);
    for(const auto& x:r.clocks)clock(c,x);
    for(const auto& x:r.spans)span(c,x);
    for(const auto& x:r.buckets)bucket(c,x);
    for(const auto& x:r.tasks)c.text(x);
    for(const auto& x:r.operations)c.text(x);
    return c;
}
// Reserve every scalar completion alternative the producer can emit and one
// bucket per span plus the unclassified bucket. Repeated buckets overreserve;
// admission does not need an allocation or a deduplication map.
inline Counter planned(const ProblemId& p,const ConfigId& config,const RunId& run,
                       const std::vector<ClockDomain>& clocks,const std::vector<SpanDescriptor>& spans,
                       const std::vector<std::string>& tasks,const std::vector<std::string>& operations){
    auto c=root(p,config,run);c.add(10); // unavailable completeness, empty prose
    for(const auto& x:clocks)clock(c,x);
    for(const auto& d:spans){
        descriptor(c,d);
        // Interval21, call18+source/version bytes, termination10, iterations10,
        // detail10, failed status45, completion/disposition2 =116.
        c.add(116);c.add(d.observation_source.size());c.add(d.module.version.size());
        // Bucket: id8, clock framing8, ten ExactCount9, metric at most10.
        c.add(116);c.add(d.clock.value.size());
    }
    c.add(116); // unclassified bucket, empty clock
    for(const auto& x:tasks)c.text(x);
    for(const auto& x:operations)c.text(x);
    return c;
}
} // namespace csl::artifacts::collection_budget
