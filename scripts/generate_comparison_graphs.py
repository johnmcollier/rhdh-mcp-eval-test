#!/usr/bin/env python3
"""Generate model / metric / topic comparison graphs from per-model summary JSON."""

from __future__ import annotations

import glob
import json
import os
import sys

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

if len(sys.argv) < 2:
    print(f"Usage: {sys.argv[0]} <evaluation-result-directory>")
    sys.exit(1)

RESULT_DIR = sys.argv[1]
OUTPUT_DIR = RESULT_DIR
os.makedirs(OUTPUT_DIR, exist_ok=True)

TARGET_METRICS = [
    "custom:tool_eval",
    "custom:answer_correctness",
    "ragas:faithfulness",  # optional; ignored if absent
]
DISPLAY = {
    "custom:tool_eval": "Tool Eval",
    "custom:answer_correctness": "Answer Correctness",
    "ragas:faithfulness": "Faithfulness",
}

models_data: dict[str, dict] = {}
for model_dir in sorted(os.listdir(RESULT_DIR)):
    model_path = os.path.join(RESULT_DIR, model_dir)
    if not os.path.isdir(model_path):
        continue
    if model_dir.startswith("_") or model_dir in {"graphs", "historical"}:
        continue
    json_files = sorted(glob.glob(os.path.join(model_path, "*_summary.json")))
    if not json_files:
        continue
    # Prefer renamed <model>_summary.json if present
    preferred = os.path.join(model_path, f"{model_dir}_summary.json")
    path = preferred if os.path.exists(preferred) else json_files[-1]
    with open(path) as f:
        models_data[model_dir] = json.load(f)
    print(f"Loaded: {model_dir} <- {os.path.basename(path)}")

if not models_data:
    raise SystemExit(f"No model summaries found under {RESULT_DIR}")

model_rows = []
metric_rows = []
topic_rows = []

for model_name, data in models_data.items():
    results = data.get("results") or []
    if not results:
        continue
    overall_pass = sum(1 for r in results if r.get("result") == "PASS")
    model_rows.append(
        {
            "Model": model_name,
            "Pass Rate": (overall_pass / len(results)) * 100,
        }
    )
    for metric in TARGET_METRICS:
        mres = [r for r in results if r.get("metric_identifier") == metric]
        if not mres:
            continue
        mp = sum(1 for r in mres if r.get("result") == "PASS")
        metric_rows.append(
            {
                "Model": model_name,
                "Metric": DISPLAY.get(metric, metric),
                "Pass Rate": (mp / len(mres)) * 100,
            }
        )
    for r in results:
        tags = r.get("tag") or []
        if isinstance(tags, str):
            tags = [tags]
        topic = tags[0] if tags else "unknown"
        topic_rows.append(
            {
                "Model": model_name,
                "Topic": topic,
                "Pass": 1 if r.get("result") == "PASS" else 0,
            }
        )

sns.set_theme(style="whitegrid")

# Model pass rate
df_model = pd.DataFrame(model_rows).sort_values("Pass Rate", ascending=False)
plt.figure(figsize=(10, 6))
ax = sns.barplot(data=df_model, x="Model", y="Pass Rate", color="#4C78A8")
ax.set_ylim(0, 100)
ax.set_title("MCP Eval — Model Pass Rate")
ax.set_ylabel("Pass Rate (%)")
plt.xticks(rotation=30, ha="right")
plt.tight_layout()
plt.savefig(os.path.join(OUTPUT_DIR, "model-pass-rate.png"), dpi=150)
plt.close()
print("Wrote model-pass-rate.png")

# Metric pass rate heatmap-ish grouped bars
df_metric = pd.DataFrame(metric_rows)
plt.figure(figsize=(12, 6))
ax = sns.barplot(data=df_metric, x="Model", y="Pass Rate", hue="Metric")
ax.set_ylim(0, 100)
ax.set_title("MCP Eval — Metric Pass Rate by Model")
ax.set_ylabel("Pass Rate (%)")
plt.xticks(rotation=30, ha="right")
plt.legend(bbox_to_anchor=(1.02, 1), loc="upper left")
plt.tight_layout()
plt.savefig(os.path.join(OUTPUT_DIR, "model-metric-passrate.png"), dpi=150)
plt.close()
print("Wrote model-metric-passrate.png")

# Topic pass rate
df_topic = pd.DataFrame(topic_rows)
if not df_topic.empty:
    agg = (
        df_topic.groupby(["Model", "Topic"], as_index=False)["Pass"]
        .mean()
        .assign(**{"Pass Rate": lambda d: d["Pass"] * 100})
    )
    plt.figure(figsize=(12, 6))
    ax = sns.barplot(data=agg, x="Topic", y="Pass Rate", hue="Model")
    ax.set_ylim(0, 100)
    ax.set_title("MCP Eval — Topic Pass Rate by Model")
    ax.set_ylabel("Pass Rate (%)")
    plt.xticks(rotation=30, ha="right")
    plt.legend(bbox_to_anchor=(1.02, 1), loc="upper left")
    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, "topic-passrate.png"), dpi=150)
    plt.close()
    print("Wrote topic-passrate.png")
