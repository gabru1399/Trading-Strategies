#!/usr/bin/env python3
"""Locate the heatmap fetch call-sites across all page chunks: which endpoint
each model uses and the exact params (symbol format, interval, limit, model)."""
import re, glob

files = sorted(glob.glob("/home/z/my-project/scripts/cg-js/heatmap__*.js"))
pats = {
    "v5call":   r"tw\s*\(",
    "v6call":   r"t_\s*\(",
    "v4agg":    r"tS\s*\(",
    "liqMap5":  r"tk\s*\(",
    "exLiqMap": r"tA\s*\(",
    "model":    r"\bmodel\b",
    "endTime":  r"endTime",
    "interval": r"interval\s*[:=]",
}
for f in files:
    try:
        src = open(f, encoding="utf-8", errors="replace").read()
    except Exception:
        continue
    counts = {k: len(re.findall(v, src)) for k, v in pats.items()}
    if counts["model"] or counts["v5call"] or counts["v6call"] or counts["interval"]:
        print(f"{f.split('/')[-1][:52]:52s}", {k: c for k, c in counts.items() if c})
