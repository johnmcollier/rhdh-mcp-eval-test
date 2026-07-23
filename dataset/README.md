# Dataset

Golden evaluation tasks for RHDH MCP tools.

| File | Purpose |
| --- | --- |
| `eval_data.yaml` | Conversations for `lightspeed-eval` (includes `tool_calls` for offline scoring) |
| `eval_data.with-traces.yaml` | Local regenerate output (gitignored) |

## Schema

Each turn includes:

- `query` — user prompt
- `expected_tool_calls` — gold tool name(s) and arguments (regex supported; alternatives as multiple top-level sets)
- `tool_calls` — what the agent actually did (from live MCP traces)

Tool names use Backstage MCP form: `<pluginId>.<action-name>`  
Example: `software-catalog-mcp-extras.query-catalog-entities`

See `../categories.yaml` for category tags and the root README for fixture assumptions.
