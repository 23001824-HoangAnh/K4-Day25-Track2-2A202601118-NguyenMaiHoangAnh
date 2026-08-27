"""M2 — Inference Cost Levers: $/1M-token, batch x cache x cascade (deck §7).

Run: python missions/m2_inference_levers.py
"""
from __future__ import annotations
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
from collections import defaultdict
from missions._common import load_csv, num
from finops import pricing, sustainability

# $/1M tokens (input, output) — illustrative 2026.
MODEL_PRICES = {"small": (0.20, 0.40), "large": (3.00, 15.00)}
CACHE_READ_DISCOUNT = 0.10
REASONING_CAP_TRAFFIC_PCT = 5.0


def _cache_economics(rows: list[dict]) -> dict:
    """Estimate prefix reuse by model tier and gate caching on break-even.

    The synthetic log has no prefix id, so ``team + project + route_tier`` is
    used as a transparent proxy for one reusable system/document prefix.
    """
    groups = defaultdict(list)
    for row in rows:
        if int(num(row["cached_input_tokens"])) > 0:
            key = (row["route_tier"], row["team"], row["project"] or "(untagged)")
            groups[key].append(int(num(row["cached_input_tokens"])))

    by_tier = {}
    for tier, (input_price, _) in MODEL_PRICES.items():
        tier_groups = [values for (group_tier, _, _), values in groups.items() if group_tier == tier]
        avg_reads = (
            sum(max(0, len(values) - 1) for values in tier_groups) / len(tier_groups)
            if tier_groups else 0.0
        )
        # Conservative assumption: writing 1M cache tokens costs one full-price
        # uncached input unit. Each prefix is written once per day.
        write_cost_per_m = input_price
        break_even = pricing.cache_break_even_reads(
            write_cost_per_m,
            read_discount=CACHE_READ_DISCOUNT,
            uncached_read_cost_per_m=input_price,
        )
        write_cost_daily = sum(
            ((sum(values) / len(values)) / 1e6) * write_cost_per_m
            for values in tier_groups
        )
        by_tier[tier] = {
            "avg_cache_reads": round(avg_reads, 1),
            "break_even_reads": round(break_even, 2),
            "cache_enabled": pricing.cache_is_worth_it(
                avg_reads,
                write_cost_per_m,
                read_discount=CACHE_READ_DISCOUNT,
                uncached_read_cost_per_m=input_price,
            ),
            "write_cost_daily": round(write_cost_daily, 4),
        }
    return by_tier


def run(verbose: bool = True) -> dict:
    rows = load_csv("token_usage.csv")
    cache_economics = _cache_economics(rows)
    base_cost = opt_cost = 0.0
    total_tokens = 0
    reasoning_requests = 0
    reasoning_cost = reasoning_replacement_cost = 0.0
    reasoning_wh = reasoning_replacement_wh = 0.0
    total_wh = 0.0
    for r in rows:
        inp, out = int(num(r["input_tokens"])), int(num(r["output_tokens"]))
        tier = r["route_tier"]
        cached = int(num(r["cached_input_tokens"])) if cache_economics[tier]["cache_enabled"] else 0
        is_batch = bool(int(num(r["is_batch"])))
        is_reasoning = bool(int(num(r["is_reasoning"])))
        total_tokens += inp + out
        # BASELINE: naive deployment — everything on the large model, no cache, no batch
        lin, lout = MODEL_PRICES["large"]
        base_cost += pricing.request_cost(inp, out, lin, lout)
        # OPTIMIZED: cascade (route_tier), prompt caching, batch API
        pin, pout = MODEL_PRICES[tier]
        row_cost = pricing.request_cost(inp, out, pin, pout, cached_in=cached, batch=is_batch)
        opt_cost += row_cost

        row_wh = sustainability.wh_per_query(inp + out, is_reasoning=is_reasoning)
        total_wh += row_wh
        if is_reasoning:
            reasoning_requests += 1
            reasoning_cost += row_cost
            reasoning_wh += row_wh
            # The generator models reasoning output as a 6x expansion. The cap
            # routes excess requests to the normal path rather than dropping them.
            normal_out = max(1, round(out / 6))
            reasoning_replacement_cost += pricing.request_cost(
                inp, normal_out, pin, pout, cached_in=cached, batch=is_batch
            )
            reasoning_replacement_wh += sustainability.wh_per_query(inp + normal_out)

    cache_write_cost = sum(v["write_cost_daily"] for v in cache_economics.values() if v["cache_enabled"])
    opt_cost += cache_write_cost

    base_pm = pricing.dollars_per_million(base_cost, total_tokens)
    opt_pm = pricing.dollars_per_million(opt_cost, total_tokens)
    savings_pct = (1 - opt_cost / base_cost) * 100 if base_cost else 0.0

    traffic_pct = reasoning_requests / len(rows) * 100 if rows else 0.0
    cap_fraction = (
        max(0.0, reasoning_requests - len(rows) * REASONING_CAP_TRAFFIC_PCT / 100.0)
        / reasoning_requests
        if reasoning_requests else 0.0
    )
    reasoning_budget = {
        "requests": reasoning_requests,
        "traffic_pct": round(traffic_pct, 1),
        "cost_daily": round(reasoning_cost, 2),
        "cost_share_pct": round(reasoning_cost / opt_cost * 100, 1) if opt_cost else 0.0,
        "energy_wh_daily": round(reasoning_wh, 1),
        "energy_share_pct": round(reasoning_wh / total_wh * 100, 1) if total_wh else 0.0,
        "cap_traffic_pct": REASONING_CAP_TRAFFIC_PCT,
        "cap_savings_daily": round(max(0.0, reasoning_cost - reasoning_replacement_cost) * cap_fraction, 2),
        "cap_energy_savings_wh_daily": round(
            max(0.0, reasoning_wh - reasoning_replacement_wh) * cap_fraction, 1
        ),
    }

    if verbose:
        print("== M2 Inference Cost Levers ==")
        print(f"requests={len(rows)}  tokens={total_tokens:,}")
        print(f"baseline  : ${base_cost:,.2f}/day   ${base_pm:.3f}/1M-token")
        print(f"optimized : ${opt_cost:,.2f}/day   ${opt_pm:.3f}/1M-token")
        print(f"savings   : {savings_pct:.1f}%  (cascade + caching + batch)")
        print(f"discount stack (batch + 100% cache): {pricing.discount_stack(batch=True, cache_hit_frac=1.0):.3f} of naive")
        print("cache economics (observed reads vs break-even):")
        for tier, econ in cache_economics.items():
            print(
                f"  {tier:5} {econ['avg_cache_reads']:>6.1f} vs {econ['break_even_reads']:.2f}"
                f" -> enabled={econ['cache_enabled']}"
            )
        print(
            f"reasoning : {reasoning_budget['traffic_pct']:.1f}% traffic, "
            f"{reasoning_budget['cost_share_pct']:.1f}% optimized cost, "
            f"{reasoning_budget['energy_share_pct']:.1f}% energy"
        )
        print(
            f"5% cap    : save ${reasoning_budget['cap_savings_daily']:.2f}/day + "
            f"{reasoning_budget['cap_energy_savings_wh_daily']:.1f} Wh/day"
        )

    return {
        "baseline_daily": round(base_cost, 2), "optimized_daily": round(opt_cost, 2),
        "baseline_per_m": round(base_pm, 3), "optimized_per_m": round(opt_pm, 3),
        "savings_pct": round(savings_pct, 1), "total_tokens": total_tokens,
        "cache_economics": cache_economics, "reasoning_budget": reasoning_budget,
    }


if __name__ == "__main__":
    run()
