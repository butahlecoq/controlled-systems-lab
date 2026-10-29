import importlib.util
from pathlib import Path
from fractions import Fraction as F


SCRIPT = Path(__file__).parents[2] / "benchmarks/reporting/mpc08_explicit/explicit_nonunique_double_integrator.py"
SPEC = importlib.util.spec_from_file_location("mpc08_nonunique_reference", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_exact_nonunique_family_and_minimum_norm_selector_are_distinct():
    assert MODULE.optimal_u0_interval(F(0)) == (F(-1), F(1))
    assert MODULE.optimal_u0_interval(F(2)) == (F(-1), F(-1))
    assert MODULE.optimal_u0_interval(F(-2)) == (F(1), F(1))
    assert MODULE.selector(F(0)) == (F(0), F(0))
    assert MODULE.selector(F(2)) == (F(-1), F(-1))


def test_reference_covers_declared_initial_grid_and_replays_optimal_histories():
    states, histories = MODULE.verify()

    assert len(states) == 15
    assert len(histories) == 45
    assert sum(F(row["first_action_set_width_exact"]) > 0 for row in states) == 9
    assert all(row["terminal_v_exact"] == "0" for row in histories)
    assert all(F(row["u0_exact"]) >= -1 and F(row["u0_exact"]) <= 1 for row in histories)
    assert all(F(row["u1_exact"]) >= -1 and F(row["u1_exact"]) <= 1 for row in histories)


def test_figure_labels_selector_as_fill_color_and_shows_full_optimal_fiber():
    figure = MODULE.svg()

    assert "fill color encodes selector" in figure
    assert "u₀+u₁=0" in figure
    assert "full optimal control fiber" in figure.lower()
    assert "tie-broken selector" not in figure
