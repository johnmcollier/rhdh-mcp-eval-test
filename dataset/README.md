# Dataset

Golden evaluation tasks for RHDH MCP tools.

## Files

| File | Purpose |
| --- | --- |
| `eval_data.yaml` | Conversations/turns for `lightspeed-eval` |

## Schema (tool evaluation)

Each turn should include:

- `query` — user prompt
- `expected_tool_calls` — gold tool name(s) and arguments
- `tool_calls` — what the agent actually did (fill from live MCP traces; smoke data may be hand-filled)

Tool names use Backstage MCP form: `<pluginId>.<action-name>`  
Example: `software-catalog-mcp-extras.query-catalog-entities`

See also `../categories.yaml` for category tags.
