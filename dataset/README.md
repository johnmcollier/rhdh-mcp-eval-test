# Dataset

Shared golden evaluation tasks for RHDH MCP tools (RHIDP-14578).

| File | Purpose |
| --- | --- |
| `eval_data.yaml` | Shared gold: `query`, `expected_tool_calls`, `expected_response` (no per-model traces) |

Per-model traces (`tool_calls`, `response`, `contexts`) are written under
`evaluation-result/<model>/evaluation_dataset.yaml` by `scripts/generate_traces.py`.

Rebuild gold:

```bash
.venv/bin/python scripts/build_gold_dataset.py
```

Tool names use Backstage MCP form: `<pluginId>.<action-name>`.
