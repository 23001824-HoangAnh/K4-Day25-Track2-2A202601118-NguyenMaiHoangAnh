"""M5 — Optimization Report: combine M1-M4 into baseline-vs-optimized (deck §1/§11).

Run: python missions/m5_report.py   ->  outputs/report.md + outputs/savings.png
"""
from __future__ import annotations
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import os
from missions._common import num, catalog_by_type, ROOT
from finops import report, sustainability
from missions import m1_efficiency_audit, m2_inference_levers, m3_purchasing

DAYS = 30
# one tier down for over-provisioned ("util-lie") GPUs
RIGHTSIZE_MAP = {"H100": "A100", "H200": "H100", "A100": "A10G", "A10G": "L4", "L4": "L4"}


def _analysis_sections(r1: dict, r2: dict, levers: dict) -> dict[str, list[str]]:
    lies = r1["lies"]
    headline = next((item for item in lies if item["gpu_id"] == "gpu-h100-4"), lies[0])
    cache_lines = [
        "Caching is enabled only when observed prefix reuse exceeds its write-cost break-even.",
        "",
        "| Tier | Observed reads/prefix | Break-even reads | Cache decision | Write cost/day |",
        "|---|---:|---:|---|---:|",
    ]
    for tier, econ in r2["cache_economics"].items():
        decision = "enable" if econ["cache_enabled"] else "disable"
        cache_lines.append(
            f"| {tier} | {econ['avg_cache_reads']:.1f} | {econ['break_even_reads']:.2f} | "
            f"{decision} | ${econ['write_cost_daily']:.4f} |"
        )
    cache_lines += [
        "",
        "Both tiers clear break-even by a wide margin. Choosing solely from the 90% read "
        "discount would miss the one-time write charge; the gate makes that assumption explicit.",
    ]

    budget = r2["reasoning_budget"]
    reasoning_lines = [
        f"- Reasoning is **{budget['traffic_pct']:.1f}% of requests** but "
        f"**{budget['cost_share_pct']:.1f}% of optimized inference cost** and "
        f"**{budget['energy_share_pct']:.1f}% of serving energy**.",
        f"- Route reasoning only when task complexity/confidence requires it and cap it at "
        f"**{budget['cap_traffic_pct']:.0f}% of traffic**.",
        f"- Estimated cap impact: **${budget['cap_savings_daily']:.2f}/day** "
        f"(${budget['cap_savings_daily'] * DAYS:,.2f}/month) and "
        f"**{budget['cap_energy_savings_wh_daily'] / 1000:.2f} kWh/day** saved.",
    ]

    largest_lever = max(levers, key=levers.get)
    findings = [
        f"- `{headline['gpu_id']}` reports {headline['gpu_util_pct']:.1f}% GPU-Util but only "
        f"{headline['mfu']:.1%} MFU. GPU-Util records active-clock time, so memory stalls, "
        "I/O waits, small kernels, or launch overhead can keep the clock busy without useful FLOPs.",
        f"- Paying the full GPU-hour for this behavior hides over-provisioning; right-sizing all "
        f"detected util-lies is worth **${levers['Right-size util-lies']:,.0f}/month**.",
        f"- Start with **{largest_lever}** (${levers[largest_lever]:,.0f}/month), then inference "
        f"optimization (${levers['Inference (cascade/cache/batch)']:,.0f}/month), and finally "
        "enforce idle shutdown plus MFU/MBU alerts. This order follows measured monthly ROI.",
        "- Keep chargeback behind the tag-coverage gate; showback remains safer when allocation "
        "data is incomplete.",
    ]
    return {
        "Findings and prioritized actions": findings,
        "Extension 3 — Cache economics": cache_lines,
        "Extension 4 — Reasoning budget": reasoning_lines,
    }


def _build_writeup(
    r1: dict,
    r2: dict,
    baseline: float,
    optimized: float,
    levers: dict,
    sustainability_snapshot: dict,
) -> str:
    total_savings = baseline - optimized
    total_pct = total_savings / baseline * 100 if baseline else 0.0
    headline = next(item for item in r1["lies"] if item["gpu_id"] == "gpu-h100-4")
    budget = r2["reasoning_budget"]
    cache = r2["cache_economics"]
    lever_rows = "\n".join(f"| {name} | ${value:,.0f} |" for name, value in levers.items())
    return f"""# Bài viết ngắn — Lab 25 GPU FinOps

## 1. Baseline và optimized

NimbusAI có baseline **${baseline:,.0f}/tháng** và mức chi sau tối ưu **${optimized:,.0f}/tháng**. Tổng tiết kiệm là **${total_savings:,.0f}/tháng ({total_pct:.1f}%)**, đạt mục tiêu 40–95%. Riêng inference giảm từ **${r2['baseline_per_m']:.3f}/1M-token** xuống **${r2['optimized_per_m']:.3f}/1M-token**, tương đương **{r2['savings_pct']:.1f}%**.

## 2. Đóng góp của từng đòn bẩy

| Đòn bẩy | Tiết kiệm/tháng |
|---|---:|
{lever_rows}

Purchasing mang lại ROI tuyệt đối lớn nhất nên cần triển khai trước. Cascade/cache/batch có tỷ lệ giảm mạnh nhất trên unit economics của inference. Tắt GPU idle và right-size nhỏ hơn về giá trị tuyệt đối nhưng là quick win ít rủi ro.

## 3. GPU-Util lie

`gpu-h100-4` có GPU-Util **{headline['gpu_util_pct']:.1f}%** nhưng MFU chỉ **{headline['mfu']:.1%}**. GPU-Util chỉ nói clock có hoạt động; memory stall, I/O wait, kernel nhỏ hoặc launch overhead vẫn làm chỉ số này cao trong khi FLOPs hữu ích thấp. Vì vậy NimbusAI đang trả trọn giờ H100 nhưng chỉ nhận khoảng một phần năm năng lực tính toán. Right-size các GPU bị phát hiện giúp tiết kiệm **${levers['Right-size util-lies']:,.0f}/tháng**; shutdown phần idle tiết kiệm thêm **${levers['Kill idle GPUs']:,.0f}/tháng**.

## 4. Hai phần mở rộng

### Cache economics

Với giả định một lần ghi cache có giá bằng một input uncached, điểm hòa vốn là **{cache['small']['break_even_reads']:.2f} lượt đọc**. Dataset đạt **{cache['small']['avg_cache_reads']:.1f} lượt** cho small tier và **{cache['large']['avg_cache_reads']:.1f} lượt** cho large tier, nên cache có lợi ở cả hai. Policy mới chỉ bật cache khi số lượt đọc quan sát được vượt điểm hòa vốn, đồng thời cộng chi phí ghi cache vào optimized cost.

### Reasoning budget

Reasoning chiếm **{budget['traffic_pct']:.1f}% traffic**, nhưng chiếm **{budget['cost_share_pct']:.1f}% optimized cost** và **{budget['energy_share_pct']:.1f}% năng lượng** vì output dài hơn và hệ số năng lượng 80×. Đề xuất chỉ route sang reasoning khi confidence thấp hoặc task complexity vượt ngưỡng, đồng thời cap ở **{budget['cap_traffic_pct']:.0f}% traffic**. Mô phỏng cho thấy cap này tiết kiệm **${budget['cap_savings_daily'] * DAYS:,.2f}/tháng** và **{budget['cap_energy_savings_wh_daily'] * DAYS / 1000:,.1f} kWh/tháng**.

## 5. Khuyến nghị ưu tiên

1. Áp dụng spot có checkpoint cho job interruptible và reserved cho inference ổn định; đây là lever lớn nhất.
2. Giữ cascade/cache/batch nhưng theo dõi `$/1M-token`; cache phải qua break-even gate và reasoning phải qua routing budget.
3. Thiết lập auto-shutdown cho idle GPU, alert theo MFU/MBU thay vì GPU-Util, và duy trì tag coverage trên 80% trước khi chargeback.

Về bền vững, một query đại diện dùng **{sustainability_snapshot['wh_per_query']:.2f} Wh**. Chuyển từ `us-east-1` sang `europe-north1` giảm khoảng **{sustainability_snapshot['carbon_reduction_pct']:.1f}% carbon** và **{sustainability_snapshot['energy_cost_reduction_pct']:.1f}% chi phí điện** theo snapshot tháng 6/2026; cần cân bằng thêm latency trước khi triển khai thực tế.
"""


def run(verbose: bool = True) -> dict:
    r1 = m1_efficiency_audit.run(verbose=False)
    r2 = m2_inference_levers.run(verbose=False)
    r3 = m3_purchasing.run(verbose=False)
    cat = catalog_by_type()

    # --- savings buckets ---
    infer_savings = (r2["baseline_daily"] - r2["optimized_daily"]) * DAYS
    purchasing_savings = r3["on_demand_monthly"] - r3["optimized_monthly"]
    idle_savings = r1["idle_waste_daily"] * DAYS
    rightsize_savings = 0.0
    for lie in r1["lies"]:
        cur = lie["gpu_type"]
        tgt = RIGHTSIZE_MAP.get(cur, cur)
        delta = num(cat[cur]["on_demand_hr"]) - num(cat[tgt]["on_demand_hr"])
        rightsize_savings += max(0.0, delta) * 24 * DAYS

    levers = {
        "Inference (cascade/cache/batch)": round(infer_savings),
        "Purchasing (spot/reserved)": round(purchasing_savings),
        "Right-size util-lies": round(rightsize_savings),
        "Kill idle GPUs": round(idle_savings),
    }
    baseline = r2["baseline_daily"] * DAYS + r3["on_demand_monthly"]
    optimized = baseline - sum(levers.values())
    total_pct = sum(levers.values()) / baseline * 100 if baseline else 0.0

    # --- sustainability snapshot ---
    median_tokens = 800
    wh = sustainability.wh_per_query(median_tokens)
    best_region = min(sustainability.REGION_CARBON, key=sustainability.REGION_CARBON.get)
    current_carbon = sustainability.carbon_g(wh, "us-east-1")
    best_carbon = sustainability.carbon_g(wh, best_region)
    current_energy_cost = sustainability.energy_cost_usd(wh, "us-east-1")
    best_energy_cost = sustainability.energy_cost_usd(wh, best_region)
    sust = {
        "wh_per_query": wh,
        "carbon_g": current_carbon,
        "energy_cost_usd": current_energy_cost,
        "best_region": best_region,
        "carbon_reduction_pct": (1 - best_carbon / current_carbon) * 100 if current_carbon else 0.0,
        "energy_cost_reduction_pct": (
            (1 - best_energy_cost / current_energy_cost) * 100 if current_energy_cost else 0.0
        ),
    }

    md = report.build_report(
        baseline,
        optimized,
        levers,
        sustainability=sust,
        unit_economics=r2,
        sections=_analysis_sections(r1, r2, levers),
    )
    out_dir = os.path.join(ROOT, "outputs")
    os.makedirs(out_dir, exist_ok=True)
    out_md = os.path.join(out_dir, "report.md")
    with open(out_md, "w", encoding="utf-8") as f:
        f.write(md)
    writeup = _build_writeup(r1, r2, baseline, optimized, levers, sust)
    with open(os.path.join(out_dir, "writeup.md"), "w", encoding="utf-8") as f:
        f.write(writeup)
    png = report.savings_waterfall(levers, os.path.join(out_dir, "savings.png"))

    if verbose:
        print("== M5 Optimization Report ==")
        print(md)
        artifacts = "outputs/report.md + outputs/writeup.md"
        print(f"\nWritten: {artifacts}" + (" + outputs/savings.png" if png else " (matplotlib absent: PNG skipped)"))

    return {
        "baseline_monthly": round(baseline),
        "optimized_monthly": round(optimized),
        "levers": levers,
        "total_savings_pct": round(total_pct, 1),
        "extensions": {
            "cache_economics": r2["cache_economics"],
            "reasoning_budget": r2["reasoning_budget"],
        },
    }


if __name__ == "__main__":
    run()
