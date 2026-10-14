"""
Tests for the evaluator itself: a grounding check is only useful if it
catches planted errors and doesn't flag a correct narrative.
"""
import re

import pytest

from evals.grounding import check
from report_agent import kpis as K
from report_agent.narrate import narrate_offline

K_AUG = K.compute(K.load_rows("data/sample_campaigns.csv"), "2026-08")
GOOD = narrate_offline(K_AUG)


def kinds(md):
    return {k for k, _ in check(md, K_AUG).issues}


def test_clean_narrative_passes():
    res = check(GOOD, K_AUG)
    assert res.passed, res.summary()
    assert res.numbers_checked > 15


def test_catches_hallucinated_number():
    spend = K_AUG["totals"]["display"]["current"]["spend"]
    assert kinds(GOOD.replace(spend, "$31,250", 1)) == {"ungrounded_number"}


def test_catches_self_computed_rounding():
    cpa = K_AUG["totals"]["display"]["current"]["cpa"]   # e.g. $53.85
    rounded = "$" + str(round(float(cpa[1:].replace(",", ""))))
    assert "ungrounded_number" in kinds(GOOD.replace(cpa, rounded, 1))


def test_catches_wrong_direction():
    ch = K_AUG["totals"]["change"]["conversions"]
    wrong = "rose" if ch < 0 else "fell"
    md = GOOD + f"\n\nTotal conversions {wrong} {K_AUG['totals']['display']['change']['conversions'].lstrip('+-')} this month."
    assert "wrong_direction" in kinds(md)


def test_catches_platform_level_wrong_direction():
    meta = next(p for p in K_AUG["by_platform"] if p["key"] == "Meta")
    wrong = "fell" if meta["change"]["cpa"] > 0 else "rose"
    md = GOOD + f"\n\nOn Meta, CPA {wrong} to {meta['display']['current']['cpa']}."
    assert "wrong_direction" in kinds(md)


def test_catches_missing_section():
    md = re.sub(r"## Recommendations.*", "", GOOD, flags=re.S)
    assert "missing_section" in kinds(md)


def test_catches_wrong_period():
    assert "wrong_period" in kinds(GOOD + "\n\nThis continues the trend from March.")


@pytest.mark.parametrize("month", ["2026-02", "2026-05", "2026-07", "2026-09"])
def test_offline_baseline_passes_every_month(month):
    k = K.compute(K.load_rows("data/sample_campaigns.csv"), month)
    res = check(narrate_offline(k), k)
    assert res.passed, res.summary()
