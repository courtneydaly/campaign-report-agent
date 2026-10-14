from report_agent import kpis as K

ROWS = K.load_rows("data/sample_campaigns.csv")


def test_ratios_are_ratios_of_sums():
    k = K.compute(ROWS, "2026-08")
    cur = [r for r in ROWS if r["month"] == "2026-08"]
    spend = sum(r["spend"] for r in cur)
    conv = sum(r["conversions"] for r in cur)
    assert abs(k["totals"]["current"]["cpa"] - spend / conv) < 1e-9


def test_platforms_sum_to_total():
    k = K.compute(ROWS, "2026-08")
    for metric in ("spend", "conversions", "clicks", "revenue"):
        total = sum(p["current"][metric] for p in k["by_platform"])
        assert abs(total - k["totals"]["current"][metric]) < 0.02


def test_roas_excludes_lead_gen_spend():
    k = K.compute(ROWS, "2026-08")
    cur = [r for r in ROWS if r["month"] == "2026-08"]
    ecom_spend = sum(r["spend"] for r in cur if r["goal"] == "ecommerce")
    revenue = sum(r["revenue"] for r in cur)
    assert abs(k["totals"]["current"]["roas"] - revenue / ecom_spend) < 1e-9


def test_prior_month_rolls_over_year():
    assert K.prior_month("2026-01") == "2025-12"


def test_display_change_has_no_negative_zero():
    assert K.fmt_change(-0.00001) == "0.0%"
