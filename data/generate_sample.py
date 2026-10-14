"""
Generate a synthetic monthly campaign export for a fictional home-products
retailer ("Aldercrest Home"). One row per platform x campaign x month.

Invariants: clicks <= impressions, conversions <= clicks, revenue only on
ecommerce campaigns, deterministic for a seed.

  python data/generate_sample.py            # writes data/sample_campaigns.csv
"""
from __future__ import annotations

import csv
import random
from pathlib import Path

MONTHS = [f"2026-{m:02d}" for m in range(1, 10)]

# platform, campaign, monthly spend, cpc, ctr, cvr, avg order value (0 = lead gen)
CAMPAIGNS = [
    ("Google Ads", "Search - Brand", 2400, 1.40, 0.090, 0.080, 165),
    ("Google Ads", "Search - Outdoor Lighting", 5200, 2.60, 0.045, 0.028, 210),
    ("Google Ads", "Search - Water Filtration", 3900, 2.90, 0.040, 0.025, 240),
    ("Google Ads", "Shopping - All Products", 6100, 0.95, 0.011, 0.018, 185),
    ("Google Ads", "Search - Trade Program Leads", 2800, 3.80, 0.035, 0.060, 0),
    ("Microsoft Ads", "Search - Brand", 600, 1.10, 0.080, 0.075, 160),
    ("Microsoft Ads", "Search - Nonbrand", 1500, 1.90, 0.030, 0.022, 205),
    ("Meta", "Prospecting - Smart Thermostats", 3300, 1.20, 0.009, 0.010, 195),
    ("Meta", "Retargeting - Site Visitors", 1700, 0.95, 0.014, 0.030, 175),
]

# Month-level story so the narrative has something to say:
# a summer push on outdoor lighting + shopping, and a Meta cost spike in August.
MONTH_SPEND_FACTOR = {"2026-06": 1.10, "2026-07": 1.25, "2026-08": 1.15}
AUGUST_META_CPC_FACTOR = 1.35


def generate(seed: int = 11) -> list[dict]:
    rng = random.Random(seed)
    rows = []
    for month in MONTHS:
        for platform, campaign, spend, cpc, ctr, cvr, aov in CAMPAIGNS:
            f = MONTH_SPEND_FACTOR.get(month, 1.0) if ("Outdoor" in campaign or "Shopping" in campaign) else 1.0
            s = round(spend * f * rng.uniform(0.9, 1.1), 2)
            m_cpc = cpc * rng.uniform(0.92, 1.08)
            if platform == "Meta" and month == "2026-08":
                m_cpc *= AUGUST_META_CPC_FACTOR
            clicks = int(s / m_cpc)
            impressions = int(clicks / (ctr * rng.uniform(0.9, 1.1)))
            conversions = int(clicks * cvr * rng.uniform(0.85, 1.15))
            revenue = round(conversions * aov * rng.uniform(0.9, 1.1), 2) if aov else 0.0
            rows.append({
                "month": month, "platform": platform, "campaign": campaign,
                "impressions": impressions, "clicks": clicks, "spend": s,
                "conversions": conversions, "revenue": revenue,
                "goal": "ecommerce" if aov else "lead_gen",
            })
    return rows


def main() -> None:
    rows = generate()
    out = Path(__file__).with_name("sample_campaigns.csv")
    with out.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {len(rows)} rows -> {out}")


if __name__ == "__main__":
    main()
