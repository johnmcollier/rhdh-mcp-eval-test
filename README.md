# RHDH MCP Evaluation

Campaign artifacts for evaluating Backstage / Red Hat Developer Hub MCP tools
(software-catalog, scaffolder, and techdocs overlays).

**Repo:** https://github.com/johnmcollier/rhdh-mcp-eval-test

Operational model matches
[developer-lightspeed-evaluation](https://github.com/redhat-ai-dev/developer-lightspeed-evaluation):
curated dataset → on-demand full eval runs → checked-in results.

This repo does **not** contain the evaluation runner. Use
[lightspeed-evaluation](https://github.com/lightspeed-core/lightspeed-evaluation)
(`lightspeed-eval` CLI).

## Layout

| Path | Purpose |
| --- | --- |
| `categories.yaml` | Task category definitions |
| `dataset/` | Golden prompts, expected tool calls, recorded traces |
| `config/` | `lightspeed-eval` system configs |
| `evaluation-result/` | Checked-in campaign outputs |
| `scripts/` | Helpers (e.g. generate MCP tool traces) |

## Prerequisites

| Piece | Detail |
| --- | --- |
| Runner | Clone `lightspeed-evaluation`, `uv sync` |
| MCP server | Backstage/RHDH with MCP actions, e.g. `http://localhost:7007/api/mcp-actions/v1` |
| `MCP_TOKEN` | Bearer token for the MCP endpoint (from your local RHDH auth setup) |
| `OPENAI_API_KEY` | Agent model under test (and framework boot) |
| Vertex judge (optional) | `GOOGLE_APPLICATION_CREDENTIALS` + `GOOGLE_CLOUD_PROJECT` |

Note: MCP is served by the **backend** (typically port `7007`), not the frontend (`3000`).

**Do not commit secrets.** Set credentials via env vars or local key files that are gitignored (see `.gitignore`).

## Offline smoke (tool_eval only)

Scores pre-filled `tool_calls` against `expected_tool_calls`. No live MCP agent required.
Generate traces first (see below), or use a dataset that already includes `tool_calls`.

```bash
export OPENAI_API_KEY=...   # required for lightspeed-eval boot; unused by tool_eval scoring

REPO="$(pwd)"   # this repository root
cd /path/to/lightspeed-evaluation
uv run lightspeed-eval \
  --system-config "$REPO/config/system-offline-tool-eval.yaml" \
  --eval-data "$REPO/dataset/eval_data.yaml"
```

Results are written under `evaluation-result/offline-catalog-smoke/` (see config).
Run `lightspeed-eval` from this repo root (or adjust `storage.output_dir` in the config)
so relative output paths resolve correctly.

## Generate real traces

```bash
python3 -m venv .venv && .venv/bin/pip install -r scripts/requirements.txt

export MCP_TOKEN=...          # your Backstage/RHDH MCP bearer token
export OPENAI_API_KEY=...     # or use --openai-key-file /path/to/key
.venv/bin/python scripts/generate_traces.py \
  --in-place
```

Then score (offline `tool_eval`) as above.

## Next steps

1. Expand coverage across categories in `categories.yaml`.
2. Add a Vertex/Gemini judge config when scoring answer quality.
3. Publish campaign runs under `evaluation-result/<campaign>/`.

## Related

- Tools under test: `rhdh-plugins/workspaces/mcp-integrations`
- Runner: https://github.com/lightspeed-core/lightspeed-evaluation
- Pattern reference: https://github.com/redhat-ai-dev/developer-lightspeed-evaluation
- Investigation: [MCP Evaluations for Backstage MCP Tools (RHDH)](https://docs.google.com/document/d/1ikYNJIcfHD2-ZuZkHYYXJir33nx0JxGfy8RsobHwRg8/edit)
