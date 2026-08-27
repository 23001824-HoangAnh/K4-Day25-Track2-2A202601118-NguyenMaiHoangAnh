# NimbusAI — GPU Cost Optimization Report

**Period:** monthly  
**Baseline spend:** $27,133  
**Optimized spend:** $14,627  
**Projected savings:** $12,506  (**46%**)

## Inference unit economics

| Metric | Baseline | Optimized | Reduction |
|---|---:|---:|---:|
| $/1M-token | $6.488 | $1.129 | 82.6% |
| Daily inference cost | $48.87 | $8.50 | 82.6% |

## Savings by lever

| Lever | Savings (USD) |
|---|---:|
| Inference (cascade/cache/batch) | $1,211 |
| Purchasing (spot/reserved) | $10,040 |
| Right-size util-lies | $655 |
| Kill idle GPUs | $600 |

## Sustainability

- Energy per representative query: 0.24 Wh
- Carbon per query in us-east-1: 0.091 gCO2e
- Electricity per query in us-east-1: $0.000029
- Cheapest+cleanest region: europe-north1
- Moving that query to the recommended region cuts carbon by 92.1% and electricity cost by 25.0%.

## Findings and prioritized actions

- `gpu-h100-4` reports 98.2% GPU-Util but only 19.4% MFU. GPU-Util records active-clock time, so memory stalls, I/O waits, small kernels, or launch overhead can keep the clock busy without useful FLOPs.
- Paying the full GPU-hour for this behavior hides over-provisioning; right-sizing all detected util-lies is worth **$655/month**.
- Start with **Purchasing (spot/reserved)** ($10,040/month), then inference optimization ($1,211/month), and finally enforce idle shutdown plus MFU/MBU alerts. This order follows measured monthly ROI.
- Keep chargeback behind the tag-coverage gate; showback remains safer when allocation data is incomplete.

## Extension 3 — Cache economics

Caching is enabled only when observed prefix reuse exceeds its write-cost break-even.

| Tier | Observed reads/prefix | Break-even reads | Cache decision | Write cost/day |
|---|---:|---:|---|---:|
| small | 236.8 | 1.11 | enable | $0.0010 |
| large | 61.2 | 1.11 | enable | $0.0158 |

Both tiers clear break-even by a wide margin. Choosing solely from the 90% read discount would miss the one-time write charge; the gate makes that assumption explicit.

## Extension 4 — Reasoning budget

- Reasoning is **8.4% of requests** but **16.4% of optimized inference cost** and **94.0% of serving energy**.
- Route reasoning only when task complexity/confidence requires it and cap it at **5% of traffic**.
- Estimated cap impact: **$0.41/day** ($12.30/month) and **11.93 kWh/day** saved.

_Figures are June-2026 as-of snapshots; re-baseline before acting._