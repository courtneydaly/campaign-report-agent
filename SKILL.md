---
name: campaign-report-agent
description: Write a monthly paid media performance narrative from a campaign export (CSV with month, platform, campaign, impressions, clicks, spend, conversions, revenue, goal). Computes KPIs deterministically, writes the narrative using only pre-formatted numbers, runs a grounding check, and renders a .docx. Use when asked to "do the monthly report" for a campaign export.
---

# Campaign report agent

1. Run `python -m report_agent --input <csv> --month <YYYY-MM> --out out/ --no-check` to compute `out/kpis_<month>.json`. Do not compute any metric yourself.
2. Read the KPI JSON. Write the narrative to `out/narrative_<month>.md` following the rules in `report_agent/narrate.py::SYSTEM_PROMPT` exactly: cite only numbers that appear in a `display` field, copied verbatim, with the four required section headings.
3. Run the grounding check:
   ```bash
   python -c "import json; from evals.grounding import check; k=json.load(open('out/kpis_<month>.json')); print(check(open('out/narrative_<month>.md').read(), k).summary())"
   ```
4. If it fails, fix only the flagged sentences and re-run the check. Do not render until it passes.
5. Render: `python -c "import json; from report_agent.render_docx import render; render(json.load(open('out/kpis_<month>.json')), open('out/narrative_<month>.md').read(), 'out/report_<month>.docx')"`
