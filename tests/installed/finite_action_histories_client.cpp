#include <csl/synthesis/finite_action_histories.hpp>

#include <iostream>
#include <variant>

int main() {
    const csl::FiniteDomain actions{1,{{0.0},{0.0}}};
    auto prepared=csl::synthesis::FiniteActionHistoryCursor::prepare(actions,2);
    if(!std::holds_alternative<csl::synthesis::FiniteActionHistoryCursor>(prepared))return 1;
    auto cursor=std::get<csl::synthesis::FiniteActionHistoryCursor>(std::move(prepared));
    const auto first=cursor.take_prefix(2);
    const auto second=cursor.take_prefix(2);
    if(first.histories.size()!=2 || first.complete || second.histories.size()!=2 || !second.complete)return 2;
    if(first.histories[0].catalogue_indices!=std::vector<std::size_t>{0,0} ||
       first.histories[1].catalogue_indices!=std::vector<std::size_t>{0,1} ||
       second.histories[0].catalogue_indices!=std::vector<std::size_t>{1,0} ||
       second.histories[1].catalogue_indices!=std::vector<std::size_t>{1,1})return 3;
    std::cout<<"Installed finite action history cursor passed\n";
}
