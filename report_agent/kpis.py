"""
Deterministic KPI layer. The LLM never does arithmetic: every number it may
cite is computed here and handed over pre-formatted in `display` fields.
"""
from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

ADDITIVE = ("spend", "impressions", "clicks", "conversions", "revenue")


def load_rows(path: str | Path) -> list[dict]:
    rows = []
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            rows.append({
                "month": r["month"], "platform": r["platform"], "campaign": r["campaign"],
                "impressions": int(r["impressions"]), "clicks": int(r["clicks"]),
                "spend": float(r["spend"]), "conversions": int(r["conversions"]),
                "revenue": float(r["revenue"]),
                "goal": r.get("goal", "ecommerce"),
            })
    return rows


def prior_month(month: str) -> str:
    y, m = map(int, month.split("-"))
    y, m = (y - 1, 12) if m == 1 else (y, m - 1)
    return f"{y}-{m:02d}"


def _div(a: float, b: float) -> float | None:
    return a / b if b else None


def derive(t: dict) -> dict:
    """Ratios are always ratios of sums."""
    return {
        **{k: round(t[k], 2) if isinstance(t[k], float) else t[k] for k in ADDITIVE},
        "ctr": _div(t["clicks"], t["impressions"]),
        "cpc": _div(t["spend"], t["clicks"]),
        "cvr": _div(t["conversions"], t["clicks"]),
        "cpa": _div(t["spend"], t["conversions"]),
        # ROAS only over ecommerce spend: lead-gen spend has no revenue and would drag it down.
        "roas": _div(t["revenue"], t["ecommerce_spend"]) if t["ecommerce_spend"] else None,
    }


def pct_change(cur: float | None, prev: float | None) -> float | None:
    if cur is None or prev in (None, 0):
        return None
    return (cur - prev) / prev


# --- display formatting: the only strings the narrative may use ------------

def fmt_money(v: float | None) -> str | None:
    return None if v is None else f"${v:,.2f}" if v < 100 else f"${v:,.0f}"


def fmt_int(v: float | None) -> str | None:
    return None if v is None else f"{v:,.0f}"


def fmt_rate(v: float | None) -> str | None:
    return None if v is None else f"{v * 100:.2f}%"


def fmt_roas(v: float | None) -> str | None:
    return None if v is None else f"{v:.2f}x"


def fmt_change(v: float | None) -> str | None:
    if v is None:
        return None
    return "0.0%" if abs(v) < 0.0005 else f"{v * 100:+.1f}%"


FORMATTERS = {
    "spend": fmt_money, "revenue": fmt_money, "cpc": fmt_money, "cpa": fmt_money,
    "impressions": fmt_int, "clicks": fmt_int, "conversions": fmt_int,
    "ctr": fmt_rate, "cvr": fmt_rate, "roas": fmt_roas,
}


def block(cur: dict, prev: dict) -> dict:
    c, p = derive(cur), derive(prev)
    change = {k: pct_change(c[k], p[k]) for k in c}
    return {
        "current": c,
        "prior": p,
        "change": change,
        "display": {
            "current": {k: FORMATTERS[k](v) for k, v in c.items()},
            "prior": {k: FORMATTERS[k](v) for k, v in p.items()},
            "change": {k: fmt_change(v) for k, v in change.items()},
        },
    }


def _sum(rows: list[dict]) -> dict:
    t = {k: 0 for k in ADDITIVE}
    t["ecommerce_spend"] = 0.0
    for r in rows:
        for k in ADDITIVE:
            t[k] += r[k]
        if r["goal"] == "ecommerce":
            t["ecommerce_spend"] += r["spend"]
    t["spend"] = float(t["spend"])
    t["revenue"] = float(t["revenue"])
    return t


def compute(rows: list[dict], month: str, client: str = "Aldercrest Home") -> dict:
    prev = prior_month(month)
    months = {r["month"] for r in rows}
    if month not in months or prev not in months:
        raise ValueError(f"need both {month} and {prev} in the data; found {sorted(months)}")

    cur_rows = [r for r in rows if r["month"] == month]
    prev_rows = [r for r in rows if r["month"] == prev]

    def grouped(key):
        out = []
        cur_g, prev_g = defaultdict(list), defaultdict(list)
        for r in cur_rows:
            cur_g[key(r)].append(r)
        for r in prev_rows:
            prev_g[key(r)].append(r)
        for k in sorted(set(cur_g) | set(prev_g)):
            out.append({"key": k, **block(_sum(cur_g[k]), _sum(prev_g[k]))})
        return out

    by_campaign = grouped(lambda r: f"{r['platform']} | {r['campaign']}")
    movers = sorted(
        (c for c in by_campaign if c["current"]["conversions"] and c["prior"]["conversions"]),
        key=lambda c: abs(c["current"]["conversions"] - c["prior"]["conversions"]),
        reverse=True,
    )[:3]

    return {
        "client": client,
        "month": month,
        "prior_month": prev,
        "totals": block(_sum(cur_rows), _sum(prev_rows)),
        "by_platform": grouped(lambda r: r["platform"]),
        "by_campaign": by_campaign,
        "top_conversion_movers": [m["key"] for m in movers],
    }
