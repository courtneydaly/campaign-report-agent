"""
Turn the KPI JSON into a client-facing narrative.

Two modes:
  * llm      -> Claude writes the narrative from the KPI JSON (needs ANTHROPIC_API_KEY)
  * offline  -> deterministic template; used in CI and as the eval baseline

Either way the output is Markdown with fixed section headings so the renderer
and the evals know where everything is.
"""
from __future__ import annotations

import json
import os
from datetime import date

SECTIONS = ["Summary", "Platform Performance", "Campaign Highlights", "Recommendations"]

SYSTEM_PROMPT = """You write the monthly paid media performance narrative for a client.

You will receive a JSON object of pre-computed KPIs. Rules:
1. Cite ONLY numbers that appear in a `display` field of the JSON, copied exactly as written.
   Never compute, round, re-derive, or estimate a number yourself. If a number you want isn't
   there, describe the direction in words instead.
2. Month-over-month changes come from `display.change`. A change for CPA or CPC that is negative
   is an improvement; say so explicitly.
3. Use the section headings exactly: ## Summary, ## Platform Performance, ## Campaign Highlights,
   ## Recommendations. 2-4 short paragraphs or bullets per section. No other headings.
4. Plain, confident, client-ready language. No hedging filler, no exclamation points.
5. Recommendations must follow from the data shown; tie each one to a specific platform or campaign.
"""


def month_name(m: str) -> str:
    y, mo = map(int, m.split("-"))
    return date(y, mo, 1).strftime("%B %Y")


def build_user_prompt(kpis: dict) -> str:
    return (
        f"Client: {kpis['client']}\nReporting month: {month_name(kpis['month'])} "
        f"(compared with {month_name(kpis['prior_month'])})\n\nKPI JSON:\n"
        + json.dumps(kpis, indent=1, default=str)
    )


def narrate_llm(kpis: dict, model: str | None = None, temperature: float = 0.3) -> str:
    import anthropic

    client = anthropic.Anthropic()
    resp = client.messages.create(
        model=model or os.environ.get("REPORT_MODEL", "claude-sonnet-5-5"),
        max_tokens=2000,
        temperature=temperature,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": build_user_prompt(kpis)}],
    )
    return "".join(b.text for b in resp.content if b.type == "text").strip()


def _direction(change: float | None, lower_is_better: bool = False) -> str:
    if change is None or abs(change) < 0.0005:
        return "held flat at"
    up = change > 0
    if lower_is_better:
        return "improved" if not up else "worsened"
    return "increased" if up else "decreased"


def _abs(display_change: str | None) -> str:
    return (display_change or "n/a").lstrip("+-")


def narrate_offline(kpis: dict) -> str:
    t = kpis["totals"]
    d, ch = t["display"], t["change"]
    m, pm = month_name(kpis["month"]), month_name(kpis["prior_month"])
    summary = [
        f"In {m}, paid media drove {d['current']['conversions']} conversions on {d['current']['spend']} "
        f"in spend, for a cost per acquisition of {d['current']['cpa']}.",
        f"Conversions {_direction(ch['conversions'])} {_abs(d['change']['conversions'])} versus {pm}.",
        f"CPA {_direction(ch['cpa'])} {_abs(d['change']['cpa'])} "
        f"({'a cost improvement' if (ch['cpa'] or 0) < 0 else 'higher cost per result'}).",
    ]
    if t["current"]["roas"] is not None:
        summary.append(
            f"Ecommerce revenue was {d['current']['revenue']}, a return on ad spend of {d['current']['roas']}."
        )
    lines = ["## Summary", " ".join(summary), "", "## Platform Performance"]
    for p in kpis["by_platform"]:
        pd = p["display"]
        lines.append(
            f"- **{p['key']}:** {pd['current']['spend']} spend, {pd['current']['conversions']} conversions "
            f"({pd['change']['conversions']} MoM), CPA {pd['current']['cpa']} ({pd['change']['cpa']} MoM)."
        )
    lines += ["", "## Campaign Highlights"]
    by_key = {c["key"]: c for c in kpis["by_campaign"]}
    for k in kpis["top_conversion_movers"]:
        c = by_key[k]
        lines.append(
            f"- **{k}:** conversions {_direction(c['change']['conversions'])} "
            f"{_abs(c['display']['change']['conversions'])} to {c['display']['current']['conversions']}."
        )
    worst = max(kpis["by_platform"], key=lambda p: p["change"]["cpa"] or 0)
    lines += [
        "",
        "## Recommendations",
        f"- Review {worst['key']} first: its CPA moved {worst['display']['change']['cpa']} month over month.",
        "- Shift incremental budget toward the campaigns with the lowest current CPA.",
    ]
    return "\n".join(lines)


def narrate(kpis: dict, mode: str = "offline", **kw) -> str:
    return narrate_llm(kpis, **kw) if mode == "llm" else narrate_offline(kpis)
