import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from finops import pricing
from missions import m2_inference_levers


def test_cache_break_even_and_gate():
    threshold = pricing.cache_break_even_reads(
        write_cost_per_m=3.0,
        read_discount=0.10,
        uncached_read_cost_per_m=3.0,
    )
    assert abs(threshold - (1 / 0.9)) < 1e-9
    assert pricing.cache_is_worth_it(1.0, 3.0, 0.10, 3.0) is False
    assert pricing.cache_is_worth_it(2.0, 3.0, 0.10, 3.0) is True


def test_cache_without_read_discount_never_pays():
    assert pricing.cache_break_even_reads(1.0, read_discount=1.0) == float("inf")
    assert pricing.cache_is_worth_it(1_000, 1.0, read_discount=1.0) is False


def test_reasoning_budget_is_measured_and_actionable():
    result = m2_inference_levers.run(verbose=False)
    assert all(v["cache_enabled"] for v in result["cache_economics"].values())
    budget = result["reasoning_budget"]
    assert budget["traffic_pct"] > budget["cap_traffic_pct"]
    assert budget["cost_share_pct"] > budget["traffic_pct"]
    assert budget["energy_share_pct"] > 90
    assert budget["cap_savings_daily"] > 0
    assert budget["cap_energy_savings_wh_daily"] > 0
