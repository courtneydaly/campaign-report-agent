"""
Grounding checks for a generated narrative against the KPI JSON it was given.

Checks
------
1. number_grounding   every number in the narrative matches a value in a `display`
                      field (same unit, same displayed precision). Catches
                      hallucinated or self-computed numbers.
2. direction          a sentence that names exactly one metric and one direction
                      word ("CPA rose") agrees with the sign of that metric's change,
                      for the total or for the platform named in the sentence.
3. structure          all required section headings are present.
4. period             no month other than the reporting / prior month is named.
5. trend              no streak or multi-month trend claim ("third straight month",
                      "continues to decline"). The KPI JSON covers two months, so
                      these claims can't be grounded even when no month is named.

Known limits (documented, not hidden)
-------------------------------------
* Plain integers 1-12 and years 2000-2100 are not checked (list counts, dates).
* Direction is only judged when a sentence is unambiguous; sentences naming a
  campaign, or several metrics, are skipped rather than guessed at.
"""
from __future__ import annotations

import calendar
import re
from dataclasses import dataclass, field

from report_agent.narrate import SECTIONS, month_name

NUM_RE = re.compile(r"(?P<sign>[+\-−])?(?P<cur>\$)?(?P<num>\d[\d,]*(?:\.\d+)?)(?P<unit>%|x\b)?")

METRICS = [  # order matters: longer phrases first so "conversion rate" isn't read as "conversions"
    ("cvr", r"conversion rate"),
    ("cpa", r"\bCPA\b|cost per acquisition"),
    ("cpc", r"\bCPC\b|cost per click"),
    ("ctr", r"\bCTR\b|click-through rate"),
    ("roas", r"\bROAS\b|return on ad spend"),
    ("conversions", r"\bconversions?\b"),
    ("revenue", r"\brevenue\b"),
    ("spend", r"\bspend\b"),
    ("clicks", r"\bclicks\b"),
    ("impressions", r"\bimpressions\b"),
]
_ORD = r"(?:second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|\d+(?:st|nd|rd|th))"
_CNT = r"(?:two|three|four|five|six|seven|eight|nine|ten|several|multiple|\d+)"
TREND_PATTERNS = [
    rf"\b{_ORD}\s+(?:straight|consecutive|successive)\s+(?:month|quarter)\b",
    rf"\b{_CNT}\s+(?:straight|consecutive|successive)\s+(?:months|quarters)\b",
    rf"\b{_CNT}\s+months\s+in\s+a\s+row\b",
    rf"\b(?:for|over)\s+(?:the\s+)?(?:past|last)\s+{_CNT}\s+months\b",
    rf"\bfor\s+{_CNT}\s+months\b",
    r"\bmonth\s+after\s+month\b",
    r"\banother\s+month\s+of\b",
    r"\bstreak\b",
    r"\bcontinu\w*\s+to\s+(?:decline|fall|drop|slide|slip|rise|climb|grow|increase|decrease|improve|worsen)\b",
    r"\bcontinu\w*\s+(?:its|the|a|an)\s+(?:\w+\s+){0,2}?(?:trend|decline|slide|climb|rise|growth|downturn|run)\b",
    r"\b(?:year|quarter)[- ]to[- ]date\b|\bYTD\b",
]
TREND_RE = re.compile("|".join(TREND_PATTERNS), flags=re.I)
UP = r"\b(increased|rose|grew|climbed|jumped|gained|higher|up)\b"
DOWN = r"\b(decreased|fell|declined|dropped|slipped|lower|down)\b"


@dataclass
class Result:
    issues: list[tuple[str, str]] = field(default_factory=list)
    numbers_checked: int = 0
    numbers_grounded: int = 0
    directions_checked: int = 0

    @property
    def passed(self) -> bool:
        return not self.issues

    @property
    def grounding_rate(self) -> float:
        return self.numbers_grounded / self.numbers_checked if self.numbers_checked else 1.0

    def summary(self) -> str:
        head = (f"grounding: {self.numbers_grounded}/{self.numbers_checked} numbers grounded, "
                f"{self.directions_checked} direction claims checked, "
                f"{'PASS' if self.passed else f'FAIL ({len(self.issues)} issues)'}")
        return "\n".join([head] + [f"  [{kind}] {detail}" for kind, detail in self.issues])


def _parse(m: re.Match) -> tuple[str, float, int]:
    """-> (unit, value, decimals)"""
    raw = m.group("num").replace(",", "")
    decimals = len(raw.split(".")[1]) if "." in raw else 0
    value = float(raw)
    unit = "$" if m.group("cur") else (m.group("unit") or "n")
    return unit, value, decimals


def _allowed(kpis: dict) -> set[tuple[str, float]]:
    out: set[tuple[str, float]] = set()

    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k == "display":
                    collect(v)
                else:
                    walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    def collect(o):
        if isinstance(o, dict):
            for v in o.values():
                collect(v)
        elif isinstance(o, str):
            for m in NUM_RE.finditer(o):
                unit, value, _ = _parse(m)
                out.add((unit, round(value, 4)))  # sign dropped: "fell 5.1%" is fine

    walk(kpis)
    return out


def _skippable(unit: str, value: float, decimals: int) -> bool:
    return unit == "n" and decimals == 0 and (value <= 12 or 2000 <= value <= 2100)


def _sentences(md: str) -> list[str]:
    text = re.sub(r"^#+ .*$", "", md, flags=re.M)
    text = re.sub(r"\*\*", "", text)
    # split on sentence ends, but not on decimal points
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+(?=[A-Z\-*])|\n+", text) if s.strip()]


def check(md: str, kpis: dict) -> Result:
    r = Result()

    # 1. numbers
    allowed = _allowed(kpis)
    body = re.sub(r"^#+ .*$", "", md, flags=re.M)
    for m in NUM_RE.finditer(body):
        unit, value, decimals = _parse(m)
        if _skippable(unit, value, decimals):
            continue
        r.numbers_checked += 1
        if (unit, round(value, 4)) in allowed:
            r.numbers_grounded += 1
        else:
            ctx = body[max(0, m.start() - 40): m.end() + 20].replace("\n", " ")
            r.issues.append(("ungrounded_number", f"{m.group(0)!r} in '...{ctx}...'"))

    # 2. direction
    platforms = {p["key"]: p for p in kpis["by_platform"]}
    campaign_names = {c["key"].split(" | ", 1)[1] for c in kpis["by_campaign"]}
    for s in _sentences(md):
        if any(name in s for name in campaign_names):
            continue
        remaining, hits = s, []
        for key, pat in METRICS:
            if re.search(pat, remaining, flags=re.I):
                hits.append(key)
                remaining = re.sub(pat, " ", remaining, flags=re.I)
        up, down = re.search(UP, s, flags=re.I), re.search(DOWN, s, flags=re.I)
        if len(hits) != 1 or bool(up) == bool(down):
            continue
        named = [p for p in platforms if p in s]
        if len(named) > 1:
            continue
        scope = platforms[named[0]] if named else kpis["totals"]
        change = scope["change"].get(hits[0])
        if change is None or abs(change) < 0.005:
            continue
        r.directions_checked += 1
        claimed_up = bool(up)
        if claimed_up != (change > 0):
            where = named[0] if named else "total"
            r.issues.append(("wrong_direction",
                             f"{hits[0]} ({where}) changed {change:+.1%} but text says "
                             f"'{(up or down).group(0)}': {s[:120]}"))

    # 3. structure
    for sec in SECTIONS:
        if not re.search(rf"^## {re.escape(sec)}\s*$", md, flags=re.M):
            r.issues.append(("missing_section", sec))

    # 4. period
    ok_months = {month_name(kpis["month"]).split()[0], month_name(kpis["prior_month"]).split()[0]}
    for name in calendar.month_name[1:]:
        if name not in ok_months and re.search(rf"\b{name}\b", md):
            r.issues.append(("wrong_period", f"mentions {name}"))

    # 5. trend
    for m in TREND_RE.finditer(body):
        ctx = body[max(0, m.start() - 40): m.end() + 20].replace("\n", " ")
        r.issues.append(("unsupported_trend", f"{m.group(0)!r} in '...{ctx}...'"))

    return r
