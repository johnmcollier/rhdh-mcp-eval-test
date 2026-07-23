# Evaluation results

Checked-in outputs from MCP eval campaigns (CSV / JSON / TXT / graphs).

```text
evaluation-result/
  <campaign-or-model>/
    *_detailed.csv
    *_summary.json
    *_summary.txt
    graphs/   # optional
```

| Campaign | Metric | Result |
| --- | --- | --- |
| `rhidp-14578-tool-eval` | offline `custom:tool_eval` | 21/21 PASS |
| `offline-catalog-smoke` | early 3-turn smoke | historical |

Review reports before publishing if they embed sensitive catalog text.
