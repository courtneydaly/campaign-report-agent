"""
Run the narrative generator N times per month and score the outputs.

  python -m evals.run_evals --mode offline                      # baseline, no API key
  python -m evals.run_evals --mode llm --runs 5 --months 2026-06 2026-07 2026-08

Writes evals/results/<timestamp>_<mode>.json and prints a summary table:
pass rate, mean number-grounding rate, and issue counts by type.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime
from pathlib import Path

from report_agent import kpis as K
from report_agent.narrate import narrate

from .grounding import check


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="data/sample_campaigns.csv")
    ap.add_argument("--months", nargs="+", default=["2026-06", "2026-07", "2026-08", "2026-09"])
    ap.add_argument("--mode", choices=["offline", "llm"], default="offline")
    ap.add_argument("--runs", type=int, default=1)
    ap.add_argument("--model", default=None)
    args = ap.parse_args()

    rows = K.load_rows(args.input)
    records, issue_counts = [], Counter()
    for month in args.months:
        k = K.compute(rows, month)
        for i in range(args.runs):
            md = narrate(k, mode=args.mode, **({"model": args.model} if args.model else {}))
            res = check(md, k)
            issue_counts.update(kind for kind, _ in res.issues)
            records.append({
                "month": month, "run": i, "passed": res.passed,
                "grounding_rate": round(res.grounding_rate, 4),
                "numbers_checked": res.numbers_checked,
                "directions_checked": res.directions_checked,
                "issues": res.issues, "narrative": md,
            })
            print(f"{month} run {i}: {'PASS' if res.passed else 'FAIL'}  "
                  f"grounding {res.numbers_grounded}/{res.numbers_checked}")

    n = len(records)
    summary = {
        "mode": args.mode, "model": args.model, "runs": n,
        "pass_rate": round(sum(r["passed"] for r in records) / n, 3),
        "mean_grounding_rate": round(sum(r["grounding_rate"] for r in records) / n, 4),
        "issues_by_type": dict(issue_counts),
    }
    out = Path(__file__).parent / "results"
    out.mkdir(exist_ok=True)
    path = out / f"{datetime.now():%Y%m%d_%H%M%S}_{args.mode}.json"
    path.write_text(json.dumps({"summary": summary, "records": records}, indent=2))
    print(json.dumps(summary, indent=2))
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
