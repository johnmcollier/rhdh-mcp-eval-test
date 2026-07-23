# RHDH MCP Evaluation

Campaign artifacts for evaluating Red Hat Developer Hub / Backstage MCP tools
from [`rhdh-plugins/workspaces/mcp-integrations`](https://github.com/redhat-developer/rhdh-plugins/tree/main/workspaces/mcp-integrations)
(software-catalog, scaffolder, and techdocs overlays).

**Canonical repo:** https://github.com/redhat-ai-dev/rhdh-mcp-eval

Scoring uses
[lightspeed-evaluation](https://github.com/lightspeed-core/lightspeed-evaluation)
(`lightspeed-eval` CLI) with offline `custom:tool_eval` only
(`agents.enabled: false`). This is not the Lightspeed RAG / `lsdataset` pipeline.

## Layout

| Path | Purpose |
| --- | --- |
| `categories.yaml` | Task category definitions |
| `dataset/eval_data.yaml` | Golden prompts, expected tool calls, recorded traces |
| `config/system-offline-tool-eval.yaml` | Offline `tool_eval` system config |
| `evaluation-result/` | Checked-in campaign outputs |
| `scripts/generate_traces.py` | OpenAI agent → live MCP → fill `tool_calls` |

## Fixture assumptions

Traces were collected against the local `mcp-integrations` demo catalog:

- Owners such as `payments-team` and `security-team`
- Entities such as `consent-management-api` / payment APIs
- **Template kind count is 0** → `execute-template` is not scored; write coverage uses sandbox-safe `validate-scaffolder` / `dry-run-template` instead
- TechDocs entity list may be empty depending on local indexing; multi-step retrieve is optional when fetch returns nothing

Prefer overlay tools (`*-mcp-extras.*`) over upstream duplicates when both exist.

## Prerequisites

1. Local RHDH/Backstage with MCP actions on the **backend**
   (`http://localhost:7007/api/mcp-actions/v1`). The frontend (`:3000`) is not the MCP server.
2. `MCP_TOKEN` matching the static token configured for MCP external access.
3. OpenAI API access for trace generation (agent under test).
4. Clone of [lightspeed-evaluation](https://github.com/lightspeed-core/lightspeed-evaluation) with `uv sync`.

Credentials stay in the environment or gitignored local files (see `.gitignore`).

## Generate traces

```bash
python3 -m venv .venv && .venv/bin/pip install -r scripts/requirements.txt

export MCP_TOKEN=...
export MCP_URL=http://localhost:7007/api/mcp-actions/v1

.venv/bin/python scripts/generate_traces.py \
  --openai-key-file "$HOME/path/to/openai-key" \
  --no-response \
  --output dataset/eval_data.with-traces.yaml
```

Review `tool_calls`, adjust `expected_tool_calls` in `dataset/eval_data.yaml` where needed,
then copy `tool_calls` into `eval_data.yaml` for offline scoring.
`*.with-traces.yaml` is gitignored (may contain large tool payloads).

## Score (offline tool_eval)

```bash
export OPENAI_API_KEY=...   # framework boot; unused by tool_eval scoring itself

REPO="$(pwd)"
cd /path/to/lightspeed-evaluation
uv run lightspeed-eval \
  --system-config "$REPO/config/system-offline-tool-eval.yaml" \
  --eval-data "$REPO/dataset/eval_data.yaml"
```

Run from the artifacts repo root (or set an absolute `storage.output_dir`) so results land under
`evaluation-result/rhidp-14578-tool-eval/`.

### What is scored

| Metric | Mode | Notes |
| --- | --- | --- |
| `custom:tool_eval` | Offline | Ordered matching, `full_match: false` (extra helper calls allowed) |
| Answer quality (ragas / judge panel) | Not required for RHIDP-14578 | Optional follow-up |

Coverage in the checked-in campaign:

- **catalog** — list/filter/get/model description
- **techdocs** — fetch + coverage
- **scaffolder-read** — templates, actions, tasks
- **scaffolder-write** — dry-run validate (execute-template skipped; no Templates in fixture)
- **multi_step** — catalog→coverage; techdocs fetch→(optional retrieve)
- **negative** — inspect-only; empty filter

## Latest campaign result

`evaluation-result/rhidp-14578-tool-eval/` — **21/21 PASS** (`custom:tool_eval`, gpt-4o-mini agent traces).

## Related

- Tools under test: `rhdh-plugins/workspaces/mcp-integrations`
- Runner: https://github.com/lightspeed-core/lightspeed-evaluation
- Packaging pattern (RAG, not MCP): https://github.com/redhat-ai-dev/developer-lightspeed-evaluation
- Investigation: [MCP Evaluations for Backstage MCP Tools (RHDH)](https://docs.google.com/document/d/1ikYNJIcfHD2-ZuZkHYYXJir33nx0JxGfy8RsobHwRg8/edit)
- Jira: RHIDP-14578
