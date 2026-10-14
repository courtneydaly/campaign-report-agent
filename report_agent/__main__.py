"""
python -m report_agent --input data/sample_campaigns.csv --month 2026-08 [--mode llm] [--out out/]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import kpis as K
from .narrate import narrate
from .render_docx import render


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="data/sample_campaigns.csv")
    ap.add_argument("--month", required=True, help="YYYY-MM")
    ap.add_argument("--mode", choices=["offline", "llm"], default="offline")
    ap.add_argument("--out", default="out")
    ap.add_argument("--no-check", action="store_true", help="skip the grounding check")
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    k = K.compute(K.load_rows(args.input), args.month)
    (out / f"kpis_{args.month}.json").write_text(json.dumps(k, indent=2, default=str))

    md = narrate(k, mode=args.mode)
    (out / f"narrative_{args.month}.md").write_text(md)

    if not args.no_check:
        from evals.grounding import check

        result = check(md, k)
        print(result.summary())
        if not result.passed:
            raise SystemExit("Narrative failed the grounding check; not rendering. See issues above.")

    path = render(k, md, out / f"report_{args.month}.docx")
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
