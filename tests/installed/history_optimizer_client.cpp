#include <csl/optimization/history_optimizer.hpp>

#include <string_view>

int main() {
    return std::string_view(csl::registry::HistoryOptimizerPort::name)=="whole-history-optimizer"?0:1;
}
