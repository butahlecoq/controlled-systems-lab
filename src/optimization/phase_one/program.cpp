#include <csl/optimization/phase_one.hpp>
namespace csl::optimization::phase_one {
LPDataResult<LinearProgram> make_program(ProgramIdentity identity, const SparseMatrix& a, std::span<const double> b) {
    if(b.size()!=a.rows)
        return Diagnostics{{DiagnosticCode::invalid_input,"phase_one.rhs","RHS length differs from row count"}};
    std::vector<Interval> rows; rows.reserve(b.size());
    for(double value:b) rows.push_back({value,value});
    return make_linear_program({std::move(identity),Vector(a.cols,0),0,a,
        std::vector<Interval>(a.cols,Interval{0,{}}),std::move(rows)});
}
}
