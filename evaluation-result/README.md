# Evaluation Results

Per-model MCP evaluation outputs (Lightspeed-style packaging).

## High-level benchmarks

| Visualization | Description |
| --- | --- |
| [model-pass-rate.png](./model-pass-rate.png) | Overall pass rate by agent model |
| [model-metric-passrate.png](./model-metric-passrate.png) | Pass rate by metric × model |
| [topic-passrate.png](./topic-passrate.png) | Pass rate by category tag × model |

## Model directories

- [gpt-4o-mini](./gpt-4o-mini/)
- [gpt-5-mini](./gpt-5-mini/)
- [gpt-5.5](./gpt-5.5/)
- [gemini-2.5-pro](./gemini-2.5-pro/)
- [gemini-2.5-flash-lite](./gemini-2.5-flash-lite/)
- [llama-31-8b](./llama-31-8b/)

Each folder contains `evaluation_dataset.yaml` (gold + that model's traces), summary JSON/TXT/CSV, and per-run graphs.

## Metrics

- `custom:tool_eval`
- `custom:answer_correctness`
- `ragas:faithfulness`

Judge panel: `vertex_ai/gemini-2.5-pro` + `openai/gpt-4o-mini` (max aggregation).

## Historical

Earlier smoke / prototype runs live under [historical/](./historical/).
