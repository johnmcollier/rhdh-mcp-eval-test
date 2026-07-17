# Evaluation results

Checked-in outputs from MCP eval campaigns (CSV / JSON / TXT / graphs).

Layout convention (per campaign or model):

```text
evaluation-result/
  <campaign-or-model>/
    *_detailed.csv
    *_summary.json
    *_summary.txt
    graphs/   # optional
```

Do not commit secrets or raw API keys. Traces in reports should be reviewed for sensitive catalog data before publishing.
